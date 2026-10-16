"""
So sánh 2 thuật toán phát hiện CLASS NOISE trên CÙNG 1 bộ dữ liệu (Adult
Census Income) bằng NHIỄU NHÃN CẤY THÊM CÓ KIỂM SOÁT -- dùng lại Y HỆT
phương pháp đánh giá đã có ở evaluate_class_noise_synthetic.py (cấy nhiễu
biết trước rồi đo Precision/Recall/F1 so với đúng các dòng đã flip), để
2 thuật toán được đo trên CÙNG 1 ground truth, so sánh công bằng:

  1. Confident Learning + Random Forest (Single learning-based, đang chạy
     trên web -- class_noise/confident_learning.py).
  2. Mutual k-Nearest Neighbor (Distance-based, N13 -- vừa code ở
     class_noise/distance_based.py).

Chạy: python3 evaluate_distance_vs_confident.py
"""

import random

import pandas as pd

from attribute_noise.pipeline import load_data
from class_noise.config import ClassNoiseConfig
from class_noise.confident_learning import detect_class_noise
from class_noise.distance_based import detect_class_noise_distance

DATA_PATH = "data/kaggle_adult_income.csv"
LABEL_COLUMN = "income"
FEATURE_COLUMNS = ["age", "fnlwgt", "education.num", "capital.gain", "capital.loss", "hours.per.week"]
NOISE_RATES = [0.10, 0.30]  # nhẹ (10%) và nặng (30%), giống bản gốc
RANDOM_SEED = 42


def inject_label_noise(df: pd.DataFrame, noise_rate: float, seed: int) -> tuple[pd.DataFrame, set[int]]:
    """Trả về (df đã cấy nhiễu, tập index các dòng BỊ FLIP -- ground truth)."""
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

    # --- Thuật toán 1: Confident Learning + Random Forest (đang chạy trên web) ---
    cl_config = ClassNoiseConfig(label_column=LABEL_COLUMN, feature_columns=FEATURE_COLUMNS)
    cl_result = detect_class_noise(noisy_df, cl_config)
    cl_flagged = {f.row_number - 1 for f in cl_result.findings}
    cl_tp, cl_fp, cl_fn, cl_p, cl_r, cl_f1 = _prf(cl_flagged, flip_indices)

    # --- Thuật toán 2: Mutual k-NN (N13, distance-based) ---
    dist_config = ClassNoiseConfig(label_column=LABEL_COLUMN, feature_columns=FEATURE_COLUMNS)
    dist_result = detect_class_noise_distance(noisy_df, dist_config, k=5)
    dist_flagged = {f.row_number - 1 for f in dist_result.findings}
    dist_tp, dist_fp, dist_fn, dist_p, dist_r, dist_f1 = _prf(dist_flagged, flip_indices)

    # --- Mức độ 2 thuật toán ĐỒNG Ý với nhau (không liên quan ground truth) ---
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
