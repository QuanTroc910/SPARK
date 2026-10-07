"""
Đánh giá định lượng (Precision / Recall / F1) cho 7 detector Attribute Noise,
so kết quả detect() với ground truth đã biết trước (data/noise_ground_truth*.csv).

MỤC ĐÍCH: lấy số liệu đưa vào khoá luận, KHÔNG phải tính năng sản phẩm -- không
bị import bởi app.py, giống tinh thần các file demo_*.py khác (xem CLAUDE.md).
Lý do không đưa vào web: ground truth CHỈ tồn tại cho 2 bộ dữ liệu mẫu này (vì
đã biết trước lỗi nào bị cấy ở đâu khi tạo dữ liệu test) -- người dùng thật tải
file của họ lên sẽ KHÔNG BAO GIỜ có sẵn file ground truth để so sánh.

Cách chạy:
    python3 evaluate_attribute_detectors.py            # chạy cả 2 bộ (small + large)
    python3 evaluate_attribute_detectors.py small       # chỉ bộ nhỏ (114 dòng)
    python3 evaluate_attribute_detectors.py large       # chỉ bộ lớn (313 dòng)

Cách tính TP/FP/FN: so khớp theo khoá (id, column, noise_type) -- dùng "id"
(cột ổn định, không đổi theo thứ tự dòng) thay vì vị trí dòng, đúng quy ước
ground truth đã ghi theo CLAUDE.md.
    TP = khoá có trong CẢ ground truth lẫn kết quả detect -- bắt đúng.
    FP = khoá CHỈ có trong kết quả detect -- báo động giả (gắn cờ nhầm).
    FN = khoá CHỈ có trong ground truth -- bỏ sót.
"""

import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

from attribute_noise.config import DuplicateRowConfig
from attribute_noise.pipeline import detect_noise, load_data
from demo import COLUMN_CONFIGS

# demo.py dùng subset_columns=["id"] cho duplicate_row -- giữ NGUYÊN y hệt để
# đánh giá đúng cấu hình đang thật sự chạy, không bịa config riêng.
DUPLICATE_ROW_CONFIG = DuplicateRowConfig(subset_columns=["id"])

# Ground truth dùng 1 vài nhãn noise_type CHI TIẾT HƠN để mô tả rõ ý đồ lúc
# TẠO dữ liệu test (vd phân biệt "duplicate y hệt cả dòng" với "duplicate
# nhưng dữ liệu mâu thuẫn"), nhưng ở phía detect THẬT thì:
#   - cả 2 kiểu duplicate đều do CHUNG 1 detector `duplicate_row` bắt (vì
#     DuplicateRowConfig(subset_columns=["id"]) chỉ so khớp theo "id", không
#     phân biệt lý do trùng).
#   - "special_character_noise" (full_name dính "###") do CHUNG detector
#     `whitespace_noise` bắt (qua disallowed_chars_pattern, xem detectors.py).
# Khai rõ mapping này ra đây để minh bạch, không so khớp ngầm.
GROUND_TRUTH_LABEL_TO_NOISE_TYPE = {
    "missing_value": "missing_value",
    "format_noise": "format_noise",
    "out_of_range": "out_of_range",
    "outlier": "outlier",
    "inconsistent_category": "inconsistent_category",
    "whitespace_noise": "whitespace_noise",
    "special_character_noise": "whitespace_noise",
    "duplicate_row": "duplicate_row",
    "duplicate_id_conflicting_data": "duplicate_row",
}

# duplicate_row là noise CẤP DÒNG (không gắn với 1 cột cụ thể, xem CLAUDE.md
# mục 3) -- nên so khớp theo (id, noise_type) thôi, bỏ qua "column" (ground
# truth ghi "ALL" hoặc "id" tuỳ dòng, còn code thật ghi "id" vì
# subset_columns=["id"] -- 2 bên không khớp chữ nên phải loại cột ra khỏi
# khoá so sánh để tránh bị tính nhầm thành FN/FP).
ROW_LEVEL_NOISE_TYPES = {"duplicate_row"}


