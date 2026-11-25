"""Tổng hợp kết quả class noise (Bảng 4.5, 4.6 và các số ở mục 4.4): trung bình theo mức nhiễu,
so sánh bộ kết hợp với từng thuật toán (thắng/hòa/thua, kiểm định dấu hạng Wilcoxon), số dòng gắn cờ ở mức 0%.
    python experiments/class_noise_report.py            (mặc định đọc results/class_noise.jsonl)
    python experiments/class_noise_report.py tep1.jsonl tep2.jsonl --csv results/class_noise_tong_hop.csv
"""
import argparse, json
import pandas as pd
from scipy.stats import wilcoxon

ap = argparse.ArgumentParser(); ap.add_argument("files", nargs="*", default=["results/class_noise.jsonl"]); ap.add_argument("--csv")
a = ap.parse_args()
rows = []
for f in a.files:
    for line in open(f, encoding="utf-8"):
        r = json.loads(line)
        for key, label in [("ket_hop", "Kết hợp"), ("single_learning", "Confident Learning"), ("distance_based", "Mutual k-NN")]:
            if key in r:
                rows.append(dict(ds=r["dataset"], lv=r["level"], seed=r["seed"], m=label, n_true=r["n_true"], sec=r["sec"], **r[key]))
d = pd.DataFrame(rows); pd.set_option("display.width", 250)
g = (d[d.lv > 0].groupby(["ds", "lv", "m"], sort=False)
     .agg(sai_that=("n_true", "mean"), gan_co=("n", "mean"), dung=("tp", "mean"), P=("P", "mean"), R=("R", "mean"),
          F1=("F1", "mean"), F1_sd=("F1", "std"), giay=("sec", "mean")).round(3))
print(g.to_string())
if a.csv:
    g.reset_index().to_csv(a.csv, index=False)
print("\nSố dòng gắn cờ ở mức 0%:", d[d.lv == 0].groupby(["ds", "m"]).n.mean().to_dict())
w = d[d.lv > 0].pivot_table(index=["ds", "lv", "seed"], columns="m", values="F1")
for ds in list(dict.fromkeys(d.ds)) + [None]:
    x = w if ds is None else w.loc[ds]
    for other in ["Confident Learning", "Mutual k-NN"]:
        diff = x["Kết hợp"] - x[other]
        win, tie, lose = int((diff > 1e-9).sum()), int((diff.abs() <= 1e-9).sum()), int((diff < -1e-9).sum())
        p = wilcoxon(x["Kết hợp"], x[other]).pvalue if (diff.abs() > 1e-9).any() else float("nan")
        print(f"{ds or 'cả ba bộ':12s} kết hợp so với {other:18s}: thắng {win} hòa {tie} thua {lose} / {len(x)} | "
              f"F1 {x['Kết hợp'].mean():.3f} vs {x[other].mean():.3f} | Wilcoxon p = {p:.2g}")
print("\nThời gian trung bình một lần phát hiện (giây):", d.groupby("ds").sec.mean().round(1).to_dict())
# Bảng 4.7: bước chuẩn bị, mức vượt mốc, độ phủ của Mutual k-NN (chỉ có trong tệp do class_noise_web.py hiện tại ghi)
raw = [json.loads(l) for f in a.files for l in open(f, encoding="utf-8")]
raw = [r for r in raw if "chuan_bi" in r]
if raw:
    print("\nBảng 4.7 (hạt giống 0): bộ | mức | bỏ vì tương quan | Boruta giữ/vào (số vòng) | dòng gộp bớt | mức vượt mốc | độ phủ k-NN | cảnh báo")
    for r in raw:
        if r["seed"] == 0:
            c = r["chuan_bi"]
            print(f"  {r['dataset']:12s} {r['level']:.2f} | {c['bo_tuong_quan']} | {c['boruta_giu']}/{c['boruta_vao']} ({c['boruta_vong']}) | "
                  f"{c['dong_gop_bot']} | {r['muc_vuot_moc']:.3f} | {r['do_phu_knn']:.3f} | {len(r['canh_bao'])}")
    kept = pd.DataFrame([dict(ds=r["dataset"], lv=r["level"], giu=r["chuan_bi"]["boruta_giu"]) for r in raw])
    print("Số cột Boruta giữ (nhỏ nhất, lớn nhất) theo bộ và mức:", kept.groupby(["ds", "lv"]).giu.agg(["min", "max"]).to_dict("index"))
    print("Số lần chạy có cảnh báo về mức vượt mốc:", sum(1 for r in raw if r["canh_bao"]))
