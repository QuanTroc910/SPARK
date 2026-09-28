"""
Script test CLI cho class_noise/ -- chạy Confident Learning (Random Forest +
5-fold CV) trên bộ dữ liệu train thật thầy cung cấp (data/class_noise_train.csv),
KHÔNG phải sản phẩm cuối, giống vai trò của demo.py với attribute_noise/.

Bài toán: cột "V153" (Yes/No) là NHÃN, 3 cột số "V44", "V12", "V4" là ĐẶC TRƯNG.
"""

from attribute_noise.pipeline import load_data
from class_noise.config import ClassNoiseConfig
from class_noise.confident_learning import detect_class_noise

pd_display_rows = 15

df = load_data("data/class_noise_train.csv")

config = ClassNoiseConfig(
    label_column="V153",
    feature_columns=["V44", "V12", "V4"],
)

print("Đang train Random Forest qua 5-fold CV trên", len(df), "dòng... (có thể mất vài phút)")
result = detect_class_noise(df, config)
diag = result.diagnostics

print()
print("=" * 70)
print("CHẨN ĐOÁN ĐỘ TIN CẬY (xem trước khi tin bất kỳ finding nào)")
print("=" * 70)
print(f"Số dòng tổng:        {diag.n_rows_total}")
print(f"Số dòng dùng được:   {diag.n_rows_used}")
print(f"Các lớp:             {diag.class_names}")
print(f"Số lượng mỗi lớp:    {diag.class_counts}")
print()
print(f"CV accuracy (argmax): {diag.cv_accuracy:.4f}")
print(f"Baseline (đoán bừa lớp đa số): {diag.majority_baseline_accuracy:.4f}")
if diag.cv_accuracy <= diag.majority_baseline_accuracy + 0.02:
    print("!! CẢNH BÁO: accuracy gần sát baseline -- model gần như KHÔNG học được gì")
    print("   từ feature_columns hiện tại. Các finding bên dưới RẤT KHÔNG đáng tin.")
else:
    print(f"-> Model học được thêm {diag.cv_accuracy - diag.majority_baseline_accuracy:.4f} so với baseline.")

print()
print("Precision / Recall / F1 riêng từng lớp (từ argmax, CHƯA qua lọc ngưỡng CL):")
for cls in diag.class_names:
    r = diag.per_class_report[cls]
    print(f"  {cls:<6} precision={r['precision']:.3f}  recall={r['recall']:.3f}  f1={r['f1-score']:.3f}  (n={int(r['support'])})")

print()
print("Ngưỡng tự tin riêng từng lớp (bước 2 Confident Learning):")
for cls, t in diag.class_thresholds.items():
    print(f"  {cls:<6} ngưỡng = {t:.3f}")

print()
print("Ma trận đếm (hàng = nhãn GHI, cột = nhãn model TỰ TIN):")
print(diag.confusion_count_matrix)

print()
print("=" * 70)
print(f"TỔNG SỐ DÒNG BỊ GẮN CỜ NGHI NGỜ SAI NHÃN: {len(result.findings)} / {diag.n_rows_used}")
print("=" * 70)

print()
print(f"Top {pd_display_rows} dòng đáng ngờ NHẤT (margin cao nhất):")
print(f"{'row_number':>10}  {'nhãn ghi':<10} {'model tự tin':<14} {'margin':>8}")
for f in result.findings[:pd_display_rows]:
    print(f"{f.row_number:>10}  {f.recorded_label:<10} {f.confident_label:<14} {f.margin:>8.4f}")
