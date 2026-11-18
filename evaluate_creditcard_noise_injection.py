"""
THÍ NGHIỆM CẤY NHIỄU NHÃN trên Credit Card Fraud (nguyên bộ 284.807 dòng) cho CẢ 3 thuật toán
Class Noise (Single learning / Distance-based / Ensemble) -- đo xem mỗi thuật toán TÌM LẠI được
bao nhiêu dòng đã bị đảo nhãn có chủ đích (CLAUDE.md mục 35: đây mới là bằng chứng hiệu quả,
các chỉ số trên màn hình web chỉ đo chất lượng model chứ không đo việc tìm nhiễu).

Hai kiểu cấy nhiễu:
  A "đồng đều"        : chọn ngẫu nhiên p% TẤT CẢ dòng rồi đảo nhãn (chuẩn trong các bài báo). Vì gian lận
                        chỉ 0,17%, kiểu này tạo ra rất nhiều "gian lận giả" (p=5% -> ~14.200 dòng).
  B "giữ tỉ lệ lớp hiếm": đảo q% các dòng GIAN LẬN THẬT (1 -> 0) và đảo ĐÚNG BẰNG ẤY dòng bình thường
                        (0 -> 1). Gian lận giả chỉ bằng q% gian lận thật, sát thực tế hơn.

Báo cáo: Precision / Recall / F1 của "dòng thuật toán gắn cờ" so với "dòng đã đảo" (tổng và theo từng
chiều đảo 0->1, 1->0), kèm thời gian chạy. Hai bộ cột: đủ 30 cột, và cột giảm bằng Elbow.

Dòng KHÔNG bị đảo mà vẫn bị gắn cờ được tính là báo nhầm (FP), dù có thể đó là nhiễu thật sẵn có trong
dữ liệu gốc (không có đáp án về nhiễu gốc) -- Precision vì vậy là cận DƯỚI.

Tiền xử lý (cap outlier IQR + log1p) y hệt luồng web, nhưng bước cap dùng bản vector hoá
(`fast_cap_outliers`) vì `cap_outliers()` gốc mất hơn 20 phút cho 30 cột (lặp .loc từng ô). Đã đối chiếu
bản vector hoá với bản gốc trên vài cột (xem `verify_fast_cap`). Đặc trưng không phụ thuộc nhãn nên
chỉ cần tiền xử lý MỘT lần rồi cache ra đĩa.

Chạy: python3 evaluate_creditcard_noise_injection.py --help
"""

import argparse
import json
import os
import time

import numpy as np
import pandas as pd

from attribute_noise.pipeline import load_data
from class_noise.config import ClassNoiseConfig
from class_noise.confident_learning import detect_class_noise
from class_noise.distance_based import detect_class_noise_distance
from class_noise.ensemble_based import detect_class_noise_ensemble
from class_noise.feature_selection import (
    cap_outliers,
    log_transform,
    rank_by_importance,
    select_by_elbow,
)

DATA_PATH = "data/kaggle_creditcard_fraud.csv"
LABEL_COLUMN = "Class"


# --------------------------------------------------------------------------------------
# Tiền xử lý: cap outlier (vector hoá) + log1p, giống luồng web
# --------------------------------------------------------------------------------------
def fast_cap_outliers(df: pd.DataFrame, columns: list[str], threshold: float = 1.5) -> pd.DataFrame:
    """Bản vector hoá của `cap_outliers()` (IQR). Cùng luật: bỏ qua cột IQR = 0; ô ngoài
    [Q1 - k*IQR, Q3 + k*IQR] bị kéo về biên rồi làm tròn 2 chữ số thập phân (như
    `_format_numeric_for_column` với cột FLOAT); ô trong biên giữ nguyên chuỗi gốc."""
    result = df.copy()
    for col in columns:
        numeric = pd.to_numeric(result[col], errors="coerce")
        valid = numeric.dropna()
        q1, q3 = valid.quantile(0.25), valid.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0 or len(valid) < 4:
            continue
        lower, upper = q1 - threshold * iqr, q3 + threshold * iqr
        outlier = numeric.notna() & ((numeric < lower) | (numeric > upper))
        if not outlier.any():
            continue
        capped = numeric[outlier].clip(lower=lower, upper=upper).round(2).astype(str)
        result.loc[outlier, col] = capped
    return result


