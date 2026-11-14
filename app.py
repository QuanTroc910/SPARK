"""Backend Flask -- lớp "cầu nối" giữa frontend và code logic attribute_noise/.

File này KHÔNG chứa logic detect noise gì cả -- nó chỉ làm 3 việc:
  1. Nhận request (file upload, JSON config) từ frontend qua HTTP.
  2. Gọi đúng hàm trong attribute_noise/ (code lõi đã viết từ trước).
  3. Đóng gói kết quả thành JSON, trả ngược lại cho frontend.

Chạy thử: python3 app.py -> server chạy ở http://localhost:5000
"""

import csv
import io
import json
import os
import re
import threading
import uuid
from functools import wraps
from io import StringIO
from pathlib import Path
from typing import Optional

import pandas as pd
from flask import Flask, Response, jsonify, request, session
from flask_cors import CORS

from accounts.db import init_db
from accounts.service import AccountError, authenticate, change_password, get_user, register
from attribute_noise.attribute_handling import (
    DuplicateHandlingChoice,
    DuplicateKeep,
    HandlingAction,
    HandlingChoice,
    apply_handling,
    get_available_actions,
)
from attribute_noise.config import (
    ColumnDType,
    ColumnNoiseConfig,
    CompareOperator,
    CrossFieldRuleConfig,
    DuplicateRowConfig,
    NoiseType,
    RuleType,
    RuleValueType,
)
from attribute_noise.cross_field_rules import FormulaError
from attribute_noise.pipeline import (
    NoiseFinding,
    detect_noise,
    get_flagged_rows,
    guess_column_dtype,
    guess_date_format,
    load_data,
)
from attribute_noise.quick_tools import (
    QuickToolError,
    auto_column_types,
    blank_column_summary,
    find_format_errors,
    quick_handle_blanks,
    quick_remove_duplicates,
    preview_blank_changes,
    preview_duplicate_rows,
    preview_format_errors,
    preview_trim_changes,
    quick_fix_format_noise,
    quick_trim_whitespace,
)
from class_noise.categorical_encoding import one_hot_encode_columns
from class_noise.config import ClassNoiseConfig
from class_noise.confident_learning import detect_class_noise
from class_noise.distance_based import detect_class_noise_distance
from class_noise.ensemble_based import detect_class_noise_ensemble
from class_noise.feature_selection import (
    cap_outliers,
    filter_correlated,
    log_transform,
    rank_by_importance,
    select_by_elbow,
)
from converters.transform import (
    DELIMITER_LABELS,
    ConversionError,
    convert_csv_delimiter,
    csv_text_to_json,
    json_text_to_csv,
)

# MỚI (tài khoản đăng nhập): phục vụ luôn frontend/ từ ĐÚNG Flask này
# (static_folder="frontend", static_url_path="" -- file frontend/style.css
# tự có sẵn ở URL "/style.css", khớp đúng đường dẫn tương đối index.html
# đang dùng, không cần sửa gì bên HTML/JS). LÝ DO bắt buộc phải làm vậy:
# đăng nhập dùng session (cookie) -- cookie chỉ gửi kèm request đáng tin cậy
# khi frontend VÀ backend nằm CÙNG 1 "origin" (cùng domain+port). Trước đây
# frontend mở riêng (file:// hoặc 1 static server khác port) nên LÀ 2 origin
# khác nhau với backend -- cookie đăng nhập sẽ không gửi kèm được 1 cách
# đáng tin cậy (trình duyệt hiện đại chặn/giới hạn cookie "cross-site" khá
# chặt). Gộp chung 1 origin giải quyết TẬN GỐC vấn đề này, không cần đụng
# tới hàng chục chỗ gọi fetch() rải rác trong script.js.
app = Flask(__name__, static_folder="frontend", static_url_path="")

# secret_key: Flask dùng để KÝ (sign) cookie session, chống giả mạo/sửa nội
# dung cookie phía trình duyệt. Đọc từ biến môi trường SPARK_SECRET_KEY nếu
# có (để cố định qua các lần restart), không có thì tự sinh ngẫu nhiên mỗi
# lần khởi động -- GIỚI HẠN ĐÃ BIẾT (demo 1 người dùng): restart server là
# mọi người đang đăng nhập bị đăng xuất (cookie cũ ký bằng key cũ không còn
# hợp lệ) -- chấp nhận được cho quy mô khoá luận, giống tinh thần các giới
# hạn đã ghi nhận ở Bước 5 an toàn (CLAUDE.md mục 13).
app.secret_key = os.environ.get("SPARK_SECRET_KEY") or os.urandom(32)

# CORS: cho phép trình duyệt gọi API này dù frontend chạy ở 1 origin khác.
# Giờ frontend đã được phục vụ CÙNG origin (xem trên) nên về lý thuyết không
# còn bắt buộc nữa, nhưng vẫn giữ lại -- không hại gì, và lỡ có ai mở
# frontend/index.html kiểu cũ (vd đang phát triển dở, mở trực tiếp bằng
# trình duyệt) thì các API KHÔNG CẦN đăng nhập (vd health check) vẫn gọi được.
CORS(app)

init_db()  # tạo bảng users trong SQLite nếu chưa có -- an toàn gọi nhiều lần

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# Lưu tạm DataFrame đã upload trong RAM, key = file_id (uuid ngẫu nhiên).
# Đây là cách làm ĐƠN GIẢN CHO DEMO thôi -- app thật khi deploy nên lưu vào
# database/redis/cloud storage vì lưu trong biến Python thế này sẽ mất hết
# khi server restart, và không chạy được nếu có nhiều server cùng lúc.
UPLOADED_FILES: dict[str, "pd.DataFrame"] = {}

# Lưu tạm DataFrame ĐÃ LÀM SẠCH (sau /api/apply-handling), key = download_id --
# tách riêng dict này với UPLOADED_FILES để không bao giờ ghi đè lên file gốc
# (người dùng có thể muốn thử nhiều phương án xử lý khác nhau trên cùng 1 file
# upload, không nên làm mất bản gốc).
CLEANED_FILES: dict[str, "pd.DataFrame"] = {}

# Bản "đang làm việc" của từng file -- khác UPLOADED_FILES (bản GỐC, không bao
# giờ đổi) ở chỗ WORKING_FILES bị SỬA DẦN qua nhiều lần gọi
# /api/apply-handling-partial (Bước 5 giờ xử lý TỪNG NHÓM lỗi một, không phải
# 1 lần bấm áp dụng hết như trước). Chỉ tạo (copy từ UPLOADED_FILES) khi lần
# đầu người dùng bấm "Áp dụng" cho 1 nhóm nào đó -- xem _get_working_df().
WORKING_FILES: dict[str, "pd.DataFrame"] = {}

# MỚI (tài khoản đăng nhập, multi-user THẬT): ghi nhớ "file_id/download_id
# này thuộc về tài khoản nào" -- cũng chỉ sống trong RAM (giống 3 dict trên,
# KHÔNG cần lưu lâu dài vì bản thân file cũng chỉ sống trong RAM), nhưng
# BẮT BUỘC phải có để kiểm tra quyền sở hữu (xem _require_file_owner() bên
# dưới) -- trước đây KHÔNG có khái niệm "chủ sở hữu" nào, ai biết đúng
# file_id cũng lấy/sửa được, đã giải thích rõ với người dùng đây là lỗ hổng
# cần tài khoản thật mới vá được.
FILE_OWNERS: dict[str, int] = {}
DOWNLOAD_OWNERS: dict[str, int] = {}


def _get_working_df(file_id: str):
    if file_id not in WORKING_FILES:
        original = UPLOADED_FILES.get(file_id)
        if original is None:
            return None
        WORKING_FILES[file_id] = original.copy()
    return WORKING_FILES[file_id]


def _peek_working_df(file_id: str):
    """Giống _get_working_df() nhưng KHÔNG tạo bản "đang làm việc" nếu chưa có
    (chỉ ĐỌC) -- dùng cho dry_run, vì chạy thử không được để lại bất kỳ dấu vết
    nào, kể cả việc sinh ra 1 bản copy mới của cả file trong RAM."""
    working = WORKING_FILES.get(file_id)
    return working if working is not None else UPLOADED_FILES.get(file_id)


# ---------------------------------------------------------------------------
# Lịch sử xử lý ở Bước 5 -- phục vụ nút "Hoàn tác" + nhật ký thao tác.
#
# HANDLING_HISTORY[file_id] là danh sách (CŨ -> MỚI) các lần "Áp dụng" ĐÃ GHI
# THẬT lên bản đang làm việc (dry_run KHÔNG bao giờ ghi vào đây). Mỗi phần tử
# là 1 dict:
#   group_key    -- "cột|loại noise" hoặc "duplicate_row" (để FE biết nhóm nào
#                   đã xử lý, dựng lại nút "Xem sau xử lý" sau khi hoàn tác)
#   column / noise_type -- nhóm lỗi vừa xử lý (column = None với duplicate_row)
#   actions      -- {tên hành động: số dòng}, vd {"remove_row": 4}
#   rows_removed / cells_changed -- tác động THẬT đo được (không phải số dòng
#                   người dùng tick), vd 1 dòng đã bị xoá từ lần trước sẽ không
#                   được tính lại
#   rows_before / rows_after -- tổng số dòng trước/sau
#   snapshot     -- DataFrame TRƯỚC khi áp dụng bước này (hoặc None nếu không
#                   còn hoàn tác được bước này nữa). Không bao giờ gửi cho FE.
#
# Vì sao lưu snapshot bằng THAM CHIẾU mà không cần .copy(): mọi lần sửa đều
# tạo ra DataFrame MỚI (apply_handling() bắt đầu bằng df.copy(), còn xoá trùng
# dòng dùng df.drop() -- cả hai đều trả về object mới), không có chỗ nào sửa
# tại chỗ lên DataFrame đang nằm trong WORKING_FILES. Nên DataFrame "trước khi
# sửa" cứ giữ nguyên là được, không tốn thêm 1 bản copy riêng.
#
# Giới hạn bộ nhớ (3 lớp, vì file có thể lên tới hàng trăm nghìn dòng):
#   - MAX_UNDO_STEPS: chỉ giữ snapshot của N bước GẦN NHẤT.
#   - MAX_HISTORY_LOG: nhật ký chữ giữ tối đa N bước (rất nhẹ).
#   - UNDO_MAX_CELLS: bảng quá lớn (số dòng x số cột vượt ngưỡng) thì KHÔNG lưu
#     snapshot, chỉ còn nút "Về dữ liệu gốc" (luôn dùng được vì bản gốc
#     UPLOADED_FILES không bao giờ bị sửa).
# Giống UPLOADED_FILES/WORKING_FILES: nằm trong RAM, server restart là mất hết.
# ---------------------------------------------------------------------------
HANDLING_HISTORY: dict[str, list[dict]] = {}

