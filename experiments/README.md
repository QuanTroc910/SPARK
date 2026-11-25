# Thực nghiệm (Chương 4 khóa luận)

Chạy từ thư mục gốc của mã nguồn, sau khi `pip install -r requirements.txt`. Dữ liệu nằm sẵn trong `data/benchmarks/`.

| Lệnh | Kết quả |
|---|---|
| `python experiments/attribute_beers.py` | Phần Beers của Bảng 4.3 (vài giây) |
| `python experiments/attribute_hospital.py` | Phần Hospital của Bảng 4.3 và Bảng 4.4 (vài giây) |
| `python experiments/class_noise_web.py` | 90 lần phát hiện nhãn sai: 3 bộ × 6 mức × 5 hạt giống (khoảng 25 phút trên máy 2 nhân) |
| `python experiments/class_noise_report.py` | Bảng 4.5, 4.6, 4.7 và các số ở mục 4.4 |
| `python tests/test_boruta.py`, `python tests/test_fd_majority.py` | Hai bộ kiểm thử ở Bảng 4.2 |

`class_noise_web.py` ghi thêm vào cuối tệp `results/class_noise.jsonl` (đổi bằng `--out`; chạy lại từ đầu thì xóa tệp cũ trước), mỗi lần phát hiện một dòng JSON; muốn chạy một phần thì dùng
`--datasets`, `--levels`, `--seeds` (ví dụ `--datasets pendigits --levels 0.05 --seeds 0`, khoảng 10 giây).

Nguồn dữ liệu: Beers, Hospital lấy từ kho mã của Raha (bản chứa lỗi `*_dirty.csv`, bản sạch `*_clean.csv`);
`hospital_constraints.txt` (15 ràng buộc) lấy từ kho mã của HoloClean, thực nghiệm dùng 13 ràng buộc có một cột xác định;
Pendigits, Letter Recognition, Waveform-40 là dữ liệu UCI ở dạng TSV nén của kho PMLB, cột nhãn tên `target`.
