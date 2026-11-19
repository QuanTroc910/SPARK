#!/usr/bin/env python3
"""Sinh bộ dữ liệu TEST cho phần ATTRIBUTE NOISE của Denoise: MỘT file nhân viên (chủ đề thống nhất) có đủ mọi loại lỗi
mà các tool Attribute dò được. (Class Noise dùng bộ Credit Card, không nằm trong file này -- xem CLAUDE.md mục 35-36.)

Chạy:  python3 data/generate_test_attribute_noise.py                      (bộ test 552 dòng)
       SCALE=3.62 OUT_NAME=demo_attribute_noise_2000 python3 data/generate_test_attribute_noise.py  (bộ DEMO 1997 dòng)
SCALE nhân số lượng MỌI loại lỗi và số nhân viên (SCALE=1 ra đúng bộ test cũ); OUT_NAME là tên file ra.
Sinh ra (trong thư mục data/):
  - <OUT_NAME>.csv / .xlsx                    : 20 cột, đủ lỗi (xem bảng đáp án bên dưới); SCALE=1 -> 552 dòng, SCALE=3.62 -> 1997 dòng
  - <OUT_NAME>_ground_truth.csv               : đáp án -- mỗi ô bị cấy lỗi (dòng, cột, loại lỗi, giá trị gốc, tool nên bắt)
  - test_convert_*.{json,jsonl,csv,txt}       : file nhỏ để thử 3 tool Convert
  - test_empty.csv, test_header_only.csv, test_bad.json : file "xấu" để thử báo lỗi

Hạt giống cố định (SEED) nên chạy lại ra đúng cùng một file. "Dòng" trong đáp án là số thứ tự dòng DỮ LIỆU
(1 = dòng đầu tiên sau tiêu đề), khớp cột "Dòng" trong giao diện Denoise (trong Excel thì cộng thêm 1 vì có tiêu đề).

Bảng lỗi cấy (cột -> lỗi):
  Ô trống ........ ho_ten, gioi_tinh, tuoi, email, so_dien_thoai, phong_ban, luong, diem_dg, ngay_sinh, ngay_vao,
                   ngay_ra, ghi_chu, Hệ số lương, hoa_hong (+ 4 dòng trống hoàn toàn + cột cot_trong trống hoàn toàn)
  Sai định dạng .. tuoi, luong, email, so_dien_thoai, ngay_sinh, ngay_vao, diem_dg, Hệ số lương
  Khoảng trắng ... ho_ten, ghi_chu (đầu / cuối / lặp giữa / zero-width / non-breaking space)
  Dòng trùng ..... 18 dòng trùng hệt + 6 dòng gần trùng (khác hoa/thường email, khoảng trắng ghi_chu)
  Ngoài khoảng ... tuoi (18-65), luong (3tr-100tr), diem_dg (1-10), Hệ số lương (> 0)
  Bất thường ..... luong (8 giá trị 45-70 triệu), thuong (cột "zero-inflated": 85% bằng 0 -> IQR = 0)
  Không nhất quán  gioi_tinh, phong_ban, loai_hd (khác hoa/thường; vài chỗ gõ sai chính tả)
  Rule liên cột .. ngay_ra < ngay_vao; tong_thu_nhap != luong + thuong; Thử việc mà lương > 12 triệu;
                   Sales mà thiếu hoa_hong; ma_nv -> ho_ten và ma_nv -> ngay_sinh bị mâu thuẫn
"""
import json
import os
import unicodedata
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent
SEED = 20260617
rng = np.random.default_rng(SEED)
SCALE = float(os.environ.get("SCALE", "1"))
OUT_NAME = os.environ.get("OUT_NAME", "test_attribute_noise")


def sc(x: int) -> int:
    """Số lượng sau khi nhân SCALE (SCALE=1 giữ nguyên x, nên bộ test cũ không đổi)."""
    return max(1, int(round(x * SCALE)))


def cyc(vals: list, k: int | None = None) -> list:
    """Kéo dài danh sách giá trị lỗi mẫu cho đủ số lượng cần (lặp vòng); SCALE=1 giữ nguyên danh sách."""
    k = sc(len(vals)) if k is None else k
    return [vals[i % len(vals)] for i in range(k)]



