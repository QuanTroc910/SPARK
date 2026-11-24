"""
Chạy thuật toán CLASS NOISE ngay trên terminal (không cần mở web).

Ví dụ:
    python3 run_class_noise.py --file data/kaggle_creditcard_fraud.csv \
        --label Class --features V1,V2,V3,V4,V10,V12,V14 --method distance

    python3 run_class_noise.py --file data/class_noise_train.csv \
        --label V153 --features V44,V12,V4 --method single --out ketqua.csv

Hai phương pháp (--method):
    single    Confident Learning + Random Forest (chậm nhất)
    distance  Mutual k-NN, dựa vào khoảng cách (không train model)

Giống web: cột đặc trưng phải là cột SỐ. Với distance, mặc định tự cap
outlier + log trước khi chạy (thêm --no-prep nếu muốn tắt); với single (cây quyết
định) thì KHÔNG cap/log vì không có tác dụng đo được (xem CLAUDE.md, kế hoạch mục 3).
"""

import argparse
import sys
import time

import pandas as pd

from attribute_noise.pipeline import load_data
from class_noise.config import ClassNoiseConfig
from class_noise.confident_learning import detect_class_noise
from class_noise.distance_based import detect_class_noise_distance
from class_noise.feature_selection import cap_outliers, log_transform


def parse_args():
    p = argparse.ArgumentParser(description="Phát hiện Class Noise trên terminal")
    p.add_argument("--file", required=True, help="đường dẫn file CSV/Excel")
    p.add_argument("--label", required=True, help="tên cột nhãn")
    p.add_argument("--features", required=True,
                   help="các cột đặc trưng (SỐ), cách nhau bằng dấu phẩy")
    p.add_argument("--method", choices=["single", "distance"],
                   default="distance", help="thuật toán (mặc định: distance)")
    p.add_argument("--n-estimators", type=int, default=300,
                   help="[single] số cây Random Forest")
    p.add_argument("--cv-folds", type=int, default=5,
                   help="[single] số fold cross-validation")
    p.add_argument("--k", default="5",
                   help="[distance] số láng giềng k (số nguyên), hoặc 'auto' để tự chọn "
                        "k nhỏ nhất đạt độ phủ mục tiêu (mặc định: 5)")
    p.add_argument("--metric", choices=["euclidean", "manhattan"], default="euclidean",
                   help="[distance] cách đo khoảng cách (mặc định: euclidean)")
    p.add_argument("--weighting", choices=["count", "distance"], default="count",
                   help="[distance] 'count' = mỗi láng giềng 1 phiếu; "
                        "'distance' = láng giềng gần thì phiếu nặng hơn")
    p.add_argument("--pca", choices=["off", "auto", "on"], default="off",
                   help="[distance] giảm chiều bằng PCA: off (mặc định), auto (chỉ bật khi "
                        "95%% biến thiên nằm trong ít hơn nửa số cột), on")
    p.add_argument("--top", type=int, default=20, help="in ra N dòng đáng ngờ nhất")
    p.add_argument("--out", help="ghi TOÀN BỘ dòng nghi ngờ ra file CSV này")
    p.add_argument("--no-prep", action="store_true",
                   help="không cap outlier + log-transform trước khi chạy "
                        "(distance; single vốn không cap/log)")
    return p.parse_args()


def main():
    args = parse_args()
    features = [c.strip() for c in args.features.split(",") if c.strip()]

    # --k nhận số nguyên hoặc chữ "auto"; gõ sai thì báo ngay thay vì để lỗi thư viện.
    if str(args.k).lower() == "auto":
        k_value = "auto"
    else:
        try:
            k_value = int(args.k)
        except ValueError:
            sys.exit(f"--k phải là số nguyên hoặc 'auto', nhận được: {args.k!r}")

    df = load_data(args.file)
    thieu = [c for c in [args.label, *features] if c not in df.columns]
    if thieu:
        sys.exit(f"Không có cột: {thieu}. Các cột trong file: {list(df.columns)}")

    if not args.no_prep and args.method != "single":
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
            pca_mode = {"off": False, "auto": "auto", "on": True}[args.pca]
            res = detect_class_noise_distance(
                df, cfg, k=k_value, metric=args.metric,
                weighting=args.weighting, pca=pca_mode)
    except Exception as e:  # lỗi thường gặp: cột đặc trưng không phải số
        sys.exit(f"Lỗi: {e}")
    print(f"Xong trong {time.time() - t0:.1f} giây.\n")

    # Chuẩn hoá tên trường giống web: suggested_label / score
    rows = []
    for f in res.findings:
        if args.method == "single":
            sug, score = f.confident_label, f.margin
        else:
            sug, score = f.suggested_label, f.disagreement_ratio
        rows.append({"row_number": f.row_number, "recorded_label": f.recorded_label,
                     "suggested_label": sug, "score": score})

    # --- Chẩn đoán: XEM TRƯỚC khi tin kết quả ---
    d = res.diagnostics
    print("=== CHẨN ĐOÁN ĐỘ TIN CẬY ===")
    if args.method == "single":
        print(f"CV accuracy {d.cv_accuracy:.4f} | baseline {d.majority_baseline_accuracy:.4f}")
        if d.cv_accuracy <= d.majority_baseline_accuracy + 0.02:
            print("!! Model gần như không học được gì -> kết quả KHÔNG đáng tin.")
    else:
        print(f"k = {d.k} ({'tự chọn' if d.k_mode == 'auto' else 'đặt tay'}) | "
              f"độ phủ {d.coverage:.1%} ({d.n_rows_with_mutual_neighbors}/{d.n_rows_used} dòng "
              f"có láng giềng lẫn nhau)")
        if d.coverage_by_k:
            print("độ phủ theo k:", {k_: f"{v:.1%}" for k_, v in d.coverage_by_k.items()})
        print(f"khoảng cách {d.metric} | phiếu theo '{d.weighting}' | "
              f"cột nhị phân giữ 0/1: {d.binary_columns or 'không có'} | "
              f"PCA: {'bật (' + str(d.pca.get('n_components')) + ' thành phần)' if d.pca.get('applied') else 'tắt'}")
        for w in d.warnings:
            print("!!", w)

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
