"""
VI DU CODE THAT CUA 1 "MODEL DECISION TREE", TU VIET TAY (khong dung thu vien
scikit-learn) -- de thay ro model nay KHONG PHAI 1 num van duy nhat nhu vi du
truoc, ma la CA MOT CAY gom nhieu "nut" (node) noi voi nhau.

De chay nhanh cho MUC DICH MINH HOA, dung mau con 20.000 dong (thay vi ca
588k dong that) -- ket qua co the hoi khac ban chay tren toan bo du lieu,
nhung CO CHE hoat dong la GIONG HET.
"""
import pandas as pd

df_full = pd.read_csv("data/class_noise_train.csv")
df = df_full.sample(20000, random_state=1)  # mau con de chay nhanh

COTS = ["V44", "V12", "V4"]


def tinh_gini(nhan_series):
    """Do 'do lon xon' cua 1 nhom nhan -- 0 = hoan toan thuan 1 nhan (tot),
    cang gan 0.5 = cang tron lan Yes/No be bet (xau)."""
    if len(nhan_series) == 0:
        return 0
    ti_le = nhan_series.value_counts(normalize=True)
    return 1 - (ti_le ** 2).sum()


def tim_cau_hoi_tot_nhat(data):
    """Thu nhieu cap (cot, nguong), chon cap lam GIAM Gini nhieu nhat sau
    khi tach 2 nhom -- day la buoc 'hoc' cot loi cua Decision Tree."""
    gini_truoc = tinh_gini(data["V153"])
    tot_nhat = None
    giam_lon_nhat = 0

    for cot in COTS:
        # thu 99 nguong (theo 99 phan vi 1%-99%, DAY hon ban dau) cho nhanh,
        # khong thu HET moi gia tri co the co trong cot (se qua cham) --
        # phai thu DAY o day vi co 1 cum dac biet (V44=0) chi chiem ~1.9%
        # du lieu, thu thua (vd cach 5%) se "lot luoi" khong bat duoc no.
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


def xay_cay(data, do_sau=0, do_sau_toi_da=2):
    """Day chinh la ham 'TRAIN' -- de quy: tim cau hoi tot nhat, tach 2 nhom,
    roi LAP LAI dung logic nay cho tung nhom con, den khi dat do_sau_toi_da.
    Tra ve 1 dict Python -- day CHINH LA 'model' sau khi train xong."""
    nhan_pho_bien = data["V153"].value_counts().idxmax()

    if do_sau >= do_sau_toi_da:
        return {"la": True, "du_doan": nhan_pho_bien}

    cau_hoi = tim_cau_hoi_tot_nhat(data)
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


def in_cay(node, thut_le=""):
    """In cau truc cay ra man hinh cho de nhin -- CHINH LA noi dung 'model'."""
    if node["la"]:
        print(f"{thut_le}-> du doan: {node['du_doan']}")
        return
    print(f"{thut_le}{node['cot']} <= {node['nguong']:.3f} ?")
    print(f"{thut_le}  NEU CO (dung):")
    in_cay(node["trai"], thut_le + "    ")
    print(f"{thut_le}  NEU KHONG (sai):")
    in_cay(node["phai"], thut_le + "    ")


def du_doan(node, dong):
    """Dung model (cai cay) de doan 1 dong moi -- di tu goc, re trai/phai
    theo dung cau hoi tai moi nut, cho toi khi gap la."""
    if node["la"]:
        return node["du_doan"]
    if dong[node["cot"]] <= node["nguong"]:
        return du_doan(node["trai"], dong)
    return du_doan(node["phai"], dong)


print(f"DANG TRAIN (xay cay tu {len(df)} dong mau)...")
cay_da_train = xay_cay(df, do_sau_toi_da=2)

print()
print("=== MODEL SAU KHI TRAIN XONG -- CHINH LA CAI CAY NAY ===")
in_cay(cay_da_train)

print()
print("DUNG MODEL DE DOAN THU 5 DONG MOI (lay tu toan bo file, khong chi mau train):")
mau_test = df_full.sample(5, random_state=99)
for _, dong in mau_test.iterrows():
    ket_qua = du_doan(cay_da_train, dong)
    khop = "khop" if ket_qua == dong["V153"] else "SAI"
    print(
        f"  V44={dong['V44']:.2f} V12={dong['V12']:.2f} V4={dong['V4']:.2f} "
        f"-> model doan: {ket_qua:<4} | nhan that: {dong['V153']:<4} ({khop})"
    )
