"""
Đánh giá CẢ 3 thuật toán phát hiện CLASS NOISE (Single learning-based =
Confident Learning + Random Forest, Distance-based = N13/Mutual k-NN,
Ensemble-based = N29) theo khuôn TRAIN/TEST trên dữ liệu THẬT của thầy
(data/class_noise_train.csv 588.393 dòng + data/class_noise_test.csv
147.097 dòng -- 3 đặc trưng V44/V12/V4, nhãn V153 "No"/"Yes").

Ý TƯỞNG: thay vì chỉ chạy 1 thuật toán trên 1 file đơn lẻ (như
detect_class_noise()/detect_class_noise_distance()/detect_class_noise_ensemble()
làm trong web -- không có khái niệm train/test), ta dùng TẬP TRAIN để "học"
mô hình/ngân hàng láng giềng, rồi áp dụng lên TẬP TEST (dữ liệu mô hình CHƯA
TỪNG THẤY) để lấy "dự đoán độc lập" cho mỗi dòng test. So dự đoán đó với nhãn
ĐANG GHI trong file test -- nếu khác thì gắn cờ nghi ngờ.

CẢNH BÁO QUAN TRỌNG (PHẢI đọc trước khi tin số liệu bên dưới, giống hệt
caveat đã ghi trong evaluate_distance_train_test.py): nhãn ghi trong file
test KHÔNG PHẢI ground truth đã được kiểm chứng độc lập (thầy không cung cấp
file "đáp án sạch" riêng) -- ta chỉ đang coi nó LÀ đúng để có 1 cột mốc so
sánh. Vì vậy mọi "accuracy"/"agreement_rate"/Precision/Recall/F1 ở đây đo
"mô hình học từ train có dự đoán KHỚP nhãn ghi của test hay không", KHÔNG
PHẢI "mô hình bắt được nhãn SAI THẬT bao nhiêu %". Muốn đo đúng nghĩa thứ 2
thì cần cấy nhiễu có kiểm soát (như evaluate_class_noise_synthetic.py) hoặc
có file đáp án độc lập -- cả 2 đều chưa có cho đúng dữ liệu của thầy.

Tiền xử lý (Bước 3 feature_selection.py -- cap_outliers + log_transform):
KHÔNG gọi lại cap_outliers()/log_transform() riêng cho TRAIN và riêng cho
TEST (sẽ làm 2 bộ dùng 2 biên cap KHÁC NHAU, tự fit trên chính nó) -- vì
mục tiêu ở đây là mô phỏng đúng tinh thần ML "học tham số tiền xử lý từ
TRAIN, áp dụng NGUYÊN VẸN cho TEST" (tránh để phân phối của TEST "rò rỉ"
vào bước làm sạch). Biên cap IQR tính 1 LẦN từ TRAIN (hàm fit_cap_bounds())
rồi áp dụng y hệt lên CẢ train lẫn test (apply_cap()); log1p không cần fit
tham số gì nên áp dụng trực tiếp cho cả 2 (apply_log1p()). Công thức giống
NGUYÊN VẸN class_noise/feature_selection.py (IQR k=1.5, log1p, bỏ qua cột
IQR suy biến/có giá trị âm) -- chỉ khác chỗ TÁCH fit/apply để không phạm
lỗi "học tham số từ dữ liệu test" (data leakage).

Chạy: python3 evaluate_class_noise_train_test.py
"""

import time
from collections import Counter

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.naive_bayes import GaussianNB
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.svm import LinearSVC

from attribute_noise.pipeline import load_data
from class_noise.confident_learning import (
    _compute_class_thresholds,
    _find_confident_classes,
    get_out_of_fold_probs,
)
from class_noise.config import ClassNoiseConfig

TRAIN_PATH = "data/class_noise_train.csv"
TEST_PATH = "data/class_noise_test.csv"
LABEL_COLUMN = "V153"
FEATURE_COLUMNS = ["V44", "V12", "V4"]
K_NEIGHBORS = 5
CV_FOLDS = 5
N_ESTIMATORS = 300
RANDOM_STATE = 42
OUTLIER_THRESHOLD = 1.5  # k trong công thức IQR, khớp mặc định cap_outliers()


