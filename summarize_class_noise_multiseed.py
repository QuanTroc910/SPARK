"""
TỔNG HỢP KẾT QUẢ thí nghiệm Class Noise nhiều seed (đọc file do evaluate_class_noise_multiseed.py ghi).

Việc script này làm (kế hoạch mục 5):
  1. CHỌN alpha của bộ kết hợp CHỈ trên seed 0: alpha có F1 phát hiện trung bình cao nhất, tính gộp trên
     mọi (bộ dữ liệu, kiểu nhiễu); hoà thì lấy alpha NHỎ hơn (đơn giản hơn). Sau đó alpha được GIỮ CỐ ĐỊNH.
  2. Mọi bảng so sánh chỉ dùng các seed >= 1 ("seed giữ lại") -- seed 0 đã được dùng để chọn alpha nên
     không đưa vào so sánh, tránh tinh chỉnh theo đúng dữ liệu đang đánh giá.
  3. Bảng mean ± std theo từng (bộ dữ liệu, kiểu nhiễu) và từng phương pháp, với 3 thước đo:
       - F1 / Precision / Recall của luật gắn cờ RIÊNG của mỗi phương pháp (phụ thuộc số dòng bị gắn cờ);
       - ap (average precision) và p_at_k: xếp hạng không phụ thuộc số dòng gắn cờ -> dùng khi so phương pháp.
  4. Kiểm định Wilcoxon bắt cặp (hai phía) giữa bộ kết hợp (alpha đã chọn) và từng đường cơ sở, gộp các cặp
     (bộ dữ liệu, kiểu nhiễu, seed giữ lại), kèm hiệu chỉnh Holm trong mỗi thước đo. Cũng báo theo từng bộ.
     LƯU Ý: các cặp trong cùng 1 bộ dữ liệu không độc lập hoàn toàn (cùng dữ liệu gốc, chỉ khác seed chia
     train/test và seed cấy nhiễu); với n nhỏ, p-value tối thiểu của kiểm định hai phía còn rất lớn.
  5. Bảng downstream: PR-AUC trên tập test SẠCH khi huấn luyện trên dữ liệu đã lọc / sửa nhãn, so với
     dữ liệu nhiễu chưa làm sạch và với nhãn gốc sạch (Oracle).
  6. Bảng biến thể của Mutual k-NN (đo trên mọi seed vì không phụ thuộc alpha) + thống kê cổng chất lượng
     của bộ kết hợp (phương pháp nào bị loại bao nhiêu lần) + thời gian chạy.

Chạy:  python3 summarize_class_noise_multiseed.py [--in data/class_noise_multiseed_v2.jsonl]
           [--alpha 0.5] [--md data/class_noise_experiment_summary.md]
"""

import argparse
import json
import sys

import numpy as np
import pandas as pd
from scipy.stats import wilcoxon

BASELINES = ["naive_cv", "enn", "single", "distance", "ensemble"]
VARIANTS = ["distance_auto", "distance_w", "distance_l1", "distance_raw"]
DETECT_METRICS = ["precision", "recall", "f1"]
RANK_METRICS = ["ap", "p_at_k"]
COMPARE_METRICS = ["f1", "ap", "p_at_k"]  # thước đo dùng cho kiểm định
NAMES = {"naive_cv": "naive_cv (đối chứng)", "enn": "ENN k=3 (đối chứng)", "single": "Confident Learning",
         "distance": "Mutual k-NN", "ensemble": "Ensemble"}