def verify_fast_cap(df: pd.DataFrame, columns: list[str]) -> None:
    """Đối chiếu bản vector hoá với `cap_outliers()` gốc trên vài cột -- phải ra y hệt từng ô."""
    for col in columns:
        slow = cap_outliers(df, [col])[col]
        fast = fast_cap_outliers(df, [col])[col]
        same = bool((slow == fast).all())
        print(f"  đối chiếu cap cột {col}: {'GIỐNG HỆT' if same else 'KHÁC'}", flush=True)
        if not same:
            raise SystemExit(f"fast_cap_outliers lệch với cap_outliers ở cột {col}")


def prepare_features(cache_path: str, verify_columns: list[str]) -> tuple[pd.DataFrame, list[str]]:
    """Trả (DataFrame đã tiền xử lý, danh sách 30 cột đặc trưng). Có cache để khỏi làm lại."""
    raw = load_data(DATA_PATH)
    feature_columns = [c for c in raw.columns if c != LABEL_COLUMN]
    if os.path.exists(cache_path):
        cached = pd.read_pickle(cache_path)
        return cached, feature_columns

    if verify_columns:
        print("Đối chiếu bản cap vector hoá với bản gốc...", flush=True)
        verify_fast_cap(raw, verify_columns)

    t = time.time()
    cleaned = fast_cap_outliers(raw, feature_columns)
    cleaned = log_transform(cleaned, feature_columns)
    for col in feature_columns:
        cleaned[col] = pd.to_numeric(cleaned[col])
    print(f"Tiền xử lý xong ({time.time() - t:.1f}s), lưu cache {cache_path}", flush=True)
    cleaned.to_pickle(cache_path)
    return cleaned, feature_columns


# --------------------------------------------------------------------------------------
# Cấy nhiễu
# --------------------------------------------------------------------------------------
def inject_noise(labels: pd.Series, scheme: str, rate: float, seed: int) -> tuple[pd.Series, set[int]]:
    """Trả (nhãn đã đảo, tập chỉ số dòng bị đảo). `labels` là chuỗi "0"/"1"."""
    rng = np.random.default_rng(seed)
    noisy = labels.copy()
    if scheme == "A":
        n_flip = int(round(len(labels) * rate))
        flip_idx = rng.choice(labels.index.to_numpy(), size=n_flip, replace=False)
    elif scheme == "B":
        fraud_idx = labels.index[labels == "1"].to_numpy()
        normal_idx = labels.index[labels == "0"].to_numpy()
        n_each = int(round(len(fraud_idx) * rate))
        flip_idx = np.concatenate(
            [
                rng.choice(fraud_idx, size=n_each, replace=False),
                rng.choice(normal_idx, size=n_each, replace=False),
            ]
        )
    else:
        raise ValueError(scheme)
    noisy.loc[flip_idx] = np.where(labels.loc[flip_idx] == "1", "0", "1")
    return noisy, set(int(i) for i in flip_idx)


# --------------------------------------------------------------------------------------
# Chạy thuật toán + tính chỉ số
# --------------------------------------------------------------------------------------
def run_method(name: str, df: pd.DataFrame, features: list[str], single_trees: int, k: int):
    config = ClassNoiseConfig(label_column=LABEL_COLUMN, feature_columns=features, n_estimators=single_trees)
    t = time.time()
    if name == "single":
        result = detect_class_noise(df, config)
        diag = {
            "cv_accuracy": result.diagnostics.cv_accuracy,
            "baseline": result.diagnostics.majority_baseline_accuracy,
        }
        flagged = {f.row_number - 1: (f.recorded_label, f.confident_label) for f in result.findings}
    elif name == "distance":
        result = detect_class_noise_distance(df, config, k=k)
        d = result.diagnostics
        diag = {"k": d.k, "coverage": d.n_rows_with_mutual_neighbors / d.n_rows_used}
        flagged = {f.row_number - 1: (f.recorded_label, f.suggested_label) for f in result.findings}
    elif name == "ensemble":
        result = detect_class_noise_ensemble(df, config)
        d = result.diagnostics
        diag = {"per_classifier_accuracy": d.per_classifier_accuracy, "baseline": d.majority_baseline_accuracy}
        flagged = {f.row_number - 1: (f.recorded_label, f.suggested_label) for f in result.findings}
    else:
        raise ValueError(name)
    return flagged, diag, time.time() - t


def prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * p * r / (p + r) if (p + r) else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": p, "recall": r, "f1": f1}


