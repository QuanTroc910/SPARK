from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from .config import ColumnNoiseConfig, DuplicateRowConfig, NoiseType
from .detectors import DETECTORS, detect_duplicate_rows


def load_data(file_path: str) -> pd.DataFrame:
    """Đọc file CSV/Excel thành DataFrame.

    Ép hết mọi cột về kiểu str và tắt việc pandas tự suy đoán "giá trị thiếu"
    (keep_default_na=False, na_filter=False) -- vì chính các detector trong
    detectors.py mới là nơi quyết định thế nào là "thiếu", ta không muốn
    pandas âm thầm convert trước khi mình kịp kiểm tra.
    """
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path, dtype=str, keep_default_na=False, na_filter=False)
    if suffix in (".xlsx", ".xls"):
        return pd.read_excel(path, dtype=str).fillna("")
    raise ValueError(f"Unsupported file type: {suffix}")


@dataclass
class NoiseFinding:
    """1 bản ghi noise cụ thể: ở dòng nào, cột nào, loại gì, giá trị bị lỗi là gì.

    Với duplicate_row, column sẽ là "ALL" (hoặc tên các cột trong subset)
    vì noise này không thuộc về 1 cột riêng lẻ.
    """

    row_index: int
    column: str
    noise_type: str
    value: Any


def detect_noise(
    df: pd.DataFrame,
    column_configs: list[ColumnNoiseConfig],
    duplicate_row_config: Optional[DuplicateRowConfig] = None,
) -> list[NoiseFinding]:
    """Chạy toàn bộ detector theo config, gộp kết quả thành 1 list NoiseFinding.

    - column_configs: danh sách config theo TỪNG CỘT (missing/format/out_of_range/
      outlier/inconsistent_category/whitespace) -- ứng với các lựa chọn của
      người dùng trên UI cho từng cột.
    - duplicate_row_config: nếu khác None, sẽ chạy thêm bước kiểm tra trùng dòng
      trên toàn bộ DataFrame (không gắn với 1 cột cụ thể).
    """
    findings: list[NoiseFinding] = []

    # --- Bước 1: chạy các detector theo từng cột ---
    for cfg in column_configs:
        if cfg.column not in df.columns:
            continue
        series = df[cfg.column]
        for noise_type in cfg.noise_types:
            detector = DETECTORS[noise_type]
            mask = detector(series, cfg)
            for row_index in series.index[mask]:
                findings.append(
                    NoiseFinding(
                        row_index=row_index,
                        column=cfg.column,
                        noise_type=noise_type.value,
                        value=series.loc[row_index],
                    )
                )

    # --- Bước 2: kiểm tra trùng lặp dòng (nếu người dùng có bật) ---
    if duplicate_row_config is not None:
        mask = detect_duplicate_rows(df, duplicate_row_config.subset_columns)
        column_label = (
            ", ".join(duplicate_row_config.subset_columns)
            if duplicate_row_config.subset_columns
            else "ALL"
        )
        for row_index in df.index[mask]:
            findings.append(
                NoiseFinding(
                    row_index=row_index,
                    column=column_label,
                    noise_type=NoiseType.DUPLICATE_ROW.value,
                    value=None,
                )
            )

    return findings


def findings_to_dataframe(findings: list[NoiseFinding]) -> pd.DataFrame:
    if not findings:
        return pd.DataFrame(columns=["row_index", "column", "noise_type", "value"])
    return pd.DataFrame([f.__dict__ for f in findings])


def get_flagged_rows(df: pd.DataFrame, findings: list[NoiseFinding]) -> pd.DataFrame:
    """Gom lại NGUYÊN CẢ DÒNG cho bất kỳ dòng nào có ít nhất 1 ô (hoặc bị đánh
    dấu duplicate) bị phát hiện noise -- đúng yêu cầu "1 ô lỗi thì lấy cả dòng".

    Thêm cột noise_reasons liệt kê tất cả lý do (cột:loại_noise) của dòng đó,
    để người dùng biết vì sao dòng này bị gắn cờ.
    """
    reasons_per_row: dict[int, list[str]] = {}
    for f in findings:
        reasons_per_row.setdefault(f.row_index, []).append(f"{f.column}:{f.noise_type}")

    flagged_indices = sorted(reasons_per_row.keys())
    result = df.loc[flagged_indices].copy()
    result["noise_reasons"] = [", ".join(reasons_per_row[i]) for i in result.index]
    return result
