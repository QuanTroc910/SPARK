"""
Thử nghiệm: cột CHỮ (category) có ảnh hưởng nhiều tới nhãn "income" trên bộ
Adult Income không, so với 6 cột SỐ đang dùng làm đặc trưng cho Class Noise?

Hiện tại `class_noise/` CHỈ chấp nhận cột SỐ làm đặc trưng -- 8 cột chữ
(workclass, education, marital.status, occupation, relationship, race, sex,
native.country) hoàn toàn chưa dùng được. Script này one-hot encode 8 cột đó
(gộp nhóm giá trị HIẾM thành "Khac" trước, giống kỹ thuật RareLabelEncoder
của feature-engine -- xem giải thích đã trao đổi) rồi dùng NGUYÊN VẸN
`rank_by_importance()` có sẵn (class_noise/feature_selection.py, không viết
lại logic Random Forest importance lần 2) để xếp hạng TẤT CẢ ứng viên (6 cột
số + các cột one-hot) cùng lúc, xem cột chữ xếp hạng thế nào so với cột số.

Vì 1 cột chữ one-hot ra NHIỀU cột con (vd marital.status -> 7 cột), xếp hạng
importance từng cột con riêng lẻ sẽ khó đọc -- nên script CỘNG DỒN importance
của các cột con về lại đúng CỘT GỐC của nó để trả lời đúng câu hỏi "cột
marital.status NÓI CHUNG quan trọng cỡ nào", không phải "riêng giá trị
Married-civ-spouse quan trọng cỡ nào".

Chạy: python3 evaluate_adult_categorical_importance.py
"""

import pandas as pd

from attribute_noise.pipeline import load_data
from class_noise.feature_selection import rank_by_importance, select_by_elbow

DATA_PATH = "data/kaggle_adult_income.csv"
LABEL_COLUMN = "income"
NUMERIC_COLUMNS = ["age", "fnlwgt", "education.num", "capital.gain", "capital.loss", "hours.per.week"]
CATEGORICAL_COLUMNS = ["workclass", "education", "marital.status", "occupation", "relationship", "race", "sex", "native.country"]
RARE_THRESHOLD = 0.01  # giá trị chiếm dưới 1% tổng số dòng -> gộp vào "Khac"


def group_rare_categories(series: pd.Series, threshold: float = RARE_THRESHOLD) -> pd.Series:
    """Gộp các giá trị HIẾM (tỉ lệ < threshold) thành 1 nhóm chung "Khac" --
    tránh one-hot tạo quá nhiều cột con gần như toàn số 0 (xem giải thích đã
    trao đổi). Áp dụng CHUNG cho mọi cột, không hardcode riêng cột nào.
    """
    freq = series.value_counts(normalize=True)
    rare_values = freq[freq < threshold].index
    return series.where(~series.isin(rare_values), "Khac")


def main() -> None:
    df = load_data(DATA_PATH)
    print(f"Tổng số dòng: {len(df):,}\n")

    # --- Gộp nhóm hiếm + one-hot encode 8 cột chữ ---
    onehot_frames = []
    column_origin: dict[str, str] = {col: col for col in NUMERIC_COLUMNS}  # cột số -> chính nó
    for col in CATEGORICAL_COLUMNS:
        grouped = group_rare_categories(df[col])
        n_before = df[col].nunique()
        n_after = grouped.nunique()
        dummies = pd.get_dummies(grouped, prefix=col)
        onehot_frames.append(dummies)
        for dummy_col in dummies.columns:
            column_origin[dummy_col] = col  # nhớ cột one-hot này thuộc cột gốc nào
        print(f"{col:<16} {n_before:>3} giá trị gốc -> {n_after:>2} giá trị sau gộp nhóm hiếm (<{RARE_THRESHOLD:.0%}) -> {len(dummies.columns)} cột one-hot")

    encoded_df = pd.concat([df[NUMERIC_COLUMNS + [LABEL_COLUMN]]] + onehot_frames, axis=1)
    candidate_columns = NUMERIC_COLUMNS + [c for frame in onehot_frames for c in frame.columns]
    print(f"\nTổng ứng viên đưa vào rank_by_importance(): {len(candidate_columns)} cột "
          f"({len(NUMERIC_COLUMNS)} số + {len(candidate_columns) - len(NUMERIC_COLUMNS)} one-hot từ 8 cột chữ)\n")

    # --- Xếp hạng importance (TÁI DÙNG rank_by_importance(), không viết lại) ---
    ranked = rank_by_importance(encoded_df, LABEL_COLUMN, candidate_columns)

    print("=" * 70)
    print("TOP 15 cột (one-hot con + cột số) importance cao nhất:")
    print("=" * 70)
    for r in ranked[:15]:
        kind = "SỐ" if r.column in NUMERIC_COLUMNS else "CHỮ (one-hot)"
        print(f"  {r.column:<28} importance={r.importance:.4f}  [{kind}]")

    # --- Cộng dồn importance về lại ĐÚNG CỘT GỐC (numeric giữ nguyên, cột
    # chữ cộng tất cả mảnh one-hot con của nó lại) ---
    aggregated: dict[str, float] = {}
    for r in ranked:
        origin = column_origin[r.column]
        aggregated[origin] = aggregated.get(origin, 0.0) + r.importance
    aggregated_sorted = sorted(aggregated.items(), key=lambda kv: kv[1], reverse=True)

    print("\n" + "=" * 70)
    print("XẾP HẠNG THEO CỘT GỐC (đã cộng dồn các mảnh one-hot) -- câu trả lời chính:")
    print("=" * 70)
    for col, imp in aggregated_sorted:
        kind = "SỐ" if col in NUMERIC_COLUMNS else "CHỮ"
        bar = "#" * int(imp / aggregated_sorted[0][1] * 40)
        print(f"  {col:<16} [{kind}]  importance={imp:.4f}  {bar}")

    total_numeric = sum(v for k, v in aggregated.items() if k in NUMERIC_COLUMNS)
    total_categorical = sum(v for k, v in aggregated.items() if k in CATEGORICAL_COLUMNS)
    print(f"\nTổng importance 6 cột SỐ: {total_numeric:.4f} ({total_numeric / (total_numeric + total_categorical):.1%})")
    print(f"Tổng importance 8 cột CHỮ: {total_categorical:.4f} ({total_categorical / (total_numeric + total_categorical):.1%})")

    elbow_cols_raw = select_by_elbow(ranked)
    elbow_origins = sorted({column_origin[c] for c in elbow_cols_raw}, key=lambda c: -aggregated[c])
    print(f"\nElbow Method (trên {len(candidate_columns)} ứng viên one-hot) giữ {len(elbow_cols_raw)} cột con, "
          f"thuộc về {len(elbow_origins)} cột gốc: {elbow_origins}")


if __name__ == "__main__":
    main()
