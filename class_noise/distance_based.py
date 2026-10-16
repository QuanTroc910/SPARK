"""
Phát hiện CLASS NOISE bằng kỹ thuật DISTANCE-BASED: Mutual k-Nearest Neighbor.

Dựa theo bài báo N13 trong Bảng 6 (Gupta & Gupta, 2019) -- Liu, Huawen, and
Shichao Zhang. "Noisy data elimination using mutual k-nearest neighbor for
classification mining." Journal of Systems and Software 85.5 (2012):
1067-1074. Đây là bài DUY NHẤT trong nhóm "Distance based" vừa đạt điểm chất
lượng 9/9 (Bảng 4) vừa có tên bài khớp đúng 100% với định nghĩa distance-based
của chính review (dùng thuần khoảng cách, không train model nào).

KHÁC HẲN Confident Learning (confident_learning.py) ở điểm cốt lõi: module
này KHÔNG train bất kỳ model học máy nào, chỉ dựa vào KHOẢNG CÁCH giữa các
điểm dữ liệu trong không gian đặc trưng -- nên không có khái niệm "xác suất
dự đoán" hay "cross-validation" như Confident Learning.

Ý tưởng cốt lõi -- "láng giềng LẪN NHAU" (mutual neighbor):
  k-NN thông thường là quan hệ 1 CHIỀU: B có thể là 1-trong-k-láng-giềng-gần-
  nhất của A, nhưng A chưa chắc là láng giềng gần của B (thường xảy ra ở vùng
  dữ liệu THƯA, nơi B có rất ít điểm xung quanh nên A "lọt" vào top-k của B dù
  thực ra A khá xa). Để tránh báo nhiễu nhầm vì hiệu ứng này, chỉ coi A và B
  là láng giềng CỦA NHAU khi quan hệ đúng CẢ 2 CHIỀU: A nằm trong k-láng-giềng-
  gần-nhất của B VÀ B nằm trong k-láng-giềng-gần-nhất của A.

4 bước:
  Bước 1: Chuẩn hoá các cột đặc trưng về z-score -- BẮT BUỘC vì khoảng cách
          Euclid nhạy với đơn vị đo (cột "tuổi" 0-100 sẽ át hẳn cột tỉ lệ
          0-1 nếu không chuẩn hoá trước).
  Bước 2: Với mỗi điểm, tìm k láng giềng gần nhất (Euclid).
  Bước 3: Lọc ra láng giềng LẪN NHAU (quan hệ 2 chiều ở trên).
  Bước 4: Với mỗi điểm có >=1 láng giềng lẫn nhau, tính tỉ lệ láng giềng lẫn
          nhau mang nhãn KHÁC nhãn của chính điểm đó -- vượt quá bán (>50%)
          thì gắn cờ nghi ngờ sai nhãn. Điểm KHÔNG có láng giềng lẫn nhau nào
          thì bỏ qua, không kết luận được gì (giống "-1" của Confident
          Learning khi không lớp nào vượt ngưỡng tự tin).
"""

from collections import Counter
from dataclasses import dataclass

import pandas as pd
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

from .config import ClassNoiseConfig


@dataclass
class DistanceNoiseFinding:
    """Kết quả cho ĐÚNG 1 dòng bị nghi ngờ sai nhãn.

    disagreement_ratio: tỉ lệ láng giềng LẪN NHAU mang nhãn khác (0..1) --
    dùng để sắp xếp mức độ đáng ngờ, đóng vai trò tương đương "margin" của
    ClassNoiseFinding bên confident_learning.py.
    """

    row_number: int
    recorded_label: str
    suggested_label: str
    disagreement_ratio: float


@dataclass
class DistanceNoiseDiagnostics:
    """Chỉ số chẩn đoán cho 1 lượt chạy -- vai trò tương đương
    ClassNoiseDiagnostics bên confident_learning.py, nhưng đổi khác vì
    phương pháp distance-based không có model/cv_accuracy để soi.

    n_rows_with_mutual_neighbors: bao nhiêu dòng có ít nhất 1 láng giềng lẫn
    nhau -- đây là chỉ số "độ phủ" (coverage) PHẢI xem trước khi tin findings:
    nếu quá ít dòng có láng giềng lẫn nhau (vd do k quá nhỏ hoặc dữ liệu quá
    thưa), phần lớn dòng không kết luận được gì, findings sẽ rất ít dù dữ
    liệu có thể vẫn còn nhiễu thật.
    """

    n_rows_total: int
    n_rows_used: int
    k: int
    n_rows_with_mutual_neighbors: int
    class_names: list[str]
    class_counts: dict[str, int]


