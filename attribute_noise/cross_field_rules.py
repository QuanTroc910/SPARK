"""Detect mâu thuẫn LOGIC giữa 2 cột -- khác hẳn detectors.py vì các hàm ở đó
chỉ nhìn 1 cột riêng lẻ (hoặc so khớp y hệt cả dòng với duplicate_row), còn
ở đây cần hiểu QUAN HỆ giữa 2 cột cụ thể.

Đây LUÔN LÀ RULE DO NGƯỜI DÙNG TỰ KHAI (xem CLAUDE.md mục 7) -- hệ thống
không tự suy ra được quan hệ giữa 2 cột bất kỳ chỉ từ dữ liệu, vì đó là domain
knowledge riêng của từng file, không phổ quát như dtype.

4 loại rule (CrossFieldRuleConfig.rule_type quyết định dùng hàm nào, xem
registry CROSS_FIELD_RULE_DETECTORS ở cuối file):
  1. COMPARE                -> detect_compare_rule
  2. CONDITIONAL (NẾU...THÌ...) -> detect_conditional_rule
  3. FORMULA                 -> detect_formula_rule
  4. FUNCTIONAL_DEPENDENCY   -> detect_functional_dependency_rule

Mỗi hàm nhận (df, cfg), trả về 1 Series bool CÙNG INDEX với df: True = dòng
đó VI PHẠM rule (bị coi là noise). Ô nào không so sánh được (vd 1 trong 2 cột
liên quan đang bị missing/format_noise, ép kiểu thất bại) thì KHÔNG kết luận
gì cả (không tính là vi phạm) -- tương tự cách detect_out_of_range/detect_outlier
trong detectors.py dùng numeric.notna() để tự bỏ qua ô không ép được thành số.
"""

import ast
import operator
from typing import Any, Optional

import pandas as pd

from .config import DEFAULT_MISSING_PLACEHOLDERS, CompareOperator, CrossFieldRuleConfig, RuleType, RuleValueType
from .expression_rules import (
    detect_expression_rule,
    detect_if_then_rule,
    expression_column_names,
    expression_columns,
    if_then_column_names,
    if_then_columns,
)

# Ánh xạ CompareOperator (enum) -> hàm so sánh thật của module operator chuẩn.
_COMPARE_FUNCS = {
    CompareOperator.LT: operator.lt,
    CompareOperator.LTE: operator.le,
    CompareOperator.GT: operator.gt,
    CompareOperator.GTE: operator.ge,
    CompareOperator.EQ: operator.eq,
    CompareOperator.NEQ: operator.ne,
}


def _is_missing_text(text: str) -> bool:
    normalized = text.strip().lower()
    return normalized in [p.lower() for p in DEFAULT_MISSING_PLACEHOLDERS]


def _parsed_numeric(series: pd.Series) -> pd.Series:
    """Ép 1 Series (toàn string) về số thực; ô không ép được -> NaN (tự động
    bị loại khỏi so sánh ở nơi gọi, không báo lỗi ở đây)."""
    return pd.to_numeric(series.astype(str).str.strip(), errors="coerce")


def _parsed_date(series: pd.Series, date_format: Optional[str]) -> pd.Series:
    """Ép 1 Series về datetime theo date_format; ô không ép được -> NaT."""
    fmt = date_format or "%Y-%m-%d"
    return pd.to_datetime(series.astype(str).str.strip(), format=fmt, errors="coerce")


def _cast_series(series: pd.Series, value_type: RuleValueType, date_format: Optional[str]) -> pd.Series:
    """Ép cả 1 cột về đúng kiểu cần so sánh, theo value_type người dùng khai."""
    if value_type == RuleValueType.NUMBER:
        return _parsed_numeric(series)
    if value_type == RuleValueType.DATE:
        return _parsed_date(series, date_format)
    return series.astype(str).str.strip()  # TEXT: chỉ chuẩn hoá khoảng trắng thừa


