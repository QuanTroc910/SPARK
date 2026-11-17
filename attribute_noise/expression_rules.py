"""Bộ máy "Biểu thức" cho rule liên cột (đợt 1: gộp "So sánh" + "Công thức" của cross_field_rules.py).

Người dùng viết MỘT điều kiện mà MỌI dòng phải thoả, vd:
    ngay_nghi > ngay_vao
    tong == so_luong * don_gia
    tuoi >= 18 và tuoi <= 65
Dòng nào CHẮC CHẮN sai thì bị gắn cờ. Dòng không tính được (ô trống, sai kiểu, chia cho 0) thì BỎ QUA nhưng được ĐẾM và báo lại
cho người dùng -- không âm thầm coi là "không lỗi" (lỗi cũ: chọn sai khuôn ngày thì mọi dòng bị bỏ qua và web báo "0 lỗi").

AN TOÀN: KHÔNG dùng eval()/exec(). Biểu thức được đọc bằng bộ tách từ + bộ phân tích cú pháp tự viết, chỉ hiểu đúng những gì liệt kê
dưới đây; gặp gì lạ (gọi hàm không có trong danh sách, ký tự lạ, truy cập thuộc tính...) là báo lỗi, không bao giờ chạy mã.

CÚ PHÁP (từ thấp tới cao theo độ ưu tiên):
    <=>   (tương đương: hai vế cùng đúng hoặc cùng sai)
    =>    (kéo theo "nếu … thì …", kết hợp từ phải sang trái; a => b chỉ SAI khi a đúng mà b sai)
    hoặc  (or, ||)
    và    (and, &&)
    không (not, !)
    so sánh  <  <=  >  >=  =  ==  !=  <>  (viết liền kiểu 0 <= tuoi <= 120 nghĩa là 0 <= tuoi và tuoi <= 120)
    + -
    * /
    - (dấu âm)
    số: 12  3.5   chuỗi chữ: "Sales" hoặc 'Sales'   cột: ten_cot hoặc [Tên cột có dấu cách]   ngoặc ( )
    hàm ép kiểu: so(x) -> Số, ngay(x) / ngay(x, "%d/%m/%Y") -> Ngày, chu(x) -> Chữ
    hàm kiểm tra ô: có(cột) -> Đúng nếu ô có giá trị, Sai nếu ô trống (luôn biết chắc, không "chưa biết"), dùng cho "bắt buộc có giá trị khi …":
        phong_ban = "Sales" => có(ma_khach)
Tab "Nếu – thì" của giao diện dùng evaluate_conditional(): hai ô NẾU và THÌ đều là biểu thức đầy đủ, kết quả = NẾU => THÌ.
Chấp nhận cả "va/hoac/khong" viết không dấu; tên cột không phân biệt hoa/thường nếu không bị trùng.

KIỂU GIÁ TRỊ: mỗi cột tự được nhận là Số / Ngày / Chữ theo dữ liệu thật (>= 90% ô khớp), người dùng ép lại bằng so()/ngay()/chu() nếu đoán sai.
    Số ± Số, Số * Số, Số / Số -> Số (chia cho 0 -> "chưa biết", được đếm riêng).  Ngày - Ngày -> số ngày.  Ngày ± Số -> Ngày.
    So sánh phải cùng kiểu; chữ viết thẳng trong biểu thức ("2024-01-31", "18") được tự đổi sang kiểu của vế kia.

LOGIC 3 GIÁ TRỊ (Đúng / Sai / Chưa biết): ô thiếu hoặc không đọc được cho "Chưa biết", KHÔNG phải "Sai". Chỉ gắn cờ khi kết quả CHẮC CHẮN Sai
(vd `Sai và Chưa biết` = Sai thì vẫn gắn cờ; `Đúng và Chưa biết` = Chưa biết thì bỏ qua). Dùng kiểu "boolean" (nullable) của pandas
vốn đã cài sẵn đúng bảng chân trị Kleene này.

Module này CHỈ phụ thuộc config.py (không import pipeline.py/cross_field_rules.py) để cross_field_rules.py import được mà không vòng tròn.
"""

from __future__ import annotations

import difflib
import operator
import unicodedata
from collections import namedtuple
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

import numpy as np
import pandas as pd

from .config import DEFAULT_MISSING_PLACEHOLDERS, CrossFieldRuleConfig

MAX_EXPRESSION_LENGTH = 2000  # ký tự
MAX_TOKENS = 600
MAX_DEPTH = 40  # độ lồng ngoặc / "không" tối đa (chặn đệ quy quá sâu)
DEFAULT_TOLERANCE = 0.01  # sai số cho phép khi so bằng (== / !=) giữa 2 số, giống rule Công thức cũ
TYPE_SAMPLE_SIZE = 1000  # số ô KHÔNG thiếu đầu tiên dùng để đoán kiểu cột / khuôn ngày
TYPE_MATCH_RATIO = 0.9  # >= 90% ô khớp mới nhận cột là Số / Ngày (cùng ngưỡng guess_column_dtype)

# Khuôn ngày thử lần lượt khi tự nhận (khuôn đứng trước thắng khi 2 khuôn đọc được số ô bằng nhau). Dạng ngày-trước đứng trước tháng-trước
# vì dữ liệu của người dùng Việt Nam thường là dd/mm/yyyy; file Excel đọc ra "2024-01-31 00:00:00" nên có cả khuôn kèm giờ.
DATE_FORMAT_CANDIDATES = [
    "%Y-%m-%d",
    "%Y-%m-%d %H:%M:%S",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%m/%d/%Y",
    "%Y/%m/%d",
]

KIND_LABELS = {"num": "Số", "date": "Ngày", "text": "Chữ", "bool": "Đúng/Sai"}

_MISSING_LOWER = frozenset(p.lower() for p in DEFAULT_MISSING_PLACEHOLDERS)


def _clean_text(series: pd.Series) -> pd.Series:
    """Cách bộ máy đọc 1 cột chữ: cắt khoảng trắng hai đầu, ô thiếu (trống, N/A, null, ?...) thành NaN. Dùng chung cho tính biểu thức (_Evaluator.raw),
    chip giá trị (column_value_counts) và việc tự nhận chữ trần (bind_bare_values) để cả 3 luôn thấy CÙNG một tập giá trị."""
    text = series.astype(str).str.strip()
    return text.astype(object).mask(text.str.lower().isin(_MISSING_LOWER))


class ExpressionError(ValueError):
    """Biểu thức sai cú pháp / sai kiểu / nhắc tới cột không có. Thông báo viết sẵn bằng tiếng Việt, hiển thị thẳng cho người dùng."""


def _fail(text: str, pos: int, message: str) -> ExpressionError:
    start, end = max(0, pos - 15), min(len(text), pos + 15)
    return ExpressionError(f"Biểu thức sai ở ký tự thứ {pos + 1}: {message}. Đoạn gần đó: «{text[start:end]}»")


# ---------------------------------------------------------------------------
# 1. Tách từ
# ---------------------------------------------------------------------------
_Tok = namedtuple("_Tok", "kind value pos")  # kind: num str col ident kw op lp rp comma end

