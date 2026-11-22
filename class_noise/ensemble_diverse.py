"""
ENSEMBLE 5 HỌ cho Class Noise (kế hoạch mục 7, 22/11/2026) -- bản làm lại của ensemble_based.py.

`ensemble_based.py` (3 classifier tuyến tính/xác suất/biên cực đại, bỏ phiếu bằng NHÃN, có
class_weight="balanced") trên thực nghiệm gắn cờ rất nhiều dòng với Precision thấp (~0,2 trên Car,
0,01-0,05 trên Credit Card) và bị cổng chất lượng của bộ kết hợp loại ở nhiều bộ dữ liệu. File này giữ
NGUYÊN bản cũ làm đối chứng và thêm bản mới, sửa bốn điểm:

  1. NĂM HỌ thuật toán, đều có xác suất dự đoán (predict_proba):
        LogisticRegression (tuyến tính) · GaussianNB (xác suất) · KNeighbors (dựa láng giềng) ·
        MLP (mạng nơ-ron) · HistGradientBoosting (cây tăng cường).
     Có xác suất nên chấm điểm nghi ngờ mịn cho MỌI dòng (bản cũ chỉ có 4 mức 0/⅓/⅔/1).
     LƯU Ý: KNeighbors cùng "họ láng giềng" với Mutual k-NN và HistGradientBoosting cùng "họ cây" với Random
     Forest của Confident Learning; ở mục 11 ta từng loại 2 họ này vì sợ trùng góc nhìn. Kế hoạch mục 7 đưa
     lại để có mô hình mạnh hơn -- nên có ma trận ĐỘ ĐA DẠNG (diagnostics.pairwise_agreement) để đo trùng thật.
  2. BỎ class_weight="balanced" và bỏ ép tiên nghiệm đều của GaussianNB: các mô hình học theo tỉ lệ lớp thật.
     Bù lớp hiếm bằng trọng số làm xác suất lớp hiếm bị đẩy lên nên mô hình "tưởng" nhiều dòng là lớp hiếm.
  3. CÂN HAI LOẠI LỖI bằng ngưỡng quyết định (thay cho việc bù bằng trọng số). Với 2 lớp: ngưỡng của từng
     mô hình được chọn sao cho tỉ lệ dương giả = tỉ lệ âm giả (điểm cắt EER trên đường ROC, tính từ xác suất
     out-of-fold so với nhãn ghi; lớp hiếm là lớp "dương"). Với nhiều lớp (không có "2 loại lỗi"), dùng luật
     cân bằng lớp argmax p(c)/tần suất(c). CHƯA đọc bài gốc Khoshgoftaar 2005: đây là cách hiểu "cân 2 loại
     lỗi" của dự án, chưa kiểm là đúng từng chi tiết của bài.
  4. MỨC BỎ PHIẾU min_votes (3/5, 4/5, 5/5): dòng bị gắn cờ khi ít nhất min_votes mô hình dự đoán KHÁC nhãn ghi.
     Mức càng cao càng thận trọng (5/5 = mọi mô hình đồng ý nhãn ghi sai).

ĐIỂM NGHI NGỜ cho mọi dòng: suspicion = trung bình trên 5 mô hình của (1 - P(nhãn ghi)), P là xác suất
out-of-fold -- bỏ phiếu mềm; dùng để xếp hạng và để bộ kết hợp (combined.py) gộp. Luật gắn cờ riêng của
phương pháp vẫn dùng phiếu cứng (min_votes) để ra danh sách.

CHẨN ĐOÁN: accuracy / mức vượt mốc từng mô hình (argmax thuần, KHÔNG qua ngưỡng cân bằng, để so được với
baseline), ngưỡng đã chọn, ma trận tỉ lệ dự đoán giống nhau từng cặp (độ đa dạng), phân bố số phiếu.

Module thuần Python/numpy/pandas/scikit-learn, không phụ thuộc Flask.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_curve
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.naive_bayes import GaussianNB
from sklearn.neighbors import KNeighborsClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import LabelEncoder, StandardScaler

from .config import ClassNoiseConfig

KNN_NEIGHBORS = 15  # k lớn hơn bản Mutual k-NN (5) để xác suất mịn hơn (bước 1/15)


def make_classifiers(random_state: int) -> dict:
    """5 họ, không dùng class_weight. Thứ tự cố định (ảnh hưởng ma trận đa dạng và cách phá hoà phiếu)."""
    return {
        "LogisticRegression": LogisticRegression(max_iter=1000, random_state=random_state),
        "GaussianNB": GaussianNB(),
        "KNeighbors": KNeighborsClassifier(n_neighbors=KNN_NEIGHBORS),
        "MLP": MLPClassifier(hidden_layer_sizes=(64,), early_stopping=True, max_iter=200, random_state=random_state),
        "HistGradientBoosting": HistGradientBoostingClassifier(random_state=random_state),
    }


@dataclass
class EnsembleDiverseFinding:
    row_number: int
    recorded_label: str
    suggested_label: str
    votes: int  # số mô hình (trên 5) dự đoán khác nhãn ghi
    suspicion: float  # trung bình (1 - P(nhãn ghi)) trên 5 mô hình


@dataclass
class EnsembleDiverseScores:
    """Điểm cho MỌI dòng dùng được.

    suspicion: bỏ phiếu mềm (liên tục, dùng để xếp hạng). votes: số phiếu cứng 0..5 (dùng để gắn cờ theo
    min_votes). suggested_labels: nhãn được nhiều mô hình chọn nhất TRONG SỐ các nhãn khác nhãn ghi ("" nếu
    cả 5 mô hình đều đồng ý với nhãn ghi).
    """

    row_numbers: np.ndarray
    suspicion: np.ndarray
    votes: np.ndarray
    suggested_labels: np.ndarray


@dataclass
class EnsembleDiverseDiagnostics:
    n_rows_total: int
    n_rows_used: int
    classifier_names: list[str]
    class_names: list[str]
    class_counts: dict[str, int]
    majority_baseline_accuracy: float
    per_classifier_accuracy: dict[str, float]  # argmax thuần so với nhãn ghi
    per_classifier_excess: dict[str, float]  # (acc - baseline) / (1 - baseline)
    best_excess_over_baseline: float
    thresholds: dict  # ngưỡng EER của từng mô hình (2 lớp) hoặc None (nhiều lớp / không cân)
    pairwise_agreement: pd.DataFrame  # tỉ lệ dòng 2 mô hình dự đoán GIỐNG nhau (sau cân ngưỡng)
    mean_pairwise_agreement: float
    vote_distribution: dict  # {số phiếu khác nhãn ghi: số dòng}
    min_votes: int
    balance_thresholds: bool
    params: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class EnsembleDiverseResult:
    findings: list[EnsembleDiverseFinding]
    diagnostics: EnsembleDiverseDiagnostics
    scores: EnsembleDiverseScores


def _prepare_usable_subset(df: pd.DataFrame, config: ClassNoiseConfig) -> pd.DataFrame:
    """Lọc dòng dùng được -- lặp lại logic của các module detect khác (giữ module độc lập nhau)."""
    working = df.copy()
    for col in config.feature_columns:
        working[col] = pd.to_numeric(working[col], errors="coerce")
    label_ok = working[config.label_column].astype(str).str.strip() != ""
    features_ok = working[config.feature_columns].notna().all(axis=1)
    return working[label_ok & features_ok]


def balanced_predictions(proba: np.ndarray, y: np.ndarray, class_counts: np.ndarray, balance: bool):
    """Dự đoán nhãn từ xác suất, có (hoặc không) cân bằng 2 loại lỗi. Trả (nhãn dự đoán, ngưỡng hoặc None).

    balance=False: argmax thuần.
    balance=True, 2 lớp: lớp hiếm (theo nhãn ghi) là "dương"; chọn ngưỡng t sao cho tỉ lệ dương giả
        (FPR) và tỉ lệ âm giả (FNR) gần nhau nhất trên xác suất out-of-fold; dự đoán dương nếu p >= t.
    balance=True, nhiều lớp: argmax p(c) / tần suất(c) (luật cân bằng lớp).
    """
    n_classes = proba.shape[1]
    if not balance:
        return proba.argmax(axis=1), None
    if n_classes == 2:
        pos = int(np.argmin(class_counts))
        fpr, tpr, thr = roc_curve(y == pos, proba[:, pos], drop_intermediate=False)
        t = float(thr[int(np.argmin(np.abs(fpr - (1.0 - tpr))))])
        return np.where(proba[:, pos] >= t, pos, 1 - pos), t
    prior = class_counts / class_counts.sum()
    return (proba / prior).argmax(axis=1), None


def detect_class_noise_ensemble_diverse(
    df: pd.DataFrame,
    config: ClassNoiseConfig,
    cv_folds: int = 5,
    random_state: int = 42,
    min_votes: int = 3,
    balance_thresholds: bool = True,
) -> EnsembleDiverseResult:
    """Chạy Ensemble 5 họ (xem docstring module). min_votes trong [1, 5]."""
    classifiers = make_classifiers(random_state)
    names = list(classifiers)
    n_clf = len(names)
    if not 1 <= min_votes <= n_clf:
        raise ValueError(f"min_votes phải nằm trong [1, {n_clf}].")

    usable = _prepare_usable_subset(df, config)
    n = len(usable)
    X = StandardScaler().fit_transform(usable[config.feature_columns].to_numpy())  # cần cho LogReg/KNN/MLP
    encoder = LabelEncoder()
    y = encoder.fit_transform(usable[config.label_column].astype(str).to_numpy())
    class_names = list(encoder.classes_)
    n_classes = len(class_names)
    if n_classes < 2:
        raise ValueError("Cột nhãn chỉ có 1 lớp -- không có gì để so sánh nhãn.")
    row_numbers = usable.index.to_numpy() + 1
    class_counts = np.bincount(y, minlength=n_classes).astype(float)
    majority_baseline = float(class_counts.max() / n)

    skf = StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=random_state)
    # n_jobs=1: HistGradientBoosting và KNeighbors tự song song bên trong, tránh chạy chồng 2 tầng.
    probas = {nm: cross_val_predict(clf, X, y, cv=skf, method="predict_proba", n_jobs=1) for nm, clf in classifiers.items()}

    preds, thresholds, plain_acc = {}, {}, {}
    for nm, p in probas.items():
        preds[nm], thresholds[nm] = balanced_predictions(p, y, class_counts, balance_thresholds)
        plain_acc[nm] = float((p.argmax(axis=1) == y).mean())
    excess = {nm: ((a - majority_baseline) / (1.0 - majority_baseline) if majority_baseline < 1.0 else 0.0)
              for nm, a in plain_acc.items()}

    pred_matrix = np.column_stack([preds[nm] for nm in names])  # (n, 5)
    votes = (pred_matrix != y[:, None]).sum(axis=1)
    p_rec = np.column_stack([probas[nm][np.arange(n), y] for nm in names])  # (n, 5) P(nhãn ghi)
    suspicion = (1.0 - p_rec).mean(axis=1)

    # Nhãn gợi ý: nhãn khác nhãn ghi được nhiều mô hình chọn nhất (hoà -> chỉ số nhỏ nhất, lặp lại được).
    counts = np.zeros((n, n_classes), dtype=int)
    for m in range(n_clf):
        np.add.at(counts, (np.arange(n), pred_matrix[:, m]), 1)
    counts[np.arange(n), y] = 0
    names_arr = np.array(class_names, dtype=object)
    suggested = np.where(counts.max(axis=1) > 0, names_arr[counts.argmax(axis=1)], "")

    agreement = np.array([[float((pred_matrix[:, i] == pred_matrix[:, j]).mean()) for j in range(n_clf)] for i in range(n_clf)])
    off_diag = agreement[~np.eye(n_clf, dtype=bool)]

    flagged_idx = np.where(votes >= min_votes)[0]
    findings = [EnsembleDiverseFinding(int(row_numbers[i]), class_names[y[i]], str(suggested[i]), int(votes[i]), float(suspicion[i]))
                for i in flagged_idx]
    findings.sort(key=lambda f: (f.votes, f.suspicion), reverse=True)

    warnings = []
    if max(excess.values()) <= 0:
        warnings.append("Không mô hình nào vượt cách đoán bừa lớp đông nhất: kết quả không đáng tin.")
    if float(off_diag.mean()) > 0.95:
        warnings.append("5 mô hình dự đoán gần như giống hệt nhau: bỏ phiếu không thêm thông tin.")

    diagnostics = EnsembleDiverseDiagnostics(
        n_rows_total=len(df), n_rows_used=n, classifier_names=names, class_names=class_names,
        class_counts={class_names[c]: int(class_counts[c]) for c in range(n_classes)},
        majority_baseline_accuracy=majority_baseline,
        per_classifier_accuracy=plain_acc, per_classifier_excess=excess,
        best_excess_over_baseline=float(max(excess.values())),
        thresholds=thresholds,
        pairwise_agreement=pd.DataFrame(agreement, index=names, columns=names),
        mean_pairwise_agreement=float(off_diag.mean()),
        vote_distribution={int(v): int((votes == v).sum()) for v in range(n_clf + 1)},
        min_votes=min_votes, balance_thresholds=balance_thresholds,
        params={"cv_folds": cv_folds, "random_state": random_state, "knn_neighbors": KNN_NEIGHBORS},
        warnings=warnings,
    )
    scores = EnsembleDiverseScores(row_numbers=row_numbers, suspicion=suspicion, votes=votes, suggested_labels=suggested)
    return EnsembleDiverseResult(findings=findings, diagnostics=diagnostics, scores=scores)
