"""
So sánh TRỰC TIẾP: chạy cả 3 thuật toán Class Noise trên Adult Income với
(A) CHỈ 6 cột số (đúng như evaluate_class_noise_richer_datasets.py đã chạy
trước đó) và (B) 6 cột số + 8 cột chữ đã one-hot encode (drop-first, gộp
nhóm hiếm <1% -- class_noise/categorical_encoding.py) -- CÙNG 1 cách chia
train/test (80/20, stratify theo nhãn, random_state=42) để so sánh công bằng.

QUAN TRỌNG -- khác với one_hot_encode_columns() dùng trong app.py (chạy
trên 1 file DUY NHẤT, không có khái niệm train/test): ở đây phải tách
riêng FIT (học value nào "phổ biến" tới mức giữ riêng, value nào "hiếm" bị
gộp "Khac" -- CHỈ dựa trên TRAIN) và APPLY (dùng ĐÚNG mapping đã học từ
train để biến đổi CẢ train lẫn test), để không bị rò rỉ thông tin test vào
bước chọn danh sách category. Cột one-hot của test được REINDEX về đúng bộ
cột one-hot của train (`reindex(..., fill_value=0)`) -- 1 giá trị category
xuất hiện ở test nhưng KHÔNG hề thấy ở train (hiếm, gần như không xảy ra
với Adult Income vì đủ lớn) sẽ tự động rơi về "mọi cột one-hot = 0" (coi
như thuộc nhóm tham chiếu/baseline bị drop-first) -- không bị lỗi, không
cần xử lý đặc biệt.

Chạy: python3 evaluate_adult_categorical_vs_numeric.py
"""

import pandas as pd
from sklearn.model_selection import train_test_split

from attribute_noise.pipeline import load_data
from class_noise.categorical_encoding import group_rare_categories
from evaluate_class_noise_train_test import (
    _print_confusion,
    _print_report_table,
    evaluate_distance,
    evaluate_ensemble,
    evaluate_single_learning,
    preprocess,
)

DATA_PATH = "data/kaggle_adult_income.csv"
LABEL_COLUMN = "income"
NUMERIC_COLUMNS = ["age", "fnlwgt", "education.num", "capital.gain", "capital.loss", "hours.per.week"]
CATEGORICAL_COLUMNS = ["workclass", "education", "marital.status", "occupation", "relationship", "race", "sex", "native.country"]
RARE_THRESHOLD = 0.01