_AND_WORDS = frozenset({"và", "va", "and"})
_OR_WORDS = frozenset({"hoặc", "hoac", "or"})
_NOT_WORDS = frozenset({"không", "khong", "not"})
_DIGITS = "0123456789"
_DOUBLE_QUOTES = '"“”'
_SINGLE_QUOTES = "'‘’"
# Ký tự hay bị chép từ Word/Excel/trình soạn thảo vào: đổi về phép toán thường.
_CHAR_ALIASES = {"−": "-", "–": "-", "—": "-", "×": "*", "÷": "/", "≤": "<=", "≥": ">=", "≠": "!="}
_RELOPS = frozenset({"<", "<=", ">", ">=", "==", "!="})
_FUNCTIONS = {"so": "so", "số": "so", "ngay": "ngay", "ngày": "ngay", "chu": "chu", "chữ": "chu", "co": "co", "có": "co"}


def _tokenize(text: str) -> list:
    tokens: list = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if ch in _DIGITS or (ch == "." and i + 1 < n and text[i + 1] in _DIGITS):
            j = i
            while j < n and text[j] in _DIGITS:
                j += 1
            if j < n and text[j] == ".":
                j += 1
                while j < n and text[j] in _DIGITS:
                    j += 1
            if j < n and (text[j].isalpha() or text[j] == "_"):
                raise _fail(text, i, "tên cột bắt đầu bằng chữ số phải viết trong ngoặc vuông, vd [2024_doanh_thu]")
            tokens.append(_Tok("num", float(text[i:j]), i))
            i = j
            continue
        if ch in _DOUBLE_QUOTES or ch in _SINGLE_QUOTES:
            closers = _DOUBLE_QUOTES if ch in _DOUBLE_QUOTES else _SINGLE_QUOTES
            j, buf = i + 1, []
            while j < n and text[j] not in closers:
                if text[j] == "\\" and j + 1 < n:  # \" hoặc \\ : lấy nguyên ký tự đứng sau
                    j += 1
                buf.append(text[j])
                j += 1
            if j >= n:
                raise _fail(text, i, "chuỗi chữ thiếu dấu nháy đóng")
            tokens.append(_Tok("str", "".join(buf), i))
            i = j + 1
            continue
        if ch == "[":
            j = text.find("]", i + 1)
            if j == -1:
                raise _fail(text, i, "thiếu dấu ] đóng tên cột")
            name = text[i + 1 : j].strip()
            if not name:
                raise _fail(text, i, "tên cột trong [ ] đang để trống")
            tokens.append(_Tok("col", name, i))
            i = j + 1
            continue
        two = text[i : i + 2]
        if text[i : i + 3] in ("<=>", "<->"):
            tokens.append(_Tok("kw", "iff", i))
            i += 3
            continue
        if two in ("=>", "->"):
            tokens.append(_Tok("kw", "imp", i))
            i += 2
            continue
        if two in ("<=", ">=", "==", "!="):
            tokens.append(_Tok("op", two, i))
            i += 2
            continue
        if two == "<>":
            tokens.append(_Tok("op", "!=", i))
            i += 2
            continue
        if two == "&&":
            tokens.append(_Tok("kw", "and", i))
            i += 2
            continue
        if two == "||":
            tokens.append(_Tok("kw", "or", i))
            i += 2
            continue
        if ch in _CHAR_ALIASES:
            tokens.append(_Tok("op", _CHAR_ALIASES[ch], i))
            i += 1
            continue
        if ch in "<>+-*/":
            tokens.append(_Tok("op", ch, i))
            i += 1
            continue
        if ch == "=":
            tokens.append(_Tok("op", "==", i))
            i += 1
            continue
        if ch == "!":
            tokens.append(_Tok("kw", "not", i))
            i += 1
            continue
        if ch == "(":
            tokens.append(_Tok("lp", ch, i))
            i += 1
            continue
        if ch == ")":
            tokens.append(_Tok("rp", ch, i))
            i += 1
            continue
        if ch == ",":
            tokens.append(_Tok("comma", ch, i))
            i += 1
            continue
        if ch.isalpha() or ch == "_":
            j = i + 1
            while j < n and (text[j].isalnum() or text[j] in "_."):  # dấu . được phép trong tên cột (vd capital.gain)
                j += 1
            word = text[i:j]
            low = word.casefold()
            if low in _AND_WORDS:
                tokens.append(_Tok("kw", "and", i))
            elif low in _OR_WORDS:
                tokens.append(_Tok("kw", "or", i))
            elif low in _NOT_WORDS:
                tokens.append(_Tok("kw", "not", i))
            else:
                tokens.append(_Tok("ident", word, i))
            i = j
            continue
        raise _fail(text, i, f"ký tự «{ch}» không dùng được trong biểu thức (tên cột có ký tự đặc biệt thì viết trong [ ])")
        # (không tới được đây)
    tokens.append(_Tok("end", "", n))
    return tokens