COLS = ["id", "ma_nv", "ho_ten", "gioi_tinh", "tuoi", "ngay_sinh", "email", "so_dien_thoai",
        "phong_ban", "loai_hd", "ngay_vao", "ngay_ra", "luong", "thuong", "tong_thu_nhap", "hoa_hong", "diem_dg",
        "Hệ số lương", "ghi_chu", "cot_trong"]

SURNAMES = ["Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Huỳnh", "Phan", "Vũ", "Võ", "Đặng", "Bùi", "Đỗ"]
MIDDLES = ["Văn", "Thị", "Minh", "Quốc", "Hồng", "Thanh", "Ngọc", "Đức", "Anh", "Gia"]
GIVENS = ["An", "Bình", "Châu", "Dũng", "Giang", "Hà", "Hải", "Hiếu", "Hoa", "Huy", "Khánh", "Lan", "Linh",
          "Long", "Mai", "Nam", "Phúc", "Quân", "Sơn", "Thảo", "Trang", "Tuấn", "Vy"]
DEPTS = ["Sales", "HR", "IT", "Marketing", "Finance"]
NOTES = ["Đã duyệt", "Chờ ký hợp đồng", "Đã duyệt, chờ ký", "Cần bổ sung hồ sơ", "Hoàn thành tốt",
         "Nghỉ phép dài ngày", "Chuyển phòng ban"]


def ascii_lower(s: str) -> str:
    s = s.replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower()


def r100k(x: float) -> int:
    return int(round(x / 100000.0)) * 100000


# ------------------------------------------------------------------ 1. dữ liệu SẠCH
N_EMP, N_SECOND, N_THIRD = sc(400), sc(100), sc(12)
emps, used_names = [], set()
for i in range(N_EMP):
    while True:
        sn, mid, gv = rng.choice(SURNAMES), rng.choice(MIDDLES), rng.choice(GIVENS)
        name = f"{sn} {mid} {gv}"
        if name not in used_names:
            used_names.add(name)
            break
    year = int(rng.integers(1972, 2003))
    emps.append({
        "ma_nv": f"NV{1001 + i}", "ho_ten": name,
        "gioi_tinh": "Nữ" if mid == "Thị" else str(rng.choice(["Nam", "Nữ"])),
        "tuoi": str(2025 - year),
        "ngay_sinh": f"{year}-{int(rng.integers(1, 13)):02d}-{int(rng.integers(1, 29)):02d}",
        "email": f"{ascii_lower(gv)}.{ascii_lower(sn)}{1001 + i}@congty.vn",
        "so_dien_thoai": "09" + "".join(str(int(d)) for d in rng.integers(0, 10, 8)),
    })

second = set(rng.choice(N_EMP, N_SECOND, replace=False).tolist())
third = set(rng.choice([i for i in range(N_EMP) if i not in second], N_THIRD, replace=False).tolist())
rows, emp_of = [], []
for i, e in enumerate(emps):
    for _ in range(3 if i in third else (2 if i in second else 1)):
        loai = str(rng.choice(["Chính thức", "Thử việc", "Cộng tác viên"], p=[0.6, 0.25, 0.15]))
        dept = str(rng.choice(DEPTS, p=[0.28, 0.14, 0.26, 0.18, 0.14]))
        vao = date(2016, 1, 1) + timedelta(days=int(rng.integers(0, 3287)))
        ra = vao + timedelta(days=int(rng.integers(120, 1200)))
        if loai == "Thử việc":
            luong = r100k(rng.uniform(7e6, 11.5e6))
        elif loai == "Chính thức":
            luong = r100k(min(max(rng.normal(18e6, 5e6), 10e6), 32e6))
        else:
            luong = r100k(rng.uniform(5e6, 14e6))
        thuong = 0 if rng.random() < 0.85 else r100k(rng.uniform(5e5, 9e6))
        rows.append({
            **e, "phong_ban": dept, "loai_hd": loai, "ngay_vao": vao.isoformat(), "ngay_ra": ra.isoformat(),
            "luong": str(luong), "thuong": str(thuong), "tong_thu_nhap": str(luong + thuong),
            "hoa_hong": str(round(float(rng.uniform(1.5, 8.0)), 1)) if dept == "Sales" else "0",
            "diem_dg": str(round(float(rng.uniform(5, 9.5)), 1)),
            "Hệ số lương": str(round(float(rng.uniform(1.0, 5.0)), 1)),
            "ghi_chu": str(rng.choice(NOTES)), "cot_trong": "",
        })
        emp_of.append(i)

