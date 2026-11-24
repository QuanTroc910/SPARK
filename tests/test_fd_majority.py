"""Test cho luật ĐOÁN Ô SAI của phụ thuộc hàm sau khi thêm "ĐA SỐ RÕ RÀNG" (CLAUDE.md mục 51, 24/11/2026).

Chạy:  python3 tests/test_fd_majority.py      (không cần pytest; in "KẾT QUẢ: N đạt, M lỗi", thoát mã 1 nếu có lỗi)

Chỉ kiểm `analyze_functional_dependency` (attribute_noise/cross_field_rules.py) và cách app.py dùng kết quả của nó
(`_fd_plan`, route /api/noise-tools/configured với cách xử lý "Sửa về giá trị phổ biến nhất" / "Chỉ xoá dòng nghi sai").
Phần PHÁT HIỆN nhóm vi phạm không đổi, nên có 1 kiểm tra riêng đối chiếu với `groupby().nunique() > 1` độc lập.

Luật mới: nếu trong cột B của nhóm, giá trị phổ biến nhất xuất hiện >= 2 lần VÀ nhiều hơn hẳn giá trị thứ 2 -> "dependent"
(chỉ ô B lệch bị nghi, không đổ lỗi cho A). Không có đa số rõ ràng thì giữ luật cũ (so các cột còn lại).
"""
import io
import json
import os
import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import accounts.db as db_module  # noqa: E402

db_module.DB_PATH = Path(tempfile.NamedTemporaryFile(suffix=".db", delete=False).name)  # DB tạm, không đụng tài khoản thật

import app as A  # noqa: E402
from attribute_noise.config import CrossFieldRuleConfig, RuleType  # noqa: E402
from attribute_noise.cross_field_rules import (  # noqa: E402
    analyze_functional_dependency,
    detect_functional_dependency_rule,
)

ok = fail = 0


def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
    else:
        fail += 1
        print("  FAIL:", name, extra)


def cfg(det, dep):
    return CrossFieldRuleConfig(rule_type=RuleType.FUNCTIONAL_DEPENDENCY, determinant_column=det, dependent_column=dep)


def flagged_cells(result):
    return {(i, c) for i, info in result["rows"].items() for c in info["flagged"]}


# ---------------------------------------------------------------------------------------------
# Dữ liệu 1 (giống Hospital): mã đo "ami-1" có 10 dòng của 10 bệnh viện KHÁC NHAU.
#   condition = "heart attack" x9 + "hearx axxack" x1 (lỗi gõ cần bắt, ở dòng chỉ số 3)
#   measure_name là cột "ổn định" (đồng nhất ở các mã đo khác) nhưng dòng chỉ số 6 cũng dính 1 lỗi gõ ->
#   luật so cột cũ thấy cột này KHÁC NHAU ở nhóm vi phạm -> kết luận nhầm "nghi sai measure_code, tô cả nhóm".
#   hospital / address khác nhau giữa các dòng ở MỌI nhóm nên không được dùng làm bằng chứng.
# ---------------------------------------------------------------------------------------------
TYPO_ROW = 3
rows1 = []
for i in range(10):
    rows1.append({
        "measure_code": "ami-1",
        "condition": "hearx axxack" if i == TYPO_ROW else "heart attack",
        "measure_name": "aspirin at arrivxl" if i == 6 else "aspirin at arrival",
        "hospital": f"hospital {i}", "address": f"{i} main street",
    })
for code, cond, name, n in (("scip-1", "surgery", "antibiotic on time", 4), ("pn-2", "pneumonia", "vaccine check", 4), ("hf-1", "heart failure", "discharge advice", 3)):
    for j in range(n):
        rows1.append({"measure_code": code, "condition": cond, "measure_name": name, "hospital": f"hosp {code} {j}", "address": f"{j} {code} road"})
df1 = pd.DataFrame(rows1)