# ---------------------------------------------------------------------------
# 2. Phân tích cú pháp -> cây (tuple). Hình dạng các nút:
#    ("num", giá_trị, pos) ("str", chuỗi, pos) ("col", tên, pos) ("neg", nút, pos)
#    ("bin", "+|-|*|/", trái, phải, pos) ("cmp", [các vế], [các phép so], [pos...])
#    ("and"|"or", trái, phải, pos) ("not", nút, pos) ("call", tên_hàm, [đối số], pos)
# ---------------------------------------------------------------------------
class _Parser:
    def __init__(self, text: str, tokens: list):
        self.text = text
        self.toks = tokens
        self.i = 0
        self.depth = 0

    def peek(self) -> _Tok:
        return self.toks[self.i]

    def take(self) -> _Tok:
        tok = self.toks[self.i]
        self.i += 1
        return tok

    def fail(self, tok: _Tok, message: str) -> ExpressionError:
        return _fail(self.text, tok.pos, message)

    def _enter(self, tok: _Tok) -> None:
        self.depth += 1
        if self.depth > MAX_DEPTH:
            raise self.fail(tok, "biểu thức lồng quá sâu")

    def _leave(self) -> None:
        self.depth -= 1

    def parse(self):
        node = self.expr()
        tok = self.peek()
        if tok.kind != "end":
            if tok.kind == "rp":
                raise self.fail(tok, "dấu ) thừa (không có dấu ( mở tương ứng)")
            raise self.fail(tok, "thiếu phép nối (và / hoặc) hoặc phép so sánh/tính trước chỗ này")
        return node

    def expr(self):
        """Mức thấp nhất: a <=> b (tương đương); trên nó là a => b (kéo theo, kết hợp phải); rồi hoặc / và / không / so sánh ..."""
        self._enter(self.peek())
        try:
            node = self.implies_expr()
            while self.peek().kind == "kw" and self.peek().value == "iff":
                tok = self.take()
                node = ("iff", node, self.implies_expr(), tok.pos)
            return node
        finally:
            self._leave()

    def implies_expr(self):
        node = self.or_expr()
        if self.peek().kind == "kw" and self.peek().value == "imp":
            tok = self.take()
            self._enter(tok)
            try:
                return ("imp", node, self.implies_expr(), tok.pos)  # a => b => c  ==  a => (b => c)
            finally:
                self._leave()
        return node

    def or_expr(self):
        self._enter(self.peek())
        try:
            node = self.and_expr()
            while self.peek().kind == "kw" and self.peek().value == "or":
                tok = self.take()
                node = ("or", node, self.and_expr(), tok.pos)
            return node
        finally:
            self._leave()

    def and_expr(self):
        node = self.not_expr()
        while self.peek().kind == "kw" and self.peek().value == "and":
            tok = self.take()
            node = ("and", node, self.not_expr(), tok.pos)
        return node

    def not_expr(self):
        tok = self.peek()
        if tok.kind == "kw" and tok.value == "not":
            self.take()
            self._enter(tok)
            try:
                return ("not", self.not_expr(), tok.pos)
            finally:
                self._leave()
        return self.comparison()

    def comparison(self):
        operands = [self.additive()]
        ops: list = []
        positions: list = []
        while self.peek().kind == "op" and self.peek().value in _RELOPS:
            tok = self.take()
            ops.append(tok.value)
            positions.append(tok.pos)
            operands.append(self.additive())
        if not ops:
            return operands[0]
        return ("cmp", operands, ops, positions)

    def additive(self):
        node = self.term()
        while self.peek().kind == "op" and self.peek().value in ("+", "-"):
            tok = self.take()
            node = ("bin", tok.value, node, self.term(), tok.pos)
        return node

    def term(self):
        node = self.unary()
        while self.peek().kind == "op" and self.peek().value in ("*", "/"):
            tok = self.take()
            node = ("bin", tok.value, node, self.unary(), tok.pos)
        return node

    def unary(self):
        tok = self.peek()
        if tok.kind == "op" and tok.value in ("-", "+"):
            self.take()
            self._enter(tok)
            try:
                inner = self.unary()
            finally:
                self._leave()
            return ("neg", inner, tok.pos) if tok.value == "-" else inner
        return self.primary()

    def primary(self):
        tok = self.take()
        if tok.kind == "num":
            return ("num", tok.value, tok.pos)
        if tok.kind == "str":
            return ("str", tok.value, tok.pos)
        if tok.kind == "col":
            return ("col", tok.value, tok.pos)
        if tok.kind == "ident":
            if self.peek().kind == "lp":
                return self.call(tok)
            return ("col", tok.value, tok.pos)
        if tok.kind == "lp":
            node = self.expr()
            close = self.peek()
            if close.kind != "rp":
                raise self.fail(tok, "dấu ( này chưa có dấu ) đóng")
            self.take()
            return node
        if tok.kind == "end":
            raise self.fail(tok, "biểu thức bị cắt cụt, thiếu vế phía sau")
        raise self.fail(tok, "chỗ này cần một cột, một số, một chuỗi chữ hoặc một biểu thức trong ngoặc")

    def call(self, name_tok: _Tok):
        name = _FUNCTIONS.get(name_tok.value.casefold())
        if name is None:
            raise self.fail(name_tok, f"«{name_tok.value}» không phải hàm (hàm có sẵn: so, ngay, chu, có). Nếu «{name_tok.value}» là tên cột thì thiếu phép toán "
                                      "hoặc và/hoặc sau nó; tên cột có ngoặc ( ) thì viết trong [ ]")
        self.take()  # dấu (
        args: list = []
        if self.peek().kind != "rp":
            while True:
                args.append(self.expr())
                if self.peek().kind == "comma":
                    self.take()
                    continue
                break
        close = self.peek()
        if close.kind != "rp":
            raise self.fail(name_tok, f"hàm «{name_tok.value}» chưa có dấu ) đóng")
        self.take()
        low, high = (1, 2) if name == "ngay" else (1, 1)
        if not low <= len(args) <= high:
            expected = "1 hoặc 2 đối số (cột, và khuôn ngày tuỳ chọn)" if name == "ngay" else "đúng 1 đối số"
            raise self.fail(name_tok, f"hàm «{name_tok.value}» cần {expected}, đang có {len(args)}")
        return ("call", name, args, name_tok.pos)


def parse_expression(expression: Optional[str]):
    """Đọc biểu thức -> (cây, chuỗi đã chuẩn hoá Unicode NFC). Raise ExpressionError nếu sai."""
    if expression is None or not str(expression).strip():
        raise ExpressionError("Chưa nhập biểu thức")
    text = unicodedata.normalize("NFC", str(expression)).strip()
    if len(text) > MAX_EXPRESSION_LENGTH:
        raise ExpressionError(f"Biểu thức quá dài ({len(text)} ký tự, tối đa {MAX_EXPRESSION_LENGTH})")
    tokens = _tokenize(text)
    if len(tokens) > MAX_TOKENS:
        raise ExpressionError(f"Biểu thức quá phức tạp (hơn {MAX_TOKENS} thành phần)")
    node = _Parser(text, tokens).parse()
    if not _columns_in(node):
        raise ExpressionError("Biểu thức chưa nhắc tới cột nào. Viết tên cột (hoặc [Tên cột có dấu cách]) vào biểu thức")
    return node, text


def _columns_in(node, out: Optional[list] = None) -> list:
    """Các (tên cột như người dùng gõ, vị trí) theo thứ tự xuất hiện, trùng thì giữ cả (lọc ở nơi gọi)."""
    out = [] if out is None else out
    kind = node[0]
    if kind == "col":
        out.append((node[1], node[2]))
    elif kind in ("neg", "not"):
        _columns_in(node[1], out)
    elif kind == "bin":
        _columns_in(node[2], out)
        _columns_in(node[3], out)
    elif kind in ("and", "or", "imp", "iff"):
        _columns_in(node[1], out)
        _columns_in(node[2], out)
    elif kind == "cmp":
        for operand in node[1]:
            _columns_in(operand, out)
    elif kind == "call":
        for arg in node[2]:
            _columns_in(arg, out)
    return out


# ---------------------------------------------------------------------------
# 3. Tên cột -> cột thật của bảng
# ---------------------------------------------------------------------------
def _nfc(value: Any) -> str:
    return unicodedata.normalize("NFC", str(value))


