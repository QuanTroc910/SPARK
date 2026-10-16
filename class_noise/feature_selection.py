"""
Module GIẢM SỐ CỘT (feature selection) cho Class Noise -- chạy TRƯỚC Confident
Learning, theo đúng quy trình thầy hướng dẫn (3 bước):
  Bước 1 (module này): xếp hạng cột theo mức LIÊN QUAN TỚI NHÃN, giữ top-K.
  Bước 2 (module này): trong các cột còn lại, loại bớt cột THỪA THÔNG TIN LẪN
    NHAU (tương quan cao giữa CỘT VỚI CỘT, không liên quan gì tới nhãn).
  Bước 3 (module này): trên các cột CUỐI CÙNG sau Bước 1+2 -- (3a) cap outlier
    về biên IQR/Z-score (TÁI DÙNG detect_outlier() + apply_handling() đã có ở
    attribute_noise/, không viết lại công thức IQR/Z-score lần 2), (3b) biến
    đổi logarit để phân phối đỡ "lệch đuôi dài", cân đối hơn.

Phân biệt quan trọng giữa Bước 1 và Bước 2 (dễ nhầm vì cả 2 đều "giảm cột"):
  - Bước 1 hỏi: "cột này có giúp đoán được NHÃN không?"   (cột vs NHÃN)
  - Bước 2 hỏi: "2 cột này có đang nói CÙNG 1 chuyện với NHAU không?" (cột vs CỘT)
Vì hỏi 2 câu khác nhau nên dùng 2 kỹ thuật khác nhau, không gộp làm 1 được.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder

from attribute_noise.attribute_handling import HandlingAction, HandlingChoice, apply_handling
from attribute_noise.config import ColumnDType, ColumnNoiseConfig, NoiseType
from attribute_noise.detectors import detect_outlier
from attribute_noise.pipeline import NoiseFinding


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
    tìm ô outlier + `apply_handling()` (attribute_noise/attribute_handling.py)
    với action `CAP_TO_RANGE` để cap -- không viết lại công thức IQR/Z-score
    lần thứ 2, đúng tinh thần "tái dùng" đã áp dụng xuyên suốt dự án.
    """
    result = df.copy()
    for col in columns:
        cfg = ColumnNoiseConfig(
            column=col,
            dtype=ColumnDType.FLOAT,
            noise_types=[NoiseType.OUTLIER],
            outlier_method=outlier_method,
            outlier_threshold=outlier_threshold,
        )
        is_outlier = detect_outlier(result[col], cfg)
        findings = [
            NoiseFinding(row_index=idx, column=col, noise_type=NoiseType.OUTLIER.value, value=None)
            for idx in result.index[is_outlier]
        ]
        if not findings:
            continue  # cột này không có outlier -> không cần gọi apply_handling()

        choice = HandlingChoice(column=col, noise_type=NoiseType.OUTLIER, action=HandlingAction.CAP_TO_RANGE)
        result, _stats = apply_handling(result, [cfg], findings, [choice])
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
