"""
Module GIẢM SỐ CỘT (feature selection) cho Class Noise.

Còn lại trong module này (sau khi gỡ "Random Forest + điểm gãy" ngày 24/11/2026 -- bước giảm cột theo
NHÃN nay do BORUTA làm, xem class_noise/boruta.py và class_noise/preprocess.py):
  - filter_correlated(): loại bớt cột THỪA THÔNG TIN LẪN NHAU (tương quan cao giữa CỘT VỚI CỘT,
    không liên quan gì tới nhãn); `order_columns_without_labels()` là luật xếp thứ tự giữ cột
    KHÔNG nhìn nhãn mà `filter_correlated(prioritized=False)` dùng.
  - cap_outliers(): cap outlier về biên IQR/Z-score (TÁI DÙNG detect_outlier() + công thức biên/định
    dạng số đã có ở attribute_noise/, không viết lại công thức IQR/Z-score lần 2).
  - log_transform(): biến đổi logarit để phân phối đỡ "lệch đuôi dài", cân đối hơn.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from attribute_noise.attribute_handling import _format_numeric_for_column, _resolve_cap_bounds
from attribute_noise.config import ColumnDType, ColumnNoiseConfig, NoiseType
from attribute_noise.detectors import detect_outlier


@dataclass
class FeatureRanking:
    """Một dòng của bảng xếp hạng cột theo mức quan trọng (cột + mức quan trọng).

    Hàm xếp hạng cũ (`rank_by_importance`, `select_by_elbow`) đã bị gỡ ngày 24/11/2026 (thay bằng Boruta);
    chỉ còn giữ kiểu dữ liệu này (không được web gọi)."""

    column: str
    importance: float


def order_columns_without_labels(
    df: pd.DataFrame, columns: list[str], method: str = "pearson"
) -> list[str]:
    """Xếp thứ tự ưu tiên giữ cột mà KHÔNG nhìn cột nhãn (nên không bị nhãn bẩn làm lệch).

    Luật (theo đúng thứ tự so sánh): (1) ít ô trống hơn -> đứng trước, vì cột đủ dữ liệu
    đáng tin hơn; (2) tương quan trung bình với các cột khác THẤP hơn -> đứng trước, vì
    cột "độc lập" mang nhiều thông tin riêng hơn; (3) hoà thì giữ nguyên thứ tự ban đầu.
    """
    numeric = df[columns].apply(pd.to_numeric, errors="coerce")
    blanks = numeric.isna().sum()
    corr = numeric.corr(method=method).abs().fillna(0.0).to_numpy(copy=True)
    np.fill_diagonal(corr, 0.0)  # bỏ tương quan của cột với chính nó
    mean_other = corr.sum(axis=1) / max(1, len(columns) - 1)
    position = {c: i for i, c in enumerate(columns)}
    return sorted(
        columns,
        key=lambda c: (int(blanks[c]), float(mean_other[position[c]]), position[c]),
    )


def filter_correlated(
    df: pd.DataFrame,
    columns: list[str],
    threshold: float = 0.8,
    prioritized: bool = True,
    method: str = "pearson",
    return_report: bool = False,
):
    """Loại cột THỪA THÔNG TIN LẪN NHAU (tương quan cao giữa CỘT VỚI CỘT, không liên quan
    gì tới nhãn) -- ngưỡng 0.8 là quy ước thống kê phổ biến (giống 1.5 của IQR, 3.0 của
    Z-score).

    Hai cách chọn cột nào được GIỮ trong mỗi cặp "thừa nhau":
      - prioritized=True (hành vi cũ, các nơi gọi cũ không phải đổi): `columns` ĐÃ được sắp
        theo độ ưu tiên giảm dần (thường lấy từ `rank_by_importance()` -- tức dựa vào NHÃN).
        Duyệt đúng thứ tự đó, cột nào tương quan >= threshold với 1 cột ĐÃ GIỮ thì bị loại.
      - prioritized=False (KHÔNG dùng nhãn): tự xếp thứ tự bằng `order_columns_without_labels()`
        (ít ô trống -> ít tương quan với cột khác). Nhờ vậy nhãn sai không ảnh hưởng gì tới
        cột được giữ. Danh sách trả về vẫn theo thứ tự ban đầu của `columns`.

    method: "pearson" (mặc định) hoặc "spearman" (bắt được quan hệ đồng biến không tuyến tính).
    return_report=True: trả thêm danh sách cột bị loại, mỗi phần tử có dạng
    {"column", "kept_column", "correlation"} -- loại vì trùng thông tin với cột nào, |r| bao nhiêu.
    """
    working = df[columns].apply(pd.to_numeric, errors="coerce")
    order = columns if prioritized else order_columns_without_labels(working, columns, method)
    corr_matrix = working.corr(method=method).abs()

    kept: list[str] = []
    dropped: list[dict] = []
    for col in order:
        # các cột đã giữ mà cột này quá giống (NaN so sánh luôn False nên cột hằng không bị loại ở đây)
        similar = [(float(corr_matrix.loc[col, k]), k) for k in kept if corr_matrix.loc[col, k] >= threshold]
        if similar:
            r, kept_col = max(similar)
            dropped.append({"column": col, "kept_column": kept_col, "correlation": r})
        else:
            kept.append(col)

    if not prioritized:
        keep_set = set(kept)
        kept = [c for c in columns if c in keep_set]  # trả lại theo thứ tự ban đầu cho dễ đọc
    return (kept, dropped) if return_report else kept


def cap_outliers(
    df: pd.DataFrame,
    columns: list[str],
    outlier_method: str = "iqr",
    outlier_threshold: float = 1.5,
) -> pd.DataFrame:
    """Bước 3a: xử lý outlier trên các cột CUỐI CÙNG (sau Bước 1+2) bằng cách
    CAP VỀ BIÊN (Winsorizing) -- giá trị vượt biên bị KÉO VỀ ĐÚNG BIÊN, KHÔNG
    xoá dòng nào. Chọn cap thay vì remove_row vì giữ được TỐI ĐA dữ liệu cho
    Confident Learning học (đúng nguyên tắc đã rút ra nhiều lần: càng nhiều
    dữ liệu/đặc trưng tốt thì model càng học tốt).

    TÁI DÙNG NGUYÊN VẸN `detect_outlier()` (attribute_noise/detectors.py) để
    tìm ô outlier + `_resolve_cap_bounds()` / `_format_numeric_for_column()`
    (attribute_noise/attribute_handling.py) để tính biên và định dạng giá trị cap --
    đúng các hàm mà `apply_handling()` dùng cho hành động CAP_TO_RANGE.

    BỎ QUA cột có IQR/độ lệch chuẩn SUY BIẾN (= 0) -- LỖI THẬT đã gặp khi
    test: `capital.gain`/`capital.loss` của Adult Income có Q1=Q3=0 (đa số
    giá trị = 0, "zero-inflated"), nên biên cap = [0, 0], khiến MỌI giá trị
    khác 0 (chính là tín hiệu quan trọng nhất của 2 cột này) bị ép về 0 --
    xoá sạch 2.712/1.519 giá trị có ý nghĩa thật, làm CV accuracy tụt xuống
    DƯỚI CẢ baseline. Cột nào rơi vào trường hợp này thì GIỮ NGUYÊN, không
    cap gì cả -- an toàn hơn cap sai.

    TỐC ĐỘ (CLAUDE.md mục 38): bản đầu gọi `apply_handling()` rồi lặp `.loc[từng_dòng]`
    cho mọi ô outlier -- trên Credit Card (284k dòng, hàng chục nghìn ô outlier mỗi cột)
    mất 20-85 giây MỖI CỘT, hơn 20 phút cho 30 cột mỗi lần bấm Phát hiện. Giờ cap cả
    cột bằng 1 phép gán vector hoá (6 giây cho 30 cột); kết quả đã đối chiếu từng ô
    với bản cũ (xem CLAUDE.md mục 38).
    """
    result = df.copy()
    for col in columns:
        numeric = pd.to_numeric(result[col], errors="coerce")
        valid = numeric.dropna()
        spread = valid.std() if outlier_method == "zscore" else valid.quantile(0.75) - valid.quantile(0.25)
        if spread == 0:
            continue  # IQR/std suy biến -> không cap được an toàn, bỏ qua cột này

        cfg = ColumnNoiseConfig(
            column=col,
            dtype=ColumnDType.FLOAT,
            noise_types=[NoiseType.OUTLIER],
            outlier_method=outlier_method,
            outlier_threshold=outlier_threshold,
        )
        is_outlier = detect_outlier(result[col], cfg)
        if not is_outlier.any():
            continue  # cột này không có outlier

        lower, upper = _resolve_cap_bounds(result, col, NoiseType.OUTLIER, cfg)
        capped = numeric.clip(lower=lower, upper=upper)[is_outlier]
        capped = capped[capped.notna()]  # ô không ép được thành số thì không đụng tới
        # Ghi CẢ CỘT một lần (cùng cách định dạng chuỗi như apply_handling: làm tròn 2 chữ số).
        result.loc[capped.index, col] = [_format_numeric_for_column(v, cfg) for v in capped.to_numpy()]
    return result


def log_transform(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Bước 3b: biến đổi logarit các cột SỐ cuối cùng -- làm phân phối đỡ
    "lệch đuôi dài" hơn, cân đối hơn (giống hình chuông), theo đúng công thức
    chuẩn hay dùng trong thực tế: `log(x + 1)` (cộng 1 để xử lý trường hợp
    x = 0, vì log(0) không xác định) -- đã kiểm chứng đây là kỹ thuật tiền xử
    lý phổ biến thật, kể cả áp dụng trực tiếp lên cột Amount của chính bộ
    Credit Card Fraud đang dùng để thử nghiệm (xem lịch sử trò chuyện).

    CHỈ áp dụng được cho cột KHÔNG có giá trị ÂM (log của số âm không xác
    định) -- cột nào có giá trị âm thì GIỮ NGUYÊN, không biến đổi (vd cột
    "chênh lệch"/nhiệt độ có thể âm, khác cột tiền bạc/số lượng luôn >= 0).

    Nên chạy SAU `cap_outliers()` -- biến đổi logarit chỉ nên chỉnh HÌNH DẠNG
    phân phối của dữ liệu ĐÃ ĐÚNG, không phải "nguỵ trang" cho outlier do lỗi
    nhập liệu còn sót lại.
    """
    result = df.copy()
    for col in columns:
        numeric = pd.to_numeric(result[col], errors="coerce")
        if (numeric < 0).any():
            continue  # có giá trị âm -> log không xác định, giữ nguyên cột này

        # log1p(x) = log(x+1), chính xác hơn log(x+1) thường với x nhỏ (tránh
        # mất độ chính xác do dấu phẩy động khi x gần 0). Gán VECTOR HOÁ (1
        # phép gán cho cả cột cùng lúc qua mask `valid`) thay vì lặp từng dòng
        # bằng Python -- với file lớn (vd Credit Card Fraud 284k dòng), lặp
        # từng dòng qua .loc CHẬM RÕ RỆT (từng bị phát hiện treo máy khi test
        # thật), vector hoá nhanh hơn rất nhiều lần.
        transformed = np.log1p(numeric)
        valid = transformed.notna()
        result.loc[valid, col] = transformed[valid].round(4).astype(str)
    return result
