"""
PHƯƠNG PHÁP KẾT HỢP cho Class Noise (kế hoạch mục 4, 22/11/2026) -- đóng góp riêng của đề tài.

Vấn đề: các phương pháp có sẵn (Confident Learning, Mutual k-NN, Ensemble) cho các danh sách
nghi ngờ khác nhau, chất lượng thay đổi theo dữ liệu (trên dữ liệu có đặc trưng yếu thì mô
hình học máy gần như đoán bừa, trong khi k-NN vẫn dùng được; ngược lại có dữ liệu mô hình
tốt hơn hẳn). Người dùng không biết nên tin phương pháp nào. Module này gộp chúng lại thành
MỘT danh sách duy nhất, tự biết phương pháp nào đáng tin trên chính dữ liệu đang xét.

PHƯƠNG PHÁP THÀNH PHẦN (23/11/2026): trên web bộ kết hợp CHỈ gộp Confident Learning + Mutual k-NN
(`DEFAULT_METHODS`). Ensemble vẫn nằm trong code và gộp được qua tham số `methods` của
`detect_class_noise_combined()` (dùng cho thực nghiệm), nhưng không còn chạy mặc định.

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

Bước 4 + 5 (điểm kết hợp và số dòng K) nằm riêng trong `merge_scores_and_select_k()`: công thức gộp
điểm và luật chọn K CHƯA chốt (chờ thực nghiệm), nên tách ra 1 hàm để sau này đổi đúng 1 chỗ, không
đụng tới phần hạng phần trăm / cổng chất lượng / trọng số ở trên.

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

# Phương pháp thành phần mặc định của bộ kết hợp (web): Confident Learning + Mutual k-NN. Ensemble KHÔNG nằm
# trong mặc định (vẫn gộp được nếu truyền vào `methods`).
DEFAULT_METHODS = ("single_learning", "distance_based")

# Gọi tắt cho tiện: "single" = Confident Learning, "distance" = Mutual k-NN, "ensemble" = Ensemble.
METHOD_ALIASES = {"single": "single_learning", "distance": "distance_based", "ensemble": "ensemble_based"}


def normalize_methods(methods) -> tuple[str, ...]:
    """Chuẩn hoá danh sách phương pháp thành phần: nhận tên đầy đủ hoặc tên gọi tắt, trả tuple tên đầy đủ
    theo đúng METHOD_ORDER (nên thứ tự người gọi liệt kê không ảnh hưởng kết quả). Rỗng / lạ / trùng thì báo lỗi."""
    if isinstance(methods, str):
        methods = (methods,)
    names: list[str] = []
    for m in methods:
        name = METHOD_ALIASES.get(m, m)
        if name not in METHOD_ORDER:
            raise ValueError(f"Phương pháp thành phần không hợp lệ: {m!r}. Chọn trong {list(METHOD_ORDER)}.")
        if name in names:
            raise ValueError(f"Phương pháp thành phần bị trùng: {m!r}.")
        names.append(name)
    if not names:
        raise ValueError("Cần chọn ít nhất 1 phương pháp thành phần.")
    return tuple(sorted(names, key=METHOD_ORDER.index))


def _order_key(name: str) -> int:
    """Vị trí của phương pháp trong METHOD_ORDER (tên lạ xếp cuối) -- dùng để phá hoà."""
    return METHOD_ORDER.index(name) if name in METHOD_ORDER else len(METHOD_ORDER)


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
class MethodFinding:
    """1 dòng mà CHÍNH một phương pháp thành phần tự gắn cờ (theo luật riêng của nó, không qua bộ kết hợp).

    score là điểm nghi ngờ của riêng phương pháp đó: Confident Learning = 1 - xác suất mô hình cho nhãn đang ghi;
    Mutual k-NN = tỉ lệ láng giềng lẫn nhau mang nhãn khác.
    """

    row_number: int
    recorded_label: str
    suggested_label: str
    score: float


@dataclass
class MergedScores:
    """Kết quả bước "gộp điểm + chọn K" (xem merge_scores_and_select_k)."""

    combined: np.ndarray  # điểm kết hợp từng dòng, 0..1 (NaN = không phương pháp đang bật nào có ý kiến)
    n_supporters: np.ndarray  # số phương pháp đang bật tự gắn cờ dòng đó
    k: int  # số dòng trả về
    k_method: str  # phương pháp là nguồn của K ("" nếu không phương pháp nào đang bật)


@dataclass
class CombinedResult:
    findings: list[CombinedFinding]
    diagnostics: CombinedDiagnostics
    scores: CombinedScores
    # Kết quả gốc của từng phương pháp (chỉ có khi chạy qua detect_class_noise_combined).
    method_results: dict = field(default_factory=dict)
    # Đầu ra đã chuẩn hoá của từng phương pháp thành phần (điểm + cờ + nhãn gợi ý), tên -> MethodOutput.
    # Có ngay cả khi gọi thẳng combine_methods; dùng để liệt kê "danh sách riêng của từng phương pháp".
    method_outputs: dict = field(default_factory=dict)
    # Nhãn đang ghi (index = số dòng 1-based); None nếu người gọi không đưa vào.
    recorded_labels: pd.Series | None = None


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


def from_ensemble_diverse(result) -> MethodOutput:
    """Từ kết quả của ensemble_diverse.detect_class_noise_ensemble_diverse (Ensemble 5 họ, kế hoạch mục 7).

    Dùng ĐIỂM MỀM (trung bình 1 - P(nhãn ghi) của 5 mô hình) để xếp hạng, và luật phiếu cứng min_votes để
    gắn cờ. Mang tên "ensemble_based" để thay đúng chỗ của Ensemble cũ trong thứ tự phá hoà trọng số.
    Mức vượt mốc = của mô hình tốt nhất tính bằng argmax thuần (không qua ngưỡng cân bằng).
    """
    s = result.scores
    return MethodOutput(
        name="ensemble_based",
        row_numbers=s.row_numbers,
        scores=np.asarray(s.suspicion, dtype=float),
        flagged=_flag_mask(s.row_numbers, result.findings),
        suggested_labels=s.suggested_labels,
        quality=float(result.diagnostics.best_excess_over_baseline),
        note=f"Ensemble 5 họ, bỏ phiếu {result.diagnostics.min_votes}/5",
    )


def method_findings(output: MethodOutput, recorded_labels: pd.Series | None = None) -> list[MethodFinding]:
    """Danh sách RIÊNG của 1 phương pháp: các dòng mà chính nó tự gắn cờ, xếp theo điểm nghi ngờ của nó giảm dần
    (hoà điểm -> dòng đứng trước trong file, để lặp lại được).

    Dùng cho phần "xem thêm" trên web: người dùng xem từng phương pháp thành phần đang nghi những dòng nào, không
    chỉ danh sách đã gộp. recorded_labels: Series nhãn ghi, index = số dòng 1-based; không đưa vào thì nhãn ghi để trống.
    """
    scores = np.asarray(output.scores, dtype=float)
    idx = np.flatnonzero(np.asarray(output.flagged, dtype=bool))
    # Điểm NaN (không có ý kiến) xếp cuối; thực tế dòng đã gắn cờ luôn có điểm.
    order = idx[np.argsort(-np.where(np.isnan(scores[idx]), -np.inf, scores[idx]), kind="stable")]
    rec = recorded_labels.to_dict() if recorded_labels is not None else {}
    out = []
    for i in order:
        row = int(output.row_numbers[i])
        out.append(
            MethodFinding(
                row_number=row,
                recorded_label=str(rec.get(row, "")),
                suggested_label=str(output.suggested_labels[i]),
                score=float(scores[i]),
            )
        )
    return out


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


def merge_scores_and_select_k(
    ranks: dict[str, np.ndarray],
    flagged: dict[str, np.ndarray],
    weights: dict[str, float],
    active: list[str],
    n_rows: int,
) -> MergedScores:
    """BƯỚC "GỘP ĐIỂM + CHỌN K" (bước 4 và 5 trong docstring module) -- tách riêng để sau này đổi công thức gộp
    điểm hoặc luật chọn K chỉ phải sửa hàm này. HIỆN TẠI (chưa chốt, chờ thực nghiệm):

      * điểm kết hợp = trung bình có trọng số của hạng phần trăm, chỉ tính các phương pháp ĐANG BẬT và CÓ ý
        kiến về dòng đó (hạng NaN = không có ý kiến);
      * K = số dòng mà phương pháp có trọng số LỚN NHẤT tự gắn cờ theo luật riêng của nó (hoà trọng số -> theo
        METHOD_ORDER).

    ranks / flagged: tên phương pháp -> mảng độ dài n_rows (hạng phần trăm 0..1, NaN nếu không có ý kiến / cờ
        True-False); weights: tên -> trọng số; active: các phương pháp đang bật, theo thứ tự cộng dồn.
    Trả MergedScores; việc lấy Top-K dòng theo điểm kết hợp và ghép nhãn gợi ý do combine_methods làm.
    """
    num = np.zeros(n_rows)
    den = np.zeros(n_rows)
    n_support = np.zeros(n_rows, dtype=int)
    for m in active:
        r = ranks[m]
        has = ~np.isnan(r)
        num[has] += weights[m] * r[has]
        den[has] += weights[m]
        n_support += (flagged[m] & has).astype(int)
    combined = np.where(den > 0, num / np.where(den > 0, den, 1.0), np.nan)

    if active:
        k_method = sorted(active, key=lambda m: (-weights[m], _order_key(m)))[0]
        k = int(flagged[k_method].sum())
    else:
        k_method, k = "", 0
    return MergedScores(combined=combined, n_supporters=n_support, k=k, k_method=k_method)


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

    # Gộp điểm + chọn K (công thức và luật chọn K nằm riêng trong merge_scores_and_select_k).
    merged = merge_scores_and_select_k(
        ranks={m: ranks[m].to_numpy() for m in names},
        flagged={m: flagged[m].to_numpy() for m in names},
        weights=weights,
        active=active,
        n_rows=n,
    )
    combined, n_support, k_method, k = merged.combined, merged.n_supporters, merged.k_method, merged.k

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
    return CombinedResult(
        findings=findings,
        diagnostics=diagnostics,
        scores=scores,
        method_outputs={o.name: o for o in outputs},
        recorded_labels=recorded_labels,
    )


# --------------------------------------------------------------------------------------
# Tiện ích: chạy các phương pháp thành phần rồi gộp
# --------------------------------------------------------------------------------------
def detect_class_noise_combined(
    df: pd.DataFrame,
    config: ClassNoiseConfig,
    alpha: float = 0.0,
    k_neighbors: int | str = "auto",
    cv_folds: int = 5,
    prepare_features=None,
    methods=DEFAULT_METHODS,
) -> CombinedResult:
    """Chạy các phương pháp thành phần trên df rồi gộp bằng combine_methods.

    methods: phương pháp thành phần, mặc định Confident Learning + Mutual k-NN (`DEFAULT_METHODS`). Nhận tên đầy
        đủ ("single_learning", "distance_based", "ensemble_based") hoặc gọi tắt ("single", "distance", "ensemble").
        Chỉ phương pháp được chọn mới chạy (Ensemble không chạy nếu không chọn).
    k_neighbors: k của Mutual k-NN (số nguyên hoặc "auto" = chọn theo độ phủ).
    cv_folds: số fold của Ensemble (Confident Learning lấy `config.cv_folds`); không tác dụng nếu không chọn Ensemble.
    prepare_features: hàm (df, feature_columns) -> df dùng làm tiền xử lý cho Mutual k-NN và
        Ensemble (vd cap outlier + log như web); Confident Learning luôn dùng df nguyên (cây
        quyết định không cần, xem CLAUDE.md kế hoạch mục 3). None = không tiền xử lý.
        Lưu ý: `cap_outliers()` / `log_transform()` của feature_selection.py làm việc trên bảng
        DẠNG CHUỖI như `load_data()` trả về (đọc `dtype=str`); đưa vào bảng đã là số sẽ lỗi kiểu dữ liệu.
    """
    selected = normalize_methods(methods)

    # Import trong hàm để module này nhẹ khi chỉ dùng combine_methods với điểm đã lưu, và để phương pháp
    # không được chọn (vd Ensemble) không bị nạp.
    from .confident_learning import _prepare_usable_subset

    needs_prepared = "distance_based" in selected or "ensemble_based" in selected
    df_other = prepare_features(df, config.feature_columns) if (prepare_features and needs_prepared) else df

    outputs: list[MethodOutput] = []
    method_results: dict = {}
    if "single_learning" in selected:
        from .confident_learning import detect_class_noise

        method_results["single_learning"] = detect_class_noise(df, config)
        outputs.append(from_single(method_results["single_learning"]))
    if "distance_based" in selected:
        from .distance_based import detect_class_noise_distance

        method_results["distance_based"] = detect_class_noise_distance(df_other, config, k=k_neighbors)
        outputs.append(from_distance(method_results["distance_based"]))
    if "ensemble_based" in selected:
        from .ensemble_based import detect_class_noise_ensemble

        method_results["ensemble_based"] = detect_class_noise_ensemble(
            df_other, config, cv_folds=cv_folds, random_state=config.random_state
        )
        outputs.append(from_ensemble(method_results["ensemble_based"]))

    usable = _prepare_usable_subset(df, config)
    recorded = pd.Series(usable[config.label_column].astype(str).to_numpy(), index=usable.index.to_numpy() + 1)

    result = combine_methods(outputs, alpha=alpha, recorded_labels=recorded)
    result.method_results = method_results
    return result
