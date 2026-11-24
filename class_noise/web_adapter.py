"""
CÁC HÀM PHỤ cho route Class Noise của web (`app.py::class_noise_detect_api`).

Vì sao tách ra file riêng: `app.py` chỉ nên "phiên dịch" JSON <-> Python (xem docstring đầu app.py),
nên những việc có chút logic -- đổi kết quả đã chạy trên bảng RÚT GỌN (sau bước chuẩn bị chung)
về lại ĐÚNG dòng của file gốc, chấm mức tin cậy theo "mức vượt mốc", rút gọn báo cáo chuẩn bị --
đặt ở đây. Module thuần Python, không phụ thuộc Flask.

"Mức vượt mốc" = (độ chính xác CV - độ chính xác đoán toàn lớp đông nhất) / (1 - cùng mốc đó).
0 = chỉ ngang đoán bừa, 1 = đạt mức tối đa, âm = còn kém cả đoán bừa.
"""

import math

import pandas as pd

from .combined import MethodFinding
from .preprocess import PreparedData, PreprocessConfig, PreprocessReport

# Dưới ngưỡng này thì mô hình chỉ "hơi hơn" đoán bừa -> chỉ nên tham khảo danh sách. Dùng CHUNG với
# cảnh báo ở bước "Giảm số cột" (PreprocessConfig.low_margin_warning) để web chỉ có 1 con số.
# Ngưỡng 20% là TỰ ĐỀ XUẤT (chưa có căn cứ thống kê), ghi trong CLAUDE.md.
LOW_EXCESS = PreprocessConfig.__dataclass_fields__["low_margin_warning"].default

# Báo cáo trả cho giao diện chỉ liệt kê tối đa ngần này nhóm/dòng (số tổng vẫn đầy đủ).
MAX_LISTED_IN_RESPONSE = 50

# Tên ngắn của từng phương pháp thành phần của bộ kết hợp, dùng trong câu nhận xét trả cho giao diện.
COMPONENT_LABELS = {
    "single_learning": "Confident Learning (Random Forest)",
    "distance_based": "Mutual k-NN",
    "ensemble_based": "Ensemble",
}


def finite(value):
    """Số hữu hạn -> float; NaN / inf / None -> None (jsonify không viết được NaN thành JSON hợp lệ)."""
    if value is None:
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def string_frame(prepared: PreparedData) -> pd.DataFrame:
    """Bản sao của bảng đã chuẩn bị, mọi cột ở dạng CHUỖI.

    `cap_outliers()` / `log_transform()` (feature_selection.py) làm việc trên bảng dạng chuỗi như
    `load_data()` trả về (đọc `dtype=str`); đưa bảng đã là số thực vào sẽ lỗi kiểu dữ liệu. `str(float)`
    giữ nguyên giá trị (không mất chữ số) nên đổi qua lại không làm đổi số liệu.
    """
    return prepared.df.astype(str)


def expand_findings(findings: list[dict], prepared: PreparedData) -> list[dict]:
    """Trả kết quả của dòng ĐẠI DIỆN về cả nhóm dòng trùng đặc trưng + cùng nhãn đã bị gộp.

    Bước chuẩn bị gộp mỗi nhóm dòng giống hệt (cùng đặc trưng, cùng nhãn) thành 1 đại diện để thuật toán
    không bị lệch bởi dòng lặp. Đại diện bị gắn cờ thì cả nhóm đều bị gắn cờ (cùng đặc trưng + cùng nhãn nên
    cùng số phận); các dòng thêm vào có `duplicate_of` = số dòng đại diện. Danh sách vẫn xếp theo điểm giảm dần.
    """
    if not prepared.groups:
        return findings
    out: list[dict] = []
    for f in findings:
        out.append(f)
        rep = int(f["row_number"])
        for member in prepared.groups.get(rep - 1, []):
            if int(member) + 1 != rep:
                copy = dict(f)
                copy["row_number"] = int(member) + 1
                copy["duplicate_of"] = rep
                out.append(copy)
    out.sort(key=lambda f: -(f.get("score") or 0.0))  # sort ổn định: hoà điểm giữ thứ tự cũ
    return out


def method_list_json(findings: list[MethodFinding], prepared: PreparedData) -> list[dict]:
    """Danh sách RIÊNG của 1 phương pháp thành phần (các dòng chính nó tự gắn cờ, kèm điểm nghi của nó) ở dạng JSON.

    Trả về cả nhóm dòng trùng đã gộp ở bước chuẩn bị (giống danh sách kết hợp, xem expand_findings) để số dòng
    khớp với bảng chính. Mỗi phần tử: row_number, recorded_label, suggested_label, score (+ duplicate_of nếu là bản trùng).
    """
    rows = [
        {
            "row_number": int(f.row_number),
            "recorded_label": f.recorded_label,
            "suggested_label": f.suggested_label,
            "score": finite(f.score),
        }
        for f in findings
    ]
    return expand_findings(rows, prepared)


def quality_assessment(excess: float | None, what: str = "Mô hình", low: float = LOW_EXCESS) -> dict | None:
    """Chấm độ tin cậy của danh sách nghi ngờ theo MỨC VƯỢT MỐC (thay luật cũ "<= 2 điểm % và dưới 30% mức trần").

    level: "none" (<= 0, không hơn đoán bừa) | "low" (0 < x < low) | "ok" (>= low). None nếu không có chỉ số
    (Mutual k-NN không train mô hình nên không có mức vượt mốc).
    """
    excess = finite(excess)
    if excess is None:
        return None
    pct = f"{excess * 100:.1f}%"
    if excess <= 0:
        level = "none"
        message = (
            f"{what} không hơn cách đoán toàn bộ là lớp đông nhất (mức vượt mốc {pct}), "
            "nên danh sách nghi ngờ gần như không đáng tin. Thử chọn lại cột đặc trưng."
        )
    elif excess < low:
        level = "low"
        message = (
            f"{what} chỉ vượt mốc đoán bừa {pct} (dưới {low * 100:.0f}%), "
            "nên danh sách nghi ngờ chỉ nên dùng để tham khảo."
        )
    else:
        level = "ok"
        message = f"{what} vượt mốc đoán bừa {pct}."
    return {"level": level, "excess": excess, "threshold": low, "message": message}


def preprocess_info(report: PreprocessReport) -> dict:
    """Báo cáo bước chuẩn bị chung ở dạng gọn cho giao diện: cột nào bị bỏ vì luật gì, số dòng bị loại / gộp,
    nhóm dòng mâu thuẫn (cùng đặc trưng khác nhãn)."""
    data = report.to_dict()
    data["conflict_groups_total"] = data["n_conflict_groups"]
    data["conflict_groups"] = data["conflict_groups"][:MAX_LISTED_IN_RESPONSE]
    data["blank_feature_rows"] = data["blank_feature_rows"][:MAX_LISTED_IN_RESPONSE]
    return data
