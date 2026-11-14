"""Logic cho 4 "Free Tools" nhanh (Xoá dòng trùng, Cắt khoảng trắng thừa,
Điền/xoá ô trống đơn giản, Xoá dòng trống hoàn toàn) -- KHÁC HẲN luồng
Attribute Noise đầy đủ (`pipeline.detect_noise()` + `attribute_handling.
apply_handling()`) ở chỗ:
  - KHÔNG cần `ColumnNoiseConfig`/`NoiseFinding` gì cả -- chạy NGAY trên
    DataFrame, không phải "detect xong mới handle" 2 lượt tách rời.
  - Mỗi hàm nhận `df` vào, trả về (df đã xử lý, stats) LUÔN trong 1 lần gọi
    -- đúng tinh thần "Free Tools" của 1 trang tham khảo (CYD): bấm 1 phát
    là xong, không cấu hình nhiều bước như Workspace (5 bước chính).
  - TÁI DÙNG logic "thế nào là ô thiếu" đã có sẵn trong `attribute_handling.py`
    (không viết lại lần 2) -- để Free Tools và Workspace ra CÙNG 1 định nghĩa.
  - `_is_missing_text` import trực tiếp (kể cả có dấu `_` ở đầu, quy ước
    "riêng tư" của Python chỉ là quy ước) thay vì copy lại -- 2 module cùng
    nằm trong package `attribute_noise`. KHÔNG dùng `detectors._is_missing`
    (bản có `cfg: ColumnNoiseConfig` tuỳ biến theo cột) vì Free Tools không
    thu thập cấu hình riêng từng cột.
  - **MỚI**: 4 tuỳ chọn thêm cho đúng bằng tool tham khảo (CYD) -- xem từng
    hàm bên dưới. Việc cắt khoảng trắng ở đây dùng hàm RIÊNG
    `_clean_whitespace_advanced()` (KHÔNG tái dùng `_clean_whitespace_value()`
    của attribute_handling.py nữa) vì hàm cũ LUÔN gộp khoảng trắng lặp lại,
    không có cờ bật/tắt -- tool tham khảo cần "Gộp khoảng trắng lặp lại" là
    tuỳ chọn RIÊNG (mặc định TẮT), còn Workspace đầy đủ vẫn giữ nguyên hành
    vi cũ của `_clean_whitespace_value()` (không đổi, để không ảnh hưởng
    tính năng đã test kỹ).
"""

import re
from typing import Optional

import pandas as pd

from .attribute_handling import DuplicateKeep, _is_missing_text


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


# U+200B..200D (zero-width space/non-joiner/joiner) + U+FEFF (BOM, cũng gọi là
# "zero width no-break space") -- đúng 4 ký tự tool tham khảo (CYD) ghi rõ
# trong mô tả "zero-width characters". U+00A0 (non-breaking space) KHÔNG nằm
# trong nhóm này -- xử lý riêng ở dưới (đổi thành dấu cách thường, không XOÁ
# hẳn, vì nó vẫn là 1 dấu cách "nhìn thấy được", chỉ sai loại ký tự).
_ZERO_WIDTH_PATTERN = re.compile("[​‌‍﻿]")


def _clean_whitespace_advanced(value, collapse_repeated: bool, remove_zero_width: bool) -> str:
    """Cắt khoảng trắng cho tool "Cắt khoảng trắng thừa" -- LUÔN đổi
    non-breaking space (U+00A0) thành dấu cách thường rồi cắt đầu/cuối
    (hành vi CƠ BẢN, không tắt được, vì đây chính là lý do tool này tồn tại);
    2 THAM SỐ còn lại là tuỳ chọn BẬT/TẮT riêng, khớp đúng 2 checkbox của
    tool tham khảo (CYD): `collapse_repeated` (gộp nhiều dấu cách liên tiếp
    thành 1, mặc định TẮT) và `remove_zero_width` (xoá ký tự vô hình, mặc
    định BẬT)."""
    text = str(value).replace(" ", " ")
    text = re.sub(r"[\t\n\r]", " ", text)
    if remove_zero_width:
        text = _ZERO_WIDTH_PATTERN.sub("", text)
    text = text.strip()
    if collapse_repeated:
        text = re.sub(r" {2,}", " ", text)
    return text


def _normalize_for_compare(value, ignore_case: bool, ignore_whitespace: bool) -> str:
    """Chuẩn hoá 1 giá trị CHỈ ĐỂ SO SÁNH xem có trùng không -- KHÔNG dùng để
    ghi lại vào dữ liệu (dữ liệu gốc giữ nguyên, xem `quick_remove_duplicates`)."""
    text = str(value)
    if ignore_whitespace:
        text = re.sub(r"\s+", " ", text.strip())
    if ignore_case:
        text = text.lower()
    return text