# --------------------------------------------------------------------------
# Tiền xử lý: fit biên cap TỪ TRAIN, áp dụng NGUYÊN VẸN cho cả train + test.
# Công thức y hệt class_noise/feature_selection.py (cap_outliers/log_transform)
# -- xem docstring module ở trên để biết lý do tách fit/apply riêng.
# --------------------------------------------------------------------------
def fit_cap_bounds(train_df: pd.DataFrame, columns: list[str]) -> dict[str, tuple[float, float]]:
    bounds = {}
    for col in columns:
        s = pd.to_numeric(train_df[col], errors="coerce")
        q1, q3 = s.quantile(0.25), s.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            continue  # IQR suy biến -> bỏ qua cột này, giống cap_outliers()
        bounds[col] = (q1 - OUTLIER_THRESHOLD * iqr, q3 + OUTLIER_THRESHOLD * iqr)
    return bounds


def apply_cap(df: pd.DataFrame, bounds: dict[str, tuple[float, float]]) -> pd.DataFrame:
    result = df.copy()
    for col, (lo, hi) in bounds.items():
        result[col] = pd.to_numeric(result[col], errors="coerce").clip(lo, hi)
    return result


def apply_log1p(df: pd.DataFrame, columns: list[str], skip_columns: set[str]) -> pd.DataFrame:
    result = df.copy()
    for col in columns:
        if col in skip_columns:
            continue
        result[col] = np.log1p(pd.to_numeric(result[col], errors="coerce"))
    return result


def preprocess(
    train_df: pd.DataFrame, test_df: pd.DataFrame, feature_columns: list[str] = FEATURE_COLUMNS
) -> tuple[pd.DataFrame, pd.DataFrame]:
    bounds = fit_cap_bounds(train_df, feature_columns)
    train_capped = apply_cap(train_df, bounds)
    test_capped = apply_cap(test_df, bounds)

    # Quyết định cột nào ĐỦ ĐIỀU KIỆN log1p (không âm) DỰA TRÊN TRAIN -- tránh
    # peek vào test để quyết định tiền xử lý.
    skip_log = {
        col
        for col in feature_columns
        if (pd.to_numeric(train_capped[col], errors="coerce") < 0).any()
    }
    train_final = apply_log1p(train_capped, feature_columns, skip_log)
    test_final = apply_log1p(test_capped, feature_columns, skip_log)

    print(f"Tiền xử lý (cap_outliers + log_transform, fit trên train):")
    for col in feature_columns:
        status = "log1p" if col not in skip_log else "KHÔNG log (có giá trị âm sau cap)"
        bound_str = f"biên=[{bounds[col][0]:.3f}, {bounds[col][1]:.3f}]" if col in bounds else "IQR suy biến -> không cap"
        print(f"  {col}: {bound_str}, {status}")
    print()
    return train_final, test_final


def _print_report_table(report: dict, class_names: list[str]) -> None:
    print(f"{'Lớp':<8} {'Precision':>10} {'Recall':>8} {'F1':>8} {'n (test)':>10}")
    for cls in class_names:
        r = report[cls]
        print(f"{cls:<8} {r['precision']:>10.3f} {r['recall']:>8.3f} {r['f1-score']:>8.3f} {int(r['support']):>10,}")


def _print_confusion(cm: np.ndarray, class_names: list[str], row_label: str) -> None:
    print(f"\nMa trận đếm (hàng = {row_label}, cột = dự đoán):")
    print(f"{'':<10}" + "".join(f"{c:>12}" for c in class_names))
    for i, name in enumerate(class_names):
        print(f"{name:<10}" + "".join(f"{cm[i, j]:>12,}" for j in range(len(class_names))))


