"""
PHÂN TÍCH "CẮT CÙNG K" cho thí nghiệm Class Noise nhiều seed (kế hoạch mục 5).

Vì sao cần: bộ kết hợp (class_noise/combined.py) lấy K = số dòng mà Confident Learning tự gắn cờ rồi chọn K dòng
điểm kết hợp cao nhất. So với Confident Learning thì F1 cao hơn, nhưng AP/P@K lại thấp hơn. Hai kết quả chỉ hoà giải
được nếu "danh sách gắn cờ" của Confident Learning (luật confident-joint) vốn là một cách CẮT kém hơn chính xếp hạng
điểm của nó. Script này đo trực tiếp: với CÙNG K = số dòng Confident Learning tự gắn cờ, Precision của
  - luật gắn cờ riêng của Confident Learning,
  - cắt top-K theo điểm nghi ngờ của chính Confident Learning,
  - bộ kết hợp (alpha chọn bằng --alpha),
  - đối chứng naive_cv cắt top-K theo điểm của nó,
trung bình trên các seed giữ lại (seed >= 1), theo từng (bộ dữ liệu, kiểu nhiễu) và gộp.

Chạy:  python3 analyze_class_noise_same_k.py [--scores-dir data/class_noise_scores_v2] [--alpha 1]
Đọc điểm đã lưu bởi evaluate_class_noise_multiseed.py (không chạy lại thuật toán nào).
"""

import argparse
import glob
import os

import numpy as np
import pandas as pd

from evaluate_class_noise_multiseed import combined_output, load_cell


def top_k_precision(scores: np.ndarray, truth: np.ndarray, k: int) -> float:
    """Precision của k dòng điểm cao nhất (điểm NaN xếp cuối; hoà điểm theo thứ tự dòng)."""
    s = np.nan_to_num(scores, nan=-np.inf)
    return float(truth[np.argsort(-s, kind="stable")[:k]].mean())


def collect(scores_dir: str, alpha: float, min_seed: int = 1) -> pd.DataFrame:
    rows = []
    for path in sorted(glob.glob(os.path.join(scores_dir, "*.npz"))):
        ds, seed, scheme, rate = os.path.basename(path)[:-4].split("_")
        if int(seed) < min_seed:
            continue
        z = np.load(path, allow_pickle=False)
        outs = load_cell(path)
        if not all(m in outs for m in ("single", "distance", "ensemble", "naive_cv")):
            continue
        flipped, noisy = z["flipped"], pd.Series(z["noisy"])
        single = outs["single"]
        k = int(single.flagged.sum())
        if k == 0:
            continue
        combined, _ = combined_output(outs, noisy, alpha)
        rows.append({
            "dataset": ds, "scenario": f"{scheme}:{rate}", "seed": int(seed), "K": k, "n_flipped": int(flipped.sum()),
            "cl_rule": float(flipped[single.flagged].mean()),
            "cl_top_k": top_k_precision(single.scores, flipped, k),
            "combined": top_k_precision(combined.scores, flipped, k),
            "naive_cv_top_k": top_k_precision(outs["naive_cv"].scores, flipped, k),
        })
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scores-dir", default="data/class_noise_scores_v2")
    ap.add_argument("--alpha", type=float, default=1.0)
    args = ap.parse_args()
    d = collect(args.scores_dir, args.alpha)
    if d.empty:
        raise SystemExit("Không có điểm đã lưu để phân tích.")
    cols = ["K", "n_flipped", "cl_rule", "cl_top_k", "combined", "naive_cv_top_k"]
    print("Precision tại CÙNG K = số dòng Confident Learning tự gắn cờ (trung bình các seed giữ lại):\n")
    print(d.groupby(["dataset", "scenario"], sort=False)[cols].mean().round(3).to_string())
    print("\nGộp mọi ô:")
    print(d[cols[2:]].mean().round(3).to_string())
    n = len(d)
    print(f"\nTrên {n} ô: bộ kết hợp > CL cắt theo điểm của nó ở {int((d.combined > d.cl_top_k).sum())} ô, "
          f"bằng {int((d.combined == d.cl_top_k).sum())}, kém hơn {int((d.combined < d.cl_top_k).sum())}.")
    print(f"CL cắt theo điểm của nó > luật gắn cờ riêng của CL ở {int((d.cl_top_k > d.cl_rule).sum())}/{n} ô.")


if __name__ == "__main__":
    main()
