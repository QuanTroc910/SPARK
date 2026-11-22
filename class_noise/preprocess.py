"""
PIPELINE CHUẨN BỊ DỮ LIỆU CHUNG cho Class Noise (mục 1 của "Kế hoạch cải tiến Class Noise").

Mục tiêu: trước khi chạy BẤT KỲ phương pháp nào (Single / Distance / Ensemble / bộ kết hợp), dữ liệu
đi qua cùng 1 bước làm sạch, và các bước này KHÔNG dùng cột nhãn để quyết định giữ/bỏ cột.
Lý do: nhãn chính là thứ đang nghi là sai -- nếu chọn cột dựa vào nhãn bẩn thì kết quả bị lệch
(đã đo: nhiễu kiểu A làm Random Forest + Elbow chỉ giữ 1 cột `Time`, F1 tụt mạnh).

Thứ tự các bước (hàm chính: `prepare_for_class_noise`):
  1. Chuẩn hoá cột nhãn (cắt khoảng trắng); bỏ dòng nhãn trống; báo lớp có ít dòng hơn số fold.
  2. Luật theo từng cột (không nhìn nhãn): bỏ cột toàn ô trống, cột chữ (chưa hỗ trợ), cột gần như
     toàn ô trống (mặc định > 50%), cột hằng, cột định danh (số nguyên có >= 95% giá trị khác nhau).
  3. Lọc tương quan |r| >= 0.8, chọn cột giữ KHÔNG dùng nhãn (ít ô trống -> ít tương quan hơn).
  4. (TUỲ CHỌN, mặc định TẮT) giảm số cột theo nhãn bằng Random Forest + điểm gãy -- đây là bước
     đầu thầy yêu cầu; chỉ chạy khi người dùng chọn "Giảm số cột", kèm cảnh báo khi nhãn chưa đủ
     tin cậy để chọn cột theo nhãn.
  5. Bỏ dòng còn ô trống ở các cột đã giữ, báo rõ số dòng.
  6. Gom dòng TRÙNG đặc trưng: nhóm cùng nhãn -> gộp 1 đại diện (kết quả sau này trả về cả nhóm);
     nhóm khác nhãn -> báo "dòng mâu thuẫn" (giữ nguyên các dòng này: đó là dấu hiệu nhãn sai, hoặc đặc trưng chưa đủ phân biệt).

Cố tình KHÔNG reset_index(): index gốc được giữ, để row_number (= index + 1) của các phương pháp
phía sau luôn khớp đúng dòng trong file gốc.
"""

from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.preprocessing import LabelEncoder

from attribute_noise.detectors import detect_duplicate_rows

from .feature_selection import filter_correlated, rank_by_importance, select_by_elbow


class PreprocessError(Exception):
    """Dữ liệu không dùng được cho Class Noise (vd không còn cột đặc trưng nào). app.py bắt để trả HTTP 400."""


@dataclass
class PreprocessConfig:
    label_column: str
    feature_columns: list[str]
    n_folds: int = 5                       # số fold sẽ dùng ở bước phát hiện (để cảnh báo lớp quá ít dòng)
    numeric_ratio: float = 0.9             # cột được coi là SỐ nếu >= 90% ô có giá trị ép được thành số
    max_blank_ratio: float = 0.5           # bỏ cột có hơn 50% ô trống
    identifier_unique_ratio: float = 0.95  # cột số nguyên có >= 95% giá trị khác nhau -> coi là mã định danh
    identifier_min_rows: int = 30          # dưới số dòng này không xét "định danh" (file quá nhỏ thì tỉ lệ vô nghĩa)
    correlation_threshold: float = 0.8
    correlation_method: str = "pearson"    # hoặc "spearman"
    reduce_by_label: bool = False          # giảm cột theo NHÃN: mặc định KHÔNG
    n_estimators: int = 100                # số cây cho Random Forest ở bước giảm cột theo nhãn
    low_margin_warning: float = 0.2        # cảnh báo nếu "mức vượt mốc" của mô hình < 20% (ngưỡng tạm, chưa chốt)
    min_minority_rows: int = 50            # cảnh báo nếu lớp hiếm có ít hơn ngần này dòng
    group_duplicates: bool = True
    max_listed_rows: int = 1000            # tối đa số dòng/nhóm liệt kê trong báo cáo (tránh response quá to)
    random_state: int = 42


@dataclass
class DroppedColumn:
    column: str
    reason: str   # all_blank | not_numeric | mostly_blank | constant | identifier | correlated | label_reduction
    detail: str   # câu tiếng Việt giải thích để hiện cho người dùng


