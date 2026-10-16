"""
Demo thu nghiem 2 buoc giam cot (feature selection) cho Class Noise, chay
tren bo Credit Card Fraud (29 cot candidate: Time + V1-28 + Amount) vi chua
co file goc ~35 cot cua thay -- thay bao co the dung tam file nay de thu
truoc, khong bat buoc dung dung file goc.

Buoc 1: xep hang 29 cot theo Feature Importance (Random Forest), tu chon so
        cot giu lai bang Elbow Method (khong lay cung 1 so cot dinh san).
Buoc 2: loc bot cot tuong quan >= 0.8 voi nhau trong cac cot Buoc 1 giu lai.
"""

from attribute_noise.pipeline import load_data
from class_noise.feature_selection import (
    filter_correlated,
    rank_by_importance,
    select_by_elbow,
)

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

top_cols = select_by_elbow(ranked)
print(f"\n--> Elbow Method tu chon giu {len(top_cols)} cot: {top_cols}\n")

print(f"Buoc 2: loc tuong quan (nguong 0.8) trong {len(top_cols)} cot do...")
final = filter_correlated(df, top_cols, threshold=0.8)
print(f"--> Con lai {len(final)} cot sau loc: {final}")

print(f"\nMa tran tuong quan giua {len(top_cols)} cot (de doi chieu vi sao cot nao bi loai):")
import pandas as pd

numeric_top = df[top_cols].apply(pd.to_numeric, errors="coerce")
print(numeric_top.corr().round(2))