def _cast_literal(value: str, value_type: RuleValueType, date_format: Optional[str]) -> Any:
    """Ép 1 giá trị literal (người dùng nhập tay trên UI, vd '18') về đúng
    kiểu để so sánh công bằng với giá trị lấy ra từ cột."""
    if value_type == RuleValueType.NUMBER:
        return float(value)
    if value_type == RuleValueType.DATE:
        return pd.to_datetime(value, format=date_format or "%Y-%m-%d")
    return str(value).strip()


# ---------------------------------------------------------------------------
# 1. COMPARE: "column_a operator column_b"
# ---------------------------------------------------------------------------
def detect_compare_rule(df: pd.DataFrame, cfg: CrossFieldRuleConfig) -> pd.Series:
    if cfg.column_a not in df.columns or cfg.column_b not in df.columns:
        return pd.Series(False, index=df.index)

    left = _cast_series(df[cfg.column_a], cfg.value_type, cfg.date_format)
    right = _cast_series(df[cfg.column_b], cfg.value_type, cfg.date_format)

    both_parsed = left.notna() & right.notna()
    compare_func = _COMPARE_FUNCS[cfg.operator]
    rule_holds = compare_func(left, right)  # True = rule ĐÚNG (không phải noise)

    # Vi phạm = 2 vế ĐỀU ép kiểu được (so sánh được thật) NHƯNG rule sai.
    # Ô không ép kiểu được thì bỏ qua (thuộc trách nhiệm missing/format_noise).
    return both_parsed & ~rule_holds


# ---------------------------------------------------------------------------
# 2. CONDITIONAL: "NẾU if_column if_operator if_value THÌ then_column then_operator then_value"
# ---------------------------------------------------------------------------
def _eval_condition(
    series: pd.Series, op: CompareOperator, literal: str, value_type: RuleValueType, date_format: Optional[str]
) -> tuple[pd.Series, pd.Series]:
    """Trả về (mask_parsed_được, mask_điều_kiện_đúng) cho 1 vế NẾU hoặc THÌ."""
    casted_series = _cast_series(series, value_type, date_format)
    casted_literal = _cast_literal(literal, value_type, date_format)
    parsed = casted_series.notna()
    holds = _COMPARE_FUNCS[op](casted_series, casted_literal)
    return parsed, holds


def detect_conditional_rule(df: pd.DataFrame, cfg: CrossFieldRuleConfig) -> pd.Series:
    if cfg.if_column not in df.columns or cfg.then_column not in df.columns:
        return pd.Series(False, index=df.index)

    if_parsed, if_holds = _eval_condition(
        df[cfg.if_column], cfg.if_operator, cfg.if_value, cfg.if_value_type, cfg.date_format
    )
    then_parsed, then_holds = _eval_condition(
        df[cfg.then_column], cfg.then_operator, cfg.then_value, cfg.then_value_type, cfg.date_format
    )

    # Rule chỉ ÁP DỤNG cho các dòng thoả điều kiện "NẾU" (if_parsed & if_holds).
    # Trong nhóm đó, dòng nào "THÌ" không ép kiểu được thì bỏ qua (N/A, không
    # kết luận), còn lại: vi phạm khi "THÌ" ép kiểu được nhưng điều kiện sai.
    applies = if_parsed & if_holds
    return applies & then_parsed & ~then_holds


# ---------------------------------------------------------------------------
# 3. FORMULA: 1 biểu thức so sánh, vd "thanh_tien == so_luong * don_gia"
# ---------------------------------------------------------------------------
# CHỈ diễn giải đúng những node cú pháp liệt kê dưới đây -- KHÔNG dùng
# eval()/exec() của Python (2 hàm đó chạy được MỌI code Python, là lỗ hổng
# command injection nghiêm trọng nếu formula lấy trực tiếp từ input người
# dùng). Đây là 1 "máy diễn giải" tối giản, tự viết tay, chỉ hiểu +,-,*,/,
# so sánh, số, và tên cột -- không thể làm gì khác ngoài tính toán số học.
_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
_COMPARE_NODE_OPS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}