# Khoá chung cho MỌI thao tác đọc-rồi-ghi lên WORKING_FILES/HANDLING_HISTORY (áp
# dụng thật, dry-run, hoàn tác, về dữ liệu gốc). Flask chạy threaded=True nên 2
# request có thể chạy chồng nhau: nếu cả hai cùng đọc bản đang làm việc rồi cùng
# ghi lại, bản ghi sau sẽ ĐÈ MẤT thay đổi của bản ghi trước (lost update). Có khoá
# thì mỗi lần Áp dụng thấy đúng kết quả của lần trước. RLock để route gọi lồng
# nhau không tự khoá chết mình. Chấp nhận được cho demo 1 người dùng.
HANDLING_LOCK = threading.RLock()

# Chỉ giữ lịch sử (kèm snapshot) của N file thao tác GẦN NHẤT -- mỗi lần upload
# sinh 1 file_id mới và server không có chỗ nào xoá file_id cũ, nếu không giới hạn
# thì snapshot của mọi file từng xử lý sẽ nằm mãi trong RAM.
MAX_FILES_WITH_HISTORY = 3
MAX_UNDO_STEPS = 5
MAX_HISTORY_LOG = 20
UNDO_MAX_CELLS = 5_000_000


def _as_bool(value) -> bool:
    """Đọc cờ true/false từ JSON một cách CHẶT: bool("false") trong Python là True
    (chuỗi không rỗng), nên không dùng bool() thẳng -- gửi nhầm "false" dạng chuỗi
    mà bị hiểu là "chạy thử" (hoặc ngược lại) sẽ làm sai hành vi xoá dữ liệu."""
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes")
    return bool(value)


def _record_history(file_id: str, entry: dict, snapshot_df) -> None:
    """Ghi 1 bước vừa áp dụng vào lịch sử, đồng thời dọn bớt snapshot cũ để
    không phình RAM. `snapshot_df` là DataFrame TRƯỚC khi áp dụng bước này."""
    # Chuyển file_id lên CUỐI dict (= "vừa dùng gần nhất"), rồi bỏ lịch sử của các
    # file cũ nhất nếu đang giữ quá MAX_FILES_WITH_HISTORY file.
    history = HANDLING_HISTORY.pop(file_id, [])
    HANDLING_HISTORY[file_id] = history
    while len(HANDLING_HISTORY) > MAX_FILES_WITH_HISTORY:
        HANDLING_HISTORY.pop(next(iter(HANDLING_HISTORY)))

    can_snapshot = snapshot_df.shape[0] * snapshot_df.shape[1] <= UNDO_MAX_CELLS
    entry["snapshot"] = snapshot_df if can_snapshot else None
    history.append(entry)

    if not can_snapshot:
        # Bước mới nhất không hoàn tác được -> các snapshot cũ hơn cũng không
        # còn "với tới" được (hoàn tác luôn lùi từng bước từ mới nhất), giữ
        # lại chỉ tốn RAM vô ích.
        for older in history[:-1]:
            older["snapshot"] = None

    # Chỉ giữ snapshot của MAX_UNDO_STEPS bước gần nhất.
    for older in history[:-MAX_UNDO_STEPS]:
        older["snapshot"] = None

    # Nhật ký chữ chỉ giữ MAX_HISTORY_LOG bước gần nhất.
    del history[:-MAX_HISTORY_LOG]


def _history_payload(file_id: str) -> dict:
    """Phần lịch sử gửi cho FE: bỏ snapshot (DataFrame không JSON hoá được và
    cũng không nên gửi), thêm cờ `undoable` cho từng bước và `can_undo` chung."""
    entries = HANDLING_HISTORY.get(file_id, [])
    return {
        "entries": [
            {**{k: v for k, v in e.items() if k != "snapshot"}, "undoable": e["snapshot"] is not None}
            for e in entries
        ],
        "can_undo": bool(entries) and entries[-1]["snapshot"] is not None,
        "undo_limit": MAX_UNDO_STEPS,
    }


def _summarize_change(before, after, column):
    """Đo tác động THẬT của 1 lần xử lý: (số dòng bị xoá, số ô bị sửa giá trị).
    Dùng chung cho dry_run (hiện "Sẽ xoá N dòng") lẫn nhật ký lịch sử, để 2 nơi
    luôn cùng 1 con số. Ô "bị sửa" chỉ đếm trên cột `column` (None = xoá trùng
    dòng, không sửa ô nào) và chỉ trên các dòng CÒN LẠI sau xử lý."""
    rows_removed = len(before) - len(after)
    cells_changed = 0
    if column is not None and column in before.columns:
        common = after.index.intersection(before.index)
        before_values = before.loc[common, column].fillna("").astype(str)
        after_values = after.loc[common, column].fillna("").astype(str)
        cells_changed = int((before_values != after_values).sum())
    return rows_removed, cells_changed


def _detect_config_from_partial_payload(payload: dict):
    """Đọc phần cấu hình detect (column_configs, cross_field_rules,
    duplicate_row) trong payload của các route Bước 5 -- để chạy lại
    detect_noise() trên bản mới sau khi sửa/hoàn tác/quay về gốc. Dùng chung cho
    /api/apply-handling-partial, /api/undo-handling, /api/reset-working."""
    column_configs = [_config_from_json(item) for item in payload.get("column_configs", [])]
    cross_field_rules = [
        _cross_field_rule_from_json(item) for item in payload.get("cross_field_rules", [])
    ]
    duplicate_payload = payload.get("duplicate_row")
    duplicate_row_config = (
        DuplicateRowConfig(subset_columns=duplicate_payload.get("subset_columns"))
        if duplicate_payload
        else None
    )
    return column_configs, cross_field_rules, duplicate_row_config


def _build_detect_response(df, findings) -> dict:
    """Đóng gói kết quả detect thành đúng dạng JSON như /api/detect-noise
    (FE tái dùng thẳng renderStep4()). row_number = index + 1 (xem quyết định
    thiết kế #5 trong CLAUDE.md)."""
    flagged_rows_df = get_flagged_rows(df, findings)
    flagged_rows_out = flagged_rows_df.copy()
    flagged_rows_out.insert(0, "row_number", flagged_rows_out.index + 1)
    return {
        "total_rows": len(df),
        "total_flagged_rows": len(flagged_rows_df),
        "findings": [
            {
                "row_number": int(f.row_index) + 1,
                "column": f.column,
                "noise_type": f.noise_type,
                "value": f.value,
            }
            for f in findings
        ],
        "flagged_rows": flagged_rows_out.to_dict(orient="records"),
    }


@app.route("/")
def serve_frontend():
    """Trả về frontend/workspace.html -- giao diện "Denoise" mới, GỘP luôn
    trang chủ/Guide/Security/Privacy (công khai, khách xem được không cần
    đăng nhập) lẫn các công cụ (Cần cấu hình, Class Noise, Free Tools,
    Convert, Hồ sơ -- những mục này tự bật form đăng nhập nếu chưa có tài
    khoản). Đây là "mặt tiền" thật sự của web, thay cho landing.html + index.html
    cũ (2 file cũ vẫn còn trong frontend/ và vẫn mở được qua /landing.html,
    /index.html nhờ static_folder, chỉ là "/" không trỏ vào đó nữa).
    Flask tự phục vụ các file tĩnh còn lại (workspace.css, workspace.js,
    style.css...) nhờ static_folder="frontend" đã khai báo ở trên, không cần
    route riêng cho từng file."""
    return app.send_static_file("workspace.html")


def login_required(view_func):
    """Decorator: route nào gắn @login_required sẽ trả lỗi 401 ngay nếu
    chưa đăng nhập, không chạy logic thật của route. Dùng cho route KHÔNG
    gắn với 1 file_id có sẵn (vd /api/upload -- lúc này CHƯA có file_id nào
    để kiểm tra chủ sở hữu, vì chính request này mới TẠO ra file_id)."""

    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Cần đăng nhập trước"}), 401
        return view_func(*args, **kwargs)

    return wrapped


def _require_file_owner(file_id):
    """Kiểm tra người đang đăng nhập có đúng là chủ sở hữu file_id này
    không. Trả về None nếu hợp lệ (route gọi tiếp bình thường); ngược lại
    trả (response, status_code) để route `return` thẳng luôn.

    Cố tình dùng CHUNG 1 thông báo lỗi cho CẢ 3 trường hợp (chưa đăng nhập /
    file_id không tồn tại / file_id tồn tại nhưng của người khác) -- không
    tiết lộ qua nội dung lỗi rằng 1 file_id "có tồn tại nhưng không phải
    của bạn" (giống cách CYD mô tả: "requests for another account's
    dataset are answered as if it did not exist", đã trao đổi với người dùng).
    """
    user_id = session.get("user_id")
    owner_id = FILE_OWNERS.get(file_id)
    if user_id is None or owner_id is None or owner_id != user_id:
        return jsonify({"error": "file_id không tồn tại, hãy upload lại file"}), 404
    return None


def _require_download_owner(download_id):
    """Giống _require_file_owner() nhưng cho download_id (CLEANED_FILES) --
    tách riêng vì đây là 2 "không gian" file_id khác nhau, không dùng
    chung FILE_OWNERS được."""
    user_id = session.get("user_id")
    owner_id = DOWNLOAD_OWNERS.get(download_id)
    if user_id is None or owner_id is None or owner_id != user_id:
        return jsonify({"error": "download_id không tồn tại hoặc đã hết hạn"}), 404
    return None


@app.route("/api/auth/register", methods=["POST"])
def auth_register():
    """Đăng ký tài khoản mới -- đăng ký xong TỰ ĐỘNG đăng nhập luôn (đỡ phải
    đăng ký xong lại đăng nhập lại ngay, trải nghiệm phổ biến ở hầu hết web)."""
    payload = request.get_json() or {}
    try:
        user = register(payload.get("username", ""), payload.get("password", ""))
    except AccountError as exc:
        return jsonify({"error": str(exc)}), 400
    session["user_id"] = user.id
    # Trả lồng trong "user" (kèm created_at) giống /api/auth/me -- để frontend
    # dùng CHUNG 1 shape response cho cả 3 route (đăng ký/đăng nhập/kiểm tra
    # trạng thái), không phải nhớ 2 cách đọc response khác nhau.
    return jsonify({"user": {"id": user.id, "username": user.username, "created_at": user.created_at}})


@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    payload = request.get_json() or {}
    try:
        user = authenticate(payload.get("username", ""), payload.get("password", ""))
    except AccountError as exc:
        return jsonify({"error": str(exc)}), 400
    session["user_id"] = user.id
    return jsonify({"user": {"id": user.id, "username": user.username, "created_at": user.created_at}})


@app.route("/api/auth/logout", methods=["POST"])
def auth_logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/auth/me", methods=["GET"])
def auth_me():
    """Frontend gọi route này lúc tải trang để biết "ai đang đăng nhập"
    (hoặc chưa đăng nhập ai cả) -- quyết định hiện thẳng Bước 1 hay bắt
    đăng nhập trước. Trả {"user": null} thay vì lỗi 401 vì đây là trạng
    thái BÌNH THƯỜNG (chưa đăng nhập), không phải lỗi."""
    user_id = session.get("user_id")
    if user_id is None:
        return jsonify({"user": None})
    user = get_user(user_id)
    if user is None:
        # Tài khoản đã bị xoá khỏi DB (vd người dùng khác xoá CSDL thủ công)
        # nhưng cookie session cũ vẫn còn hợp lệ -- dọn sạch session để
        # tránh kẹt ở trạng thái "tưởng đã đăng nhập" nhưng không làm gì được.
        session.clear()
        return jsonify({"user": None})
    return jsonify({"user": {"id": user.id, "username": user.username, "created_at": user.created_at}})


