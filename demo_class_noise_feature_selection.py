"""
Demo thu nghiem 2 buoc giam cot (feature selection) cho Class Noise, chay
tren bo Credit Card Fraud (29 cot candidate: Time + V1-28 + Amount) vi chua
co file goc ~35 cot cua thay -- thay bao co the dung tam file nay de thu
truoc, khong bat buoc dung dung file goc.

Buoc 1: xep hang 29 cot theo Feature Importance (Random Forest).
Buoc 2: loc bot cot tuong quan >= 0.8 voi nhau trong top 8 cot dau.
"""

from attribute_noise.pipeline import load_data
from class_noise.feature_selection import filter_correlated, rank_by_importance

df = load_data("data/kaggle_creditcard_fraud.csv")
candidates = [c for c in df.columns if c != "Class"]

print(f"Buoc 0: co {len(candidates)} cot candidate ban dau ({candidates}).\n")

print("Buoc 1: train Random Forest, xep hang theo Feature Importance...")
ranked = rank_by_importance(
    df, label_column="Class", candidate_columns=candidates, n_estimators=300
)
print("Xep hang day du (giam dan):")
for r in ranked:
    print(f"  {r.column:>8}: {r.importance:.4f}")

top8 = [r.column for r in ranked[:8]]
print(f"\n--> Giu top 8 cot quan trong nhat: {top8}\n")

print("Buoc 2: loc tuong quan (nguong 0.8) trong 8 cot do...")
final = filter_correlated(df, top8, threshold=0.8)
print(f"--> Con lai {len(final)} cot sau loc: {final}")

print("\nMa tran tuong quan giua 8 cot (de doi chieu vi sao cot nao bi loai):")
import pandas as pd

numeric_top8 = df[top8].apply(pd.to_numeric, errors="coerce")
print(numeric_top8.corr().round(2))