# --------------------------------------------------------------------------------------
# Đọc dữ liệu
# --------------------------------------------------------------------------------------
def load_records(path: str) -> pd.DataFrame:
    """Đọc .jsonl thành 1 bảng phẳng: mỗi dòng = 1 (bộ dữ liệu, kiểu nhiễu, seed, phương pháp)."""
    rows = []
    for line in open(path, encoding="utf-8"):
        r = json.loads(line)
        flat = {"dataset": r["dataset"], "seed": r["seed"], "scenario": f"{r['scheme']}:{r['rate']:g}",
                "method": r["method"], "n_train": r.get("n_train"), "n_flipped": r.get("n_flipped")}
        if r["method"] == "_ref":
            for k in ("noisy", "oracle"):
                d = (r.get("downstream") or {}).get(k) or {}
                flat[f"ref_{k}_pr_auc"] = d.get("pr_auc")
        else:
            det, rk = r.get("detection") or {}, r.get("ranking") or {}
            flat.update(n_flagged=r.get("n_flagged"), seconds=r.get("seconds"), quality=r.get("quality"),
                        alpha=r.get("alpha"), **{m: det.get(m) for m in DETECT_METRICS}, **{m: rk.get(m) for m in RANK_METRICS})
            for kind in ("filtered", "relabeled"):
                d = ((r.get("downstream") or {}).get(kind)) or {}
                flat[f"ds_{kind}_pr_auc"] = d.get("pr_auc")
            e5 = r.get("ensemble5_info")
            if e5:
                flat["e5_mean_agreement"] = e5.get("mean_agreement")
                flat["e5_best_excess"] = e5.get("best_excess")
                for clf, v in (e5.get("excess") or {}).items():
                    flat[f"e5_excess_{clf}"] = v
            c = r.get("combined")
            if c:
                flat["k_method"] = c["k_method"]
                for m, on in c["on"].items():
                    flat[f"on_{m}"] = on
        rows.append(flat)
    return pd.DataFrame(rows)


def combined_name(alpha: float) -> str:
    return f"combined_a{alpha:g}"


def choose_alpha(df: pd.DataFrame, metric: str = "f1") -> tuple[float, pd.Series]:
    """alpha tốt nhất trên seed 0 (trung bình gộp mọi bộ dữ liệu x kiểu nhiễu); hoà -> alpha nhỏ hơn."""
    c = df[df["method"].str.startswith("combined_a") & (df["seed"] == 0)]
    if c.empty:
        raise SystemExit("Không có kết quả combined ở seed 0 để chọn alpha.")
    table = c.groupby("alpha")[metric].mean().sort_index()
    best = table.max()
    return float(min(a for a, v in table.items() if v >= best - 1e-12)), table


# --------------------------------------------------------------------------------------
# Định dạng bảng markdown
# --------------------------------------------------------------------------------------
def fmt(series: pd.Series, digits: int = 3) -> str:
    s = series.dropna()
    if s.empty:
        return "–"
    if len(s) == 1:
        return f"{s.iloc[0]:.{digits}f}"
    return f"{s.mean():.{digits}f}±{s.std(ddof=1):.{digits}f}"


def md_table(header: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


# --------------------------------------------------------------------------------------
# Các bảng
# --------------------------------------------------------------------------------------
def combined_methods(alpha: float) -> list[str]:
    """Bản công tắc (α=0) và bản pha trộn (α đã chọn); nếu α đã chọn = 0 thì chỉ còn 1 bản."""
    return ["combined_a0"] if alpha == 0 else ["combined_a0", combined_name(alpha)]


def combined_labels(alpha: float, short: bool = False) -> dict:
    sw = "Kết hợp α=0" if short else "Kết hợp, công tắc (α=0)"
    labels = {"combined_a0": sw}
    if alpha != 0:
        labels[combined_name(alpha)] = f"Kết hợp α={alpha:g}" if short else f"Kết hợp, pha trộn (α={alpha:g})"
    return labels


def main_tables(held: pd.DataFrame, alpha: float) -> str:
    """Bảng mean ± std theo (bộ dữ liệu, kiểu nhiễu) và phương pháp, trên seed giữ lại."""
    order = BASELINES + combined_methods(alpha)
    labels = {**NAMES, **combined_labels(alpha)}
    out = []
    for (ds, sc), g in held.groupby(["dataset", "scenario"], sort=False):
        rows = []
        for m in order:
            x = g[g["method"] == m]
            if x.empty:
                continue
            rows.append([labels[m], f"{x['n_flagged'].mean():.0f}", fmt(x["precision"]), fmt(x["recall"]), fmt(x["f1"]),
                         fmt(x["ap"]), fmt(x["p_at_k"])])
        n_seeds = g["seed"].nunique()
        n_flip = g["n_flipped"].dropna().mean()
        out.append(f"#### {ds} · nhiễu {sc} (≈{n_flip:.0f} dòng bị đảo, {n_seeds} seed giữ lại)\n\n"
                   + md_table(["Phương pháp", "Số dòng cờ", "Precision", "Recall", "F1", "AP", "P@K"], rows))
    return "\n\n".join(out)


def paired_diffs(held: pd.DataFrame, a: str, b: str, metric: str) -> pd.DataFrame:
    keys = ["dataset", "scenario", "seed"]
    x = held[held["method"] == a][keys + [metric]].rename(columns={metric: "a"})
    y = held[held["method"] == b][keys + [metric]].rename(columns={metric: "b"})
    m = x.merge(y, on=keys).dropna()
    m["diff"] = m["a"] - m["b"]
    return m


def wilcoxon_p(diff: np.ndarray) -> float | None:
    d = diff[np.abs(diff) > 1e-12]
    if len(d) < 1:
        return None
    try:
        return float(wilcoxon(d, alternative="two-sided").pvalue)
    except ValueError:
        return None


def holm(pvals: list[float | None]) -> list[float | None]:
    idx = [i for i, p in enumerate(pvals) if p is not None]
    order = sorted(idx, key=lambda i: pvals[i])
    adj, running = {}, 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (len(order) - rank) * pvals[i]))
        adj[i] = running
    return [adj.get(i) for i in range(len(pvals))]