@app.route("/api/auth/change-password", methods=["POST"])
@login_required
def auth_change_password():
    payload = request.get_json() or {}
    try:
        change_password(
            session["user_id"], payload.get("old_password", ""), payload.get("new_password", "")
        )
    except AccountError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True})


@app.route("/api/upload", methods=["POST"])
@login_required
def upload_file():
    """Bước 1: Frontend gửi file CSV/Excel lên đây.

    Trả về file_id (để các request sau tham chiếu tới đúng file này), danh
    sách tên cột, và `guessed_dtypes` -- **MỚI**: đoán sẵn kiểu dữ liệu hợp
    lý nhất cho TỪNG cột (`guess_column_dtype()`, xem pipeline.py) để frontend
    TỰ CHỌN SẴN trong dropdown "Kiểu dữ liệu" ở Bước 3, đỡ người dùng phải tự
    đổi từng cột một (mặc định cũ luôn là "text" cho mọi cột). Chỉ là gợi ý --
    người dùng vẫn đổi lại bình thường, backend không ép buộc gì.
    """
    file = request.files.get("file")
    if file is None:
        return jsonify({"error": "Thiếu file trong request"}), 400

    file_id = str(uuid.uuid4())
    save_path = UPLOAD_DIR / f"{file_id}_{file.filename}"
    file.save(save_path)

    df = load_data(str(save_path))  # hàm có sẵn trong attribute_noise/pipeline.py
    UPLOADED_FILES[file_id] = df
    FILE_OWNERS[file_id] = session["user_id"]

    return jsonify(
        {
            "file_id": file_id,
            "columns": list(df.columns),
            "row_count": len(df),
            "guessed_dtypes": {col: guess_column_dtype(df[col]) for col in df.columns},
        }
    )


def _config_from_json(item: dict) -> ColumnNoiseConfig:
    """Convert 1 object JSON (frontend gửi lên) thành ColumnNoiseConfig.

    Đây chính là "hàm nhỏ" mình nhắc ở tin nhắn trước -- nó khớp field JSON
    với đúng field của ColumnNoiseConfig trong attribute_noise/config.py.
    .get(...) dùng cho các field KHÔNG bắt buộc, để frontend không gửi cũng
    không lỗi (mặc định là None hoặc giá trị mặc định của dataclass).
    """
    return ColumnNoiseConfig(
        column=item["column"],
        dtype=ColumnDType(item["dtype"]),
        noise_types=[NoiseType(nt) for nt in item["noise_types"]],
        min_value=item.get("min_value"),
        max_value=item.get("max_value"),
        date_format=item.get("date_format"),
        valid_categories=item.get("valid_categories"),
        outlier_method=item.get("outlier_method", "iqr"),
        outlier_threshold=item.get("outlier_threshold", 1.5),
        category_similarity_threshold=item.get("category_similarity_threshold", 0.85),
        disallowed_chars_pattern=item.get("disallowed_chars_pattern"),
    )


def _cross_field_rule_from_json(item: dict) -> CrossFieldRuleConfig:
    """Convert 1 object JSON rule liên cột (frontend gửi lên) thành
    CrossFieldRuleConfig -- vai trò giống _config_from_json() ở trên, nhưng
    cho rule liên cột (compare/conditional/formula/functional_dependency).

    Frontend chỉ gửi các field ỨNG VỚI rule_type đang chọn (vd rule "compare"
    thì không gửi if_column/then_column...), nên mọi field ở đây dùng
    .get(...) với default None/giá trị mặc định -- không bắt buộc phải có đủ.
    """
    return CrossFieldRuleConfig(
        rule_type=RuleType(item["rule_type"]),
        label=item.get("label"),
        date_format=item.get("date_format"),
        column_a=item.get("column_a"),
        operator=CompareOperator(item["operator"]) if item.get("operator") else None,
        column_b=item.get("column_b"),
        value_type=RuleValueType(item.get("value_type", "number")),
        if_column=item.get("if_column"),
        if_operator=CompareOperator(item["if_operator"]) if item.get("if_operator") else None,
        if_value=item.get("if_value"),
        if_value_type=RuleValueType(item.get("if_value_type", "text")),
        then_column=item.get("then_column"),
        then_operator=CompareOperator(item["then_operator"]) if item.get("then_operator") else None,
        then_value=item.get("then_value"),
        then_value_type=RuleValueType(item.get("then_value_type", "text")),
        formula=item.get("formula"),
        tolerance=item.get("tolerance", 0.01),
        determinant_column=item.get("determinant_column"),
        dependent_column=item.get("dependent_column"),
    )


@app.route("/api/detect-noise", methods=["POST"])
def detect_noise_api():
    """Bước 2: Frontend gửi lên file_id (từ bước upload) + cấu hình noise
    của từng cột (JSON) mà user đã chọn trên giao diện.

    Route này chỉ làm nhiệm vụ "phiên dịch" JSON <-> Python object, còn việc
    detect thật sự vẫn do detect_noise() trong attribute_noise/pipeline.py làm.
    """
    payload = request.get_json()
    file_id = payload.get("file_id")
    owner_error = _require_file_owner(file_id)
    if owner_error:
        return owner_error
    # Detect trên bản ĐANG LÀM VIỆC nếu người dùng đã xử lý ở Bước 5 (còn chưa thì
    # là bản gốc). Trước đây luôn detect trên bản GỐC, nên Detect lại từ Bước 3 sau
    # khi đã xử lý sẽ hiện lại đúng những lỗi đã sửa/xoá, lệch với bản đang làm việc
    # và lịch sử trên server (Bước 5 báo "đã xử lý" mà dữ liệu không đổi). Bản đang
    # làm việc luôn khớp với những gì Bước 5 đang thao tác nên 2 bước nhất quán;
    # muốn detect lại từ đầu thì bấm "Về dữ liệu gốc" ở Bước 5.
    df = _peek_working_df(file_id)
    if df is None:
        return jsonify({"error": "file_id không tồn tại, hãy upload lại file"}), 404

    # "Phiên dịch" toàn bộ JSON của request thành các object Python mà
    # detect_noise() cần. Việc này (parse rule_type/operator/value_type từ
    # chuỗi JSON, hoặc formula sai cú pháp) CÓ THỂ lỗi nếu người dùng khai
    # rule sai (vd chọn cột không tồn tại, gõ formula sai) -- nên bọc trong
    # try/except để trả lỗi rõ ràng (400) cho FE hiển thị, thay vì để Flask
    # trả lỗi 500 chung không rõ nguyên nhân.
    try:
        column_configs = [_config_from_json(item) for item in payload.get("column_configs", [])]

        duplicate_row_config = None
        if payload.get("check_duplicate_row"):
            duplicate_row_config = DuplicateRowConfig(
                subset_columns=payload.get("duplicate_subset_columns")
            )

        cross_field_rules = [
            _cross_field_rule_from_json(item) for item in payload.get("cross_field_rules", [])
        ]

        findings = detect_noise(
            df,
            column_configs,
            duplicate_row_config=duplicate_row_config,
            cross_field_rules=cross_field_rules,
        )
    except (FormulaError, ValueError, KeyError, TypeError, re.error) as exc:
        return jsonify({"error": f"Cấu hình rule/noise không hợp lệ: {exc}"}), 400

    flagged_rows_df = get_flagged_rows(df, findings)

    # Pandas đánh số dòng bắt đầu từ 0 (dòng dữ liệu đầu tiên = 0), nhưng hầu
    # hết công cụ xem CSV/spreadsheet (Excel, PyCharm CSV viewer...) đánh số
    # dòng dữ liệu bắt đầu từ 1. Cộng thêm 1 ở đây để "row_number" trả về
    # khớp với số dòng người dùng nhìn thấy khi mở file bằng các công cụ đó,
    # tránh nhầm lẫn kiểu lệch 1 dòng.
    flagged_rows_out = flagged_rows_df.copy()
    flagged_rows_out.insert(0, "row_number", flagged_rows_out.index + 1)
    flagged_rows_json = flagged_rows_out.to_dict(orient="records")

    return jsonify(
        {
            "total_rows": len(df),
            "total_flagged_rows": len(flagged_rows_df),
            "findings": [
                {
                    "row_number": int(f.row_index) + 1,
                    "column": f.column,
                    "noise_type": f.noise_type,
                    "value": f.value,
                }
                for f in findings
            ],
            "flagged_rows": flagged_rows_json,
        }
    )


def _handling_choice_from_json(item: dict) -> HandlingChoice:
    """Convert 1 object JSON (frontend gửi lên ở Bước 4 -- xử lý noise) thành
    HandlingChoice, vai trò giống _config_from_json()/_cross_field_rule_from_json()
    ở trên nhưng cho lựa chọn XỬ LÝ thay vì lựa chọn DETECT."""
    return HandlingChoice(
        column=item["column"],
        noise_type=NoiseType(item["noise_type"]),
        action=HandlingAction(item["action"]),
        fixed_value=item.get("fixed_value"),
    )


def _duplicate_handling_from_json(item: dict) -> DuplicateHandlingChoice:
    return DuplicateHandlingChoice(
        keep=DuplicateKeep(item.get("keep", "first")),
        subset_columns=item.get("subset_columns"),
    )