df = pd.DataFrame(rows)
df.insert(0, "id", [str(i + 1) for i in range(len(df))])
df = df[COLS].astype(str)
NB = len(df)
cnt_emp = pd.Series(emp_of).value_counts()
SINGLE = [r for r in range(NB) if cnt_emp[emp_of[r]] == 1]            # nhân viên chỉ 1 hợp đồng
SECOND_OF_DOUBLE, LAST_OF_TRIPLE = [], []     # dòng hợp đồng cuối của nhân viên có 2 / 3 hợp đồng
for r in range(NB):
    if emp_of[r] != (emp_of[r + 1] if r + 1 < NB else None):          # dòng cuối của nhân viên này
        if cnt_emp[emp_of[r]] == 2: SECOND_OF_DOUBLE.append(r)
        elif cnt_emp[emp_of[r]] == 3: LAST_OF_TRIPLE.append(r)
ALL = list(range(NB))

# ------------------------------------------------------------------ 2. cấy lỗi
gt: list[dict] = []
used: set[tuple[int, str]] = set()


def put(r, col, new, ntype, tool, note=""):
    assert (r, col) not in used, (r, col)
    used.add((r, col))
    gt.append({"_r": r, "column": col, "noise_type": ntype, "original_value": df.at[r, col],
               "injected_value": new, "expected_tool": tool, "note": note})
    df.at[r, col] = new


def reserve(r, *cols):
    for c in cols:
        used.add((r, c))


def take(col, k, pool=None, where=None):
    cand = [r for r in (ALL if pool is None else pool) if (r, col) not in used and (where is None or where(r))]
    return [int(x) for x in rng.choice(cand, k, replace=False)]


def ztake(values, col, pool=None, where=None):
    """Cặp (giá trị lỗi mẫu, dòng) cho đủ số lượng đã nhân SCALE."""
    values = cyc(values)
    return zip(values, take(col, len(values), pool, where))


not_probation = lambda r: df.at[r, "loai_hd"] != "Thử việc"
BLANK_TOK = ["", "NA", "N/A", "null", "-", "?", "none", "--"]


def blanks(col, k, pool=None, where=None, tool="Free Tools · Ô trống", note=""):
    for j, r in enumerate(take(col, k, pool, where)):
        put(r, col, BLANK_TOK[j % len(BLANK_TOK)], "missing_value", tool, note)


# --- 2a. Rule liên cột (làm TRƯỚC để giữ chỗ các ô liên quan)
for r in take("ngay_ra", sc(10), where=lambda r: (r, "ngay_vao") not in used):
    vao = date.fromisoformat(df.at[r, "ngay_vao"])
    put(r, "ngay_ra", (vao - timedelta(days=int(rng.integers(10, 300)))).isoformat(), "cross_rule_expression",
        "Cần cấu hình · Rule liên cột · Biểu thức", "ngay_ra < ngay_vao; biểu thức: ngay_ra >= ngay_vao")
    reserve(r, "ngay_vao")
for r in take("tong_thu_nhap", sc(8)):
    tt = int(df.at[r, "tong_thu_nhap"])
    put(r, "tong_thu_nhap", str(tt + int(rng.choice([-500000, -1000, 7000, 120000, 999999]))), "cross_rule_expression",
        "Cần cấu hình · Rule liên cột · Biểu thức", "tong_thu_nhap != luong + thuong; biểu thức: luong + thuong = tong_thu_nhap")
    reserve(r, "luong", "thuong")
for r in take("luong", sc(5), where=lambda r: df.at[r, "loai_hd"] == "Thử việc"):
    put(r, "luong", str(r100k(rng.uniform(14e6, 20e6))), "cross_rule_if_then",
        "Cần cấu hình · Rule liên cột · Biểu thức", 'loai_hd = "Thử việc" => luong <= 12000000')
    reserve(r, "loai_hd")
