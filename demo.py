import sys
from pathlib import Path

from attribute_noise.config import ColumnDType, ColumnNoiseConfig, DuplicateRowConfig, NoiseType
from attribute_noise.pipeline import detect_noise, findings_to_dataframe, get_flagged_rows, load_data

# Đây là chỗ người dùng "chọn loại noise cho từng cột" -- sau này UI sẽ build ra
# đúng list ColumnNoiseConfig này từ lựa chọn của người dùng trên giao diện.
# Mỗi phần tử = 1 cột user chọn + các loại noise + tham số riêng user điền cho cột đó.
COLUMN_CONFIGS = [
    ColumnNoiseConfig(
        column="id",
        dtype=ColumnDType.INTEGER,
        noise_types=[NoiseType.MISSING_VALUE, NoiseType.FORMAT_NOISE],
    ),
    ColumnNoiseConfig(
        column="full_name",
        dtype=ColumnDType.TEXT,
        # thêm WHITESPACE_NOISE để bắt tên có khoảng trắng thừa/ký tự lạ (vd "###")
        noise_types=[NoiseType.MISSING_VALUE, NoiseType.WHITESPACE_NOISE],
        disallowed_chars_pattern=r"[#@$%^&*]",
    ),
    ColumnNoiseConfig(
        column="age",
        dtype=ColumnDType.INTEGER,
        # thêm OUTLIER để bắt tuổi hợp lệ về định dạng/khoảng nhưng bất thường
        # so với phân bố chung (vd 95 tuổi trong khi đa số 22-60)
        noise_types=[
            NoiseType.MISSING_VALUE,
            NoiseType.FORMAT_NOISE,
            NoiseType.OUT_OF_RANGE,
            NoiseType.OUTLIER,
        ],
        min_value=0,
        max_value=120,
        outlier_method="iqr",
        outlier_threshold=1.5,
    ),
    ColumnNoiseConfig(
        column="gender",
        dtype=ColumnDType.CATEGORY,
        # thêm INCONSISTENT_CATEGORY để bắt "male"/"MALE"/"M" thay vì "Male"
        noise_types=[NoiseType.MISSING_VALUE, NoiseType.INCONSISTENT_CATEGORY],
        valid_categories=["Male", "Female"],
        category_similarity_threshold=0.85,
    ),
    ColumnNoiseConfig(
        column="email",
        dtype=ColumnDType.EMAIL,
        noise_types=[NoiseType.MISSING_VALUE, NoiseType.FORMAT_NOISE],
    ),
    ColumnNoiseConfig(
        column="department",
        dtype=ColumnDType.CATEGORY,
        # thêm INCONSISTENT_CATEGORY để bắt "it"/"I.T."/"Sale" thay vì "IT"/"Sales"
        noise_types=[NoiseType.MISSING_VALUE, NoiseType.INCONSISTENT_CATEGORY],
        valid_categories=["Sales", "IT", "HR", "Marketing", "Finance"],
        category_similarity_threshold=0.8,
    ),
    ColumnNoiseConfig(
        column="salary",
        dtype=ColumnDType.FLOAT,
        # thêm OUTLIER để bắt lương hợp lệ về định dạng/khoảng nhưng cao/thấp
        # bất thường so với mặt bằng chung (vd 500 triệu giữa các mức 8-40 triệu)
        noise_types=[
            NoiseType.MISSING_VALUE,
            NoiseType.FORMAT_NOISE,
            NoiseType.OUT_OF_RANGE,
            NoiseType.OUTLIER,
        ],
        min_value=0,
        max_value=100_000_000,
        outlier_method="iqr",
        outlier_threshold=1.5,
    ),
    ColumnNoiseConfig(
        column="join_date",
        dtype=ColumnDType.DATE,
        noise_types=[NoiseType.MISSING_VALUE, NoiseType.FORMAT_NOISE],
        date_format="%Y-%m-%d",
    ),
    ColumnNoiseConfig(
        column="phone",
        dtype=ColumnDType.PHONE,
        noise_types=[NoiseType.MISSING_VALUE, NoiseType.FORMAT_NOISE],
    ),
    ColumnNoiseConfig(
        column="performance_score",
        dtype=ColumnDType.FLOAT,
        noise_types=[
            NoiseType.MISSING_VALUE,
            NoiseType.FORMAT_NOISE,
            NoiseType.OUT_OF_RANGE,
            NoiseType.OUTLIER,
        ],
        min_value=0,
        max_value=100,
        outlier_method="iqr",
        outlier_threshold=1.5,
    ),
]

# Cấu hình riêng cho DUPLICATE_ROW: chỉ cần trùng "id" là bị đánh dấu, kể cả
# khi các cột khác khác nhau (bắt được cả trường hợp "contradictory instances"
# -- cùng id nhưng thông tin khác nhau -- lẫn trường hợp trùng y hệt cả dòng).
DUPLICATE_ROW_CONFIG = DuplicateRowConfig(subset_columns=["id"])


def main(input_path: str) -> None:
    df = load_data(input_path)
    findings = detect_noise(df, COLUMN_CONFIGS, duplicate_row_config=DUPLICATE_ROW_CONFIG)

    findings_df = findings_to_dataframe(findings)
    flagged_rows_df = get_flagged_rows(df, findings)

    print(f"Tổng số dòng: {len(df)}")
    print(f"Số dòng có ít nhất 1 ô lỗi: {len(flagged_rows_df)}")
    print(f"Tổng số ô lỗi phát hiện được: {len(findings_df)}")
    if not findings_df.empty:
        print("\nSố lượng theo từng loại noise:")
        print(findings_df["noise_type"].value_counts().to_string())

    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)

    findings_df.to_csv(out_dir / "noise_findings.csv", index=False)

    flagged_rows_out = flagged_rows_df.copy()
    flagged_rows_out.insert(0, "csv_line_number", flagged_rows_out.index + 2)
    flagged_rows_out.to_csv(out_dir / "flagged_rows.csv", index=False)

    print(f"\nĐã lưu: {out_dir / 'noise_findings.csv'}")
    print(f"Đã lưu: {out_dir / 'flagged_rows.csv'}")


if __name__ == "__main__":
    input_path = sys.argv[1] if len(sys.argv) > 1 else "data/noisy_employee_dataset.csv"
    main(input_path)
