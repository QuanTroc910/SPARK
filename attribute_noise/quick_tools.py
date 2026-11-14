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
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from .attribute_handling import (
    DuplicateKeep, HandlingAction, HandlingChoice, _is_missing_text, apply_handling,
)
from .config import DEFAULT_MISSING_PLACEHOLDERS, ColumnDType, ColumnNoiseConfig, NoiseType
from .detectors import INTEGER_RE, detect_format_noise
from .pipeline import NoiseFinding, guess_column_dtype, guess_date_format


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


# Đổi ký tự khoảng trắng "nhìn không thấy" thành ký hiệu hiện được, CHỈ để hiển thị danh sách ô đã
# sửa (xem `preview_trim_changes`) -- nếu không, giá trị trước/sau khi cắt trông y hệt nhau.
_VISIBLE_WHITESPACE = {
    ord(" "): "\u2423",       # ␣ dấu cách
    ord("\t"): "\u21e5",      # ⇥ tab
    ord("\n"): "\u23ce",      # ⏎ xuống dòng
    ord("\r"): "\u240d",      # ␍ về đầu dòng
    0x00A0: "\u237d",        # ⍽ non-breaking space
}


def _visible_whitespace(value) -> str:
    text = _ZERO_WIDTH_PATTERN.sub("\u27e8ZW\u27e9", str(value))  # ⟨ZW⟩ ký tự vô hình
    return text.translate(_VISIBLE_WHITESPACE)


def preview_trim_changes(
    df: pd.DataFrame, collapse_repeated: bool = False, remove_zero_width: bool = True, limit: int = 100
) -> dict:
    """MỚI -- dữ liệu cho nút "Xem các ô đã sửa" của tool Cắt khoảng trắng thừa.

    Dùng đúng `_clean_whitespace_advanced()` với đúng 2 tuỳ chọn như `quick_trim_whitespace()`
    nên tập ô bị đánh dấu "đã sửa" KHỚP ĐÚNG tập ô thật sự bị đổi (test có kiểm chứng:
    `changed_cell_count` == `stats.cells_changed`).

    Trả về các DÒNG có ít nhất 1 ô bị sửa, theo thứ tự trong file. Ô đã sửa hiện giá trị TRƯỚC khi
    sửa, khoảng trắng đổi thành ký hiệu hiện được (xem `_VISIBLE_WHITESPACE`); ô không đổi giữ nguyên.

    Kết quả (dict, sẵn sàng jsonify):
      rows            -- [header, ...dòng] tối đa `limit` dòng dữ liệu.
      row_numbers     -- số thứ tự dòng GỐC (1-based, không tính dòng tiêu đề) của từng dòng trong `rows`.
      cell_changed    -- cùng hình dạng với phần dữ liệu của `rows`: True = ô đó đã bị sửa.
      changed_cell_count / changed_row_count -- thống kê TOÀN BỘ file (không bị cắt bởi `limit`);
                         `shown_count` = số dòng thật sự trả về."""
    changed = pd.DataFrame(index=df.index)
    for col in df.columns:
        cleaned = df[col].apply(lambda v: _clean_whitespace_advanced(v, collapse_repeated, remove_zero_width))
        changed[col] = (cleaned != df[col]).to_numpy()
    mask = changed.to_numpy()
    row_has_change = mask.any(axis=1) if mask.size else mask.any(axis=0)
    positions = row_has_change.nonzero()[0]
    header = [str(c) for c in df.columns]
    shown = positions[:limit]
    rows = [header]
    cell_changed = []
    for pos in shown:
        values = df.iloc[pos].tolist()
        flags = mask[pos].tolist()
        rows.append([_visible_whitespace(v) if f else ("" if v is None else str(v)) for v, f in zip(values, flags)])
        cell_changed.append([bool(f) for f in flags])
    return {
        "rows": rows,
        "row_numbers": [int(pos) + 1 for pos in shown],
        "cell_changed": cell_changed,
        "changed_cell_count": int(mask.sum()),
        "changed_row_count": int(len(positions)),
        "shown_count": int(len(shown)),
    }