@app.route("/api/class-noise/detect", methods=["POST"])
def class_noise_detect_api():
    """Hướng Class Noise, Bước 3 -> 4: frontend gửi lên file_id (từ /api/upload,
    DÙNG CHUNG với hướng attribute -- không có endpoint upload riêng) +
    label_column + feature_columns + method (+ tham số riêng từng method).

    **method** (mới, 3 giá trị khớp đúng Bảng 6 Gupta & Gupta 2019):
      - "single_learning" (mặc định, giữ nguyên hành vi cũ): Random Forest +
        5-fold CV + Confident Learning (class_noise/confident_learning.py).
        Tham số riêng: n_estimators, cv_folds.
      - "distance_based": Mutual k-Nearest Neighbor, N13
        (class_noise/distance_based.py) -- KHÔNG train model nào, chỉ xét
        khoảng cách. Tham số riêng: k.
      - "ensemble_based": N29 (class_noise/ensemble_based.py) -- 3 classifier
        khác họ (LogisticRegression, GaussianNB, LinearSVC) biểu quyết qua
        cross-validation. Tham số riêng: cv_folds.
    Route này CHỈ "phiên dịch" JSON <-> Python object + JSON-hoá kết quả,
    không có logic detect nào viết thêm ở đây -- logic thật nằm hết ở 3 module
    class_noise/confident_learning.py và class_noise/distance_based.py.

    **MỚI**: feature_columns giờ CHO PHÉP cả cột CHỮ (category), không chỉ cột
    số như trước -- cột chữ được tự động ONE-HOT ENCODE (drop-first, xem
    class_noise/categorical_encoding.py) trước khi đưa vào 3 thuật toán.
    Validate/báo lỗi "cột đặc trưng phải là cột số" đã bị XOÁ, thay bằng
    bước encode này.

    Response LUÔN có field "method" ở gốc để frontend biết nên render kiểu
    diagnostics/findings nào (2 phương pháp có hình dạng diagnostics KHÁC
    NHAU -- distance-based không có khái niệm cv_accuracy/per_class_report/
    confusion_matrix vì không train model). Findings được CHUẨN HOÁ chung tên
    trường (`suggested_label`, `score`) cho cả 2 method để bảng "danh sách
    dòng nghi ngờ" ở frontend dùng chung được 1 cách render.

    **MỚI (giữ nguyên từ trước)**: trước khi chạy, LUÔN tự động áp dụng Bước 3
    của pipeline giảm cột (`cap_outliers()` + `log_transform()`, xem
    class_noise/feature_selection.py) lên feature_columns -- áp dụng cho CẢ 2
    method vì đều cần feature_columns đã được làm sạch outlier/phân phối.

    CẢNH BÁO quan trọng cho người chạy thử: với file lớn (hàng trăm nghìn
    dòng), "single_learning" (train Random Forest qua Cross-Validation) có
    thể mất VÀI PHÚT; "distance_based" thường nhanh hơn nhiều vì không train
    model nào. Route này chạy ĐỒNG BỘ (block luôn request), không có thanh
    tiến trình -- chấp nhận được cho quy mô 1 công cụ demo khoá luận.
    """
    payload = request.get_json()
    file_id = payload.get("file_id")
    owner_error = _require_file_owner(file_id)
    if owner_error:
        return owner_error
    df = UPLOADED_FILES.get(file_id)
    if df is None:
        return jsonify({"error": "file_id không tồn tại, hãy upload lại file"}), 404

    method = payload.get("method") or "single_learning"
    if method not in ("single_learning", "distance_based", "ensemble_based"):
        return jsonify({"error": f"method không hợp lệ: {method}"}), 400

    label_column = payload.get("label_column")
    feature_columns = payload.get("feature_columns") or []
    if not label_column:
        return jsonify({"error": "Thiếu label_column"}), 400
    if not feature_columns:
        return jsonify({"error": "Phải chọn ít nhất 1 cột đặc trưng"}), 400
    if label_column in feature_columns:
        return jsonify({"error": "Cột nhãn không được trùng với cột đặc trưng"}), 400
    missing_cols = [c for c in [label_column, *feature_columns] if c not in df.columns]
    if missing_cols:
        return jsonify({"error": f"Cột không tồn tại trong file: {', '.join(missing_cols)}"}), 400

    # MỚI: cột đặc trưng được chọn giờ có thể là cột CHỮ (category) -- tự động
    # ONE-HOT ENCODE (class_noise/categorical_encoding.py) trước khi đưa vào
    # 3 thuật toán detect, thay vì từ chối như trước. Lý do chọn one-hot thay
    # vì Label/Target Encoding, và vì sao dùng kiểu "drop-first": xem docstring
    # module categorical_encoding.py (tóm tắt: Label Encoding áp đặt thứ tự giả
    # hại thuật toán tính khoảng cách/đường biên tuyến tính; Target Encoding
    # rò rỉ chính nhãn đang đi tìm lỗi vào đặc trưng -- không hợp bài toán
    # phát hiện CLASS NOISE).
    categorical_feature_columns = [c for c in feature_columns if not _is_mostly_numeric(df[c])]
    numeric_feature_columns = [c for c in feature_columns if c not in categorical_feature_columns]

    if categorical_feature_columns:
        encoded_df, encoded_info = one_hot_encode_columns(df, categorical_feature_columns)
        # feature_columns THẬT SỰ đưa vào 3 thuật toán detect: cột số gốc +
        # các cột one-hot mới sinh ra (thay cho tên cột chữ gốc, lúc này đã
        # không còn tồn tại trong encoded_df).
        detect_feature_columns = numeric_feature_columns + [i.encoded_column for i in encoded_info]
    else:
        encoded_df = df
        detect_feature_columns = numeric_feature_columns  # == feature_columns nguyên vẹn

    # Bước 3 (xem class_noise/feature_selection.py + CLAUDE.md mục 9): LUÔN áp
    # dụng cap outlier (về biên IQR) + log-transform TRƯỚC khi chạy -- áp dụng
    # cho CẢ 3 method, không phải tuỳ chọn. CHỈ áp dụng lên cột SỐ GỐC
    # (numeric_feature_columns) -- cột one-hot (toàn 0/1) KHÔNG cần cap/log:
    # IQR của cột gần như toàn 1 giá trị sẽ suy biến (tự động bị cap_outliers()
    # bỏ qua), còn log1p sẽ biến 0/1 "sạch" thành 0/0.693 không cần thiết,
    # không có lợi gì cho 1 cột vốn đã nhị phân sẵn.
    cleaned_df = cap_outliers(encoded_df, numeric_feature_columns)
    cleaned_df = log_transform(cleaned_df, numeric_feature_columns)

    if method == "distance_based":
        dist_config = ClassNoiseConfig(label_column=label_column, feature_columns=detect_feature_columns)
        k = int(payload.get("k") or 5)
        try:
            result = detect_class_noise_distance(cleaned_df, dist_config, k=k)
        except (ValueError, KeyError) as exc:
            return jsonify({"error": f"Không chạy được với cấu hình này: {exc}"}), 400

        diag = result.diagnostics
        return jsonify(
            {
                "method": "distance_based",
                "diagnostics": {
                    "n_rows_total": diag.n_rows_total,
                    "n_rows_used": diag.n_rows_used,
                    "k": diag.k,
                    "n_rows_with_mutual_neighbors": diag.n_rows_with_mutual_neighbors,
                    "class_names": diag.class_names,
                    "class_counts": diag.class_counts,
                },
                "findings": [
                    {
                        "row_number": f.row_number,
                        "recorded_label": f.recorded_label,
                        "suggested_label": f.suggested_label,
                        "score": f.disagreement_ratio,
                    }
                    for f in result.findings
                ],
            }
        )

    if method == "ensemble_based":
        ens_config = ClassNoiseConfig(label_column=label_column, feature_columns=detect_feature_columns)
        cv_folds = int(payload.get("cv_folds") or 5)
        try:
            result = detect_class_noise_ensemble(cleaned_df, ens_config, cv_folds=cv_folds)
        except (ValueError, KeyError) as exc:
            return jsonify({"error": f"Không chạy được với cấu hình này: {exc}"}), 400

        diag = result.diagnostics
        return jsonify(
            {
                "method": "ensemble_based",
                "diagnostics": {
                    "n_rows_total": diag.n_rows_total,
                    "n_rows_used": diag.n_rows_used,
                    "classifier_names": diag.classifier_names,
                    "per_classifier_accuracy": diag.per_classifier_accuracy,
                    "majority_baseline_accuracy": diag.majority_baseline_accuracy,
                    "class_names": diag.class_names,
                    "class_counts": diag.class_counts,
                },
                "findings": [
                    {
                        "row_number": f.row_number,
                        "recorded_label": f.recorded_label,
                        "suggested_label": f.suggested_label,
                        "score": f.disagree_ratio,
                    }
                    for f in result.findings
                ],
            }
        )

    # method == "single_learning" (hành vi gốc, Confident Learning + Random Forest)
    config = ClassNoiseConfig(
        label_column=label_column,
        feature_columns=detect_feature_columns,
        n_estimators=int(payload.get("n_estimators") or 300),
        cv_folds=int(payload.get("cv_folds") or 5),
    )
    try:
        result = detect_class_noise(cleaned_df, config)
    except (ValueError, KeyError) as exc:
        # Hay gặp nhất: 1 lớp có quá ít dòng dùng được so với cv_folds (vd chọn
        # cv_folds=5 nhưng lớp hiếm chỉ có 3 dòng sau khi loại bỏ dòng hỏng) --
        # StratifiedKFold của sklearn tự raise ValueError trong trường hợp này.
        return jsonify({"error": f"Không chạy được với cấu hình này: {exc}"}), 400

    diag = result.diagnostics
    return jsonify(
        {
            "method": "single_learning",
            "diagnostics": {
                "n_rows_total": diag.n_rows_total,
                "n_rows_used": diag.n_rows_used,
                "class_names": diag.class_names,
                "class_counts": diag.class_counts,
                "cv_accuracy": diag.cv_accuracy,
                "majority_baseline_accuracy": diag.majority_baseline_accuracy,
                "class_thresholds": diag.class_thresholds,
                "per_class_report": diag.per_class_report,
                "confusion_count_matrix": {
                    "class_names": diag.class_names,
                    # .tolist() tự ép numpy int64 (kiểu pandas hay dùng) thành
                    # int thường -- jsonify() không serialize được numpy int64.
                    "rows": diag.confusion_count_matrix.values.tolist(),
                },
            },
            "findings": [
                {
                    "row_number": f.row_number,
                    "recorded_label": f.recorded_label,
                    "suggested_label": f.confident_label,
                    "score": f.margin,
                }
                for f in result.findings
            ],
        }
    )


def _is_mostly_numeric(series, min_ratio: float = 0.9) -> bool:
    """Coi 1 cột là "đủ số" để làm candidate cho Feature Importance nếu ít
    nhất `min_ratio` (mặc định 90%) các ô KHÔNG RỖNG của nó ép được thành số.

    Cần lọc TRƯỚC khi đưa vào rank_by_importance(), vì hàm đó yêu cầu MỌI
    candidate đều phải là số TRÊN CÙNG 1 DÒNG mới tính dòng đó "dùng được" --
    nếu lỡ đưa nguyên 1 cột CHỮ (vd "workclass") vào làm candidate, cột đó
    luôn luôn NaN sau khi ép số, khiến TOÀN BỘ dòng bị loại (0 dòng dùng
    được), lỗi ngay từ bước train Random Forest.
    """
    non_empty = series.astype(str).str.strip()
    non_empty = non_empty[non_empty != ""]
    if non_empty.empty:
        return False
    numeric = pd.to_numeric(non_empty, errors="coerce")
    return numeric.notna().mean() >= min_ratio


