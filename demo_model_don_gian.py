"""
VI DU DON GIAN NHAT DE HIEU "MODEL" LA GI VA "NUM VAN" LA GI.

Model o day CHI dung 1 cot V44 de doan Yes/No, theo dung 1 luat:
    "neu V44 < threshold thi doan Yes, nguoc lai doan No"

"Num van" cua model nay la DUY NHAT 1 con so: threshold.
TRUOC khi train: threshold la 1 con so BUA (chua biet chon bao nhieu).
TRAIN = thu nhieu gia tri threshold khac nhau tren du lieu that,
        do xem gia tri nao cho doan DUNG NHIEU NHAT, roi CHOT lai gia tri do.
"""
import pandas as pd

df = pd.read_csv("data/class_noise_train.csv")


def du_doan(v44: float, threshold: float) -> str:
    """Day chinh la toan bo 'cong thuc' cua model -- cuc ky don gian."""
    return "Yes" if v44 < threshold else "No"


def tinh_do_chinh_xac(threshold: float) -> float:
    """Cho model doan CA 588k dong, roi dem xem doan dung bao nhieu %."""
    du_doan_ca_file = df["V44"].apply(lambda v: du_doan(v, threshold))
    so_dong_dung = (du_doan_ca_file == df["V153"]).sum()
    return so_dong_dung / len(df)


# ===== TRUOC KHI TRAIN: "num van" threshold dang o gia tri BUA =====
threshold_ban_dau = 0
print(f"TRUOC KHI TRAIN -- threshold dang de bua = {threshold_ban_dau}")
print(f"Do chinh xac luc nay: {tinh_do_chinh_xac(threshold_ban_dau):.4f}")

# ===== TRAIN: thu nhieu threshold, xem cai nao doan dung nhieu nhat =====
print()
print("DANG TRAIN -- thu lan luot nhieu threshold, do do chinh xac tung cai:")
ung_vien = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0]
threshold_tot_nhat = None
do_chinh_xac_tot_nhat = 0.0

for t in ung_vien:
    acc = tinh_do_chinh_xac(t)
    danh_dau = "  <-- tot nhat tinh den gio" if acc > do_chinh_xac_tot_nhat else ""
    print(f"  thu threshold = {t:>4}: do chinh xac = {acc:.4f}{danh_dau}")
    if acc > do_chinh_xac_tot_nhat:
        do_chinh_xac_tot_nhat = acc
        threshold_tot_nhat = t

print()
print("=== TRAIN XONG ===")
print(f"'Num van' threshold sau khi train duoc CHOT lai = {threshold_tot_nhat}")
print(f"Do chinh xac voi threshold nay: {do_chinh_xac_tot_nhat:.4f}")

# ===== DUNG MODEL DA TRAIN DE DOAN 1 DONG MOI =====
print()
print("DUNG MODEL DA TRAIN XONG DE DOAN THU VAI DONG:")
mau = df.sample(5, random_state=7)
for _, row in mau.iterrows():
    ket_qua = du_doan(row["V44"], threshold_tot_nhat)
    khop = "khop" if ket_qua == row["V153"] else "SAI"
    print(f"  V44={row['V44']:.3f} -> model doan: {ket_qua:<4} | nhan that: {row['V153']:<4} ({khop})")