def _compare_frame(
    df: pd.DataFrame, subset_columns: Optional[list[str]], ignore_case: bool, ignore_whitespace: bool
) -> pd.DataFrame:
    """Bảng CHỈ DÙNG ĐỂ SO SÁNH tìm dòng trùng: đúng các cột được chọn (rỗng = toàn
    bộ cột), và nếu bật bỏ qua hoa/thường / khoảng trắng thì mỗi ô đã được chuẩn
    hoá (xem `_normalize_for_compare`). Báo lỗi nếu tên cột không tồn tại."""
    compare_columns = subset_columns if subset_columns else list(df.columns)
    missing = [c for c in compare_columns if c not in df.columns]
    if missing:
        raise QuickToolError(f"Cột không tồn tại: {', '.join(missing)}")
    frame = df[compare_columns]
    if ignore_case or ignore_whitespace:
        # DataFrame.map() (KHÔNG phải .applymap() -- đã bị XOÁ ở pandas 3.0).
        frame = frame.map(lambda v: _normalize_for_compare(v, ignore_case, ignore_whitespace))
    return frame


def quick_remove_duplicates(
    df: pd.DataFrame,
    subset_columns: Optional[list[str]],
    keep: DuplicateKeep,
    ignore_case: bool = False,
    ignore_whitespace: bool = False,
) -> tuple[pd.DataFrame, dict]:
    """Xoá dòng trùng -- `subset_columns=None` nghĩa là so trùng trên TOÀN
    BỘ cột (giống `DuplicateRowConfig.subset_columns` ở luồng đầy đủ).

    `ignore_case`/`ignore_whitespace` (MỚI, khớp 2 checkbox "Ignore case"/
    "Ignore extra spaces" của tool tham khảo): chỉ ảnh hưởng tới việc SO
    SÁNH 2 dòng có được coi là trùng hay không (vd "An" và "AN" tính là
    trùng nếu bật `ignore_case`) -- GIÁ TRỊ THẬT được giữ lại (bản được giữ)
    vẫn y nguyên, không bị hạ về chữ thường hay cắt khoảng trắng."""
    compare_columns = subset_columns if subset_columns else list(df.columns)
    missing = [c for c in compare_columns if c not in df.columns]
    if missing:
        raise QuickToolError(f"Cột không tồn tại: {', '.join(missing)}")

    if not (ignore_case or ignore_whitespace):
        result = df.drop_duplicates(subset=subset_columns, keep=keep.value).reset_index(drop=True)
        return result, _stats(df, result)

    # Dựng 1 bảng CHUẨN HOÁ riêng chỉ để tìm dòng trùng -- áp dụng
    # _normalize_for_compare() lên đúng các cột đang so sánh, rồi lấy mask
    # "dòng nào bị coi là bản trùng" từ bảng chuẩn hoá đó, áp NGƯỢC lại lên
    # DataFrame GỐC (để không làm hỏng giá trị thật khi xoá).
    # DataFrame.map() (KHÔNG phải .applymap() -- đã bị XOÁ hẳn ở pandas 3.0,
    # project này dùng pandas>=2.0 nên phải dùng tên mới để chạy được trên
    # cả 2 phiên bản mới/cũ).
    compare_df = _compare_frame(df, subset_columns, ignore_case, ignore_whitespace)
    is_dup = compare_df.duplicated(keep=keep.value)
    result = df[~is_dup].reset_index(drop=True)
    return result, _stats(df, result)


def preview_duplicate_rows(
    df: pd.DataFrame,
    subset_columns: Optional[list[str]],
    keep: DuplicateKeep,
    ignore_case: bool = False,
    ignore_whitespace: bool = False,
    limit: int = 100,
) -> dict:
    """MỚI -- dữ liệu cho nút "Xem các dòng trùng" của tool Xoá dòng trùng.

    Cùng cách so sánh với `quick_remove_duplicates()` (cùng cột so, cùng 2 tuỳ
    chọn bỏ qua hoa/thường + khoảng trắng, cùng `keep`) nên tập dòng bị đánh
    dấu "Xoá" ở đây KHỚP ĐÚNG tập dòng thật sự bị xoá -- test có kiểm chứng.
    Trả về mọi dòng thuộc 1 NHÓM TRÙNG (cả bản được giữ lẫn các bản bị xoá, để
    người dùng thấy dòng nào trùng với dòng nào), xếp theo nhóm: các dòng cùng
    nhóm nằm CẠNH NHAU, nhóm xuất hiện trước trong file thì đứng trước.

    Kết quả (dict, đã sẵn sàng jsonify):
      rows          -- [header, ...dòng] tối đa `limit` dòng dữ liệu; cột ĐẦU là
                       "Kết quả" ("Giữ"/"Xoá"), các cột sau là dữ liệu gốc.
      row_numbers   -- số thứ tự dòng GỐC (1-based, không tính dòng tiêu đề,
                       khớp số dòng ở bảng xem trước đầu vào) của từng dòng trong `rows`.
      row_status    -- "keep"/"remove" của từng dòng (FE dựa vào đây để tô màu).
      group_count / group_row_count / removed_row_count -- thống kê TOÀN BỘ file
                       (không bị cắt bởi `limit`); `shown_count` = số dòng thật sự trả về."""
    compare_df = _compare_frame(df, subset_columns, ignore_case, ignore_whitespace)
    removed = compare_df.duplicated(keep=keep.value).to_numpy()
    in_group = compare_df.duplicated(keep=False).to_numpy()

    # Vị trí (0-based) các dòng thuộc nhóm trùng. Dùng vị trí chứ không dùng
    # nhãn index để không phụ thuộc df có index liên tục hay không.
    positions = in_group.nonzero()[0]
    header = ["Kết quả"] + [str(c) for c in df.columns]
    if len(positions) == 0:
        return {
            "rows": [header], "row_numbers": [], "row_status": [],
            "group_count": 0, "group_row_count": 0, "removed_row_count": 0, "shown_count": 0,
        }

    # Đánh số nhóm theo thứ tự xuất hiện đầu tiên (sort=False), rồi xếp ổn định
    # theo nhóm -- trong cùng nhóm vẫn giữ thứ tự gốc trong file.
    group_ids = compare_df.iloc[positions].groupby(list(compare_df.columns), sort=False).ngroup().to_numpy()
    order = group_ids.argsort(kind="stable")
    ordered_positions = positions[order]

    shown = ordered_positions[:limit]
    body = df.iloc[shown]
    rows = [header]
    statuses = []
    for pos, values in zip(shown, body.itertuples(index=False, name=None)):
        status = "remove" if removed[pos] else "keep"
        statuses.append(status)
        rows.append(["Xoá" if status == "remove" else "Giữ"] + ["" if v is None else str(v) for v in values])
    return {
        "rows": rows,
        "row_numbers": [int(pos) + 1 for pos in shown],
        "row_status": statuses,
        "group_count": int(group_ids.max()) + 1,
        "group_row_count": int(len(positions)),
        "removed_row_count": int(removed.sum()),
        "shown_count": int(len(shown)),
    }


