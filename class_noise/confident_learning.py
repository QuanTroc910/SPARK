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
          các dòng THẬT SỰ thuộc lớp đó.
  Bước 3: Với mỗi dòng, lọc ra các lớp vượt ngưỡng riêng của chính chúng
          (candidates), chọn lớp có xác suất cao nhất làm "confident_class".
  Bước 4: So confident_class với nhãn ghi trong file -- lệch thì gắn cờ nghi
          ngờ sai nhãn, kèm "margin" để xếp hạng mức độ đáng ngờ.

Module này KHÔNG phụ thuộc Flask/web -- thuần Python + pandas + scikit-learn,
giống đúng tinh thần attribute_noise/ (logic tách biệt khỏi backend).
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report
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
class ClassNoiseDiagnostics:
    """Các chỉ số CHẨN ĐOÁN độ tin cậy của kết quả phát hiện -- PHẢI xem
    trước khi tin bất kỳ finding nào, vì nếu model gần như không học được gì
    (cv_accuracy sát baseline) thì các dòng bị gắn cờ đa phần là do model dở,
    không phải noise thật (bài học rút ra từ 1 demo thất bại có chủ đích
    trước khi module này được viết -- xem lịch sử trò chuyện/README nội bộ).
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


@dataclass
class ClassNoiseResult:
    findings: list[ClassNoiseFinding]
    diagnostics: ClassNoiseDiagnostics


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

    class_weight="balanced": mỗi lớp được cho "trọng số" tỉ lệ nghịch với số
    lượng dòng của lớp đó khi cây tính độ thuần (Gini) lúc chọn ngưỡng tách
    -- bù lại cho lớp hiếm, tránh model chỉ học cách đoán lớp đa số cho nhàn.
    """
    rf = RandomForestClassifier(
        n_estimators=config.n_estimators,
        class_weight="balanced",
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
    dòng mà nhãn GHI trong file thật sự thuộc lớp đó.
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
    """
    n_rows, n_classes = pred_probs.shape
    confident_class = np.full(n_rows, -1)
    above_threshold = pred_probs >= thresholds  # broadcast theo từng cột lớp
    for i in range(n_rows):
        candidates = np.where(above_threshold[i])[0]
        if len(candidates) == 0:
            continue
        confident_class[i] = candidates[np.argmax(pred_probs[i, candidates])]
    return confident_class


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

    pred_probs = get_out_of_fold_probs(X, y, config)

    # --- Chỉ số hiệu năng THÔ của model (argmax, chưa qua bước lọc ngưỡng) ---
    # Đây là con số PHẢI xem trước tiên: nếu cv_accuracy chỉ nhỉnh hơn chút
    # so với majority_baseline_accuracy thì model gần như không học được gì
    # từ feature_columns -- mọi finding bên dưới nên bị nghi ngờ, không phải
    # noise thật.
    argmax_labels = pred_probs.argmax(axis=1)
    cv_accuracy = float((argmax_labels == y).mean())
    class_counts_raw = pd.Series(y).value_counts()
    majority_baseline_accuracy = float(class_counts_raw.max() / len(y))
    per_class_report = classification_report(
        y, argmax_labels, target_names=class_names, output_dict=True, zero_division=0
    )

    # --- Các bước 2-4 của Confident Learning ---
    thresholds = _compute_class_thresholds(pred_probs, y, n_classes)
    confident_class = _find_confident_classes(pred_probs, thresholds)

    count_matrix = np.zeros((n_classes, n_classes), dtype=int)
    findings: list[ClassNoiseFinding] = []
    row_numbers = usable.index.to_numpy() + 1  # quy ước 1-based, xem docstring ClassNoiseFinding

    for i in range(len(y)):
        if confident_class[i] == -1:
            continue
        count_matrix[y[i], confident_class[i]] += 1
        if confident_class[i] == y[i]:
            continue  # khớp nhãn ghi -- không phải finding
        margin = float(pred_probs[i, confident_class[i]] - pred_probs[i, y[i]])
        findings.append(
            ClassNoiseFinding(
                row_number=int(row_numbers[i]),
                recorded_label=class_names[y[i]],
                confident_label=class_names[confident_class[i]],
                margin=margin,
            )
        )

    findings.sort(key=lambda f: f.margin, reverse=True)

    diagnostics = ClassNoiseDiagnostics(
        n_rows_total=len(df),
        n_rows_used=len(usable),
        class_names=class_names,
        class_counts={class_names[c]: int(cnt) for c, cnt in class_counts_raw.items()},
        cv_accuracy=cv_accuracy,
        majority_baseline_accuracy=majority_baseline_accuracy,
        class_thresholds={class_names[c]: float(thresholds[c]) for c in range(n_classes)},
        per_class_report=per_class_report,
        confusion_count_matrix=pd.DataFrame(count_matrix, index=class_names, columns=class_names),
    )

    return ClassNoiseResult(findings=findings, diagnostics=diagnostics)
