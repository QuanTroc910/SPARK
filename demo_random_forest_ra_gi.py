"""
VI DU: Random Forest chay tren du lieu that cua m RA CAI GI, va cach tinh
do chinh xac co dung khong -- CHUA dung Confident Learning, chi don gian
"train roi doan roi dem dung/sai".
"""
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_predict

df = pd.read_csv("data/class_noise_train.csv")
X = df[["V44", "V12", "V4"]].values
y = df["V153"].values  # chua ma hoa, de nguyen "Yes"/"No" cho de doc

print(f"Dang train Random Forest (300 cay) qua 5-fold CV tren {len(df)} dong...")

rf = RandomForestClassifier(n_estimators=300, class_weight="balanced", random_state=42, n_jobs=-1)
skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
pred_probs = cross_val_predict(rf, X, y, cv=skf, method="predict_proba", n_jobs=1)

# cross_val_predict tra ve mang so (0/1), can biet cot nao la "No", cot nao la "Yes"
rf_tam = RandomForestClassifier().fit(X[:100], y[:100])  # chi de lay thu tu class_
ten_cac_lop = rf_tam.classes_
print(f"Thu tu 2 cot trong pred_probs: {list(ten_cac_lop)}")

print()
print("=" * 70)
print("PHAN 1: pred_probs TRONG RA GI -- xem thu 10 dong that")
print("=" * 70)
mau_idx = df.sample(10, random_state=5).index
for i in mau_idx:
    p_no, p_yes = pred_probs[i]
    print(
        f"  dong {i:>6}: V44={df.loc[i,'V44']:.2f} V12={df.loc[i,'V12']:.2f} V4={df.loc[i,'V4']:.2f}"
        f"  ->  P(No)={p_no:.3f}  P(Yes)={p_yes:.3f}   | nhan that = {df.loc[i,'V153']}"
    )

print()
print("=" * 70)
print("PHAN 2: TINH DO CHINH XAC -- tung buoc, khong giau gi ca")
print("=" * 70)

# Buoc A: voi moi dong, chon nhan co xac suat CAO HON (argmax)
du_doan = pd.Series(
    [ten_cac_lop[0] if p[0] > p[1] else ten_cac_lop[1] for p in pred_probs],
    index=df.index,
)
print("Buoc A: voi moi dong, chon nhan co xac suat cao hon.")
print("  Vi du 10 dong tren:")
for i in mau_idx:
    khop = "khop" if du_doan[i] == df.loc[i, "V153"] else "SAI"
    print(f"    dong {i}: model doan = {du_doan[i]:<4} | nhan that = {df.loc[i,'V153']:<4}  ({khop})")

print()
so_dong_dung = (du_doan == df["V153"]).sum()
tong_so_dong = len(df)
print(f"Buoc B: dem TOAN BO {tong_so_dong} dong -- bao nhieu dong model doan == nhan that")
print(f"  So dong doan DUNG : {so_dong_dung}")
print(f"  So dong doan SAI  : {tong_so_dong - so_dong_dung}")
print(f"  Do chinh xac = {so_dong_dung} / {tong_so_dong} = {so_dong_dung / tong_so_dong:.6f}")

print()
so_dong_no = (df["V153"] == "No").sum()
print(f"Buoc C: so sanh voi baseline (doan bua la 'No' cho MOI dong)")
print(f"  So dong nhan that la No: {so_dong_no} / {tong_so_dong} = {so_dong_no / tong_so_dong:.6f}")
print(f"  -> Neu doan bua 'No' cho tat ca, se dung dung {so_dong_no} dong (dung dung so dong La No)")
