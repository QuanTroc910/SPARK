"""Thực nghiệm attribute noise trên Hospital (mục 4.3): ba công cụ qua đúng các hàm mà route của ứng dụng gọi;
phụ thuộc hàm lấy các ràng buộc một cột xác định trong data/benchmarks/hospital_constraints.txt của HoloClean,
gộp theo cột xác định.    python experiments/attribute_hospital.py"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd
from _common import load_attr_benchmark, cell_score
import app as A
from attribute_noise.quick_tools import auto_column_types, find_format_errors

df, clean, truth = load_attr_benchmark("hospital")
print("Hospital:", len(df), "dòng,", int(truth.values.sum()), "ô lỗi")
flag = {}
types = auto_column_types(df)
flag["Sai định dạng, kiểu tự đoán"] = find_format_errors(df, types).reindex(columns=df.columns, fill_value=False)
cat_cols = ["city", "state", "county", "type", "owner", "emergency_service", "condition", "measure_code"]
def inconsistent(valid):
    _, _, fs, _, _ = A._run_config_tool_detect(df, {"tool": "inconsistent-category", "items": [
        {"column": c, "dtype": "category", "params": {"valid_categories": valid[c]}} for c in cat_cols]})
    m = pd.DataFrame(False, index=df.index, columns=df.columns)
    for f in fs: m.loc[int(f.row_index), f.column] = True
    return m
# giá trị chuẩn = mọi giá trị xuất hiện từ 3 lần trở lên (mô phỏng người dùng chọn từ các giá trị phổ biến)
flag["Không nhất quán (8 cột phân loại)"] = inconsistent({c: [v for v, k in df[c].value_counts().items() if k >= 3] for c in cat_cols})
# 13 ràng buộc một cột xác định của HoloClean, gộp thành 6 khai báo theo cột xác định
fd_rules = [("provider_number", ["name"]),
            ("name", ["zip", "phone", "address_1", "owner", "provider_number", "city"]),
            ("measure_code", ["measure_name", "state_average", "condition"]),
            ("city", ["county"]), ("zip", ["emergency_service"]), ("measure_name", ["measure_code"])]
m = pd.DataFrame(False, index=df.index, columns=df.columns); fixes = {}
for det, deps in fd_rules:
    _, rules, _, _, _ = A._run_config_tool_detect(df, {"tool": "cross-rule", "rule": {
        "rule_type": "functional_dependency", "determinant_column": det, "dependent_columns": deps}})
    an = A._fd_analyses(df, rules); cells, _ = A._fd_cell_info(an)
    for r, info in cells.items():
        for c in info["flagged"]: m.loc[int(r), c] = True
    fixes.update(A._fd_plan(an)["fixes"])
flag["Phụ thuộc hàm (13 ràng buộc của HoloClean, 6 khai báo)"] = m
for k, v in flag.items(): cell_score(v, truth, k)
allm = flag["Sai định dạng, kiểu tự đoán"] | flag["Không nhất quán (8 cột phân loại)"] | m
cell_score(allm, truth, "Hợp ba công cụ")
ok = sum(1 for (r, c), v in fixes.items() if v == clean.loc[r, c])
print(f"\nSửa về giá trị phổ biến nhất: đề xuất {len(fixes)} ô, {ok} ô trở về đúng giá trị của bản sạch")
print("\nTheo cột: ô lỗi | Sai định dạng | Không nhất quán | Phụ thuộc hàm | hợp | báo nhầm")
for c in df.columns:
    t = int(truth[c].sum())
    if t:
        f = lambda k: int((flag[k][c] & truth[c]).sum())
        print(f"  {c:18s} {t:4d} {f('Sai định dạng, kiểu tự đoán'):4d} {f('Không nhất quán (8 cột phân loại)'):4d} "
              f"{int((m[c] & truth[c]).sum()):4d} {int((allm[c] & truth[c]).sum()):4d} {int((allm[c] & ~truth[c]).sum()):4d}")
oracle = inconsistent({c: sorted(set(clean[c]) - {""}) for c in cat_cols})
print("\nKhông nhất quán khi giá trị chuẩn lấy từ bản sạch:", int((oracle & truth).values.sum()), "ô đúng /", int(oracle.values.sum()), "ô gắn cờ")