res1 = analyze_functional_dependency(df1, cfg("measure_code", "condition"))
check("nhóm lớn có đa số: đúng 1 nhóm vi phạm", len(res1["groups"]) == 1, res1["groups"])
g1 = res1["groups"][0]
check("nhóm lớn có đa số: verdict = dependent (không đổ lỗi cho mã đo)", g1["verdict"] == "dependent", g1["verdict"])
check("chỉ tô ô condition của đúng dòng lỗi", flagged_cells(res1) == {(TYPO_ROW, "condition")}, flagged_cells(res1))
check("KHÔNG tô measure_code ở dòng nào", not any(c == "measure_code" for _, c in flagged_cells(res1)))
check("majority_value = heart attack, suspect_rows = [dòng lỗi]", g1["majority_value"] == "heart attack" and g1["suspect_rows"] == [TYPO_ROW], g1)
notes = " ".join(n for info in res1["rows"].values() for n in info["notes"])
check("câu giải thích nói 'phổ biến rõ ràng' + 'm/n dòng'", "phổ biến rõ ràng" in notes and "9/10 dòng" in notes, notes[:300])
check("câu giải thích không in '0/0'", "0/0" not in notes)

# Phần PHÁT HIỆN nhóm vi phạm không đổi: tập dòng gắn cờ = các dòng thuộc nhóm có > 1 giá trị B khác nhau (tính độc lập bằng pandas).
mask = detect_functional_dependency_rule(df1, cfg("measure_code", "condition"))
expected = df1.groupby("measure_code")["condition"].transform("nunique") > 1
check("detect: cùng tập dòng với tính độc lập bằng pandas", list(mask) == list(expected), (mask.sum(), expected.sum()))

# ---------------------------------------------------------------------------------------------
# Dữ liệu 2: nhân viên. Các mã khác nhau (NV02.. NV04) có nhiều dòng, phong_ban + ngay_sinh đồng nhất -> hai cột này là "ổn định".
# ---------------------------------------------------------------------------------------------
def employees(extra_rows):
    base = [
        ("NV02", "Chi", "KD", "1992-02-02", 11), ("NV02", "Chi", "KD", "1992-02-02", 12), ("NV02", "Chi", "KD", "1992-02-02", 13),
        ("NV03", "Dũng", "KT", "1993-03-03", 21), ("NV03", "Dũng", "KT", "1993-03-03", 22),
        ("NV04", "Em", "NS", "1994-04-04", 31), ("NV04", "Em", "NS", "1994-04-04", 32),
    ]
    return pd.DataFrame(list(extra_rows) + base, columns=["ma_nv", "ten", "phong_ban", "ngay_sinh", "luong"])


# 2) Hai nhân viên KHÁC NHAU trùng mã, mỗi người 1 dòng, các cột khác khác nhau -> không có đa số -> giữ luật cũ: nghi sai mã.
df2 = employees([("NV01", "An", "KT", "1990-01-01", 10), ("NV01", "Bình", "NS", "1985-05-05", 20)])
res2 = analyze_functional_dependency(df2, cfg("ma_nv", "ten"))
check("2 người trùng mã (2 dòng): 1 nhóm, verdict determinant", len(res2["groups"]) == 1 and res2["groups"][0]["verdict"] == "determinant", res2["groups"])
check("2 người trùng mã: tô cột mã ở cả 2 dòng, KHÔNG tô cột tên", flagged_cells(res2) == {(0, "ma_nv"), (1, "ma_nv")}, flagged_cells(res2))
check("2 người trùng mã: không có majority_value", res2["groups"][0]["majority_value"] is None and res2["groups"][0]["suspect_rows"] == [])

# 3) Cùng 1 người, 2 dòng, tên "An" / "Ân", các cột khác giống -> hoà, không có đa số -> dependent nhưng chưa rõ giá trị đúng (như cũ).
df3 = employees([("NV05", "An", "KT", "1990-01-01", 10), ("NV05", "Ân", "KT", "1990-01-01", 10)])
res3 = analyze_functional_dependency(df3, cfg("ma_nv", "ten"))
g3 = res3["groups"][0]
check("cùng người, tên An/Ân: verdict dependent", g3["verdict"] == "dependent", g3["verdict"])
check("cùng người, tên An/Ân: hoà nên majority_value None, suspect_rows rỗng", g3["majority_value"] is None and g3["suspect_rows"] == [], g3)
check("cùng người, tên An/Ân: chỉ tô cột tên, gợi ý 'Chưa rõ ten'", flagged_cells(res3) == {(0, "ten"), (1, "ten")} and res3["rows"][0]["hint"] == ["Chưa rõ ten"], res3["rows"])

