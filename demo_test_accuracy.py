"""
Khac voi demo truoc (chi danh gia NGAY TRONG train.csv qua 5-fold CV),
o day TRAIN model tren TOAN BO train.csv (588k dong), roi dem model do
chua tung thay MOT DONG NAO trong test.csv ca -- day la cach danh gia
CHUAN va dang tin nhat, vi test.csv hoan toan tach biet, khong lien quan
gi den luc train.
"""
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report

train = pd.read_csv("data/class_noise_train.csv")
test = pd.read_csv("data/class_noise_test.csv")

X_train = train[["V44", "V12", "V4"]].values
y_train = train["V153"].values
X_test = test[["V44", "V12", "V4"]].values
y_test = test["V153"].values

print(f"Train tren TOAN BO {len(train)} dong cua train.csv...")
rf = RandomForestClassifier(n_estimators=300, class_weight="balanced", random_state=42, n_jobs=-1)
rf.fit(X_train, y_train)

print(f"Dung model da train xong, doan cho {len(test)} dong cua test.csv (chua tung thay)...")
du_doan = rf.predict(X_test)

so_dung = (du_doan == y_test).sum()
tong = len(test)
print()
print("=" * 70)
print(f"So dong doan DUNG tren test.csv: {so_dung} / {tong}")
print(f"Accuracy tren test.csv: {so_dung / tong:.4f} ({so_dung/tong*100:.2f}%)")

so_no_test = (y_test == "No").sum()
print(f"\nBaseline (doan bua 'No' cho tat ca): {so_no_test} / {tong} = {so_no_test/tong:.4f} ({so_no_test/tong*100:.2f}%)")

print()
print("Precision / Recall / F1 rieng tung lop tren test.csv:")
print(classification_report(y_test, du_doan, digits=3))