@app.route("/api/class-noise/reduce-features", methods=["POST"])
def class_noise_reduce_features_api():
    """Bước 3 (class), nút "🪄 Giảm cột tự động": chạy 2 bước giảm cột TRƯỚC
    khi người dùng tick tay đặc trưng (xem class_noise/feature_selection.py):
      Bước 1 -- rank_by_importance() + select_by_elbow(): xếp hạng TẤT CẢ cột
        (trừ cột đang là nhãn) theo mức liên quan tới nhãn, tự tìm điểm "gãy
        khúc" để giữ lại nhóm cột quan trọng nhất -- KHÔNG cần chọn tay % hay
        số cột nào (Elbow Method, xem docstring select_by_elbow()).
      Bước 2 -- filter_correlated(): trong nhóm đó, loại bớt cột THỪA THÔNG
        TIN LẪN NHAU (tương quan >= 0.8 giữa 2 cột với nhau).

    Route này CHỈ TÍNH TOÁN và trả kết quả, KHÔNG tự áp dụng xuống cấu hình
    detect thật -- frontend nhận về rồi TỰ TICK lại danh sách checkbox sẵn có
    (người dùng vẫn sửa tay thêm được, không bị khoá cứng theo kết quả này).
    """
    payload = request.get_json()
    file_id = payload.get("file_id")
    owner_error = _require_file_owner(file_id)
    if owner_error:
        return owner_error
    df = UPLOADED_FILES.get(file_id)
    if df is None:
        return jsonify({"error": "file_id không tồn tại, hãy upload lại file"}), 404

    label_column = payload.get("label_column")
    if not label_column:
        return jsonify({"error": "Thiếu label_column"}), 400
    if label_column not in df.columns:
        return jsonify({"error": f"Cột không tồn tại trong file: {label_column}"}), 400

    # Chỉ lấy cột ĐỦ SỐ làm candidate -- loại tự động các cột chữ (vd
    # "workclass", "occupation"...), khớp đúng lời hứa đã ghi trong mô tả
    # panel ("cột không ép được thành số sẽ tự động bị loại").
    candidate_columns = [
        c for c in df.columns if c != label_column and _is_mostly_numeric(df[c])
    ]
    if not candidate_columns:
        return jsonify(
            {"error": "Không có cột số nào để chạy giảm cột (toàn bộ cột còn lại đều là cột chữ)"}
        ), 400

    n_estimators = int(payload.get("n_estimators") or 300)

    try:
        ranked = rank_by_importance(
            df,
            label_column=label_column,
            candidate_columns=candidate_columns,
            n_estimators=n_estimators,
        )
        after_importance = select_by_elbow(ranked)
        after_correlation = filter_correlated(df, after_importance, threshold=0.8)
    except (ValueError, KeyError) as exc:
        return jsonify({"error": f"Không chạy được với cấu hình này: {exc}"}), 400

    return jsonify(
        {
            "ranked": [{"column": r.column, "importance": r.importance} for r in ranked],
            "after_importance": after_importance,
            "after_correlation": after_correlation,
        }
    )


@app.route("/api/apply-handling", methods=["POST"])
def apply_handling_api():
    """Bước 4: Frontend gửi lên file_id + LẠI đúng column_configs đã dùng ở
    Bước 2 (để backend tự chạy detect_noise() lại, đảm bảo xử lý ĐÚNG những ô
    người dùng đã thấy ở Bước 3, không tin tưởng 1 danh sách findings do FE tự
    gửi lên) + danh sách handling_choices (mỗi lựa chọn ứng với 1 cặp cột +
    loại noise) + tuỳ chọn duplicate_handling.

    Trả về thống kê (số dòng bị xoá, số dòng còn lại) + download_id để gọi
    /api/download/<download_id> tải file CSV đã làm sạch.
    """
    payload = request.get_json()
    file_id = payload.get("file_id")
    owner_error = _require_file_owner(file_id)
    if owner_error:
        return owner_error
    df = UPLOADED_FILES.get(file_id)
    if df is None:
        return jsonify({"error": "file_id không tồn tại, hãy upload lại file"}), 404

    try:
        column_configs = [_config_from_json(item) for item in payload.get("column_configs", [])]
        handling_choices = [
            _handling_choice_from_json(item) for item in payload.get("handling_choices", [])
        ]

        duplicate_row_config = None
        duplicate_handling_choice = None
        duplicate_payload = payload.get("duplicate_handling")
        if duplicate_payload:
            duplicate_row_config = DuplicateRowConfig(
                subset_columns=duplicate_payload.get("subset_columns")
            )
            duplicate_handling_choice = _duplicate_handling_from_json(duplicate_payload)

        # Chạy lại detect_noise() với ĐÚNG config đã dùng ở Bước 2 -- không
        # cần cross_field_rules vì bảng quyết định handling (CLAUDE.md mục 6)
        # hiện chưa có hành động xử lý cho rule liên cột, chỉ cho 7 loại
        # attribute noise + duplicate_row.
        findings = detect_noise(df, column_configs, duplicate_row_config=duplicate_row_config)

        cleaned_df, stats = apply_handling(
            df,
            column_configs,
            findings,
            handling_choices,
            duplicate_handling=duplicate_handling_choice,
        )
    except (FormulaError, ValueError, KeyError, TypeError) as exc:
        return jsonify({"error": f"Cấu hình xử lý không hợp lệ: {exc}"}), 400

    download_id = str(uuid.uuid4())
    CLEANED_FILES[download_id] = cleaned_df
    DOWNLOAD_OWNERS[download_id] = session["user_id"]

    return jsonify({**stats, "download_id": download_id})


@app.route("/api/apply-handling-partial", methods=["POST"])
def apply_handling_partial_api():
    """Bước 5 (kiểu mới -- xử lý TỪNG NHÓM, TỪNG DÒNG được tick chọn, không
    bắt buộc xử lý hết 1 lượt như /api/apply-handling cũ):

    Payload:
      - file_id, column_configs, cross_field_rules, duplicate_row (subset_columns) --
        dùng để chạy lại detect_noise() SAU khi sửa, để FE biết còn lỗi gì.
      - column: tên cột (None nếu noise_type = "duplicate_row").
      - noise_type: 1 trong 7 loại, hoặc "duplicate_row".
      - rows: danh sách [{"row_number": 101, "action": "impute_mean"},
        {"row_number": 140, "action": "fixed_value", "fixed_value": "30"}, ...]
        -- MỖI DÒNG có thể chọn 1 hành động RIÊNG (khác hẳn bản trước chỉ cho
        1 action dùng chung cho cả lượt gọi), vì trên FE giờ mỗi dòng trong
        bảng chi tiết có 1 dropdown xử lý của chính nó. Với noise_type =
        "duplicate_row" thì field "action" của mỗi dòng bị bỏ qua (luôn hiểu
        là xoá dòng đó, không có hành động nào khác hợp lý).
      - dry_run (tuỳ chọn, mặc định false): true = "CHẠY THỬ" -- tính đúng như
        thật trên bản sao nhưng KHÔNG ghi gì (không đụng WORKING_FILES, không
        ghi lịch sử, không tạo bản đang làm việc nếu chưa có), chỉ trả về
        {dry_run, rows_before, rows_after, rows_removed, cells_changed} để FE
        hiện "Sẽ xoá N dòng (a -> b)" cho người dùng xác nhận TRƯỚC khi áp dụng thật.

    Chạy thật: sửa lên bản "đang làm việc" (WORKING_FILES[file_id]), ghi 1 bước
    vào lịch sử (để hoàn tác được), rồi trả về NGUYÊN VẸN response giống
    /api/detect-noise (để FE tái dùng renderStep4() hiển thị luôn số lỗi CÒN
    LẠI sau khi xử lý xong nhóm này) cộng thêm field "history".
    """
    payload = request.get_json()
    owner_error = _require_file_owner(payload.get("file_id"))
    if owner_error:
        return owner_error
    with HANDLING_LOCK:
        return _apply_handling_partial(payload)


def _apply_handling_partial(payload: dict):
    """Phần ruột của /api/apply-handling-partial, tách riêng để route chạy TRỌN
    nó trong HANDLING_LOCK (đọc bản đang làm việc -> sửa -> ghi lại là 1 khối,
    không để request khác chen vào giữa)."""
    file_id = payload.get("file_id")
    dry_run = _as_bool(payload.get("dry_run"))
    # Chạy thử chỉ ĐỌC (không tạo bản đang làm việc); chạy thật mới tạo nếu chưa có.
    df = _peek_working_df(file_id) if dry_run else _get_working_df(file_id)
    if df is None:
        return jsonify({"error": "file_id không tồn tại, hãy upload lại file"}), 404

    try:
        column_configs, cross_field_rules, duplicate_row_config = _detect_config_from_partial_payload(
            payload
        )

        noise_type = payload["noise_type"]
        rows_payload = payload.get("rows", [])

        # `df` = bản TRƯỚC khi sửa (giữ nguyên, không bị đụng tới); `new_df` =
        # kết quả sau khi sửa. Cả apply_handling() lẫn df.drop() đều trả về
        # DataFrame MỚI nên `df` không bao giờ bị sửa tại chỗ -- đó là lý do
        # dùng thẳng `df` làm snapshot hoàn tác được (xem HANDLING_HISTORY).
        new_df = df
        action_counts: dict[str, int] = {}

        if noise_type == "duplicate_row":
            # Trùng dòng: chỉ có 1 hành động hợp lý là XOÁ các dòng được tick
            # -- không đi qua apply_handling() vì đó là hàm xử lý theo CỘT,
            # còn đây là xoá thẳng theo row_index, không gắn với cột nào.
            column = None
            row_indices = [int(item["row_number"]) - 1 for item in rows_payload]
            existing = [i for i in row_indices if i in df.index]
            new_df = df.drop(index=existing)
            if existing:
                action_counts["remove_row"] = len(existing)
        else:
            column = payload["column"]
            # Gom các dòng theo TỪNG hành động khác nhau -- mỗi dòng có thể tự
            # chọn cách xử lý riêng (vd dòng A điền trung bình, dòng B điền
            # tay), nên không thể gộp chung 1 HandlingChoice cho cả lượt gọi
            # như trước; xử lý tuần tự từng nhóm hành động trên CÙNG 1 df,
            # kết quả của nhóm trước làm đầu vào cho nhóm sau.
            rows_by_action: dict[tuple[str, str | None], list[int]] = {}
            for item in rows_payload:
                action_key = (item["action"], item.get("fixed_value"))
                rows_by_action.setdefault(action_key, []).append(int(item["row_number"]) - 1)

            for (action_value, fixed_value), row_indices in rows_by_action.items():
                fake_findings = [
                    NoiseFinding(row_index=i, column=column, noise_type=noise_type, value=None)
                    for i in row_indices
                    if i in df.index
                ]
                if not fake_findings:
                    continue
                choice = HandlingChoice(
                    column=column,
                    noise_type=NoiseType(noise_type),
                    action=HandlingAction(action_value),
                    fixed_value=fixed_value,
                )
                new_df, _stats = apply_handling(new_df, column_configs, fake_findings, [choice])
                action_counts[action_value] = action_counts.get(action_value, 0) + len(fake_findings)

        rows_removed, cells_changed = _summarize_change(df, new_df, column)

        if dry_run:
            return jsonify(
                {
                    "dry_run": True,
                    "rows_before": len(df),
                    "rows_after": len(new_df),
                    "rows_removed": rows_removed,
                    "cells_changed": cells_changed,
                }
            )

        # Detect lại trên bản MỚI để FE biết chính xác còn lỗi gì -- phần vừa
        # xử lý xong sẽ tự biến mất khỏi kết quả. PHẢI chạy TRƯỚC khi ghi bất cứ
        # thứ gì: nếu detect lỗi (cấu hình sai...) thì route trả 400 mà dữ liệu và
        # lịch sử vẫn nguyên vẹn, thay vì "báo lỗi nhưng dữ liệu đã bị sửa".
        findings = detect_noise(
            new_df,
            column_configs,
            duplicate_row_config=duplicate_row_config,
            cross_field_rules=cross_field_rules,
        )

        # Chỉ ghi lịch sử khi bước này THẬT SỰ làm thay đổi dữ liệu -- vd chọn
        # "Giữ nguyên" hoặc xử lý các dòng đã bị xoá từ lần trước thì không có gì
        # để hoàn tác, đừng làm đầy nhật ký bằng các bước rỗng.
        if rows_removed or cells_changed:
            _record_history(
                file_id,
                {
                    "group_key": "duplicate_row" if column is None else f"{column}|{noise_type}",
                    "column": column,
                    "noise_type": noise_type,
                    "actions": action_counts,
                    "rows_removed": rows_removed,
                    "cells_changed": cells_changed,
                    "rows_before": len(df),
                    "rows_after": len(new_df),
                },
                snapshot_df=df,
            )
        WORKING_FILES[file_id] = new_df
    except (FormulaError, ValueError, KeyError, TypeError, re.error) as exc:
        return jsonify({"error": f"Cấu hình xử lý không hợp lệ: {exc}"}), 400

    return jsonify(
        {
            **_build_detect_response(new_df, findings),
            "history": _history_payload(file_id),
            "applied": {"rows_removed": rows_removed, "cells_changed": cells_changed},
        }
    )


