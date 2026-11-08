"""Logic cho 4 "Free Tools" nhanh (Xoá dòng trùng, Cắt khoảng trắng thừa,
Điền/xoá ô trống đơn giản, Xoá dòng trống hoàn toàn) -- KHÁC HẲN luồng
Attribute Noise đầy đủ (`pipeline.detect_noise()` + `attribute_handling.
apply_handling()`) ở chỗ:
  - KHÔNG cần `ColumnNoiseConfig`/`NoiseFinding` gì cả -- chạy NGAY trên
    DataFrame, không phải "detect xong mới handle" 2 lượt tách rời.
  - Mỗi hàm nhận `df` vào, trả về (df đã xử lý, stats) LUÔN trong 1 lần gọi
    -- đúng tinh thần "Free Tools" của 1 trang tham khảo (CYD): bấm 1 phát
    là xong, không cấu hình nhiều bước như Workspace (5 bước chính).
  - TÁI DÙNG logic "thế nào là ô thiếu"/"thế nào là khoảng trắng thừa" đã
    có sẵn trong `attribute_handling.py` (không viết lại lần 2) -- để người
    dùng dùng Free Tools hay Workspace đều ra CÙNG 1 định nghĩa, không lệch
    kết quả giữa 2 luồng.
  - `_is_missing_text`/`_clean_whitespace_value` import trực tiếp (kể cả có
    dấu `_` ở đầu, quy ước "riêng tư" của Python chỉ là quy ước, không bị
    chặn) thay vì copy lại: 2 module cùng nằm trong package `attribute_noise`,
    chia sẻ logic nội bộ như vậy là hợp lý, tránh 2 nơi định nghĩa "thiếu"
    khác nhau rồi lệch nhau theo thời gian. KHÔNG dùng `detectors._is_missing`
    (bản có `cfg: ColumnNoiseConfig` tuỳ biến theo cột) vì Free Tools không
    thu thập cấu hình riêng từng cột -- `_is_missing_text` (dùng thẳng
    `DEFAULT_MISSING_PLACEHOLDERS`) mới đúng tinh thần "không cấu hình gì".
"""

from typing import Optional

import pandas as pd

from .attribute_handling import DuplicateKeep, _clean_whitespace_value, _is_missing_text


class QuickToolError(Exception):
    """Lỗi nghiệp vụ của 4 Free Tools (cột không tồn tại, thiếu giá trị cố
    định...) -- app.py bắt lỗi này để trả HTTP 400 kèm message rõ ràng,
    cùng cách các module khác trong dự án xử lý (vd AccountError,
    ConversionError)."""


def _stats(df_before: pd.DataFrame, df_after: pd.DataFrame, cells_changed: int = 0) -> dict:
    """Gói thống kê ngắn để FE hiển thị -- cùng 3 field gốc
    (`original_row_count`/`removed_row_count`/`final_row_count`) như
    `apply_handling()` ở luồng đầy đủ, cộng `cells_changed` khi có (chỉ
    SỬA giá trị chứ không xoá dòng nào, vd cắt khoảng trắng/điền giá trị)."""
    return {
        "original_row_count": len(df_before),
        "removed_row_count": len(df_before) - len(df_after),
        "final_row_count": len(df_after),
        "cells_changed": cells_changed,
    }


def quick_remove_duplicates(
    df: pd.DataFrame, subset_columns: Optional[list[str]], keep: DuplicateKeep
) -> tuple[pd.DataFrame, dict]:
    """Xoá dòng trùng -- `subset_columns=None` nghĩa là so trùng trên TOÀN
    BỘ cột (giống `DuplicateRowConfig.subset_columns` ở luồng đầy đủ)."""
    if subset_columns:
        missing = [c for c in subset_columns if c not in df.columns]
        if missing:
            raise QuickToolError(f"Cột không tồn tại: {', '.join(missing)}")
    result = df.drop_duplicates(subset=subset_columns, keep=keep.value).reset_index(drop=True)
    return result, _stats(df, result)


def quick_trim_whitespace(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Cắt khoảng trắng thừa trên MỌI Ô của bảng -- không cần chọn cột, vì
    đây vốn là hành động "an toàn, luôn bật mặc định" ở luồng đầy đủ
    (`AUTO_CLEAN_WHITESPACE`), áp dụng sẵn cho tất cả các cột ở đây."""
    result = df.copy()
    cells_changed = 0
    for col in result.columns:
        cleaned = result[col].apply(lambda v: _clean_whitespace_value(v, None))
        cells_changed += int((cleaned != result[col]).sum())
        result[col] = cleaned
    return result, _stats(df, result, cells_changed)


def quick_fill_or_remove_blanks(
    df: pd.DataFrame, column: str, action: str, fixed_value: Optional[str] = None
) -> tuple[pd.DataFrame, dict]:
    """Điền/xoá ô trống Ở ĐÚNG 1 CỘT người dùng tự gõ tên -- `action`:
    "remove_row" hoặc "fixed_value", đúng 2 trong số các lựa chọn
    `get_available_actions()` đã có cho MISSING_VALUE ở luồng đầy đủ, bớt
    đi impute mean/median/KNN/mode cho đúng tinh thần "không cấu hình" của
    Free Tools (ai cần impute thông minh hơn thì dùng Workspace)."""
    if column not in df.columns:
        raise QuickToolError(f"Cột '{column}' không tồn tại trong file")
    is_blank = df[column].astype(str).apply(_is_missing_text)

    if action == "remove_row":
        result = df[~is_blank].reset_index(drop=True)
        return result, _stats(df, result)

    if action == "fixed_value":
        if not fixed_value:
            raise QuickToolError("Thiếu giá trị cố định để điền vào ô trống")
        result = df.copy()
        result.loc[is_blank, column] = fixed_value
        return result, _stats(df, result, cells_changed=int(is_blank.sum()))

    raise QuickToolError(f"action không hợp lệ: {action}")


def is_row_fully_empty(df: pd.DataFrame) -> pd.Series:
    """Dòng mà MỌI cột đều "thiếu" (theo đúng định nghĩa `_is_missing_text`
    dùng chung toàn hệ thống) -- KHÁC `missing_value` (xét từng Ô riêng lẻ):
    ở đây xét CẢ DÒNG, tương đương "Remove empty rows" của tool tham khảo,
    loại noise cấp dòng mà luồng Attribute Noise đầy đủ CHƯA có detector
    riêng (chỉ mới có `duplicate_row` ở cấp dòng)."""
    if df.empty:
        return pd.Series(dtype=bool)
    return df.apply(lambda row: all(_is_missing_text(v) for v in row), axis=1)


def quick_remove_empty_rows(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    mask = is_row_fully_empty(df)
    result = df[~mask].reset_index(drop=True)
    return result, _stats(df, result)
