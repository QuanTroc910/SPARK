"""
Chạy lại ĐÚNG khuôn đánh giá TRAIN/TEST vừa dùng cho dữ liệu thầy
(evaluate_class_noise_train_test.py) nhưng trên 2 bộ dữ liệu "giàu đặc
trưng" hơn hẳn (Adult Income: 6 đặc trưng số; Credit Card Fraud: 29 đặc
trưng số) -- để kiểm chứng: liệu kết quả yếu (cả 3 thuật toán không vượt
baseline) trên dữ liệu thầy là do ĐẶC TRƯNG quá ít (chỉ 3 cột), hay là lỗi/
hạn chế chung của CÁCH đánh giá/3 thuật toán.

KHÁC dữ liệu thầy (đã có sẵn 2 file train/test riêng do thầy cung cấp):
Adult Income và Credit Card Fraud chỉ có 1 file duy nhất -- tự chia TRAIN/
TEST 80/20 bằng `train_test_split(..., stratify=y)` (giữ đúng tỉ lệ lớp ở
cả 2 phần, quan trọng với Credit Card Fraud vì lớp "1" (fraud) cực hiếm,
chỉ 492/284.807 = 0.17%).

Tái dùng NGUYÊN VẸN các hàm đã viết ở evaluate_class_noise_train_test.py
(fit_cap_bounds/apply_cap/apply_log1p/preprocess/evaluate_single_learning/
evaluate_distance/evaluate_ensemble) -- không viết lại lần 2, chỉ đổi
label_column/feature_columns truyền vào.

Chạy: python3 evaluate_class_noise_richer_datasets.py
"""

import time

from sklearn.model_selection import train_test_split

from attribute_noise.pipeline import load_data
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
        "feature_columns": ["age", "fnlwgt", "education.num", "capital.gain", "capital.loss", "hours.per.week"],
    },
    {
        "name": "Credit Card Fraud",
        "path": "data/kaggle_creditcard_fraud.csv",
        "label_column": "Class",
        # 28 thành phần PCA (V1-V28) + Amount -- bỏ "Time" (chỉ là mốc thời
        # gian giao dịch, không mang ý nghĩa đặc trưng dự đoán).
        "feature_columns": [f"V{i}" for i in range(1, 29)] + ["Amount"],
    },
]


def run_one_dataset(name: str, path: str, label_column: str, feature_columns: list[str]) -> None:
    print("\n" + "#" * 90)
    print(f"# BỘ DỮ LIỆU: {name}  ({path})")
    print("#" * 90)

    df = load_data(path)
    print(f"Tổng số dòng: {len(df):,} | Số đặc trưng: {len(feature_columns)}")
    print(f"Phân bố nhãn: {dict(df[label_column].value_counts())}")

    # Chia 80/20, stratify theo nhãn để giữ đúng tỉ lệ lớp hiếm ở cả 2 phần.
    train_df, test_df = train_test_split(
        df, test_size=0.2, random_state=42, stratify=df[label_column]
    )
    print(f"Train: {len(train_df):,} dòng | Test: {len(test_df):,} dòng (chia 80/20, stratify theo nhãn)")
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
    print(f"TỔNG HỢP -- {name} -- train={len(train_clean):,}, test={len(test_clean):,} "
          f"(tổng thời gian: {t1 - t0:.1f}s)")
    print("=" * 90)

    print("\n--- 1) SINGLE LEARNING-BASED (Confident Learning + Random Forest) ---")
    print(f"Test accuracy: {single_result['test_accuracy']:.4f} ({single_result['test_accuracy']:.2%})")
    print(f"Baseline: {single_result['baseline']:.4f} ({single_result['baseline']:.2%})")
    print(f"Chênh lệch so baseline: {(single_result['test_accuracy'] - single_result['baseline']) * 100:+.2f} điểm %")
    print(f"Số dòng test bị gắn cờ: {len(single_result['flagged_row_numbers']):,} "
          f"({len(single_result['flagged_row_numbers']) / single_result['n_test']:.2%})")
    _print_report_table(single_result["report"], single_result["class_names"])
    _print_confusion(single_result["confusion_matrix"], single_result["class_names"], "nhãn ghi (test)")

    print("\n\n--- 2) DISTANCE-BASED (Mutual k-NN, N13) ---")
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
        run_one_dataset(cfg["name"], cfg["path"], cfg["label_column"], cfg["feature_columns"])


if __name__ == "__main__":
    main()
