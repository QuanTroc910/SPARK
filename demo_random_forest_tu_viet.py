"""
RANDOM FOREST VIET TAY -- xay THANG TU demo_decision_tree_tu_viet.py m da hieu.
Dung LAI CHINH XAC logic tinh_gini / tim_cau_hoi_tot_nhat / xay_cay / du_doan,
chi them 2 "meo ngau nhien" (bootstrap + random feature subset) + buoc gop
phieu nhieu cay -- de thay Random Forest KHONG PHAI thuat toan moi, ma la
"Decision Tree nhan len nhieu lan".
"""
import random

import pandas as pd

df_full = pd.read_csv("data/class_noise_train.csv")
df = df_full.sample(20000, random_state=1)  # mau con de chay nhanh

TAT_CA_COT = ["V44", "V12", "V4"]
SO_COT_THU_MOI_LAN = 2  # RANDOM FEATURE SUBSET: moi lan tach chi duoc xet 2/3 cot
SO_CAY = 7               # so cay trong rung (that su dung 300, giam xuong 7 de chay nhanh + de nhin)

random.seed(42)


def tinh_gini(nhan_series):
    """Y HET ham o demo_decision_tree_tu_viet.py -- khong doi gi ca."""
    if len(nhan_series) == 0:
        return 0
    ti_le = nhan_series.value_counts(normalize=True)
    return 1 - (ti_le ** 2).sum()


def tim_cau_hoi_tot_nhat(data, cac_cot_duoc_xet):
    """GIONG HET ham cu, chi khac 1 cho: nhan them tham so 'cac_cot_duoc_xet'
    thay vi luon luon dung ca TAT_CA_COT -- day la cho RANDOM FEATURE SUBSET
    duoc ap dung."""
    gini_truoc = tinh_gini(data["V153"])
    tot_nhat = None
    giam_lon_nhat = 0

    for cot in cac_cot_duoc_xet:  # <- CHI xet cac cot duoc chon ngau nhien, khong phai het 3 cot
        cac_nguong = data[cot].quantile([i / 100 for i in range(1, 100)]).unique()
        for nguong in cac_nguong:
            trai = data[data[cot] <= nguong]["V153"]
            phai = data[data[cot] > nguong]["V153"]
            if len(trai) == 0 or len(phai) == 0:
                continue
            gini_sau = (
                len(trai) / len(data) * tinh_gini(trai)
                + len(phai) / len(data) * tinh_gini(phai)
            )
            giam = gini_truoc - gini_sau
            if giam > giam_lon_nhat:
                giam_lon_nhat = giam
                tot_nhat = (cot, nguong)

    return tot_nhat


def xay_cay(data, do_sau=0, do_sau_toi_da=3):
    """GIONG HET ham xay_cay cu, chi them 1 dong: o MOI lan tach, chon ngau
    nhien SO_COT_THU_MOI_LAN cot trong TAT_CA_COT de xet -- day la
    RANDOM FEATURE SUBSET, 1 trong 2 'meo ngau nhien' cua Random Forest."""
    nhan_pho_bien = data["V153"].value_counts().idxmax()

    if do_sau >= do_sau_toi_da:
        return {"la": True, "du_doan": nhan_pho_bien}

    cac_cot_duoc_xet = random.sample(TAT_CA_COT, SO_COT_THU_MOI_LAN)  # <- MOI MOI so voi ban cu
    cau_hoi = tim_cau_hoi_tot_nhat(data, cac_cot_duoc_xet)
    if cau_hoi is None:
        return {"la": True, "du_doan": nhan_pho_bien}

    cot, nguong = cau_hoi
    trai = data[data[cot] <= nguong]
    phai = data[data[cot] > nguong]

    return {
        "la": False,
        "cot": cot,
        "nguong": nguong,
        "trai": xay_cay(trai, do_sau + 1, do_sau_toi_da),
        "phai": xay_cay(phai, do_sau + 1, do_sau_toi_da),
    }


def du_doan_1_cay(node, dong):
    """Y HET ham du_doan cu -- dung cho 1 cay duy nhat."""
    if node["la"]:
        return node["du_doan"]
    if dong[node["cot"]] <= node["nguong"]:
        return du_doan_1_cay(node["trai"], dong)
    return du_doan_1_cay(node["phai"], dong)


# ================= XAY RUNG: lap SO_CAY lan, moi lan 1 cay rieng =================
print(f"Dang trong {SO_CAY} cay (moi cay tu 1 mau BOOTSTRAP rieng + xet ngau nhien cot)...")
rung = []
for i in range(SO_CAY):
    # BOOTSTRAP (meo ngau nhien thu 2): lay mau CO HOAN LAI, cung kich thuoc voi df
    # -- co dong bi lap lai 2-3 lan, co dong vang mat hoan toan -- MOI CAY thay
    # 1 phien ban du lieu HOI KHAC nhau.
    mau_bootstrap = df.sample(n=len(df), replace=True, random_state=100 + i)
    cay = xay_cay(mau_bootstrap, do_sau_toi_da=3)
    rung.append(cay)
    if cay["la"]:
        print(f"  Cay {i+1}: la luon -> du doan {cay['du_doan']}")
    else:
        print(f"  Cay {i+1}: cau hoi GOC = {cay['cot']} <= {cay['nguong']:.3f}")


def du_doan_rung(rung, dong):
    """Cho CA RUNG cung doan 1 dong -- moi cay 1 phieu, dem phieu roi lay da so."""
    phieu = [du_doan_1_cay(cay, dong) for cay in rung]
    so_no = phieu.count("No")
    so_yes = phieu.count("Yes")
    ket_qua = "No" if so_no > so_yes else "Yes"
    return ket_qua, so_no, so_yes


print()
print("=== DUNG CA RUNG (7 CAY) DE DOAN THU -- CHON CO Y VAI DONG YES DE DE THAY BO PHIEU ===")
yes_trong_cum_zero = df_full[(df_full["V153"] == "Yes") & (df_full["V44"] == 0)].sample(2, random_state=1)
yes_ngoai_cum_zero = df_full[(df_full["V153"] == "Yes") & (df_full["V44"] != 0)].sample(2, random_state=1)
no_binh_thuong = df_full[df_full["V153"] == "No"].sample(2, random_state=1)
mau_test = pd.concat([yes_trong_cum_zero, yes_ngoai_cum_zero, no_binh_thuong])
for _, dong in mau_test.iterrows():
    ket_qua, so_no, so_yes = du_doan_rung(rung, dong)
    khop = "khop" if ket_qua == dong["V153"] else "SAI"
    print(
        f"  V44={dong['V44']:.2f} V12={dong['V12']:.2f} V4={dong['V4']:.2f}  "
        f"-> {so_no}/{SO_CAY} cay noi No, {so_yes}/{SO_CAY} cay noi Yes "
        f"=> model doan: {ket_qua:<4} | nhan that: {dong['V153']:<4} ({khop})"
    )