@dataclass
class ConflictGroup:
    rows: list[int]            # row_number (1-based) của các dòng cùng đặc trưng
    labels: dict[str, int]     # nhãn -> số dòng mang nhãn đó trong nhóm


@dataclass
class PreprocessReport:
    n_rows_input: int = 0
    n_rows_blank_label: int = 0
    n_rows_blank_feature: int = 0
    blank_feature_rows: list[int] = field(default_factory=list)   # row_number (cắt ở max_listed_rows)
    n_rows_after_cleaning: int = 0        # sau khi bỏ dòng nhãn trống / ô trống
    n_rows_merged_away: int = 0           # số dòng bị gộp vào đại diện (nhóm trùng cùng nhãn)
    n_duplicate_groups_merged: int = 0
    n_rows_final: int = 0                 # số dòng đưa vào thuật toán
    dropped_columns: list[DroppedColumn] = field(default_factory=list)
    kept_columns: list[str] = field(default_factory=list)
    small_classes: list[dict] = field(default_factory=list)       # [{"label", "count"}]
    conflict_groups: list[ConflictGroup] = field(default_factory=list)
    n_conflict_groups: int = 0
    n_conflict_rows: int = 0
    label_reduction: dict | None = None   # kết quả bước giảm cột theo nhãn (None = không chạy)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PreparedData:
    df: pd.DataFrame                  # chỉ gồm cột nhãn (chuỗi đã chuẩn hoá) + các cột đặc trưng (số thực), index gốc
    label_column: str
    feature_columns: list[str]
    groups: dict[int, list[int]]      # index đại diện -> mọi index (gốc) cùng nhóm; CHỈ nhóm có > 1 dòng
    report: PreprocessReport

    def expand_row_numbers(self, row_numbers) -> list[int]:
        """Từ danh sách row_number (1-based) của các dòng ĐẠI DIỆN, thêm các dòng cùng nhóm trùng
        đã bị gộp -> trả về danh sách đầy đủ, sắp tăng dần, không lặp."""
        out: set[int] = set()
        for rn in row_numbers:
            out.add(int(rn))
            for member in self.groups.get(int(rn) - 1, []):
                out.add(int(member) + 1)
        return sorted(out)


# --------------------------------------------------------------------------------------
# Bước 2: luật theo từng cột
# --------------------------------------------------------------------------------------
def _column_problem(raw: pd.Series, cfg: PreprocessConfig) -> tuple[str, str] | None:
    """Trả (mã lý do, câu giải thích) nếu cột nên bỏ, ngược lại None. Không dùng nhãn."""
    text = raw.astype("string").str.strip()
    present = raw.notna() & (text != "")          # ô có nội dung (kể cả chữ)
    numeric = pd.to_numeric(raw, errors="coerce")
    usable = numeric.notna()
    n, n_present, n_usable = len(raw), int(present.sum()), int(usable.sum())

    if n_present == 0:
        return "all_blank", "toàn bộ ô trống"
    if n_usable / n_present < cfg.numeric_ratio:
        return "not_numeric", "cột chữ (chưa hỗ trợ), chỉ nhận cột số"
    blank_ratio = 1 - n_usable / n
    if blank_ratio > cfg.max_blank_ratio:
        return "mostly_blank", f"{blank_ratio:.0%} ô trống (quá nhiều, ngưỡng {cfg.max_blank_ratio:.0%})"
    values = numeric[usable]
    n_unique = int(values.nunique())
    if n_unique <= 1:
        return "constant", "mọi ô có cùng 1 giá trị (cột hằng, không giúp phân biệt gì)"
    # Cột định danh: chỉ xét cột SỐ NGUYÊN (cột số thực như Amount có nhiều giá trị khác nhau là bình thường).
    is_integer_valued = bool(np.all(values.to_numpy() == np.floor(values.to_numpy())))
    if is_integer_valued and len(values) >= cfg.identifier_min_rows:
        unique_ratio = n_unique / len(values)
        if unique_ratio >= cfg.identifier_unique_ratio:
            return "identifier", f"giống mã định danh ({unique_ratio:.0%} giá trị khác nhau)"
    return None


