from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class NoiseType(str, Enum):
    """Các loại attribute noise mà hệ thống hỗ trợ phát hiện.

    Mỗi giá trị enum tương ứng với 1 hàm detect riêng trong detectors.py
    (xem DETECTORS registry ở cuối file đó để biết map noise_type -> hàm nào).
    """

    MISSING_VALUE = "missing_value"
    FORMAT_NOISE = "format_noise"
    OUT_OF_RANGE = "out_of_range"
    OUTLIER = "outlier"
    INCONSISTENT_CATEGORY = "inconsistent_category"
    WHITESPACE_NOISE = "whitespace_noise"
    # DUPLICATE_ROW khác các loại trên: nó không kiểm tra TỪNG CỘT riêng lẻ mà
    # kiểm tra TOÀN BỘ DÒNG (hoặc 1 nhóm cột) so với các dòng khác trong data.
    # Vì vậy nó không nằm trong ColumnNoiseConfig mà có config + hàm xử lý riêng
    # (xem DuplicateRowConfig bên dưới và detect_duplicate_rows() trong detectors.py).
    DUPLICATE_ROW = "duplicate_row"


class ColumnDType(str, Enum):
    """Kiểu dữ liệu kỳ vọng của 1 cột, dùng để chọn cách kiểm tra format_noise."""

    INTEGER = "integer"
    FLOAT = "float"
    TEXT = "text"
    EMAIL = "email"
    PHONE = "phone"
    DATE = "date"
    CATEGORY = "category"


# Các chuỗi được coi là "giá trị thiếu" sau khi đã strip() + lower().
# Đây là danh sách mặc định, mỗi cột có thể override qua ColumnNoiseConfig.missing_placeholders
# nếu file dữ liệu dùng ký hiệu khác (ví dụ "unknown", "chưa có"...).
DEFAULT_MISSING_PLACEHOLDERS = ["", "n/a", "na", "null", "none", "?", "-", "--"]


@dataclass
class ColumnNoiseConfig:
    """Cấu hình noise cho 1 cột — tương ứng đúng 1-1 với những gì người dùng
    chọn trên UI: chọn cột nào, kiểu dữ liệu gì, muốn check những loại noise nào,
    và tham số riêng cho từng loại noise đó (min/max, format ngày, v.v.).

    Sau này khi có backend API, FE sẽ gửi lên 1 danh sách JSON có cấu trúc y hệt
    các field bên dưới, và backend chỉ cần dựng lại thành list[ColumnNoiseConfig].
    """

    column: str
    dtype: ColumnDType
    noise_types: list[NoiseType]

    # --- Tham số riêng cho OUT_OF_RANGE (chỉ áp dụng cột số) ---
    min_value: Optional[float] = None
    max_value: Optional[float] = None

    # --- Tham số riêng cho FORMAT_NOISE khi dtype = DATE ---
    date_format: Optional[str] = None  # ví dụ "%Y-%m-%d"

    # --- Tham số riêng cho INCONSISTENT_CATEGORY (và cũng dùng để check
    # FORMAT_NOISE/MISSING khi dtype = CATEGORY) ---
    valid_categories: Optional[list[str]] = None
    # Ngưỡng độ giống nhau (0.0 - 1.0) để coi 2 chuỗi là "cùng 1 category nhưng
    # viết khác nhau" (vd "Sale" vs "Sales"). Càng gần 1.0 càng khắt khe.
    category_similarity_threshold: float = 0.85

    # --- Tham số riêng cho OUTLIER (chỉ áp dụng cột số) ---
    # method: "iqr" (Interquartile Range) hoặc "zscore".
    outlier_method: str = "iqr"
    # threshold: hệ số nhân với IQR (thường dùng 1.5) hoặc số độ lệch chuẩn (zscore
    # thường dùng 3.0) để xác định biên trên/dưới của giá trị "bình thường".
    outlier_threshold: float = 1.5

    # --- Tham số riêng cho WHITESPACE_NOISE ---
    # Regex mô tả các ký tự KHÔNG được phép xuất hiện trong cột (vd r"[#@$%]").
    # Để None nếu không cần check ký tự đặc biệt, chỉ check khoảng trắng thừa.
    disallowed_chars_pattern: Optional[str] = None

    # --- Dùng chung cho MISSING_VALUE (và các hàm khác cần bỏ qua ô đang thiếu) ---
    missing_placeholders: list[str] = field(
        default_factory=lambda: list(DEFAULT_MISSING_PLACEHOLDERS)
    )


@dataclass
class DuplicateRowConfig:
    """Cấu hình cho việc phát hiện dòng bị trùng lặp (duplicate_row).

    subset_columns:
        - None -> so sánh trùng trên TOÀN BỘ các cột (dòng phải giống hệt nhau
          ở mọi cột mới bị coi là trùng).
        - ["id"] -> chỉ so sánh trên các cột được liệt kê (vd chỉ cần trùng "id"
          là bị coi là trùng, dù các cột khác có khác nhau -> bắt được cả
          "contradictory instances" nói trong bài báo: cùng id nhưng dữ liệu khác).
    """

    subset_columns: Optional[list[str]] = None
