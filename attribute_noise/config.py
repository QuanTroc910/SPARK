from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class NoiseType(str, Enum):
    MISSING_VALUE = "missing_value"
    FORMAT_NOISE = "format_noise"
    OUT_OF_RANGE = "out_of_range"
    # to be added later: OUTLIER, INCONSISTENT_CATEGORY, WHITESPACE, DUPLICATE_ROW


class ColumnDType(str, Enum):
    INTEGER = "integer"
    FLOAT = "float"
    TEXT = "text"
    EMAIL = "email"
    PHONE = "phone"
    DATE = "date"
    CATEGORY = "category"


DEFAULT_MISSING_PLACEHOLDERS = ["", "n/a", "na", "null", "none", "?", "-", "--"]


@dataclass
class ColumnNoiseConfig:
    column: str
    dtype: ColumnDType
    noise_types: list[NoiseType]
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    date_format: Optional[str] = None
    valid_categories: Optional[list[str]] = None
    missing_placeholders: list[str] = field(
        default_factory=lambda: list(DEFAULT_MISSING_PLACEHOLDERS)
    )
