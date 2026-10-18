"""
Chạy lại ĐÚNG pipeline đánh giá đã làm ở evaluate_adult_categorical_vs_numeric.py
(CHỈ cột số vs SỐ+CHỮ, cả 3 thuật toán) nhưng dùng ĐÚNG SPLIT TRAIN/TEST
CHUẨN của UCI Adult Income -- KHÔNG tự chia 80/20 ngẫu nhiên nữa:
  - Train: data/kaggle_adult_income.csv (32.561 dòng -- đã xác nhận khớp
    y hệt 100% file adult.data gốc của UCI, chỉ khác thứ tự dòng).
  - Test:  data/kaggle_adult_income_test_uci.csv (16.281 dòng -- chuyển đổi
    từ adult.test gốc, đã xử lý 2 lỗi định dạng gốc: bỏ dòng comment đầu
    file + bỏ dấu "." thừa cuối nhãn).

Dùng split CHUẨN này để kết quả SO SÁNH ĐƯỢC TRỰC TIẾP với các con số đã
công bố trên chính bộ Adult Income (vd C4.5 lỗi 15.54%, Naive-Bayes 16.12%,
NBTree 14.10% -- ghi trong chính file adult.names) -- khác hẳn split tự
chia 80/20 trước đó (mỗi người tự chia ra tập test khác nhau, không so
sánh công bằng được với nghiên cứu khác).

Tái dùng NGUYÊN VẸN fit_transform_categorical()/run_and_print() đã viết ở
evaluate_adult_categorical_vs_numeric.py -- không viết lại.

Chạy: python3 evaluate_adult_official_uci_split.py
"""

from attribute_noise.pipeline import load_data
from evaluate_adult_categorical_vs_numeric import (
    CATEGORICAL_COLUMNS,
    LABEL_COLUMN,
    NUMERIC_COLUMNS,
    fit_transform_categorical,
    run_and_print,
)
from evaluate_class_noise_train_test import preprocess

TRAIN_PATH = "data/kaggle_adult_income.csv"
TEST_PATH = "data/kaggle_adult_income_test_uci.csv"


def main() -> None:
    train_df = load_data(TRAIN_PATH)
    test_df = load_data(TEST_PATH)
    print(f"Train (adult.data gốc): {len(train_df):,} dòng")
    print(f"Test  (adult.test gốc): {len(test_df):,} dòng")
    print(f"Phân bố nhãn train: {dict(train_df[LABEL_COLUMN].value_counts())}")
    print(f"Phân bố nhãn test:  {dict(test_df[LABEL_COLUMN].value_counts())}")

    # --- (A) CHỈ 6 cột số ---
    train_numeric, test_numeric = preprocess(train_df, test_df, feature_columns=NUMERIC_COLUMNS)
    results_a = run_and_print("(A) CHỈ CỘT SỐ (6 cột) -- split CHUẨN UCI", train_numeric, test_numeric, NUMERIC_COLUMNS)

    # --- (B) 6 cột số + 8 cột chữ one-hot (fit trên train, apply cho test) ---
    train_full, test_full, dummy_columns = fit_transform_categorical(train_df, test_df, CATEGORICAL_COLUMNS)
    train_full, test_full = preprocess(train_full, test_full, feature_columns=NUMERIC_COLUMNS)
    feature_columns_b = NUMERIC_COLUMNS + dummy_columns
    results_b = run_and_print(
        f"(B) SỐ + CHỮ ({len(dummy_columns)} cột one-hot) -- split CHUẨN UCI",
        train_full, test_full, feature_columns_b,
    )

    print(f"\n\n{'=' * 90}\nBẢNG SO SÁNH (split CHUẨN UCI) -- (A) CHỈ SỐ  vs  (B) SỐ + CHỮ\n{'=' * 90}")
    rows = [
        ("Single learning", "test_accuracy", "baseline", "single"),
        ("Distance-based (N13)", "agreement_rate", "baseline", "distance"),
        ("Ensemble (majority vote)", "majority_vote_accuracy", "baseline", "ensemble"),
    ]
    print(f"{'Phương pháp':<28} {'Accuracy (A)':>13} {'Accuracy (B)':>13} {'Δ baseline (A)':>16} {'Δ baseline (B)':>16}")
    for label, acc_key, base_key, result_key in rows:
        a = results_a[result_key]
        b = results_b[result_key]
        delta_a = (a[acc_key] - a[base_key]) * 100
        delta_b = (b[acc_key] - b[base_key]) * 100
        print(f"{label:<28} {a[acc_key]:>12.4f} {b[acc_key]:>12.4f} {delta_a:>+15.2f}% {delta_b:>+15.2f}%")

    # So với số liệu LỊCH SỬ ghi trong adult.names (lỗi = 1 - accuracy), đo
    # trên ĐÚNG split chuẩn này -- để so sánh trực tiếp được.
    print("\nĐối chiếu với số liệu lịch sử ghi trong adult.names (đo trên ĐÚNG split chuẩn này):")
    print("  C4.5 (1996): lỗi 15.54% (accuracy ~84.46%)")
    print("  Naive-Bayes (1996): lỗi 16.12% (accuracy ~83.88%)")
    print("  NBTree (1996): lỗi 14.10% (accuracy ~85.90%)  <- tốt nhất trong các thuật toán 1996")
    print(f"  Single learning (B, số+chữ, khoá luận): accuracy {results_b['single']['test_accuracy']:.4f} "
          f"({results_b['single']['test_accuracy']:.2%})")


if __name__ == "__main__":
    main()