@app.route("/api/undo-handling", methods=["POST"])
def undo_handling_api():
    """Bước 5 (nút "Hoàn tác"): lùi lại 1 bước -- đặt bản đang làm việc về đúng
    trạng thái TRƯỚC lần "Áp dụng" gần nhất (lấy từ snapshot đã lưu trong
    HANDLING_HISTORY), gỡ bước đó khỏi lịch sử, rồi detect lại để FE dựng lại
    danh sách nhóm lỗi cho khớp.

    Payload: file_id + column_configs/cross_field_rules/duplicate_row (cùng
    dạng với /api/apply-handling-partial, để chạy lại detect_noise()).
    Trả về: response dạng /api/detect-noise + "history".

    Lỗi 409 nếu không có gì để hoàn tác, hoặc bước gần nhất đã quá cũ/bảng quá
    lớn nên không còn snapshot (khi đó chỉ còn cách "Về dữ liệu gốc").
    """
    payload = request.get_json()
    owner_error = _require_file_owner(payload.get("file_id"))
    if owner_error:
        return owner_error
    with HANDLING_LOCK:
        return _undo_handling(payload)


def _undo_handling(payload: dict):
    """Phần ruột của /api/undo-handling (chạy trong HANDLING_LOCK, xem route)."""
    file_id = payload.get("file_id")
    if file_id not in UPLOADED_FILES:
        return jsonify({"error": "file_id không tồn tại, hãy upload lại file"}), 404

    history = HANDLING_HISTORY.get(file_id, [])
    if not history:
        return jsonify({"error": "Chưa có bước xử lý nào để hoàn tác."}), 409
    last = history[-1]
    if last["snapshot"] is None:
        return jsonify(
            {
                "error": (
                    "Không hoàn tác được bước này (bảng quá lớn, hoặc đã vượt quá "
                    f"{MAX_UNDO_STEPS} bước gần nhất). Hãy dùng \"Về dữ liệu gốc\"."
                )
            }
        ), 409

    try:
        column_configs, cross_field_rules, duplicate_row_config = _detect_config_from_partial_payload(
            payload
        )
        restored = last["snapshot"]
        findings = detect_noise(
            restored,
            column_configs,
            duplicate_row_config=duplicate_row_config,
            cross_field_rules=cross_field_rules,
        )
    except (FormulaError, ValueError, KeyError, TypeError, re.error) as exc:
        # Lỗi cấu hình -> chưa đụng gì vào dữ liệu/lịch sử, người dùng thử lại được.
        return jsonify({"error": f"Cấu hình không hợp lệ: {exc}"}), 400

    # Chỉ sau khi mọi thứ trên đã thành công mới thật sự ghi (tránh hoàn tác dở dang).
    history.pop()
    WORKING_FILES[file_id] = restored
    return jsonify({**_build_detect_response(restored, findings), "history": _history_payload(file_id)})


@app.route("/api/reset-working", methods=["POST"])
def reset_working_api():
    """Bước 5 (nút "Về dữ liệu gốc"): bỏ TOÀN BỘ các lần xử lý, quay về đúng bản
    người dùng đã upload. Rất đơn giản vì UPLOADED_FILES không bao giờ bị sửa:
    chỉ cần xoá bản đang làm việc + lịch sử, lần Áp dụng kế tiếp sẽ tự copy lại
    từ bản gốc (xem _get_working_df()). Luôn dùng được, kể cả khi file quá lớn
    để có snapshot hoàn tác.

    Payload/response: giống /api/undo-handling (response dạng detect + "history",
    lúc này history rỗng).
    """
    payload = request.get_json()
    owner_error = _require_file_owner(payload.get("file_id"))
    if owner_error:
        return owner_error
    with HANDLING_LOCK:
        return _reset_working(payload)


def _reset_working(payload: dict):
    """Phần ruột của /api/reset-working (chạy trong HANDLING_LOCK, xem route)."""
    file_id = payload.get("file_id")
    original = UPLOADED_FILES.get(file_id)
    if original is None:
        return jsonify({"error": "file_id không tồn tại, hãy upload lại file"}), 404

    try:
        column_configs, cross_field_rules, duplicate_row_config = _detect_config_from_partial_payload(
            payload
        )
        findings = detect_noise(
            original,
            column_configs,
            duplicate_row_config=duplicate_row_config,
            cross_field_rules=cross_field_rules,
        )
    except (FormulaError, ValueError, KeyError, TypeError, re.error) as exc:
        return jsonify({"error": f"Cấu hình không hợp lệ: {exc}"}), 400

    WORKING_FILES.pop(file_id, None)
    HANDLING_HISTORY.pop(file_id, None)
    return jsonify({**_build_detect_response(original, findings), "history": _history_payload(file_id)})


@app.route("/api/working-data/<file_id>", methods=["GET"])
def working_data_api(file_id: str):
    """Bước 5 (nút "Xem dữ liệu sau xử lý"): trả về TOÀN BỘ dữ liệu ở trạng
    thái hiện tại (đã áp dụng các lần xử lý từng phần trước đó, nếu có) --
    không chỉ các dòng còn lỗi như /api/detect-noise, để người dùng xem lại
    được cả các dòng đã sạch."""
    owner_error = _require_file_owner(file_id)
    if owner_error:
        return owner_error
    df = WORKING_FILES.get(file_id, UPLOADED_FILES.get(file_id))
    if df is None:
        return jsonify({"error": "file_id không tồn tại, hãy upload lại file"}), 404
    out = df.copy()
    out.insert(0, "row_number", out.index + 1)
    return jsonify({"rows": out.to_dict(orient="records"), "total_rows": len(df)})


@app.route("/api/export-working", methods=["POST"])
def export_working_api():
    """Bước 5 (nút xuất file cuối cùng): đóng gói bản "đang làm việc" hiện tại
    (hoặc bản gốc nếu người dùng chưa xử lý gì) thành 1 download_id, dùng
    chung cơ chế tải file với /api/download/<id> đã có."""
    payload = request.get_json()
    file_id = payload.get("file_id")
    owner_error = _require_file_owner(file_id)
    if owner_error:
        return owner_error
    df = WORKING_FILES.get(file_id, UPLOADED_FILES.get(file_id))
    if df is None:
        return jsonify({"error": "file_id không tồn tại, hãy upload lại file"}), 404

    download_id = str(uuid.uuid4())
    CLEANED_FILES[download_id] = df
    DOWNLOAD_OWNERS[download_id] = session["user_id"]
    return jsonify({"final_row_count": len(df), "download_id": download_id})


@app.route("/api/download/<download_id>", methods=["GET"])
def download_cleaned_file(download_id: str):
    """Bước 4 (tiếp): trả file CSV đã làm sạch cho trình duyệt tải về, dựa
    trên download_id nhận được từ /api/apply-handling."""
    owner_error = _require_download_owner(download_id)
    if owner_error:
        return owner_error
    cleaned_df = CLEANED_FILES.get(download_id)
    if cleaned_df is None:
        return jsonify({"error": "download_id không tồn tại hoặc đã hết hạn"}), 404

    buffer = StringIO()
    cleaned_df.to_csv(buffer, index=False)
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=spark_cleaned.csv"},
    )


# =============================================================================
# "Convert" -- 3 tool đổi ĐỊNH DẠNG file (đổi delimiter CSV, CSV<->JSON), KHÔNG
# liên quan gì tới detect/xử lý noise -- logic thật nằm ở converters/transform.py,
# 3 route dưới đây chỉ "phiên dịch" multipart/form-data <-> gọi hàm, giống triết
# lý app.py ở mọi route khác. CẢ 3 route đều @login_required (khác free tool
# công khai của trang tham khảo) -- và KHÔNG cần file_id/UPLOADED_FILES gì cả:
# xong trong ĐÚNG 1 request (đọc file/text -> convert -> trả kết quả luôn),
# không có bước "xem rồi xử lý tiếp" nhiều lượt như luồng Attribute/Class Noise.
# =============================================================================
_VALID_DELIMITERS = set(DELIMITER_LABELS.keys())


def _extract_convert_text(req) -> str:
    """Lấy nội dung văn bản cần convert -- chấp nhận file tải lên (field
    "file", tab FILE trên FE) HOẶC text dán tay (field "text", tab PASTE) --
    FE luôn gửi multipart/form-data cho cả 2 tab để route chỉ cần đọc 1 kiểu.
    utf-8-sig: tự bỏ BOM nếu Excel/Windows có thêm vào đầu file, không ảnh
    hưởng gì nếu file vốn không có BOM."""
    file = req.files.get("file")
    if file is not None and file.filename:
        try:
            return file.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            raise ConversionError("File không phải văn bản UTF-8 hợp lệ")
    text = req.form.get("text", "")
    if text.strip():
        return text
    raise ConversionError("Thiếu file hoặc nội dung dán tay")


def _delimiter_param(form, field_name: str, allow_auto: bool) -> str:
    """Đọc 1 tham số delimiter từ form, validate CHẶT ở ranh giới API (route) --
    converters/transform.py không tự giới hạn delimiter là ký tự gì (nhận ký tự
    bất kỳ cũng chạy được), nhưng FE chỉ nên gửi đúng 1 trong 4 lựa chọn đã định
    nghĩa trước (xem DELIMITER_LABELS) -- validate ở đây để báo lỗi rõ ràng nếu
    có gì đó gửi sai, thay vì convert ra kết quả khó hiểu."""
    value = form.get(field_name, "auto" if allow_auto else ",")
    if allow_auto and value == "auto":
        return value
    if value not in _VALID_DELIMITERS:
        raise ConversionError(f"Giá trị '{field_name}' không hợp lệ")
    return value


# Số dòng DỮ LIỆU tối đa hiện ở các bảng xem trước (Free Tools, Convert, Cần cấu
# hình -- cả khung Đầu vào lẫn Kết quả). Phải KHỚP hằng số PREVIEW_ROWS trong
# frontend/workspace.js (khung Đầu vào được trình duyệt tự cắt theo số đó).
# Chỉ giới hạn việc HIỂN THỊ -- xử lý và file tải xuống luôn đủ toàn bộ dòng.
PREVIEW_DATA_ROWS = 100


