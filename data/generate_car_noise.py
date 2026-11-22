"""
Chuẩn hoá bộ Car Evaluation (UCI) về SỐ + cấy nhiễu nhãn CÓ KIỂM SOÁT (5% và 10%).

Chạy:  python3 data/generate_car_noise.py        (hạt giống cố định -> luôn ra đúng cùng file)

Đầu vào : data/car.data  (1728 dòng, không có dòng tiêu đề, 6 đặc trưng chữ + nhãn chữ)
Đầu ra  : data/car_clean.csv              bộ đã chuẩn hoá về số (nhãn gốc, sạch)
          data/car_noisy_5.csv            bản cấy 5% nhiễu nhãn  (86 dòng)
          data/car_noisy_10.csv           bản cấy 10% nhiễu nhãn (173 dòng)
          data/car_noise_ground_truth.csv đáp án: dòng nào bị cấy, nhãn gốc -> nhãn mới
          data/car_noisy_highlight.xlsx   bản Excel tô màu vàng ô nhãn của dòng bị cấy + bảng mã hoá

Cách mã hoá: TẤT CẢ cột trong bộ này đều có THỨ TỰ sẵn (ordinal) nên mã hoá theo đúng thứ tự đó,
không dùng mã tuỳ ý (không dùng one-hot, vì sẽ làm mất thứ tự và phình cột).

Cách cấy nhiễu (nhiễu nhãn, "cấy có kiểm soát"): chọn ngẫu nhiên các dòng rồi ĐỔI nhãn của chúng
sang một nhãn KHÁC, chọn đều ngẫu nhiên trong 3 nhãn còn lại. Hai mức dùng CHUNG 1 thứ tự xáo
trộn nên các dòng của mức 5% nằm trọn trong mức 10% và đổi sang đúng cùng nhãn mới. Chỉ cột nhãn
bị đổi, các cột đặc trưng giữ nguyên.
"""
import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font

SEED = 42
COLS = ["buying", "maint", "doors", "persons", "lug_boot", "safety", "class"]

# Thứ tự thấp -> cao của từng cột (khớp tài liệu UCI Car Evaluation)
ENCODING = {
    "buying":   {"low": 1, "med": 2, "high": 3, "vhigh": 4},      # giá mua
    "maint":    {"low": 1, "med": 2, "high": 3, "vhigh": 4},      # chi phí bảo dưỡng
    "doors":    {"2": 2, "3": 3, "4": 4, "5more": 5},             # số cửa (5more = 5 trở lên)
    "persons":  {"2": 2, "4": 4, "more": 6},                      # số chỗ ngồi (more = hơn 4 -> 6, cách đều)
    "lug_boot": {"small": 1, "med": 2, "big": 3},                 # cốp xe
    "safety":   {"low": 1, "med": 2, "high": 3},                  # độ an toàn
    "class":    {"unacc": 0, "acc": 1, "good": 2, "vgood": 3},    # nhãn: mức chấp nhận được
}
CLASS_NAME = {v: k for k, v in ENCODING["class"].items()}

raw = pd.read_csv("data/car.data", header=None, names=COLS, dtype=str)
clean = raw.copy()
for col, mapping in ENCODING.items():
    clean[col] = raw[col].map(mapping)
    if clean[col].isna().any():
        raise SystemExit(f"Cột {col} có giá trị chưa có trong bảng mã hoá: {sorted(raw.loc[clean[col].isna(), col].unique())}")
clean = clean.astype(int)
n = len(clean)

rng = np.random.default_rng(SEED)
order = rng.permutation(n)
n5, n10 = int(round(0.05 * n)), int(round(0.10 * n))
rows10 = order[:n10]
rows5 = order[:n5]                      # nằm trọn trong rows10
orig = clean["class"].to_numpy()
new_label = orig.copy()
new_label[rows10] = (orig[rows10] + rng.integers(1, 4, size=n10)) % 4   # luôn KHÁC nhãn gốc

def make_noisy(rows):
    d = clean.copy()
    d.loc[rows, "class"] = new_label[rows]
    return d

noisy5, noisy10 = make_noisy(rows5), make_noisy(rows10)

# Đáp án: row_number tính 1-based theo dòng DỮ LIỆU (không tính dòng tiêu đề) -- khớp cách web đếm dòng.
# excel_row = số dòng khi mở bằng Excel (dòng 1 là tiêu đề nên = row_number + 1).
rows10_sorted = np.sort(rows10)
in5 = set(int(i) for i in rows5)
truth = pd.DataFrame({
    "row_number": rows10_sorted + 1,
    "excel_row": rows10_sorted + 2,
    "original_class": orig[rows10_sorted],
    "noisy_class": new_label[rows10_sorted],
    "original_class_name": [CLASS_NAME[v] for v in orig[rows10_sorted]],
    "noisy_class_name": [CLASS_NAME[v] for v in new_label[rows10_sorted]],
    "in_5pct": [1 if int(i) in in5 else 0 for i in rows10_sorted],
    "in_10pct": 1,
})

clean.to_csv("data/car_clean.csv", index=False)
noisy5.to_csv("data/car_noisy_5.csv", index=False)
noisy10.to_csv("data/car_noisy_10.csv", index=False)
truth.to_csv("data/car_noise_ground_truth.csv", index=False)

# --- Excel: tô vàng ô nhãn của dòng bị cấy ---
yellow = PatternFill("solid", fgColor="FFE066")
bold = Font(bold=True)
wb = Workbook()
wb.remove(wb.active)
for title, df, rows in (("Cay 5%", noisy5, rows5), ("Cay 10%", noisy10, rows10)):
    ws = wb.create_sheet(title)
    ws.append(list(df.columns))
    for c in ws[1]:
        c.font = bold
    for rec in df.itertuples(index=False):
        ws.append(list(rec))
    class_col = list(df.columns).index("class") + 1
    for i in rows:
        ws.cell(row=int(i) + 2, column=class_col).fill = yellow
ws = wb.create_sheet("Bang ma hoa")
ws.append(["cot", "gia tri goc", "ma so"])
for c in ws[1]:
    c.font = bold
for col, mapping in ENCODING.items():
    for k, v in mapping.items():
        ws.append([col, k, v])
wb.save("data/car_noisy_highlight.xlsx")

# --- Kiểm tra lại ---
for name, d, rows in (("5%", noisy5, rows5), ("10%", noisy10, rows10)):
    diff = np.where(d["class"].to_numpy() != orig)[0]
    assert set(diff) == set(int(i) for i in rows), "dòng đổi nhãn không khớp danh sách cấy"
    assert (d.drop(columns="class") == clean.drop(columns="class")).all().all(), "cột đặc trưng bị đổi"
    print(f"Mức {name}: đổi nhãn {len(diff)} dòng ({len(diff)/n:.2%}), cột đặc trưng giữ nguyên.")
assert in5 <= set(int(i) for i in rows10)
print("Phân bố nhãn gốc :", dict(clean['class'].value_counts().sort_index()))
print("Hướng đổi (10%) :")
print(pd.crosstab(truth.original_class_name, truth.noisy_class_name).to_string())
print("Mẫu đáp án:"); print(truth.head(6).to_string(index=False))
