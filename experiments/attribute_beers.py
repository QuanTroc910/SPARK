"""Thực nghiệm attribute noise trên Beers (mục 4.3): chạy các công cụ qua đúng các hàm mà route của ứng dụng gọi,
so từng ô với bản sạch.    python experiments/attribute_beers.py"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd
from _common import load_attr_benchmark, cell_score
import app as A
from attribute_noise.quick_tools import auto_column_types, find_format_errors, blank_mask

df, clean, truth = load_attr_benchmark("beers")
print("Beers:", len(df), "dòng,", int(truth.values.sum()), "ô lỗi")
flag = {}
auto = auto_column_types(df)
print("kiểu tự đoán:", {k: v["dtype"] for k, v in auto.items()})
flag["Sai định dạng, kiểu tự đoán"] = find_format_errors(df, auto).reindex(columns=df.columns, fill_value=False)
fixed = dict(auto); fixed.update({c: {"dtype": "float"} for c in ["ounces", "abv", "ibu"]})
flag["Sai định dạng, ounces/abv/ibu đổi sang số thực"] = find_format_errors(df, fixed).reindex(columns=df.columns, fill_value=False)
flag["Ô trống"] = blank_mask(df).reindex(columns=df.columns, fill_value=False)
# Không nhất quán: giá trị chuẩn = mọi giá trị xuất hiện từ 3 lần trở lên (mô phỏng người dùng chọn từ các giá trị phổ biến)
cat_cols = ["city", "state"]
vc = {c: [v for v, k in df[c].value_counts().items() if k >= 3 and v != ""] for c in cat_cols}
_, _, fs, _, _ = A._run_config_tool_detect(df, {"tool": "inconsistent-category", "items": [
    {"column": c, "dtype": "category", "params": {"valid_categories": vc[c]}} for c in cat_cols]})
m = pd.DataFrame(False, index=df.index, columns=df.columns)
for f in fs: m.loc[int(f.row_index), f.column] = True
flag["Không nhất quán (city, state)"] = m
cfg = {"tool": "cross-rule", "rule": {"rule_type": "functional_dependency", "determinant_column": "brewery_id",
                                      "dependent_columns": ["brewery_name", "city", "state"]}}
_, rules, _, _, _ = A._run_config_tool_detect(df, cfg)
cells, _ = A._fd_cell_info(A._fd_analyses(df, rules))
m = pd.DataFrame(False, index=df.index, columns=df.columns)
for r, info in cells.items():
    for c in info["flagged"]: m.loc[int(r), c] = True
flag["Phụ thuộc hàm brewery_id -> brewery_name, city, state"] = m
for k, v in flag.items(): cell_score(v, truth, k)
keys = list(flag)
cell_score(flag[keys[0]] | flag[keys[2]] | flag[keys[3]] | flag[keys[4]], truth, "Hợp bốn công cụ, kiểu tự đoán")
allm = flag[keys[1]] | flag[keys[2]] | flag[keys[3]] | flag[keys[4]]
cell_score(allm, truth, "Hợp bốn công cụ, kiểu đã sửa")
print("\nTheo cột (hợp, kiểu đã sửa): tìm được / ô lỗi, báo nhầm")
for c in df.columns:
    t = int(truth[c].sum())
    if t or allm[c].any(): print(f"  {c:12s} {int((allm[c] & truth[c]).sum()):5d}/{t:5d}   báo nhầm {int((allm[c] & ~truth[c]).sum())}")
