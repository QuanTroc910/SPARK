from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .config import ColumnNoiseConfig
from .detectors import DETECTORS


def load_data(file_path: str) -> pd.DataFrame:
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path, dtype=str, keep_default_na=False, na_filter=False)
    if suffix in (".xlsx", ".xls"):
        return pd.read_excel(path, dtype=str).fillna("")
    raise ValueError(f"Unsupported file type: {suffix}")


@dataclass
class NoiseFinding:
    row_index: int
    column: str
    noise_type: str
    value: Any


def detect_noise(
    df: pd.DataFrame, column_configs: list[ColumnNoiseConfig]
) -> list[NoiseFinding]:
    findings: list[NoiseFinding] = []
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
    return findings


def findings_to_dataframe(findings: list[NoiseFinding]) -> pd.DataFrame:
    if not findings:
        return pd.DataFrame(columns=["row_index", "column", "noise_type", "value"])
    return pd.DataFrame([f.__dict__ for f in findings])


def get_flagged_rows(df: pd.DataFrame, findings: list[NoiseFinding]) -> pd.DataFrame:
    reasons_per_row: dict[int, list[str]] = {}
    for f in findings:
        reasons_per_row.setdefault(f.row_index, []).append(f"{f.column}:{f.noise_type}")

    flagged_indices = sorted(reasons_per_row.keys())
    result = df.loc[flagged_indices].copy()
    result["noise_reasons"] = [", ".join(reasons_per_row[i]) for i in result.index]
    return result
