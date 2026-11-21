"""
KHUNG THÍ NGHIỆM CLASS NOISE (nhiều seed, nhiều bộ dữ liệu, nhiễu IDN, đo DOWNSTREAM).

Trả lời góp ý "thực nghiệm chưa đủ tin cậy": thay vì 1 bộ dữ liệu + 1 seed + chỉ đo "tìm lại
được bao nhiêu nhãn sai", script này chạy:
  - 3 bộ dữ liệu: Credit Card (lệch lớp rất nặng), Adult (6 cột số, lệch vừa), dữ liệu thầy (3 cột yếu).
  - nhiều seed (mean ± std ở bước tổng hợp, xem summarize_class_noise_multiseed.py).
  - 3 kiểu nhiễu: A (đảo đồng đều), B (đảo lớp hiếm + số bằng vậy từ lớp đa số),
    IDN (Instance-Dependent Noise: nhãn của các mẫu KHÓ -- sát ranh giới quyết định -- dễ bị đảo hơn).
  - các thuật toán: single, distance, ensemble (hiện tại) + naive_cv (đối chứng "sklearn thuần":
    cross_val_predict 1 mô hình rồi gắn cờ mọi dòng dự đoán khác nhãn ghi) + (sau này) bản cải tiến.
  - đo DOWNSTREAM: huấn luyện CÙNG 1 mô hình trên 4 bản tập train rồi chấm trên tập TEST SẠCH:
      (1) chưa làm sạch  (2) lọc bỏ dòng bị gắn cờ  (3) sửa nhãn theo gợi ý  (4) nhãn gốc sạch (Oracle).

Giao thức mỗi (bộ dữ liệu, seed): chia train/test 70/30 phân tầng; nhiễu CHỈ cấy vào nhãn train;
test giữ nhãn gốc. Mô hình downstream là HistGradientBoosting (có sẵn trong sklearn).

Lấy mẫu con (để chạy nhiều seed trong thời gian cho phép): Credit Card giữ NGUYÊN 492 dòng gian
lận + lấy ngẫu nhiên dòng bình thường cho đủ --max-rows (nên tỉ lệ gian lận trong mẫu cao hơn 0,17%
của bộ gốc -- phải ghi rõ khi báo cáo); các bộ khác lấy mẫu phân tầng. Mẫu con cố định (seed 0) giữa các lần chạy.

Chạy:  python3 evaluate_class_noise_multiseed.py --seeds 5
Kết quả ghi nối vào file .jsonl (chạy lại sẽ BỎ QUA các ô đã xong -> có thể ngắt giữa chừng).
"""

import argparse
import json
import os
import time

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, f1_score, matthews_corrcoef
from sklearn.model_selection import StratifiedKFold, cross_val_predict, train_test_split

from attribute_noise.pipeline import load_data
from class_noise.config import ClassNoiseConfig
from class_noise.confident_learning import detect_class_noise
from class_noise.distance_based import detect_class_noise_distance
from class_noise.ensemble_based import detect_class_noise_ensemble
from class_noise.feature_selection import log_transform
from evaluate_creditcard_noise_injection import fast_cap_outliers, prf

LABEL_COL = "__label__"

DATASETS = {
    "creditcard": dict(path="data/kaggle_creditcard_fraud.csv", label="Class", keep_minority=True),
    "adult": dict(path="data/kaggle_adult_income.csv", label="income", keep_minority=False),
    "thay": dict(path="data/class_noise_train.csv", label="V153", keep_minority=False),
}


# --------------------------------------------------------------------------------------
# Dữ liệu
# --------------------------------------------------------------------------------------
def load_dataset(name: str, max_rows: int) -> tuple[pd.DataFrame, pd.Series, str]:
    """Trả (X số đã cap outlier + log1p như luồng web, y chuỗi, nhãn lớp hiếm)."""
    spec = DATASETS[name]
    raw = load_data(spec["path"])
    label = spec["label"]
    y_all = raw[label].astype(str).str.strip()
    raw = raw[y_all != ""].reset_index(drop=True)
    y_all = raw[label].astype(str).str.strip()
    features = [
        c for c in raw.columns
        if c != label and pd.to_numeric(raw[c], errors="coerce").notna().mean() >= 0.9
    ]
    rng = np.random.default_rng(0)
    if len(raw) > max_rows:
        if spec["keep_minority"]:
            minority = y_all.value_counts().idxmin()
            keep_idx = raw.index[y_all == minority].to_numpy()
            rest = raw.index[y_all != minority].to_numpy()
            take = rng.choice(rest, size=max(0, max_rows - len(keep_idx)), replace=False)
            idx = np.sort(np.concatenate([keep_idx, take]))
        else:
            frac = max_rows / len(raw)
            idx = np.sort(np.concatenate([
                rng.choice(g.index.to_numpy(), size=max(2, int(round(len(g) * frac))), replace=False)
                for _, g in raw.groupby(y_all)
            ]))
        raw = raw.loc[idx].reset_index(drop=True)
        y_all = raw[label].astype(str).str.strip()
    cleaned = fast_cap_outliers(raw[features], features)
    cleaned = log_transform(cleaned, features)
    for c in features:
        cleaned[c] = pd.to_numeric(cleaned[c], errors="coerce")
    ok = cleaned.notna().all(axis=1)
    X = cleaned[ok].reset_index(drop=True)
    y = y_all[ok].reset_index(drop=True)
    minority = y.value_counts().idxmin()
    return X, y, minority


