"""
Core logic phát hiện CLASS NOISE bằng thuật toán Confident Learning
(Northcutt, Jiang, Chuang -- "Confident Learning: Estimating Uncertainty in
Dataset Labels", JAIR 2021), dùng Random Forest làm "core" model để lấy xác
suất dự đoán.

4 bước của thuật toán (đã giải thích chi tiết ngoài code, tóm tắt lại ở đây
để đọc code không bị lạc):
  Bước 1: Train Random Forest qua Stratified K-Fold CV -> lấy pred_probs
          "trung thực" (out-of-fold) cho MỌI dòng.
  Bước 2: Với mỗi lớp, tính ngưỡng tự tin riêng = trung bình P(lớp đó) trên
          các dòng MANG NHÃN GHI là lớp đó (nhãn ghi có thể sai, nên đây chưa
          chắc là các dòng "thật sự" thuộc lớp đó).
  Bước 3: Với mỗi dòng, lọc ra các lớp vượt ngưỡng riêng của chính chúng
          (candidates), chọn lớp có xác suất cao nhất làm "confident_class".
  Bước 4: So confident_class với nhãn ghi trong file -- lệch thì gắn cờ nghi
          ngờ sai nhãn, kèm "margin" để xếp hạng mức độ đáng ngờ.

CẢI TIẾN (kế hoạch mục 3, 22/11/2026) -- mặc định VẪN cho ra đúng danh sách
dòng bị gắn cờ như trước nếu đặt min_samples_leaf=1:
  - Random Forest có min_samples_leaf (mặc định 5) và bật/tắt class_weight
    "balanced" (xem ClassNoiseConfig).
  - Trả thêm chỉ số chẩn đoán: "mức vượt mốc", MCC, PR-AUC (xem
    ClassNoiseDiagnostics).
  - Trả điểm nghi ngờ cho MỌI dòng (result.scores), không chỉ dòng bị gắn cờ --
    để phương pháp kết hợp (kế hoạch mục 4) xếp hạng được trên cùng 1 thang.
  - Ước lượng TỶ LỆ NHÃN SAI của cả bảng bằng cách hiệu chỉnh ma trận đếm
    (calibrated confident joint, đúng theo bài gốc Northcutt 2021, mục 3).
  - Hai vòng lặp từng dòng đổi sang numpy (kết quả giống hệt, nhanh hơn trên
    bảng lớn).

Module này KHÔNG phụ thuộc Flask/web -- thuần Python + pandas + scikit-learn,
giống đúng tinh thần attribute_noise/ (logic tách biệt khỏi backend).
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    average_precision_score,
    classification_report,
    matthews_corrcoef,
)
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.preprocessing import LabelEncoder

from .config import ClassNoiseConfig


@dataclass
class ClassNoiseFinding:
    """Kết quả phát hiện cho ĐÚNG 1 dòng bị nghi ngờ sai nhãn.

    row_number dùng quy ước 1-based (index gốc trong file + 1) -- khớp đúng
    quy ước row_number của attribute_noise (xem CLAUDE.md mục 5), để sau này
    backend/frontend có thể tái dùng chung cách tham chiếu dòng.
    """

    row_number: int
    recorded_label: str
    confident_label: str
    margin: float


@dataclass
class ClassNoiseScores:
    """Điểm nghi ngờ cho MỌI dòng dùng được (không chỉ các dòng bị gắn cờ).

    Các mảng cùng độ dài và cùng thứ tự dòng với bảng đầu vào (sau khi loại dòng
    hỏng). Dùng để so Confident Learning với các phương pháp khác trên cùng 1
    thang, và để đổi ngưỡng gắn cờ mà không phải train lại model.

    suspicion: 1 - P(nhãn ghi), với P là xác suất out-of-fold. Càng gần 1 càng
        đáng ngờ. Khác `margin` trong finding (chỉ có ở dòng bị gắn cờ).
    suggested_labels: nhãn KHÁC nhãn ghi mà model cho xác suất cao nhất (luôn có
        giá trị, kể cả khi dòng không bị gắn cờ).
    confident_labels: lớp mà Confident Learning "tự tin" dòng này thuộc về (đã
        qua ngưỡng riêng từng lớp); chuỗi rỗng nếu không lớp nào vượt ngưỡng.
        Dòng bị gắn cờ <=> confident_labels khác rỗng và khác nhãn ghi.
    """

    row_numbers: np.ndarray
    suspicion: np.ndarray
    suggested_labels: np.ndarray
    confident_labels: np.ndarray


@dataclass
class ClassNoiseDiagnostics:
    """Các chỉ số CHẨN ĐOÁN độ tin cậy của kết quả phát hiện -- PHẢI xem
    trước khi tin bất kỳ finding nào, vì nếu model gần như không học được gì
    (cv_accuracy sát baseline) thì các dòng bị gắn cờ đa phần là do model dở,
    không phải noise thật (bài học rút ra từ 1 demo thất bại có chủ đích
    trước khi module này được viết -- xem lịch sử trò chuyện/README nội bộ).

    Lưu ý chung cho các chỉ số accuracy / MCC / PR-AUC bên dưới: chúng đo model
    đoán GIỎI TỚI ĐÂU SO VỚI NHÃN GHI, chứ không phải so với nhãn thật (không có
    nhãn thật). Nhãn ghi bị sai thì các chỉ số này bị kéo xuống theo.
    """

    n_rows_total: int
    n_rows_used: int
    class_names: list[str]
    class_counts: dict[str, int]
    cv_accuracy: float
    majority_baseline_accuracy: float
    class_thresholds: dict[str, float]
    per_class_report: dict
    confusion_count_matrix: pd.DataFrame

    # --- Thêm ở kế hoạch mục 3 (đều có giá trị mặc định để code cũ không vỡ) ---
    # "Mức vượt mốc" = (accuracy - baseline) / (1 - baseline): model hơn cách
    # "đoán bừa lớp đông nhất" được bao nhiêu phần của khoảng cách tối đa có thể
    # hơn. 0 = không hơn gì, 1 = đoán đúng hết. Âm = còn kém cả đoán bừa.
    excess_over_baseline: float = 0.0
    mcc: float = 0.0  # Matthews correlation, -1..1, bền với lớp mất cân bằng
    # PR-AUC (average precision) theo từng lớp, và trung bình các lớp.
    pr_auc_per_class: dict = field(default_factory=dict)
    pr_auc_macro: float = 0.0
    # Ước lượng tỷ lệ nhãn sai cả bảng (hiệu chỉnh ma trận đếm, Northcutt 2021).
    estimated_noise_rate: float = 0.0
    estimated_label_errors: int = 0
    # Q̂: xác suất đồng thời (nhãn ghi i, nhãn thật j); hàng = nhãn ghi, cột = nhãn thật.
    calibrated_joint: pd.DataFrame | None = None
    # Tham số Random Forest thực sự đã dùng (để biết kết quả ứng với cấu hình nào).
    params: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ClassNoiseResult:
    findings: list[ClassNoiseFinding]
    diagnostics: ClassNoiseDiagnostics
    scores: ClassNoiseScores | None = None


def _prepare_usable_subset(
    df: pd.DataFrame, config: ClassNoiseConfig
) -> pd.DataFrame:
    """Lọc ra các dòng DÙNG ĐƯỢC cho bài toán class noise: nhãn không rỗng và
    mọi cột đặc trưng ép được thành số.

    Cố tình KHÔNG reset_index() -- giữ nguyên index gốc của df đầu vào, để
    row_number (= index + 1) trong ClassNoiseFinding luôn khớp đúng vị trí
    dòng trong file gốc, kể cả sau khi đã loại bớt dòng dính lỗi khác.
    """
    working = df.copy()

    for col in config.feature_columns:
        working[col] = pd.to_numeric(working[col], errors="coerce")

    label_ok = working[config.label_column].astype(str).str.strip() != ""
    features_ok = working[config.feature_columns].notna().all(axis=1)

    return working[label_ok & features_ok]


def get_out_of_fold_probs(
    X: np.ndarray, y: np.ndarray, config: ClassNoiseConfig
) -> np.ndarray:
    """Bước 1: train Random Forest qua Stratified K-Fold CV, trả về xác suất
    dự đoán "trung thực" (out-of-fold) cho MỌI dòng trong X/y.

    "Out-of-fold" nghĩa là: chia dữ liệu thành cv_folds phần, mỗi dòng luôn
    được ĐOÁN bởi 1 model KHÔNG train trên chính nó (model train trên các
    fold còn lại). Nhờ vậy pred_probs phản ánh đúng khả năng thật của model
    trên dữ liệu "chưa từng thấy", không bị lạc quan giả tạo do model học
    thuộc lòng chính dòng nó đang đoán.

    class_weight="balanced" (khi config.balanced=True): mỗi lớp được cho
    "trọng số" tỉ lệ nghịch với số lượng dòng của lớp đó khi cây tính độ thuần
    (Gini) lúc chọn ngưỡng tách -- bù lại cho lớp hiếm, tránh model chỉ học
    cách đoán lớp đa số cho nhàn. Tắt (balanced=False) thì xác suất phản ánh
    đúng tỉ lệ lớp trong dữ liệu hơn nhưng lớp hiếm dễ bị bỏ qua.

    min_samples_leaf: mỗi lá phải có ít nhất chừng đó dòng; ép cây không mọc
    tới từng dòng lẻ nên không học thuộc nhãn sai (xem ClassNoiseConfig).
    """
    rf = RandomForestClassifier(
        n_estimators=config.n_estimators,
        min_samples_leaf=config.min_samples_leaf,
        class_weight="balanced" if config.balanced else None,
        random_state=config.random_state,
        n_jobs=-1,
    )
    skf = StratifiedKFold(
        n_splits=config.cv_folds, shuffle=True, random_state=config.random_state
    )
    # n_jobs=1 ở cross_val_predict (chạy tuần tự từng fold) vì bản thân
    # RandomForestClassifier đã tự chạy song song (n_jobs=-1) rồi -- chạy
    # song song luôn cả 2 tầng dễ khiến máy bị "quá tải" (oversubscribe CPU).
    return cross_val_predict(rf, X, y, cv=skf, method="predict_proba", n_jobs=1)


def _compute_class_thresholds(
    pred_probs: np.ndarray, y: np.ndarray, n_classes: int
) -> np.ndarray:
    """Bước 2: ngưỡng tự tin riêng từng lớp = trung bình P(lớp đó) trên các
    dòng MANG NHÃN GHI là lớp đó.

    (Nhãn ghi có thể sai nên đây chưa chắc là các dòng "thật sự" thuộc lớp đó --
    đó chính là lý do thuật toán cần ước lượng ngưỡng theo cách này thay vì
    dùng 1 ngưỡng cố định như 0,5.)
    """
    thresholds = np.zeros(n_classes)
    for c in range(n_classes):
        mask = y == c
        thresholds[c] = pred_probs[mask, c].mean()
    return thresholds


def _find_confident_classes(
    pred_probs: np.ndarray, thresholds: np.ndarray
) -> np.ndarray:
    """Bước 3: với mỗi dòng, lọc các lớp vượt ngưỡng riêng của chính chúng
    (candidates), chọn lớp xác suất cao nhất. Trả về -1 nếu không lớp nào
    vượt ngưỡng (không đủ căn cứ để kết luận gì cho dòng đó).

    Viết bằng numpy cả bảng (không lặp từng dòng). Kết quả giống hệt bản lặp
    cũ, kể cả khi hoà xác suất: cả hai đều chọn lớp có chỉ số nhỏ nhất.
    """
    above_threshold = pred_probs >= thresholds  # broadcast theo từng cột lớp
    # Lớp không vượt ngưỡng bị "loại" bằng -inf để argmax không bao giờ chọn.
    masked = np.where(above_threshold, pred_probs, -np.inf)
    best = masked.argmax(axis=1)
    return np.where(above_threshold.any(axis=1), best, -1)


def _calibrated_joint(
    count_matrix: np.ndarray, recorded_counts: np.ndarray, class_names: list[str]
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Hiệu chỉnh ma trận đếm (confident joint) -- Northcutt 2021, mục 3.

    count_matrix[i][j] = số dòng có nhãn ghi i mà Confident Learning tự tin là
    lớp j. Ma trận này CHƯA dùng được để ước lượng tỷ lệ nhãn sai ngay vì 2 lý do:
    (a) dòng không lớp nào vượt ngưỡng bị bỏ ra ngoài nên tổng hàng i nhỏ hơn
        số dòng thật mang nhãn ghi i;
    (b) lớp hiếm bị đếm thiếu nhiều hơn lớp đông.
    Hiệu chỉnh: kéo MỖI HÀNG về đúng số dòng mang nhãn ghi đó (recorded_counts),
    rồi chia cho tổng để ra xác suất đồng thời Q̂ (tổng = 1):
        Ĉ[i][j] = C[i][j] / sum_j C[i][j] * recorded_counts[i]
        Q̂[i][j] = Ĉ[i][j] / sum_ij Ĉ[i][j]
    Tỷ lệ nhãn sai ước lượng = 1 - trace(Q̂) (phần xác suất nằm ngoài đường chéo).

    Trả về (Ĉ, Q̂, cảnh báo). Lớp nào không có dòng nào vượt ngưỡng (tổng hàng = 0)
    thì KHÔNG có căn cứ nào để ước lượng: tạm coi lớp đó không nhiễu (dồn hết vào
    đường chéo) và ghi cảnh báo -- đây là giả định, không phải kết luận.
    """
    n_classes = count_matrix.shape[0]
    c_hat = np.zeros((n_classes, n_classes), dtype=float)
    notes: list[str] = []
    row_sums = count_matrix.sum(axis=1)
    for i in range(n_classes):
        if row_sums[i] > 0:
            c_hat[i] = count_matrix[i] / row_sums[i] * recorded_counts[i]
        else:
            c_hat[i, i] = recorded_counts[i]
            notes.append(
                f"Lớp «{class_names[i]}»: không dòng nào vượt ngưỡng tự tin nên không ước "
                "lượng được nhiễu của lớp này, tạm coi là không nhiễu."
            )
    total = c_hat.sum()
    q_hat = c_hat / total if total > 0 else c_hat
    return c_hat, q_hat, notes