# ---------------------------------------------------------------------------
# Tool "Sai định dạng" (nhóm Tự động) -- quét MỌI cột cùng lúc, mỗi cột theo kiểu dữ liệu của nó (tự
# đoán, người dùng sửa được ở giao diện). Lõi dùng lại NGUYÊN `detect_format_noise()` của luồng Attribute
# Noise đầy đủ, nên "thế nào là sai định dạng" giống hệt Workspace cũ (email cần @, SĐT chỉ chữ số và vài
# ký tự +-(), ngày đúng khuôn, số nguyên/số thực parse được; ô trống/thiếu KHÔNG bị tính là sai -- đã có
# tool Điền/Xoá ô trống lo).
# ---------------------------------------------------------------------------

# 5 kiểu có "khuôn" để kiểm tra; category/text không có khuôn nên không bao giờ bị gắn cờ.
FORMAT_CHECKED_DTYPES = (
    ColumnDType.INTEGER, ColumnDType.FLOAT, ColumnDType.EMAIL, ColumnDType.PHONE, ColumnDType.DATE,
)
FORMAT_ACTIONS = ("report", "clear_cell", "remove_row")


def auto_column_types(df: pd.DataFrame) -> dict:
    """Kiểu từng cột do thuật toán tự đoán (cùng hàm giao diện dùng để điền sẵn) -- dùng khi request
    không gửi `column_types`, để tool vẫn chạy được "một phát" không cần khai gì."""
    types = {}
    for col in df.columns:
        dtype = guess_column_dtype(df[col])
        spec = {"dtype": dtype}
        if dtype == ColumnDType.DATE.value:
            spec["date_format"] = guess_date_format(df[col]) or "%Y-%m-%d"
        types[str(col)] = spec
    return types


def find_format_errors(df: pd.DataFrame, column_types: dict) -> pd.DataFrame:
    """Bảng True/False cùng hình dạng với `df`: True = ô sai định dạng so với kiểu cột đã chọn.
    `column_types` = {tên cột: {"dtype": "email"|"phone"|"date"|"integer"|"float"|"category"|"text",
    "date_format": "%Y-%m-%d" (chỉ cần với kiểu date)}}. Cột không có trong `column_types` hoặc có kiểu
    không kiểm tra (category/text) thì cả cột là False."""
    mask = pd.DataFrame(False, index=df.index, columns=df.columns)
    for col, spec in column_types.items():
        if col not in df.columns:
            raise QuickToolError(f"Cột không tồn tại: {col}")
        spec = spec or {}
        try:
            dtype = ColumnDType(spec.get("dtype"))
        except ValueError:
            raise QuickToolError(f"Kiểu dữ liệu không hợp lệ ở cột '{col}': {spec.get('dtype')}")
        if dtype not in FORMAT_CHECKED_DTYPES:
            continue
        date_format = (spec.get("date_format") or "").strip() or None
        if dtype == ColumnDType.DATE and date_format and "%" not in date_format:
            raise QuickToolError(f"Khuôn ngày ở cột '{col}' phải dạng %Y-%m-%d (có dấu %), nhận được: {date_format}")
        cfg = ColumnNoiseConfig(column=col, dtype=dtype, noise_types=[NoiseType.FORMAT_NOISE], date_format=date_format)
        mask[col] = detect_format_noise(df[col], cfg).to_numpy()
    return mask


def quick_fix_format_noise(df: pd.DataFrame, mask: pd.DataFrame, action: str) -> tuple[pd.DataFrame, dict]:
    """Áp 1 trong 3 cách lên các ô bị gắn cờ (`mask` từ `find_format_errors`):
      "report"     -- chỉ báo, KHÔNG sửa gì (mặc định an toàn);
      "clear_cell" -- đổi ô sai thành ô trống (rồi có thể điền lại bằng tool Điền/xoá ô trống);
      "remove_row" -- xoá cả dòng có ít nhất 1 ô sai.
    stats ngoài 4 field chung còn có `flagged_cell_count`/`flagged_row_count` (số ô/dòng sai, tính trên
    dữ liệu ĐẦU VÀO, không phụ thuộc cách xử lý)."""
    if action not in FORMAT_ACTIONS:
        raise QuickToolError(f"action không hợp lệ: {action}")
    row_flagged = mask.any(axis=1)
    flagged_cells = int(mask.to_numpy().sum())
    if action == "remove_row":
        result = df[~row_flagged].reset_index(drop=True)
        stats = _stats(df, result)
    elif action == "clear_cell":
        result = df.mask(mask, "")
        stats = _stats(df, result, cells_changed=flagged_cells)
    else:
        result = df
        stats = _stats(df, result)
    stats["flagged_cell_count"] = flagged_cells
    stats["flagged_row_count"] = int(row_flagged.sum())
    return result, stats