def wilcoxon_tables(held: pd.DataFrame, alpha: float, subject: str) -> str:
    out = []
    for scope, data in [("Gộp mọi bộ dữ liệu", held)] + [(f"Riêng {ds}", held[held["dataset"] == ds]) for ds in held["dataset"].unique()]:
        for metric in COMPARE_METRICS:
            rows, pvals, recs = [], [], []
            for b in BASELINES:
                d = paired_diffs(data, subject, b, metric)
                if d.empty:
                    continue
                diff = d["diff"].to_numpy()
                p = wilcoxon_p(diff)
                recs.append((b, len(d), float(diff.mean()), int((diff > 1e-12).sum()), int((np.abs(diff) <= 1e-12).sum()), int((diff < -1e-12).sum())))
                pvals.append(p)
            adj = holm(pvals)
            for (b, n, md, w, t, l), p, pa in zip(recs, pvals, adj):
                rows.append([NAMES[b], n, f"{md:+.3f}", f"{w}/{t}/{l}", "–" if p is None else f"{p:.4f}", "–" if pa is None else f"{pa:.4f}"])
            if rows:
                out.append(f"**{scope} · thước đo {metric}**\n\n" + md_table(
                    ["So với", "Số cặp", "Hiệu trung bình", "Thắng/Hoà/Thua", "p (Wilcoxon)", "p (Holm)"], rows))
    return "\n\n".join(out)


def downstream_table(held: pd.DataFrame, refs: pd.DataFrame, alpha: float) -> str:
    """PR-AUC trên test sạch: chênh so với train nhiễu chưa làm sạch, trung bình trên seed giữ lại, theo bộ dữ liệu."""
    keys = ["dataset", "scenario", "seed"]
    methods = BASELINES + combined_methods(alpha)
    labels = {**NAMES, **combined_labels(alpha, short=True)}
    r = refs[refs["seed"] >= 1]
    out = []
    for kind, title in (("filtered", "lọc bỏ dòng bị gắn cờ"), ("relabeled", "sửa nhãn theo gợi ý")):
        header = ["Phương pháp"] + sorted(held["dataset"].unique())
        rows = []
        for m in methods:
            row = [labels[m]]
            for ds in header[1:]:
                x = held[(held["method"] == m) & (held["dataset"] == ds)][keys + [f"ds_{kind}_pr_auc"]]
                x = x.merge(r[r["dataset"] == ds][keys + ["ref_noisy_pr_auc"]], on=keys).dropna()
                row.append(fmt(x[f"ds_{kind}_pr_auc"] - x["ref_noisy_pr_auc"]) if len(x) else "–")
            rows.append(row)
        gap = ["(Oracle − nhiễu)"]
        for ds in header[1:]:
            x = r[r["dataset"] == ds].dropna(subset=["ref_noisy_pr_auc", "ref_oracle_pr_auc"])
            gap.append(fmt(x["ref_oracle_pr_auc"] - x["ref_noisy_pr_auc"]) if len(x) else "–")
        rows.append(gap)
        out.append(f"**Downstream PR-AUC, {title} — chênh so với train nhiễu chưa làm sạch** (dương = tốt hơn)\n\n" + md_table(header, rows))
    return "\n\n".join(out)


