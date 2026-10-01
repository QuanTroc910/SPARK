"""
So sanh thuat toan Confident Learning (dung LAI module class_noise/ that, khong
sua gi) tren 2 bo du lieu Kaggle (tai ve qua GitHub mirror, vi Kaggle.com bi
chan boi proxy cua moi truong nay) -- xem co cho ket qua TOT HON bo du lieu
thay cung cap khong, hay van yeu nhu nhau.

1. Credit Card Fraud Detection (ULB/Kaggle) -- 284.807 dong, nhan Class (0/1),
   29 dac trung so (V1..V28 + Amount) -- rat giong cau truc bo du lieu cua
   thay (V44/V12/V4), nhung NHIEU dac trung hon han (29 vs 3).
2. Adult Census Income (UCI/Kaggle) -- 32.561 dong, nhan income (<=50K/>50K),
   6 dac trung so (age, fnlwgt, education.num, capital.gain, capital.loss,
   hours.per.week).
"""
from attribute_noise.pipeline import load_data
from class_noise.config import ClassNoiseConfig
from class_noise.confident_learning import detect_class_noise


def chay_va_in(ten_bo, file_path, label_column, feature_columns, n_estimators=200):
    print("=" * 70)
    print(f"BO DU LIEU: {ten_bo}")
    print("=" * 70)
    df = load_data(file_path)
    config = ClassNoiseConfig(
        label_column=label_column, feature_columns=feature_columns, n_estimators=n_estimators
    )
    print(f"So dong: {len(df)}  |  So dac trung: {len(feature_columns)}  |  n_estimators={n_estimators}")
    result = detect_class_noise(df, config)
    diag = result.diagnostics

    print(f"Cac lop: {diag.class_names}  |  So luong: {diag.class_counts}")
    print(f"CV accuracy (argmax): {diag.cv_accuracy:.4f}")
    print(f"Baseline (lop da so): {diag.majority_baseline_accuracy:.4f}")
    print(f"Chenh lech: {diag.cv_accuracy - diag.majority_baseline_accuracy:+.4f}")
    print()
    print("Precision/Recall/F1 tung lop:")
    for cls in diag.class_names:
        r = diag.per_class_report[cls]
        print(f"  {cls:<8} precision={r['precision']:.3f}  recall={r['recall']:.3f}  f1={r['f1-score']:.3f}  (n={int(r['support'])})")
    print()
    print(f"So dong bi gan co nghi ngo: {len(result.findings)} / {diag.n_rows_used} ({len(result.findings)/diag.n_rows_used:.2%})")
    print()
    return diag


# ===== Bo 1: Credit Card Fraud =====
v_cols = [f"V{i}" for i in range(1, 29)] + ["Amount"]
diag1 = chay_va_in(
    "Credit Card Fraud Detection (Kaggle/ULB)",
    "data/kaggle_creditcard_fraud.csv",
    label_column="Class",
    feature_columns=v_cols,
)

# ===== Bo 2: Adult Census Income =====
diag2 = chay_va_in(
    "Adult Census Income (Kaggle/UCI)",
    "data/kaggle_adult_income.csv",
    label_column="income",
    feature_columns=["age", "fnlwgt", "education.num", "capital.gain", "capital.loss", "hours.per.week"],
)

print("=" * 70)
print("TOM TAT SO SANH")
print("=" * 70)
print(f"{'Bo du lieu':<35} {'Accuracy':>10} {'Baseline':>10} {'Chenh lech':>12}")
print(f"{'Credit Card Fraud':<35} {diag1.cv_accuracy:>10.4f} {diag1.majority_baseline_accuracy:>10.4f} {diag1.cv_accuracy-diag1.majority_baseline_accuracy:>+12.4f}")
print(f"{'Adult Census Income':<35} {diag2.cv_accuracy:>10.4f} {diag2.majority_baseline_accuracy:>10.4f} {diag2.cv_accuracy-diag2.majority_baseline_accuracy:>+12.4f}")
print(f"{'(Du lieu thay cho, da biet)':<35} {0.9723:>10.4f} {0.9745:>10.4f} {0.9723-0.9745:>+12.4f}")
