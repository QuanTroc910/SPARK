"""Backend Flask -- lớp "cầu nối" giữa frontend và code logic attribute_noise/.

File này KHÔNG chứa logic detect noise gì cả -- nó chỉ làm 3 việc:
  1. Nhận request (file upload, JSON config) từ frontend qua HTTP.
  2. Gọi đúng hàm trong attribute_noise/ (code lõi đã viết từ trước).
  3. Đóng gói kết quả thành JSON, trả ngược lại cho frontend.

Chạy thử: python3 app.py -> server chạy ở http://localhost:5000
"""

import uuid
from io import StringIO
from pathlib import Path

from flask import Flask, Response, jsonify, request
from flask_cors import CORS

from attribute_noise.attribute_handling import (
    DuplicateHandlingChoice,
    DuplicateKeep,
    HandlingAction,
    HandlingChoice,
    apply_handling,
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
from attribute_noise.pipeline import NoiseFinding, detect_noise, get_flagged_rows, load_data

app = Flask(__name__)

# CORS: cho phép trình duyệt gọi API này dù frontend chạy ở 1 origin khác
# (vd mở file index.html trực tiếp, hoặc chạy ở port khác với backend).
# Nếu không bật cái này, trình duyệt sẽ tự chặn request dù code đúng.
CORS(app)

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


def _get_working_df(file_id: str):
    if file_id not in WORKING_FILES:
        original = UPLOADED_FILES.get(file_id)
        if original is None:
            return None
        WORKING_FILES[file_id] = original.copy()
    return WORKING_FILES[file_id]


@app.route("/api/upload", methods=["POST"])
def upload_file():
    """Bước 1: Frontend gửi file CSV/Excel lên đây.

    Trả về file_id (để các request sau tham chiếu tới đúng file này) và
    danh sách tên cột (để frontend hiển thị cho user chọn).
    """
    file = request.files.get("file")
    if file is None:
        return jsonify({"error": "Thiếu file trong request"}), 400

    file_id = str(uuid.uuid4())
    save_path = UPLOAD_DIR / f"{file_id}_{file.filename}"
    file.save(save_path)

    df = load_data(str(save_path))  # hàm có sẵn trong attribute_noise/pipeline.py
    UPLOADED_FILES[file_id] = df

    return jsonify(
        {
            "file_id": file_id,
            "columns": list(df.columns),
            "row_count": len(df),
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
    df = UPLOADED_FILES.get(file_id)
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
    except (FormulaError, ValueError, KeyError, TypeError) as exc:
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

    Sửa trực tiếp lên bản "đang làm việc" (WORKING_FILES[file_id]) rồi trả về
    NGUYÊN VẸN response giống /api/detect-noise (để FE tái dùng renderStep4()
    hiển thị luôn số lỗi CÒN LẠI sau khi xử lý xong nhóm này).
    """
    payload = request.get_json()
    file_id = payload.get("file_id")
    df = _get_working_df(file_id)
    if df is None:
        return jsonify({"error": "file_id không tồn tại, hãy upload lại file"}), 404

    try:
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

        noise_type = payload["noise_type"]
        rows_payload = payload.get("rows", [])

        if noise_type == "duplicate_row":
            # Trùng dòng: chỉ có 1 hành động hợp lý là XOÁ các dòng được tick
            # -- không đi qua apply_handling() vì đó là hàm xử lý theo CỘT,
            # còn đây là xoá thẳng theo row_index, không gắn với cột nào.
            row_indices = [int(item["row_number"]) - 1 for item in rows_payload]
            existing = [i for i in row_indices if i in df.index]
            df = df.drop(index=existing)
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
                df, _stats = apply_handling(df, column_configs, fake_findings, [choice])

        WORKING_FILES[file_id] = df

        # Detect lại trên bản MỚI để FE biết chính xác còn lỗi gì -- phần vừa
        # xử lý xong sẽ tự biến mất khỏi kết quả.
        findings = detect_noise(
            df, column_configs, duplicate_row_config=duplicate_row_config, cross_field_rules=cross_field_rules
        )
    except (FormulaError, ValueError, KeyError, TypeError) as exc:
        return jsonify({"error": f"Cấu hình xử lý không hợp lệ: {exc}"}), 400

    flagged_rows_df = get_flagged_rows(df, findings)
    flagged_rows_out = flagged_rows_df.copy()
    flagged_rows_out.insert(0, "row_number", flagged_rows_out.index + 1)

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
            "flagged_rows": flagged_rows_out.to_dict(orient="records"),
        }
    )


@app.route("/api/working-data/<file_id>", methods=["GET"])
def working_data_api(file_id: str):
    """Bước 5 (nút "Xem dữ liệu sau xử lý"): trả về TOÀN BỘ dữ liệu ở trạng
    thái hiện tại (đã áp dụng các lần xử lý từng phần trước đó, nếu có) --
    không chỉ các dòng còn lỗi như /api/detect-noise, để người dùng xem lại
    được cả các dòng đã sạch."""
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
    df = WORKING_FILES.get(file_id, UPLOADED_FILES.get(file_id))
    if df is None:
        return jsonify({"error": "file_id không tồn tại, hãy upload lại file"}), 404

    download_id = str(uuid.uuid4())
    CLEANED_FILES[download_id] = df
    return jsonify({"final_row_count": len(df), "download_id": download_id})


@app.route("/api/download/<download_id>", methods=["GET"])
def download_cleaned_file(download_id: str):
    """Bước 4 (tiếp): trả file CSV đã làm sạch cho trình duyệt tải về, dựa
    trên download_id nhận được từ /api/apply-handling."""
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


if __name__ == "__main__":
    app.run(port=5000, debug=True)