for j, r in enumerate(take("hoa_hong", sc(7), where=lambda r: df.at[r, "phong_ban"] == "Sales")):
    put(r, "hoa_hong", ["", "NA", "-", "", "?", "", "null"][j % 7], "cross_rule_if_then",
        "Cần cấu hình · Rule liên cột · Biểu thức (cũng là ô trống)", 'phong_ban = "Sales" => có(hoa_hong)')
    reserve(r, "phong_ban")

# --- 2b. Phụ thuộc hàm ma_nv -> ho_ten / ngay_sinh
#   * nhân viên có 3 hợp đồng: 1 dòng sai -> "sửa về giá trị phổ biến" xác định được (2 đúng : 1 sai)
#   * nhân viên có 2 hợp đồng: 2 dòng khác nhau -> hoà số lượng, Denoise báo "chưa xác định được"
#   * 2 mã bị DÙNG CHUNG cho 2 người khác nhau (nghi sai chính cột ma_nv)
def wrong_name(r):
    return str(rng.choice([e["ho_ten"] for e in emps if e["ho_ten"] != df.at[r, "ho_ten"]]))
def wrong_birth(r):
    y = int(df.at[r, "ngay_sinh"][:4]) + int(rng.choice([-3, -2, 2, 3]))
    return f"{y}{df.at[r, 'ngay_sinh'][4:]}"
tri = [int(x) for x in rng.choice(LAST_OF_TRIPLE, sc(6), replace=False)]
dbl = [int(x) for x in rng.choice(SECOND_OF_DOUBLE, sc(5), replace=False)]
for r in tri[:sc(4)] + dbl[:sc(3)]:
    put(r, "ho_ten", wrong_name(r), "functional_dependency", "Cần cấu hình · Rule liên cột · Phụ thuộc hàm",
        "ma_nv -> ho_ten: " + ("nhóm 3 dòng, 1 dòng sai (xác định được, sửa về giá trị phổ biến)" if r in tri else "nhóm 2 dòng, hai tên khác nhau (hoà, chưa xác định được dòng nào sai)"))
for r in tri[sc(4):] + dbl[sc(3):]:
    put(r, "ngay_sinh", wrong_birth(r), "functional_dependency", "Cần cấu hình · Rule liên cột · Phụ thuộc hàm",
        "ma_nv -> ngay_sinh: " + ("nhóm 3 dòng, 1 dòng sai (xác định được)" if r in tri else "nhóm 2 dòng, hoà (chưa xác định được)"))
for r in tri + dbl:
    reserve(r, "ma_nv")
pair_src = [int(x) for x in rng.choice(SINGLE, 2 * sc(2), replace=False)]
for a, b in zip(pair_src[0::2], pair_src[1::2]):
    reserve(a, "ma_nv", "ho_ten", "ngay_sinh")
    reserve(b, "ho_ten", "ngay_sinh")
    put(b, "ma_nv", df.at[a, "ma_nv"], "functional_dependency", "Cần cấu hình · Rule liên cột · Phụ thuộc hàm",
        f"ma_nv trùng với một NGƯỜI KHÁC (nhân viên ở dòng gốc khác): Denoise nên kết luận nghi sai cột ma_nv")

# --- 2c. Ô trống
blanks("ho_ten", sc(5), SINGLE)
blanks("gioi_tinh", sc(6))
blanks("tuoi", sc(4))
blanks("email", sc(7))
blanks("so_dien_thoai", sc(6))
blanks("phong_ban", sc(5), where=lambda r: df.at[r, "phong_ban"] != "Sales")
blanks("luong", sc(6), where=not_probation)
blanks("diem_dg", sc(4))
blanks("ngay_sinh", sc(4), SINGLE)
blanks("ngay_vao", sc(3), where=lambda r: (r, "ngay_ra") not in used)
blanks("ngay_ra", sc(3))
blanks("Hệ số lương", sc(3))
for j, r in enumerate(take("ghi_chu", sc(30))):
    put(r, "ghi_chu", ["", "-", "NA"][j % 3], "missing_value", "Free Tools · Ô trống", "dùng để thử 'giá trị cố định' cho cột chữ")