# 4) Ranh giới của "đa số rõ ràng" (>= 2 lần VÀ nhiều hơn hẳn giá trị thứ 2).
df4a = employees([("NV06", "An", "KT", "1990-01-01", 1), ("NV06", "An", "KT", "1990-01-01", 2), ("NV06", "Ân", "NS", "1991-01-01", 3), ("NV06", "Ân", "NS", "1991-01-01", 4)])
g4a = analyze_functional_dependency(df4a, cfg("ma_nv", "ten"))["groups"][0]
check("hoà 2 - 2: KHÔNG có đa số rõ ràng -> giữ luật cũ (các cột khác khác nhau -> determinant)", g4a["verdict"] == "determinant" and g4a["majority_value"] is None, g4a)
df4b = employees([("NV06", "An", "KT", "1990-01-01", 1), ("NV06", "Ân", "KT", "1990-01-01", 2), ("NV06", "Anh", "KT", "1990-01-01", 3)])
g4b = analyze_functional_dependency(df4b, cfg("ma_nv", "ten"))["groups"][0]
check("1 - 1 - 1: KHÔNG có đa số (đa số phải >= 2 lần) -> luật cũ", g4b["majority_value"] is None and g4b["suspect_rows"] == [], g4b)
df4c = employees([("NV06", "An", "KT", "1990-01-01", 1), ("NV06", "An", "KT", "1990-01-01", 2), ("NV06", "An", "KT", "1990-01-01", 3), ("NV06", "Ân", "KT", "1990-01-01", 4), ("NV06", "Anh", "KT", "1990-01-01", 5)])
g4c = analyze_functional_dependency(df4c, cfg("ma_nv", "ten"))["groups"][0]
check("3 - 1 - 1: đa số rõ ràng", g4c["verdict"] == "dependent" and g4c["majority_value"] == "An" and g4c["suspect_rows"] == [3, 4], g4c)

# 5) HẠN CHẾ đã biết: 2 dòng "An" + 1 dòng "Bình" (Bình là NGƯỜI KHÁC dùng chung mã) -> luật mới coi "Bình" là ô gõ sai thay vì nghi mã.
df5 = employees([("NV01", "An", "KT", "1990-01-01", 10), ("NV01", "An", "KT", "1990-01-01", 11), ("NV01", "Bình", "NS", "1985-05-05", 20)])
res5 = analyze_functional_dependency(df5, cfg("ma_nv", "ten"))
g5 = res5["groups"][0]
check("HẠN CHẾ: An x2 + Bình x1 (người khác) -> coi Bình là gõ sai (dependent, nghi ô tên của dòng Bình)",
      g5["verdict"] == "dependent" and g5["suspect_rows"] == [2] and flagged_cells(res5) == {(2, "ten")}, g5)

# 6) Không có cột nào khác để so sánh: trước đây "unknown"; có đa số rõ ràng thì nay kết luận được, không có thì vẫn unknown.
two_col = pd.DataFrame({"ma": ["a", "a", "a", "b"], "ten": ["x", "x", "y", "z"]})
g6 = analyze_functional_dependency(two_col, cfg("ma", "ten"))["groups"][0]
check("chỉ 2 cột, có đa số (x x y): dependent, nghi ô y, không in '0/0'",
      g6["verdict"] == "dependent" and g6["suspect_rows"] == [2], g6)
n6 = " ".join(n for info in analyze_functional_dependency(two_col, cfg("ma", "ten"))["rows"].values() for n in info["notes"])
check("chỉ 2 cột: câu giải thích không có '0/0'", "0/0" not in n6, n6)
two_tie = pd.DataFrame({"ma": ["a", "a"], "ten": ["x", "y"]})
g6b = analyze_functional_dependency(two_tie, cfg("ma", "ten"))["groups"][0]
check("chỉ 2 cột, hoà (x y): vẫn unknown như cũ", g6b["verdict"] == "unknown", g6b)

