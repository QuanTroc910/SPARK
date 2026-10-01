"""
THI NGHIEM CO DOI CHUNG: giu NGUYEN bo Credit Card Fraud (284.807 dong, cung
nhan Class, cung do mat can bang) -- CHI doi DUY NHAT 1 bien: so dac trung
(29 -> 3), de tach rieng xem "it dac trung" tu no da du lam recall tut
manh hay khong, khong bi lan voi viec "doi sang bo du lieu khac".

3 cot duoc chon NGAU NHIEN (khong chon loc theo do quan trong) de mo phong
dung tinh huong "duoc giao san 3 cot bat ky" giong bo du lieu cua thay.
"""
from attribute_noise.pipeline import load_data
from class_noise.config import ClassNoiseConfig
from class_noise.confident_learning import detect_class_noise

df = load_data("data/kaggle_creditcard_fraud.csv")

configs = [
    ("3 cot ngau nhien (V11, V5, V13)", ["V11", "V5", "V13"]),
    ("Toan bo 29 cot (doi chung)", [f"V{i}" for i in range(1, 29)] + ["Amount"]),
]

ket_qua = []
for ten, cols in configs:
    print("=" * 70)
    print(f"CAU HINH: {ten}  ({len(cols)} dac trung)")
    print("=" * 70)
    config = ClassNoiseConfig(label_column="Class", feature_columns=cols, n_estimators=200)
    result = detect_class_noise(df, config)
    diag = result.diagnostics
    print(f"CV accuracy: {diag.cv_accuracy:.4f}  |  Baseline: {diag.majority_baseline_accuracy:.4f}  |  Chenh lech: {diag.cv_accuracy-diag.majority_baseline_accuracy:+.4f}")
    r = diag.per_class_report["1"]
    print(f"Lop 1 (fraud): precision={r['precision']:.3f}  recall={r['recall']:.3f}  f1={r['f1-score']:.3f}")
    print(f"So dong bi gan co nghi ngo: {len(result.findings)} / {diag.n_rows_used}")
    ket_qua.append((ten, len(cols), diag.cv_accuracy, diag.majority_baseline_accuracy, r['precision'], r['recall']))
    print()

print("=" * 70)
print("TOM TAT -- CUNG 1 BO DU LIEU (284.807 dong, cung nhan Class), CHI doi so cot")
print("=" * 70)
print(f"{'Cau hinh':<35} {'So cot':>7} {'Accuracy':>10} {'Baseline':>10} {'Precision':>10} {'Recall':>8}")
for ten, n, acc, base, prec, rec in ket_qua:
    print(f"{ten:<35} {n:>7} {acc:>10.4f} {base:>10.4f} {prec:>10.3f} {rec:>8.3f}")