# --------------------------------------------------------------------------
# 1) SINGLE LEARNING-BASED: Confident Learning + Random Forest.
#    - Ngưỡng tự tin riêng từng lớp (class_thresholds) tính qua OOF-CV TRÊN
#      TRAIN (đúng thuật toán gốc -- thresholds phải đến từ dữ liệu "model
#      chưa học thuộc lòng").
#    - Model THẬT dùng để dự đoán TEST là 1 Random Forest fit 1 LẦN trên
#      TOÀN BỘ train (không cần CV nữa vì đã có TEST thật làm holdout --
#      CV trong bản sản phẩm chỉ là giải pháp thay thế cho lúc KHÔNG có
#      tập test riêng).
# --------------------------------------------------------------------------
def evaluate_single_learning(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    label_column: str = LABEL_COLUMN,
    feature_columns: list[str] = FEATURE_COLUMNS,
) -> dict:
    label_encoder = LabelEncoder().fit(train_df[label_column])
    y_train = label_encoder.transform(train_df[label_column])
    y_test = label_encoder.transform(test_df[label_column])
    class_names = list(label_encoder.classes_)
    n_classes = len(class_names)

    X_train = train_df[feature_columns].apply(lambda s: s.astype(float)).to_numpy()
    X_test = test_df[feature_columns].apply(lambda s: s.astype(float)).to_numpy()

    config = ClassNoiseConfig(
        label_column=label_column,
        feature_columns=feature_columns,
        n_estimators=N_ESTIMATORS,
        cv_folds=CV_FOLDS,
        random_state=RANDOM_STATE,
    )

    print("[Single learning] Đang chạy OOF-CV trên train để tính ngưỡng tự tin từng lớp...")
    t0 = time.time()
    oof_probs = get_out_of_fold_probs(X_train, y_train, config)
    thresholds = _compute_class_thresholds(oof_probs, y_train, n_classes)
    t1 = time.time()
    print(f"  -> xong OOF-CV trong {t1 - t0:.1f}s")

    print("[Single learning] Đang fit Random Forest cuối cùng trên TOÀN BỘ train...")
    rf = RandomForestClassifier(
        n_estimators=N_ESTIMATORS, class_weight="balanced", random_state=RANDOM_STATE, n_jobs=-1
    )
    rf.fit(X_train, y_train)
    t2 = time.time()
    print(f"  -> xong fit trong {t2 - t1:.1f}s")

    pred_probs_test = rf.predict_proba(X_test)
    t3 = time.time()
    print(f"  -> xong predict_proba trên test trong {t3 - t2:.1f}s")

    argmax_test = pred_probs_test.argmax(axis=1)
    test_accuracy = float((argmax_test == y_test).mean())
    class_counts_test = pd.Series(y_test).value_counts()
    baseline = float(class_counts_test.max() / len(y_test))

    confident_test = _find_confident_classes(pred_probs_test, thresholds)
    n_confident_total = int((confident_test != -1).sum())
    flagged_mask = (confident_test != -1) & (confident_test != y_test)
    flagged_row_numbers = (np.where(flagged_mask)[0] + 1).tolist()  # 1-based, khớp quy ước findings

    report = classification_report(
        y_test, argmax_test, labels=range(n_classes), target_names=class_names, output_dict=True, zero_division=0
    )
    cm = confusion_matrix(y_test, argmax_test, labels=range(n_classes))

    return dict(
        method="single_learning",
        class_names=class_names,
        thresholds=dict(zip(class_names, thresholds.tolist())),
        test_accuracy=test_accuracy,
        baseline=baseline,
        report=report,
        confusion_matrix=cm,
        n_confident_total=n_confident_total,
        n_test=len(y_test),
        flagged_row_numbers=set(flagged_row_numbers),
        timings=dict(oof_cv=t1 - t0, fit_final=t2 - t1, predict=t3 - t2),
    )


