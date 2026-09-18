"""Xử lý (handling) các ô/dòng đã bị phát hiện noise ở attribute_noise/detectors.py
và cross_field_rules.py -- ĐÂY LÀ BƯỚC SAU detect_noise(), không phải thay thế.

Nguyên tắc quan trọng (xem CLAUDE.md mục 6): hành động khả dụng phải được
quyết định dựa trên CẶP (ColumnDType, NoiseType) -- tổng quát, áp dụng cho MỌI
cột, KHÔNG hardcode theo tên cột cụ thể. `get_available_actions()` chính là
bảng quyết định đó, dựng thành dict tra cứu.

Luồng dùng thực tế (xem app.py):
  1. Backend đã chạy detect_noise() ở bước trước, trả về `findings` cho FE.
  2. FE cho người dùng chọn, với MỖI (cột, loại noise) xuất hiện trong kết quả,
     1 hành động xử lý trong số get_available_actions(dtype, noise_type).
  3. FE gửi lại danh sách lựa chọn đó (HandlingChoice) -> gọi apply_handling().
"""

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import Enum
from typing import Optional

import pandas as pd

from .config import DEFAULT_MISSING_PLACEHOLDERS, ColumnDType, ColumnNoiseConfig, NoiseType
from .pipeline import NoiseFinding


class HandlingAction(str, Enum):
    """Tất cả hành động xử lý có thể có, gộp chung cho mọi dtype/noise_type.
    Loại nào dùng hành động nào là do `get_available_actions()` quyết định,
    KHÔNG phải mọi hành động đều hợp lệ cho mọi (dtype, noise_type)."""

    REMOVE_ROW = "remove_row"
    IMPUTE_MEAN = "impute_mean"
    IMPUTE_MEDIAN = "impute_median"
    IMPUTE_KNN = "impute_knn"
    IMPUTE_MODE = "impute_mode"
    FIXED_VALUE = "fixed_value"
    CAP_TO_RANGE = "cap_to_range"
    AUTO_NORMALIZE_CATEGORY = "auto_normalize_category"
    AUTO_CLEAN_WHITESPACE = "auto_clean_whitespace"
    KEEP = "keep"  # giữ nguyên, không sửa gì (vd outlier nhưng người dùng thấy vẫn hợp lý)


class DuplicateKeep(str, Enum):
    """Với 1 nhóm dòng trùng nhau, giữ lại bản ĐẦU TIÊN hay CUỐI CÙNG."""

    FIRST = "first"
    LAST = "last"


# Bảng quyết định (dtype, noise_type) -> các hành động khả dụng.
# Đây chính là bảng ở CLAUDE.md mục 6, chuyển thành dict tra cứu. INTEGER/FLOAT
# dùng chung 1 bộ hành động, EMAIL/PHONE dùng chung 1 bộ khác (không impute vì
# không thể đoán định danh cá nhân).
_NUMERIC_DTYPES = (ColumnDType.INTEGER, ColumnDType.FLOAT)
_ID_LIKE_DTYPES = (ColumnDType.EMAIL, ColumnDType.PHONE)

_ACTION_TABLE: dict[tuple[ColumnDType, NoiseType], list[HandlingAction]] = {}

for _dtype in _NUMERIC_DTYPES:
    _ACTION_TABLE[(_dtype, NoiseType.MISSING_VALUE)] = [
        HandlingAction.REMOVE_ROW,
        HandlingAction.IMPUTE_MEAN,
        HandlingAction.IMPUTE_MEDIAN,
        HandlingAction.IMPUTE_KNN,
        HandlingAction.FIXED_VALUE,
    ]
    _ACTION_TABLE[(_dtype, NoiseType.FORMAT_NOISE)] = list(
        _ACTION_TABLE[(_dtype, NoiseType.MISSING_VALUE)]
    )
    _ACTION_TABLE[(_dtype, NoiseType.OUT_OF_RANGE)] = [
        HandlingAction.REMOVE_ROW,
        HandlingAction.CAP_TO_RANGE,
        HandlingAction.IMPUTE_MEAN,
        HandlingAction.IMPUTE_MEDIAN,
        HandlingAction.IMPUTE_KNN,
        HandlingAction.FIXED_VALUE,
    ]
    _ACTION_TABLE[(_dtype, NoiseType.OUTLIER)] = [
        HandlingAction.REMOVE_ROW,
        HandlingAction.CAP_TO_RANGE,
        HandlingAction.IMPUTE_MEAN,
        HandlingAction.IMPUTE_MEDIAN,
        HandlingAction.IMPUTE_KNN,
        HandlingAction.KEEP,
    ]

