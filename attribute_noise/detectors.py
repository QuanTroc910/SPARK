import re
from datetime import datetime
from difflib import SequenceMatcher

import pandas as pd

from .config import ColumnDType, ColumnNoiseConfig, NoiseType

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^0\d{9}$")
INTEGER_RE = re.compile(r"^[+-]?\d+$")


def _is_missing(text: str, cfg: ColumnNoiseConfig) -> bool:
    """Kiểm tra 1 chuỗi (đã ép về str) có phải là giá trị 'thiếu' hay không.

    Dùng chung cho mọi detector khác để BỎ QUA các ô đang thiếu -- vì 1 ô
    thiếu thì không nên vừa bị báo missing_value vừa bị báo thêm format_noise/
    out_of_range/... (tránh báo trùng nhiều loại noise trên cùng 1 ô).
    """
    normalized = text.strip().lower()
    return normalized in [p.lower() for p in cfg.missing_placeholders]


def detect_missing_value(series: pd.Series, cfg: ColumnNoiseConfig) -> pd.Series:
    """Loại noise 1: MISSING VALUE.

    Trả về Series bool cùng index với series đầu vào: True = ô đó bị thiếu.
    """
    return series.astype(str).apply(lambda v: _is_missing(v, cfg))


def _is_valid_format(value: str, cfg: ColumnNoiseConfig) -> bool:
    """Kiểm tra 1 giá trị có ĐÚNG định dạng kỳ vọng theo cfg.dtype hay không.

    Trả về True nghĩa là hợp lệ (không phải format noise); ô đang thiếu cũng
    được coi là "hợp lệ" ở đây vì nó đã được xử lý riêng bởi detect_missing_value.
    """
    text = str(value).strip()
    if _is_missing(text, cfg):
        return True

    if cfg.dtype == ColumnDType.INTEGER:
        return bool(INTEGER_RE.match(text))
    if cfg.dtype == ColumnDType.FLOAT:
        try:
            float(text)
            return True
        except ValueError:
            return False
    if cfg.dtype == ColumnDType.EMAIL:
        return bool(EMAIL_RE.match(text))
    if cfg.dtype == ColumnDType.PHONE:
        return bool(PHONE_RE.match(text))
    if cfg.dtype == ColumnDType.DATE:
        fmt = cfg.date_format or "%Y-%m-%d"
        try:
            # strptime tự validate luôn cả ngày/tháng vô lý (vd ngày 45, tháng 13)
            datetime.strptime(text, fmt)
            return True
        except ValueError:
            return False
    if cfg.dtype == ColumnDType.CATEGORY:
        if not cfg.valid_categories:
            return True
        return text in cfg.valid_categories
    return True  # TEXT: không ràng buộc định dạng


def detect_format_noise(series: pd.Series, cfg: ColumnNoiseConfig) -> pd.Series:
    """Loại noise 2: FORMAT / TYPE NOISE (sai định dạng, sai kiểu dữ liệu)."""
    return ~series.astype(str).apply(lambda v: _is_valid_format(v, cfg))


def _to_numeric_or_nan(value: str) -> float:
    """Cố ép 1 chuỗi về số thực; không ép được thì trả về NaN.

    Dùng cho các detector cần tính toán trên số (out_of_range, outlier) --
    những ô không parse được số coi như bỏ qua ở đây (đã có format_noise
    lo phần báo lỗi định dạng riêng).
    """
    try:
        return float(str(value).strip())
    except ValueError:
        return float("nan")


def detect_out_of_range(series: pd.Series, cfg: ColumnNoiseConfig) -> pd.Series:
    """Loại noise 3: OUT OF RANGE (giá trị đúng định dạng nhưng vô lý về mặt
    logic, vd tuổi = -5, tuổi = 250) -- so với min_value/max_value đã khai báo.
    """
    if cfg.min_value is None and cfg.max_value is None:
        return pd.Series(False, index=series.index)

    numeric = series.astype(str).apply(_to_numeric_or_nan)
    lower_bound = cfg.min_value if cfg.min_value is not None else float("-inf")
    upper_bound = cfg.max_value if cfg.max_value is not None else float("inf")
    # numeric.notna(): chỉ tính out_of_range cho các ô ĐÃ parse được thành số.
    return numeric.notna() & ((numeric < lower_bound) | (numeric > upper_bound))


def detect_outlier(series: pd.Series, cfg: ColumnNoiseConfig) -> pd.Series:
    """Loại noise 4: OUTLIER (giá trị đúng định dạng, trong khoảng hợp lệ,
    nhưng lệch bất thường so với PHÂN BỐ chung của cả cột).

    Hỗ trợ 2 phương pháp qua cfg.outlier_method:
      - "iqr": outlier nếu nằm ngoài [Q1 - k*IQR, Q3 + k*IQR], k = outlier_threshold
               (thường dùng k = 1.5). Ưu điểm: không giả định phân phối chuẩn.
      - "zscore": outlier nếu |giá trị - mean| > k * độ lệch chuẩn (k thường = 3).
               Chỉ chính xác khi dữ liệu gần với phân phối chuẩn.
    """
    numeric = series.astype(str).apply(_to_numeric_or_nan)
    valid_numeric = numeric.dropna()

    # Cần đủ số lượng điểm dữ liệu mới tính median/std đáng tin cậy.
    if len(valid_numeric) < 4:
        return pd.Series(False, index=series.index)

    if cfg.outlier_method == "zscore":
        mean = valid_numeric.mean()
        std = valid_numeric.std()
        if std == 0:  # mọi giá trị giống hệt nhau -> không có outlier
            return pd.Series(False, index=series.index)
        lower_bound = mean - cfg.outlier_threshold * std
        upper_bound = mean + cfg.outlier_threshold * std
    else:  # mặc định dùng "iqr"
        q1 = valid_numeric.quantile(0.25)
        q3 = valid_numeric.quantile(0.75)
        iqr = q3 - q1
        lower_bound = q1 - cfg.outlier_threshold * iqr
        upper_bound = q3 + cfg.outlier_threshold * iqr

    return numeric.notna() & ((numeric < lower_bound) | (numeric > upper_bound))