@dataclass
class DistanceNoiseResult:
    findings: list[DistanceNoiseFinding]
    diagnostics: DistanceNoiseDiagnostics


def _prepare_usable_subset(df: pd.DataFrame, config: ClassNoiseConfig) -> pd.DataFrame:
    """Lọc dòng dùng được: nhãn không rỗng, mọi cột đặc trưng ép được thành
    số -- lặp lại y hệt logic của confident_learning.py (không import dùng
    chung vì đây là hàm private riêng của module đó, giữ 2 module độc lập
    nhau để không bị ràng buộc chéo khi sửa sau này).
    """
    working = df.copy()
    for col in config.feature_columns:
        working[col] = pd.to_numeric(working[col], errors="coerce")

    label_ok = working[config.label_column].astype(str).str.strip() != ""
    features_ok = working[config.feature_columns].notna().all(axis=1)
    return working[label_ok & features_ok]


def detect_class_noise_distance(
    df: pd.DataFrame, config: ClassNoiseConfig, k: int = 5, disagreement_threshold: float = 0.5
) -> DistanceNoiseResult:
    """Hàm chính: chạy đủ 4 bước Mutual k-NN trên df theo config.

    k: số láng giềng gần nhất xét cho mỗi điểm (mặc định 5, giá trị phổ biến
       trong tài liệu k-NN).
    disagreement_threshold: tỉ lệ láng giềng lẫn nhau mang nhãn khác TỐI
       THIỂU để gắn cờ (mặc định 0.5 = đa số láng giềng không đồng ý với
       nhãn ghi thì mới nghi ngờ).
    """
    usable = _prepare_usable_subset(df, config)
    n_rows_used = len(usable)

    X_raw = usable[config.feature_columns].to_numpy()
    X = StandardScaler().fit_transform(X_raw)  # Bước 1: z-score chuẩn hoá
    y_labels = usable[config.label_column].astype(str).to_numpy()
    row_numbers = usable.index.to_numpy() + 1  # quy ước 1-based, khớp ClassNoiseFinding

    # Bước 2: tìm k láng giềng gần nhất cho mỗi điểm (n_neighbors=k+1 vì
    # chính điểm đó luôn là láng giềng gần nhất của chính nó, khoảng cách 0).
    n_neighbors = min(k + 1, n_rows_used)
    # n_jobs=-1: tận dụng đa luồng khi tìm láng giềng -- cần thiết với file
    # lớn (vd Credit Card Fraud 284k dòng), không ảnh hưởng kết quả.
    nn_model = NearestNeighbors(n_neighbors=n_neighbors, n_jobs=-1)
    nn_model.fit(X)
    _distances, indices = nn_model.kneighbors(X)
    neighbor_sets = [set(indices[i, 1:]) for i in range(n_rows_used)]  # bỏ cột đầu (chính nó)

    findings: list[DistanceNoiseFinding] = []
    n_with_mutual = 0

    for i in range(n_rows_used):
        # Bước 3: lọc láng giềng LẪN NHAU (quan hệ 2 chiều).
        mutual = [j for j in neighbor_sets[i] if i in neighbor_sets[j]]
        if not mutual:
            continue  # không có láng giềng lẫn nhau -> không kết luận được gì
        n_with_mutual += 1

        # Bước 4: tính tỉ lệ láng giềng lẫn nhau mang nhãn KHÁC nhãn hiện tại.
        neighbor_labels = [y_labels[j] for j in mutual]
        disagree_count = sum(1 for lbl in neighbor_labels if lbl != y_labels[i])
        disagreement_ratio = disagree_count / len(mutual)

        if disagreement_ratio > disagreement_threshold:
            majority_label = Counter(neighbor_labels).most_common(1)[0][0]
            findings.append(
                DistanceNoiseFinding(
                    row_number=int(row_numbers[i]),
                    recorded_label=str(y_labels[i]),
                    suggested_label=str(majority_label),
                    disagreement_ratio=float(disagreement_ratio),
                )
            )

    findings.sort(key=lambda f: f.disagreement_ratio, reverse=True)

    class_counts_raw = pd.Series(y_labels).value_counts()
    diagnostics = DistanceNoiseDiagnostics(
        n_rows_total=len(df),
        n_rows_used=n_rows_used,
        k=k,
        n_rows_with_mutual_neighbors=n_with_mutual,
        class_names=list(class_counts_raw.index),
        class_counts={str(c): int(cnt) for c, cnt in class_counts_raw.items()},
    )

    return DistanceNoiseResult(findings=findings, diagnostics=diagnostics)
