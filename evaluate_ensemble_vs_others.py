"""
So sánh ĐỦ CẢ 3 thuật toán phát hiện CLASS NOISE (khớp đúng 3 nhóm Bảng 6,
Gupta & Gupta 2019) trên CÙNG 1 bộ dữ liệu (Adult Income) bằng nhiễu nhãn cấy
thêm có kiểm soát (y hệt phương pháp evaluate_distance_vs_confident.py):

  1. Single learning-based  -- Confident Learning + Random Forest
  2. Distance-based (N13)   -- Mutual k-NN
  3. Ensemble-based (N29)   -- LogisticRegression + GaussianNB + LinearSVC biểu quyết

Chạy: python3 evaluate_ensemble_vs_others.py
"""

import random

import pandas as pd

from attribute_noise.pipeline import load_data
from class_noise.config import ClassNoiseConfig
from class_noise.confident_learning import detect_class_noise
from class_noise.distance_based import detect_class_noise_distance
from class_noise.ensemble_based import detect_class_noise_ensemble

DATA_PATH = "data/kaggle_adult_income.csv"
LABEL_COLUMN = "income"
FEATURE_COLUMNS = ["age", "fnlwgt", "education.num", "capital.gain", "capital.loss", "hours.per.week"]
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

    print(f"\n{'=' * 86}")
    print(f"=== Mức nhiễu cấy thêm: {noise_rate:.0%} ({len(flip_indices)}/{len(clean_df)} dòng bị flip nhãn) ===")
    print(f"{'=' * 86}")

    config = ClassNoiseConfig(label_column=LABEL_COLUMN, feature_columns=FEATURE_COLUMNS)

    cl_result = detect_class_noise(noisy_df, config)
    cl_flagged = {f.row_number - 1 for f in cl_result.findings}
    cl_stats = _prf(cl_flagged, flip_indices)

    dist_result = detect_class_noise_distance(noisy_df, config, k=5)
    dist_flagged = {f.row_number - 1 for f in dist_result.findings}
    dist_stats = _prf(dist_flagged, flip_indices)

    ens_result = detect_class_noise_ensemble(noisy_df, config)
    ens_flagged = {f.row_number - 1 for f in ens_result.findings}
    ens_stats = _prf(ens_flagged, flip_indices)

    print(f"\n{'Thuật toán':<36} {'Gắn cờ':>8} {'TP':>6} {'FP':>6} {'FN':>6} {'Precision':>10} {'Recall':>8} {'F1':>8}")
    for name, flagged, stats in [
        ("Single learning (Confident Learning)", cl_flagged, cl_stats),
        ("Distance-based (N13, Mutual k-NN)", dist_flagged, dist_stats),
        ("Ensemble-based (N29, 3 classifier)", ens_flagged, ens_stats),
    ]:
        tp, fp, fn, p, r, f1 = stats
        print(f"{name:<36} {len(flagged):>8} {tp:>6} {fp:>6} {fn:>6} {p:>10.4f} {r:>8.4f} {f1:>8.4f}")

    print(f"\nCL diagnostics: cv_accuracy={cl_result.diagnostics.cv_accuracy:.4f}  baseline={cl_result.diagnostics.majority_baseline_accuracy:.4f}")
    print(f"N13 diagnostics: dòng có láng giềng lẫn nhau={dist_result.diagnostics.n_rows_with_mutual_neighbors}/{dist_result.diagnostics.n_rows_used} ({dist_result.diagnostics.n_rows_with_mutual_neighbors/dist_result.diagnostics.n_rows_used:.1%})")
    print(f"N29 diagnostics: baseline={ens_result.diagnostics.majority_baseline_accuracy:.4f}  per-classifier accuracy:")
    for name, acc in ens_result.diagnostics.per_classifier_accuracy.items():
        print(f"    {name:<20} {acc:.4f}  (chênh baseline: {(acc - ens_result.diagnostics.majority_baseline_accuracy)*100:+.2f} điểm %)")

    overlap_all = len(cl_flagged & dist_flagged & ens_flagged)
    print(f"\nSố dòng CẢ 3 thuật toán cùng gắn cờ: {overlap_all}")


def main() -> None:
    df = load_data(DATA_PATH)
    for rate in NOISE_RATES:
        evaluate_one_noise_rate(df, rate)


if __name__ == "__main__":
    main()