# --------------------------------------------------------------------------
# 2) DISTANCE-BASED: Mutual k-NN (N13), khuôn train/test -- y hệt
#    evaluate_distance_train_test.py, chỉ khác đầu vào đã qua cap+log.
# --------------------------------------------------------------------------
def evaluate_distance(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    k: int = K_NEIGHBORS,
    label_column: str = LABEL_COLUMN,
    feature_columns: list[str] = FEATURE_COLUMNS,
) -> dict:
    X_train_raw = train_df[feature_columns].apply(lambda s: s.astype(float)).to_numpy()
    X_test_raw = test_df[feature_columns].apply(lambda s: s.astype(float)).to_numpy()
    scaler = StandardScaler().fit(X_train_raw)
    X_train = scaler.transform(X_train_raw)
    X_test = scaler.transform(X_test_raw)

    y_train = train_df[label_column].astype(str).to_numpy()
    y_test = test_df[label_column].astype(str).to_numpy()
    class_names = sorted(set(y_train) | set(y_test))

    print(f"[Distance-based] Đang xây ngân hàng láng giềng từ train (k={k})...")
    t0 = time.time()
    nn_model = NearestNeighbors(n_neighbors=k, n_jobs=-1)
    nn_model.fit(X_train)
    _distances, indices = nn_model.kneighbors(X_test)
    t1 = time.time()
    print(f"  -> xong tra cứu láng giềng cho toàn bộ test trong {t1 - t0:.1f}s")

    predictions = np.empty(len(X_test), dtype=object)
    disagree_ratio = np.zeros(len(X_test))
    for i in range(len(X_test)):
        neighbor_labels = y_train[indices[i]]
        predictions[i] = Counter(neighbor_labels).most_common(1)[0][0]
        disagree_ratio[i] = np.mean(neighbor_labels != y_test[i])

    agreement_rate = float((predictions == y_test).mean())
    class_counts_test = pd.Series(y_test).value_counts()
    baseline = float(class_counts_test.max() / len(y_test))

    flagged_mask = disagree_ratio > 0.5
    flagged_row_numbers = set((np.where(flagged_mask)[0] + 1).tolist())

    report = classification_report(
        y_test, predictions, labels=class_names, target_names=class_names, output_dict=True, zero_division=0
    )
    cm = confusion_matrix(y_test, predictions, labels=class_names)

    return dict(
        method="distance_based",
        class_names=class_names,
        k=k,
        agreement_rate=agreement_rate,
        baseline=baseline,
        report=report,
        confusion_matrix=cm,
        n_test=len(y_test),
        flagged_row_numbers=flagged_row_numbers,
        timings=dict(neighbor_lookup=t1 - t0),
    )