def _csv_preview_rows(csv_text: str, delimiter: str, limit: int = PREVIEW_DATA_ROWS + 1) -> list:
    """Đọc trước tối đa `limit` dòng đầu (mặc định 1 header + PREVIEW_DATA_ROWS dòng
    dữ liệu) của 1 CSV text để trả cho FE hiện bảng xem trước -- tránh FE phải tự viết
    1 bộ phân tích CSV bằng JS (đúng quyết định kiến trúc đã chốt: mọi phân
    tích dữ liệu luôn làm ở backend thật, xem CLAUDE.md phần frontend/)."""
    reader = csv.reader(io.StringIO(csv_text), delimiter=delimiter)
    rows = []
    for i, row in enumerate(reader):
        if i >= limit:
            break
        rows.append(row)
    return rows


@app.route("/api/convert/delimiter", methods=["POST"])
@login_required
def convert_delimiter_api():
    """Tool 1: đổi delimiter của 1 file/đoạn CSV (vd ; -> ,)."""
    try:
        text = _extract_convert_text(request)
        from_delimiter = _delimiter_param(request.form, "from_delimiter", allow_auto=True)
        to_delimiter = _delimiter_param(request.form, "to_delimiter", allow_auto=False)
        result_text, used_from = convert_csv_delimiter(text, from_delimiter, to_delimiter)
    except ConversionError as exc:
        return jsonify({"error": str(exc)}), 400

    preview = _csv_preview_rows(result_text, to_delimiter)
    return jsonify(
        {
            "result_text": result_text,
            "used_from_delimiter": used_from,
            "row_count": result_text.count("\n") + (0 if result_text.endswith("\n") else 1),
            "preview_rows": preview,
        }
    )


@app.route("/api/convert/csv-to-json", methods=["POST"])
@login_required
def convert_csv_to_json_api():
    """Tool 2: CSV -> JSON."""
    try:
        text = _extract_convert_text(request)
        delimiter = _delimiter_param(request.form, "delimiter", allow_auto=True)
        result_text, used_delimiter = csv_text_to_json(
            text,
            has_header=_as_bool(request.form.get("has_header", "true")),
            delimiter=delimiter,
            as_array_of_arrays=request.form.get("shape") == "arrays",
            convert_types=_as_bool(request.form.get("convert_types", "true")),
            indent=_as_bool(request.form.get("indent", "true")),
        )
    except ConversionError as exc:
        return jsonify({"error": str(exc)}), 400

    # result_text luôn là JSON hợp lệ do chính json.dumps() ở converters/transform.py
    # sinh ra -- parse lại để đếm số record cho FE hiện số liệu, không phải đếm ký tự.
    parsed = json.loads(result_text)
    return jsonify(
        {
            "result_text": result_text,
            "used_delimiter": used_delimiter,
            "record_count": len(parsed) if isinstance(parsed, list) else 1,
        }
    )


@app.route("/api/convert/json-to-csv", methods=["POST"])
@login_required
def convert_json_to_csv_api():
    """Tool 3: JSON (array object hoặc JSON Lines) -> CSV."""
    try:
        text = _extract_convert_text(request)
        output_delimiter = _delimiter_param(request.form, "output_delimiter", allow_auto=False)
        result_text, columns = json_text_to_csv(text, output_delimiter)
    except ConversionError as exc:
        return jsonify({"error": str(exc)}), 400

    preview = _csv_preview_rows(result_text, output_delimiter)
    return jsonify(
        {
            "result_text": result_text,
            "columns": columns,
            "row_count": result_text.count("\n") + (0 if result_text.endswith("\n") else 1),
            "preview_rows": preview,
        }
    )


# =============================================================================
# "Free Tools" (noise-tools) -- 4 công cụ xử lý nhiễu KHÔNG cần cấu hình tay,
# đối lập với 7 loại Attribute Noise + Class Noise ở Workspace (5 bước chính,
# luôn cần chọn cột/tham số trước khi detect). Vận hành GIỐNG Convert File
# (@login_required, KHÔNG cần file_id/UPLOADED_FILES, xong trong ĐÚNG 1
# request) nhưng KHÁC ở chỗ cần hiểu DỮ LIỆU DẠNG BẢNG (trùng dòng, ô nào
# trống...) nên đọc bằng pandas qua load_data()/pd.read_csv() (giống
# Workspace) thay vì module csv/json chuẩn như converters/transform.py.
# =============================================================================


def _read_df_for_noise_tool(req) -> pd.DataFrame:
    """Đọc DataFrame từ request -- chấp nhận file tải lên (CSV/Excel, field
    "file") HOẶC CSV text dán tay (field "text"), giống 2 tab FILE/PASTE của
    khối Convert/Free Tools trong workspace.html. File tải lên được lưu TẠM rồi XOÁ NGAY sau khi đọc xong
    (khác /api/upload giữ nguyên file trong UPLOAD_DIR để dùng lại ở các
    bước sau) -- free tool chạy xong 1 lần là kết thúc, không cần giữ gì lại."""
    file = req.files.get("file")
    if file is not None and file.filename:
        temp_path = UPLOAD_DIR / f"_quicktool_{uuid.uuid4()}_{file.filename}"
        file.save(temp_path)
        try:
            return load_data(str(temp_path))
        finally:
            temp_path.unlink(missing_ok=True)

    text = req.form.get("text", "")
    if text.strip():
        # Đọc CSV text dán tay bằng ĐÚNG tham số load_data() dùng cho CSV
        # (dtype=str, keep_default_na=False, na_filter=False) -- giữ nguyên
        # văn mọi giá trị, không để pandas tự suy đoán kiểu/NaN (xem lý do
        # gốc ở pipeline.py::load_data()).
        return pd.read_csv(StringIO(text), dtype=str, keep_default_na=False, na_filter=False)

    raise QuickToolError("Thiếu file hoặc nội dung dán tay")


def _noise_tool_response(result_df: pd.DataFrame, stats: dict, extra: Optional[dict] = None) -> Response:
    """Đóng gói kết quả giống các route /api/convert/* (result_text để tải
    về + preview_rows để FE hiện bảng), tái dùng _csv_preview_rows() đã có.
    `extra` = các field riêng của từng tool, gộp thêm vào response (vd Xoá dòng
    trùng gửi kèm `duplicate_preview`)."""
    buffer = StringIO()
    result_df.to_csv(buffer, index=False)
    result_text = buffer.getvalue()
    payload = {
        "result_text": result_text,
        "stats": stats,
        "preview_rows": _csv_preview_rows(result_text, ","),
    }
    if extra:
        payload.update(extra)
    return jsonify(payload)


@app.route("/api/noise-tools/remove-duplicates", methods=["POST"])
@login_required
def noise_tool_remove_duplicates():
    """Free Tool 1: Xoá dòng trùng -- subset_columns để trống = so trùng
    trên TOÀN BỘ cột. `ignore_case`/`ignore_whitespace` (MỚI) chỉ ảnh hưởng
    cách SO SÁNH 2 dòng, không đổi giá trị thật -- xem quick_tools.py."""
    try:
        df = _read_df_for_noise_tool(request)
        subset_raw = request.form.get("subset_columns", "").strip()
        subset_columns = [c.strip() for c in subset_raw.split(",") if c.strip()] or None
        keep = DuplicateKeep(request.form.get("keep", "first"))
        ignore_case = _as_bool(request.form.get("ignore_case", "false"))
        ignore_whitespace = _as_bool(request.form.get("ignore_whitespace", "false"))
        result_df, stats = quick_remove_duplicates(
            df, subset_columns, keep, ignore_case=ignore_case, ignore_whitespace=ignore_whitespace
        )
        # Danh sách các dòng thuộc nhóm trùng (cho nút "Xem các dòng trùng" ở FE) --
        # tính trên DỮ LIỆU ĐẦU VÀO với đúng cùng tuỳ chọn so sánh, nên khớp đúng
        # tập dòng vừa bị xoá.
        duplicate_preview = preview_duplicate_rows(
            df, subset_columns, keep,
            ignore_case=ignore_case, ignore_whitespace=ignore_whitespace,
            limit=PREVIEW_DATA_ROWS,
        )
    except QuickToolError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Không đọc/xử lý được file: {exc}"}), 400
    return _noise_tool_response(result_df, stats, {"duplicate_preview": duplicate_preview})


@app.route("/api/noise-tools/trim-whitespace", methods=["POST"])
@login_required
def noise_tool_trim_whitespace():
    """Free Tool 2: Cắt khoảng trắng thừa trên MỌI ô. `collapse_repeated`/
    `remove_zero_width` (MỚI) -- xem `_clean_whitespace_advanced()` trong
    quick_tools.py để biết mặc định bật/tắt của từng cái."""
    try:
        df = _read_df_for_noise_tool(request)
        collapse_repeated = _as_bool(request.form.get("collapse_repeated", "false"))
        remove_zero_width = _as_bool(request.form.get("remove_zero_width", "true"))
        result_df, stats = quick_trim_whitespace(
            df, collapse_repeated=collapse_repeated, remove_zero_width=remove_zero_width
        )
        # Danh sách các ô đã bị sửa (cho nút "Xem các ô đã sửa" ở FE) -- tính trên DỮ LIỆU ĐẦU
        # VÀO với đúng cùng 2 tuỳ chọn, nên khớp đúng tập ô vừa bị đổi.
        trim_preview = preview_trim_changes(
            df, collapse_repeated=collapse_repeated, remove_zero_width=remove_zero_width,
            limit=PREVIEW_DATA_ROWS,
        )
    except QuickToolError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Không đọc/xử lý được file: {exc}"}), 400
    return _noise_tool_response(result_df, stats, {"trim_preview": trim_preview})


@app.route("/api/noise-tools/blanks", methods=["POST"])
@login_required
def noise_tool_blanks():
    """Free Tool 3: Ô trống -- GỘP 3 tool cũ (Xoá dòng trống + Điền/xoá ô trống + Thiếu giá trị nâng cao). Field:
    `column_actions` (JSON {cột: {dtype, action, fixed_value}}, bỏ trống = không đụng cột nào), `remove_empty_rows`
    (mặc định true: xoá dòng mà MỌI cột đều trống), `remove_empty_columns` (mặc định false). Thứ tự xử lý và các cách xử lý
    hợp lệ theo kiểu cột: xem quick_tools.py (quick_handle_blanks)."""
    try:
        df = _read_df_for_noise_tool(request)
        raw = request.form.get("column_actions", "").strip()
        column_actions = {}
        if raw:
            try:
                column_actions = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise QuickToolError(f"column_actions không phải JSON hợp lệ: {exc}")
            if not isinstance(column_actions, dict):
                raise QuickToolError("column_actions phải là object {tên cột: {dtype, action, fixed_value}}")
        remove_empty_rows = _as_bool(request.form.get("remove_empty_rows", "true"))
        remove_empty_columns = _as_bool(request.form.get("remove_empty_columns", "false"))
        result_df, stats, outcome = quick_handle_blanks(
            df, column_actions, remove_empty_rows=remove_empty_rows, remove_empty_columns=remove_empty_columns
        )
        blank_preview = preview_blank_changes(df, outcome, limit=PREVIEW_DATA_ROWS)
    except QuickToolError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Không đọc/xử lý được file: {exc}"}), 400
    return _noise_tool_response(result_df, stats, {"blank_preview": blank_preview})


