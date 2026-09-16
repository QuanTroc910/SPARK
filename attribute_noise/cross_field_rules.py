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
def detect_functional_dependency_rule(df: pd.DataFrame, cfg: CrossFieldRuleConfig) -> pd.Series:
    det_col, dep_col = cfg.determinant_column, cfg.dependent_column
    if det_col not in df.columns or dep_col not in df.columns:
        return pd.Series(False, index=df.index)

    # Chuẩn hoá (strip + lowercase) trước khi so sánh -- tránh báo trùng với
    # whitespace_noise/inconsistent_category đã có (vd "Nguyen A" và
    # "nguyen a " không nên bị coi là 2 giá trị KHÁC NHAU ở check này).
    det_normalized = df[det_col].astype(str).str.strip().str.lower()
    dep_normalized = df[dep_col].astype(str).str.strip().str.lower()

    # Bỏ qua dòng có ô "thiếu" ở 1 trong 2 cột -- thuộc trách nhiệm của
    # missing_value, không nên bị FD kết luận vi phạm thêm lần 2.
    is_missing = det_normalized.apply(_is_missing_text) | dep_normalized.apply(_is_missing_text)

    working = pd.DataFrame({"det": det_normalized, "dep": dep_normalized})
    working = working[~is_missing]

    # groupby determinant -> đếm số giá trị KHÁC NHAU của dependent trong
    # nhóm. nunique > 1 nghĩa là cùng 1 determinant nhưng ra >1 dependent
    # khác nhau -> vi phạm (đánh dấu HẾT các dòng trong nhóm đó, giống cách
    # duplicate_row đánh dấu cả 2 bản trùng để người dùng tự xem và quyết định
    # bản nào đúng).
    nunique_per_group = working.groupby("det")["dep"].transform("nunique")
    violated_index = working.index[nunique_per_group > 1]

    return pd.Series(df.index.isin(violated_index), index=df.index)


def describe_rule(cfg: CrossFieldRuleConfig) -> str:
    """Chuỗi ngắn mô tả các cột liên quan tới rule -- dùng làm 'column' trong
    NoiseFinding để người dùng biết rule nào đã vi phạm. Dùng " & " (không
    dùng ",") để nối tên cột, vì "," đã được dùng làm dấu phân cách GIỮA CÁC
    LÝ DO khác nhau của 1 dòng trong get_flagged_rows() -- nếu dùng "," ở đây
    sẽ làm frontend tách nhầm 1 rule thành 2 lý do riêng."""
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
}