# ---------------------------------------------------------------------------------------------
# app.py dùng kết quả: _fd_plan + route (Sửa về giá trị phổ biến nhất / Chỉ xoá dòng nghi sai)
# ---------------------------------------------------------------------------------------------
plan = A._fd_plan(A._fd_analyses(df1, [cfg("measure_code", "condition")]))
check("_fd_plan: sửa đúng ô lệch về giá trị đa số", plan["fixes"] == {(TYPO_ROW, "condition"): "heart attack"}, plan["fixes"])
check("_fd_plan: dòng nghi sai = đúng dòng lỗi, không nhóm chưa xác định", plan["suspect_rows"] == {TYPO_ROW} and plan["unresolved_groups"] == 0, plan)

client = A.app.test_client()
r = client.post("/api/auth/register", json={"username": "fdmaj", "password": "abcdef123"})
check("đăng ký tài khoản test", r.status_code in (200, 201), r.get_json())
csv_bytes = df1.to_csv(index=False).encode("utf-8")


def call(config, mode="detect"):
    resp = client.post("/api/noise-tools/configured", data={"mode": mode, "config": json.dumps(config), "file": (io.BytesIO(csv_bytes), "t.csv")},
                       content_type="multipart/form-data")
    return resp.status_code, resp.get_json()


def fd_config(action=None):
    c = {"tool": "cross-rule", "rule": {"rule_type": "functional_dependency", "determinant_column": "measure_code", "dependent_columns": ["condition"]}}
    if action:
        c["action"] = action
    return c


st, det = call(fd_config())
check("route detect: 200, gắn cờ 10 dòng của nhóm", st == 200 and det["flagged_rows_count"] == 10, (st, det.get("flagged_rows_count") if det else None))
check("route detect: fd_plan khớp (1 ô sửa, 1 dòng nghi sai, xoá cả nhóm = 10 dòng)",
      st == 200 and det["fd_plan"] == {"fix_to_majority": {"cells": 1, "rows": 0}, "remove_suspect_rows": {"cells": 0, "rows": 1},
                                       "remove_row": {"cells": 0, "rows": 10}, "unresolved_groups": 0}, det.get("fd_plan") if det else None)
check("route detect: kết luận nhóm theo cột phụ thuộc = dependent 1, determinant 0",
      st == 200 and det["fd_analysis"]["rules"][0]["dependent"] == 1 and det["fd_analysis"]["rules"][0]["determinant"] == 0, det.get("fd_analysis") if det else None)

st, fixed = call(fd_config("fix_to_majority"), "apply")
table = pd.read_csv(io.StringIO(fixed["result_text"]), dtype=str, keep_default_na=False)
orig = pd.read_csv(io.StringIO(csv_bytes.decode("utf-8")), dtype=str, keep_default_na=False)
diff = [(r_, c) for r_ in range(len(orig)) for c in orig.columns if orig.loc[r_, c] != table.loc[r_, c]]
check("route apply 'Sửa về giá trị phổ biến': không xoá dòng, đổi đúng 1 ô", st == 200 and len(table) == len(orig) and fixed["stats"]["cells_changed"] == 1, fixed.get("stats"))
check("route apply 'Sửa về giá trị phổ biến': ô lỗi thành 'heart attack', không ô nào khác đổi", diff == [(TYPO_ROW, "condition")] and table.loc[TYPO_ROW, "condition"] == "heart attack", diff)

st, removed = call(fd_config("remove_suspect_rows"), "apply")
table2 = pd.read_csv(io.StringIO(removed["result_text"]), dtype=str, keep_default_na=False)
check("route apply 'Chỉ xoá dòng nghi sai': xoá đúng 1 dòng (dòng lỗi)", st == 200 and len(table2) == len(orig) - 1 and "hearx axxack" not in set(table2["condition"]), removed.get("stats"))

print(f"\nKẾT QUẢ: {ok} đạt, {fail} lỗi")
sys.exit(1 if fail else 0)