# --------------------------------------------------------------------------------------
# Cấy nhiễu
# --------------------------------------------------------------------------------------
def inject_noise(X: pd.DataFrame, y: pd.Series, minority: str, scheme: str, rate: float, seed: int):
    """Trả (nhãn đã đảo, tập vị trí dòng bị đảo). Chỉ hỗ trợ bài toán 2 lớp."""
    classes = sorted(y.unique())
    if len(classes) != 2:
        raise ValueError("chỉ hỗ trợ 2 lớp")
    other = {classes[0]: classes[1], classes[1]: classes[0]}
    rng = np.random.default_rng(seed)
    n = len(y)
    if scheme == "A":
        flip = rng.choice(n, size=int(round(n * rate)), replace=False)
    elif scheme == "B":
        mi = np.where(y == minority)[0]
        ma = np.where(y != minority)[0]
        k = int(round(len(mi) * rate))
        flip = np.concatenate([rng.choice(mi, size=k, replace=False), rng.choice(ma, size=k, replace=False)])
    elif scheme == "IDN":
        # mẫu càng KHÓ (mô hình tham chiếu càng ít tin vào nhãn thật) càng dễ bị đảo.
        # Mô hình tham chiếu = HistGradientBoosting out-of-fold, khác họ với 3 thuật toán được đo.
        yb = (y == minority).astype(int).to_numpy()
        proba = cross_val_predict(
            HistGradientBoostingClassifier(random_state=seed), X, yb,
            cv=StratifiedKFold(3, shuffle=True, random_state=seed), method="predict_proba",
        )[:, 1]
        p_true = np.where(yb == 1, proba, 1 - proba)
        w = (1 - p_true) + 1e-3
        flip = rng.choice(n, size=int(round(n * rate)), replace=False, p=w / w.sum())
    else:
        raise ValueError(scheme)
    noisy = y.copy()
    noisy.iloc[flip] = y.iloc[flip].map(other).to_numpy()
    return noisy, set(int(i) for i in flip)


# --------------------------------------------------------------------------------------
# Thuật toán phát hiện: trả {vị trí dòng: (nhãn ghi, nhãn gợi ý)}
# --------------------------------------------------------------------------------------
def run_method(name: str, X: pd.DataFrame, noisy: pd.Series, seed: int, single_trees: int, k: int):
    features = list(X.columns)
    df = X.copy()
    df[LABEL_COL] = noisy.to_numpy()
    cfg = ClassNoiseConfig(label_column=LABEL_COL, feature_columns=features,
                           n_estimators=single_trees, random_state=seed)
    t = time.time()
    if name == "single":
        res = detect_class_noise(df, cfg)
        flagged = {f.row_number - 1: (f.recorded_label, f.confident_label) for f in res.findings}
    elif name == "distance":
        res = detect_class_noise_distance(df, cfg, k=k)
        flagged = {f.row_number - 1: (f.recorded_label, f.suggested_label) for f in res.findings}
    elif name == "ensemble":
        res = detect_class_noise_ensemble(df, cfg, random_state=seed)
        flagged = {f.row_number - 1: (f.recorded_label, f.suggested_label) for f in res.findings}
    elif name == "naive_cv":
        # đối chứng "sklearn thuần": 1 mô hình, dự đoán out-of-fold, khác nhãn ghi là gắn cờ
        pred = cross_val_predict(
            HistGradientBoostingClassifier(random_state=seed), X, noisy,
            cv=StratifiedKFold(5, shuffle=True, random_state=seed),
        )
        bad = np.where(pred != noisy.to_numpy())[0]
        flagged = {int(i): (noisy.iloc[i], pred[i]) for i in bad}
    else:
        raise ValueError(name)
    return flagged, time.time() - t