# --------------------------------------------------------------------------
# 3) ENSEMBLE-BASED (N29): 3 classifier khác họ, khuôn train/test -- fit
#    TRỰC TIẾP trên toàn bộ train (không cần CV nữa, lý do giống mục 1),
#    dự đoán trên test, biểu quyết đa số.
# --------------------------------------------------------------------------
def evaluate_ensemble(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    random_state: int = RANDOM_STATE,
    label_column: str = LABEL_COLUMN,
    feature_columns: list[str] = FEATURE_COLUMNS,
) -> dict:
    X_train_raw = train_df[feature_columns].apply(lambda s: s.astype(float)).to_numpy()
    X_test_raw = test_df[feature_columns].apply(lambda s: s.astype(float)).to_numpy()
    scaler = StandardScaler().fit(X_train_raw)
    X_train = scaler.transform(X_train_raw)
    X_test = scaler.transform(X_test_raw)

    label_encoder = LabelEncoder().fit(train_df[label_column])
    y_train = label_encoder.transform(train_df[label_column])
    y_test = label_encoder.transform(test_df[label_column])
    class_names = list(label_encoder.classes_)
    n_classes = len(class_names)

    classifiers = {
        "LogisticRegression": LogisticRegression(class_weight="balanced", max_iter=1000, random_state=random_state),
        "GaussianNB": GaussianNB(priors=[1 / n_classes] * n_classes),
        "LinearSVC": LinearSVC(class_weight="balanced", max_iter=5000, random_state=random_state),
    }

    predictions_test: dict[str, np.ndarray] = {}
    per_classifier_test_accuracy: dict[str, float] = {}
    timings: dict[str, dict[str, float]] = {}
    for name, clf in classifiers.items():
        print(f"[Ensemble] Đang fit {name} trên toàn bộ train...")
        t0 = time.time()
        clf.fit(X_train, y_train)
        t1 = time.time()
        preds = clf.predict(X_test)
        t2 = time.time()
        predictions_test[name] = preds
        per_classifier_test_accuracy[name] = float((preds == y_test).mean())
        timings[name] = dict(fit=t1 - t0, predict=t2 - t1)
        print(f"  -> fit {t1 - t0:.1f}s, predict {t2 - t1:.1f}s, accuracy(test)={per_classifier_test_accuracy[name]:.4f}")

    class_counts_test = pd.Series(y_test).value_counts()
    baseline = float(class_counts_test.max() / len(y_test))

    clf_names = list(classifiers.keys())
    votes_matrix = np.vstack([predictions_test[name] for name in clf_names])  # (3, n_test)
    majority_vote = np.array(
        [Counter(votes_matrix[:, i]).most_common(1)[0][0] for i in range(votes_matrix.shape[1])]
    )
    majority_vote_accuracy = float((majority_vote == y_test).mean())

    disagree_ratio = (votes_matrix != y_test).mean(axis=0)
    flagged_mask = disagree_ratio > 0.5
    flagged_row_numbers = set((np.where(flagged_mask)[0] + 1).tolist())

    report = classification_report(
        y_test, majority_vote, labels=range(n_classes), target_names=class_names, output_dict=True, zero_division=0
    )
    cm = confusion_matrix(y_test, majority_vote, labels=range(n_classes))

    return dict(
        method="ensemble_based",
        class_names=class_names,
        classifier_names=clf_names,
        per_classifier_test_accuracy=per_classifier_test_accuracy,
        majority_vote_accuracy=majority_vote_accuracy,
        baseline=baseline,
        report=report,
        confusion_matrix=cm,
        n_test=len(y_test),
        flagged_row_numbers=flagged_row_numbers,
        timings=timings,
    )