_ACTION_TABLE[(ColumnDType.CATEGORY, NoiseType.MISSING_VALUE)] = [
    HandlingAction.REMOVE_ROW,
    HandlingAction.IMPUTE_MODE,
    HandlingAction.FIXED_VALUE,
]
_ACTION_TABLE[(ColumnDType.CATEGORY, NoiseType.INCONSISTENT_CATEGORY)] = [
    HandlingAction.AUTO_NORMALIZE_CATEGORY,
]

_ACTION_TABLE[(ColumnDType.TEXT, NoiseType.WHITESPACE_NOISE)] = [
    HandlingAction.AUTO_CLEAN_WHITESPACE,
]

for _dtype in _ID_LIKE_DTYPES:
    _ACTION_TABLE[(_dtype, NoiseType.MISSING_VALUE)] = [
        HandlingAction.REMOVE_ROW,
        HandlingAction.FIXED_VALUE,
    ]
    _ACTION_TABLE[(_dtype, NoiseType.FORMAT_NOISE)] = list(
        _ACTION_TABLE[(_dtype, NoiseType.MISSING_VALUE)]
    )

_ACTION_TABLE[(ColumnDType.DATE, NoiseType.MISSING_VALUE)] = [
    HandlingAction.REMOVE_ROW,
    HandlingAction.FIXED_VALUE,
]
_ACTION_TABLE[(ColumnDType.DATE, NoiseType.FORMAT_NOISE)] = list(
    _ACTION_TABLE[(ColumnDType.DATE, NoiseType.MISSING_VALUE)]
)


def get_available_actions(dtype: ColumnDType, noise_type: NoiseType) -> list[HandlingAction]:
    """Trả về danh sách hành động hợp lệ cho 1 cặp (dtype, noise_type).
    Danh sách rỗng nghĩa là cặp đó chưa có hành động xử lý nào được định nghĩa
    (vd whitespace_noise trên cột CATEGORY -- chưa cần vì demo hiện tại chỉ
    dùng whitespace_noise cho TEXT)."""
    return list(_ACTION_TABLE.get((dtype, noise_type), []))


@dataclass
class HandlingChoice:
    """1 lựa chọn xử lý do người dùng chọn trên UI cho 1 cặp (cột, loại noise)
    cụ thể -- giống ColumnNoiseConfig ở bước detect nhưng cho bước handle."""

    column: str
    noise_type: NoiseType
    action: HandlingAction
    fixed_value: Optional[str] = None  # dùng khi action = FIXED_VALUE


@dataclass
class DuplicateHandlingChoice:
    """Lựa chọn xử lý cho duplicate_row -- khác HandlingChoice vì đây là noise
    cấp DÒNG, không gắn với 1 cột cụ thể (giống DuplicateRowConfig ở pipeline.py)."""

    keep: DuplicateKeep = DuplicateKeep.FIRST
    subset_columns: Optional[list[str]] = None


def _is_missing_text(text: str) -> bool:
    normalized = str(text).strip().lower()
    return normalized in [p.lower() for p in DEFAULT_MISSING_PLACEHOLDERS]


def _clean_whitespace_value(value, disallowed_pattern: Optional[str]) -> str:
    """Tự động dọn 1 giá trị text: gộp tab/xuống dòng/khoảng trắng thừa về 1
    dấu cách, cắt khoảng trắng đầu-cuối, và xoá luôn ký tự nằm trong
    disallowed_chars_pattern nếu cột có khai báo."""
    text = str(value)
    text = re.sub(r"[\t\n\r]", " ", text)
    text = re.sub(r" {2,}", " ", text)
    text = text.strip()
    if disallowed_pattern:
        text = re.sub(disallowed_pattern, "", text)
    return text


def _best_canonical_match(
    value: str, valid_categories: list[str], threshold: float
) -> Optional[str]:
    """Tìm giá trị CHUẨN (canonical) giống nhất với `value` -- dùng chung ý
    tưởng với detect_inconsistent_category() nhưng ở đây cần chọn ra ĐÚNG 1
    giá trị tốt nhất để thay thế (không chỉ trả True/False như lúc detect)."""
    text = str(value).strip()
    normalized = text.lower()
    best_match: Optional[str] = None
    best_score = 0.0
    for canonical in valid_categories:
        canonical_normalized = canonical.strip().lower()
        if normalized == canonical_normalized:
            return canonical  # khớp tuyệt đối (chỉ khác hoa/thường/khoảng trắng)
        score = SequenceMatcher(None, normalized, canonical_normalized).ratio()
        if score > best_score:
            best_score = score
            best_match = canonical
    if best_match is not None and best_score >= threshold:
        return best_match
    return None


