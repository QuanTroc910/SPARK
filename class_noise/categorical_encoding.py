"""
Mã hoá cột CHỮ (category) thành cột SỐ để dùng làm đặc trưng (feature) cho
Class Noise -- 3 thuật toán hiện có (confident_learning.py/distance_based.py/
ensemble_based.py) đều CHỈ nhận đầu vào là số, nên cột chữ (vd workclass,
marital.status...) phải qua bước này TRƯỚC khi đưa vào detect.

Dùng ONE-HOT ENCODING kiểu "drop-first" (đã trao đổi + thống nhất với
người dùng), KHÔNG dùng Label/Target Encoding:
  - Label Encoding tự áp đặt 1 THỨ TỰ GIẢ giữa các giá trị (vd Sales=0,
    HR=1, IT=2 ngụ ý "HR nằm giữa Sales và IT" -- vô nghĩa với category
    không có thứ tự tự nhiên) -- hại các thuật toán dựa khoảng cách/đường
    biên tuyến tính (N13, N29).
  - Target Encoding (mã hoá theo trung bình NHÃN của từng giá trị) có RỦI
    RO RÒ RỈ chính thứ đang đi tìm: nếu nhãn ghi bị sai ở 1 nhóm nào đó,
    cách mã hoá này sẽ "nướng" luôn cái sai đó vào đặc trưng -- vòng lặp
    quẩn, không hợp bài toán PHÁT HIỆN nhãn sai.
  - One-Hot AN TOÀN vì không đụng gì tới nhãn, không áp đặt thứ tự giả.

"drop-first" (k giá trị -> chỉ tạo (k-1) cột, KHÔNG phải k cột): tránh
"dummy variable trap" -- nếu giữ đủ k cột, biết (k-1) cột là suy ra được
cột còn lại (mọi dòng chỉ có đúng 1 cột =1, các cột còn lại =0), tức là 1
cột luôn THỪA THÔNG TIN. Với cột chỉ 2 giá trị (vd sex), giữ đủ 2 cột one-
hot sẽ tương quan tuyệt đối -1.0 -- `filter_correlated()` (Bước 2
feature_selection.py) TỰ BẮT ĐƯỢC trường hợp này (tương quan CẶP 1-1), nhưng
với cột >=3 giá trị, sự dư thừa nằm ở TOÀN BỘ các cột CỘNG LẠI (tổng luôn
=1), không phải ở 1 CẶP cụ thể nào -- filter_correlated KHÔNG bắt được, nên
phải né ngay từ bước encode bằng drop-first, không trông chờ Bước 2 dọn hộ.

Đây là MODULE RIÊNG (không gộp vào feature_selection.py) vì là 1 mối quan
tâm khác: feature_selection.py xử lý DỮ LIỆU SỐ sẵn có (xếp hạng/lọc tương
quan/cap outlier/log), còn module này lo việc CHUYỂN cột chữ thành số
TRƯỚC KHI các bước đó chạy được.
"""

from dataclasses import dataclass

import pandas as pd

from .feature_selection import FeatureRanking

# Ngưỡng 1% -- gần với mặc định 5% của thư viện feature-engine
# (RareLabelEncoder), chọn chặt hơn 1 chút vì muốn giữ lại nhiều nhóm thật
# hơn (dữ liệu khoá luận không quá lớn, 5% có thể gộp mất vài nhóm còn ý
# nghĩa). Xem giải thích đầy đủ đã trao đổi với người dùng.
DEFAULT_RARE_THRESHOLD = 0.01
RARE_LABEL = "Khac"


def group_rare_categories(series: pd.Series, threshold: float = DEFAULT_RARE_THRESHOLD) -> pd.Series:
    """Gộp các giá trị HIẾM (tỉ lệ xuất hiện < threshold trong TOÀN BỘ
    series) thành 1 nhóm chung `RARE_LABEL` -- tránh one-hot tạo quá nhiều
    cột con gần như toàn số 0 khi cột có nhiều giá trị khác nhau (vd
    native.country ~42 giá trị, nhiều nước chỉ có vài dòng).
    """
    text = series.astype(str).str.strip()
    freq = text.value_counts(normalize=True)
    rare_values = freq[freq < threshold].index
    return text.where(~text.isin(rare_values), RARE_LABEL)


