"""
Đánh giá N13 (Mutual k-NN) theo đúng khuôn TRAIN/TEST trên dữ liệu THẬT của
thầy (class_noise_train.csv / class_noise_test.csv -- 3 đặc trưng V44/V12/V4,
nhãn V153 "No"/"Yes").

KHÁC với distance_based.py (tự tìm láng giềng LẪN NHAU bên trong CÙNG 1 file):
N13 không có khái niệm "train rồi predict" như Random Forest, nên cách dùng
hợp lý nhất cho cặp train/test là XÂY "ngân hàng láng giềng" từ tập TRAIN, rồi
với MỖI dòng ở tập TEST, tìm k láng giềng gần nhất của nó TRONG tập train, lấy
nhãn ĐA SỐ của các láng giềng đó làm "dự đoán" cho dòng test -- nếu khác nhãn
đang ghi thì gắn cờ nghi ngờ.

QUAN TRỌNG -- con số "% khớp" (agreement_rate) tính ra ở đây vẫn CHỈ so với
NHÃN GHI trong file test (không phải nhãn đúng thật, vì không có ground truth
cho dữ liệu thầy) -- giống hệt cách cv_accuracy/baseline của Confident
Learning cũng chỉ so với nhãn ghi. Đây là chỉ số "N13 có học được cấu trúc
thật không", KHÔNG PHẢI "N13 đoán trúng nhãn ĐÚNG bao nhiêu %" (câu đó chỉ đo
được bằng cấy nhiễu có kiểm soát như evaluate_distance_vs_confident.py).

Chạy: python3 evaluate_distance_train_test.py
"""

from collections import Counter

import numpy as np
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

from attribute_noise.pipeline import load_data

TRAIN_PATH = "data/class_noise_train.csv"
TEST_PATH = "data/class_noise_test.csv"
LABEL_COLUMN = "V153"
FEATURE_COLUMNS = ["V44", "V12", "V4"]
K = 5