def detect_inconsistent_category(series: pd.Series, cfg: ColumnNoiseConfig) -> pd.Series:
    """Loại noise 5: INCONSISTENT CATEGORY (cùng 1 ý nghĩa nhưng viết khác
    nhau, vd "Nam"/"nam"/"NAM "/"Sale" thay vì "Sales").

    Cần cfg.valid_categories = danh sách giá trị "chuẩn" (canonical). Với mỗi
    ô không khớp CHÍNH XÁC 1 giá trị chuẩn nào, ta thử:
      1) So khớp sau khi chuẩn hoá (strip + lowercase) -- bắt lỗi khác hoa/thường
         hoặc khoảng trắng thừa.
      2) Nếu vẫn không khớp, dùng SequenceMatcher (độ giống nhau chuỗi, 0..1)
         để bắt lỗi chính tả nhỏ (vd thiếu/thừa vài ký tự) so với 1 giá trị chuẩn.
    Nếu ô đó không giống bất kỳ giá trị chuẩn nào (kể cả sau chuẩn hoá/fuzzy),
    hàm này COI NHƯ KHÔNG PHẢI inconsistent_category (có thể là noise loại khác,
    hoặc dữ liệu thật sự không hợp lệ -- không thuộc phạm vi hàm này).
    """
    if not cfg.valid_categories:
        return pd.Series(False, index=series.index)

    canonical_exact = set(cfg.valid_categories)
    canonical_normalized = [c.strip().lower() for c in cfg.valid_categories]

    def is_inconsistent(value) -> bool:
        text = str(value).strip()
        if _is_missing(text, cfg):
            return False
        if text in canonical_exact:
            return False  # khớp chính xác -> không có vấn đề gì

        normalized = text.lower()
        for canon_norm in canonical_normalized:
            if normalized == canon_norm:
                return True  # chỉ khác hoa/thường hoặc khoảng trắng
            similarity = SequenceMatcher(None, normalized, canon_norm).ratio()
            if similarity >= cfg.category_similarity_threshold:
                return True  # đủ giống -> nghi là lỗi chính tả của giá trị chuẩn này
        return False

    return series.astype(str).apply(is_inconsistent)


def detect_whitespace_noise(series: pd.Series, cfg: ColumnNoiseConfig) -> pd.Series:
    """Loại noise 6: WHITESPACE / SPECIAL CHARACTER NOISE.

    Bắt các trường hợp:
      - Có khoảng trắng thừa ở đầu/cuối chuỗi (vd "  Ten Nguoi").
      - Có ký tự tab/xuống dòng lẫn trong giá trị.
      - Có 2 khoảng trắng liên tiếp trở lên ở giữa chuỗi.
      - (tuỳ chọn) Có ký tự nằm trong cfg.disallowed_chars_pattern, vd "###".
    """
    disallowed_pattern = (
        re.compile(cfg.disallowed_chars_pattern) if cfg.disallowed_chars_pattern else None
    )

    def has_issue(value) -> bool:
        text = str(value)
        stripped = text.strip()
        if _is_missing(stripped, cfg):
            return False
        if text != stripped:
            return True  # thừa khoảng trắng đầu/cuối
        if re.search(r"[\t\n\r]", text):
            return True  # có tab/xuống dòng
        if re.search(r" {2,}", text):
            return True  # có 2+ khoảng trắng liên tiếp ở giữa
        if disallowed_pattern and disallowed_pattern.search(text):
            return True  # có ký tự đặc biệt không cho phép
        return False

    return series.astype(str).apply(has_issue)


def detect_duplicate_rows(df: pd.DataFrame, subset_columns: list[str] | None = None) -> pd.Series:
    """Loại noise 7: DUPLICATE ROW -- khác các hàm trên vì kiểm tra CẢ DÒNG
    (hoặc 1 nhóm cột) thay vì 1 cột đơn lẻ, nên nhận vào cả DataFrame.

    keep=False: đánh dấu True cho TẤT CẢ các dòng nằm trong 1 nhóm trùng nhau
    (kể cả dòng xuất hiện đầu tiên), để người dùng nhìn thấy đủ các bản sao
    và tự quyết định giữ lại dòng nào.
    """
    return df.duplicated(subset=subset_columns, keep=False)


# Registry: map noise_type -> hàm detect tương ứng.
# Lưu ý: DUPLICATE_ROW không nằm ở đây vì nó thao tác trên cả DataFrame,
# không theo khuôn signature (series, cfg) như các loại còn lại -- nó được
# xử lý riêng trong pipeline.detect_noise().
DETECTORS = {
    NoiseType.MISSING_VALUE: detect_missing_value,
    NoiseType.FORMAT_NOISE: detect_format_noise,
    NoiseType.OUT_OF_RANGE: detect_out_of_range,
    NoiseType.OUTLIER: detect_outlier,
    NoiseType.INCONSISTENT_CATEGORY: detect_inconsistent_category,
    NoiseType.WHITESPACE_NOISE: detect_whitespace_noise,
}