def variants_table(df: pd.DataFrame) -> str:
    """Biến thể Mutual k-NN, trên MỌI seed (không phụ thuộc alpha)."""
    ms = ["distance"] + VARIANTS
    labels = {"distance": "Mutual k-NN gốc (k=5)", "distance_auto": "k theo độ phủ", "distance_w": "bỏ phiếu theo khoảng cách",
              "distance_l1": "khoảng cách Manhattan", "distance_raw": "không cap + log"}
    out = []
    for ds, g in df[df["method"].isin(ms)].groupby("dataset", sort=False):
        rows = []
        for m in ms:
            x = g[g["method"] == m]
            if not x.empty:
                rows.append([labels[m], f"{x['n_flagged'].mean():.0f}", fmt(x["f1"]), fmt(x["ap"]), fmt(x["p_at_k"])])
        out.append(f"**{ds}** (mọi seed, gộp các kiểu nhiễu)\n\n" + md_table(["Biến thể", "Số dòng cờ", "F1", "AP", "P@K"], rows))
    return "\n\n".join(out)


def gating_table(held: pd.DataFrame, alpha: float) -> str:
    c = held[held["method"] == combined_methods(alpha)[-1]]
    rows = []
    for ds, g in c.groupby("dataset", sort=False):
        off_s = 1 - g["on_single_learning"].astype(float).mean() if "on_single_learning" in g else float("nan")
        off_e = 1 - g["on_ensemble_based"].astype(float).mean() if "on_ensemble_based" in g else float("nan")
        km = g["k_method"].value_counts(normalize=True).round(2).to_dict() if "k_method" in g else {}
        rows.append([ds, len(g), f"{off_s:.0%}", f"{off_e:.0%}", ", ".join(f"{k.split('_')[0]} {v:.0%}" for k, v in km.items())])
    return md_table(["Bộ dữ liệu", "Số ô", "Confident Learning bị loại", "Ensemble bị loại", "K lấy từ"], rows)


def time_table(df: pd.DataFrame) -> str:
    base = df[df["method"].isin(BASELINES + VARIANTS)]
    t = base.groupby(["dataset", "method"])["seconds"].mean().unstack("method")
    cols = [m for m in BASELINES + VARIANTS if m in t.columns]
    return md_table(["Bộ dữ liệu"] + cols, [[ds] + [f"{t.loc[ds, c]:.1f}s" if pd.notna(t.loc[ds, c]) else "–" for c in cols] for ds in t.index])


E5_METHODS = ["ensemble", "ensemble5", "ensemble5_v4", "ensemble5_v5"]
E5_LABELS = {"ensemble": "Ensemble cũ (3 họ)", "ensemble5": "Ensemble 5 họ, 3/5 phiếu", "ensemble5_v4": "Ensemble 5 họ, 4/5 phiếu",
             "ensemble5_v5": "Ensemble 5 họ, 5/5 phiếu"}


def choose_alpha_for(df: pd.DataFrame, prefix: str) -> float | None:
    """Như choose_alpha nhưng cho họ bản ghi `prefix` (vd 'combined5_a'); None nếu không có."""
    c = df[df["method"].str.startswith(prefix) & (df["seed"] == 0)]
    if c.empty:
        return None
    table = c.groupby("alpha")["f1"].mean().sort_index()
    return float(min(a for a, v in table.items() if v >= table.max() - 1e-12))


