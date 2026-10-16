"""
Phát hiện CLASS NOISE bằng kỹ thuật ENSEMBLE-BASED: nhiều classifier THUỘC
HỌ THUẬT TOÁN KHÁC NHAU cùng biểu quyết.

Dựa theo paper N29 trong Bảng 6 Gupta & Gupta (2019) -- Khoshgoftaar, Taghi
M., Shi Zhong, và Vedang Joshi. (2005) "Enhancing software quality
estimation using ensemble-classifier based noise filtering." Intelligent
Data Analysis, 9(1): 3-27 -- nhóm "Ensemble based", 9/9 điểm chất lượng.

Ý tưởng cốt lõi (khác HẲN confident_learning.py lẫn distance_based.py):
train NHIỀU classifier KHÁC LOẠI (không phải nhiều lần cùng 1 loại như Random
Forest), mỗi classifier tự dự đoán nhãn qua cross-validation (out-of-fold,
cùng cơ chế StratifiedKFold+cross_val_predict như confident_learning.py --
đảm bảo mỗi dòng luôn được đoán bởi model KHÔNG train trên chính nó). Dòng
nào bị ĐA SỐ classifier dự đoán KHÁC với nhãn ghi thì gắn cờ nghi ngờ.

3 classifier được chọn, CỐ TÌNH KHÔNG trùng họ thuật toán với 2 phương pháp
đã có trong hệ thống (Random Forest ở confident_learning.py -- họ cây/tree-
based; Mutual k-NN ở distance_based.py -- họ láng giềng/instance-based) --
nếu trùng họ, 2/3 phương pháp sẽ đưa ra phán đoán tương quan nhau, làm yếu đi
mục đích so sánh 3 góc nhìn ĐỘC LẬP:
  - LogisticRegression: họ TUYẾN TÍNH, tối ưu theo khả năng hợp lý
    (likelihood) -- nhìn TOÀN BỘ điểm dữ liệu.
  - GaussianNB: họ XÁC SUẤT, giả định mỗi cột độc lập + phân phối chuẩn
    trong từng lớp.
  - LinearSVC: họ BIÊN CỰC ĐẠI (margin-based) -- chỉ quan tâm các điểm SÁT
    BIÊN giữa 2 lớp, bỏ qua phần lớn điểm ở xa.
LogisticRegression và LinearSVC tuy cùng vẽ ra đường phân chia THẲNG (hình
dạng giống nhau), nhưng TÌM ra đường đó theo 2 cách rất khác nhau (nhìn toàn
bộ điểm vs chỉ nhìn điểm sát biên) nên vẫn coi là đủ đa dạng, khác hẳn mức
trùng nghiêm trọng nếu dùng Decision Tree (trùng họ Random Forest) hay KNN
(trùng họ Mutual k-NN).

Xử lý mất cân bằng lớp (vì không phải classifier nào cũng hỗ trợ
class_weight như nhau): LogisticRegression/LinearSVC dùng
class_weight="balanced" (có hỗ trợ sẵn); GaussianNB không có tham số này nên
ép priors đều nhau giữa các lớp (1/số_lớp mỗi lớp, KHÔNG dùng đúng tỉ lệ thật
trong dữ liệu) để giảm thiên vị lớp đa số.
"""

from collections import Counter
from dataclasses import dataclass

import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.naive_bayes import GaussianNB
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.svm import LinearSVC

from .config import ClassNoiseConfig


@dataclass
class EnsembleNoiseFinding:
    """Kết quả cho ĐÚNG 1 dòng bị nghi ngờ sai nhãn.

    disagree_ratio: tỉ lệ classifier (trong 3 cái) dự đoán KHÁC nhãn ghi
    (vd 2/3 = 0.667, 3/3 = 1.0) -- dùng để sắp xếp mức độ đáng ngờ, đóng vai
    trò tương đương "margin" (confident_learning.py) / "disagreement_ratio"
    (distance_based.py).
    """

    row_number: int
    recorded_label: str
    suggested_label: str
    disagree_ratio: float


@dataclass
class EnsembleNoiseDiagnostics:
    """Chỉ số chẩn đoán -- vai trò tương đương ClassNoiseDiagnostics, nhưng
    thay vì 1 cv_accuracy duy nhất (1 model), có RIÊNG accuracy cho TỪNG
    classifier (per_classifier_accuracy) -- PHẢI xem trước khi tin findings:
    nếu CẢ 3 classifier đều có accuracy sát majority_baseline_accuracy thì
    không classifier nào học được gì từ feature_columns, findings không
    đáng tin (giống hệt lý do đã áp dụng cho cv_accuracy ở Confident
    Learning).
    """

    n_rows_total: int
    n_rows_used: int
    classifier_names: list[str]
    per_classifier_accuracy: dict[str, float]
    majority_baseline_accuracy: float
    class_names: list[str]
    class_counts: dict[str, int]


