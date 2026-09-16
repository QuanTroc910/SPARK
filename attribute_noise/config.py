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


class RuleType(str, Enum):
    """4 loại "cross-field rule" -- kiểm tra mâu thuẫn LOGIC giữa 2 cột khác
    nhau. Khác hẳn NoiseType ở trên: các NoiseType chỉ nhìn 1 cột riêng lẻ
    (hoặc so khớp y hệt cả dòng với duplicate_row), còn rule ở đây cần HIỂU
    QUAN HỆ giữa 2 cột cụ thể -- không có cách nào tự suy ra được từ dữ liệu,
    LUÔN phải do người dùng tự khai qua UI cho từng file (xem CLAUDE.md mục 7:
    "Cross-field rule" -- không hardcode tên cột, chỉ hardcode 4 KHUÔN rule
    tổng quát này, còn nội dung rule cụ thể do người dùng điền).
    """

    COMPARE = "compare"  # so sánh 2 cột: cột_A <operator> cột_B
    CONDITIONAL = "conditional"  # NẾU cột_if <op> giá_trị THÌ cột_then <op> giá_trị
    FORMULA = "formula"  # 1 biểu thức so sánh, vd "thanh_tien == so_luong * don_gia"
    FUNCTIONAL_DEPENDENCY = "functional_dependency"  # cột_A xác định cột_B (1 chiều)


class CompareOperator(str, Enum):
    """Phép so sánh dùng cho rule COMPARE và 2 vế NẾU/THÌ của CONDITIONAL."""

    LT = "<"
    LTE = "<="
    GT = ">"
    GTE = ">="
    EQ = "=="
    NEQ = "!="


class RuleValueType(str, Enum):
    """Cách ép kiểu 1 giá trị (vốn là chuỗi thô đọc từ file) trước khi so
    sánh -- giống vai trò ColumnDType nhưng chỉ cần đủ 3 loại để SO SÁNH
    được, không cần phân biệt email/phone/category như ColumnDType."""

    NUMBER = "number"
    DATE = "date"
    TEXT = "text"


@dataclass
class CrossFieldRuleConfig:
    """Cấu hình 1 rule liên cột do NGƯỜI DÙNG tự khai trên UI (không có giá
    trị mặc định hợp lý nào cả -- xem docstring RuleType). `rule_type` quyết
    định NHÓM field nào bên dưới được dùng thật; các field của những rule_type
    khác cứ để None, không ảnh hưởng gì (giống cách ColumnNoiseConfig có nhiều
    field tuỳ dtype/noise_type nhưng không phải cột nào cũng dùng hết).

    label: tên rule do người dùng đặt (tuỳ chọn) -- chỉ để hiển thị cho dễ
    nhận biết trong kết quả, không ảnh hưởng logic detect.

    date_format: DÙNG CHUNG cho MỌI vế có value_type = DATE trong rule này
    (column_a/column_b của COMPARE, if_value/then_value của CONDITIONAL) --
    đơn giản hoá vì 1 rule hiếm khi cần 2 định dạng ngày khác nhau.
    """

    rule_type: RuleType
    label: Optional[str] = None
    date_format: Optional[str] = None  # dùng khi có vế nào value_type = DATE

    # --- Dùng cho COMPARE: so sánh "column_a operator column_b" ---
    column_a: Optional[str] = None
    operator: Optional[CompareOperator] = None
    column_b: Optional[str] = None
    value_type: RuleValueType = RuleValueType.NUMBER

    # --- Dùng cho CONDITIONAL: "NẾU if_column if_operator if_value
    # THÌ then_column then_operator then_value" ---
    if_column: Optional[str] = None
    if_operator: Optional[CompareOperator] = None
    if_value: Optional[str] = None
    if_value_type: RuleValueType = RuleValueType.TEXT
    then_column: Optional[str] = None
    then_operator: Optional[CompareOperator] = None
    then_value: Optional[str] = None
    then_value_type: RuleValueType = RuleValueType.TEXT

    # --- Dùng cho FORMULA: 1 biểu thức so sánh, vd "a == b * c" ---
    # CHỈ cho phép +,-,*,/ và tên cột (xem cross_field_rules.py) -- không dùng
    # eval()/exec() trần vì đó là lỗ hổng code injection nếu formula đến từ
    # input của người dùng.
    formula: Optional[str] = None
    tolerance: float = 0.01  # sai số cho phép khi so sánh bằng (==) trên số thực

    # --- Dùng cho FUNCTIONAL_DEPENDENCY: "determinant_column xác định
    # dependent_column" (1 CHIỀU -- không cần đúng ngược lại) ---
    determinant_column: Optional[str] = None
    dependent_column: Optional[str] = None