def ensemble5_section(df: pd.DataFrame, held: pd.DataFrame, alpha_old: float) -> str:
    """Phần 8: Ensemble 5 họ (kế hoạch mục 7) so với Ensemble cũ, đối chứng, và bộ kết hợp dùng nó."""
    if not (df["method"] == "ensemble5").any():
        return "(chưa có kết quả Ensemble 5 họ: chạy evaluate_class_noise_multiseed.py --methods single,distance,ensemble5 --variants '')"
    parts = []
    # (a) bảng theo bộ dữ liệu, gộp 3 kiểu nhiễu
    rows = []
    for ds, g in held.groupby("dataset", sort=False):
        for m in E5_METHODS + ["naive_cv"]:
            x = g[g["method"] == m]
            if not x.empty:
                rows.append([ds, E5_LABELS.get(m, NAMES.get(m, m)), f"{x['n_flagged'].mean():.0f}", fmt(x["precision"]), fmt(x["recall"]),
                             fmt(x["f1"]), fmt(x["ap"]), fmt(x["p_at_k"])])
    parts.append("**Theo bộ dữ liệu (gộp 3 kiểu nhiễu, seed giữ lại)**\n\n"
                 + md_table(["Bộ", "Phương pháp", "Số dòng cờ", "Precision", "Recall", "F1", "AP", "P@K"], rows))
    # (b) Wilcoxon: Ensemble 5 họ so với Ensemble cũ và naive_cv
    for subject, others in (("ensemble5", ["ensemble", "naive_cv", "single", "distance"]), ("ensemble5_v5", ["ensemble"])):
        out_rows = []
        for metric in COMPARE_METRICS:
            for b in others:
                d = paired_diffs(held, subject, b, metric)
                if d.empty:
                    continue
                diff = d["diff"].to_numpy(); p = wilcoxon_p(diff)
                out_rows.append([metric, E5_LABELS.get(b, NAMES.get(b, b)), len(d), f"{diff.mean():+.3f}",
                                 f"{int((diff > 1e-12).sum())}/{int((abs(diff) <= 1e-12).sum())}/{int((diff < -1e-12).sum())}",
                                 "–" if p is None else f"{p:.4f}"])
        parts.append(f"**{E5_LABELS[subject]} so với** (gộp mọi bộ, seed giữ lại)\n\n"
                     + md_table(["Thước đo", "So với", "Số cặp", "Hiệu trung bình", "Thắng/Hoà/Thua", "p (Wilcoxon)"], out_rows))
    # (c) độ đa dạng + mức vượt mốc từng mô hình
    e5 = df[df["method"] == "ensemble5"]
    clfs = sorted(c[len("e5_excess_"):] for c in e5.columns if c.startswith("e5_excess_"))
    rows = [[ds, f"{g['e5_mean_agreement'].mean():.3f}"] + [f"{g[f'e5_excess_{c}'].mean():+.2f}" for c in clfs] + [f"{g['e5_best_excess'].mean():+.2f}"]
            for ds, g in e5.groupby("dataset", sort=False)]
    parts.append("**Độ đa dạng và mức vượt mốc từng mô hình (mọi seed)** — 'giống nhau' = tỉ lệ dòng 2 mô hình dự đoán trùng, trung bình các cặp\n\n"
                 + md_table(["Bộ", "Dự đoán giống nhau"] + clfs + ["Tốt nhất"], rows))
    # (d) bộ kết hợp dùng Ensemble 5 họ
    a5 = choose_alpha_for(df, "combined5_a")
    if a5 is not None:
        subject = f"combined5_a{a5:g}"
        old_subject = combined_methods(alpha_old)[-1]
        gate = held[held["method"] == subject]
        off = 1 - gate["on_ensemble_based"].astype(float).mean() if "on_ensemble_based" in gate else float("nan")
        rows = []
        for b in ["naive_cv", "single", old_subject]:
            for metric in COMPARE_METRICS:
                d = paired_diffs(held, subject, b, metric)
                if d.empty:
                    continue
                diff = d["diff"].to_numpy(); p = wilcoxon_p(diff)
                rows.append([metric, "Kết hợp (Ensemble cũ)" if b == old_subject else NAMES.get(b, b), len(d), f"{diff.mean():+.3f}",
                             f"{int((diff > 1e-12).sum())}/{int((abs(diff) <= 1e-12).sum())}/{int((diff < -1e-12).sum())}",
                             "–" if p is None else f"{p:.4f}"])
        km = gate["k_method"].value_counts(normalize=True).round(2).to_dict() if "k_method" in gate else {}
        parts.append(f"**Bộ kết hợp dùng Ensemble 5 họ** (α chọn trên seed 0 = **{a5:g}**; Ensemble 5 họ bị cổng loại ở {off:.0%} số ô; "
                     f"K lấy từ: {', '.join(f'{k.split(chr(95))[0]} {v:.0%}' for k, v in km.items())})\n\n"
                     + md_table(["Thước đo", "So với", "Số cặp", "Hiệu trung bình", "Thắng/Hoà/Thua", "p (Wilcoxon)"], rows))
    return "\n\n".join(parts)


