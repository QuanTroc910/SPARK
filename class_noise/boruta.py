"""Boruta (Kursa & Rudnicki, "Feature Selection with the Boruta Package", J. Stat. Softw. 36(11), 2010,
doi 10.18637/jss.v036.i11), viết lại theo các bước của bản chuẩn BorutaPy, chỉ dùng scikit-learn + scipy.

Mỗi vòng: tạo cột bóng (xáo trộn từng cột chưa bị loại) -> train Random Forest trên cột thật + cột bóng
-> cột thật có độ quan trọng > cột bóng mạnh nhất (perc = 100) thì +1 "lần thắng" -> kiểm định nhị thức cho
các cột "chưa quyết định", hiệu chỉnh 2 bước (Benjamini-Hochberg rồi Bonferroni theo số vòng, như two_step=True
của BorutaPy) -> "giữ" / "bỏ". Dừng khi hết cột chưa quyết định hoặc đủ max_iter vòng.
Chỉ BỎ cột bị kết luận "bỏ"; cột "chưa quyết định" vẫn giữ (chưa chứng minh vô ích thì không bỏ).
Khác BorutaPy duy nhất: số cây mỗi vòng cố định (mặc định 50) để chạy nhanh."""
from dataclasses import dataclass, field
import numpy as np
import pandas as pd
from scipy.stats import binom
from sklearn.ensemble import RandomForestClassifier


@dataclass
class BorutaResult:
    kept: list[str]
    rejected: list[str]
    tentative: list[str] = field(default_factory=list)
    n_iter: int = 0


def _benjamini_hochberg(p: np.ndarray, alpha: float) -> np.ndarray:
    n = len(p)
    if n == 0:
        return np.zeros(0, bool)
    order = np.argsort(p)
    adj = p[order] * n / np.arange(1, n + 1)
    adj = np.minimum.accumulate(adj[::-1])[::-1]
    out = np.zeros(n, bool)
    out[order] = adj <= alpha
    return out


def boruta_select(X: pd.DataFrame, y, max_iter: int = 100, alpha: float = 0.05,
                  n_estimators: int = 50, random_state: int = 42) -> BorutaResult:
    """X: cột số, KHÔNG ô trống; y: nhãn (có thể còn nhãn sai)."""
    rng = np.random.default_rng(random_state)
    A = X.to_numpy(dtype=float)
    y = np.asarray(y)
    p = A.shape[1]
    dec = np.zeros(p, int)   # 0 chưa quyết định, 1 giữ, -1 bỏ
    hits = np.zeros(p, int)
    it = 0
    while (dec == 0).any() and it < max_iter:
        it += 1
        active = np.where(dec >= 0)[0]
        real = A[:, active]
        shadow = np.column_stack([rng.permutation(real[:, j]) for j in range(real.shape[1])])
        rf = RandomForestClassifier(n_estimators=n_estimators, n_jobs=-1,
                                    random_state=int(rng.integers(1 << 31)))
        imp = rf.fit(np.hstack([real, shadow]), y).feature_importances_
        k = len(active)
        hits[active[imp[:k] > imp[k:].max()]] += 1
        tent = np.where(dec == 0)[0]
        p_acc = binom.sf(hits[tent] - 1, it, 0.5)   # P(thắng >= hits) nếu chỉ do may rủi
        p_rej = binom.cdf(hits[tent], it, 0.5)      # P(thắng <= hits)
        acc = _benjamini_hochberg(p_acc, alpha) & (p_acc <= alpha / it)
        rej = _benjamini_hochberg(p_rej, alpha) & (p_rej <= alpha / it)
        dec[tent[acc]] = 1
        dec[tent[rej]] = -1
    cols = np.array(X.columns)
    return BorutaResult(kept=list(cols[dec >= 0]), rejected=list(cols[dec == -1]),
                        tentative=list(cols[dec == 0]), n_iter=it)