# --------------------------------------------------------------------------------------
# Chấm điểm
# --------------------------------------------------------------------------------------
def detection_scores(flagged: dict, flipped: set) -> dict:
    fs = set(flagged)
    return prf(len(fs & flipped), len(fs - flipped), len(flipped - fs))


def downstream(Xtr, ytr, Xte, yte, minority, seed) -> dict | None:
    """Huấn luyện HistGradientBoosting trên (Xtr, ytr) rồi chấm trên tập test SẠCH."""
    if ytr.nunique() < 2:
        return None
    model = HistGradientBoostingClassifier(random_state=seed)
    model.fit(Xtr, (ytr == minority).astype(int))
    proba = model.predict_proba(Xte)[:, 1]
    truth = (yte == minority).astype(int)
    pred = proba >= 0.5
    return {
        "pr_auc": float(average_precision_score(truth, proba)),
        "f1": float(f1_score(truth, pred, zero_division=0)),
        "mcc": float(matthews_corrcoef(truth, pred)),
    }


def downstream_variants(Xtr, ytr_clean, noisy, flagged, Xte, yte, minority, seed) -> dict:
    keep = np.ones(len(noisy), dtype=bool)
    keep[list(flagged)] = False
    relabeled = noisy.copy()
    for i, (_, suggested) in flagged.items():
        relabeled.iloc[i] = suggested
    return {
        "filtered": downstream(Xtr[keep], noisy[keep], Xte, yte, minority, seed),
        "relabeled": downstream(Xtr, relabeled, Xte, yte, minority, seed),
    }


# --------------------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--datasets", default="creditcard,adult,thay")
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--scenarios", default="A:0.10,B:0.30,IDN:0.10")
    ap.add_argument("--methods", default="naive_cv,ensemble,distance,single")
    ap.add_argument("--max-rows", type=int, default=30000)
    ap.add_argument("--single-trees", type=int, default=100)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--out", default="data/class_noise_multiseed_results.jsonl")
    args = ap.parse_args()

    done = set()
    if os.path.exists(args.out):
        for line in open(args.out, encoding="utf-8"):
            r = json.loads(line)
            done.add(r["key"])

    def emit(rec: dict) -> None:
        with open(args.out, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        done.add(rec["key"])

    scenarios = [(s.split(":")[0], float(s.split(":")[1])) for s in args.scenarios.split(",")]
    methods = args.methods.split(",")
    for ds in args.datasets.split(","):
        X, y, minority = load_dataset(ds, args.max_rows)
        print(f"\n=== {ds}: {len(X)} dòng x {X.shape[1]} cột, lớp hiếm '{minority}' = "
              f"{(y == minority).mean():.2%} ===", flush=True)
        for seed in range(args.seeds):
            Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.3, stratify=y, random_state=seed)
            Xtr, Xte = Xtr.reset_index(drop=True), Xte.reset_index(drop=True)
            ytr, yte = ytr.reset_index(drop=True), yte.reset_index(drop=True)
            for scheme, rate in scenarios:
                tag = f"{ds}|{seed}|{scheme}:{rate}"
                if all(f"{tag}|{m}" in done for m in methods + ["_ref"]):
                    continue
                noisy, flipped = inject_noise(Xtr, ytr, minority, scheme, rate, seed)
                base = dict(dataset=ds, seed=seed, scheme=scheme, rate=rate, n_train=len(Xtr),
                            n_flipped=len(flipped), minority_rate=float((y == minority).mean()))
                if f"{tag}|_ref" not in done:
                    emit({**base, "key": f"{tag}|_ref", "method": "_ref",
                          "downstream": {
                              "noisy": downstream(Xtr, noisy, Xte, yte, minority, seed),
                              "oracle": downstream(Xtr, ytr, Xte, yte, minority, seed)}})
                for m in methods:
                    if f"{tag}|{m}" in done:
                        continue
                    flagged, secs = run_method(m, Xtr, noisy, seed, args.single_trees, args.k)
                    det = detection_scores(flagged, flipped)
                    ds_scores = downstream_variants(Xtr, ytr, noisy, flagged, Xte, yte, minority, seed)
                    emit({**base, "key": f"{tag}|{m}", "method": m, "seconds": round(secs, 1),
                          "n_flagged": len(flagged), "detection": det, "downstream": ds_scores})
                    print(f"[{ds} s{seed} {scheme}:{rate}] {m:<9} flag={len(flagged):>6} "
                          f"P={det['precision']:.3f} R={det['recall']:.3f} F1={det['f1']:.3f} ({secs:.0f}s)",
                          flush=True)


if __name__ == "__main__":
    main()