def main() -> None:
    train_df = load_data(TRAIN_PATH)
    test_df = load_data(TEST_PATH)
    print(f"Train: {len(train_df):,} dòng | Test: {len(test_df):,} dòng | k={K}")

    # Chuẩn hoá z-score: fit TRÊN TRAIN, áp dụng cho CẢ train lẫn test -- đúng
    # thực hành chuẩn của ML (tránh "rò rỉ" thông tin thống kê của test vào
    # lúc chuẩn hoá, dù ở đây ảnh hưởng không lớn vì chỉ chuẩn hoá, không học
    # tham số dự đoán gì từ test).
    X_train_raw = train_df[FEATURE_COLUMNS].apply(lambda s: s.astype(float)).to_numpy()
    X_test_raw = test_df[FEATURE_COLUMNS].apply(lambda s: s.astype(float)).to_numpy()
    scaler = StandardScaler().fit(X_train_raw)
    X_train = scaler.transform(X_train_raw)
    X_test = scaler.transform(X_test_raw)

    y_train = train_df[LABEL_COLUMN].astype(str).to_numpy()
    y_test = test_df[LABEL_COLUMN].astype(str).to_numpy()

    print("Đang xây 'ngân hàng láng giềng' từ tập train + tra cứu cho từng dòng test...")
    nn_model = NearestNeighbors(n_neighbors=K, n_jobs=-1)
    nn_model.fit(X_train)
    _distances, indices = nn_model.kneighbors(X_test)  # mỗi dòng test -> K chỉ số trong train

    agree = 0
    predictions = np.empty(len(X_test), dtype=object)  # "dự đoán" của N13 cho mỗi dòng test
    flagged_rows = []  # (row_number 1-based, recorded_label, suggested_label, disagree_ratio)
    for i in range(len(X_test)):
        neighbor_labels = y_train[indices[i]]
        majority_label, _majority_count = Counter(neighbor_labels).most_common(1)[0]
        predictions[i] = majority_label
        if majority_label == y_test[i]:
            agree += 1
        else:
            disagree_count = sum(1 for lbl in neighbor_labels if lbl != y_test[i])
            flagged_rows.append((i + 1, y_test[i], majority_label, disagree_count / K))

    agreement_rate = agree / len(X_test)

    # Baseline: đoán bừa lớp đa số của CHÍNH tập test (để so sánh công bằng,
    # cùng population với agreement_rate) -- giống hệt công thức
    # majority_baseline_accuracy bên Confident Learning.
    class_counts = Counter(y_test)
    majority_class, majority_n = class_counts.most_common(1)[0]
    baseline = majority_n / len(y_test)

    print()
    print("=" * 70)
    print("KẾT QUẢ — N13 (Mutual k-NN), train làm ngân hàng láng giềng, test để đánh giá")
    print("=" * 70)
    print(f"Số dòng test: {len(y_test):,}")
    print(f"Phân bố nhãn test: {dict(class_counts)}")
    print(f"Số dòng 'dự đoán' (đa số láng giềng train) KHỚP nhãn ghi: {agree:,} / {len(y_test):,}")
    print(f"=> agreement_rate = {agreement_rate:.4f} ({agreement_rate:.2%})")
    print(f"Baseline (đoán bừa lớp đa số '{majority_class}' của chính tập test): {baseline:.4f} ({baseline:.2%})")
    print(f"Chênh lệch so với baseline: {(agreement_rate - baseline) * 100:+.2f} điểm %")
    print(f"Số dòng bị gắn cờ nghi ngờ sai nhãn: {len(flagged_rows):,} ({len(flagged_rows) / len(y_test):.2%})")

    # --- Coi nhãn ghi trong file test LÀ ĐÚNG (giả định của câu hỏi), xem
    # N13 "đoán" (= nhãn đa số của k láng giềng lấy từ train) khớp bao nhiêu
    # % THEO TỪNG LỚP riêng -- đây chính là Precision/Recall/F1 kiểu
    # classification_report, giống hệt per_class_report bên
    # confident_learning.py để dễ so sánh. ---
    print()
    print("=" * 70)
    print("GIẢ ĐỊNH nhãn ghi trong file test LÀ ĐÚNG -- Precision/Recall/F1 từng lớp")
    print("=" * 70)
    report = classification_report(y_test, predictions, output_dict=True, zero_division=0)
    labels_order = sorted(report.keys() - {"accuracy", "macro avg", "weighted avg"})
    print(f"{'Lớp':<8} {'Precision':>10} {'Recall':>8} {'F1':>8} {'n (số dòng thật)':>18}")
    for cls in labels_order:
        r = report[cls]
        print(f"{cls:<8} {r['precision']:>10.3f} {r['recall']:>8.3f} {r['f1-score']:>8.3f} {int(r['support']):>18,}")
    print(f"\nTổng accuracy (coi nhãn ghi là đúng): {report['accuracy']:.4f} ({report['accuracy']:.2%})")

    cm = confusion_matrix(y_test, predictions, labels=labels_order)
    print(f"\nMa trận đếm (hàng = nhãn ghi/\"đúng\", cột = N13 dự đoán):")
    print(f"{'':<10}" + "".join(f"{c:>12}" for c in labels_order))
    for i, row_label in enumerate(labels_order):
        print(f"{row_label:<10}" + "".join(f"{cm[i, j]:>12,}" for j in range(len(labels_order))))

    print()
    print("5 dòng nghi ngờ cao nhất (tỉ lệ láng giềng bất đồng cao nhất):")
    flagged_rows.sort(key=lambda r: r[3], reverse=True)
    for row_number, recorded, suggested, ratio in flagged_rows[:5]:
        print(f"  Dòng {row_number}: ghi='{recorded}', gợi ý='{suggested}', tỉ lệ bất đồng={ratio:.2f}")


if __name__ == "__main__":
    main()