class _ColumnResolver:
    """Khớp tên cột người dùng gõ với cột thật: khớp đúng -> khớp sau khi cắt khoảng trắng -> khớp không phân biệt hoa/thường (chỉ khi
    duy nhất). Không khớp thì báo lỗi kèm gợi ý cột gần giống."""

    def __init__(self, columns):
        self.columns = list(columns)
        self.exact: dict = {}
        self.stripped: dict = {}
        self.folded: dict = {}
        for column in self.columns:
            name = _nfc(column)
            self.exact.setdefault(name, column)
            self.stripped.setdefault(name.strip(), column)
            self.folded.setdefault(name.strip().casefold(), []).append(column)

    def known(self, name: str) -> bool:
        """Có cột nào khớp tên này không (kể cả trường hợp nhiều cột chỉ khác hoa/thường, vẫn là "tên cột")."""
        wanted = _nfc(name)
        return wanted in self.exact or wanted.strip() in self.stripped or bool(self.folded.get(wanted.strip().casefold()))

    def resolve(self, name: str, text: str = "", pos: int = 0, value_col=None, near_values=()):
        """value_col != None: từ này đứng cạnh cột `value_col` trong một phép so sánh và đã được tra KHÔNG phải giá trị nào của cột đó
        (xem bind_bare_values); near_values = các giá trị gần giống để gợi ý."""
        wanted = _nfc(name)
        if wanted in self.exact:
            return self.exact[wanted]
        if wanted.strip() in self.stripped:
            return self.stripped[wanted.strip()]
        matches = self.folded.get(wanted.strip().casefold(), [])
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise _fail(text, pos, f"có nhiều cột chỉ khác nhau hoa/thường ({', '.join('«' + str(m) + '»' for m in matches)}), hãy gõ đúng một tên")
        # Từ đứng cạnh một cột (value_col) nhiều khả năng là giá trị chứ không phải tên cột gõ nhầm: chỉ gợi ý tên cột khi giống rất sát (agee -> age),
        # tránh gợi ý nhiễu kiểu "Salse -> age".
        close = difflib.get_close_matches(wanted.strip(), [_nfc(c).strip() for c in self.columns], n=3, cutoff=0.5 if value_col is None else 0.75)
        hint = f" Có phải: {', '.join('«' + c + '»' for c in close)}?" if close else ""
        # Lỗi hay gặp nhất khi gõ tay: viết GIÁ TRỊ CHỮ mà quên dấu nháy (department == Sales) nên bị hiểu là tên một cột. Tên viết trong [ ] thì
        # chắc chắn là người dùng muốn nói tới cột, không nhắc nháy. Luôn nhắc cả khi đã có "Có phải ...?" vì tên giá trị (sales) có thể giống tên cột (salary).
        quote_hint = "" if text[pos:pos + 1] == "[" else f" Nếu «{name}» là giá trị chữ chứ không phải tên cột, hãy viết trong dấu nháy: \"{name}\"."
        if value_col is not None:
            # Từ này đứng cạnh một cột nên có thể là giá trị chữ viết trần, nhưng đã tra: cột đó không có giá trị nào như vậy (gõ nhầm, hoặc khác hoa/thường).
            near = f" (giá trị gần giống: {', '.join('«' + v + '»' for v in near_values)})" if near_values else ""
            quote_hint = f" «{name}» cũng không phải giá trị nào của cột «{value_col}»{near}. Muốn so với một chữ khác thì viết trong dấu nháy: \"{name}\"."
        sample = ", ".join(f"«{c}»" for c in list(map(str, self.columns))[:15])
        more = " …" if len(self.columns) > 15 else ""
        raise _fail(text, pos, f"không có cột «{name}» trong dữ liệu.{hint}{quote_hint} Các cột có sẵn: {sample}{more}")


def bind_bare_values(node, text: str, df: pd.DataFrame, resolver: Optional["_ColumnResolver"] = None):
    """Tự nhận GIÁ TRỊ CHỮ viết trần (không dấu nháy): `department = Sales` hiểu như `department = "Sales"`.

    Chỉ áp dụng cho một từ đứng cạnh một CỘT trong phép so sánh, và chỉ khi từ đó (1) không phải tên cột nào, (2) không viết trong [ ], (3) đúng là một giá
    trị thật của cột đứng cạnh (so ĐÚNG như phép so chữ: cắt khoảng trắng hai đầu, phân biệt hoa/thường, bỏ ô thiếu). Nhờ điều kiện (3) mà gõ nhầm tên cột
    (agee) hay nhầm giá trị (Salse) KHÔNG bị hiểu thầm thành chữ rồi gắn cờ cả file: vẫn báo lỗi, kèm giá trị gần giống để chọn lại. Tên cột luôn thắng
    (từ trùng tên một cột thì vẫn là cột). Giá trị có dấu cách hay ký tự lạ vẫn phải viết trong nháy (hoặc bấm chip giá trị).

    Trả về CÂY MỚI (nút ("col", từ, pos) được đổi thành ("str", từ, pos)), cây gốc không bị sửa. Gọi sau parse_expression, trước khi tính / liệt kê cột."""
    resolver = resolver or _ColumnResolver(df.columns)
    cache: dict = {}  # cột thật -> các giá trị chữ khác nhau (đã sắp, để gợi ý ổn định)

    def values_of(actual) -> list:
        if actual not in cache:
            cache[actual] = sorted(set(_clean_text(df[actual]).dropna()))
        return cache[actual]

    def is_bare_unknown(n) -> bool:
        return n[0] == "col" and text[n[2]:n[2] + 1] != "[" and not resolver.known(n[1])

    def known_column(n):
        if n[0] != "col" or not resolver.known(n[1]):
            return None
        try:
            return resolver.resolve(n[1], text, n[2])
        except ExpressionError:  # nhiều cột chỉ khác hoa/thường: để lỗi gốc báo lúc tính
            return None

    def walk(n):
        kind = n[0]
        if kind in ("neg", "not"):
            return (kind, walk(n[1]), n[2])
        if kind == "bin":
            return ("bin", n[1], walk(n[2]), walk(n[3]), n[4])
        if kind in ("and", "or", "imp", "iff"):
            return (kind, walk(n[1]), walk(n[2]), n[3])
        if kind == "call":
            return ("call", n[1], [walk(a) for a in n[2]], n[3])
        if kind != "cmp":
            return n
        operands = [walk(o) for o in n[1]]
        for j, operand in enumerate(operands):
            if not is_bare_unknown(operand):
                continue
            for k in (j - 1, j + 1):  # a < b < c: mỗi vế xét với cột đứng liền kề
                if not 0 <= k < len(operands):
                    continue
                actual = known_column(operands[k])
                if actual is None:
                    continue
                word, values = operand[1], values_of(actual)
                if word in values:
                    operands[j] = ("str", word, operand[2])
                else:
                    near = [v for v in values if v.casefold() == word.casefold()]
                    near += [v for v in difflib.get_close_matches(word, values, n=3, cutoff=0.6) if v not in near]
                    resolver.resolve(word, text, operand[2], value_col=actual, near_values=near[:3])  # từ không phải cột nên luôn raise
                break
        return ("cmp", operands, n[2], n[3])

    return walk(node)


def expression_column_names(expression: Optional[str]) -> list:
    """Tên cột NHƯ NGƯỜI DÙNG GÕ trong biểu thức (chưa khớp với bảng), theo thứ tự xuất hiện, không trùng. Dùng khi chưa có bảng dữ liệu."""
    node, _text = parse_expression(expression)
    names: list = []
    for name, _pos in _columns_in(node):
        if name not in names:
            names.append(name)
    return names