def detect_class_noise(df: pd.DataFrame, config: ClassNoiseConfig) -> ClassNoiseResult:
    """Hàm chính: chạy đủ 4 bước Confident Learning trên df theo config, trả
    về cả danh sách dòng bị nghi ngờ (findings) LẪN các chỉ số chẩn đoán độ
    tin cậy (diagnostics) -- bắt buộc phải nhìn diagnostics trước khi tin
    findings (xem docstring ClassNoiseDiagnostics).
    """
    usable = _prepare_usable_subset(df, config)

    X = usable[config.feature_columns].to_numpy()
    label_encoder = LabelEncoder()
    y = label_encoder.fit_transform(usable[config.label_column].to_numpy())
    class_names = list(label_encoder.classes_)
    n_classes = len(class_names)
    n_rows = len(y)
    if n_classes < 2:
        raise ValueError(
            "Cột nhãn chỉ có 1 lớp (sau khi bỏ dòng thiếu nhãn/đặc trưng) -- "
            "không có gì để so sánh nhãn."
        )

    pred_probs = get_out_of_fold_probs(X, y, config)

    # --- Chỉ số hiệu năng THÔ của model (argmax, chưa qua bước lọc ngưỡng) ---
    # Đây là con số PHẢI xem trước tiên: nếu cv_accuracy chỉ nhỉnh hơn chút
    # so với majority_baseline_accuracy thì model gần như không học được gì
    # từ feature_columns -- mọi finding bên dưới nên bị nghi ngờ, không phải
    # noise thật.
    argmax_labels = pred_probs.argmax(axis=1)
    cv_accuracy = float((argmax_labels == y).mean())
    class_counts_raw = pd.Series(y).value_counts()
    majority_baseline_accuracy = float(class_counts_raw.max() / n_rows)
    per_class_report = classification_report(
        y, argmax_labels, target_names=class_names, output_dict=True, zero_division=0
    )
    if majority_baseline_accuracy < 1.0:
        excess = (cv_accuracy - majority_baseline_accuracy) / (1.0 - majority_baseline_accuracy)
    else:
        excess = 0.0  # chỉ còn 1 lớp có dòng -> không có "khoảng cách" để vượt
    mcc = float(matthews_corrcoef(y, argmax_labels))
    # PR-AUC từng lớp: coi "dòng mang nhãn ghi là lớp này" là dương tính, xếp hạng
    # theo xác suất out-of-fold của lớp đó. (y[:, None] == arange) = one-hot,
    # dùng cách này vì label_binarize trả 1 cột duy nhất khi chỉ có 2 lớp.
    one_hot = y[:, None] == np.arange(n_classes)
    pr_auc_per_class = {
        class_names[c]: float(average_precision_score(one_hot[:, c], pred_probs[:, c]))
        for c in range(n_classes)
    }

    # --- Các bước 2-4 của Confident Learning ---
    thresholds = _compute_class_thresholds(pred_probs, y, n_classes)
    confident_class = _find_confident_classes(pred_probs, thresholds)

    has_confident = confident_class >= 0
    count_matrix = np.zeros((n_classes, n_classes), dtype=int)
    np.add.at(count_matrix, (y[has_confident], confident_class[has_confident]), 1)

    row_numbers = usable.index.to_numpy() + 1  # quy ước 1-based, xem docstring ClassNoiseFinding
    flagged_idx = np.where(has_confident & (confident_class != y))[0]
    margins = pred_probs[flagged_idx, confident_class[flagged_idx]] - pred_probs[flagged_idx, y[flagged_idx]]
    findings = [
        ClassNoiseFinding(
            row_number=int(row_numbers[i]),
            recorded_label=class_names[y[i]],
            confident_label=class_names[confident_class[i]],
            margin=float(m),
        )
        for i, m in zip(flagged_idx, margins)
    ]
    # sort ổn định: các dòng bằng margin giữ thứ tự dòng, như bản cũ
    findings.sort(key=lambda f: f.margin, reverse=True)

    # --- Điểm cho MỌI dòng ---
    names = np.array(class_names, dtype=object)
    p_recorded = pred_probs[np.arange(n_rows), y]
    others = pred_probs.copy()
    others[np.arange(n_rows), y] = -np.inf  # loại nhãn ghi, chọn nhãn khác có xác suất cao nhất
    suggested_labels = names[others.argmax(axis=1)]
    confident_labels = np.where(has_confident, names[np.where(has_confident, confident_class, 0)], "")
    scores = ClassNoiseScores(
        row_numbers=row_numbers,
        suspicion=1.0 - p_recorded,
        suggested_labels=suggested_labels,
        confident_labels=confident_labels,
    )

    # --- Ước lượng tỷ lệ nhãn sai (hiệu chỉnh ma trận đếm) ---
    recorded_counts = np.bincount(y, minlength=n_classes).astype(float)
    c_hat, q_hat, warnings = _calibrated_joint(count_matrix, recorded_counts, class_names)
    estimated_noise_rate = float(1.0 - np.trace(q_hat))

    diagnostics = ClassNoiseDiagnostics(
        n_rows_total=len(df),
        n_rows_used=n_rows,
        class_names=class_names,
        class_counts={class_names[c]: int(cnt) for c, cnt in class_counts_raw.items()},
        cv_accuracy=cv_accuracy,
        majority_baseline_accuracy=majority_baseline_accuracy,
        class_thresholds={class_names[c]: float(thresholds[c]) for c in range(n_classes)},
        per_class_report=per_class_report,
        confusion_count_matrix=pd.DataFrame(count_matrix, index=class_names, columns=class_names),
        excess_over_baseline=float(excess),
        mcc=mcc,
        pr_auc_per_class=pr_auc_per_class,
        pr_auc_macro=float(np.mean(list(pr_auc_per_class.values()))),
        estimated_noise_rate=estimated_noise_rate,
        estimated_label_errors=int(round(estimated_noise_rate * n_rows)),
        calibrated_joint=pd.DataFrame(q_hat, index=class_names, columns=class_names),
        params={
            "n_estimators": config.n_estimators,
            "min_samples_leaf": config.min_samples_leaf,
            "balanced": config.balanced,
            "cv_folds": config.cv_folds,
            "random_state": config.random_state,
        },
        warnings=warnings,
    )

    return ClassNoiseResult(findings=findings, diagnostics=diagnostics, scores=scores)
