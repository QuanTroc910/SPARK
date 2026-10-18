"""
Lặp lại đánh giá train/test (evaluate_class_noise_richer_datasets.py) cho
Adult Income + Credit Card Fraud, nhưng lần này CÓ chạy Bước 1+2 của pipeline
giảm cột (class_noise/feature_selection.py -- rank_by_importance() +
select_by_elbow() + filter_correlated()) TRƯỚC khi detect, để so sánh với
kết quả "giữ nguyên toàn bộ cột" đã có từ evaluate_class_noise_richer_datasets.py.

QUAN TRỌNG -- fit Bước 1+2 CHỈ TRÊN TRAIN (không phải cả df gốc như
`POST /api/class-noise/reduce-features` làm trên web, vì web không có khái
niệm train/test): tránh để tập test "rò rỉ" vào lúc quyết định giữ cột nào,
giống đúng lý do tách fit/apply ở preprocess() (cap_outliers/log_transform).
Áp dụng ĐÚNG danh sách cột đã chọn từ train lên CẢ train lẫn test khi detect.

Chạy: python3 evaluate_class_noise_reduced_features.py
"""

import time

from sklearn.model_selection import train_test_split

from attribute_noise.pipeline import load_data
from class_noise.feature_selection import filter_correlated, rank_by_importance, select_by_elbow
from evaluate_class_noise_train_test import (
    _print_confusion,
    _print_report_table,
    evaluate_distance,
    evaluate_ensemble,
    evaluate_single_learning,
    preprocess,
)

DATASETS = [
    {
        "name": "Adult Income",
        "path": "data/kaggle_adult_income.csv",
        "label_column": "income",
        "candidate_columns": ["age", "fnlwgt", "education.num", "capital.gain", "capital.loss", "hours.per.week"],
    },
    {
        "name": "Credit Card Fraud",
        "path": "data/kaggle_creditcard_fraud.csv",
        "label_column": "Class",
        "candidate_columns": [f"V{i}" for i in range(1, 29)] + ["Amount"],
    },
]


