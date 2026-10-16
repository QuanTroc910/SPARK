"""
Y HỆT evaluate_distance_vs_confident.py nhưng chạy trên Credit Card Fraud
(284.807 dòng, 29 đặc trưng số V1-V28 + Amount) thay vì Adult Income -- để
xem kết luận "N13 (Mutual k-NN) thắng Confident Learning" có còn đúng không
khi đặc trưng MẠNH hơn hẳn (29 cột PCA-transformed thay vì 6 cột thô).

Lưu ý quan trọng về cách cấy nhiễu trên bộ NÀY: Credit Card Fraud cực kỳ lệch
lớp (492/284.807 ≈ 0,17% là fraud) -- flip ngẫu nhiên đồng đều 10%/30% số
dòng nghĩa là gần như toàn bộ lượt flip rơi vào dòng lớp 0 (biến thành fraud
giả), chỉ 1 phần rất nhỏ trong 492 dòng fraud thật bị flip ngược lại. Đây là
đặc điểm THẬT của bộ dữ liệu, không phải lỗi -- giữ nguyên cùng cách cấy
nhiễu với bản Adult Income để so sánh phương pháp luận nhất quán.

Chạy: python3 evaluate_distance_vs_confident_creditcard.py
(CẢNH BÁO: chậm hơn hẳn bản Adult Income vì 284.807 dòng x 29 cột --
 Random Forest 300 cây x 5-fold CV x 2 mức nhiễu + Mutual k-NN x 2 mức nhiễu.)
"""

import random
import time

import pandas as pd

from attribute_noise.pipeline import load_data
from class_noise.config import ClassNoiseConfig
from class_noise.confident_learning import detect_class_noise
from class_noise.distance_based import detect_class_noise_distance

DATA_PATH = "data/kaggle_creditcard_fraud.csv"
LABEL_COLUMN = "Class"
FEATURE_COLUMNS = [f"V{i}" for i in range(1, 29)] + ["Amount"]
NOISE_RATES = [0.10, 0.30]
RANDOM_SEED = 42


def inject_label_noise(df: pd.DataFrame, noise_rate: float, seed: int) -> tuple[pd.DataFrame, set[int]]:
    rng = random.Random(seed)
    classes = sorted(df[LABEL_COLUMN].unique())
    n_flip = int(len(df) * noise_rate)
    flip_indices = set(rng.sample(list(df.index), n_flip))

    noisy_df = df.copy()
    for idx in flip_indices:
        true_label = df.loc[idx, LABEL_COLUMN]
        other_classes = [c for c in classes if c != true_label]
        noisy_df.loc[idx, LABEL_COLUMN] = rng.choice(other_classes)
    return noisy_df, flip_indices


def _prf(flagged_indices: set[int], flip_indices: set[int]) -> tuple[int, int, int, float, float, float]:
    tp = len(flagged_indices & flip_indices)
    fp = len(flagged_indices - flip_indices)
    fn = len(flip_indices - flagged_indices)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return tp, fp, fn, precision, recall, f1


def evaluate_one_noise_rate(clean_df: pd.DataFrame, noise_rate: float) -> None:
    noisy_df, flip_indices = inject_label_noise(clean_df, noise_rate, RANDOM_SEED)

    print(f"\n{'=' * 78}")
    print(f"=== Mức nhiễu cấy thêm: {noise_rate:.0%} ({len(flip_indices)}/{len(clean_df)} dòng bị flip nhãn) ===")
    print(f"{'=' * 78}")

    t0 = time.time()
    cl_config = ClassNoiseConfig(label_column=LABEL_COLUMN, feature_columns=FEATURE_COLUMNS)
    cl_result = detect_class_noise(noisy_df, cl_config)
    cl_flagged = {f.row_number - 1 for f in cl_result.findings}
    cl_tp, cl_fp, cl_fn, cl_p, cl_r, cl_f1 = _prf(cl_flagged, flip_indices)
    print(f"[Confident Learning xong sau {time.time() - t0:.1f}s]")

    t0 = time.time()
    dist_config = ClassNoiseConfig(label_column=LABEL_COLUMN, feature_columns=FEATURE_COLUMNS)
    dist_result = detect_class_noise_distance(noisy_df, dist_config, k=5)
    dist_flagged = {f.row_number - 1 for f in dist_result.findings}
    dist_tp, dist_fp, dist_fn, dist_p, dist_r, dist_f1 = _prf(dist_flagged, flip_indices)
    print(f"[Mutual k-NN xong sau {time.time() - t0:.1f}s]")

    overlap = len(cl_flagged & dist_flagged)

    print(f"\n{'Thuật toán':<32} {'Gắn cờ':>8} {'TP':>6} {'FP':>6} {'FN':>6} {'Precision':>10} {'Recall':>8} {'F1':>8}")
    print(f"{'Confident Learning (RF)':<32} {len(cl_flagged):>8} {cl_tp:>6} {cl_fp:>6} {cl_fn:>6} {cl_p:>10.4f} {cl_r:>8.4f} {cl_f1:>8.4f}")
    print(f"{'Mutual k-NN (N13)':<32} {len(dist_flagged):>8} {dist_tp:>6} {dist_fp:>6} {dist_fn:>6} {dist_p:>10.4f} {dist_r:>8.4f} {dist_f1:>8.4f}")

    print(f"\nCL diagnostics: cv_accuracy={cl_result.diagnostics.cv_accuracy:.4f}  baseline={cl_result.diagnostics.majority_baseline_accuracy:.4f}")
    print(f"N13 diagnostics: k={dist_result.diagnostics.k}  dòng có láng giềng lẫn nhau={dist_result.diagnostics.n_rows_with_mutual_neighbors}/{dist_result.diagnostics.n_rows_used} ({dist_result.diagnostics.n_rows_with_mutual_neighbors/dist_result.diagnostics.n_rows_used:.1%})")
    print(f"Số dòng CẢ 2 thuật toán cùng gắn cờ: {overlap}")


def main() -> None:
    df = load_data(DATA_PATH)
    for rate in NOISE_RATES:
        evaluate_one_noise_rate(df, rate)


if __name__ == "__main__":
    main()