@dataclass
class EncodedColumnInfo:
    """Theo dõi 1 cột one-hot MỚI sinh ra thuộc về cột CHỮ GỐC nào -- cần
    thiết để sau này cộng dồn importance (xem `aggregate_importance_by_origin()`)
    hoặc hiển thị kết quả cho người dùng (không nên chỉ hiện
    "workclass_Private" trần trụi mà không biết nó thuộc cột gốc nào).
    """

    encoded_column: str
    source_column: str


def one_hot_encode_columns(
    df: pd.DataFrame,
    columns: list[str],
    threshold: float = DEFAULT_RARE_THRESHOLD,
) -> tuple[pd.DataFrame, list[EncodedColumnInfo]]:
    """Mã hoá DANH SÁCH cột chữ trong `columns` thành các cột one-hot
    (drop-first), sau khi đã gộp nhóm hiếm TỪNG CỘT riêng (ngưỡng tính theo
    CHÍNH cột đó, không so chéo giữa các cột).

    Trả về (DataFrame đã thay thế các cột chữ gốc bằng cột one-hot, danh
    sách EncodedColumnInfo để truy vết nguồn gốc). DataFrame trả về GIỮ
    NGUYÊN mọi cột KHÔNG nằm trong `columns` (kể cả cột nhãn, cột số khác)
    -- chỉ thay thế đúng các cột trong `columns`, không động gì tới phần
    còn lại của df.
    """
    result = df.copy()
    encoded_info: list[EncodedColumnInfo] = []

    for col in columns:
        grouped = group_rare_categories(df[col], threshold)
        dummies = pd.get_dummies(grouped, prefix=col, drop_first=True)
        # pd.get_dummies trả cột kiểu bool -- ép về int (0/1) để khớp kiểu
        # dữ liệu số mà 3 thuật toán detect (confident_learning.py/
        # distance_based.py/ensemble_based.py) đang kỳ vọng ở feature_columns.
        dummies = dummies.astype(int)

        result = result.drop(columns=[col])
        result = pd.concat([result, dummies], axis=1)
        encoded_info.extend(
            EncodedColumnInfo(encoded_column=c, source_column=col) for c in dummies.columns
        )

    return result, encoded_info


def aggregate_importance_by_origin(
    ranked: list[FeatureRanking], encoded_info: list[EncodedColumnInfo]
) -> list[FeatureRanking]:
    """Cộng dồn importance của các cột one-hot CON về lại đúng cột CHỮ GỐC
    của chúng -- BẮT BUỘC phải gọi hàm này trước khi đưa kết quả
    `rank_by_importance()` vào `select_by_elbow()`, nếu candidate_columns có
    lẫn cột one-hot. Lý do: Elbow Method so sánh importance giữa các cột
    LIỀN KỀ trong bảng xếp hạng -- nếu chạy thẳng trên các mảnh one-hot rời
    rạc (1 cột gốc có thể bị xé thành nhiều mảnh rải khắp bảng), phép so
    sánh "liền kề" mất hết ý nghĩa. Đã kiểm chứng thực nghiệm: chạy Elbow
    trực tiếp trên 66 cột one-hot thô (Adult Income, 8 cột chữ) chỉ loại
    được 2/66 cột -- gần như không lọc được gì, trong khi chạy trên bảng đã
    cộng dồn (14 cột gốc) mới cho kết quả có ý nghĩa.

    Cột nào KHÔNG xuất hiện trong `encoded_info` (tức cột số bình thường,
    không qua one-hot) thì giữ nguyên importance, coi "nguồn gốc" là chính
    nó. Trả về danh sách đã SẮP XẾP GIẢM DẦN theo importance -- cùng định
    dạng `rank_by_importance()` trả về, dùng thẳng được cho
    `select_by_elbow()`/`filter_correlated()` tiếp theo.
    """
    origin_of = {info.encoded_column: info.source_column for info in encoded_info}

    aggregated: dict[str, float] = {}
    for r in ranked:
        origin = origin_of.get(r.column, r.column)
        aggregated[origin] = aggregated.get(origin, 0.0) + r.importance

    result = [FeatureRanking(column=col, importance=imp) for col, imp in aggregated.items()]
    result.sort(key=lambda r: r.importance, reverse=True)
    return result