def quick_trim_whitespace(
    df: pd.DataFrame, collapse_repeated: bool = False, remove_zero_width: bool = True
) -> tuple[pd.DataFrame, dict]:
    """Cắt khoảng trắng thừa trên MỌI Ô của bảng -- không cần chọn cột, vì
    đây vốn là hành động "an toàn" áp dụng sẵn cho tất cả các cột. 2 tham số
    MỚI khớp đúng 2 checkbox của tool tham khảo -- xem `_clean_whitespace_advanced()`."""
    result = df.copy()
    cells_changed = 0
    for col in result.columns:
        cleaned = result[col].apply(
            lambda v: _clean_whitespace_advanced(v, collapse_repeated, remove_zero_width)
        )
        cells_changed += int((cleaned != result[col]).sum())
        result[col] = cleaned
    return result, _stats(df, result, cells_changed)


def quick_fill_or_remove_blanks(
    df: pd.DataFrame, column: str, action: str, fixed_value: Optional[str] = None
) -> tuple[pd.DataFrame, dict]:
    """Điền/xoá ô trống Ở ĐÚNG 1 CỘT người dùng tự gõ tên -- `action`:
    "fill_down" (điền theo giá trị Ở DÒNG GẦN NHẤT PHÍA TRÊN, không có thì
    giữ nguyên trống -- khớp "Fill with value above" của tool tham khảo,
    **MỚI**), "fixed_value" (điền 1 giá trị cố định tự gõ), hoặc "remove_row"
    (xoá cả dòng -- SPARK giữ thêm lựa chọn này so với tool tham khảo, vì
    đây vốn đã là hành động có sẵn/đã test kỹ, không có lý do gì bỏ đi)."""
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

    if action == "fill_down":
        result = df.copy()
        # Đổi ô trống thành None rồi forward-fill (ffill): mỗi None được thay
        # bằng giá trị KHÔNG-None GẦN NHẤT phía TRÊN nó. Dòng trống mà phía
        # trên cũng toàn trống (hoặc là dòng đầu tiên) thì GIỮ NGUYÊN trống
        # -- không có gì "ở trên" để điền vào, đúng hành vi tool tham khảo.
        as_none = result[column].where(~is_blank, None)
        filled = as_none.ffill()
        still_blank = filled.isna()
        filled = filled.where(~still_blank, result[column])
        cells_changed = int((is_blank & ~still_blank).sum())
        result[column] = filled
        return result, _stats(df, result, cells_changed=cells_changed)

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


def is_column_fully_empty(series: pd.Series) -> bool:
    """Cột mà MỌI dòng đều "thiếu" -- dùng cho tuỳ chọn "Xoá luôn cột trống
    hoàn toàn" (MỚI, khớp "Also remove empty columns" của tool tham khảo)."""
    if series.empty:
        return False
    return bool(series.apply(_is_missing_text).all())


def quick_remove_empty_rows(
    df: pd.DataFrame, also_remove_empty_columns: bool = False
) -> tuple[pd.DataFrame, dict]:
    mask = is_row_fully_empty(df)
    result = df[~mask].reset_index(drop=True)
    columns_removed = 0
    if also_remove_empty_columns:
        empty_cols = [c for c in result.columns if is_column_fully_empty(result[c])]
        if empty_cols:
            result = result.drop(columns=empty_cols)
            columns_removed = len(empty_cols)
    stats = _stats(df, result)
    stats["columns_removed"] = columns_removed
    return result, stats
