"""
Đánh giá định lượng cho Class Noise (Confident Learning + Random Forest) bằng
NHIỄU NHÃN CẤY THÊM CÓ KIỂM SOÁT -- đúng phương pháp chính bài báo gốc Confident
Learning (Northcutt et al., JAIR 2021) dùng để tự đánh giá (vd thí nghiệm
"CIFAR với 40% nhiễu nhãn cấy thêm" trong bài blog l7.curtisnorthcutt.com).

LÝ DO không tìm bộ dữ liệu "nhãn sai + nhãn đúng" có sẵn trên mạng: các bộ nổi
tiếng có sẵn ground truth kiểu này (CIFAR-10N...) đều là dữ liệu ẢNH, không hợp
với Random Forest trên dữ liệu BẢNG mà khoá luận đang dùng. Cấy nhiễu có kiểm
soát lên dữ liệu bảng THẬT (Adult Income, đã xác minh sạch ở các lần chạy
trước) là cách làm được thừa nhận rộng rãi trong nghiên cứu (xem SYNLABEL,
CrowdTeacher -- cùng dùng kỹ thuật "flip nhãn 1 tỉ lệ biết trước rồi đánh giá
lại bằng nhãn gốc trước khi flip").

Cách làm:
  1. Lấy nhãn THẬT (income) của Adult Income làm "nhãn đúng" (ground truth).
  2. Chọn ngẫu nhiên đúng NOISE_RATE% số dòng, đổi nhãn của chúng (flip
     <=50K <-> >50K) -- đây là "nhãn ghi" (noisy label) sẽ đưa vào detect.
  3. Chạy detect_class_noise() như sản phẩm thật đang làm, lấy danh sách
     "findings" (dòng bị nghi ngờ sai nhãn).
  4. So findings với danh sách dòng ĐÃ BIẾT TRƯỚC bị flip -> tính TP/FP/FN,
     Precision/Recall/F1 -- CHÍNH XÁC đo được "class noise của tôi hiệu quả
     thế nào", không còn phải suy luận gián tiếp qua cv_accuracy/baseline nữa.

Chạy: python3 evaluate_class_noise_synthetic.py
"""

import random

import pandas as pd

from attribute_noise.pipeline import load_data
from class_noise.config import ClassNoiseConfig
from class_noise.confident_learning import detect_class_noise

DATA_PATH = "data/kaggle_adult_income.csv"
LABEL_COLUMN = "income"
FEATURE_COLUMNS = ["age", "fnlwgt", "education.num", "capital.gain", "capital.loss", "hours.per.week"]
NOISE_RATES = [0.10, 0.30]  # thử 2 mức nhiễu khác nhau: nhẹ (10%) và nặng (30%)
RANDOM_SEED = 42


def inject_label_noise(df: pd.DataFrame, noise_rate: float, seed: int) -> tuple[pd.DataFrame, set[int]]:
    """Trả về (df đã cấy nhiễu, tập index các dòng BỊ FLIP -- ground truth)."""
    rng = random.Random(seed)
    classes = sorted(df[LABEL_COLUMN].unique())
    n_flip = int(len(df) * noise_rate)
    flip_indices = set(rng.sample(list(df.index), n_flip))

    noisy_df = df.copy()
    for idx in flip_indices:
        true_label = df.loc[idx, LABEL_COLUMN]
        # Đổi sang 1 nhãn KHÁC nhãn thật (với bài toán 2 lớp thì chỉ có đúng 1
        # lựa chọn, nhưng viết tổng quát để chạy được cả khi >2 lớp).
        other_classes = [c for c in classes if c != true_label]
        noisy_df.loc[idx, LABEL_COLUMN] = rng.choice(other_classes)
    return noisy_df, flip_indices


def evaluate_one_noise_rate(clean_df: pd.DataFrame, noise_rate: float) -> None:
    noisy_df, flip_indices = inject_label_noise(clean_df, noise_rate, RANDOM_SEED)

    config = ClassNoiseConfig(label_column=LABEL_COLUMN, feature_columns=FEATURE_COLUMNS)
    result = detect_class_noise(noisy_df, config)

    flagged_indices = {f.row_number - 1 for f in result.findings}  # row_number la 1-based

    tp = len(flagged_indices & flip_indices)
    fp = len(flagged_indices - flip_indices)
    fn = len(flip_indices - flagged_indices)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    diag = result.diagnostics
    print(f"\n{'=' * 72}")
    print(f"=== Mức nhiễu cấy thêm: {noise_rate:.0%} ({len(flip_indices)}/{len(clean_df)} dòng bị flip nhãn) ===")
    print(f"{'=' * 72}")
    print(f"CV accuracy       : {diag.cv_accuracy:.4f}")
    print(f"Majority baseline : {diag.majority_baseline_accuracy:.4f}")
    print(f"Tong so dong bi gan co nghi ngo: {len(result.findings)}")
    print()
    print(f"So dong THAT SU bi flip (ground truth) : {len(flip_indices)}")
    print(f"TP (bat dung dong bi flip)             : {tp}")
    print(f"FP (gan co nham dong KHONG bi flip)     : {fp}")
    print(f"FN (bo sot dong bi flip)                : {fn}")
    print(f"Precision : {precision:.4f}")
    print(f"Recall    : {recall:.4f}")
    print(f"F1        : {f1:.4f}")


def main() -> None:
    df = load_data(DATA_PATH)
    for rate in NOISE_RATES:
        evaluate_one_noise_rate(df, rate)


if __name__ == "__main__":
    main()