# --- 2d. Sai định dạng
def fmt(col, values, pool=None, where=None, note=""):
    for v, r in ztake(values, col, pool, where):
        put(r, col, v, "format_noise", "Free Tools · Sai định dạng", note)


fmt("tuoi", ["hai mươi", "25 tuổi", "3O"], note="3O = chữ O thay số 0")
fmt("luong", ["12.5tr", "mười triệu", "12,500,000đ", "15 triệu", "abc"], where=not_probation)
fmt("email", ["nguyenvana.congty.vn", "an@", "an@@congty.vn", "tran thi@congty.vn", "@congty.vn", "lan.le@congty"])
fmt("so_dien_thoai", ["09123", "0912-345-678", "+84912345678", "091234567A", "912345678", "0912 345 678"])
fmt("ngay_sinh", ["1990-02-30", "1985-13-10", "không rõ", "abc"], SINGLE, note="ngày không tồn tại / không phải ngày")
for r in take("ngay_sinh", sc(6), SINGLE):
    y, m, d = df.at[r, "ngay_sinh"].split("-")
    put(r, "ngay_sinh", f"{d}/{m}/{y}", "format_noise", "Free Tools · Sai định dạng",
        "ngày đúng nhưng khác khuôn dd/mm/yyyy (so với khuôn chuẩn yyyy-mm-dd)")
fmt("ngay_vao", ["2022-02-30", "31/12/2020", "chưa có"], where=lambda r: (r, "ngay_ra") not in used)
fmt("diem_dg", ["tám", "7/10", "8,5"])
fmt("Hệ số lương", ["hai", "3,5"])

# --- 2e. Ngoài khoảng / bất thường
for v, r in ztake(["210", "150", "-5", "0", "7", "999"], "tuoi"):
    put(r, "tuoi", v, "out_of_range", "Cần cấu hình · Ngoài khoảng", "khoảng gợi ý 18-65")
for v, r in ztake(["78", "82", "91"], "tuoi"):
    put(r, "tuoi", v, "out_of_range", "Cần cấu hình · Ngoài khoảng (18-65) / Giá trị bất thường", "cao bất thường nhưng có thể là thật")
for v, r in ztake(["-3000000", "-1500000", "1000", "900000000"], "luong", where=not_probation):
    put(r, "luong", v, "out_of_range", "Cần cấu hình · Ngoài khoảng", "khoảng gợi ý 3.000.000-100.000.000")
for v, r in ztake(["11", "12.5", "0", "-1", "99", "15"], "diem_dg"):
    put(r, "diem_dg", v, "out_of_range", "Cần cấu hình · Ngoài khoảng", "khoảng gợi ý 1-10")
for v, r in ztake(["-1", "0"], "Hệ số lương"):
    put(r, "Hệ số lương", v, "out_of_range", "Cần cấu hình · Ngoài khoảng / Biểu thức [Hệ số lương] > 0", "")
for v, r in ztake([45e6, 48e6, 52e6, 55e6, 58e6, 61e6, 66e6, 70e6], "luong", where=not_probation):
    put(r, "luong", str(int(v)), "outlier", "Cần cấu hình · Giá trị bất thường", "trong khoảng 3tr-100tr nhưng lệch hẳn phần còn lại")

# --- 2f. Không nhất quán (khác hoa/thường hoặc gõ sai nhẹ)
def variants(col, mapping, where_for=None):
    for new, k in mapping:
        for r in take(col, sc(k), where=(where_for(new) if where_for else None)):
            put(r, col, new, "inconsistent_category", "Cần cấu hình · Không nhất quán")