@app.route("/api/noise-tools/format-noise", methods=["POST"])
@login_required
def noise_tool_format_noise():
    """Free Tool 5: Sai định dạng -- quét MỌI cột theo kiểu dữ liệu của từng cột. Field `column_types`
    (JSON {cột: {dtype, date_format}}) là kiểu người dùng đã xác nhận/sửa ở giao diện; thiếu field này
    thì backend tự đoán kiểu (auto_column_types). `action`: report (chỉ báo, mặc định) / clear_cell
    (để trống ô sai) / remove_row (xoá dòng có ô sai) -- xem quick_tools.py."""
    try:
        df = _read_df_for_noise_tool(request)
        raw = request.form.get("column_types", "").strip()
        if raw:
            try:
                column_types = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise QuickToolError(f"column_types không phải JSON hợp lệ: {exc}")
            if not isinstance(column_types, dict):
                raise QuickToolError("column_types phải là object {tên cột: {dtype, date_format}}")
        else:
            column_types = auto_column_types(df)
        action = request.form.get("action", "report")
        mask = find_format_errors(df, column_types)
        result_df, stats = quick_fix_format_noise(df, mask, action)
        format_preview = preview_format_errors(df, mask, limit=PREVIEW_DATA_ROWS)
    except QuickToolError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Không đọc/xử lý được file: {exc}"}), 400
    return _noise_tool_response(result_df, stats, {"format_preview": format_preview})


# ===========================================================================
# TOOL "CẦN CẤU HÌNH" (4 tool, giao diện Denoise): Ngoài khoảng / Giá trị
# bất thường / Không nhất quán / Rule liên cột. ("Sai định dạng" và "Thiếu giá
# trị nâng cao" đã chuyển sang nhóm Tự động -- route /api/noise-tools/format-noise
# và /api/noise-tools/blanks.) Vận hành GIỐNG 4 Free Tools ở trên (không file_id, xong
# trong 1 request, @login_required) nhưng KHÁC ở chỗ cần người dùng khai cột
# + tham số, nên chia 2 nhịp: mode="detect" (chỉ phát hiện, trả các dòng bị
# gắn cờ + danh sách cách xử lý hợp lệ) rồi mode="apply" (phát hiện lại trên
# cùng dữ liệu + áp dụng ĐÚNG 1 cách xử lý cho mọi ô bị gắn cờ, trả CSV kết
# quả). Lõi dùng lại NGUYÊN detect_noise()/apply_handling() (bảng quyết định
# kiểu cột × loại lỗi ở attribute_handling.py), không viết logic mới.
# ===========================================================================
CONFIG_TOOL_NOISE_TYPE = {
    "out-of-range": NoiseType.OUT_OF_RANGE,
    "outlier": NoiseType.OUTLIER,
    "inconsistent-category": NoiseType.INCONSISTENT_CATEGORY,
}
CONFIG_TOOL_FLAGGED_LIMIT = 200  # số dòng bị gắn cờ tối đa trả về cho FE hiện bảng


def _df_preview_rows(df: pd.DataFrame, limit: int = PREVIEW_DATA_ROWS) -> list:
    """Header + tối đa `limit` dòng đầu của DataFrame, dạng list[list[str]]
    (cùng shape với _csv_preview_rows()) để FE hiện bảng xem trước."""
    rows = [[str(c) for c in df.columns]]
    for values in df.head(limit).itertuples(index=False):
        rows.append(["" if v is None else str(v) for v in values])
    return rows


@app.route("/api/noise-tools/inspect", methods=["POST"])
@login_required
def noise_tool_inspect():
    """Đọc nhanh file/text vừa chọn: tên cột + kiểu dữ liệu đoán sẵn
    (guess_column_dtype(), cùng hàm /api/upload dùng) + 20 dòng xem trước.
    FE dùng để dựng dropdown chọn cột cho các tool cần cấu hình (kể cả file
    Excel mà trình duyệt không tự đọc được). Không giữ lại gì sau khi trả."""
    try:
        df = _read_df_for_noise_tool(request)
    except QuickToolError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Không đọc được file: {exc}"}), 400
    # Chỉ khi giao diện hỏi (tool Ô trống) mới đếm ô trống từng cột -- phải quét hết file nên không làm cho mọi lần đọc cột.
    blanks_info = blank_column_summary(df) if _as_bool(request.form.get("include_blanks", "false")) else {}
    return jsonify(
        {
            **blanks_info,
            "columns": [str(c) for c in df.columns],
            "guessed_dtypes": {str(c): guess_column_dtype(df[c]) for c in df.columns},
            # Khuôn ngày đoán sẵn cho các cột được đoán là "date" (tool Sai định dạng dùng để điền sẵn ô khuôn ngày).
            "guessed_date_formats": {
                str(c): guess_date_format(df[c]) or "%Y-%m-%d"
                for c in df.columns if guess_column_dtype(df[c]) == "date"
            },
            "row_count": int(len(df)),
            "preview_rows": _df_preview_rows(df),
        }
    )


def _parse_config_tool_payload(form) -> dict:
    """Field `config` là 1 chuỗi JSON (gửi kèm multipart cùng file/text):
    {tool, column, dtype, params{...}, rule{...}, action, fixed_value}."""
    raw = form.get("config", "")
    try:
        cfg = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise QuickToolError(f"config không phải JSON hợp lệ: {exc}")
    tool = cfg.get("tool")
    if tool != "cross-rule" and tool not in CONFIG_TOOL_NOISE_TYPE:
        raise QuickToolError(f"Tool không hợp lệ: {tool}")
    return cfg


def _run_config_tool_detect(df: pd.DataFrame, cfg: dict):
    """Chạy detect cho ĐÚNG 1 cấu hình. Trả về (column_configs,
    cross_field_rules, findings, noise_key, column) -- column = None với rule
    liên cột (noise cấp dòng, không gắn với 1 cột)."""
    tool = cfg["tool"]
    if tool == "cross-rule":
        rule = _cross_field_rule_from_json(cfg.get("rule") or {})
        findings = detect_noise(df, [], cross_field_rules=[rule])
        return [], [rule], findings, f"rule:{rule.rule_type.value}", None

    noise_type = CONFIG_TOOL_NOISE_TYPE[tool]
    column = cfg.get("column")
    if not column or column not in df.columns:
        raise QuickToolError(f"Cột '{column}' không tồn tại trong file")
    params = cfg.get("params") or {}
    # Bỏ các tham số để trống ("" / None) để dataclass dùng giá trị mặc định.
    params = {k: v for k, v in params.items() if v not in ("", None)}
    item = {"column": column, "dtype": cfg.get("dtype") or "text", "noise_types": [noise_type.value], **params}
    col_cfg = _config_from_json(item)
    findings = detect_noise(df, [col_cfg])
    return [col_cfg], [], findings, noise_type.value, column


def _config_tool_actions(column_configs, noise_key) -> list[str]:
    """Danh sách cách xử lý hợp lệ: theo bảng kiểu cột × loại lỗi; rule liên
    cột chỉ có 2 lựa chọn (xoá dòng vi phạm / giữ nguyên, chỉ xem)."""
    if not column_configs:
        return ["remove_row", "keep"]
    return [a.value for a in get_available_actions(column_configs[0].dtype, NoiseType(noise_key))]


@app.route("/api/noise-tools/configured", methods=["POST"])
@login_required
def noise_tool_configured():
    mode = request.form.get("mode", "detect")
    try:
        cfg = _parse_config_tool_payload(request.form)
        df = _read_df_for_noise_tool(request)
        column_configs, _rules, findings, noise_key, column = _run_config_tool_detect(df, cfg)
        actions = _config_tool_actions(column_configs, noise_key)

        if mode == "detect":
            # Gom cột bị gắn cờ theo từng dòng để FE tô màu đúng ô. Rule liên
            # cột ghi column dạng "a & b" (describe_rule()) -> tách ra từng cột.
            flagged: dict[int, set] = {}
            for f in findings:
                cols = flagged.setdefault(int(f.row_index), set())
                for part in str(f.column).split(" & "):
                    if part in df.columns:
                        cols.add(part)
            indices = sorted(flagged)
            rows = []
            for i in indices[:CONFIG_TOOL_FLAGGED_LIMIT]:
                values = ["" if v is None else str(v) for v in df.loc[i].tolist()]
                rows.append({"row_number": int(i) + 1, "cells": values, "flagged": sorted(flagged[i])})
            payload = {
                    "mode": "detect",
                    "total_rows": int(len(df)),
                    "findings_count": len(findings),
                    "flagged_rows_count": len(indices),
                    "truncated": len(indices) > CONFIG_TOOL_FLAGGED_LIMIT,
                    "columns": [str(c) for c in df.columns],
                    "flagged_rows": rows,
                    "available_actions": actions,
            }
            if not findings:
                # Không có gì để sửa -> trả luôn CSV (không đổi) để FE vẫn nối
                # tiếp sang tool khác được mà không phải gọi "apply" rỗng.
                buffer = StringIO()
                df.to_csv(buffer, index=False)
                payload["result_text"] = buffer.getvalue()
            return jsonify(payload)

        # mode == "apply"
        action = cfg.get("action") or ""
        fixed_value = cfg.get("fixed_value")
        if action not in actions:
            raise QuickToolError("Cách xử lý không hợp lệ cho kiểu cột / loại lỗi này")
        if action == "fixed_value" and (fixed_value is None or str(fixed_value) == ""):
            raise QuickToolError("Chưa nhập giá trị cố định để điền vào")
        if column is None:
            # Rule liên cột: không đi qua apply_handling() (hàm xử lý theo CỘT),
            # chỉ có xoá thẳng các dòng vi phạm theo row_index.
            flagged_idx = sorted({int(f.row_index) for f in findings})
            new_df = df.drop(index=flagged_idx) if action == "remove_row" else df
        else:
            choice = HandlingChoice(
                column=column,
                noise_type=NoiseType(noise_key),
                action=HandlingAction(action),
                fixed_value=fixed_value,
            )
            new_df, _stats = apply_handling(df, column_configs, findings, [choice])
        rows_removed, cells_changed = _summarize_change(df, new_df, column)
        stats = {
            "original_row_count": int(len(df)),
            "final_row_count": int(len(new_df)),
            "removed_row_count": int(rows_removed),
            "cells_changed": int(cells_changed),
            "findings_count": len(findings),
            "action": action,
        }
    except QuickToolError as exc:
        return jsonify({"error": str(exc)}), 400
    except (FormulaError, ValueError, KeyError, TypeError, re.error) as exc:
        return jsonify({"error": f"Cấu hình không hợp lệ: {exc}"}), 400
    except Exception as exc:
        return jsonify({"error": f"Không đọc/xử lý được file: {exc}"}), 400
    return _noise_tool_response(new_df, stats)


if __name__ == "__main__":
    # threaded=True: để request /api/class-noise/detect (có thể chạy TỚI VÀI
    # PHÚT với file lớn) không chặn luôn các request khác (vd health check
    # của frontend) trong lúc chờ -- Flask dev server mặc định xử lý tuần tự
    # từng request 1 nếu không bật tuỳ chọn này.
    app.run(port=5000, debug=True, threaded=True)