def main() -> None:
    print("Đang đọc dữ liệu...")
    train_df = load_data(TRAIN_PATH)
    test_df = load_data(TEST_PATH)
    print(f"Train: {len(train_df):,} dòng | Test: {len(test_df):,} dòng")
    print(f"Phân bố nhãn train: {dict(train_df[LABEL_COLUMN].value_counts())}")
    print(f"Phân bố nhãn test:  {dict(test_df[LABEL_COLUMN].value_counts())}")
    print()

    train_clean, test_clean = preprocess(train_df, test_df)

    overall_t0 = time.time()
    single_result = evaluate_single_learning(train_clean, test_clean)
    print()
    distance_result = evaluate_distance(train_clean, test_clean)
    print()
    ensemble_result = evaluate_ensemble(train_clean, test_clean)
    overall_t1 = time.time()

    print("\n\n" + "=" * 90)
    print(f"TỔNG HỢP KẾT QUẢ -- train={len(train_clean):,} dòng, test={len(test_clean):,} dòng "
          f"(tổng thời gian chạy: {overall_t1 - overall_t0:.1f}s)")
    print("=" * 90)

    # --- 1) Single learning ---
    print("\n--- 1) SINGLE LEARNING-BASED (Confident Learning + Random Forest) ---")
    print(f"Test accuracy (RF, argmax, fit trên toàn train): {single_result['test_accuracy']:.4f} "
          f"({single_result['test_accuracy']:.2%})")
    print(f"Baseline (đoán bừa lớp đa số của test): {single_result['baseline']:.4f} ({single_result['baseline']:.2%})")
    print(f"Chênh lệch so với baseline: {(single_result['test_accuracy'] - single_result['baseline']) * 100:+.2f} điểm %")
    print(f"Ngưỡng tự tin từng lớp (từ OOF-CV trên train): {single_result['thresholds']}")
    print(f"Số dòng test đủ tự tin để kết luận (vượt ngưỡng 1 lớp nào đó): "
          f"{single_result['n_confident_total']:,}/{single_result['n_test']:,}")
    print(f"Số dòng test bị gắn cờ nghi ngờ sai nhãn: {len(single_result['flagged_row_numbers']):,} "
          f"({len(single_result['flagged_row_numbers']) / single_result['n_test']:.2%})")
    _print_report_table(single_result["report"], single_result["class_names"])
    _print_confusion(single_result["confusion_matrix"], single_result["class_names"], "nhãn ghi (test)")

    # --- 2) Distance-based ---
    print("\n\n--- 2) DISTANCE-BASED (Mutual k-NN, N13) ---")
    print(f"k = {distance_result['k']}")
    print(f"Agreement rate (nhãn đa số của k láng giềng-train khớp nhãn ghi test): "
          f"{distance_result['agreement_rate']:.4f} ({distance_result['agreement_rate']:.2%})")
    print(f"Baseline: {distance_result['baseline']:.4f} ({distance_result['baseline']:.2%})")
    print(f"Chênh lệch so với baseline: {(distance_result['agreement_rate'] - distance_result['baseline']) * 100:+.2f} điểm %")
    print(f"Số dòng test bị gắn cờ nghi ngờ sai nhãn: {len(distance_result['flagged_row_numbers']):,} "
          f"({len(distance_result['flagged_row_numbers']) / distance_result['n_test']:.2%})")
    _print_report_table(distance_result["report"], distance_result["class_names"])
    _print_confusion(distance_result["confusion_matrix"], distance_result["class_names"], "nhãn ghi (test)")

    # --- 3) Ensemble-based ---
    print("\n\n--- 3) ENSEMBLE-BASED (N29: LogisticRegression + GaussianNB + LinearSVC) ---")
    for name, acc in ensemble_result["per_classifier_test_accuracy"].items():
        print(f"  {name:<20} accuracy(test) = {acc:.4f} ({acc:.2%}), chênh baseline "
              f"{(acc - ensemble_result['baseline']) * 100:+.2f} điểm %")
    print(f"Majority-vote accuracy (đa số 3 classifier khớp nhãn ghi test): "
          f"{ensemble_result['majority_vote_accuracy']:.4f} ({ensemble_result['majority_vote_accuracy']:.2%})")
    print(f"Baseline: {ensemble_result['baseline']:.4f} ({ensemble_result['baseline']:.2%})")
    print(f"Chênh lệch so với baseline: "
          f"{(ensemble_result['majority_vote_accuracy'] - ensemble_result['baseline']) * 100:+.2f} điểm %")
    print(f"Số dòng test bị gắn cờ nghi ngờ sai nhãn: {len(ensemble_result['flagged_row_numbers']):,} "
          f"({len(ensemble_result['flagged_row_numbers']) / ensemble_result['n_test']:.2%})")
    _print_report_table(ensemble_result["report"], ensemble_result["class_names"])
    _print_confusion(ensemble_result["confusion_matrix"], ensemble_result["class_names"], "nhãn ghi (test)")

    # --- So sánh mức độ ĐỒNG Ý giữa 3 phương pháp (không liên quan ground truth) ---
    print("\n\n--- SO SÁNH 3 PHƯƠNG PHÁP: mức độ trùng các dòng bị gắn cờ trên TEST ---")
    sl_flagged = single_result["flagged_row_numbers"]
    db_flagged = distance_result["flagged_row_numbers"]
    en_flagged = ensemble_result["flagged_row_numbers"]
    print(f"Single learning: {len(sl_flagged):,} dòng | Distance-based: {len(db_flagged):,} dòng | "
          f"Ensemble-based: {len(en_flagged):,} dòng")
    print(f"Trùng Single ∩ Distance:  {len(sl_flagged & db_flagged):,}")
    print(f"Trùng Single ∩ Ensemble:  {len(sl_flagged & en_flagged):,}")
    print(f"Trùng Distance ∩ Ensemble: {len(db_flagged & en_flagged):,}")
    print(f"Trùng CẢ 3 cùng gắn cờ:   {len(sl_flagged & db_flagged & en_flagged):,}")
    print(f"Hợp (ít nhất 1 trong 3 gắn cờ): {len(sl_flagged | db_flagged | en_flagged):,}")


if __name__ == "__main__":
    main()