def column_value_counts(series: pd.Series, limit: int = 30) -> tuple:
    """Các giá trị chữ khác nhau của 1 cột kèm số dòng, để giao diện hiện "chip giá trị" (bấm là chèn `"Sales"` vào biểu thức).

    Đếm theo ĐÚNG cách bộ máy đọc chữ (xem _Evaluator.raw): cắt khoảng trắng hai đầu (" HR" và "HR" là một), ô thiếu (trống, N/A, null, ?...)
    bỏ qua, PHÂN BIỆT hoa/thường ("Sales" và "SALES" là hai giá trị). Nhờ vậy số đếm của chip = số dòng thật sự khớp khi viết `cột = "giá trị"`.
    Trả về (danh sách [{"value", "count"}] đã sắp theo số dòng giảm dần rồi theo chữ, tối đa `limit` phần tử, số giá trị khác còn lại không hiện)."""
    text = _clean_text(series).dropna()
    ordered = sorted(text.value_counts().items(), key=lambda kv: (-int(kv[1]), str(kv[0])))
    shown = [{"value": str(v), "count": int(n)} for v, n in ordered[:limit]]
    return shown, max(0, len(ordered) - limit)


def expression_columns(df: pd.DataFrame, expression: Optional[str]) -> list:
    """Tên cột THẬT (đúng như trong bảng) mà biểu thức nhắc tới, theo thứ tự xuất hiện, không trùng -- dùng để tô ô và đặt tên rule."""
    node, text = parse_expression(expression)
    resolver = _ColumnResolver(df.columns)
    node = bind_bare_values(node, text, df, resolver)  # chữ trần như Sales (giá trị của cột đứng cạnh) không phải là cột
    result: list = []
    for name, pos in _columns_in(node):
        actual = resolver.resolve(name, text, pos)
        if actual not in result:
            result.append(actual)
    return result


# ---------------------------------------------------------------------------
# 4. Tính biểu thức (theo cả cột cùng lúc, không lặp từng dòng)
# ---------------------------------------------------------------------------
class _Val:
    """Giá trị trung gian: kind (num/date/text/bool) + Series cùng index với bảng. literal = hằng viết thẳng trong biểu thức; column =
    tên cột nếu là 1 cột nguyên; fmt = khuôn ngày của cột ngày; value = giá trị hằng."""

    __slots__ = ("kind", "data", "literal", "column", "fmt", "value")

    def __init__(self, kind: str, data: pd.Series, literal: bool = False, column: Any = None, fmt: Optional[str] = None, value: Any = None):
        self.kind, self.data, self.literal, self.column, self.fmt, self.value = kind, data, literal, column, fmt, value


