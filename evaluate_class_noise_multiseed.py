"""
KHUNG THÍ NGHIỆM CLASS NOISE (nhiều seed, nhiều bộ dữ liệu, nhiễu IDN, đo DOWNSTREAM) -- BẢN V2
(kế hoạch mục 5, 22/11/2026).

Trả lời góp ý "thực nghiệm chưa đủ tin cậy": thay vì 1 bộ dữ liệu + 1 seed + chỉ đo "tìm lại
được bao nhiêu nhãn sai", script này chạy:
  - 4 bộ dữ liệu: Credit Card (lệch lớp rất nặng), Adult (6 cột số, lệch vừa), dữ liệu thầy (3 cột
    yếu), Car Evaluation (nhãn sinh từ luật => nhãn gốc đúng 100%, 2 lớp: unacc+acc = 0, good+vgood = 1).
  - nhiều seed (mean ± std và kiểm định Wilcoxon ở summarize_class_noise_multiseed.py).
  - 3 kiểu nhiễu: A (đảo đồng đều), B (đảo lớp hiếm + số bằng vậy từ lớp đa số),
    IDN (Instance-Dependent Noise: nhãn của các mẫu KHÓ -- sát ranh giới quyết định -- dễ bị đảo hơn).
  - các phương pháp:
      * đối chứng: naive_cv (1 mô hình HistGradientBoosting dự đoán out-of-fold, gắn cờ dòng đoán
        khác nhãn ghi), enn (Edited Nearest Neighbours, Wilson 1972, k = 3, không lọc láng giềng lẫn nhau);
      * 3 phương pháp của hệ thống: single (Confident Learning), distance (Mutual k-NN), ensemble;
      * biến thể để đo (chỉ đo phát hiện, không đo downstream): distance_auto (k theo độ phủ), distance_w
        (bỏ phiếu theo khoảng cách), distance_l1 (Manhattan), distance_raw (không cap outlier + log);
      * combined_a<alpha>: bộ kết hợp (class_noise/combined.py), alpha = 0 là "công tắc", alpha > 0 là
        "pha trộn". Gộp từ ĐIỂM ĐÃ LƯU nên không phải chạy lại 3 phương pháp.
  - 3 nhóm thước đo:
      (1) PHÁT HIỆN theo luật gắn cờ riêng của mỗi phương pháp: Precision / Recall / F1 (phụ thuộc
          SỐ DÒNG bị gắn cờ nên không so công bằng giữa phương pháp gắn cờ nhiều và ít dòng);
      (2) XẾP HẠNG không phụ thuộc số dòng gắn cờ: ap (average precision khi xếp dòng theo điểm nghi
          ngờ, dương tính = dòng bị đảo) và p_at_k (precision ở K = số dòng thật sự bị đảo, hoà điểm
          thì lấy kỳ vọng) -- đây là thước đo nên dùng khi so các phương pháp với nhau;
      (3) DOWNSTREAM: huấn luyện CÙNG 1 mô hình trên 4 bản tập train rồi chấm trên tập TEST SẠCH:
          (a) chưa làm sạch (b) lọc bỏ dòng bị gắn cờ (c) sửa nhãn theo gợi ý (d) nhãn gốc sạch (Oracle).

Giao thức mỗi (bộ dữ liệu, seed): chia train/test 70/30 phân tầng; nhiễu CHỈ cấy vào nhãn train;
test giữ nhãn gốc. Mô hình downstream là HistGradientBoosting (có sẵn trong sklearn).

Đặc trưng theo ĐÚNG luồng web (xem CLAUDE.md, kế hoạch mục 3): Confident Learning dùng giá trị THÔ;
Mutual k-NN, Ensemble và ENN dùng đặc trưng đã cap outlier (IQR 1,5) + log1p.

Chọn alpha cho bộ kết hợp: KHÔNG chọn ở đây. Script này tính combined cho cả lưới alpha ở MỌI seed;
summarize_class_noise_multiseed.py chọn alpha trên seed 0 rồi giữ cố định khi báo cáo các seed còn lại
(để không tinh chỉnh theo đúng dữ liệu đang đánh giá).

Lấy mẫu con (để chạy nhiều seed trong thời gian cho phép): Credit Card giữ NGUYÊN 492 dòng gian
lận + lấy ngẫu nhiên dòng bình thường cho đủ --max-rows (nên tỉ lệ gian lận trong mẫu cao hơn 0,17%
của bộ gốc -- phải ghi rõ khi báo cáo); các bộ khác lấy mẫu phân tầng. Mẫu con cố định (seed 0) giữa các lần chạy.

Chạy:  python3 evaluate_class_noise_multiseed.py --seeds 5
Kết quả ghi nối vào file .jsonl (chạy lại sẽ BỎ QUA các ô đã xong -> có thể ngắt giữa chừng); điểm từng
dòng của mỗi phương pháp lưu ở --scores-dir (mỗi ô 1 file .npz) để gộp lại không phải chạy lại.
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
from class_noise.combined import (MethodOutput, combine_methods, from_distance, from_ensemble, from_ensemble_diverse,
                                  from_single)
from class_noise.config import ClassNoiseConfig
from class_noise.confident_learning import detect_class_noise
from class_noise.distance_based import _neighbor_table, _scale_features, detect_class_noise_distance
from class_noise.ensemble_based import detect_class_noise_ensemble
from class_noise.ensemble_diverse import detect_class_noise_ensemble_diverse
from class_noise.feature_selection import log_transform
from evaluate_creditcard_noise_injection import fast_cap_outliers, prf

LABEL_COL = "__label__"

DATASETS = {
    "creditcard": dict(path="data/kaggle_creditcard_fraud.csv", label="Class", keep_minority=True),
    "adult": dict(path="data/kaggle_adult_income.csv", label="income", keep_minority=False),
    "thay": dict(path="data/class_noise_train.csv", label="V153", keep_minority=False),
    "car": dict(path="data/car_evaluation.csv", label="class", keep_minority=False),
}

# Car Evaluation: đổi chữ sang số THEO THỨ TỰ tự nhiên của từng thuộc tính; nhãn gộp 2 lớp THEO THỨ TỰ
# (unacc+acc = 0, good+vgood = 1). KHÔNG gộp lệch thứ tự vì làm hỏng phép thử (nhãn sinh từ luật DEX).
CAR_ENCODING = {
    "buying": {"low": 1, "med": 2, "high": 3, "vhigh": 4},
    "maint": {"low": 1, "med": 2, "high": 3, "vhigh": 4},
    "doors": {"2": 2, "3": 3, "4": 4, "5more": 5},
    "persons": {"2": 2, "4": 4, "more": 5},
    "lug_boot": {"small": 1, "med": 2, "big": 3},
    "safety": {"low": 1, "med": 2, "high": 3},
}
CAR_LABEL = {"unacc": "0", "acc": "0", "good": "1", "vgood": "1"}

# Tên khoá trong file kết quả -> tên phương pháp mà combined.py dùng (để phá hoà trọng số đúng thứ tự).
COMBINED_NAMES = {"single": "single_learning", "distance": "distance_based", "ensemble": "ensemble_based",
                  "ensemble5": "ensemble_based"}
BASE_METHODS = ["naive_cv", "enn", "single", "distance", "ensemble"]
VARIANT_METHODS = ["distance_auto", "distance_w", "distance_l1", "distance_raw"]
# Ensemble 5 họ (kế hoạch mục 7) KHÔNG nằm trong danh sách mặc định: bật bằng --methods ...,ensemble5. Một lần chạy cho ra
# cả mức bỏ phiếu 3/5 (ensemble5) lẫn 4/5, 5/5 (ensemble5_v4, ensemble5_v5, tính lại từ số phiếu đã lưu).
ENSEMBLE5_VARIANTS = ["ensemble5_v4", "ensemble5_v5"]
NO_DOWNSTREAM = set(VARIANT_METHODS) | set(ENSEMBLE5_VARIANTS)  # biến thể chỉ để so phát hiện, bỏ downstream cho nhanh


# --------------------------------------------------------------------------------------
# Dữ liệu
# --------------------------------------------------------------------------------------
def load_car() -> pd.DataFrame:
    """Đọc Car Evaluation, đổi sang số theo thứ tự tự nhiên, gộp 2 nhãn. Trả DataFrame dạng chuỗi."""
    df = pd.read_csv(DATASETS["car"]["path"], dtype=str)
    for col, mapping in CAR_ENCODING.items():
        coded = df[col].map(mapping)
        if coded.isna().any():
            raise ValueError(f"Car: cột {col} có giá trị lạ ngoài {list(mapping)}")
        df[col] = coded.astype(int).astype(str)
    label = df["class"].map(CAR_LABEL)
    if label.isna().any():
        raise ValueError("Car: nhãn lạ ngoài unacc/acc/good/vgood")
    df["class"] = label
    return df


def load_dataset(name: str, max_rows: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, str]:
    """Trả (X_prep, X_raw, y, nhãn lớp hiếm).

    X_prep = đặc trưng đã cap outlier + log1p (cho Mutual k-NN / Ensemble / ENN, như luồng web);
    X_raw  = cùng các dòng, giá trị THÔ (cho Confident Learning và mô hình downstream/naive_cv).
    """
    spec = DATASETS[name]
    raw = load_car() if name == "car" else load_data(spec["path"])
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
    capped = fast_cap_outliers(raw[features], features)
    prepped = log_transform(capped, features)
    raw_num = raw[features].apply(pd.to_numeric, errors="coerce")
    for c in features:
        prepped[c] = pd.to_numeric(prepped[c], errors="coerce")
    ok = prepped.notna().all(axis=1) & raw_num.notna().all(axis=1)
    X_prep = prepped[ok].reset_index(drop=True)
    X_raw = raw_num[ok].reset_index(drop=True)
    y = y_all[ok].reset_index(drop=True)
    minority = y.value_counts().idxmin()
    return X_prep, X_raw, y, minority


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
# Các phương pháp: mỗi phương pháp trả 1 MethodOutput (điểm cho MỌI dòng + cờ + nhãn gợi ý)
# --------------------------------------------------------------------------------------
def _other_label(noisy: pd.Series) -> np.ndarray:
    """Bài toán 2 lớp: nhãn gợi ý duy nhất có thể = lớp còn lại."""
    classes = np.array(sorted(noisy.unique()))
    idx = np.searchsorted(classes, noisy.to_numpy())
    return classes[1 - idx]


def run_naive_cv(Xr: pd.DataFrame, noisy: pd.Series, seed: int) -> MethodOutput:
    """Đối chứng "sklearn thuần": 1 mô hình, xác suất out-of-fold; điểm = 1 - P(nhãn ghi)."""
    proba = cross_val_predict(
        HistGradientBoostingClassifier(random_state=seed), Xr, noisy,
        cv=StratifiedKFold(5, shuffle=True, random_state=seed), method="predict_proba",
    )
    classes = np.array(sorted(noisy.unique()))
    rec_idx = np.searchsorted(classes, noisy.to_numpy())
    p_rec = proba[np.arange(len(noisy)), rec_idx]
    flagged = proba.argmax(axis=1) != rec_idx
    n = len(noisy)
    return MethodOutput("naive_cv", np.arange(1, n + 1), 1.0 - p_rec, flagged, _other_label(noisy).astype(object))


def run_enn(Xp: pd.DataFrame, noisy: pd.Series, k: int = 3) -> MethodOutput:
    """Edited Nearest Neighbours (Wilson 1972): dòng bị gắn cờ nếu đa số k láng giềng gần nhất mang nhãn khác.

    KHÁC Mutual k-NN ở chỗ dùng MỌI k láng giềng (không lọc quan hệ 2 chiều). Cùng cách chuẩn hoá đặc trưng
    với Mutual k-NN để chỉ khác nhau đúng ở luật gắn cờ.
    """
    X, _ = _scale_features(Xp.to_numpy(float), keep_binary=True)
    idx, _dist = _neighbor_table(X, k, "euclidean")
    labels = noisy.to_numpy()
    diff = (labels[idx] != labels[:, None]).mean(axis=1)
    n = len(noisy)
    return MethodOutput("enn", np.arange(1, n + 1), diff, diff > 0.5, _other_label(noisy).astype(object))


def run_method(name: str, Xp: pd.DataFrame, Xr: pd.DataFrame, noisy: pd.Series, seed: int, trees: int, k: int):
    """Chạy 1 phương pháp. Trả (MethodOutput, giây)."""
    t = time.time()
    if name == "naive_cv":
        out = run_naive_cv(Xr, noisy, seed)
    elif name == "enn":
        out = run_enn(Xp, noisy)
    elif name == "single":
        df = Xr.copy(); df[LABEL_COL] = noisy.to_numpy()
        cfg = ClassNoiseConfig(LABEL_COL, list(Xr.columns), n_estimators=trees, random_state=seed)
        out = from_single(detect_class_noise(df, cfg))
    elif name == "ensemble":
        df = Xp.copy(); df[LABEL_COL] = noisy.to_numpy()
        cfg = ClassNoiseConfig(LABEL_COL, list(Xp.columns), random_state=seed)
        out = from_ensemble(detect_class_noise_ensemble(df, cfg, random_state=seed))
    elif name.startswith("distance"):
        feats = Xr if name == "distance_raw" else Xp
        df = feats.copy(); df[LABEL_COL] = noisy.to_numpy()
        cfg = ClassNoiseConfig(LABEL_COL, list(feats.columns))
        kw = {"distance_auto": dict(k="auto"), "distance_w": dict(k=k, weighting="distance"),
              "distance_l1": dict(k=k, metric="manhattan")}.get(name, dict(k=k))
        out = from_distance(detect_class_noise_distance(df, cfg, **kw))
    else:
        raise ValueError(name)
    return out, time.time() - t


def run_ensemble5(Xp: pd.DataFrame, noisy: pd.Series, seed: int):
    """Ensemble 5 họ. Trả (MethodOutput mức 3/5, MethodOutput lưu SỐ PHIẾU để suy ra mức 4/5 và 5/5, giây, thông tin đa dạng)."""
    t = time.time()
    df = Xp.copy()
    df[LABEL_COL] = noisy.to_numpy()
    cfg = ClassNoiseConfig(LABEL_COL, list(Xp.columns), random_state=seed)
    res = detect_class_noise_ensemble_diverse(df, cfg, random_state=seed)
    s = res.scores
    votes = MethodOutput("ensemble5_votes", s.row_numbers, s.votes.astype(float), s.votes >= 3, s.suggested_labels)
    info = {"mean_agreement": res.diagnostics.mean_pairwise_agreement,
            "best_excess": res.diagnostics.best_excess_over_baseline,
            "excess": res.diagnostics.per_classifier_excess,
            "pairwise": res.diagnostics.pairwise_agreement.round(4).to_dict()}
    return from_ensemble_diverse(res), votes, time.time() - t, info


def derive_vote_variant(base: MethodOutput, votes: MethodOutput, min_votes: int) -> MethodOutput:
    """Cùng điểm xếp hạng với `base`, chỉ đổi luật gắn cờ sang 'ít nhất min_votes/5 mô hình phản đối nhãn ghi'."""
    return MethodOutput(base.name, base.row_numbers, base.scores, votes.scores >= min_votes, base.suggested_labels,
                        base.quality, base.always_on, base.note)


# --------------------------------------------------------------------------------------
# Lưu / đọc điểm từng phương pháp (mỗi ô thí nghiệm 1 file .npz)
# --------------------------------------------------------------------------------------
def save_cell(path: str, outs: dict[str, MethodOutput], flipped_mask: np.ndarray, noisy: pd.Series) -> None:
    arrays = {"flipped": flipped_mask, "noisy": noisy.to_numpy().astype(str)}
    for m, o in outs.items():
        arrays[f"{m}__rows"] = np.asarray(o.row_numbers)
        arrays[f"{m}__score"] = np.asarray(o.scores, dtype=float)
        arrays[f"{m}__flag"] = np.asarray(o.flagged, dtype=bool)
        arrays[f"{m}__sug"] = np.asarray(o.suggested_labels).astype(str)
        arrays[f"{m}__q"] = np.array([np.nan if o.quality is None else o.quality])
        arrays[f"{m}__on"] = np.array([o.always_on])
    np.savez_compressed(path, **arrays)


def load_cell(path: str) -> dict[str, MethodOutput]:
    if not os.path.exists(path):
        return {}
    z = np.load(path, allow_pickle=False)
    outs = {}
    for m in sorted({k.split("__")[0] for k in z.files if "__" in k}):
        q = float(z[f"{m}__q"][0])
        outs[m] = MethodOutput(
            name=COMBINED_NAMES.get(m, m), row_numbers=z[f"{m}__rows"], scores=z[f"{m}__score"],
            flagged=z[f"{m}__flag"], suggested_labels=z[f"{m}__sug"].astype(object),
            quality=None if np.isnan(q) else q, always_on=bool(z[f"{m}__on"][0]),
        )
    return outs


# --------------------------------------------------------------------------------------
# Chấm điểm
# --------------------------------------------------------------------------------------
def expected_p_at_k(score: np.ndarray, truth: np.ndarray, k: int) -> float:
    """Precision của k dòng điểm cao nhất; các dòng hoà điểm ở biên được tính theo KỲ VỌNG (không phụ thuộc thứ tự dòng)."""
    if k <= 0:
        return float("nan")
    thr = np.sort(score)[::-1][k - 1]
    above, ties = score > thr, score == thr
    slots = k - int(above.sum())
    frac = truth[ties].mean() if ties.any() else 0.0
    return float((truth[above].sum() + slots * frac) / k)


def scores_to_full(row_numbers: np.ndarray, values: np.ndarray, n: int) -> np.ndarray:
    full = np.full(n, np.nan)
    full[np.asarray(row_numbers) - 1] = values
    return full


def ranking_scores(score_full: np.ndarray, flipped_mask: np.ndarray) -> dict:
    """AP và P@K của việc xếp dòng theo điểm nghi ngờ (dòng không có điểm xếp cuối)."""
    s = score_full.copy()
    s[np.isnan(s)] = (np.nanmin(s) - 1.0) if (~np.isnan(s)).any() else 0.0
    return {"ap": float(average_precision_score(flipped_mask, s)),
            "p_at_k": expected_p_at_k(s, flipped_mask, int(flipped_mask.sum()))}


def flagged_dict(rows: np.ndarray, flag: np.ndarray, sug: np.ndarray, noisy: pd.Series) -> dict:
    """{vị trí dòng: (nhãn ghi, nhãn gợi ý)} cho các dòng bị gắn cờ."""
    idx = np.asarray(rows)[np.asarray(flag)] - 1
    return {int(i): (noisy.iloc[i], str(sug[np.asarray(rows) == i + 1][0])) for i in idx}


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


def downstream_variants(Xtr, noisy, flagged, Xte, yte, minority, seed) -> dict:
    keep = np.ones(len(noisy), dtype=bool)
    if flagged:
        keep[np.array(list(flagged), dtype=int)] = False
    relabeled = noisy.copy()
    for i, (recorded, suggested) in flagged.items():
        if suggested not in ("", recorded):  # không có gợi ý thì giữ nguyên nhãn
            relabeled.iloc[i] = suggested
    return {
        "filtered": downstream(Xtr[keep], noisy[keep], Xte, yte, minority, seed),
        "relabeled": downstream(Xtr, relabeled, Xte, yte, minority, seed),
    }


def _clean(obj):
    """Đổi NaN/inf thành None để file .jsonl là JSON hợp lệ."""
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, (float, np.floating)):
        return None if not np.isfinite(obj) else float(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    return obj


# --------------------------------------------------------------------------------------
def evaluate_output(out: MethodOutput, noisy, flipped, flipped_mask, Xr_tr, Xte, yte, minority, seed, with_downstream):
    """Chấm 1 MethodOutput: phát hiện (luật riêng), xếp hạng (AP, P@K), downstream. Trả dict các trường kết quả."""
    n = len(noisy)
    flagged = flagged_dict(out.row_numbers, out.flagged, out.suggested_labels, noisy)
    rec = {"n_flagged": len(flagged), "detection": detection_scores(flagged, flipped),
           "ranking": ranking_scores(scores_to_full(out.row_numbers, out.scores, n), flipped_mask),
           "quality": out.quality}
    rec["downstream"] = downstream_variants(Xr_tr, noisy, flagged, Xte, yte, minority, seed) if with_downstream else None
    return rec


def combined_output(outs: dict, noisy: pd.Series, alpha: float, ensemble_key: str = "ensemble", prefix: str = "combined"):
    """Gộp 3 phương pháp đã lưu bằng combine_methods. Trả (MethodOutput đại diện, CombinedResult).

    ensemble_key="ensemble5" (prefix="combined5") thay Ensemble cũ bằng Ensemble 5 họ trong bộ kết hợp."""
    n = len(noisy)
    recorded = pd.Series(noisy.to_numpy(), index=np.arange(1, n + 1))
    res = combine_methods([outs["single"], outs["distance"], outs[ensemble_key]], alpha=alpha, recorded_labels=recorded)
    flag = np.zeros(n, dtype=bool)
    sug = np.full(n, "", dtype=object)
    for f in res.findings:
        flag[f.row_number - 1] = True
        sug[f.row_number - 1] = f.suggested_label
    out = MethodOutput(f"{prefix}_a{alpha:g}", res.scores.row_numbers, res.scores.score, flag[res.scores.row_numbers - 1],
                       sug[res.scores.row_numbers - 1])
    return out, res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--datasets", default="car,adult,thay,creditcard")
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--scenarios", default="A:0.10,B:0.30,IDN:0.10")
    ap.add_argument("--methods", default=",".join(BASE_METHODS))
    ap.add_argument("--variants", default=",".join(VARIANT_METHODS), help="biến thể chỉ đo phát hiện; rỗng = bỏ")
    ap.add_argument("--alphas", default="0,0.25,0.5,0.75,1", help="lưới alpha của bộ kết hợp; rỗng = bỏ combined")
    ap.add_argument("--max-rows", type=int, default=30000)
    ap.add_argument("--single-trees", type=int, default=100)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--out", default="data/class_noise_multiseed_v2.jsonl")
    ap.add_argument("--scores-dir", default="data/class_noise_scores_v2")
    args = ap.parse_args()
    os.makedirs(args.scores_dir, exist_ok=True)

    done = set()
    if os.path.exists(args.out):
        for line in open(args.out, encoding="utf-8"):
            done.add(json.loads(line)["key"])

    def emit(rec: dict) -> None:
        with open(args.out, "a", encoding="utf-8") as f:
            f.write(json.dumps(_clean(rec), ensure_ascii=False) + "\n")
        done.add(rec["key"])

    scenarios = [(s.split(":")[0], float(s.split(":")[1])) for s in args.scenarios.split(",")]
    methods = [m for m in args.methods.split(",") if m] + [m for m in args.variants.split(",") if m]
    alphas = [float(a) for a in args.alphas.split(",") if a != ""]
    combined_names = [f"combined_a{a:g}" for a in alphas]
    need_combined = bool(alphas) and all(m in methods for m in ("single", "distance", "ensemble"))
    use_e5 = "ensemble5" in methods  # Ensemble 5 họ (mục 7): thêm mức phiếu 4/5, 5/5 và bộ kết hợp thay Ensemble cũ bằng nó
    combined5_names = [f"combined5_a{a:g}" for a in alphas] if use_e5 else []

    for ds in args.datasets.split(","):
        Xp, Xr, y, minority = load_dataset(ds, args.max_rows)
        print(f"\n=== {ds}: {len(Xp)} dòng x {Xp.shape[1]} cột, lớp hiếm '{minority}' = "
              f"{(y == minority).mean():.2%} ===", flush=True)
        for seed in range(args.seeds):
            Xp_tr, Xp_te, Xr_tr, Xr_te, ytr, yte = train_test_split(Xp, Xr, y, test_size=0.3, stratify=y, random_state=seed)
            Xp_tr, Xr_tr, Xr_te = (d.reset_index(drop=True) for d in (Xp_tr, Xr_tr, Xr_te))
            ytr, yte = ytr.reset_index(drop=True), yte.reset_index(drop=True)
            for scheme, rate in scenarios:
                tag = f"{ds}|{seed}|{scheme}:{rate}"
                wanted = (methods + (ENSEMBLE5_VARIANTS if use_e5 else []) + (combined_names if need_combined else [])
                          + combined5_names + ["_ref"])
                if all(f"{tag}|{m}" in done for m in wanted):
                    continue
                noisy, flipped = inject_noise(Xr_tr, ytr, minority, scheme, rate, seed)
                flipped_mask = np.zeros(len(ytr), dtype=bool)
                flipped_mask[list(flipped)] = True
                base = dict(dataset=ds, seed=seed, scheme=scheme, rate=rate, n_train=len(Xr_tr),
                            n_flipped=len(flipped), minority_rate=float((y == minority).mean()))
                npz = os.path.join(args.scores_dir, f"{ds}_{seed}_{scheme}_{rate}.npz")
                outs = load_cell(npz)
                if f"{tag}|_ref" not in done:
                    emit({**base, "key": f"{tag}|_ref", "method": "_ref",
                          "downstream": {"noisy": downstream(Xr_tr, noisy, Xr_te, yte, minority, seed),
                                         "oracle": downstream(Xr_tr, ytr, Xr_te, yte, minority, seed)}})
                for m in methods:
                    if f"{tag}|{m}" in done and m in outs:
                        continue
                    secs, extra = 0.0, None
                    if m not in outs:  # chưa có điểm đã lưu -> chạy thật rồi lưu ngay (ngắt giữa chừng không mất)
                        if m == "ensemble5":
                            outs[m], outs["ensemble5_votes"], secs, extra = run_ensemble5(Xp_tr, noisy, seed)
                        else:
                            outs[m], secs = run_method(m, Xp_tr, Xr_tr, noisy, seed, args.single_trees, args.k)
                        save_cell(npz, outs, flipped_mask, noisy)
                    rec = evaluate_output(outs[m], noisy, flipped, flipped_mask, Xr_tr, Xr_te, yte, minority, seed,
                                          with_downstream=m not in NO_DOWNSTREAM)
                    if extra:
                        rec["ensemble5_info"] = extra  # độ đa dạng + mức vượt mốc từng mô hình (chỉ có ở lần chạy thật)
                    emit({**base, "key": f"{tag}|{m}", "method": m, "seconds": round(secs, 1), **rec})
                    det = rec["detection"]
                    print(f"[{ds} s{seed} {scheme}:{rate}] {m:<14} flag={rec['n_flagged']:>6} "
                          f"P={det['precision']:.3f} R={det['recall']:.3f} F1={det['f1']:.3f} "
                          f"AP={rec['ranking']['ap']:.3f} ({secs:.0f}s)", flush=True)
                if use_e5 and "ensemble5_votes" in outs:  # mức bỏ phiếu 4/5 và 5/5, suy ra từ số phiếu đã lưu (không chạy lại)
                    for v, vname in ((4, "ensemble5_v4"), (5, "ensemble5_v5")):
                        if f"{tag}|{vname}" in done and vname in outs:
                            continue
                        if vname not in outs:
                            outs[vname] = derive_vote_variant(outs["ensemble5"], outs["ensemble5_votes"], v)
                            save_cell(npz, outs, flipped_mask, noisy)
                        rec = evaluate_output(outs[vname], noisy, flipped, flipped_mask, Xr_tr, Xr_te, yte, minority, seed, False)
                        emit({**base, "key": f"{tag}|{vname}", "method": vname, "seconds": 0.0, **rec})
                        det = rec["detection"]
                        print(f"[{ds} s{seed} {scheme}:{rate}] {vname:<14} flag={rec['n_flagged']:>6} "
                              f"P={det['precision']:.3f} R={det['recall']:.3f} F1={det['f1']:.3f} "
                              f"AP={rec['ranking']['ap']:.3f}", flush=True)
                if use_e5 and all(k in outs for k in ("single", "distance", "ensemble5")):
                    for a, cname in zip(alphas, combined5_names):
                        if f"{tag}|{cname}" in done:
                            continue
                        cout, cres = combined_output(outs, noisy, a, ensemble_key="ensemble5", prefix="combined5")
                        rec = evaluate_output(cout, noisy, flipped, flipped_mask, Xr_tr, Xr_te, yte, minority, seed, False)
                        info = {"k_method": cres.diagnostics.k_method,
                                "weights": {m: round(v["weight"], 4) for m, v in cres.diagnostics.methods.items()},
                                "on": {m: v["on"] for m, v in cres.diagnostics.methods.items()}}
                        emit({**base, "key": f"{tag}|{cname}", "method": cname, "alpha": a, "seconds": 0.0, **rec, "combined": info})
                        det = rec["detection"]
                        print(f"[{ds} s{seed} {scheme}:{rate}] {cname:<14} flag={rec['n_flagged']:>6} "
                              f"P={det['precision']:.3f} R={det['recall']:.3f} F1={det['f1']:.3f} "
                              f"AP={rec['ranking']['ap']:.3f} (K từ {info['k_method']})", flush=True)
                if need_combined:
                    for a, cname in zip(alphas, combined_names):
                        if f"{tag}|{cname}" in done:
                            continue
                        cout, cres = combined_output(outs, noisy, a)
                        rec = evaluate_output(cout, noisy, flipped, flipped_mask, Xr_tr, Xr_te, yte, minority, seed, True)
                        info = {"k_method": cres.diagnostics.k_method,
                                "weights": {m: round(v["weight"], 4) for m, v in cres.diagnostics.methods.items()},
                                "on": {m: v["on"] for m, v in cres.diagnostics.methods.items()}}
                        emit({**base, "key": f"{tag}|{cname}", "method": cname, "alpha": a, "seconds": 0.0, **rec, "combined": info})
                        det = rec["detection"]
                        print(f"[{ds} s{seed} {scheme}:{rate}] {cname:<14} flag={rec['n_flagged']:>6} "
                              f"P={det['precision']:.3f} R={det['recall']:.3f} F1={det['f1']:.3f} "
                              f"AP={rec['ranking']['ap']:.3f} (K từ {info['k_method']})", flush=True)


if __name__ == "__main__":
    main()