def preview_format_errors(df: pd.DataFrame, mask: pd.DataFrame, limit: int = 100) -> dict:
    """Dữ liệu cho nút "Xem các ô sai định dạng": các DÒNG có ít nhất 1 ô sai (theo thứ tự trong file,
    tối đa `limit` dòng), giá trị GỐC giữ nguyên, kèm cờ từng ô.
      rows / row_numbers   -- như `preview_trim_changes` (header + dòng; số dòng gốc 1-based);
      cell_flagged         -- True = ô đó sai định dạng (cùng hình dạng với phần dữ liệu của `rows`);
      flagged_cell_count / flagged_row_count -- thống kê TOÀN BỘ file (không bị cắt bởi `limit`);
      column_error_counts  -- {tên cột: số ô sai} chỉ gồm cột có lỗi (giao diện hiện cạnh bảng kiểu cột)."""
    row_flagged = mask.any(axis=1).to_numpy()
    positions = row_flagged.nonzero()[0]
    shown = positions[:limit]
    flags = mask.to_numpy()
    rows = [[str(c) for c in df.columns]]
    cell_flagged = []
    for pos in shown:
        rows.append(["" if v is None else str(v) for v in df.iloc[pos].tolist()])
        cell_flagged.append([bool(f) for f in flags[pos].tolist()])
    return {
        "rows": rows,
        "row_numbers": [int(pos) + 1 for pos in shown],
        "cell_flagged": cell_flagged,
        "flagged_cell_count": int(flags.sum()),
        "flagged_row_count": int(len(positions)),
        "shown_count": int(len(shown)),
        "column_error_counts": {str(c): int(mask[c].sum()) for c in mask.columns if mask[c].any()},
    }