_COMPARE_OPS = {"<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge, "==": operator.eq, "!=": operator.ne}


def _nullable(values: np.ndarray, known: np.ndarray, index) -> pd.Series:
    """Series kiểu boolean (nullable): vị trí `known` = False là "chưa biết" (NA)."""
    return pd.Series(pd.arrays.BooleanArray(np.asarray(values, dtype=bool), ~np.asarray(known, dtype=bool)), index=index)


@dataclass
class ExpressionResult:
    violations: pd.Series  # True = CHẮC CHẮN sai (bị gắn cờ)
    unknown: pd.Series  # True = không tính được (bỏ qua)
    columns_used: list  # tên cột thật, theo thứ tự xuất hiện
    columns: list = field(default_factory=list)  # [{name, type, date_format, blank, unreadable, readable}] cách đọc từng cột
    zero_division_rows: int = 0  # số dòng có phép chia cho 0 (đã tính vào `unknown`)
    text_order_columns: list = field(default_factory=list)  # cột Chữ bị so thứ tự (< > <= >=) -- giao diện cảnh báo, xem _Evaluator


class _Evaluator:
    def __init__(self, df: pd.DataFrame, resolver: _ColumnResolver, text: str, tolerance: float, date_format: Optional[str]):
        self.df = df
        self.index = df.index
        self.n = len(df)
        self.resolver = resolver
        self.text = text
        self.tol = tolerance
        self.forced_fmt = date_format
        self.raw_cache: dict = {}
        self.val_cache: dict = {}
        self.info: dict = {}
        self.used: list = []
        self.text_order_columns: list = []  # cột Chữ bị so thứ tự (< > <= >=): nhiều khả năng là ngày/số bị nhận nhầm thành Chữ
        self.zero_div = np.zeros(self.n, dtype=bool)

    def err(self, pos: int, message: str) -> ExpressionError:
        return _fail(self.text, pos, message)

    # ---- đọc cột thô -> chuỗi đã cắt khoảng trắng, ô thiếu = NaN ----
    def raw(self, actual) -> pd.Series:
        if actual not in self.raw_cache:
            self.raw_cache[actual] = _clean_text(self.df[actual])
        return self.raw_cache[actual]

    def numbers(self, text: pd.Series) -> pd.Series:
        num = pd.to_numeric(text, errors="coerce").astype(float)
        return num.where(np.isfinite(num))  # "inf" / "nan" không phải số dùng được

    def best_date_format(self, text: pd.Series, ignore_forced: bool = False) -> tuple:
        """(khuôn, tỉ lệ ô đọc được) -- khuôn ép từ người dùng nếu có (trừ khi ignore_forced), không thì khuôn đọc được nhiều ô nhất trong mẫu
        (hoà: khuôn đứng trước)."""
        use_forced = self.forced_fmt and not ignore_forced
        sample = text.dropna().head(TYPE_SAMPLE_SIZE)
        if sample.empty:
            return (self.forced_fmt if use_forced else None), 0.0
        formats = [self.forced_fmt] if use_forced else DATE_FORMAT_CANDIDATES
        best_fmt, best_count = None, 0
        for fmt in formats:
            count = int(pd.to_datetime(sample, format=fmt, errors="coerce").notna().sum())
            if count > best_count:
                best_fmt, best_count = fmt, count
        return best_fmt, best_count / len(sample)

    def dates(self, text: pd.Series, fmt: Optional[str]) -> pd.Series:
        if fmt is None:
            return pd.Series(pd.NaT, index=self.index, dtype="datetime64[ns]")
        return pd.to_datetime(text, format=fmt, errors="coerce").dt.normalize()  # chỉ so theo NGÀY, bỏ phần giờ

    def infer(self, actual) -> tuple:
        """Kiểu của cột theo dữ liệu thật: Số (>= 90% ô là số, và không phải mã có số 0 đứng đầu như 007, SĐT) -> Ngày (>= 90% ô khớp 1 khuôn) -> Chữ."""
        text = self.raw(actual)
        sample = text.dropna().head(TYPE_SAMPLE_SIZE)
        if sample.empty:
            return "text", None
        numeric_ratio = float(np.isfinite(pd.to_numeric(sample, errors="coerce").astype(float)).mean())
        if numeric_ratio >= TYPE_MATCH_RATIO and float(sample.str.match(r"^0\d").mean()) < 0.1:
            return "number", None
        # Có phải cột NGÀY hay không xét theo MỌI khuôn thử được (không chỉ khuôn người dùng ép); khuôn ép chỉ quyết định cách ĐỌC. Nếu xét theo
        # khuôn ép thì ép sai khuôn làm cột bị nhận thành Chữ rồi so như chuỗi -- kết quả vô nghĩa mà không ai biết; còn như thế này cột vẫn là
        # Ngày, các ô không đọc được bị bỏ qua và được đếm/báo ra.
        auto_fmt, auto_ratio = self.best_date_format(text, ignore_forced=True)
        if self.forced_fmt:
            if max(auto_ratio, self.best_date_format(text)[1]) >= TYPE_MATCH_RATIO:
                return "date", self.forced_fmt
        elif auto_fmt and auto_ratio >= TYPE_MATCH_RATIO:
            return "date", auto_fmt
        return "text", None

    def typed(self, actual, kind: str, fmt: Optional[str] = None) -> _Val:
        """Cột `actual` đọc theo kiểu `kind` (number/date/text); ghi lại cách đọc (số ô trống, số ô không đọc được) để báo cho người dùng."""
        text = self.raw(actual)
        if kind == "number":
            data, val_kind = self.numbers(text), "num"
        elif kind == "date":
            if fmt is None:
                fmt, _ratio = self.best_date_format(text)
            data, val_kind = self.dates(text, fmt), "date"
        else:
            data, val_kind = text.map(lambda v: _nfc(v) if isinstance(v, str) else v), "text"
        key = (actual, kind, fmt)
        if key not in self.info:
            present = int(text.notna().sum())
            readable = int(data.notna().sum())
            self.info[key] = {
                "name": str(actual), "type": val_kind, "date_format": fmt if kind == "date" else None,
                "blank": self.n - present, "unreadable": present - readable, "readable": readable,
            }
        return _Val(val_kind, data, column=actual, fmt=fmt if kind == "date" else None)

    def column(self, name: str, pos: int, kind: Optional[str] = None, fmt: Optional[str] = None) -> _Val:
        actual = self.resolver.resolve(name, self.text, pos)
        if actual not in self.used:
            self.used.append(actual)
        if kind is None:
            kind, fmt = self.infer(actual)
        return self.typed(actual, kind, fmt)

    # ---- hằng ----
    def const(self, kind: str, value: Any, dtype=None) -> pd.Series:
        if kind == "num":
            return pd.Series(float(value), index=self.index)
        if kind == "date":
            return pd.Series(value, index=self.index, dtype="datetime64[ns]")
        return pd.Series(np.full(self.n, value, dtype=object), index=self.index)

    def parse_date_literal(self, value: str, hint_fmt: Optional[str], pos: int) -> pd.Timestamp:
        text = value.strip()
        for fmt in [f for f in (hint_fmt, self.forced_fmt) if f] + DATE_FORMAT_CANDIDATES:
            try:
                return pd.Timestamp(datetime.strptime(text, fmt)).normalize()
            except ValueError:
                continue
        raise self.err(pos, f"«{value}» không hiểu là ngày. Viết dạng 2024-01-31 hoặc 31/01/2024, hoặc ngay(\"{value}\", \"%d/%m/%Y\") để chỉ rõ khuôn")

    # ---- tính từng loại nút ----
    def ev(self, node) -> _Val:
        kind = node[0]
        if kind == "num":
            return _Val("num", self.const("num", node[1]), literal=True, value=node[1])
        if kind == "str":
            value = _nfc(node[1]).strip()
            return _Val("text", self.const("text", value), literal=True, value=value)
        if kind == "col":
            return self.column(node[1], node[2])
        if kind == "neg":
            inner = self.ev(node[1])
            if inner.kind != "num":
                raise self.err(node[2], f"dấu âm chỉ dùng với Số, đang là {KIND_LABELS[inner.kind]}")
            return _Val("num", -inner.data)
        if kind == "bin":
            return self.arith(node)
        if kind == "cmp":
            return self.compare_chain(node)
        if kind in ("and", "or"):
            left, right = self.ev(node[1]), self.ev(node[2])
            word = "và" if kind == "and" else "hoặc"
            for side, value in (("trái", left), ("phải", right)):
                if value.kind != "bool":
                    raise self.err(node[3], f"«{word}» phải nối hai điều kiện (vd a > 1 {word} b < 2), nhưng vế {side} đang là {KIND_LABELS[value.kind]}")
            a, b = left.data.array, right.data.array
            return _Val("bool", pd.Series(a & b if kind == "and" else a | b, index=self.index))
        if kind in ("imp", "iff"):
            left, right = self.ev(node[1]), self.ev(node[2])
            word = "=>" if kind == "imp" else "<=>"
            for side, value in (("trái", left), ("phải", right)):
                if value.kind != "bool":
                    hint = " Nếu bạn muốn so sánh «lớn hơn hoặc bằng» thì viết >= (không phải =>)." if kind == "imp" else ""
                    raise self.err(node[3], f"«{word}» (nếu … thì …) phải nối hai điều kiện, nhưng vế {side} đang là {KIND_LABELS[value.kind]}.{hint}")
            a, b = left.data.array, right.data.array
            # Kleene: a => b  =  không a hoặc b  (sai duy nhất khi a đúng mà b sai; a sai thì luôn đúng; còn lại "chưa biết" nếu chưa chắc)
            return _Val("bool", pd.Series((~a | b) if kind == "imp" else ((~a | b) & (~b | a)), index=self.index))
        if kind == "not":
            inner = self.ev(node[1])
            if inner.kind != "bool":
                raise self.err(node[2], f"«không» phải đứng trước một điều kiện (vd không a > 1), nhưng đang là {KIND_LABELS[inner.kind]}")
            return _Val("bool", pd.Series(~inner.data.array, index=self.index))
        return self.call(node)

    def arith(self, node) -> _Val:
        _, op, left_node, right_node, pos = node
        left, right = self.ev(left_node), self.ev(right_node)
        lk, rk = left.kind, right.kind
        if lk == "num" and rk == "num":
            a, b = left.data.to_numpy(dtype=float), right.data.to_numpy(dtype=float)
            with np.errstate(all="ignore"):
                if op == "+":
                    out = a + b
                elif op == "-":
                    out = a - b
                elif op == "*":
                    out = a * b
                else:
                    self.zero_div |= (b == 0) & ~np.isnan(a)  # chia cho 0: "chưa tính được", không phải "sai"
                    out = np.where(b == 0, np.nan, a / np.where(b == 0, 1.0, b))
            return _Val("num", pd.Series(np.where(np.isfinite(out), out, np.nan), index=self.index))
        if lk == "date" and rk == "date" and op == "-":
            return _Val("num", (left.data - right.data).dt.total_seconds() / 86400.0)  # số ngày giữa 2 ngày
        if op in ("+", "-") and ((lk == "date" and rk == "num") or (lk == "num" and rk == "date" and op == "+")):
            date, number = (left, right) if lk == "date" else (right, left)
            try:
                shift = pd.to_timedelta(number.data, unit="D")
                return _Val("date", date.data + shift if op == "+" else date.data - shift)
            except (OverflowError, ValueError) as exc:  # kể cả OutOfBoundsTimedelta / OutOfBoundsDatetime (đều là ValueError)
                raise self.err(pos, f"phép cộng/trừ ngày vượt quá phạm vi cho phép ({exc})")
        raise self.err(pos, f"không thể tính «{op}» giữa {KIND_LABELS[lk]} và {KIND_LABELS[rk]}" + self.mismatch_hint(left, right))

    def mismatch_hint(self, left: _Val, right: _Val) -> str:
        hints = []
        for value, other in ((left, right), (right, left)):
            if value.column is not None and value.kind == "text" and other.kind in ("num", "date"):
                func = "so" if other.kind == "num" else "ngay"
                hints.append(f"Cột «{value.column}» được đọc là Chữ (không đủ 90% ô là {KIND_LABELS[other.kind]}); muốn ép thì viết {func}({value.column})")
        return (". " + ". ".join(hints)) if hints else ""

    def coerce_literal(self, literal: _Val, other: _Val, pos: int) -> _Val:
        """Chữ viết thẳng trong biểu thức ("18", "2024-01-31") tự đổi sang kiểu của vế còn lại."""
        if other.kind == "num":
            try:
                number = float(literal.value)
            except ValueError:
                raise self.err(pos, f"«{literal.value}» không phải số nên không so được với Số")
            if not np.isfinite(number):
                raise self.err(pos, f"«{literal.value}» không phải số hữu hạn")
            return _Val("num", self.const("num", number), literal=True, value=number)
        stamp = self.parse_date_literal(literal.value, other.fmt, pos)
        return _Val("date", self.const("date", stamp), literal=True, value=stamp)

    def compare(self, op: str, left: _Val, right: _Val, pos: int) -> pd.Series:
        if left.kind == "bool" or right.kind == "bool":
            raise self.err(pos, "không so sánh trực tiếp một điều kiện (Đúng/Sai) với giá trị khác; dùng và / hoặc / không để nối các điều kiện")
        if left.kind != right.kind:
            if right.kind == "text" and right.literal:
                right = self.coerce_literal(right, left, pos)
            elif left.kind == "text" and left.literal:
                left = self.coerce_literal(left, right, pos)
            else:
                hint = self.mismatch_hint(left, right)
                num_side = left if left.kind == "num" else right
                if {left.kind, right.kind} == {"date", "num"} and num_side.column is None:
                    # Vế Số không phải 1 cột nguyên mà là kết quả phép tính/hằng: rất có thể là ngày gõ trần (2020-01-01) bị hiểu là phép trừ
                    # 2020 - 01 - 01 = 2018 nên thành Số: nhắc viết trong dấu nháy. (Số cột so với Ngày cột như salary > join_date thì không nhắc.)
                    hint += (". " if not hint else ". ") + "Nếu muốn so với một ngày cụ thể thì viết trong dấu nháy, vd \"2024-01-31\" (ngày gõ trần như 2024-01-31 bị hiểu là phép trừ)"
                raise self.err(pos, f"không so sánh được {KIND_LABELS[left.kind]} với {KIND_LABELS[right.kind]}" + hint)
        func = _COMPARE_OPS[op]
        if left.kind == "text" and op not in ("==", "!="):
            for value in (left, right):
                if value.column is not None and value.column not in self.text_order_columns:
                    self.text_order_columns.append(value.column)
        if left.kind == "num":
            a, b = left.data.to_numpy(dtype=float), right.data.to_numpy(dtype=float)
            known = ~(np.isnan(a) | np.isnan(b))
            with np.errstate(all="ignore"):
                if op == "==":
                    values = np.abs(a - b) <= self.tol  # so bằng cho phép sai số làm tròn
                elif op == "!=":
                    values = np.abs(a - b) > self.tol
                else:
                    values = func(a, b)
        elif left.kind == "date":
            known = (left.data.notna() & right.data.notna()).to_numpy()
            values = func(left.data.to_numpy(dtype="datetime64[ns]"), right.data.to_numpy(dtype="datetime64[ns]"))
        else:
            known = (left.data.notna() & right.data.notna()).to_numpy()
            a = np.where(left.data.notna().to_numpy(), left.data.to_numpy(dtype=object), "")
            b = np.where(right.data.notna().to_numpy(), right.data.to_numpy(dtype=object), "")
            values = func(a, b)
        return _nullable(np.asarray(values, dtype=bool), known, self.index)

    def compare_chain(self, node) -> _Val:
        _, operands, ops, positions = node
        values = [self.ev(o) for o in operands]
        result = None
        for k, op in enumerate(ops):  # a < b < c  ==  a < b  và  b < c
            part = self.compare(op, values[k], values[k + 1], positions[k]).array
            result = part if result is None else (result & part)
        return _Val("bool", pd.Series(result, index=self.index))

    # ---- hàm ép kiểu ----
    def call(self, node) -> _Val:
        _, name, args, pos = node
        first = args[0]
        if name == "co":
            # có(cột): ô có giá trị -> Đúng, ô trống / "N/A"... -> Sai. Luôn biết chắc nên không bao giờ "chưa biết" (khác mọi phép so sánh).
            if first[0] != "col":
                raise self.err(pos, "có() chỉ dùng với một cột, vd có(ma_khach)")
            actual = self.resolver.resolve(first[1], self.text, first[2])
            if actual not in self.used:
                self.used.append(actual)
            return _Val("bool", _nullable(self.raw(actual).notna().to_numpy(), np.ones(self.n, dtype=bool), self.index))
        if name == "so":
            if first[0] == "col":
                return self.column(first[1], first[2], kind="number")
            value = self.ev(first)
            if value.kind == "num":
                return value
            if value.kind == "text":
                return _Val("num", self.numbers(value.data))
            raise self.err(pos, f"so() chỉ ép Chữ hoặc Số thành Số, đang là {KIND_LABELS[value.kind]}")
        if name == "ngay":
            fmt = self.forced_fmt
            if len(args) == 2:
                if args[1][0] != "str" or "%" not in args[1][1]:
                    raise self.err(pos, "khuôn ngày phải là chuỗi chữ có dấu %, vd \"%d/%m/%Y\"")
                fmt = args[1][1]
            if first[0] == "col":
                return self.column(first[1], first[2], kind="date", fmt=fmt)
            value = self.ev(first)
            if value.kind == "date":
                return value
            if value.kind == "text":
                if value.literal:
                    stamp = self.parse_date_literal(value.value, fmt, pos)
                    return _Val("date", self.const("date", stamp), literal=True, value=stamp)
                use_fmt = fmt or self.best_date_format(value.data)[0]
                return _Val("date", self.dates(value.data, use_fmt), fmt=use_fmt)
            raise self.err(pos, f"ngay() chỉ ép Chữ hoặc Ngày thành Ngày, đang là {KIND_LABELS[value.kind]}")
        # chu
        if first[0] == "col":
            return self.column(first[1], first[2], kind="text")
        value = self.ev(first)
        if value.kind == "text":
            return value
        if value.kind == "num":
            def to_text(x):
                if pd.isna(x):
                    return np.nan
                return str(int(x)) if float(x).is_integer() else repr(float(x))
            return _Val("text", value.data.map(to_text).astype(object))
        if value.kind == "date":
            return _Val("text", value.data.dt.strftime("%Y-%m-%d").astype(object))
        raise self.err(pos, "chu() không dùng cho điều kiện Đúng/Sai")


def _prepare_options(tolerance: Optional[float], date_format: Optional[str]) -> tuple:
    tol = DEFAULT_TOLERANCE if tolerance in (None, "") else float(tolerance)
    if not np.isfinite(tol) or tol < 0:
        raise ExpressionError("Sai số cho phép phải là số không âm")
    if date_format is not None and str(date_format).strip() == "":
        date_format = None
    if date_format is not None and "%" not in date_format:
        raise ExpressionError(f"Khuôn ngày phải dạng %d/%m/%Y (có dấu %), nhận được: {date_format}")
    return tol, date_format


def _build_result(evaluator: "_Evaluator", outcome: pd.Series) -> ExpressionResult:
    return ExpressionResult(
        violations=~outcome.fillna(True).astype(bool),
        unknown=outcome.isna(),
        columns_used=list(evaluator.used),
        columns=list(evaluator.info.values()),
        zero_division_rows=int(evaluator.zero_div.sum()),
        text_order_columns=[str(c) for c in evaluator.text_order_columns],
    )


def evaluate_expression(df: pd.DataFrame, expression: Optional[str], tolerance: Optional[float] = None, date_format: Optional[str] = None) -> ExpressionResult:
    """Tính biểu thức trên cả bảng. Raise ExpressionError nếu biểu thức sai (cú pháp, kiểu, cột không có)."""
    node, text = parse_expression(expression)
    tol, date_format = _prepare_options(tolerance, date_format)
    resolver = _ColumnResolver(df.columns)
    node = bind_bare_values(node, text, df, resolver)
    evaluator = _Evaluator(df, resolver, text, tol, date_format)
    root = evaluator.ev(node)
    if root.kind != "bool":
        raise ExpressionError(f"Biểu thức phải cho kết quả Đúng/Sai (một phép so sánh hoặc điều kiện, vd a > b), đang cho kết quả kiểu {KIND_LABELS[root.kind]}")
    return _build_result(evaluator, root.data)


# ---------------------------------------------------------------------------
# 5. Nếu – thì: hai ô NẾU và THÌ, mỗi ô là 1 biểu thức đầy đủ; kết quả = NẾU => THÌ
# ---------------------------------------------------------------------------
def _parse_side(label: str, source: Optional[str]):
    """Đọc 1 vế; lỗi được ghi rõ là lỗi ở vế nào (vị trí ký tự tính theo RIÊNG vế đó, không phải chuỗi ghép)."""
    try:
        return parse_expression(source)
    except ExpressionError as exc:
        raise ExpressionError(f"Vế {label}: {exc}") from None


def if_then_column_names(if_expression: Optional[str], then_expression: Optional[str]) -> list:
    """Tên cột như người dùng gõ ở cả 2 vế (NẾU trước, THÌ sau), không trùng. Dùng khi chưa có bảng dữ liệu."""
    names: list = []
    for label, source in (("NẾU", if_expression), ("THÌ", then_expression)):
        node, _text = _parse_side(label, source)
        for name, _pos in _columns_in(node):
            if name not in names:
                names.append(name)
    return names


def if_then_columns(df: pd.DataFrame, if_expression: Optional[str], then_expression: Optional[str]) -> list:
    """Tên cột THẬT (đúng như trong bảng) của cả 2 vế, không trùng -- dùng để tô ô và đặt tên rule."""
    resolver = _ColumnResolver(df.columns)
    result: list = []
    for label, source in (("NẾU", if_expression), ("THÌ", then_expression)):
        node, text = _parse_side(label, source)
        try:
            node = bind_bare_values(node, text, df, resolver)
        except ExpressionError as exc:
            raise ExpressionError(f"Vế {label}: {exc}") from None
        for name, pos in _columns_in(node):
            try:
                actual = resolver.resolve(name, text, pos)
            except ExpressionError as exc:
                raise ExpressionError(f"Vế {label}: {exc}") from None
            if actual not in result:
                result.append(actual)
    return result


def evaluate_conditional(df: pd.DataFrame, if_expression: Optional[str], then_expression: Optional[str],
                         tolerance: Optional[float] = None, date_format: Optional[str] = None) -> ExpressionResult:
    """Rule "NẾU <điều kiện> THÌ <điều kiện>": dòng vi phạm = NẾU đúng mà THÌ sai. Dòng NẾU sai thì luôn đạt; NẾU hoặc THÌ chưa biết (ô trống, sai
    kiểu...) mà chưa chắc sai thì bị bỏ qua và được đếm (logic 3 giá trị như evaluate_expression). Mỗi vế là 1 biểu thức đầy đủ (và/hoặc/không,
    so cột với cột, tính toán, ngày...). Hai vế dùng chung 1 bộ đọc cột nên 1 cột dùng ở cả 2 vế chỉ đọc 1 lần, và báo lỗi theo đúng vế."""
    tol, date_format = _prepare_options(tolerance, date_format)
    resolver = _ColumnResolver(df.columns)
    sides = []
    for label, source in (("NẾU", if_expression), ("THÌ", then_expression)):
        node, text = _parse_side(label, source)
        try:
            node = bind_bare_values(node, text, df, resolver)
        except ExpressionError as exc:
            raise ExpressionError(f"Vế {label}: {exc}") from None
        sides.append((label, node, text))
    evaluator = _Evaluator(df, resolver, sides[0][2], tol, date_format)
    values = []
    for label, node, text in sides:
        evaluator.text = text  # vị trí ký tự trong thông báo lỗi tính theo đúng vế đang tính
        try:
            value = evaluator.ev(node)
        except ExpressionError as exc:
            raise ExpressionError(f"Vế {label}: {exc}") from None
        if value.kind != "bool":
            raise ExpressionError(f"Vế {label} phải là một điều kiện Đúng/Sai (một phép so sánh như a > b, hoặc nhiều điều kiện nối bằng và / hoặc), "
                                  f"đang cho kết quả kiểu {KIND_LABELS[value.kind]}")
        values.append(value)
    a, b = values[0].data.array, values[1].data.array
    return _build_result(evaluator, pd.Series(~a | b, index=df.index))


def detect_expression_rule(df: pd.DataFrame, cfg: CrossFieldRuleConfig) -> pd.Series:
    """Cùng chữ ký với các hàm detect khác của cross_field_rules.py: Series bool cùng index với df, True = dòng CHẮC CHẮN vi phạm biểu thức."""
    return evaluate_expression(df, cfg.expression, cfg.tolerance, cfg.date_format).violations


def detect_if_then_rule(df: pd.DataFrame, cfg: CrossFieldRuleConfig) -> pd.Series:
    """Như detect_expression_rule nhưng cho rule Nếu – thì (cfg.if_expression / cfg.then_expression)."""
    return evaluate_conditional(df, cfg.if_expression, cfg.then_expression, cfg.tolerance, cfg.date_format).violations