@dataclass
class EnsembleNoiseResult:
    findings: list[EnsembleNoiseFinding]
    diagnostics: EnsembleNoiseDiagnostics


def _prepare_usable_subset(df: pd.DataFrame, config: ClassNoiseConfig) -> pd.DataFrame:
    """Lọc dòng dùng được -- lặp lại y hệt logic của confident_learning.py/
    distance_based.py (không import dùng chung, giữ 3 module độc lập nhau)."""
    working = df.copy()
    for col in config.feature_columns:
        working[col] = pd.to_numeric(working[col], errors="coerce")

    label_ok = working[config.label_column].astype(str).str.strip() != ""
    features_ok = working[config.feature_columns].notna().all(axis=1)
    return working[label_ok & features_ok]


def detect_class_noise_ensemble(
    df: pd.DataFrame, config: ClassNoiseConfig, cv_folds: int = 5, random_state: int = 42
) -> EnsembleNoiseResult:
    """Hàm chính: chạy đủ 4 bước Ensemble Filter (N29) trên df theo config."""
    usable = _prepare_usable_subset(df, config)
    n_rows_used = len(usable)

    X_raw = usable[config.feature_columns].to_numpy()
    X = StandardScaler().fit_transform(X_raw)  # chuẩn hoá z-score -- bắt buộc
    # cho LogisticRegression/LinearSVC (nhạy đơn vị đo), không hại gì GaussianNB.
    label_encoder = LabelEncoder()
    y = label_encoder.fit_transform(usable[config.label_column].astype(str).to_numpy())
    class_names = list(label_encoder.classes_)
    n_classes = len(class_names)
    row_numbers = usable.index.to_numpy() + 1  # quy ước 1-based

    skf = StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=random_state)

    classifiers = {
        "LogisticRegression": LogisticRegression(
            class_weight="balanced", max_iter=1000, random_state=random_state
        ),
        "GaussianNB": GaussianNB(priors=[1 / n_classes] * n_classes),
        "LinearSVC": LinearSVC(class_weight="balanced", max_iter=5000, random_state=random_state),
    }

    # n_jobs=-1 ở cross_val_predict an toàn ở đây (khác confident_learning.py
    # phải dùng n_jobs=1) vì cả 3 classifier này đều CHẠY ĐƠN LUỒNG, không tự
    # song song hoá bên trong như RandomForestClassifier -- không có rủi ro
    # "quá tải" (oversubscribe) khi chạy song song cả 2 tầng.
    predictions: dict[str, "pd.Series"] = {}
    per_classifier_accuracy: dict[str, float] = {}
    for name, clf in classifiers.items():
        preds = cross_val_predict(clf, X, y, cv=skf, n_jobs=-1)
        predictions[name] = preds
        per_classifier_accuracy[name] = float((preds == y).mean())

    class_counts_raw = pd.Series(y).value_counts()
    majority_baseline_accuracy = float(class_counts_raw.max() / len(y))

    clf_names = list(classifiers.keys())
    n_clf = len(clf_names)
    findings: list[EnsembleNoiseFinding] = []
    for i in range(n_rows_used):
        votes = [predictions[name][i] for name in clf_names]
        disagree_count = sum(1 for v in votes if v != y[i])
        disagree_ratio = disagree_count / n_clf
        if disagree_ratio > 0.5:  # quá bán -- đa số classifier không đồng ý với nhãn ghi
            majority_vote, _count = Counter(votes).most_common(1)[0]
            findings.append(
                EnsembleNoiseFinding(
                    row_number=int(row_numbers[i]),
                    recorded_label=class_names[y[i]],
                    suggested_label=class_names[majority_vote],
                    disagree_ratio=float(disagree_ratio),
                )
            )

    findings.sort(key=lambda f: f.disagree_ratio, reverse=True)

    diagnostics = EnsembleNoiseDiagnostics(
        n_rows_total=len(df),
        n_rows_used=n_rows_used,
        classifier_names=clf_names,
        per_classifier_accuracy=per_classifier_accuracy,
        majority_baseline_accuracy=majority_baseline_accuracy,
        class_names=class_names,
        class_counts={class_names[c]: int(cnt) for c, cnt in class_counts_raw.items()},
    )

    return EnsembleNoiseResult(findings=findings, diagnostics=diagnostics)