def run_one_dataset(name: str, path: str, label_column: str, candidate_columns: list[str]) -> None:
    print("\n" + "#" * 90)
    print(f"# BỘ DỮ LIỆU: {name}  ({path}) -- CÓ giảm cột (Bước 1+2)")
    print("#" * 90)

    df = load_data(path)
    train_df, test_df = train_test_split(
        df, test_size=0.2, random_state=42, stratify=df[label_column]
    )
    print(f"Candidate ban đầu: {len(candidate_columns)} cột -- {candidate_columns}")

    # --- Bước 1: xếp hạng theo importance, CHỈ fit trên TRAIN ---
    ranked = rank_by_importance(train_df, label_column, candidate_columns)
    print("\nBước 1 -- xếp hạng importance (giảm dần, fit trên train):")
    for r in ranked:
        print(f"  {r.column:<16} importance={r.importance:.4f}")

    elbow_cols = select_by_elbow(ranked)
    print(f"\nSau Elbow Method: giữ {len(elbow_cols)}/{len(ranked)} cột -- {elbow_cols}")

    # --- Bước 2: lọc tương quan, CHỈ fit trên TRAIN ---
    final_cols = filter_correlated(train_df, elbow_cols)
    print(f"Sau lọc tương quan (>=0.8): giữ {len(final_cols)}/{len(elbow_cols)} cột -- {final_cols}")
    print(f"\n==> TỔNG: {len(candidate_columns)} cột gốc -> {len(elbow_cols)} cột (Bước 1) -> {len(final_cols)} cột (Bước 2)")

    feature_columns = final_cols
    print(f"\nTrain: {len(train_df):,} dòng | Test: {len(test_df):,} dòng | Đặc trưng dùng để detect: {feature_columns}")
    print()

    train_clean, test_clean = preprocess(train_df, test_df, feature_columns=feature_columns)

    t0 = time.time()
    single_result = evaluate_single_learning(train_clean, test_clean, label_column=label_column, feature_columns=feature_columns)
    print()
    distance_result = evaluate_distance(train_clean, test_clean, label_column=label_column, feature_columns=feature_columns)
    print()
    ensemble_result = evaluate_ensemble(train_clean, test_clean, label_column=label_column, feature_columns=feature_columns)
    t1 = time.time()

    print("\n" + "=" * 90)
    print(f"TỔNG HỢP (ĐÃ GIẢM CỘT) -- {name} -- {len(feature_columns)} đặc trưng, "
          f"train={len(train_clean):,}, test={len(test_clean):,} (tổng thời gian: {t1 - t0:.1f}s)")
    print("=" * 90)

    print("\n--- 1) SINGLE LEARNING-BASED ---")
    print(f"Test accuracy: {single_result['test_accuracy']:.4f} ({single_result['test_accuracy']:.2%})")
    print(f"Baseline: {single_result['baseline']:.4f} ({single_result['baseline']:.2%})")
    print(f"Chênh lệch so baseline: {(single_result['test_accuracy'] - single_result['baseline']) * 100:+.2f} điểm %")
    print(f"Số dòng test bị gắn cờ: {len(single_result['flagged_row_numbers']):,} "
          f"({len(single_result['flagged_row_numbers']) / single_result['n_test']:.2%})")
    _print_report_table(single_result["report"], single_result["class_names"])
    _print_confusion(single_result["confusion_matrix"], single_result["class_names"], "nhãn ghi (test)")

    print("\n\n--- 2) DISTANCE-BASED (N13) ---")
    print(f"Agreement rate: {distance_result['agreement_rate']:.4f} ({distance_result['agreement_rate']:.2%})")
    print(f"Baseline: {distance_result['baseline']:.4f} ({distance_result['baseline']:.2%})")
    print(f"Chênh lệch so baseline: {(distance_result['agreement_rate'] - distance_result['baseline']) * 100:+.2f} điểm %")
    print(f"Số dòng test bị gắn cờ: {len(distance_result['flagged_row_numbers']):,} "
          f"({len(distance_result['flagged_row_numbers']) / distance_result['n_test']:.2%})")
    _print_report_table(distance_result["report"], distance_result["class_names"])
    _print_confusion(distance_result["confusion_matrix"], distance_result["class_names"], "nhãn ghi (test)")

    print("\n\n--- 3) ENSEMBLE-BASED (N29) ---")
    for clf_name, acc in ensemble_result["per_classifier_test_accuracy"].items():
        print(f"  {clf_name:<20} accuracy(test) = {acc:.4f} ({acc:.2%}), chênh baseline "
              f"{(acc - ensemble_result['baseline']) * 100:+.2f} điểm %")
    print(f"Majority-vote accuracy: {ensemble_result['majority_vote_accuracy']:.4f} "
          f"({ensemble_result['majority_vote_accuracy']:.2%})")
    print(f"Baseline: {ensemble_result['baseline']:.4f} ({ensemble_result['baseline']:.2%})")
    print(f"Chênh lệch so baseline: "
          f"{(ensemble_result['majority_vote_accuracy'] - ensemble_result['baseline']) * 100:+.2f} điểm %")
    print(f"Số dòng test bị gắn cờ: {len(ensemble_result['flagged_row_numbers']):,} "
          f"({len(ensemble_result['flagged_row_numbers']) / ensemble_result['n_test']:.2%})")
    _print_report_table(ensemble_result["report"], ensemble_result["class_names"])
    _print_confusion(ensemble_result["confusion_matrix"], ensemble_result["class_names"], "nhãn ghi (test)")

    print("\n\n--- SO SÁNH mức độ trùng các dòng bị gắn cờ trên TEST ---")
    sl, db, en = single_result["flagged_row_numbers"], distance_result["flagged_row_numbers"], ensemble_result["flagged_row_numbers"]
    print(f"Single: {len(sl):,} | Distance: {len(db):,} | Ensemble: {len(en):,}")
    print(f"Single ∩ Distance: {len(sl & db):,} | Single ∩ Ensemble: {len(sl & en):,} | Distance ∩ Ensemble: {len(db & en):,}")
    print(f"Cả 3 cùng gắn cờ: {len(sl & db & en):,} | Hợp (>=1 phương pháp): {len(sl | db | en):,}")


def main() -> None:
    for cfg in DATASETS:
        run_one_dataset(cfg["name"], cfg["path"], cfg["label_column"], cfg["candidate_columns"])


if __name__ == "__main__":
    main()
