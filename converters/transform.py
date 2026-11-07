"""Logic thuần Python cho 3 tool "Convert" (đổi delimiter CSV, CSV -> JSON,
JSON -> CSV) -- KHÔNG phụ thuộc Flask, cùng triết lý tách lõi/web với
attribute_noise/ và class_noise/ (app.py chỉ "phiên dịch" JSON <-> gọi hàm ở
đây, không chứa logic convert thật).

Khác attribute_noise/class_noise (đọc dữ liệu BẢNG để tìm/sửa noise, dùng
pandas), 3 tool này chỉ ĐỔI ĐỊNH DẠNG chứ không cần hiểu ý nghĩa cột/dtype --
cố tình dùng module `csv`/`json` chuẩn của Python thay vì pandas, vì pandas
hay "giúp đỡ" quá tay lúc đọc/ghi (vd tự ép "007" thành số 7, tự suy đoán ô
rỗng là NaN) đúng kiểu rủi ro mà attribute_noise/pipeline.py::load_data() đã
phải tắt bằng dtype=str/keep_default_na=False -- ở đây đơn giản hơn là dùng
thẳng csv/json chuẩn, giữ nguyên văn từng giá trị theo đúng ý người dùng.
"""

import csv
import io
import json


class ConversionError(Exception):
    """Lỗi nghiệp vụ convert (JSON sai cú pháp, không đoán được delimiter,
    file rỗng...) -- app.py bắt lỗi này để trả HTTP 400 kèm message rõ ràng,
    cùng cách các module khác trong dự án làm (vd AccountError, FormulaError)."""


# 4 delimiter phổ biến nhất của file CSV -- khớp đúng 4 lựa chọn trong
# dropdown "FROM"/"TO" của tool tham khảo (CYD). Dict thay vì list để FE có
# sẵn nhãn tiếng Việt khi cần hiện dropdown (không bắt buộc dùng, FE có thể
# tự định nghĩa nhãn riêng).
DELIMITER_LABELS = {
    ",": "Dấu phẩy (,)",
    ";": "Dấu chấm phẩy (;)",
    "\t": "Tab",
    "|": "Dấu gạch đứng (|)",
}
_CANDIDATE_DELIMITERS = list(DELIMITER_LABELS.keys())


def detect_delimiter(sample_text: str) -> str:
    """Đoán delimiter CSV đang dùng trong `sample_text`.

    Thử `csv.Sniffer` (thư viện chuẩn Python, đọc vài dòng đầu để đoán dựa
    trên tần suất + tính đều đặn của ký tự) trước. Sniffer đôi khi bó tay với
    file quá ngắn hoặc dữ liệu mơ hồ (vd chỉ 1 dòng, hoặc giá trị cũng chứa
    ký tự giống delimiter) -- lúc đó dự phòng bằng cách tự đếm: delimiter nào
    xuất hiện ĐỀU nhất (số lần xuất hiện ở dòng ÍT nhất vẫn > 0) trong 10 dòng
    đầu thì chọn delimiter đó, vì 1 CSV hợp lệ phải có số cột ổn định mỗi dòng.
    """
    sample = sample_text[:8192]  # vài KB đầu đủ để đoán, file lớn không cần đọc hết
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters="".join(_CANDIDATE_DELIMITERS))
        if dialect.delimiter in _CANDIDATE_DELIMITERS:
            return dialect.delimiter
    except csv.Error:
        pass

    lines = [line for line in sample.splitlines() if line.strip()][:10]
    if not lines:
        raise ConversionError("File rỗng, không đoán được delimiter")
    best_delim, best_score = None, 0
    for delim in _CANDIDATE_DELIMITERS:
        counts = [line.count(delim) for line in lines]
        score = min(counts)  # dòng xuất hiện ÍT delimiter nhất quyết định "độ đều"
        if score > best_score:
            best_delim, best_score = delim, score
    if best_delim is None:
        raise ConversionError("Không đoán được delimiter đang dùng trong file -- hãy chọn tay")
    return best_delim