variants("gioi_tinh", [("nam", 5), ("NAM", 3)], lambda n: lambda r: df.at[r, "gioi_tinh"] == "Nam")
variants("gioi_tinh", [("nữ", 4), ("NỮ", 2)], lambda n: lambda r: df.at[r, "gioi_tinh"] == "Nữ")
src = lambda canon: (lambda n: (lambda r: df.at[r, "phong_ban"] == canon and (r, "hoa_hong") not in used))
variants("phong_ban", [("sales", 4), ("SALES", 2), ("Sale", 2)], src("Sales"))
variants("phong_ban", [("hr", 3)], src("HR"))
variants("phong_ban", [("it", 2)], src("IT"))
variants("phong_ban", [("MARKETING", 2), ("Marketting", 2)], src("Marketing"))
variants("phong_ban", [("finance", 2)], src("Finance"))
variants("loai_hd", [("chính thức", 3), ("CHÍNH THỨC", 2)], lambda n: lambda r: df.at[r, "loai_hd"] == "Chính thức")
for r in [g["_r"] for g in gt if g["column"] == "phong_ban" and g["noise_type"] == "inconsistent_category"
          and g["injected_value"] in ("Sale", "Marketting")]:
    for g in gt:
        if g["_r"] == r and g["column"] == "phong_ban":
            g["note"] = "gõ sai nhẹ: chỉ bắt khi hạ ngưỡng giống nhau xuống ~0.85"

# --- 2g. Khoảng trắng thừa
def ws(col, kind, k, pool=None):
    for r in take(col, sc(k), pool, where=lambda r: df.at[r, col] not in BLANK_TOK):
        v = df.at[r, col]
        new = {"lead": "  " + v, "trail": v + "   ", "inner": v.replace(" ", "    ", 1),
               "zw": v[:3] + "​" + v[3:], "nbsp": v.replace(" ", " ", 1)}[kind]
        put(r, col, new, "whitespace_noise", "Free Tools · Cắt khoảng trắng",
            {"lead": "khoảng trắng đầu", "trail": "khoảng trắng cuối", "inner": "khoảng trắng lặp ở giữa",
             "zw": "ký tự zero-width (nhìn không thấy)", "nbsp": "non-breaking space"}[kind])


for kind, k in [("lead", 5), ("trail", 5), ("inner", 5)]:
    ws("ho_ten", kind, k, SINGLE)
for kind, k in [("lead", 6), ("trail", 6), ("inner", 5), ("zw", 4), ("nbsp", 3)]:
    ws("ghi_chu", kind, k)

# --- 2h. Đồng bộ tong_thu_nhap: ô luong bị đổi thành SỐ khác (ngoài khoảng / bất thường / thử việc lương cao) thì tổng tính lại
#     theo luong mới, để rule "luong + thuong = tong_thu_nhap" CHỈ vi phạm đúng 8 dòng đã cấy ở 2a (không phát sinh vi phạm ngoài ý muốn).
#     Ô luong bị đổi thành chữ / để trống thì giữ tổng gốc (biểu thức coi là "chưa biết", bỏ qua dòng đó).
for g in gt:
    if g["column"] == "luong" and g["noise_type"] in ("out_of_range", "outlier", "cross_rule_if_then"):
        r = g["_r"]
        df.at[r, "tong_thu_nhap"] = str(int(float(g["injected_value"])) + int(df.at[r, "thuong"]))

# ------------------------------------------------------------------ 3. dòng trùng + dòng trống hoàn toàn
touched = {r for r, _ in used}
fd_emps = {emp_of[r] for r in tri + dbl + pair_src}      # không nhân bản dòng của nhóm Phụ thuộc hàm (sẽ làm lệch phép đếm đa số)
clean_rows = [r for r in ALL if r not in touched and emp_of[r] not in fd_emps]
dup_src = [int(x) for x in rng.choice(clean_rows, sc(24), replace=False)]
extra = []        # (dòng mới, ghi chú gt)
for r in dup_src[:sc(18)]:
    extra.append((df.loc[r].copy(), "duplicate_row", r, "trùng hệt dòng gốc"))
for r in dup_src[sc(18):]:
    row = df.loc[r].copy()
    row["email"] = row["email"].upper()
    row["ghi_chu"] = row["ghi_chu"] + " "
    extra.append((row, "near_duplicate_row", r, "gần trùng: email viết HOA + ghi_chu thừa 1 dấu cách (chỉ bắt khi bật 'bỏ qua hoa/thường' và 'bỏ qua khoảng trắng')"))