def fit_transform_categorical(
    train_df: pd.DataFrame, test_df: pd.DataFrame, columns: list[str]
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """FIT danh sách giá trị "phổ biến" (gộp nhóm hiếm) + bộ cột one-hot
    (drop-first) TỪ TRAIN, rồi APPLY y hệt lên CẢ train lẫn test -- tránh rò
    rỉ thông tin test vào bước chọn category nào được giữ riêng.
    """
    train_result = train_df.copy()
    test_result = test_df.copy()
    all_dummy_columns: list[str] = []

    for col in columns:
        train_grouped = group_rare_categories(train_df[col], RARE_THRESHOLD)
        common_values = set(train_grouped.unique())  # danh sách giá trị TRAIN đã giữ (kể cả "Khac")

        test_text = test_df[col].astype(str).str.strip()
        test_grouped = test_text.where(test_text.isin(common_values), "Khac")

        train_dummies = pd.get_dummies(train_grouped, prefix=col, drop_first=True).astype(int)
        test_dummies = pd.get_dummies(test_grouped, prefix=col).astype(int)
        # Reindex test về ĐÚNG bộ cột one-hot của train (loại cột tham chiếu
        # bị drop-first, điền 0 cho category nào train có mà test thiếu hẳn).
        test_dummies = test_dummies.reindex(columns=train_dummies.columns, fill_value=0)

        train_result = pd.concat([train_result.drop(columns=[col]), train_dummies], axis=1)
        test_result = pd.concat([test_result.drop(columns=[col]), test_dummies], axis=1)
        all_dummy_columns.extend(train_dummies.columns.tolist())

    return train_result, test_result, all_dummy_columns


def run_and_print(label: str, train_df, test_df, feature_columns: list[str]) -> dict:
    print(f"\n{'=' * 90}\n{label} -- {len(feature_columns)} đặc trưng\n{'=' * 90}")

    single_result = evaluate_single_learning(train_df, test_df, label_column=LABEL_COLUMN, feature_columns=feature_columns)
    distance_result = evaluate_distance(train_df, test_df, label_column=LABEL_COLUMN, feature_columns=feature_columns)
    ensemble_result = evaluate_ensemble(train_df, test_df, label_column=LABEL_COLUMN, feature_columns=feature_columns)

    print("\n--- 1) SINGLE LEARNING-BASED ---")
    print(f"Test accuracy: {single_result['test_accuracy']:.4f} | Baseline: {single_result['baseline']:.4f} | "
          f"Chênh lệch: {(single_result['test_accuracy'] - single_result['baseline']) * 100:+.2f} điểm %")
    _print_report_table(single_result["report"], single_result["class_names"])

    print("\n--- 2) DISTANCE-BASED (N13) ---")
    print(f"Agreement rate: {distance_result['agreement_rate']:.4f} | Baseline: {distance_result['baseline']:.4f} | "
          f"Chênh lệch: {(distance_result['agreement_rate'] - distance_result['baseline']) * 100:+.2f} điểm %")
    _print_report_table(distance_result["report"], distance_result["class_names"])

    print("\n--- 3) ENSEMBLE-BASED (N29) ---")
    for name, acc in ensemble_result["per_classifier_test_accuracy"].items():
        print(f"  {name:<20} accuracy={acc:.4f}  chênh baseline {(acc - ensemble_result['baseline']) * 100:+.2f} điểm %")
    print(f"Majority-vote: {ensemble_result['majority_vote_accuracy']:.4f} | Baseline: {ensemble_result['baseline']:.4f} | "
          f"Chênh lệch: {(ensemble_result['majority_vote_accuracy'] - ensemble_result['baseline']) * 100:+.2f} điểm %")
    _print_report_table(ensemble_result["report"], ensemble_result["class_names"])

    return dict(single=single_result, distance=distance_result, ensemble=ensemble_result)


def main() -> None:
    df = load_data(DATA_PATH)
    train_df, test_df = train_test_split(df, test_size=0.2, random_state=42, stratify=df[LABEL_COLUMN])
    print(f"Train: {len(train_df):,} dòng | Test: {len(test_df):,} dòng")

    # --- (A) CHỈ 6 cột số -- preprocess y hệt evaluate_class_noise_richer_datasets.py ---
    train_numeric, test_numeric = preprocess(train_df, test_df, feature_columns=NUMERIC_COLUMNS)
    results_a = run_and_print("(A) CHỈ CỘT SỐ (6 cột)", train_numeric, test_numeric, NUMERIC_COLUMNS)

    # --- (B) 6 cột số + 8 cột chữ one-hot (fit trên train, apply cho test) ---
    train_full, test_full, dummy_columns = fit_transform_categorical(train_df, test_df, CATEGORICAL_COLUMNS)
    train_full, test_full = preprocess(train_full, test_full, feature_columns=NUMERIC_COLUMNS)  # chỉ cap/log cột số gốc
    feature_columns_b = NUMERIC_COLUMNS + dummy_columns
    results_b = run_and_print(f"(B) SỐ + CHỮ ({len(dummy_columns)} cột one-hot từ 8 cột chữ)", train_full, test_full, feature_columns_b)

    # --- Bảng so sánh tổng kết ---
    print(f"\n\n{'=' * 90}\nBẢNG SO SÁNH (A) CHỈ SỐ  vs  (B) SỐ + CHỮ\n{'=' * 90}")
    rows = [
        ("Single learning", "test_accuracy", "baseline", "single"),
        ("Distance-based (N13)", "agreement_rate", "baseline", "distance"),
        ("Ensemble (majority vote)", "majority_vote_accuracy", "baseline", "ensemble"),
    ]
    print(f"{'Phương pháp':<28} {'Δ baseline (A)':>16} {'Δ baseline (B)':>16} {'Thay đổi':>12}")
    for label, acc_key, base_key, result_key in rows:
        a = results_a[result_key]
        b = results_b[result_key]
        delta_a = (a[acc_key] - a[base_key]) * 100
        delta_b = (b[acc_key] - b[base_key]) * 100
        print(f"{label:<28} {delta_a:>+15.2f}% {delta_b:>+15.2f}% {delta_b - delta_a:>+11.2f}pp")

    print("\nF1 lớp '>50K' (A) vs (B):")
    for label, result_key in [("Single learning", "single"), ("Distance-based", "distance"), ("Ensemble", "ensemble")]:
        f1_a = results_a[result_key]["report"][">50K"]["f1-score"]
        f1_b = results_b[result_key]["report"][">50K"]["f1-score"]
        print(f"  {label:<20} {f1_a:.4f} -> {f1_b:.4f}  ({f1_b - f1_a:+.4f})")


if __name__ == "__main__":
    main()
