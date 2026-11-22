"""
PHƯƠNG PHÁP KẾT HỢP cho Class Noise (kế hoạch mục 4, 22/11/2026) -- đóng góp riêng của đề tài.

Vấn đề: 3 phương pháp có sẵn (Confident Learning, Mutual k-NN, Ensemble) cho 3 danh sách
nghi ngờ khác nhau, chất lượng thay đổi theo dữ liệu (trên dữ liệu có đặc trưng yếu thì mô
hình học máy gần như đoán bừa, trong khi k-NN vẫn dùng được; ngược lại có dữ liệu mô hình
tốt hơn hẳn). Người dùng không biết nên tin phương pháp nào. Module này gộp chúng lại thành
MỘT danh sách duy nhất, tự biết phương pháp nào đáng tin trên chính dữ liệu đang xét.

Cách làm (đơn giản, kiểm tra được từng bước):
  1. HẠNG PHẦN TRĂM. Điểm của 3 phương pháp khác thang (1 - xác suất, tỉ lệ láng giềng bất
     đồng, tỉ lệ classifier bất đồng) nên không cộng trực tiếp được. Mỗi phương pháp đổi
     điểm thành hạng phần trăm trong chính nó (0..1, hoà điểm thì lấy hạng trung bình):
     dòng đáng ngờ nhất theo phương pháp đó có hạng gần 1.
  2. CỔNG CHẤT LƯỢNG. Phương pháp dựa trên mô hình (Confident Learning, Ensemble) bị LOẠI
     nếu "mức vượt mốc" <= 0, tức mô hình không hơn gì cách đoán bừa lớp đông nhất -- khi
     đó các dòng nó gắn cờ chủ yếu là do mô hình dở. Mutual k-NN LUÔN có mặt vì nó không
     train mô hình nào, không có accuracy để đo.
  3. TRỌNG SỐ bằng 1 tham số alpha trong [0, 1]:
         w_m = (1 - alpha) * (1 / số_phương_pháp_còn_bật) + alpha * (q_m / tổng q)
     alpha = 0: bản "CÔNG TẮC" -- phương pháp nào qua cổng thì trọng số bằng nhau.
     alpha > 0: bản "PHA TRỘN" -- phương pháp có mức vượt mốc cao được tin hơn.
     (q_m = mức vượt mốc; k-NN không có nên lấy trung bình q của các phương pháp còn bật.)
  4. ĐIỂM KẾT HỢP của mỗi dòng = trung bình có trọng số của các hạng phần trăm (chỉ tính
     phương pháp còn bật và CÓ ý kiến về dòng đó; vd k-NN không có ý kiến về dòng không có
     láng giềng lẫn nhau).
  5. SỐ DÒNG TRẢ VỀ K = số dòng mà phương pháp có trọng số LỚN NHẤT tự gắn cờ theo luật
     riêng của nó. Trả K dòng có điểm kết hợp cao nhất, kèm danh sách phương pháp nào cùng
     nghi dòng đó và lý do (mức vượt mốc). Nghĩa là bộ kết hợp chỉ SẮP XẾP LẠI cho tốt hơn,
     còn "bao nhiêu dòng" lấy từ phương pháp đáng tin nhất, không tự đặt ngưỡng mới.

alpha KHÔNG được chọn ở đây: chọn alpha là việc của khâu thực nghiệm (kế hoạch mục 5: chọn
trên 1 seed rồi giữ cố định), để không tinh chỉnh theo đúng dữ liệu đang đánh giá.

Module thuần Python/numpy/pandas, không phụ thuộc Flask.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .config import ClassNoiseConfig

# Thứ tự cố định dùng để phá hoà khi 2 phương pháp có trọng số bằng nhau.
METHOD_ORDER = ("single_learning", "distance_based", "ensemble_based")


@dataclass
class MethodOutput:
    """Đầu ra của MỘT phương pháp, ở dạng chung để gộp được.

    row_numbers: số dòng 1-based (index gốc + 1) của các dòng phương pháp đã chấm điểm.
    scores: điểm nghi ngờ, càng cao càng đáng ngờ; NaN = phương pháp không có ý kiến.
    flagged: True nếu CHÍNH phương pháp đó gắn cờ dòng này theo luật riêng của nó.
    suggested_labels: nhãn gợi ý của phương pháp ("" = không có gợi ý).
    quality: "mức vượt mốc" của mô hình (None = phương pháp không có mô hình để đo).
    always_on: True = luôn được dùng bất kể quality (Mutual k-NN).
    """

    name: str
    row_numbers: np.ndarray
    scores: np.ndarray
    flagged: np.ndarray
    suggested_labels: np.ndarray
    quality: float | None = None
    always_on: bool = False
    note: str = ""


@dataclass
class CombinedFinding:
    """1 dòng nằm trong Top-K của bộ kết hợp."""

    row_number: int
    recorded_label: str
    suggested_label: str
    score: float  # điểm kết hợp 0..1, càng cao càng đáng ngờ
    supporters: list[str]  # phương pháp (đang bật) cũng tự gắn cờ dòng này
    ranks: dict[str, float]  # hạng phần trăm của từng phương pháp (chỉ phương pháp có ý kiến)


@dataclass
class CombinedScores:
    """Điểm kết hợp cho MỌI dòng (NaN nếu không phương pháp nào có ý kiến)."""

    row_numbers: np.ndarray
    score: np.ndarray
    n_supporters: np.ndarray


@dataclass
class CombinedDiagnostics:
    alpha: float
    n_rows: int
    k: int  # số dòng trả về
    k_method: str  # phương pháp có trọng số lớn nhất, nguồn của K
    # Mỗi phương pháp: {"weight", "on", "quality", "n_flagged", "reason"}
    methods: dict[str, dict] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class CombinedResult:
    findings: list[CombinedFinding]
    diagnostics: CombinedDiagnostics
    scores: CombinedScores
    # Kết quả gốc của từng phương pháp (chỉ có khi chạy qua detect_class_noise_combined).
    method_results: dict = field(default_factory=dict)


# --------------------------------------------------------------------------------------
# Đổi kết quả của từng phương pháp sang MethodOutput
# --------------------------------------------------------------------------------------
def _flag_mask(row_numbers: np.ndarray, findings) -> np.ndarray:
    return np.isin(row_numbers, np.fromiter((f.row_number for f in findings), dtype=np.int64))


def from_single(result) -> MethodOutput:
    """Từ kết quả của confident_learning.detect_class_noise."""
    s = result.scores
    flagged = _flag_mask(s.row_numbers, result.findings)
    # Dòng bị gắn cờ thì ưu tiên nhãn "tự tin" của Confident Learning; dòng khác dùng nhãn
    # khác nhãn ghi có xác suất cao nhất.
    suggested = np.where(flagged & (s.confident_labels != ""), s.confident_labels, s.suggested_labels)
    return MethodOutput(
        name="single_learning",
        row_numbers=s.row_numbers,
        scores=np.asarray(s.suspicion, dtype=float),
        flagged=flagged,
        suggested_labels=suggested,
        quality=float(result.diagnostics.excess_over_baseline),
        note="Confident Learning + Random Forest",
    )


def from_distance(result) -> MethodOutput:
    """Từ kết quả của distance_based.detect_class_noise_distance."""
    s = result.scores
    return MethodOutput(
        name="distance_based",
        row_numbers=s.row_numbers,
        scores=np.asarray(s.disagreement, dtype=float),
        flagged=_flag_mask(s.row_numbers, result.findings),
        suggested_labels=s.suggested_labels,
        quality=None,
        always_on=True,
        note=f"Mutual k-NN, k={result.diagnostics.k}, độ phủ {result.diagnostics.coverage:.1%}",
    )


def from_ensemble(result) -> MethodOutput:
    """Từ kết quả của ensemble_based.detect_class_noise_ensemble."""
    s = result.scores
    return MethodOutput(
        name="ensemble_based",
        row_numbers=s.row_numbers,
        scores=np.asarray(s.disagreement, dtype=float),
        flagged=_flag_mask(s.row_numbers, result.findings),
        suggested_labels=s.suggested_labels,
        quality=float(result.diagnostics.best_excess_over_baseline),
        note="3 classifier biểu quyết (mức vượt mốc = của classifier tốt nhất)",
    )


# --------------------------------------------------------------------------------------
# Lõi: gộp
# --------------------------------------------------------------------------------------
def compute_weights(on: dict[str, bool], quality: dict[str, float | None], alpha: float) -> dict[str, float]:
    """Trọng số w_m (tổng = 1 trên các phương pháp đang bật; 0 nếu tắt). Xem docstring module."""
    active = [m for m, flag in on.items() if flag]
    if not active:
        return {m: 0.0 for m in on}
    uniform = 1.0 / len(active)
    # q của phương pháp không đo được (k-NN) = trung bình q của các phương pháp có q; không
    # có phương pháp nào có q (chỉ còn k-NN) thì chia đều.
    known = [quality[m] for m in active if quality[m] is not None]
    q_mean = float(np.mean(known)) if known else 1.0
    q = {m: (quality[m] if quality[m] is not None else q_mean) for m in active}
    total_q = sum(q.values())
    weights = {}
    for m in on:
        if m not in active:
            weights[m] = 0.0
        else:
            by_quality = q[m] / total_q if total_q > 0 else uniform
            weights[m] = (1.0 - alpha) * uniform + alpha * by_quality
    return weights


def combine_methods(
    outputs: list[MethodOutput],
    alpha: float = 0.0,
    recorded_labels: pd.Series | None = None,
    min_quality: float = 0.0,
) -> CombinedResult:
    """Gộp các MethodOutput thành 1 danh sách (xem docstring module).

    alpha: 0 = công tắc, 1 = trọng số tỉ lệ thuận mức vượt mốc; giá trị giữa là pha trộn.
    recorded_labels: Series nhãn ghi, index = số dòng 1-based. Không đưa vào thì nhãn ghi
        trong kết quả để trống, và nhãn gợi ý không thể loại bỏ trường hợp trùng nhãn ghi.
    min_quality: phương pháp dựa trên mô hình bị loại nếu mức vượt mốc <= ngưỡng này.
    """
    if not outputs:
        raise ValueError("Cần ít nhất 1 phương pháp để kết hợp.")
    if not 0.0 <= alpha <= 1.0:
        raise ValueError("alpha phải nằm trong khoảng [0, 1].")
    names = [o.name for o in outputs]
    if len(set(names)) != len(names):
        raise ValueError(f"Tên phương pháp bị trùng: {names}")

    # Tập dòng chung = hợp các dòng; phương pháp không chấm dòng nào thì "không có ý kiến".
    all_rows = np.unique(np.concatenate([o.row_numbers for o in outputs]))
    n = len(all_rows)
    warnings: list[str] = []

    ranks: dict[str, pd.Series] = {}
    flagged: dict[str, pd.Series] = {}
    suggested: dict[str, pd.Series] = {}
    on: dict[str, bool] = {}
    quality: dict[str, float | None] = {}
    reasons: dict[str, str] = {}

    for o in outputs:
        sc = pd.Series(o.scores, index=o.row_numbers).reindex(all_rows)
        flagged[o.name] = pd.Series(o.flagged, index=o.row_numbers).reindex(all_rows, fill_value=False).astype(bool)
        suggested[o.name] = pd.Series(o.suggested_labels, index=o.row_numbers).reindex(all_rows, fill_value="")
        quality[o.name] = o.quality
        valid = sc.dropna()
        if o.always_on:
            is_on, why = True, "luôn được dùng (không có mô hình để đo chất lượng)"
        elif o.quality is None:
            is_on, why = False, "không có chỉ số chất lượng"
        elif o.quality > min_quality:
            is_on, why = True, f"mức vượt mốc {o.quality:.3f} > {min_quality:g}"
        else:
            is_on, why = False, f"mức vượt mốc {o.quality:.3f} <= {min_quality:g}: mô hình không hơn cách đoán bừa"
        if is_on and valid.nunique() <= 1:
            # Điểm không đổi giữa các dòng thì không xếp hạng được -> không có thông tin.
            is_on, why = False, "điểm giống nhau ở mọi dòng nên không xếp hạng được"
        on[o.name] = is_on
        reasons[o.name] = why
        # Hạng phần trăm trong chính phương pháp (hoà -> hạng trung bình); NaN giữ NaN.
        ranks[o.name] = sc.rank(pct=True, method="average")

    weights = compute_weights(on, quality, alpha)
    active = [m for m in names if on[m]]
    if not active:
        warnings.append("Không phương pháp nào dùng được; kết quả rỗng.")
    elif len(active) == 1:
        warnings.append(f"Chỉ còn 1 phương pháp đáng tin ({active[0]}), kết quả kết hợp trùng với phương pháp đó.")

    # Điểm kết hợp: trung bình có trọng số trên các phương pháp CÓ ý kiến về dòng đó.
    num = np.zeros(n)
    den = np.zeros(n)
    n_support = np.zeros(n, dtype=int)
    for m in active:
        r = ranks[m].to_numpy()
        has = ~np.isnan(r)
        num[has] += weights[m] * r[has]
        den[has] += weights[m]
        n_support += (flagged[m].to_numpy() & has).astype(int)
    combined = np.where(den > 0, num / np.where(den > 0, den, 1.0), np.nan)

    # K = số dòng mà phương pháp trọng số lớn nhất tự gắn cờ (hoà trọng số -> theo METHOD_ORDER).
    def _order_key(m):
        return METHOD_ORDER.index(m) if m in METHOD_ORDER else len(METHOD_ORDER)

    if active:
        k_method = sorted(active, key=lambda m: (-weights[m], _order_key(m)))[0]
        k = int(flagged[k_method].sum())
    else:
        k_method, k = "", 0

    # Top-K theo điểm kết hợp (hoà điểm -> dòng đứng trước trong file, để lặp lại được).
    order = np.argsort(-np.where(np.isnan(combined), -np.inf, combined), kind="stable")
    order = [i for i in order if not np.isnan(combined[i])][:k]

    # Nhãn ghi: chỉ có khi người gọi đưa bảng đầy đủ vào.
    rec = {}
    if recorded_labels is not None:
        rec = recorded_labels.to_dict()

    findings = []
    for i in order:
        row = int(all_rows[i])
        # Nhãn gợi ý: bỏ phiếu có trọng số giữa các phương pháp bật có gợi ý; hoà -> phương pháp trọng số lớn hơn.
        votes: dict[str, float] = {}
        for m in active:
            lab = suggested[m].iloc[i]
            if lab != "" and lab != rec.get(row, None):
                votes[lab] = votes.get(lab, 0.0) + weights[m]
        if votes:
            best = max(votes.values())
            tied = sorted(l for l, v in votes.items() if abs(v - best) < 1e-12)
            if len(tied) > 1:
                for m in sorted(active, key=lambda m: (-weights[m], _order_key(m))):
                    if suggested[m].iloc[i] in tied:
                        tied = [suggested[m].iloc[i]]
                        break
            suggestion = tied[0]
        else:
            suggestion = ""
        findings.append(
            CombinedFinding(
                row_number=row,
                recorded_label=str(rec.get(row, "")),
                suggested_label=str(suggestion),
                score=float(combined[i]),
                supporters=[m for m in active if flagged[m].iloc[i]],
                ranks={m: float(ranks[m].iloc[i]) for m in active if not np.isnan(ranks[m].iloc[i])},
            )
        )

    diagnostics = CombinedDiagnostics(
        alpha=alpha,
        n_rows=n,
        k=len(findings),
        k_method=k_method,
        methods={
            m: {
                "weight": weights[m],
                "on": on[m],
                "quality": quality[m],
                "n_flagged": int(flagged[m].sum()),
                "reason": reasons[m],
            }
            for m in names
        },
        warnings=warnings,
    )
    scores = CombinedScores(row_numbers=all_rows, score=combined, n_supporters=n_support)
    return CombinedResult(findings=findings, diagnostics=diagnostics, scores=scores)


# --------------------------------------------------------------------------------------
# Tiện ích: chạy cả 3 phương pháp rồi gộp
# --------------------------------------------------------------------------------------
def detect_class_noise_combined(
    df: pd.DataFrame,
    config: ClassNoiseConfig,
    alpha: float = 0.0,
    k_neighbors: int | str = "auto",
    cv_folds: int = 5,
    prepare_features=None,
) -> CombinedResult:
    """Chạy Confident Learning, Mutual k-NN và Ensemble trên df rồi gộp bằng combine_methods.

    prepare_features: hàm (df, feature_columns) -> df dùng làm tiền xử lý cho Mutual k-NN và
        Ensemble (vd cap outlier + log như web); Confident Learning luôn dùng df nguyên (cây
        quyết định không cần, xem CLAUDE.md kế hoạch mục 3). None = không tiền xử lý.
    """
    # Import trong hàm để module này nhẹ khi chỉ dùng combine_methods với điểm đã lưu.
    from .confident_learning import _prepare_usable_subset, detect_class_noise
    from .distance_based import detect_class_noise_distance
    from .ensemble_based import detect_class_noise_ensemble

    df_other = prepare_features(df, config.feature_columns) if prepare_features else df
    r_single = detect_class_noise(df, config)
    r_dist = detect_class_noise_distance(df_other, config, k=k_neighbors)
    r_ens = detect_class_noise_ensemble(df_other, config, cv_folds=cv_folds, random_state=config.random_state)

    usable = _prepare_usable_subset(df, config)
    recorded = pd.Series(usable[config.label_column].astype(str).to_numpy(), index=usable.index.to_numpy() + 1)

    result = combine_methods(
        [from_single(r_single), from_distance(r_dist), from_ensemble(r_ens)],
        alpha=alpha,
        recorded_labels=recorded,
    )
    result.method_results = {"single_learning": r_single, "distance_based": r_dist, "ensemble_based": r_ens}
    return result
