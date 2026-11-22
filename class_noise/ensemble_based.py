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

from dataclasses import dataclass, field

import numpy as np
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
class EnsembleNoiseScores:
    """Điểm cho MỌI dòng dùng được (không chỉ dòng bị gắn cờ) -- để phương pháp kết hợp
    (combined.py) xếp hạng được trên cùng 1 thang với các phương pháp khác.

    disagreement: tỉ lệ classifier (trong 3 cái) dự đoán KHÁC nhãn ghi, chỉ nhận 4 giá
        trị 0, 1/3, 2/3, 1 nên có RẤT NHIỀU dòng bằng điểm nhau -- ai dùng để xếp hạng
        phải xử lý hoà (combined.py dùng hạng trung bình). Đây là hạn chế của việc dùng
        nhãn dự đoán thay vì xác suất; thiết kế 5 họ có xác suất là kế hoạch mục 7.
    suggested_labels: nhãn được nhiều classifier chọn nhất TRONG SỐ các nhãn khác nhãn
        ghi; chuỗi rỗng nếu cả 3 classifier đều đồng ý với nhãn ghi (không có gợi ý).
    """

    row_numbers: np.ndarray
    disagreement: np.ndarray
    suggested_labels: np.ndarray


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
    # Thêm ở kế hoạch mục 4 (có giá trị mặc định để code cũ không vỡ): "mức vượt mốc"
    # = (accuracy - baseline) / (1 - baseline) của TỪNG classifier, và của classifier tốt
    # nhất -- nếu ngay cả classifier tốt nhất cũng <= 0 thì không classifier nào học được
    # gì, phương pháp kết hợp sẽ loại phương pháp này.
    per_classifier_excess: dict[str, float] = field(default_factory=dict)
    best_excess_over_baseline: float = 0.0


@dataclass
class EnsembleNoiseResult:
    findings: list[EnsembleNoiseFinding]
    diagnostics: EnsembleNoiseDiagnostics
    scores: EnsembleNoiseScores | None = None


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
    if majority_baseline_accuracy < 1.0:
        per_classifier_excess = {
            name: (acc - majority_baseline_accuracy) / (1.0 - majority_baseline_accuracy)
            for name, acc in per_classifier_accuracy.items()
        }
    else:  # chỉ còn 1 lớp có dòng -> không có "khoảng cách" để vượt
        per_classifier_excess = {name: 0.0 for name in per_classifier_accuracy}

    clf_names = list(classifiers.keys())
    n_clf = len(clf_names)

    # Tính cả bảng bằng numpy. preds_matrix[i, m] = nhãn classifier m đoán cho dòng i.
    preds_matrix = np.column_stack([predictions[name] for name in clf_names])
    disagree_ratio_all = (preds_matrix != y[:, None]).sum(axis=1) / n_clf

    # Nhãn gợi ý = nhãn được NHIỀU classifier chọn nhất TRONG SỐ các nhãn khác nhãn ghi
    # (hoà phiếu -> nhãn có chỉ số nhỏ nhất, để kết quả lặp lại được). Bản cũ đếm phiếu
    # trên cả phiếu trùng nhãn ghi nên với nhiều lớp có thể ra nhãn gợi ý TRÙNG nhãn ghi
    # (vd phiếu [a, b, nhãn ghi] hoà nhau và lấy phiếu đầu); đã sửa. Tập dòng bị gắn cờ
    # và disagree_ratio KHÔNG đổi.
    vote_counts = np.zeros((n_rows_used, n_classes), dtype=int)
    for m in range(n_clf):
        np.add.at(vote_counts, (np.arange(n_rows_used), preds_matrix[:, m]), 1)
    vote_counts[np.arange(n_rows_used), y] = 0  # bỏ phiếu cho chính nhãn ghi
    best_other = vote_counts.argmax(axis=1)
    has_suggestion = vote_counts.max(axis=1) > 0
    names = np.array(class_names, dtype=object)
    suggested_all = np.where(has_suggestion, names[best_other], "")

    flagged_idx = np.where(disagree_ratio_all > 0.5)[0]  # quá bán -- đa số classifier không đồng ý với nhãn ghi
    findings = [
        EnsembleNoiseFinding(
            row_number=int(row_numbers[i]),
            recorded_label=class_names[y[i]],
            suggested_label=str(suggested_all[i]),
            disagree_ratio=float(disagree_ratio_all[i]),
        )
        for i in flagged_idx
    ]
    findings.sort(key=lambda f: f.disagree_ratio, reverse=True)

    diagnostics = EnsembleNoiseDiagnostics(
        n_rows_total=len(df),
        n_rows_used=n_rows_used,
        classifier_names=clf_names,
        per_classifier_accuracy=per_classifier_accuracy,
        majority_baseline_accuracy=majority_baseline_accuracy,
        class_names=class_names,
        class_counts={class_names[c]: int(cnt) for c, cnt in class_counts_raw.items()},
        per_classifier_excess=per_classifier_excess,
        best_excess_over_baseline=max(per_classifier_excess.values()),
    )
    scores = EnsembleNoiseScores(
        row_numbers=row_numbers,
        disagreement=disagree_ratio_all,
        suggested_labels=suggested_all,
    )

    return EnsembleNoiseResult(findings=findings, diagnostics=diagnostics, scores=scores)
