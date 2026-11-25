"""Phần dùng chung cho các script thực nghiệm: đường dẫn, đọc dữ liệu, đổi nhãn có kiểm soát, chấm điểm."""
import os, sys
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "benchmarks")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

CLASS_DATASETS = ["pendigits", "letter", "waveform_40"]


def load_class_dataset(name):
    """Bộ class noise dạng TSV nén, cột nhãn tên 'target'."""
    return pd.read_csv(os.path.join(DATA, f"{name}.tsv.gz"), sep="\t")


def flip_labels(y0, level, seed):
    """Trong mỗi lớp, đổi đúng round(level × số dòng của lớp) dòng sang một lớp khác chọn ngẫu nhiên đều.
    Trả về (nhãn mới, chỉ số các dòng bị đổi, tính từ 0). Cùng (seed, level) luôn cho cùng kết quả."""
    rng = np.random.default_rng(1000 * seed + int(round(level * 1000)))
    y = y0.copy(); classes = np.unique(y0)
    if level <= 0:
        return y, np.array([], int)
    idx = np.concatenate([rng.choice(np.where(y0 == k)[0], int(round(level * (y0 == k).sum())), replace=False) for k in classes])
    for i in idx:
        y[i] = rng.choice([k for k in classes if k != y[i]])
    return y, idx


def score_rows(rows, truth):
    """Precision, Recall, F1 trên tập số dòng (đếm từ 1)."""
    tp = len(rows & truth); n = len(rows); nt = len(truth)
    P = tp / n if n else None; R = tp / nt if nt else None
    F = 2 * P * R / (P + R) if (P and R) else (0.0 if nt else None)
    return dict(n=n, tp=tp, P=P, R=R, F1=F)


def load_attr_benchmark(name):
    """Bản chứa lỗi (đọc như ứng dụng đọc) và bản sạch của Beers / Hospital; ma trận ô lỗi = ô khác bản sạch."""
    from attribute_noise.pipeline import load_data
    df = load_data(os.path.join(DATA, f"{name}_dirty.csv"))
    clean = pd.read_csv(os.path.join(DATA, f"{name}_clean.csv"), dtype=str, keep_default_na=False)
    clean.columns = df.columns
    return df, clean, (df != clean)


def cell_score(mask, truth, name):
    tp = int((mask & truth).values.sum()); n = int(mask.values.sum()); T = int(truth.values.sum())
    print(f"{name:58s} gắn cờ {n:5d} | đúng {tp:5d} | báo nhầm {n - tp:4d} | Precision {tp / max(n, 1):.3f} | Recall {tp / T:.3f}")
    return dict(tool=name, flagged=n, correct=tp, wrong=n - tp, precision=tp / max(n, 1), recall=tp / T)