def _fill_down_series(series: pd.Series, is_blank: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Điền ô trống bằng giá trị KHÁC TRỐNG GẦN NHẤT phía TRÊN nó. Đổi ô trống thành None rồi forward-fill (ffill). Ô trống mà
    phía trên cũng toàn trống (hoặc là dòng đầu tiên) thì GIỮ NGUYÊN -- không có gì "ở trên" để điền, đúng hành vi tool tham khảo.
    Trả về (cột sau khi điền, mask ô vẫn trống)."""
    as_none = series.where(~is_blank, None)
    filled = as_none.ffill()
    still_blank = filled.isna()
    return filled.where(~still_blank, series), still_blank


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
        filled, still_blank = _fill_down_series(result[column], is_blank)
        cells_changed = int((is_blank & ~still_blank).sum())
        result[column] = filled
        return result, _stats(df, result, cells_changed=cells_changed)

    raise QuickToolError(f"action không hợp lệ: {action}")


# Tập giá trị "thiếu" đã chuẩn hoá (chữ thường) -- ĐÚNG tập `_is_missing_text` dùng, viết lại dạng frozenset để kiểm tra
# cả cột một lượt bằng thao tác chuỗi vector hoá của pandas (nhanh hơn nhiều so với gọi hàm cho từng ô trên file lớn).
_MISSING_NORMALIZED = frozenset(p.lower() for p in DEFAULT_MISSING_PLACEHOLDERS)


def _blank_series(series: pd.Series) -> pd.Series:
    """True = ô "thiếu" (trống, "NA", "null", "none", "?", "-", "--", không phân biệt hoa/thường, đã cắt khoảng trắng
    đầu/cuối). KẾT QUẢ GIỐNG HỆT `_is_missing_text` áp cho từng ô (test có kiểm chứng), chỉ khác là chạy vector hoá."""
    return series.astype(str).str.strip().str.lower().isin(_MISSING_NORMALIZED)


def blank_mask(df: pd.DataFrame) -> pd.DataFrame:
    """Bảng True/False cùng hình dạng với `df`: True = ô thiếu."""
    if df.shape[0] == 0 or df.shape[1] == 0:
        return pd.DataFrame(False, index=df.index, columns=df.columns)
    return df.apply(_blank_series)


def is_row_fully_empty(df: pd.DataFrame) -> pd.Series:
    """Dòng mà MỌI cột đều "thiếu" (theo đúng định nghĩa `_is_missing_text`
    dùng chung toàn hệ thống) -- KHÁC `missing_value` (xét từng Ô riêng lẻ):
    ở đây xét CẢ DÒNG, tương đương "Remove empty rows" của tool tham khảo,
    loại noise cấp dòng mà luồng Attribute Noise đầy đủ CHƯA có detector
    riêng (chỉ mới có `duplicate_row` ở cấp dòng)."""
    if df.empty:
        return pd.Series(dtype=bool)
    return blank_mask(df).all(axis=1)


def is_column_fully_empty(series: pd.Series) -> bool:
    """Cột mà MỌI dòng đều "thiếu" -- dùng cho tuỳ chọn "Xoá luôn cột trống
    hoàn toàn" (MỚI, khớp "Also remove empty columns" của tool tham khảo)."""
    if series.empty:
        return False
    return bool(_blank_series(series).all())


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


# ---------------------------------------------------------------------------
# Tool "Ô trống" (nhóm Tự động) -- GỘP 3 tool cũ: Xoá dòng trống + Điền/xoá ô trống + Thiếu giá trị (nâng cao).
# Cùng 1 định nghĩa "ô trống" (`_blank_series`) cho cả 3 việc. Làm theo thứ tự:
#   1. xoá DÒNG TRỐNG HOÀN TOÀN (mọi cột đều trống) -- tuỳ chọn, mặc định bật;
#   2. xoá CỘT TRỐNG HOÀN TOÀN (xét trên các dòng còn lại) -- tuỳ chọn, mặc định tắt;
#   3. với các cột chọn "Xoá dòng": xoá mọi dòng có ô trống ở cột đó (hợp nhất: dòng nào bị 1 cột đòi xoá thì xoá);
#   4. với các cột còn lại: điền ô trống theo cách đã chọn (điền từ ô phía trên / giá trị cố định / trung bình / trung vị /
#      KNN / giá trị phổ biến nhất) -- XOÁ DÒNG LÀM TRƯỚC KHI ĐIỀN để dòng sắp bị xoá không làm lệch trung bình/trung vị.
# Cách điền số/nhóm dùng lại NGUYÊN `apply_handling()` của luồng Attribute Noise đầy đủ (cùng công thức impute, cùng cách
# làm tròn theo kiểu cột), nên kết quả giống hệt tool "Thiếu giá trị (nâng cao)" cũ.
# ---------------------------------------------------------------------------

# Cách xử lý hợp lệ theo kiểu cột (giao diện lấy danh sách này từ /api/noise-tools/inspect, không tự định nghĩa lại).
_NUMERIC_BLANK_ACTIONS = ["keep", "fill_down", "fixed_value", "impute_mean", "impute_median", "impute_knn", "remove_row"]
_CATEGORY_BLANK_ACTIONS = ["keep", "fill_down", "fixed_value", "impute_mode", "remove_row"]
# Email/SĐT/ngày/văn bản: không đoán được giá trị thay thế (không thể "trung bình" của email) nên KHÔNG có impute.
_PLAIN_BLANK_ACTIONS = ["keep", "fill_down", "fixed_value", "remove_row"]
BLANK_ACTIONS_BY_DTYPE = {
    "integer": _NUMERIC_BLANK_ACTIONS,
    "float": _NUMERIC_BLANK_ACTIONS,
    "category": _CATEGORY_BLANK_ACTIONS,
    "text": _PLAIN_BLANK_ACTIONS,
    "email": _PLAIN_BLANK_ACTIONS,
    "phone": _PLAIN_BLANK_ACTIONS,
    "date": _PLAIN_BLANK_ACTIONS,
}
# Các action đi qua apply_handling (KNN xếp cuối vì nó dùng giá trị các cột khác để tính khoảng cách).
_BLANK_IMPUTE_ACTIONS = {
    "fixed_value": HandlingAction.FIXED_VALUE,
    "impute_mean": HandlingAction.IMPUTE_MEAN,
    "impute_median": HandlingAction.IMPUTE_MEDIAN,
    "impute_mode": HandlingAction.IMPUTE_MODE,
    "impute_knn": HandlingAction.IMPUTE_KNN,
}


def blank_column_summary(df: pd.DataFrame) -> dict:
    """Dữ liệu cho bảng "Ô trống từng cột" (route inspect, khi giao diện hỏi): số ô trống mỗi cột, số dòng trống hoàn
    toàn, danh sách cột trống hoàn toàn, và cách xử lý hợp lệ theo từng kiểu cột."""
    mask = blank_mask(df)
    has_data = len(df) > 0 and len(df.columns) > 0
    return {
        "blank_counts": {str(c): int(mask[c].sum()) for c in mask.columns},
        "empty_row_count": int(mask.all(axis=1).sum()) if has_data else 0,
        "empty_columns": [str(c) for c in mask.columns if len(df) > 0 and bool(mask[c].all())],
        "blank_actions": BLANK_ACTIONS_BY_DTYPE,
    }


@dataclass
class BlankOutcome:
    """Kết quả chi tiết của `quick_handle_blanks`, đủ để `preview_blank_changes` dựng danh sách "Xem các ô trống đã xử lý".
    Mọi vị trí dòng là vị trí GỐC (0-based) trong dữ liệu đầu vào."""

    removed_positions: set        # dòng đã bị xoá (trống hoàn toàn + dòng bị cột nào đó đòi xoá)
    fully_empty_count: int        # trong số đó: số dòng trống hoàn toàn
    handled: dict                 # {cột: (Index vị trí dòng có ô trống được xử lý, Series giá trị mới cùng Index)}
    columns_removed: list         # tên các cột trống hoàn toàn đã xoá
    filled_count: int = 0         # số ô trống đã được điền
    unfilled_count: int = 0       # số ô định điền nhưng vẫn trống (vd điền từ ô trên mà đó là dòng đầu, trung bình mà không có số nào)


def _check_value_for_dtype(label: str, dtype: ColumnDType, text: str) -> str:
    """Kiểm tra giá trị người dùng nhập có hợp kiểu cột không (số nguyên phải là số nguyên, số thực phải là số); cột số thì
    trả về chuỗi đã cắt khoảng trắng. `label` = mô tả giá trị để đưa vào câu báo lỗi."""
    if dtype == ColumnDType.INTEGER and not INTEGER_RE.match(text.strip()):
        raise QuickToolError(f"{label} (kiểu số nguyên) phải là số nguyên, nhận được: {text}")
    if dtype == ColumnDType.FLOAT:
        try:
            float(text.strip())
        except ValueError:
            raise QuickToolError(f"{label} (kiểu số thực) phải là số, nhận được: {text}")
    if dtype in (ColumnDType.INTEGER, ColumnDType.FLOAT):
        return text.strip()
    return text


def _validate_blank_actions(df: pd.DataFrame, column_actions: dict) -> dict:
    """Kiểm tra `column_actions` = {tên cột: {"dtype": ..., "action": ..., "fixed_value": ..., "cell_values": ...}}; trả về chỉ
    các cột có cách xử lý khác "keep", kiểu đã đổi thành ColumnDType. Thiếu "dtype" thì tự đoán từ giá trị cột.

    Cách "fixed_value" (giao diện gọi là "Điền tay từng ô") có 2 nguồn giá trị, dùng được riêng hoặc cùng lúc:
      - `cell_values` {số dòng GỐC 1-based: giá trị} -- giá trị RIÊNG cho từng ô trống (ô để chuỗi rỗng = bỏ qua, vẫn trống);
      - `fixed_value` -- giá trị CHUNG cho mọi ô trống của cột mà không có giá trị riêng.
    Phải có ít nhất 1 trong 2."""
    specs = {}
    for col, spec in column_actions.items():
        if col not in df.columns:
            raise QuickToolError(f"Cột không tồn tại: {col}")
        spec = spec or {}
        dtype_raw = spec.get("dtype") or guess_column_dtype(df[col])
        try:
            dtype = ColumnDType(dtype_raw)
        except ValueError:
            raise QuickToolError(f"Kiểu dữ liệu không hợp lệ ở cột '{col}': {dtype_raw}")
        action = spec.get("action") or "keep"
        allowed = BLANK_ACTIONS_BY_DTYPE[dtype.value]
        if action not in allowed:
            raise QuickToolError(
                f"Cách xử lý '{action}' không dùng được cho cột '{col}' (kiểu {dtype.value}); cách hợp lệ: {', '.join(allowed)}"
            )
        if action == "keep":
            continue
        fixed = None
        cell_values: dict = {}     # {vị trí dòng 0-based: giá trị}
        if action == "fixed_value":
            raw_fixed = spec.get("fixed_value")
            if raw_fixed is not None and str(raw_fixed).strip() != "":
                fixed = _check_value_for_dtype(f"Giá trị cố định của cột '{col}'", dtype, str(raw_fixed))
            raw_cells = spec.get("cell_values") or {}
            if not isinstance(raw_cells, dict):
                raise QuickToolError(f"cell_values của cột '{col}' phải là object {{số dòng: giá trị}}")
            for key, value in raw_cells.items():
                try:
                    row_number = int(key)
                except (TypeError, ValueError):
                    raise QuickToolError(f"Số dòng không hợp lệ ở cột '{col}': {key}")
                if not 1 <= row_number <= len(df):
                    raise QuickToolError(f"Dòng {row_number} không tồn tại (file có {len(df)} dòng), cột '{col}'")
                text = "" if value is None else str(value)
                if text.strip() == "":
                    continue                       # để trống = không điền ô này
                cell_values[row_number - 1] = _check_value_for_dtype(f"Giá trị ở dòng {row_number} của cột '{col}'", dtype, text)
            if fixed is None and not cell_values:
                raise QuickToolError(f"Thiếu giá trị cố định để điền vào cột '{col}' (nhập giá trị chung hoặc điền tay từng ô)")
        specs[col] = {"dtype": dtype, "action": action, "fixed_value": fixed, "cell_values": cell_values}
    return specs


def blank_rows_for_column(df: pd.DataFrame, column: str, limit: int = 100) -> dict:
    """Dữ liệu cho bảng "Điền tay từng ô": các DÒNG (đủ mọi cột) có ô trống ở cột `column`, theo thứ tự trong file, tối đa
    `limit` dòng. Dòng trống hoàn toàn KHÔNG liệt kê (tool Ô trống mặc định xoá chúng; điền 1 ô vào dòng toàn trống không có
    nghĩa) -- số dòng đó trả riêng ở `excluded_empty_rows`. `row_numbers` là số dòng GỐC (1-based), chính là khoá của
    `cell_values` khi gửi lên `quick_handle_blanks`. `total_blank_rows` đếm TOÀN BỘ, không bị cắt bởi `limit`."""
    if column not in df.columns:
        raise QuickToolError(f"Cột không tồn tại: {column}")
    work = df.reset_index(drop=True)
    mask = blank_mask(work)
    fully_empty = mask.all(axis=1) if len(work) and len(work.columns) else pd.Series(False, index=work.index)
    selected = work.index[mask[column] & ~fully_empty]
    shown = selected[:limit]
    columns = [str(c) for c in work.columns]
    rows = [["" if v is None else str(v) for v in work.iloc[int(pos)].tolist()] for pos in shown]
    return {
        "column": str(column),
        "column_index": columns.index(str(column)),
        "columns": columns,
        "rows": rows,
        "row_numbers": [int(pos) + 1 for pos in shown],
        "total_blank_rows": int(len(selected)),
        "shown_count": int(len(shown)),
        "excluded_empty_rows": int((mask[column] & fully_empty).sum()),
    }


def quick_handle_blanks(
    df: pd.DataFrame,
    column_actions: Optional[dict] = None,
    remove_empty_rows: bool = True,
    remove_empty_columns: bool = False,
) -> tuple[pd.DataFrame, dict, BlankOutcome]:
    """Xử lý ô trống theo đúng thứ tự mô tả ở đầu khối. `column_actions` rỗng/None = KHÔNG đụng cột nào (chỉ làm 2 tuỳ chọn
    xoá dòng/cột trống hoàn toàn) -- đúng tool "Xoá dòng trống" cũ. Trả về (df kết quả, stats, BlankOutcome).

    stats ngoài 4 field chung (original/removed/final_row_count, cells_changed) còn có: filled_cell_count (ô đã điền),
    unfilled_cell_count (ô định điền mà vẫn trống), empty_row_removed_count (dòng trống hoàn toàn đã xoá),
    action_row_removed_count (dòng xoá vì cột chọn "Xoá dòng"), columns_removed (số cột trống đã xoá)."""
    specs = _validate_blank_actions(df, column_actions or {})
    work = df.reset_index(drop=True)          # nhãn dòng = vị trí gốc; xoá dòng không đánh số lại nên nhãn giữ nguyên
    blank = blank_mask(work)
    has_data = len(work) > 0 and len(work.columns) > 0

    # 1. dòng trống hoàn toàn
    removed: set = set()
    fully_empty: set = set()
    if remove_empty_rows and has_data:
        fully_empty = set(work.index[blank.all(axis=1)])
        removed |= fully_empty

    # 2. cột trống hoàn toàn (xét trên các dòng còn lại, giống tool cũ)
    columns_removed: list = []
    if remove_empty_columns and has_data:
        remaining = work.index.difference(pd.Index(list(removed)))
        if len(remaining) > 0:
            sub = blank.loc[remaining]
            columns_removed = [c for c in work.columns if bool(sub[c].all())]

    # 3. cột chọn "Xoá dòng" (bỏ qua cột đã bị xoá ở bước 2 -- "xoá" thắng)
    action_removed: set = set()
    for col, spec in specs.items():
        if spec["action"] == "remove_row" and col not in columns_removed:
            action_removed |= set(work.index[blank[col]]) - removed
    removed |= action_removed

    keep_index = work.index.difference(pd.Index(list(removed)))
    result = work.loc[keep_index].drop(columns=columns_removed)
    blank_kept = blank.loc[keep_index, result.columns]

    # 4. điền ô trống từng cột. Điền từ ô phía trên trước (độc lập từng cột), rồi tới nhóm đi qua apply_handling.
    handled: dict = {}
    flagged_by_col = {}
    for col, spec in specs.items():
        if spec["action"] == "remove_row" or col in columns_removed:
            continue
        flagged = result.index[blank_kept[col]]
        if len(flagged) > 0:
            flagged_by_col[col] = flagged

    for col, spec in specs.items():
        if spec["action"] == "fill_down" and col in flagged_by_col:
            filled, _still = _fill_down_series(result[col], blank_kept[col])
            result[col] = filled

    # "Điền tay từng ô": giá trị RIÊNG của từng dòng ghi thẳng vào ô (chỉ ô đang trống và dòng còn giữ lại; dòng đã bị xoá thì
    # bỏ qua -- "xoá" thắng). Ô nào không có giá trị riêng thì rơi xuống nhánh giá trị chung (fixed_value) bên dưới.
    own_values_by_col: dict = {}
    for col, spec in specs.items():
        if spec["action"] == "fixed_value" and spec["cell_values"] and col in flagged_by_col:
            own = {int(pos): spec["cell_values"][int(pos)] for pos in flagged_by_col[col] if int(pos) in spec["cell_values"]}
            for pos, value in own.items():
                result.at[pos, col] = value
            own_values_by_col[col] = set(own)

    def _targets(col, spec):
        """Các ô trống của cột mà cách xử lý này còn phải điền (đã trừ ô được điền tay riêng)."""
        done = own_values_by_col.get(col, set())
        return [pos for pos in flagged_by_col[col] if int(pos) not in done]

    impute_specs = [
        (c, sp) for c, sp in specs.items()
        if sp["action"] in _BLANK_IMPUTE_ACTIONS and c in flagged_by_col
        and not (sp["action"] == "fixed_value" and (sp["fixed_value"] is None or not _targets(c, sp)))
    ]
    impute_specs.sort(key=lambda item: item[1]["action"] == "impute_knn")     # KNN xếp cuối
    if impute_specs:
        configs = [ColumnNoiseConfig(column=c, dtype=sp["dtype"], noise_types=[NoiseType.MISSING_VALUE]) for c, sp in impute_specs]
        findings = [
            NoiseFinding(row_index=int(pos), column=c, noise_type=NoiseType.MISSING_VALUE.value, value=result.at[pos, c])
            for c, sp in impute_specs for pos in _targets(c, sp)
        ]
        choices = [
            HandlingChoice(column=c, noise_type=NoiseType.MISSING_VALUE, action=_BLANK_IMPUTE_ACTIONS[sp["action"]], fixed_value=sp["fixed_value"])
            for c, sp in impute_specs
        ]
        result, _ = apply_handling(result, configs, findings, choices)

    filled_count = 0
    unfilled_count = 0
    for col, flagged in flagged_by_col.items():
        new_values = result.loc[flagged, col]
        still = _blank_series(new_values)
        filled_count += int((~still).sum())
        unfilled_count += int(still.sum())
        handled[col] = (flagged, new_values)

    final = result.reset_index(drop=True)
    stats = _stats(df, final, cells_changed=filled_count)
    stats.update({
        "filled_cell_count": filled_count,
        "unfilled_cell_count": unfilled_count,
        "empty_row_removed_count": len(fully_empty),
        "action_row_removed_count": len(action_removed),
        "columns_removed": len(columns_removed),
    })
    outcome = BlankOutcome(
        removed_positions=removed, fully_empty_count=len(fully_empty), handled=handled,
        columns_removed=[str(c) for c in columns_removed], filled_count=filled_count, unfilled_count=unfilled_count,
    )
    return final, stats, outcome


def preview_blank_changes(df: pd.DataFrame, outcome: BlankOutcome, limit: int = 100) -> dict:
    """Dữ liệu cho nút "Xem các ô trống đã xử lý": các DÒNG bị xoá hoặc có ô trống được xử lý, theo thứ tự trong file (tối đa
    `limit` dòng). Dòng bị xoá giữ giá trị gốc, đánh dấu "remove". Ô trống được xử lý hiện "trước → sau" (vd "(trống) → 35"
    hoặc "(trống) → (vẫn trống)" nếu không điền được) và được gắn cờ.
      rows / row_numbers / cell_flagged -- như `preview_format_errors`;  row_status -- "remove" | "fill";
      affected_row_count / removed_row_count / filled_cell_count / unfilled_cell_count -- thống kê TOÀN BỘ (không bị cắt bởi
      `limit`); removed_columns -- cột trống hoàn toàn đã xoá (vẫn hiện trong bảng vì đây là dữ liệu đầu vào)."""
    work = df.reset_index(drop=True)
    header = [str(c) for c in work.columns]
    flagged_positions: set = set()
    for flagged, _new in outcome.handled.values():
        flagged_positions.update(int(p) for p in flagged)
    positions = sorted(outcome.removed_positions | flagged_positions)
    shown = positions[:limit]
    shown_set = set(shown)
    new_by_cell = {}
    for col, (flagged, new_values) in outcome.handled.items():
        for pos in flagged:
            if int(pos) in shown_set:
                new_by_cell[(int(pos), str(col))] = new_values.at[pos]
    rows = [header]
    row_numbers, row_status, cell_flagged = [], [], []
    for pos in shown:
        values = ["" if v is None else str(v) for v in work.iloc[pos].tolist()]
        flags = [False] * len(values)
        is_removed = pos in outcome.removed_positions
        if not is_removed:
            for i, name in enumerate(header):
                if (pos, name) in new_by_cell:
                    before = values[i] if values[i].strip() else "(trống)"
                    after = new_by_cell[(pos, name)]
                    after_text = "(vẫn trống)" if _is_missing_text(after) else str(after)
                    values[i] = f"{before} → {after_text}"
                    flags[i] = True
        rows.append(values)
        row_numbers.append(int(pos) + 1)
        row_status.append("remove" if is_removed else "fill")
        cell_flagged.append(flags)
    return {
        "rows": rows,
        "row_numbers": row_numbers,
        "row_status": row_status,
        "cell_flagged": cell_flagged,
        "affected_row_count": len(positions),
        "removed_row_count": len(outcome.removed_positions),
        "filled_cell_count": outcome.filled_count,
        "unfilled_cell_count": outcome.unfilled_count,
        "removed_columns": outcome.columns_removed,
        "shown_count": len(shown),
    }
