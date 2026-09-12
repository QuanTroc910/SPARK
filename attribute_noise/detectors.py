import re
from datetime import datetime

import pandas as pd

from .config import ColumnDType, ColumnNoiseConfig, NoiseType

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^0\d{9}$")
INTEGER_RE = re.compile(r"^[+-]?\d+$")


def _is_missing(text: str, cfg: ColumnNoiseConfig) -> bool:
    normalized = text.strip().lower()
    return normalized in [p.lower() for p in cfg.missing_placeholders]


def detect_missing_value(series: pd.Series, cfg: ColumnNoiseConfig) -> pd.Series:
    return series.astype(str).apply(lambda v: _is_missing(v, cfg))


def _is_valid_format(value: str, cfg: ColumnNoiseConfig) -> bool:
    text = str(value).strip()
    if _is_missing(text, cfg):
        return True  # missing values are reported by detect_missing_value, not here

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
            datetime.strptime(text, fmt)
            return True
        except ValueError:
            return False
    if cfg.dtype == ColumnDType.CATEGORY:
        if not cfg.valid_categories:
            return True
        return text in cfg.valid_categories
    return True  # TEXT has no format constraint


def detect_format_noise(series: pd.Series, cfg: ColumnNoiseConfig) -> pd.Series:
    return ~series.astype(str).apply(lambda v: _is_valid_format(v, cfg))


def _to_numeric_or_nan(value: str) -> float:
    try:
        return float(str(value).strip())
    except ValueError:
        return float("nan")


def detect_out_of_range(series: pd.Series, cfg: ColumnNoiseConfig) -> pd.Series:
    if cfg.min_value is None and cfg.max_value is None:
        return pd.Series(False, index=series.index)

    numeric = series.astype(str).apply(_to_numeric_or_nan)
    lower_bound = cfg.min_value if cfg.min_value is not None else float("-inf")
    upper_bound = cfg.max_value if cfg.max_value is not None else float("inf")
    return numeric.notna() & ((numeric < lower_bound) | (numeric > upper_bound))


DETECTORS = {
    NoiseType.MISSING_VALUE: detect_missing_value,
    NoiseType.FORMAT_NOISE: detect_format_noise,
    NoiseType.OUT_OF_RANGE: detect_out_of_range,
}