# --------------------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="inp", default="data/class_noise_multiseed_v2.jsonl")
    ap.add_argument("--alpha", type=float, default=None, help="ép alpha (mặc định: chọn trên seed 0)")
    ap.add_argument("--md", default=None, help="ghi thêm ra file markdown này")
    args = ap.parse_args()

    df = load_records(args.inp)
    refs = df[df["method"] == "_ref"].copy()
    df = df[df["method"] != "_ref"].copy()
    n_seeds = int(df["seed"].max()) + 1
    if n_seeds < 2:
        raise SystemExit("Cần >= 2 seed (seed 0 để chọn alpha, các seed còn lại để so sánh).")

    alpha, table = choose_alpha(df)
    if args.alpha is not None:
        alpha = args.alpha
    held = df[df["seed"] >= 1]
    parts = [f"# Tổng hợp thí nghiệm Class Noise ({n_seeds} seed; {df['dataset'].nunique()} bộ dữ liệu: {', '.join(df['dataset'].unique())})\n",
             "## 1. Chọn alpha (CHỈ seed 0)\n",
             "F1 phát hiện trung bình của bộ kết hợp theo alpha, gộp mọi (bộ dữ liệu, kiểu nhiễu) ở seed 0:\n\n"
             + md_table(["alpha", "F1 trung bình"], [[f"{a:g}", f"{v:.4f}"] for a, v in table.items()])
             + f"\n\n→ alpha được dùng = **{alpha:g}** ({'ép bằng --alpha' if args.alpha is not None else 'chọn trên seed 0, hoà thì lấy nhỏ hơn'})."
             + (" Bản pha trộn không tốt hơn bản công tắc ở seed 0 nên chỉ báo cáo bản công tắc." if alpha == 0 else "")
             + f" Mọi bảng dưới đây chỉ dùng seed 1–{n_seeds - 1}.\n",
             "## 2. Kết quả theo bộ dữ liệu và kiểu nhiễu (mean ± std trên seed giữ lại)\n",
             "Số dòng cờ, Precision, Recall, F1 phụ thuộc luật gắn cờ riêng của từng phương pháp (số dòng cờ khác nhau nên "
             "KHÔNG so công bằng được). AP và P@K xếp hạng dòng theo điểm nghi ngờ nên so được giữa các phương pháp.\n",
             main_tables(held, alpha),
             "\n## 3. Kiểm định Wilcoxon bắt cặp: bộ kết hợp so với từng đường cơ sở\n",
             f"Bộ kết hợp = alpha {alpha:g}. 'Hiệu trung bình' = (kết hợp − đường cơ sở); 'Thắng/Hoà/Thua' đếm theo cặp. "
             "Cặp = (bộ dữ liệu, kiểu nhiễu, seed giữ lại); các cặp trong cùng bộ không độc lập hoàn toàn.\n",
             wilcoxon_tables(held, alpha, combined_methods(alpha)[-1]),
             "\n## 4. Downstream (PR-AUC trên tập test sạch)\n",
             downstream_table(held, refs, alpha),
             "\n## 5. Biến thể của Mutual k-NN\n",
             variants_table(df),
             "\n## 6. Cổng chất lượng của bộ kết hợp\n",
             gating_table(held, alpha),
             "\n## 7. Thời gian chạy trung bình mỗi ô\n",
             time_table(df),
             "\n## 8. Ensemble 5 họ (kế hoạch mục 7) so với Ensemble cũ\n",
             ensemble5_section(df, held, alpha)]
    text = "\n".join(parts)
    print(text)
    if args.md:
        open(args.md, "w", encoding="utf-8").write(text + "\n")
        print(f"\n(đã ghi {args.md})", file=sys.stderr)


if __name__ == "__main__":
    main()