class FormulaError(ValueError):
    """Formula chứa cú pháp không được phép, hoặc tham chiếu cột không tồn tại."""


def _extract_column_names(expr: str) -> set[str]:
    """Lấy ra danh sách TÊN CỘT được nhắc tới trong formula (mọi ast.Name)."""
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise FormulaError(f"Formula sai cú pháp: {exc}") from exc
    return {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}


def _safe_eval_node(node: ast.AST, row_values: dict[str, float]) -> float:
    """Tính giá trị số của 1 node cú pháp -- chỉ đi qua các case được cho
    phép ở trên, gặp bất kỳ cú pháp lạ nào khác (gọi hàm, import, string...)
    đều raise FormulaError, KHÔNG âm thầm bỏ qua."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        raise FormulaError("Formula chỉ được chứa số, không được chứa chuỗi/khác")
    if isinstance(node, ast.Name):
        if node.id not in row_values:
            raise FormulaError(f"Cột '{node.id}' không tồn tại trong file")
        return row_values[node.id]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_safe_eval_node(node.operand, row_values)
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        left = _safe_eval_node(node.left, row_values)
        right = _safe_eval_node(node.right, row_values)
        return _BIN_OPS[type(node.op)](left, right)
    raise FormulaError("Formula chứa cú pháp không được phép (chỉ cho +, -, *, / và tên cột)")


def _parse_formula(expr: str) -> tuple[ast.AST, type, ast.AST]:
    """Parse formula thành (node_vế_trái, loại_phép_so_sánh, node_vế_phải) --
    yêu cầu formula phải có ĐÚNG 1 phép so sánh ở ngoài cùng (vd 'a == b*c'),
    để biết rõ 'vế trái'/'vế phải' khi cần báo cho người dùng."""
    try:
        tree = ast.parse(expr, mode="eval").body
    except SyntaxError as exc:
        raise FormulaError(f"Formula sai cú pháp: {exc}") from exc
    if not isinstance(tree, ast.Compare) or len(tree.ops) != 1 or type(tree.ops[0]) not in _COMPARE_NODE_OPS:
        raise FormulaError(
            "Formula phải có đúng 1 phép so sánh ở ngoài cùng, vd 'a == b*c' hoặc 'a <= b+c'"
        )
    return tree.left, type(tree.ops[0]), tree.comparators[0]


def detect_formula_rule(df: pd.DataFrame, cfg: CrossFieldRuleConfig) -> pd.Series:
    left_node, op_type, right_node = _parse_formula(cfg.formula)

    # Formula là text tự do nên dễ gõ sai tên cột hơn hẳn so với chọn cột qua
    # dropdown (như 3 rule khác) -- báo lỗi rõ ràng ở đây thay vì lặng lẽ trả
    # "không vi phạm" (dễ khiến người dùng lầm tưởng dữ liệu sạch).
    referenced_columns = _extract_column_names(cfg.formula)
    unknown_columns = referenced_columns - set(df.columns)
    if unknown_columns:
        raise FormulaError(f"Formula tham chiếu cột không tồn tại: {', '.join(sorted(unknown_columns))}")

    numeric_cols = {col: _parsed_numeric(df[col]) for col in referenced_columns}

    violations = pd.Series(False, index=df.index)
    for row_index in df.index:
        row_values = {col: numeric_cols[col].loc[row_index] for col in referenced_columns}
        if any(pd.isna(v) for v in row_values.values()):
            continue  # 1 trong các cột liên quan không ép được thành số -> N/A

        left = _safe_eval_node(left_node, row_values)
        right = _safe_eval_node(right_node, row_values)

        if op_type is ast.Eq:
            rule_holds = abs(left - right) <= cfg.tolerance  # cho phép sai số rounding
        elif op_type is ast.NotEq:
            rule_holds = abs(left - right) > cfg.tolerance
        else:
            rule_holds = _COMPARE_NODE_OPS[op_type](left, right)

        if not rule_holds:
            violations.loc[row_index] = True

    return violations


# ---------------------------------------------------------------------------
# 4. FUNCTIONAL_DEPENDENCY: "determinant_column xác định dependent_column" (1 chiều)
# ---------------------------------------------------------------------------
def _normalize_text_series(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower()


_MISSING_SET = {p.lower() for p in DEFAULT_MISSING_PLACEHOLDERS}  # cùng định nghĩa "thiếu" với _is_missing_text, dùng cho cả bảng 1 lượt


def _fd_working_frame(df: pd.DataFrame, cfg: CrossFieldRuleConfig) -> tuple[pd.DataFrame, pd.Series]:
    """Phần gom nhóm DÙNG CHUNG cho detect và analyze (để 2 hàm luôn khớp nhau về dòng nào bị gắn cờ).
    Trả (working, violated): working = bảng 2 cột đã chuẩn hoá ("det", "dep") của các dòng KHÔNG thiếu ở cả 2 cột (giữ index gốc);
    violated = Series bool cùng index với working, True nếu nhóm của dòng đó (cùng det) có > 1 giá trị dep khác nhau."""
    det_normalized = _normalize_text_series(df[cfg.determinant_column])
    dep_normalized = _normalize_text_series(df[cfg.dependent_column])

    # Bỏ qua dòng có ô "thiếu" ở 1 trong 2 cột -- thuộc trách nhiệm của
    # missing_value, không nên bị FD kết luận vi phạm thêm lần 2.
    # .astype(bool): bảng rỗng (0 dòng) thì .apply() trả mảng không phải bool và phép | báo lỗi; ép kiểu để bảng rỗng chạy bình thường.
    is_missing = det_normalized.apply(_is_missing_text).astype(bool) | dep_normalized.apply(_is_missing_text).astype(bool)

    working = pd.DataFrame({"det": det_normalized, "dep": dep_normalized})
    working = working[~is_missing]

    # groupby determinant -> đếm số giá trị KHÁC NHAU của dependent trong nhóm. transform("nunique") chép con số của nhóm
    # về TỪNG DÒNG gốc (giữ index) nên lọc được ra các dòng thuộc nhóm có > 1 giá trị.
    nunique_per_group = working.groupby("det")["dep"].transform("nunique")
    return working, nunique_per_group > 1


def detect_functional_dependency_rule(df: pd.DataFrame, cfg: CrossFieldRuleConfig) -> pd.Series:
    det_col, dep_col = cfg.determinant_column, cfg.dependent_column
    if det_col not in df.columns or dep_col not in df.columns:
        return pd.Series(False, index=df.index)

    # Chuẩn hoá (strip + lowercase) trước khi so sánh -- tránh báo trùng với
    # whitespace_noise/inconsistent_category đã có (vd "Nguyen A" và
    # "nguyen a " không nên bị coi là 2 giá trị KHÁC NHAU ở check này).
    working, violated = _fd_working_frame(df, cfg)

    # nunique > 1 nghĩa là cùng 1 determinant nhưng ra >1 dependent khác nhau -> vi phạm (đánh dấu HẾT các dòng trong nhóm
    # đó, giống cách duplicate_row đánh dấu cả 2 bản trùng để người dùng tự xem và quyết định bản nào đúng).
    # Muốn biết Ô NÀO trong nhóm nhiều khả năng sai thì dùng analyze_functional_dependency() bên dưới.
    return pd.Series(df.index.isin(working.index[violated]), index=df.index)


# Ngưỡng của analyze_functional_dependency(): tỉ lệ cột còn lại mà các dòng trong nhóm mâu thuẫn GIỐNG NHAU.
FD_SAME_ENTITY_RATIO = 0.5    # >= : coi là cùng 1 đối tượng -> ô sai là cột PHỤ THUỘC (B);  < : khác đối tượng -> ô sai là cột XÁC ĐỊNH (A)
FD_STABLE_COLUMN_RATIO = 0.5  # cột còn lại chỉ được dùng làm bằng chứng nếu ở các nhóm KHÔNG vi phạm nó thường giống nhau từ ít nhất ngần này


def _short(value: Any, limit: int = 30) -> str:
    text = str(value).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def analyze_functional_dependency(df: pd.DataFrame, cfg: CrossFieldRuleConfig) -> dict:
    """Với mỗi nhóm vi phạm (cùng A, nhiều giá trị B khác nhau), ĐOÁN ô nào nhiều khả năng sai. Chỉ là gợi ý, KHÔNG đổi kết quả detect
    (cùng tập dòng với detect_functional_dependency_rule vì dùng chung _fd_working_frame).

    Quy tắc phụ thuộc hàm tự nó không biết ô nào sai (cả nhóm mâu thuẫn, chưa rõ lỗi ở B hay ở chính A). Ta so thêm CÁC CỘT CÒN LẠI của
    các dòng trong nhóm:
      - Các cột còn lại phần lớn GIỐNG nhau (>= FD_SAME_ENTITY_RATIO) -> cùng 1 đối tượng, A đúng, ô sai là B. Trong B, giá trị xuất hiện
        nhiều nhất là "mốc đúng", các giá trị lệch là nghi sai; hoà số lượng (vd 1 dòng "An", 1 dòng "Ân") thì chưa rõ giá trị nào đúng.
      - Các cột còn lại phần lớn KHÁC nhau -> nhiều khả năng là các đối tượng khác nhau dùng chung A (vd 2 nhân viên cùng mã): ô sai là A,
        nhưng KHÔNG suy ra được dòng nào (dữ liệu không nói).
      - Không có cột nào so được -> chưa xác định.
    Chỉ dùng làm bằng chứng những cột "ổn định": cột mà ở các nhóm không vi phạm vẫn thường giống nhau. Bảng chấm công/lương có cột
    lương, tháng khác nhau giữa các dòng của cùng 1 nhân viên là bình thường -> không được tính "khác nhau" là bằng chứng khác đối tượng.

    Trả {"rows": {row_index: {"flagged": set tên cột nghi sai, "ref": set cột mốc so sánh, "hint": [câu ngắn], "notes": [câu giải thích]}},
         "groups": [{"key": giá trị A, "column": cột phụ thuộc, "verdict": "dependent" | "determinant" | "unknown", "rows": [row_index...],
                     "majority_value": giá trị B đa số (chuỗi đầy đủ) hoặc None, "suspect_rows": [row_index dòng lệch số đông]}]}.
    majority_value / suspect_rows chỉ có nghĩa khi kết luận "dependent" VÀ có giá trị đa số rõ ràng (không hoà): đó là nhóm "xác định được" mà
    cách xử lý "sửa về giá trị phổ biến nhất" / "chỉ xoá dòng nghi sai" dựa vào. Các nhóm còn lại (hoà, nghi sai A, chưa xác định) để None / []."""
    det_col, dep_col = cfg.determinant_column, cfg.dependent_column
    empty: dict = {"rows": {}, "groups": []}
    if det_col not in df.columns or dep_col not in df.columns:
        return empty
    working, violated = _fd_working_frame(df, cfg)
    if not violated.any():
        return empty

    # Nhóm chỉ 1 dòng không thể vi phạm cũng không cho bằng chứng gì -> chỉ giữ các dòng thuộc nhóm có >= 2 dòng (đỡ chuẩn hoá cả bảng).
    group_size = working.groupby("det")["dep"].transform("size")
    multi = working[group_size >= 2]
    multi_violated = violated.loc[multi.index]
    other_cols = [c for c in df.columns if c not in (det_col, dep_col)]
    other = df.loc[multi.index, other_cols].astype(str).apply(_normalize_text_series)
    other = other.mask(other.isin(_MISSING_SET))  # ô thiếu -> NaN: không so sánh được, không tính là giống hay khác

    # Cột nào đủ "ổn định" để làm bằng chứng: xét ở các nhóm KHÔNG vi phạm (>= 2 dòng, cột có >= 2 ô đọc được).
    stable = pd.Series(True, index=other_cols)
    ok_rows = multi.index[~multi_violated]
    if len(ok_rows) and other_cols:
        sub, keys = other.loc[ok_rows], multi.loc[ok_rows, "det"]
        comparable = sub.groupby(keys).count() >= 2
        consistent = (sub.groupby(keys).nunique() <= 1) & comparable
        denominator = comparable.sum()
        ratio = consistent.sum() / denominator.where(denominator > 0)  # chưa có nhóm nào so được -> NaN -> coi là ổn định (không có bằng chứng ngược)
        stable = ~(ratio < FD_STABLE_COLUMN_RATIO)
    reference_cols = [c for c in other_cols if bool(stable[c])]

    vio = multi[multi_violated]
    compared = agree = pd.Series(dtype=int)
    if reference_cols:
        sv, kv = other.loc[vio.index, reference_cols], vio["det"]
        comparable_v = sv.groupby(kv).count() >= 2
        compared = comparable_v.sum(axis=1)
        agree = ((sv.groupby(kv).nunique() <= 1) & comparable_v).sum(axis=1)

    rows: dict = {}
    groups: list = []

    def put(row_index, flagged: set, ref: set, hint: str, note: str) -> None:
        info = rows.setdefault(row_index, {"flagged": set(), "ref": set(), "hint": [], "notes": []})
        info["flagged"] |= flagged
        info["ref"] |= ref
        info["hint"].append(hint)
        info["notes"].append(note)

    for key, group in vio.groupby("det"):
        n_compared, n_agree = int(compared.get(key, 0)), int(agree.get(key, 0))
        indices = list(group.index)
        a_text = _short(df.at[indices[0], det_col])
        counts = group["dep"].value_counts()
        if n_compared == 0:
            verdict = "unknown"
        elif n_agree / n_compared >= FD_SAME_ENTITY_RATIO:
            verdict = "dependent"
        else:
            verdict = "determinant"
        group_info = {"key": a_text, "column": dep_col, "verdict": verdict, "rows": indices, "majority_value": None, "suspect_rows": []}
        groups.append(group_info)

        if verdict == "determinant":
            # Các dòng khác nhau ở phần lớn cột khác -> nhiều khả năng là các đối tượng khác nhau dùng chung A. Không biết dòng nào sai:
            # tô A ở mọi dòng của nhóm, B chỉ là mốc để thấy các dòng khác nhau.
            note = (f"Nghi sai ô «{det_col}»: các dòng có «{det_col}» = «{a_text}» khác nhau ở {n_compared - n_agree}/{n_compared} cột còn lại "
                    f"nên có vẻ là các đối tượng khác nhau dùng chung «{det_col}». Chưa xác định dòng nào sai.")
            for row_index in indices:
                put(row_index, {det_col}, {dep_col}, f"Nghi sai {det_col} (chưa rõ dòng nào)", note)
        elif verdict == "unknown":
            note = f"«{det_col}» = «{a_text}» đi với {len(counts)} giá trị «{dep_col}» khác nhau, nhưng không có cột nào khác để so sánh nên chưa xác định ô sai."
            for row_index in indices:
                put(row_index, {det_col, dep_col}, set(), f"Chưa rõ {det_col}/{dep_col}", note)
        else:
            same_text = f"{n_agree}/{n_compared} cột còn lại giống nhau nên có vẻ cùng một đối tượng."
            has_majority = counts.iloc[0] > counts.iloc[1]  # counts đã xếp giảm dần và nhóm vi phạm luôn có >= 2 giá trị
            if not has_majority:
                note = f"«{dep_col}» có {len(counts)} giá trị khác nhau với số lượng ngang nhau nên chưa xác định giá trị nào đúng; {same_text}"
                for row_index in indices:
                    put(row_index, {dep_col}, {det_col}, f"Chưa rõ {dep_col}", note)
            else:
                majority = counts.index[0]
                majority_row = next(i for i in indices if group.at[i, "dep"] == majority)
                majority_text = _short(df.at[majority_row, dep_col])
                group_info["majority_value"] = str(df.at[majority_row, dep_col]).strip()  # giá trị thật sẽ ghi vào ô (cắt khoảng trắng thừa, không rút gọn)
                group_info["suspect_rows"] = [i for i in indices if group.at[i, "dep"] != majority]
                for row_index in indices:
                    value = group.at[row_index, "dep"]
                    if value == majority:
                        put(row_index, set(), {dep_col, det_col}, f"Mốc đúng {dep_col}",
                            f"Giá trị phổ biến của «{dep_col}» khi «{det_col}» = «{a_text}»: «{majority_text}» ({counts.iloc[0]}/{len(indices)} dòng).")
                    else:
                        put(row_index, {dep_col}, {det_col}, f"Nghi sai {dep_col}",
                            f"Nghi sai ô «{dep_col}»: «{_short(df.at[row_index, dep_col])}» lệch giá trị phổ biến «{majority_text}» "
                            f"({counts.iloc[0]}/{len(indices)} dòng có «{det_col}» = «{a_text}»); {same_text}")
    return {"rows": rows, "groups": groups}


def describe_rule(cfg: CrossFieldRuleConfig, df: Optional[pd.DataFrame] = None) -> str:
    """Chuỗi ngắn mô tả các cột liên quan tới rule -- dùng làm 'column' trong
    NoiseFinding để người dùng biết rule nào đã vi phạm. Dùng " & " (không
    dùng ",") để nối tên cột, vì "," đã được dùng làm dấu phân cách GIỮA CÁC
    LÝ DO khác nhau của 1 dòng trong get_flagged_rows() -- nếu dùng "," ở đây
    sẽ làm frontend tách nhầm 1 rule thành 2 lý do riêng.

    df (tuỳ chọn): bảng dữ liệu, chỉ rule EXPRESSION cần -- tên cột người dùng gõ có thể khác hoa/thường hoặc Unicode với cột thật, phải đổi sang
    ĐÚNG tên cột thật thì giao diện mới tô được ô. Không truyền df thì dùng tên như người dùng gõ."""
    if cfg.rule_type == RuleType.IF_THEN:
        if df is not None:
            return " & ".join(str(c) for c in if_then_columns(df, cfg.if_expression, cfg.then_expression))
        return " & ".join(if_then_column_names(cfg.if_expression, cfg.then_expression))
    if cfg.rule_type == RuleType.EXPRESSION:
        if df is not None:
            return " & ".join(str(c) for c in expression_columns(df, cfg.expression))
        return " & ".join(expression_column_names(cfg.expression))
    if cfg.rule_type == RuleType.COMPARE:
        return f"{cfg.column_a} & {cfg.column_b}"
    if cfg.rule_type == RuleType.CONDITIONAL:
        return f"{cfg.if_column} & {cfg.then_column}"
    if cfg.rule_type == RuleType.FORMULA:
        return " & ".join(sorted(_extract_column_names(cfg.formula)))
    if cfg.rule_type == RuleType.FUNCTIONAL_DEPENDENCY:
        return f"{cfg.determinant_column} & {cfg.dependent_column}"
    return ""


# Registry: map rule_type -> hàm detect tương ứng, dùng ở pipeline.py.
CROSS_FIELD_RULE_DETECTORS = {
    RuleType.COMPARE: detect_compare_rule,
    RuleType.CONDITIONAL: detect_conditional_rule,
    RuleType.FORMULA: detect_formula_rule,
    RuleType.FUNCTIONAL_DEPENDENCY: detect_functional_dependency_rule,
    RuleType.EXPRESSION: detect_expression_rule,
    RuleType.IF_THEN: detect_if_then_rule,
}