def score(flagged: dict, flipped: set[int], true_labels: pd.Series) -> dict:
    flagged_set = set(flagged)
    overall = prf(len(flagged_set & flipped), len(flagged_set - flipped), len(flipped - flagged_set))
    # theo chiều đảo: 0->1 = dòng GỐC là 0 (bị đảo thành 1); 1->0 = dòng gốc là 1 (bị đảo thành 0)
    flipped_0to1 = {i for i in flipped if true_labels.loc[i] == "0"}
    flipped_1to0 = {i for i in flipped if true_labels.loc[i] == "1"}
    by_dir = {
        "0to1": {"flipped": len(flipped_0to1), "found": len(flagged_set & flipped_0to1),
                 "recall": len(flagged_set & flipped_0to1) / len(flipped_0to1) if flipped_0to1 else None},
        "1to0": {"flipped": len(flipped_1to0), "found": len(flagged_set & flipped_1to0),
                 "recall": len(flagged_set & flipped_1to0) / len(flipped_1to0) if flipped_1to0 else None},
    }
    # độ chính xác của riêng các cờ theo nhãn ĐANG GHI (sau khi đảo)
    noisy_is_1 = {i for i in flagged_set if flagged[i][0] == "1"}
    noisy_is_0 = flagged_set - noisy_is_1
    by_recorded = {
        "flag_recorded_1": {"flagged": len(noisy_is_1), "correct": len(noisy_is_1 & flipped)},
        "flag_recorded_0": {"flagged": len(noisy_is_0), "correct": len(noisy_is_0 & flipped)},
    }
    return {"overall": overall, "by_direction": by_dir, "by_recorded": by_recorded, "n_flagged": len(flagged_set)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", default="/tmp/creditcard_prepared.pkl")
    ap.add_argument("--out", default="/tmp/creditcard_noise_results.jsonl")
    ap.add_argument("--methods", default="ensemble,distance,single")
    ap.add_argument("--scenarios", default="A:0.05,A:0.10,B:0.10,B:0.30", help="vd A:0.05,B:0.10; baseline = base:0")
    ap.add_argument("--columns", default="all", help="all | reduced | all,reduced")
    ap.add_argument("--single-trees", type=int, default=100)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--verify-cap", default="V1,V14", help="cột đối chiếu cap vector hoá (rỗng = bỏ qua)")
    ap.add_argument("--prepare-only", action="store_true")
    args = ap.parse_args()

    cleaned, all_features = prepare_features(args.cache, [c for c in args.verify_cap.split(",") if c])
    if args.prepare_only:
        return
    true_labels = cleaned[LABEL_COLUMN].astype(str)

    reduced_cache = {}

    def feature_set(kind: str, labels: pd.Series, tag: str) -> list[str]:
        if kind == "all":
            return all_features
        # Elbow dựa trên Random Forest xếp hạng cột theo NHÃN HIỆN CÓ (như nút "Giảm cột tự động")
        if tag not in reduced_cache:
            tmp = cleaned.copy()
            tmp[LABEL_COLUMN] = labels
            t = time.time()
            ranked = rank_by_importance(tmp, LABEL_COLUMN, all_features, n_estimators=args.single_trees)
            reduced_cache[tag] = select_by_elbow(ranked)
            print(f"  [giảm cột {tag}] giữ {len(reduced_cache[tag])} cột: {reduced_cache[tag]} ({time.time() - t:.0f}s)", flush=True)
        return reduced_cache[tag]

    for scen in args.scenarios.split(","):
        scheme, rate_s = scen.split(":")
        rate = float(rate_s)
        if scheme == "base":
            noisy_labels, flipped = true_labels, set()
        else:
            noisy_labels, flipped = inject_noise(true_labels, scheme, rate, args.seed)
        df = cleaned.copy()
        df[LABEL_COLUMN] = noisy_labels
        n1 = int((noisy_labels == "1").sum())
        print(f"\n=== Kịch bản {scen}: đảo {len(flipped)} dòng, nhãn 1 sau khi đảo = {n1} ===", flush=True)
        for kind in args.columns.split(","):
            feats = feature_set(kind, noisy_labels, scen)
            for m in args.methods.split(","):
                flagged, diag, secs = run_method(m, df, feats, args.single_trees, args.k)
                sc = score(flagged, flipped, true_labels) if flipped else {"n_flagged": len(flagged)}
                rec = {"scenario": scen, "columns": kind, "n_features": len(feats), "method": m,
                       "seconds": round(secs, 1), "diag": diag, **sc,
                       "n_flipped": len(flipped), "single_trees": args.single_trees, "k": args.k}
                with open(args.out, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                o = sc.get("overall")
                print(f"  {kind:<7} {m:<9} gắn cờ {sc['n_flagged']:>6}  "
                      + (f"P={o['precision']:.3f} R={o['recall']:.3f} F1={o['f1']:.3f}  " if o else "")
                      + f"({secs:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