def _impute_knn(df: pd.DataFrame, column: str, flagged_rows: set, k: int = 5) -> pd.Series:
    """KNN impute thủ công, KHÔNG phụ thuộc scikit-learn (project không cần
    thêm dependency nặng chỉ vì 1 hàm impute).

    Ý tưởng: với mỗi dòng cần điền giá trị ở `column`, tìm k dòng "hàng xóm"
    gần nhất dựa trên khoảng cách Euclid trên các cột SỐ KHÁC (đã chuẩn hoá
    z-score để các cột đơn vị khác nhau, vd tuổi vs lương, không lấn át nhau),
    rồi lấy TRUNG BÌNH giá trị `column` của các hàng xóm đó.

    "Hàng xóm" chỉ được lấy từ các dòng CHƯA bị flag ở chính cột đang điền
    (donor phải có giá trị đáng tin ở column) -- nếu không đủ dữ liệu để so
    khoảng cách hoặc không có donor nào, trả về NaN cho dòng đó (nơi gọi sẽ tự
    fallback, xem apply_handling()).
    """
    numeric_df = df.apply(lambda s: pd.to_numeric(s, errors="coerce"))
    target = numeric_df[column]
    feature_cols = [c for c in numeric_df.columns if c != column]

    result = target.copy()
    if not feature_cols:
        return result

    features = numeric_df[feature_cols]
    std = features.std().replace(0, 1)  # tránh chia 0 cho cột hằng số
    normalized = (features - features.mean()) / std
    # Cột/ô không ép được thành số (vd cột TEXT lẫn trong data) -> coi như
    # "trung bình" (0 sau chuẩn hoá), không góp phần kéo lệch khoảng cách.
    normalized = normalized.fillna(0)

    donor_index = target.dropna().index.difference(pd.Index(flagged_rows))

    for row_index in flagged_rows:
        if row_index not in normalized.index or len(donor_index) == 0:
            continue
        diff = normalized.loc[donor_index] - normalized.loc[row_index]
        distances = (diff**2).sum(axis=1) ** 0.5
        nearest = distances.nsmallest(min(k, len(distances))).index
        if len(nearest) == 0:
            continue
        result.loc[row_index] = target.loc[nearest].mean()

    return result


def _format_numeric_for_column(value: float, cfg: Optional[ColumnNoiseConfig]) -> str:
    """DataFrame gốc đọc bằng dtype=str (xem load_data() trong pipeline.py) --
    mọi giá trị SỐ tính ra (mean/median/knn/cap) phải ép về CHUỖI trước khi
    gán ngược lại, nếu không pandas báo lỗi kiểu dữ liệu. Cột INTEGER thì làm
    tròn về số nguyên cho đúng ý nghĩa (vd tuổi không thể là 43.6)."""
    if cfg is not None and cfg.dtype == ColumnDType.INTEGER:
        return str(int(round(value)))
    if cfg is not None and cfg.dtype == ColumnDType.FLOAT:
        return str(round(value, 2))  # tránh số thập phân dài do sai số dấu phẩy động
    return str(value)


def _resolve_cap_bounds(
    df: pd.DataFrame, column: str, noise_type: NoiseType, cfg: Optional[ColumnNoiseConfig]
) -> tuple[float, float]:
    """Tính biên dưới/trên để CAP_TO_RANGE -- với out_of_range dùng thẳng
    min_value/max_value đã khai; với outlier phải TÍNH LẠI đúng công thức
    IQR/zscore (cùng method/threshold) như lúc detect_outlier(), để cap đúng
    ngay tại biên đã dùng để báo lỗi."""
    if noise_type == NoiseType.OUT_OF_RANGE:
        lower = cfg.min_value if cfg and cfg.min_value is not None else float("-inf")
        upper = cfg.max_value if cfg and cfg.max_value is not None else float("inf")
        return lower, upper

    numeric = pd.to_numeric(df[column], errors="coerce")
    valid = numeric.dropna()
    threshold = cfg.outlier_threshold if cfg else 1.5
    if cfg and cfg.outlier_method == "zscore":
        mean, std = valid.mean(), valid.std()
        if std == 0:
            return float("-inf"), float("inf")
        return mean - threshold * std, mean + threshold * std

    q1, q3 = valid.quantile(0.25), valid.quantile(0.75)
    iqr = q3 - q1
    return q1 - threshold * iqr, q3 + threshold * iqr