# --------------------------------------------------------------------------------------
# Bước 4 (tuỳ chọn): giảm cột theo nhãn + cảnh báo độ tin cậy
# --------------------------------------------------------------------------------------
def _margin_over_baseline(num: pd.DataFrame, labels: pd.Series, cfg: PreprocessConfig) -> float | None:
    """"Mức vượt mốc" = (độ chính xác CV - độ chính xác đoán toàn lớp đông nhất) / (1 - cùng mốc đó).
    0 = chỉ ngang đoán bừa, 1 = đạt mức tối đa. None nếu không tính được (1 lớp duy nhất, lớp quá ít dòng)."""
    counts = labels.value_counts()
    baseline = counts.iloc[0] / counts.sum()
    n_splits = int(min(3, counts.min()))
    if baseline >= 1 or n_splits < 2:
        return None
    model = RandomForestClassifier(
        n_estimators=cfg.n_estimators, class_weight="balanced", random_state=cfg.random_state, n_jobs=-1
    )
    # Mã hoá nhãn thành số TRƯỚC khi đưa vào: scikit-learn 1.9 báo lỗi "classes ... are not in class_weight"
    # khi nhãn là chuỗi mà vẫn bật class_weight="balanced" trong cross_val_predict.
    y = LabelEncoder().fit_transform(labels.to_numpy())
    pred = cross_val_predict(
        model, num.to_numpy(), y,
        cv=StratifiedKFold(n_splits, shuffle=True, random_state=cfg.random_state),
    )
    accuracy = float((pred == y).mean())
    return (accuracy - baseline) / (1 - baseline)


def _reduce_by_label(num: pd.DataFrame, labels: pd.Series, columns: list[str], cfg: PreprocessConfig):
    """Random Forest xếp hạng cột theo NHÃN rồi cắt ở điểm gãy (đúng bước 1 thầy yêu cầu).
    Trả (cột giữ lại, thông tin để hiện, danh sách cảnh báo)."""
    tmp = num[columns].copy()
    tmp[cfg.label_column] = labels.to_numpy()
    tmp = tmp.dropna(subset=columns)               # rank_by_importance cần dòng đủ mọi cột
    lab = tmp[cfg.label_column]
    ranking = rank_by_importance(tmp, cfg.label_column, columns, n_estimators=cfg.n_estimators,
                                 random_state=cfg.random_state)
    kept = select_by_elbow(ranking)

    warnings: list[str] = []
    minority_rows = int(lab.value_counts().min())
    margin = _margin_over_baseline(tmp[columns], lab, cfg)
    if minority_rows < cfg.min_minority_rows:
        warnings.append(
            f"Lớp hiếm chỉ có {minority_rows} dòng (< {cfg.min_minority_rows}): nhãn có thể chưa đủ tin cậy "
            "để chọn cột theo nhãn."
        )
    if margin is not None and margin < cfg.low_margin_warning:
        warnings.append(
            f"Mô hình chỉ vượt mốc đoán bừa {max(margin, 0):.0%} (< {cfg.low_margin_warning:.0%}): nhãn có thể "
            "chưa đủ tin cậy để chọn cột theo nhãn."
        )
    info = {
        "applied": True,
        "ranking": [{"column": r.column, "importance": float(r.importance)} for r in ranking],
        "kept": kept,
        "margin": None if margin is None else float(margin),
        "minority_rows": minority_rows,
    }
    return kept, info, warnings


