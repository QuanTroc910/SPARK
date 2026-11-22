"""
Phát hiện CLASS NOISE bằng kỹ thuật DISTANCE-BASED: Mutual k-Nearest Neighbor.

Dựa theo bài báo N13 trong Bảng 6 (Gupta & Gupta, 2019) -- Liu, Huawen, and
Shichao Zhang. "Noisy data elimination using mutual k-nearest neighbor for
classification mining." Journal of Systems and Software 85.5 (2012):
1067-1074. Đây là bài DUY NHẤT trong nhóm "Distance based" vừa đạt điểm chất
lượng 9/9 (Bảng 4) vừa có tên bài khớp đúng 100% với định nghĩa distance-based
của chính review (dùng thuần khoảng cách, không train model nào).

KHÁC HẲN Confident Learning (confident_learning.py) ở điểm cốt lõi: module
này KHÔNG train bất kỳ model học máy nào, chỉ dựa vào KHOẢNG CÁCH giữa các
điểm dữ liệu trong không gian đặc trưng -- nên không có khái niệm "xác suất
dự đoán" hay "cross-validation" như Confident Learning.

Ý tưởng cốt lõi -- "láng giềng LẪN NHAU" (mutual neighbor):
  k-NN thông thường là quan hệ 1 CHIỀU: B có thể là 1-trong-k-láng-giềng-gần-
  nhất của A, nhưng A chưa chắc là láng giềng gần của B (thường xảy ra ở vùng
  dữ liệu THƯA, nơi B có rất ít điểm xung quanh nên A "lọt" vào top-k của B dù
  thực ra A khá xa). Để tránh báo nhiễu nhầm vì hiệu ứng này, chỉ coi A và B
  là láng giềng CỦA NHAU khi quan hệ đúng CẢ 2 CHIỀU: A nằm trong k-láng-giềng-
  gần-nhất của B VÀ B nằm trong k-láng-giềng-gần-nhất của A.

4 bước:
  Bước 1: Chuẩn hoá các cột đặc trưng về z-score -- BẮT BUỘC vì khoảng cách
          Euclid nhạy với đơn vị đo (cột "tuổi" 0-100 sẽ át hẳn cột tỉ lệ
          0-1 nếu không chuẩn hoá trước).
  Bước 2: Với mỗi điểm, tìm k láng giềng gần nhất (Euclid).
  Bước 3: Lọc ra láng giềng LẪN NHAU (quan hệ 2 chiều ở trên).
  Bước 4: Với mỗi điểm có >=1 láng giềng lẫn nhau, tính tỉ lệ láng giềng lẫn
          nhau mang nhãn KHÁC nhãn của chính điểm đó -- vượt quá bán (>50%)
          thì gắn cờ nghi ngờ sai nhãn. Điểm KHÔNG có láng giềng lẫn nhau nào
          thì bỏ qua, không kết luận được gì (giống "-1" của Confident
          Learning khi không lớp nào vượt ngưỡng tự tin).

CẢI TIẾN (kế hoạch cải tiến Class Noise, mục 2) -- mặc định GIỮ NGUYÊN kết quả bản cũ khi truyền k là số:
  - Chuẩn hoá: cột NHỊ PHÂN (đúng 2 giá trị) được đưa về 0/1 thay vì z-score (z-score làm cột nhị phân lệch
    tỉ lệ có thang đo khác hẳn các cột còn lại, và kết quả bị phụ thuộc cách mã hoá 0/1 hay 1/2).
  - Điểm bất đồng cho MỌI dòng (`result.scores`), không chỉ dòng vượt ngưỡng -- để bộ kết hợp dùng thứ hạng.
  - Chọn k theo ĐỘ PHỦ: `k="auto"` tìm láng giềng 1 lần với k lớn nhất rồi lấy k NHỎ NHẤT trong
    {3,5,7,9,11,15} mà tỉ lệ dòng có láng giềng lẫn nhau >= `coverage_target` (mặc định 90%).
  - Biến thể để đo: `weighting="distance"` (bỏ phiếu theo 1/khoảng cách), `metric="manhattan"`,
    `pca="auto"` (chỉ bật khi 95% biến thiên nằm trong ít hơn 1/2 số cột).
  - Sửa lỗi nhiều lớp: "nhãn gợi ý" chỉ chọn trong các nhãn KHÁC nhãn ghi (trước đây lấy đa số trên MỌI láng giềng
    nên có dòng bị gắn cờ mà gợi ý trùng đúng nhãn đang ghi).
  - Tìm láng giềng loại chính điểm đó theo CHỈ SỐ (không giả định nó đứng đầu), nên đúng cả khi có nhiều điểm trùng hệt.
  - Vector hoá bước lọc láng giềng lẫn nhau (trước đây vòng lặp Python từng dòng, ~85 giây trên 284k dòng).
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.neighbors import NearestNeighbors

from .config import ClassNoiseConfig

# Các giá trị k thử khi k="auto" (xếp tăng dần); k lớn nhất cũng là số láng giềng tìm 1 lần.
K_CANDIDATES = (3, 5, 7, 9, 11, 15)


@dataclass
class DistanceNoiseFinding:
    """Kết quả cho ĐÚNG 1 dòng bị nghi ngờ sai nhãn.

    disagreement_ratio: tỉ lệ láng giềng LẪN NHAU mang nhãn khác (0..1) --
    dùng để sắp xếp mức độ đáng ngờ, đóng vai trò tương đương "margin" của
    ClassNoiseFinding bên confident_learning.py. Khi weighting="distance" đây là
    tỉ lệ TRỌNG SỐ (láng giềng gần tính nặng hơn) thay vì tỉ lệ số đếm.
    """

    row_number: int
    recorded_label: str
    suggested_label: str
    disagreement_ratio: float


@dataclass
class DistanceNoiseScores:
    """Điểm bất đồng của MỌI dòng dùng được (findings chỉ giữ dòng vượt ngưỡng).

    Bốn mảng cùng độ dài = số dòng dùng được, cùng thứ tự với df đầu vào:
      row_numbers: số dòng 1-based (index + 1).
      disagreement: tỉ lệ bất đồng; NaN nếu dòng KHÔNG có láng giềng lẫn nhau nào (không kết luận được).
      n_mutual: số láng giềng lẫn nhau của dòng.
      suggested_labels: nhãn gợi ý (đa số trong các láng giềng lẫn nhau mang nhãn KHÁC nhãn ghi);
        chuỗi rỗng nếu không có láng giềng nào khác nhãn.
    """

    row_numbers: np.ndarray
    disagreement: np.ndarray
    n_mutual: np.ndarray
    suggested_labels: np.ndarray


@dataclass
class DistanceNoiseDiagnostics:
    """Chỉ số chẩn đoán cho 1 lượt chạy -- vai trò tương đương
    ClassNoiseDiagnostics bên confident_learning.py, nhưng đổi khác vì
    phương pháp distance-based không có model/cv_accuracy để soi.

    n_rows_with_mutual_neighbors: bao nhiêu dòng có ít nhất 1 láng giềng lẫn
    nhau -- đây là chỉ số "độ phủ" (coverage) PHẢI xem trước khi tin findings:
    nếu quá ít dòng có láng giềng lẫn nhau (vd do k quá nhỏ hoặc dữ liệu quá
    thưa), phần lớn dòng không kết luận được gì, findings sẽ rất ít dù dữ
    liệu có thể vẫn còn nhiễu thật.
    """

    n_rows_total: int
    n_rows_used: int
    k: int
    n_rows_with_mutual_neighbors: int
    class_names: list[str]
    class_counts: dict[str, int]
    # --- các trường thêm ở mục 2 (có giá trị mặc định để code cũ vẫn chạy) ---
    k_mode: str = "fixed"                     # "fixed" (người dùng chọn k) | "auto" (chọn theo độ phủ)
    coverage: float = 0.0                     # n_rows_with_mutual_neighbors / n_rows_used
    coverage_by_k: dict[int, float] = field(default_factory=dict)   # độ phủ từng k đã thử (chỉ khi k="auto")
    metric: str = "euclidean"
    weighting: str = "count"
    binary_columns: list[str] = field(default_factory=list)         # cột nhị phân được đưa về 0/1
    pca: dict = field(default_factory=dict)   # {"mode", "applied", "n_components", "n_features"}
    warnings: list[str] = field(default_factory=list)


@dataclass
class DistanceNoiseResult:
    findings: list[DistanceNoiseFinding]
    diagnostics: DistanceNoiseDiagnostics
    scores: DistanceNoiseScores | None = None


def _prepare_usable_subset(df: pd.DataFrame, config: ClassNoiseConfig) -> pd.DataFrame:
    """Lọc dòng dùng được: nhãn không rỗng, mọi cột đặc trưng ép được thành
    số -- lặp lại y hệt logic của confident_learning.py (không import dùng
    chung vì đây là hàm private riêng của module đó, giữ 2 module độc lập
    nhau để không bị ràng buộc chéo khi sửa sau này).
    """
    working = df.copy()
    for col in config.feature_columns:
        working[col] = pd.to_numeric(working[col], errors="coerce")

    label_ok = working[config.label_column].astype(str).str.strip() != ""
    features_ok = working[config.feature_columns].notna().all(axis=1)
    return working[label_ok & features_ok]


# --------------------------------------------------------------------------------------
# Bước 1: chuẩn hoá (+ PCA tuỳ chọn)
# --------------------------------------------------------------------------------------
def _scale_features(X_raw: np.ndarray, keep_binary: bool) -> tuple[np.ndarray, list[int]]:
    """z-score từng cột, TRỪ cột nhị phân (đúng 2 giá trị) được đưa về 0/1. Cột hằng -> 0.
    Dùng độ lệch chuẩn tổng thể (ddof=0) -- giống hệt StandardScaler của bản cũ."""
    X = np.zeros(X_raw.shape, dtype=float)
    binary_cols: list[int] = []
    for j in range(X_raw.shape[1]):
        col = X_raw[:, j].astype(float)
        uniq = np.unique(col)
        if keep_binary and len(uniq) == 2:
            X[:, j] = (col - uniq[0]) / (uniq[1] - uniq[0])
            binary_cols.append(j)
            continue
        std = col.std()
        X[:, j] = 0.0 if std == 0 else (col - col.mean()) / std
    return X, binary_cols


def _maybe_pca(X: np.ndarray, mode) -> tuple[np.ndarray, dict]:
    """PCA giữ 95% biến thiên. mode: False = tắt; True = luôn dùng khi giảm được cột;
    "auto" = chỉ dùng khi số thành phần cần giữ < 1/2 số cột (tức dữ liệu thật sự dư thừa)."""
    n_features = X.shape[1]
    info = {"mode": mode, "applied": False, "n_components": n_features, "n_features": n_features}
    if mode is False or n_features < 2:
        return X, info
    full = PCA().fit(X)
    n95 = int(np.searchsorted(np.cumsum(full.explained_variance_ratio_), 0.95) + 1)
    n95 = min(n95, n_features)
    info["n_components"] = n95
    use = n95 < n_features if mode is True else n95 < n_features / 2
    if not use:
        return X, info
    info["applied"] = True
    return full.transform(X)[:, :n95], info


# --------------------------------------------------------------------------------------
# Bước 2-3: láng giềng + lọc láng giềng lẫn nhau (vector hoá)
# --------------------------------------------------------------------------------------
def _neighbor_table(X: np.ndarray, k_max: int, metric: str) -> tuple[np.ndarray, np.ndarray]:
    """Trả (chỉ số, khoảng cách) của k_max láng giềng gần nhất, ĐÃ LOẠI chính điểm đó.

    Loại theo CHỈ SỐ chứ không giả định chính nó đứng đầu: khi có nhiều điểm trùng hệt (khoảng cách 0),
    chính nó có thể không đứng đầu, thậm chí không nằm trong top; trường hợp không có thì bỏ cột xa nhất."""
    n = len(X)
    n_query = min(k_max + 1, n)
    nn = NearestNeighbors(n_neighbors=n_query, metric=metric, n_jobs=-1).fit(X)
    dist, idx = nn.kneighbors(X)
    keep = idx != np.arange(n)[:, None]
    self_absent = keep.all(axis=1)
    keep[self_absent, -1] = False
    return idx[keep].reshape(n, n_query - 1), dist[keep].reshape(n, n_query - 1)


def _mutual_edges(idx: np.ndarray, dist: np.ndarray, k: int):
    """Các cạnh (i -> j) mà j nằm trong k láng giềng của i VÀ i nằm trong k láng giềng của j."""
    n = idx.shape[0]
    kk = min(k, idx.shape[1])
    rows = np.repeat(np.arange(n), kk)
    cols = idx[:, :kk].ravel()
    forward = rows.astype(np.int64) * n + cols
    reverse = cols.astype(np.int64) * n + rows
    mutual = np.isin(reverse, forward)
    return rows[mutual], cols[mutual], dist[:, :kk].ravel()[mutual]


def _coverage(idx: np.ndarray, dist: np.ndarray, k: int) -> float:
    rows_m, _, _ = _mutual_edges(idx, dist, k)
    return float(np.unique(rows_m).size / idx.shape[0])


def choose_k_by_coverage(
    idx: np.ndarray, dist: np.ndarray, candidates=K_CANDIDATES, target: float = 0.9
) -> tuple[int, dict[int, float]]:
    """k NHỎ NHẤT trong `candidates` mà độ phủ >= target (độ phủ chỉ tăng khi k tăng nên dừng ở k đầu tiên đạt).
    Không k nào đạt thì lấy k lớn nhất. Trả (k, độ phủ từng k đã tính)."""
    usable = [c for c in sorted(candidates) if c <= idx.shape[1]] or [idx.shape[1]]
    coverage_by_k: dict[int, float] = {}
    for c in usable:
        coverage_by_k[c] = _coverage(idx, dist, c)
        if coverage_by_k[c] >= target:
            return c, coverage_by_k
    return usable[-1], coverage_by_k


# --------------------------------------------------------------------------------------
# Hàm chính
# --------------------------------------------------------------------------------------
def detect_class_noise_distance(
    df: pd.DataFrame,
    config: ClassNoiseConfig,
    k: int | str = 5,
    disagreement_threshold: float = 0.5,
    *,
    metric: str = "euclidean",
    weighting: str = "count",
    pca=False,
    keep_binary: bool = True,
    coverage_target: float = 0.9,
    k_candidates=K_CANDIDATES,
) -> DistanceNoiseResult:
    """Hàm chính: chạy đủ 4 bước Mutual k-NN trên df theo config.

    k: số láng giềng gần nhất xét cho mỗi điểm (mặc định 5, giá trị phổ biến trong tài liệu k-NN),
       hoặc "auto" = chọn k nhỏ nhất trong `k_candidates` đạt độ phủ `coverage_target`.
    disagreement_threshold: tỉ lệ láng giềng lẫn nhau mang nhãn khác TỐI
       THIỂU để gắn cờ (mặc định 0.5 = đa số láng giềng không đồng ý với
       nhãn ghi thì mới nghi ngờ).
    metric: "euclidean" (mặc định) hoặc "manhattan".
    weighting: "count" (mặc định, mỗi láng giềng 1 phiếu) hoặc "distance" (phiếu = 1/(khoảng cách + eps),
       eps = 10% khoảng cách trung vị để điểm trùng hệt không có trọng số vô hạn).
    pca: False (mặc định) | True | "auto" -- xem `_maybe_pca`.
    keep_binary: cột nhị phân đưa về 0/1 thay vì z-score.
    """
    if metric not in ("euclidean", "manhattan"):
        raise ValueError(f"metric phải là 'euclidean' hoặc 'manhattan', nhận được {metric!r}")
    if weighting not in ("count", "distance"):
        raise ValueError(f"weighting phải là 'count' hoặc 'distance', nhận được {weighting!r}")
    if k != "auto" and (not isinstance(k, (int, np.integer)) or k < 1):
        raise ValueError(f"k phải là số nguyên >= 1 hoặc 'auto', nhận được {k!r}")

    usable = _prepare_usable_subset(df, config)
    n = len(usable)
    y_labels = usable[config.label_column].astype(str).to_numpy()
    row_numbers = usable.index.to_numpy() + 1  # quy ước 1-based, khớp ClassNoiseFinding
    classes, lab = np.unique(y_labels, return_inverse=True)
    class_counts_raw = pd.Series(y_labels).value_counts()

    def make_diag(**kw) -> DistanceNoiseDiagnostics:
        return DistanceNoiseDiagnostics(
            n_rows_total=len(df), n_rows_used=n,
            class_names=list(class_counts_raw.index),
            class_counts={str(c): int(cnt) for c, cnt in class_counts_raw.items()},
            metric=metric, weighting=weighting, **kw,
        )

    if n < 3:  # quá ít dòng để có láng giềng lẫn nhau
        diag = make_diag(k=0 if k == "auto" else int(k), n_rows_with_mutual_neighbors=0,
                         warnings=["Quá ít dòng dùng được (< 3) để tìm láng giềng."])
        empty = DistanceNoiseScores(row_numbers, np.full(n, np.nan), np.zeros(n, int), np.full(n, "", dtype=object))
        return DistanceNoiseResult(findings=[], diagnostics=diag, scores=empty)

    # Bước 1: chuẩn hoá (+ PCA tuỳ chọn)
    X_raw = usable[config.feature_columns].to_numpy()
    X, binary_idx = _scale_features(X_raw, keep_binary)
    X, pca_info = _maybe_pca(X, pca)

    # Bước 2: láng giềng (tìm 1 lần; k tự chọn thì tìm với k lớn nhất rồi cắt bớt)
    cands = sorted(set(int(c) for c in k_candidates))
    k_search = min(max(cands) if k == "auto" else int(k), n - 1)
    idx, dist = _neighbor_table(X, k_search, metric)

    warnings: list[str] = []
    coverage_by_k: dict[int, float] = {}
    if k == "auto":
        k_used, coverage_by_k = choose_k_by_coverage(idx, dist, cands, coverage_target)
        if coverage_by_k[k_used] < coverage_target:
            warnings.append(
                f"Không k nào đạt độ phủ {coverage_target:.0%} (cao nhất {coverage_by_k[k_used]:.0%} ở k = {k_used}): "
                "dữ liệu quá thưa hoặc nhiều chiều, nhiều dòng sẽ không kết luận được."
            )
    else:
        k_used = min(int(k), n - 1)

    # Bước 3: láng giềng LẪN NHAU
    rows_m, cols_m, d_m = _mutual_edges(idx, dist, k_used)

    # Bước 4: tỉ lệ (có trọng số) láng giềng lẫn nhau mang nhãn KHÁC nhãn hiện tại
    if weighting == "distance":
        positive = d_m[d_m > 0]
        eps = 0.1 * float(np.median(positive)) if positive.size else 1.0
        w = 1.0 / (d_m + eps)
    else:
        w = np.ones(len(rows_m))
    differs = lab[rows_m] != lab[cols_m]
    n_mutual = np.bincount(rows_m, minlength=n)
    w_total = np.bincount(rows_m, weights=w, minlength=n)
    w_differ = np.bincount(rows_m, weights=w * differs, minlength=n)
    has_mutual = n_mutual > 0
    ratio = np.full(n, np.nan)
    ratio[has_mutual] = w_differ[has_mutual] / w_total[has_mutual]

    # Nhãn gợi ý = nhãn chiếm nhiều phiếu nhất trong các láng giềng lẫn nhau mang nhãn KHÁC nhãn ghi
    suggested = np.full(n, "", dtype=object)
    if differs.any():
        r, c, ww = rows_m[differs], lab[cols_m[differs]], w[differs]
        uniq_rows, inverse = np.unique(r, return_inverse=True)
        votes = np.bincount(inverse * len(classes) + c, weights=ww,
                            minlength=len(uniq_rows) * len(classes)).reshape(len(uniq_rows), len(classes))
        suggested[uniq_rows] = classes[votes.argmax(axis=1)]  # hoà phiếu: lấy nhãn đứng trước theo thứ tự chữ cái

    flagged = np.where(ratio > disagreement_threshold)[0]            # NaN > x luôn False
    flagged = flagged[np.argsort(-ratio[flagged], kind="stable")]
    findings = [
        DistanceNoiseFinding(
            row_number=int(row_numbers[i]), recorded_label=str(y_labels[i]),
            suggested_label=str(suggested[i]), disagreement_ratio=float(ratio[i]),
        )
        for i in flagged
    ]

    n_with_mutual = int(has_mutual.sum())
    diagnostics = make_diag(
        k=int(k_used), n_rows_with_mutual_neighbors=n_with_mutual,
        k_mode="auto" if k == "auto" else "fixed",
        coverage=n_with_mutual / n, coverage_by_k=coverage_by_k,
        binary_columns=[config.feature_columns[j] for j in binary_idx],
        pca=pca_info, warnings=warnings,
    )
    scores = DistanceNoiseScores(row_numbers=row_numbers, disagreement=ratio, n_mutual=n_mutual,
                                 suggested_labels=suggested)
    return DistanceNoiseResult(findings=findings, diagnostics=diagnostics, scores=scores)
