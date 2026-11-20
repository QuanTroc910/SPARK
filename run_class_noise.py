"""
Chạy thuật toán CLASS NOISE ngay trên terminal (không cần mở web).

Ví dụ:
    python3 run_class_noise.py --file data/kaggle_creditcard_fraud.csv \
        --label Class --features V1,V2,V3,V4,V10,V12,V14 --method distance

    python3 run_class_noise.py --file data/class_noise_train.csv \
        --label V153 --features V44,V12,V4 --method single --out ketqua.csv

Ba phương pháp (--method):
    single    Confident Learning + Random Forest (chậm nhất)
    distance  Mutual k-NN, dựa vào khoảng cách (không train model)
    ensemble  3 classifier biểu quyết (LogReg + GaussianNB + LinearSVC)

Giống web: cột đặc trưng phải là cột SỐ, và mặc định tự cap outlier + log
trước khi chạy (thêm --no-prep nếu muốn tắt).
"""

import argparse
import sys
import time

import pandas as pd

from attribute_noise.pipeline import load_data
from class_noise.config import ClassNoiseConfig
from class_noise.confident_learning import detect_class_noise
from class_noise.distance_based import detect_class_noise_distance
from class_noise.ensemble_based import detect_class_noise_ensemble
from class_noise.feature_selection import cap_outliers, log_transform


def parse_args():
    p = argparse.ArgumentParser(description="Phát hiện Class Noise trên terminal")
    p.add_argument("--file", required=True, help="đường dẫn file CSV/Excel")
    p.add_argument("--label", required=True, help="tên cột nhãn")
    p.add_argument("--features", required=True,
                   help="các cột đặc trưng (SỐ), cách nhau bằng dấu phẩy")
    p.add_argument("--method", choices=["single", "distance", "ensemble"],
                   default="distance", help="thuật toán (mặc định: distance)")
    p.add_argument("--n-estimators", type=int, default=300,
                   help="[single] số cây Random Forest")
    p.add_argument("--cv-folds", type=int, default=5,
                   help="[single, ensemble] số fold cross-validation")
    p.add_argument("--k", type=int, default=5, help="[distance] số láng giềng k")
    p.add_argument("--top", type=int, default=20, help="in ra N dòng đáng ngờ nhất")
    p.add_argument("--out", help="ghi TOÀN BỘ dòng nghi ngờ ra file CSV này")
    p.add_argument("--no-prep", action="store_true",
                   help="không cap outlier + log-transform trước khi chạy")
    return p.parse_args()


def main():
    args = parse_args()
    features = [c.strip() for c in args.features.split(",") if c.strip()]

    df = load_data(args.file)
    thieu = [c for c in [args.label, *features] if c not in df.columns]
    if thieu:
        sys.exit(f"Không có cột: {thieu}. Các cột trong file: {list(df.columns)}")

    if not args.no_prep:
        df = cap_outliers(df, features)
        df = log_transform(df, features)

    cfg = ClassNoiseConfig(
        label_column=args.label,
        feature_columns=features,
        n_estimators=args.n_estimators,
        cv_folds=args.cv_folds,
    )

    print(f"Đang chạy '{args.method}' trên {len(df)} dòng, {len(features)} đặc trưng...")
    t0 = time.time()
    try:
        if args.method == "single":
            res = detect_class_noise(df, cfg)
        elif args.method == "distance":
            res = detect_class_noise_distance(df, cfg, k=args.k)
        else:
            res = detect_class_noise_ensemble(df, cfg, cv_folds=args.cv_folds)
    except Exception as e:  # lỗi thường gặp: cột đặc trưng không phải số
        sys.exit(f"Lỗi: {e}")
    print(f"Xong trong {time.time() - t0:.1f} giây.\n")

    # Chuẩn hoá tên trường giống web: suggested_label / score
    rows = []
    for f in res.findings:
        if args.method == "single":
            sug, score = f.confident_label, f.margin
        elif args.method == "distance":
            sug, score = f.suggested_label, f.disagreement_ratio
        else:
            sug, score = f.suggested_label, f.disagree_ratio
        rows.append({"row_number": f.row_number, "recorded_label": f.recorded_label,
                     "suggested_label": sug, "score": score})

    # --- Chẩn đoán: XEM TRƯỚC khi tin kết quả ---
    d = res.diagnostics
    print("=== CHẨN ĐOÁN ĐỘ TIN CẬY ===")
    if args.method == "single":
        print(f"CV accuracy {d.cv_accuracy:.4f} | baseline {d.majority_baseline_accuracy:.4f}")
        if d.cv_accuracy <= d.majority_baseline_accuracy + 0.02:
            print("!! Model gần như không học được gì -> kết quả KHÔNG đáng tin.")
    elif args.method == "distance":
        print(f"k = {d.k} | số dòng có láng giềng lẫn nhau: {d.n_rows_with_mutual_neighbors}")
    else:
        for name, acc in d.per_classifier_accuracy.items():
            print(f"{name:<20} accuracy {acc:.4f}")
        print(f"baseline {d.majority_baseline_accuracy:.4f}")

    print(f"\n=== {len(rows)} dòng nghi ngờ (cao nhất trước) ===")
    print(f"{'dòng':>8}  {'nhãn ghi':<10} {'gợi ý':<10} {'score':>8}")
    for r in rows[: args.top]:
        print(f"{r['row_number']:>8}  {str(r['recorded_label']):<10} "
              f"{str(r['suggested_label']):<10} {r['score']:>8.4f}")

    if args.out:
        pd.DataFrame(rows).to_csv(args.out, index=False)
        print(f"\nĐã ghi {len(rows)} dòng ra {args.out}")


if __name__ == "__main__":
    main()