# --------------------------------------------------------------------------------------
# Hàm chính
# --------------------------------------------------------------------------------------
def prepare_for_class_noise(df: pd.DataFrame, config: PreprocessConfig) -> PreparedData:
    missing = [c for c in [config.label_column, *config.feature_columns] if c not in df.columns]
    if missing:
        raise PreprocessError(f"Không có cột trong dữ liệu: {', '.join(missing)}")
    if config.label_column in config.feature_columns:
        raise PreprocessError("Cột nhãn không được nằm trong danh sách cột đặc trưng.")

    report = PreprocessReport(n_rows_input=len(df))

    # --- Bước 1: chuẩn hoá nhãn, bỏ dòng nhãn trống ---
    labels = df[config.label_column].astype("string").str.strip()
    blank_label = labels.isna() | (labels == "")
    report.n_rows_blank_label = int(blank_label.sum())
    if report.n_rows_blank_label:
        report.warnings.append(f"Đã bỏ {report.n_rows_blank_label} dòng có nhãn trống.")
    work = df.loc[~blank_label]
    labels = labels.loc[~blank_label].astype(str)
    if labels.nunique() < 2:
        raise PreprocessError("Cột nhãn chỉ có 1 giá trị (hoặc rỗng), không thể tìm nhãn sai.")

    counts = labels.value_counts()
    for lab, c in counts.items():
        if c < config.n_folds:
            report.small_classes.append({"label": str(lab), "count": int(c)})
    if report.small_classes:
        names = ", ".join(f"'{s['label']}' ({s['count']} dòng)" for s in report.small_classes)
        report.warnings.append(
            f"Lớp có ít dòng hơn số fold ({config.n_folds}): {names}. Phương pháp dùng chia fold có thể báo lỗi hoặc kém tin cậy."
        )

    # --- Bước 2: luật theo từng cột (không nhìn nhãn) ---
    columns: list[str] = []
    for col in config.feature_columns:
        problem = _column_problem(work[col], config)
        if problem:
            report.dropped_columns.append(DroppedColumn(col, problem[0], problem[1]))
        else:
            columns.append(col)
    if not columns:
        reasons = "; ".join(f"{d.column}: {d.detail}" for d in report.dropped_columns)
        raise PreprocessError(f"Không còn cột đặc trưng nào dùng được. Lý do từng cột: {reasons}")

    num = work[columns].apply(pd.to_numeric, errors="coerce").astype(float)

    # --- Bước 3: lọc tương quan, KHÔNG dùng nhãn ---
    if len(columns) > 1:
        columns, corr_dropped = filter_correlated(
            num, columns, threshold=config.correlation_threshold, prioritized=False,
            method=config.correlation_method, return_report=True,
        )
        for d in corr_dropped:
            report.dropped_columns.append(DroppedColumn(
                d["column"], "correlated",
                f"trùng thông tin với cột '{d['kept_column']}' (|r| = {d['correlation']:.2f})",
            ))

    # --- Bước 4 (tuỳ chọn): giảm cột theo nhãn ---
    if config.reduce_by_label and len(columns) > 1:
        kept, info, warns = _reduce_by_label(num, labels, columns, config)
        for c in columns:
            if c not in kept:
                report.dropped_columns.append(DroppedColumn(
                    c, "label_reduction", "xếp hạng thấp theo mức liên quan tới nhãn (Random Forest, trước điểm gãy)"))
        columns = [c for c in columns if c in kept]
        report.label_reduction = info
        report.warnings.extend(warns)

    # --- Bước 5: bỏ dòng còn ô trống ở các cột đã giữ ---
    blank_feature = num[columns].isna().any(axis=1)
    report.n_rows_blank_feature = int(blank_feature.sum())
    if report.n_rows_blank_feature:
        report.blank_feature_rows = [int(i) + 1 for i in num.index[blank_feature][: config.max_listed_rows]]
        report.warnings.append(
            f"Đã bỏ {report.n_rows_blank_feature} dòng có ô trống ở các cột đặc trưng được giữ."
        )
    num = num.loc[~blank_feature, columns]
    labels = labels.loc[num.index]
    report.n_rows_after_cleaning = len(num)

    # --- Bước 6: gom dòng trùng đặc trưng ---
    groups: dict[int, list[int]] = {}
    drop_index: list = []
    if config.group_duplicates and len(num) > 1:
        dup_mask = detect_duplicate_rows(num)         # keep=False: mọi dòng thuộc nhóm trùng
        candidates = num.index[dup_mask.to_numpy()]
        if len(candidates):
            group_id = num.loc[candidates].groupby(list(columns), sort=False, dropna=False).ngroup()
            for _, members in group_id.groupby(group_id):
                idx = list(members.index)
                label_counts = labels.loc[idx].value_counts()
                if len(label_counts) > 1:
                    # khác nhãn: BÁO, giữ nguyên cả nhóm (nhãn sai, hoặc đặc trưng chưa đủ phân biệt -- không kết luận chắc)
                    report.n_conflict_groups += 1
                    report.n_conflict_rows += len(idx)
                    if len(report.conflict_groups) < config.max_listed_rows:
                        report.conflict_groups.append(ConflictGroup(
                            rows=[int(i) + 1 for i in idx],
                            labels={str(k): int(v) for k, v in label_counts.items()},
                        ))
                else:
                    rep = idx[0]                       # đại diện = dòng có index nhỏ nhất
                    groups[int(rep)] = [int(i) for i in idx]
                    drop_index.extend(idx[1:])
        report.n_duplicate_groups_merged = len(groups)
        report.n_rows_merged_away = len(drop_index)
        if drop_index:
            report.warnings.append(
                f"Đã gộp {report.n_rows_merged_away} dòng trùng đặc trưng và cùng nhãn vào {len(groups)} dòng đại diện."
            )
        if report.n_conflict_groups:
            report.warnings.append(
                f"Có {report.n_conflict_groups} nhóm dòng cùng đặc trưng nhưng KHÁC nhãn "
                f"({report.n_conflict_rows} dòng): trong mỗi nhóm ít nhất 1 nhãn sai, hoặc các cột đặc trưng "
                "đang giữ chưa đủ để phân biệt các dòng đó."
            )
        if drop_index:
            num = num.drop(index=drop_index)
            labels = labels.drop(index=drop_index)

    out = num.copy()
    out[config.label_column] = labels
    out = out[[config.label_column, *columns]]
    report.kept_columns = list(columns)
    report.n_rows_final = len(out)
    return PreparedData(df=out, label_column=config.label_column, feature_columns=list(columns),
                        groups=groups, report=report)