for _ in range(sc(4)):
    extra.append((pd.Series({c: "" for c in COLS}), "empty_row", None, "dòng trống hoàn toàn (mọi cột đều trống)"))

df_all = pd.concat([df] + [pd.DataFrame([e[0]]) for e in extra], ignore_index=True)
M = len(df_all)
for j, (_, ntype, src_r, note) in enumerate(extra):
    gt.append({"_r": NB + j, "column": "(cả dòng)", "noise_type": ntype,
               "original_value": "", "injected_value": "",
               "expected_tool": "Free Tools · Xoá dòng trùng" if "dup" in ntype else "Free Tools · Ô trống (xoá dòng trống hoàn toàn)",
               "note": note + (f" (bản gốc là dòng {{src}})" if src_r is not None else ""), "_src": src_r})
gt.append({"_r": -1, "column": "cot_trong", "noise_type": "empty_column", "original_value": "", "injected_value": "",
           "expected_tool": "Free Tools · Ô trống (xoá luôn cột trống hoàn toàn)", "note": "cả cột không có giá trị nào", "_src": None})

perm = rng.permutation(M)
final = df_all.iloc[perm].reset_index(drop=True)
new_row = np.empty(M, dtype=int)
new_row[perm] = np.arange(M)

for g in gt:
    g["row"] = int(new_row[g["_r"]]) + 1 if g["_r"] >= 0 else 0
for g in gt:
    if "{src}" in g["note"]:
        g["note"] = g["note"].replace("{src}", str(int(new_row[g["_src"]]) + 1))

gt_df = pd.DataFrame(gt)[["row", "column", "noise_type", "original_value", "injected_value", "expected_tool", "note"]]
gt_df = gt_df.sort_values(["row", "column"], kind="stable").reset_index(drop=True)

final.to_csv(OUT / f"{OUT_NAME}.csv", index=False, encoding="utf-8")
final.to_excel(OUT / f"{OUT_NAME}.xlsx", index=False)
gt_df.to_csv(OUT / f"{OUT_NAME}_ground_truth.csv", index=False, encoding="utf-8")

# ------------------------------------------------------------------ 4. file nhỏ cho Convert + file "xấu"
nested = [
    {"id": 1, "ten": "Ana", "dia_chi": {"thanh_pho": "Hà Nội", "quan": "Cầu Giấy"}, "tags": ["a", "b"], "ma": "007"},
    {"id": 2, "ten": "Ben", "dia_chi": {"thanh_pho": "Đà Nẵng"}, "tags": [], "dang_lam": True},
    {"id": 3, "ten": "Chloé", "dia_chi": None, "diem": 8.5, "ma": "0912345678"},
    {"id": 4, "ten": "Dũng, \"Bo\"", "ghi_chu": "có dấu phẩy, ngoặc kép và\nxuống dòng"},
]
(OUT / "test_convert_nested.json").write_text(json.dumps(nested, ensure_ascii=False, indent=2), encoding="utf-8")
(OUT / "test_convert_lines.jsonl").write_text(
    "\n".join(json.dumps(o, ensure_ascii=False) for o in nested[:3]) + "\n", encoding="utf-8")
(OUT / "test_semicolon.csv").write_text(
    'ma;ten;gia;ghi_chu\n007;Bút bi;12,50;"Loại tốt, mới"\nA02;Kẹp giấy;3,00;\nA03;"Sổ ""A5""";45,00;bìa cứng\n',
    encoding="utf-8")
(OUT / "test_tab.txt").write_text("ma\tten\tgia\nA01\tBút bi\t12.5\nA02\tKẹp giấy\t3\n", encoding="utf-8")
(OUT / "test_empty.csv").write_text("", encoding="utf-8")
(OUT / "test_header_only.csv").write_text("ma,ten,gia\n", encoding="utf-8")
(OUT / "test_bad.json").write_text('[{"id": 1, "ten": "Ana"}, {"id": 2, "ten": ', encoding="utf-8")

print(f"OK: {len(final)} dòng x {len(COLS)} cột; {len(gt_df)} dòng đáp án")
print(gt_df.groupby("noise_type").size().to_string())
