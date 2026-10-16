"""
Module GIẢM SỐ CỘT (feature selection) cho Class Noise -- chạy TRƯỚC Confident
Learning, theo đúng quy trình thầy hướng dẫn (3 bước):
  Bước 1 (module này): xếp hạng cột theo mức LIÊN QUAN TỚI NHÃN, giữ top-K.
  Bước 2 (module này): trong các cột còn lại, loại bớt cột THỪA THÔNG TIN LẪN
    NHAU (tương quan cao giữa CỘT VỚI CỘT, không liên quan gì tới nhãn).
  Bước 3 (chưa code ở đây): kiểm tra outlier + biến đổi logarit cho các cột
    cuối cùng -- outlier tái dùng detector sẵn có ở attribute_noise/.

Phân biệt quan trọng giữa Bước 1 và Bước 2 (dễ nhầm vì cả 2 đều "giảm cột"):
  - Bước 1 hỏi: "cột này có giúp đoán được NHÃN không?"   (cột vs NHÃN)
  - Bước 2 hỏi: "2 cột này có đang nói CÙNG 1 chuyện với NHAU không?" (cột vs CỘT)
Vì hỏi 2 câu khác nhau nên dùng 2 kỹ thuật khác nhau, không gộp làm 1 được.
"""

from dataclasses import dataclass

import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder


@dataclass
class FeatureRanking:
    """Kết quả xếp hạng 1 cột ở Bước 1."""

    column: str
    importance: float


def rank_by_importance(
    df: pd.DataFrame,
    label_column: str,
    candidate_columns: list[str],
    n_estimators: int = 300,
    random_state: int = 42,
) -> list[FeatureRanking]:
    """Bước 1: xếp hạng các cột candidate theo mức độ LIÊN QUAN TỚI NHÃN.

    Train 1 Random Forest duy nhất dự đoán nhãn từ TẤT CẢ cột candidate, rồi
    đọc `feature_importances_` -- RF tự tính được mỗi cột góp phần bao nhiêu
    vào việc tách đúng nhãn qua các lần chia nhánh của 300 cây. Dùng cách này
    (thay vì hệ số tương quan Pearson thường) vì nó bắt được cả quan hệ
    KHÔNG tuyến tính giữa cột và nhãn, tổng quát hơn.

    Trả về danh sách đã SẮP XẾP GIẢM DẦN theo importance -- cột quan trọng
    nhất đứng đầu, để `filter_correlated()` ở Bước 2 biết thứ tự ưu tiên giữ.
    """
    working = df.copy()
    for col in candidate_columns:
        working[col] = pd.to_numeric(working[col], errors="coerce")

    label_ok = working[label_column].astype(str).str.strip() != ""
    features_ok = working[candidate_columns].notna().all(axis=1)
    usable = working[label_ok & features_ok]

    X = usable[candidate_columns].to_numpy()
    y = LabelEncoder().fit_transform(usable[label_column].to_numpy())

    rf = RandomForestClassifier(
        n_estimators=n_estimators,
        class_weight="balanced",
        random_state=random_state,
        n_jobs=-1,
    )
    rf.fit(X, y)

    rankings = [
        FeatureRanking(column=col, importance=float(imp))
        for col, imp in zip(candidate_columns, rf.feature_importances_)
    ]
    rankings.sort(key=lambda r: r.importance, reverse=True)
    return rankings


def select_by_elbow(ranked: list[FeatureRanking]) -> list[str]:
    """Chọn cột theo "Điểm Gãy" (Elbow Method) -- kỹ thuật THẬT, dùng phổ
    biến để chọn số thành phần trong PCA (scree plot) hay số cụm K trong
    K-means. KHÔNG cần tự chọn tay bất kỳ ngưỡng % hay số trần nào (khác
    với 2 bản thử nghiệm trước đó: "luôn lấy 8 cột" rồi "lấy đủ 90% có cap
    10" -- cả 2 đều cần 1 con số tự đặt, đã bỏ vì thiếu căn cứ vững) -- cách
    này TỰ TÌM điểm "gãy khúc" thật sự trong CHÍNH dữ liệu.

    Cách làm: tính tỉ lệ importance[cột sau] / importance[cột trước] cho mỗi
    cặp cột liền kề -- tỉ lệ càng gần 1 nghĩa là 2 cột liền kề gần ngang
    nhau (chưa gãy); tỉ lệ càng nhỏ nghĩa là cột sau TỤT MẠNH so với cột
    trước (dấu hiệu "hết vùng quan trọng, sang vùng vụn vặt"). Tìm vị trí
    có tỉ lệ THẤP NHẤT trong toàn bộ bảng xếp hạng -- đó là điểm gãy rõ nhất.
    Giữ lại mọi cột TRƯỚC điểm gãy, bỏ từ điểm gãy trở đi.

    Đã kiểm chứng trên Credit Card Fraud: điểm gãy mạnh nhất rơi đúng vào
    cột thứ 8→9 (V3→V2, tỉ lệ tụt còn ~53.5%) ở CẢ 3 mức n_estimators đã
    thử (200/300/500) -- không phải ngẫu nhiên 1 lần.
    """
    if len(ranked) < 2:
        return [r.column for r in ranked]

    drop_ratios = [
        ranked[i].importance / ranked[i - 1].importance
        for i in range(1, len(ranked))
    ]
    elbow_index = drop_ratios.index(min(drop_ratios)) + 1
    return [r.column for r in ranked[:elbow_index]]


def filter_correlated(
    df: pd.DataFrame,
    ranked_columns: list[str],
    threshold: float = 0.8,
) -> list[str]:
    """Bước 2: loại cột THỪA THÔNG TIN LẪN NHAU (tương quan cao giữa CỘT VỚI
    CỘT còn lại, không liên quan gì tới nhãn) -- ngưỡng 0.8 là quy ước thống
    kê phổ biến (giống 1.5 của IQR, 3.0 của Z-score).

    `ranked_columns` PHẢI đã được sắp xếp theo độ quan trọng giảm dần (lấy từ
    `rank_by_importance()`). Duyệt lần lượt theo đúng thứ tự đó: với mỗi cột,
    nếu nó tương quan >= threshold với 1 cột ĐÃ ĐƯỢC GIỮ trước đó thì loại nó
    đi -- vì cột đã giữ luôn quan trọng hơn hoặc bằng (do duyệt đúng thứ tự
    ưu tiên), nên trong mỗi cặp "thừa nhau", cột kém quan trọng hơn bị loại.
    """
    working = df.copy()
    for col in ranked_columns:
        working[col] = pd.to_numeric(working[col], errors="coerce")

    corr_matrix = working[ranked_columns].corr().abs()

    kept: list[str] = []
    for col in ranked_columns:
        too_similar_to_kept = any(corr_matrix.loc[col, k] >= threshold for k in kept)
        if not too_similar_to_kept:
            kept.append(col)
    return kept