def load_ground_truth(path: str) -> set[tuple]:
    gt = pd.read_csv(path, dtype=str, keep_default_na=False)
    keys: set[tuple] = set()
    for _, row in gt.iterrows():
        mapped_type = GROUND_TRUTH_LABEL_TO_NOISE_TYPE.get(row["noise_type"])
        if mapped_type is None:
            print(f"  [BỎ QUA] ground truth có noise_type lạ chưa map: "
                  f"{row['noise_type']} (id={row['id']})")
            continue
        if mapped_type in ROW_LEVEL_NOISE_TYPES:
            keys.add((row["id"], mapped_type))
        else:
            keys.add((row["id"], row["column"], mapped_type))
    return keys


def run_predictions(data_path: str) -> set[tuple]:
    df = load_data(data_path)
    findings = detect_noise(df, COLUMN_CONFIGS, duplicate_row_config=DUPLICATE_ROW_CONFIG)
    keys: set[tuple] = set()
    for f in findings:
        row_id = df.loc[f.row_index, "id"]
        if f.noise_type in ROW_LEVEL_NOISE_TYPES:
            keys.add((row_id, f.noise_type))
        else:
            keys.add((row_id, f.column, f.noise_type))
    return keys


def evaluate(gt_keys: set, pred_keys: set) -> dict:
    """Gom theo TỪNG loại noise_type, tính riêng TP/FP/FN cho mỗi loại."""
    all_types = {k[-1] for k in gt_keys} | {k[-1] for k in pred_keys}
    by_type = {}
    for t in all_types:
        gt_t = {k for k in gt_keys if k[-1] == t}
        pred_t = {k for k in pred_keys if k[-1] == t}
        by_type[t] = {
            "tp": len(gt_t & pred_t),
            "fp": len(pred_t - gt_t),
            "fn": len(gt_t - pred_t),
        }
    return by_type


def _prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    """Precision/Recall/F1 -- quy ước 0/0 = 0.0 (giống zero_division=0 của
    sklearn, đã dùng thống nhất ở class_noise/confident_learning.py)."""
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return precision, recall, f1


def print_report(by_type: dict, title: str) -> list[dict]:
    print(f"\n=== {title} ===")
    header = f"{'Loại noise':<24}{'TP':>6}{'FP':>6}{'FN':>6}{'Precision':>12}{'Recall':>10}{'F1':>8}"
    print(header)
    print("-" * len(header))

    rows = []
    total_tp = total_fp = total_fn = 0
    for t in sorted(by_type):
        s = by_type[t]
        tp, fp, fn = s["tp"], s["fp"], s["fn"]
        total_tp += tp
        total_fp += fp
        total_fn += fn
        precision, recall, f1 = _prf(tp, fp, fn)
        print(f"{t:<24}{tp:>6}{fp:>6}{fn:>6}{precision:>12.3f}{recall:>10.3f}{f1:>8.3f}")
        rows.append({
            "noise_type": t, "TP": tp, "FP": fp, "FN": fn,
            "precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4),
        })

    precision, recall, f1 = _prf(total_tp, total_fp, total_fn)
    print("-" * len(header))
    print(f"{'TỔNG (micro-avg)':<24}{total_tp:>6}{total_fp:>6}{total_fn:>6}"
          f"{precision:>12.3f}{recall:>10.3f}{f1:>8.3f}")
    rows.append({
        "noise_type": "TOTAL (micro-avg)", "TP": total_tp, "FP": total_fp, "FN": total_fn,
        "precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4),
    })
    return rows


def main() -> None:
    datasets = {
        "small": ("data/noisy_employee_dataset.csv", "data/noise_ground_truth.csv"),
        "large": ("data/noisy_employee_dataset_large.csv", "data/noise_ground_truth_large.csv"),
    }
    which = sys.argv[1] if len(sys.argv) > 1 else "both"
    targets = list(datasets.items()) if which == "both" else [(which, datasets[which])]

    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)

    for name, (data_path, gt_path) in targets:
        print(f"\n{'#' * 72}\n# Bộ dữ liệu: {name}  ({data_path})\n{'#' * 72}")
        gt_keys = load_ground_truth(gt_path)
        pred_keys = run_predictions(data_path)
        by_type = evaluate(gt_keys, pred_keys)
        rows = print_report(by_type, f"Kết quả đánh giá — {name}")

        out_path = out_dir / f"evaluation_{name}.csv"
        pd.DataFrame(rows).to_csv(out_path, index=False)
        print(f"\nĐã lưu: {out_path}")


if __name__ == "__main__":
    main()