def _read_csv_rows(text: str, delimiter: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text), delimiter=delimiter))


def convert_csv_delimiter(text: str, from_delimiter: str, to_delimiter: str) -> tuple[str, str]:
    """Đổi delimiter của 1 file CSV. `from_delimiter="auto"` thì tự đoán qua
    detect_delimiter() trước.

    Chỉ đổi KÝ TỰ PHÂN CÁCH, không đụng tới nội dung từng ô -- `csv.writer`
    tự động bọc dấu ngoặc kép quanh ô nào có chứa delimiter MỚI (hoặc dấu
    ngoặc kép, hoặc xuống dòng) bên trong, nên không phá vỡ cấu trúc cột dù
    đổi sang delimiter khác (đúng tinh thần "without breaking quoted values").

    Trả về (text đã đổi, delimiter THẬT đã dùng để đọc) -- vế sau để FE hiện
    "đã tự nhận diện: dấu chấm phẩy" khi người dùng chọn "Tự nhận diện".
    """
    used_from = detect_delimiter(text) if from_delimiter == "auto" else from_delimiter
    rows = _read_csv_rows(text, used_from)
    rows = [r for r in rows if r]  # bỏ dòng trắng hoàn toàn (vd dòng cuối file)
    if not rows:
        raise ConversionError("File CSV rỗng")

    out = io.StringIO()
    # lineterminator="\n": csv.writer mặc định dùng "\r\n" (đúng chuẩn CSV gốc),
    # nhưng ép về "\n" cho NHẤT QUÁN với cách pandas .to_csv() ở chỗ khác trong
    # app xuất file (vd /api/download/<id>) -- tránh 2 kiểu xuống dòng khác nhau
    # giữa các tool CSV trong cùng 1 app, dễ gây khó hiểu khi so sánh output.
    csv.writer(out, delimiter=to_delimiter, lineterminator="\n").writerows(rows)
    return out.getvalue(), used_from


def _convert_scalar(value: str, convert_types: bool) -> "str | int | float | bool":
    """Ép 1 ô CSV (luôn là chuỗi) sang kiểu JSON hợp lý nếu convert_types=True.

    GIỮ NGUYÊN DẠNG CHUỖI nếu có số 0 ở đầu (vd mã sản phẩm "007", số điện
    thoại "0912..."): ép thành số sẽ XOÁ MẤT số 0 đó (int("007")==7), đổi hẳn
    ý nghĩa dữ liệu -- khớp đúng lưu ý "Leading zeros stay text" của tool
    tham khảo. "0.5" vẫn được ép thành số bình thường (số 0 đứng trước dấu
    chấm thập phân không phải "số 0 thừa").
    """
    if not convert_types or value == "":
        return value
    low = value.lower()
    if low in ("true", "false"):
        return low == "true"

    bare = value[1:] if value.startswith("-") else value
    if len(bare) > 1 and bare[0] == "0" and bare[1] != ".":
        return value  # số 0 ở đầu (không phải "0.x") -- giữ nguyên chuỗi

    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def csv_text_to_json(
    text: str,
    has_header: bool,
    delimiter: str = "auto",
    as_array_of_arrays: bool = False,
    convert_types: bool = True,
    indent: bool = True,
) -> tuple[str, str]:
    """CSV -> JSON. Mặc định (`has_header=True, as_array_of_arrays=False`)
    mỗi dòng thành 1 object, khoá = tên cột lấy từ dòng header đầu tiên --
    đây là dạng JSON hữu ích nhất để dùng lại (mỗi object tự mô tả nó là gì,
    không cần nhớ thứ tự cột). `as_array_of_arrays=True` (hoặc file không có
    header) thì mỗi dòng thành 1 array thuần, không có tên khoá.

    Trả về (JSON text, delimiter THẬT đã dùng để đọc), giống convert_csv_delimiter().
    """
    used_delimiter = detect_delimiter(text) if delimiter == "auto" else delimiter
    rows = _read_csv_rows(text, used_delimiter)
    rows = [r for r in rows if r]
    if not rows:
        raise ConversionError("File CSV rỗng")

    if has_header and not as_array_of_arrays:
        header, *data_rows = rows
        result = [
            {header[i]: _convert_scalar(row[i] if i < len(row) else "", convert_types) for i in range(len(header))}
            for row in data_rows
        ]
    else:
        data_rows = rows[1:] if has_header else rows
        result = [[_convert_scalar(v, convert_types) for v in row] for row in data_rows]

    return json.dumps(result, ensure_ascii=False, indent=2 if indent else None), used_delimiter