def apply_handling(
    df: pd.DataFrame,
    column_configs: list[ColumnNoiseConfig],
    findings: list[NoiseFinding],
    handling_choices: list[HandlingChoice],
    duplicate_handling: Optional[DuplicateHandlingChoice] = None,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Áp dụng toàn bộ lựa chọn xử lý lên `df`, trả về (df đã làm sạch, thống
    kê ngắn để FE hiển thị).

    QUAN TRỌNG: chỉ xử lý đúng những ô đã có trong `findings` (kết quả
    detect_noise() ở bước trước) -- KHÔNG detect lại từ đầu, để đảm bảo người
    dùng xử lý đúng những gì họ đã thấy ở Bước 3, không bị lệch nếu dữ liệu có
    thay đổi ngoài ý muốn.
    """
    result = df.copy()
    rows_to_remove: set = set()

    # Gom row_index bị flag theo (column, noise_type) từ findings -- key dùng
    # đúng giá trị string của NoiseType (findings.noise_type vốn đã là str).
    flagged_by_key: dict[tuple[str, str], set] = {}
    for f in findings:
        flagged_by_key.setdefault((f.column, f.noise_type), set()).add(f.row_index)

    config_by_column = {cfg.column: cfg for cfg in column_configs}

    for choice in handling_choices:
        flagged_rows = flagged_by_key.get((choice.column, choice.noise_type.value), set())
        if not flagged_rows or choice.column not in result.columns:
            continue  # không có ô nào bị flag loại này -> không có gì để xử lý
        cfg = config_by_column.get(choice.column)
        row_list = list(flagged_rows)

        if choice.action == HandlingAction.REMOVE_ROW:
            rows_to_remove.update(flagged_rows)
            continue  # xoá dòng làm SAU CÙNG (xem cuối hàm), không cần sửa ô ở đây

        if choice.action == HandlingAction.KEEP:
            continue

        if choice.action == HandlingAction.FIXED_VALUE:
            if choice.fixed_value is None:
                continue  # chưa nhập giá trị cố định -> bỏ qua, không ghi đè bằng rác
            result.loc[row_list, choice.column] = choice.fixed_value

        elif choice.action in (HandlingAction.IMPUTE_MEAN, HandlingAction.IMPUTE_MEDIAN):
            numeric = pd.to_numeric(result[choice.column], errors="coerce")
            donor_values = numeric.drop(index=flagged_rows, errors="ignore").dropna()
            if donor_values.empty:
                continue
            fill_value = (
                donor_values.mean()
                if choice.action == HandlingAction.IMPUTE_MEAN
                else donor_values.median()
            )
            result.loc[row_list, choice.column] = _format_numeric_for_column(fill_value, cfg)

        elif choice.action == HandlingAction.IMPUTE_MODE:
            donor_values = result[choice.column].drop(index=flagged_rows, errors="ignore")
            donor_values = donor_values[~donor_values.astype(str).apply(_is_missing_text)]
            if donor_values.empty:
                continue
            result.loc[row_list, choice.column] = donor_values.mode().iloc[0]

        elif choice.action == HandlingAction.IMPUTE_KNN:
            filled = _impute_knn(result, choice.column, flagged_rows)
            for row_index in row_list:
                value = filled.loc[row_index]
                if pd.notna(value):
                    result.loc[row_index, choice.column] = _format_numeric_for_column(value, cfg)

        elif choice.action == HandlingAction.CAP_TO_RANGE:
            lower, upper = _resolve_cap_bounds(result, choice.column, choice.noise_type, cfg)
            numeric = pd.to_numeric(result[choice.column], errors="coerce")
            capped = numeric.clip(lower=lower, upper=upper)
            for row_index in row_list:
                value = capped.loc[row_index]
                if pd.notna(value):
                    result.loc[row_index, choice.column] = _format_numeric_for_column(value, cfg)

        elif choice.action == HandlingAction.AUTO_NORMALIZE_CATEGORY:
            if cfg is None or not cfg.valid_categories:
                continue
            for row_index in row_list:
                match = _best_canonical_match(
                    result.loc[row_index, choice.column],
                    cfg.valid_categories,
                    cfg.category_similarity_threshold,
                )
                if match is not None:
                    result.loc[row_index, choice.column] = match

        elif choice.action == HandlingAction.AUTO_CLEAN_WHITESPACE:
            pattern = cfg.disallowed_chars_pattern if cfg else None
            for row_index in row_list:
                result.loc[row_index, choice.column] = _clean_whitespace_value(
                    result.loc[row_index, choice.column], pattern
                )

    if duplicate_handling is not None:
        is_dup = result.duplicated(
            subset=duplicate_handling.subset_columns, keep=duplicate_handling.keep.value
        )
        rows_to_remove.update(result.index[is_dup])

    removed_count = len(rows_to_remove)
    result = result.drop(index=list(rows_to_remove))

    stats = {
        "original_row_count": len(df),
        "removed_row_count": removed_count,
        "final_row_count": len(result),
    }
    return result, stats
