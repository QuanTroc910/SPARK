"""Backend Flask -- lớp "cầu nối" giữa frontend và code logic attribute_noise/.

File này KHÔNG chứa logic detect noise gì cả -- nó chỉ làm 3 việc:
  1. Nhận request (file upload, JSON config) từ frontend qua HTTP.
  2. Gọi đúng hàm trong attribute_noise/ (code lõi đã viết từ trước).
  3. Đóng gói kết quả thành JSON, trả ngược lại cho frontend.

Chạy thử: python3 app.py -> server chạy ở http://localhost:5000
"""

import uuid
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS

from attribute_noise.config import ColumnDType, ColumnNoiseConfig, DuplicateRowConfig, NoiseType
from attribute_noise.pipeline import detect_noise, get_flagged_rows, load_data

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

    column_configs = [_config_from_json(item) for item in payload.get("column_configs", [])]

    duplicate_row_config = None
    if payload.get("check_duplicate_row"):
        duplicate_row_config = DuplicateRowConfig(
            subset_columns=payload.get("duplicate_subset_columns")
        )

    findings = detect_noise(df, column_configs, duplicate_row_config=duplicate_row_config)
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


if __name__ == "__main__":
    app.run(port=5000, debug=True)