def _flatten(obj: dict, prefix: str = "") -> dict:
    """Làm phẳng 1 object JSON lồng nhau thành dict 1 cấp, khoá nối bằng dấu
    chấm (vd {"address": {"city": "HN"}} -> {"address.city": "HN"}) -- khớp
    mô tả "nested objects flattened into columns" của tool tham khảo. List
    lồng bên trong KHÔNG làm phẳng tiếp (giữ nguyên dạng JSON string khi ghi
    ra CSV) vì không có quy ước chung hợp lý nào để trải 1 list thành nhiều
    cột (số phần tử mỗi object có thể khác nhau).
    """
    flat = {}
    for key, value in obj.items():
        new_key = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            flat.update(_flatten(value, new_key))
        else:
            flat[new_key] = value
    return flat


def _parse_json_records(text: str) -> list:
    """Chấp nhận CẢ 2 dạng: 1 JSON array/object lớn DUY NHẤT, HOẶC JSON Lines
    (mỗi dòng 1 object JSON riêng biệt, không có dấu `,`/`[]` bao ngoài) --
    tool tham khảo cũng ghi rõ hỗ trợ cả 2 dạng ("JSON array or JSON Lines")."""
    stripped = text.strip()
    if not stripped:
        raise ConversionError("Nội dung JSON rỗng")
    try:
        data = json.loads(stripped)
        if isinstance(data, list):
            return data
        return [data]
    except json.JSONDecodeError:
        pass

    records = []
    for line_no, line in enumerate(stripped.splitlines(), start=1):
        line = line.strip().rstrip(",")
        if not line or line in ("[", "]"):
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ConversionError(f"Dòng {line_no} không phải JSON hợp lệ: {exc.msg}") from exc
    if not records:
        raise ConversionError("Không đọc được object JSON nào -- kiểm tra lại cú pháp")
    return records


def json_text_to_csv(text: str, output_delimiter: str = ",") -> tuple[str, list[str]]:
    """JSON (array object hoặc JSON Lines) -> CSV.

    Cột = HỢP (union) mọi khoá xuất hiện ở BẤT KỲ object nào, không chỉ
    object đầu tiên -- object nào thiếu khoá thì để ô trống, tránh mất dữ
    liệu nếu các object không đồng nhất cấu trúc hoàn toàn (rất hay gặp với
    dữ liệu JSON thật, khác bảng CSV vốn LUÔN đủ cột mỗi dòng).

    Trả về (CSV text, danh sách tên cột) -- vế sau để FE hiện preview nhanh
    không cần tự parse lại CSV text.
    """
    records = _parse_json_records(text)
    flat_records = [_flatten(r) if isinstance(r, dict) else {"value": r} for r in records]

    columns: list[str] = []
    seen: set[str] = set()
    for rec in flat_records:
        for key in rec.keys():
            if key not in seen:
                seen.add(key)
                columns.append(key)
    if not columns:
        raise ConversionError("Không tìm thấy cột nào -- object JSON rỗng?")

    out = io.StringIO()
    writer = csv.writer(out, delimiter=output_delimiter, lineterminator="\n")
    writer.writerow(columns)
    for rec in flat_records:
        row = []
        for col in columns:
            value = rec.get(col, "")
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            elif value is None:
                value = ""
            elif isinstance(value, bool):
                value = "true" if value else "false"
            row.append(value)
        writer.writerow(row)
    return out.getvalue(), columns
