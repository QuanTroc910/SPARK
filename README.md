# Denoise — ứng dụng web phát hiện và xử lý nhiễu trong dữ liệu dạng bảng

Mã nguồn của khóa luận tốt nghiệp *"Xây dựng ứng dụng web phát hiện và xử lý nhiễu trong dữ liệu dạng bảng"*
(Nguyễn Minh Quân, mã sinh viên 11236189, Khoa Công nghệ thông tin, Đại học Kinh tế Quốc dân; GVHD TS. Đặng Minh Quân).

Denoise cho người dùng tải một bảng dữ liệu (CSV, Excel) lên rồi xử lý hai loại nhiễu mà không phải viết mã:

- **Attribute noise** (lỗi trong từng ô): tám công cụ ở hai nhóm *Tự động* (xóa dòng trùng, cắt khoảng trắng, xử lý ô trống,
  sửa sai định dạng) và *Cần cấu hình* (ngoài khoảng, bất thường IQR/Z-score, không nhất quán, quy tắc liên cột gồm biểu thức
  logic và phụ thuộc hàm), chạy nối tiếp được trên cùng một bảng; thêm ba công cụ chuyển đổi định dạng.
- **Class noise** (nhãn sai): một nút *Phát hiện nhãn sai* tự bỏ cột không dùng được, chọn cột có ích bằng Boruta, chạy
  Mutual k-NN và Confident Learning (Random Forest) rồi gộp hai danh sách theo hạng phần trăm, kèm nhãn gợi ý cho từng dòng.

Mọi thao tác xóa dòng hay đổi nhãn đều qua chạy thử và hộp xác nhận, và hoàn tác được.

## Cài đặt và chạy

Cần Python 3 (đã chạy trên Python 3.13). Từ thư mục gốc của mã nguồn:

```bash
pip install -r requirements.txt
python app.py
```

Mở trình duyệt tại **http://localhost:5000**, đăng ký tài khoản rồi dùng. Phải mở qua địa chỉ của máy chủ, không mở trực
tiếp tệp `frontend/workspace.html`, vì cookie đăng nhập chỉ được gửi khi trang web và API cùng nguồn gốc.

Tệp Excel định dạng `.xls` cũ cần cài thêm `pip install xlrd`; tệp `.xlsx` và CSV không cần.

| Biến môi trường | Mặc định | Ý nghĩa |
|---|---|---|
| `SPARK_SECRET_KEY` | tự tạo và lưu vào `.spark_secret_key` ở lần chạy đầu | Khóa ký phiên đăng nhập |
| `SPARK_FILE_TTL_MINUTES` | `60` | Tệp không được dùng quá số phút này bị xóa khỏi bộ nhớ |
| `SPARK_DEBUG` | tắt | Đặt `1` để bật chế độ debug của Flask khi phát triển |

Tài khoản được lưu trong `spark_accounts.db` (SQLite). Bảng dữ liệu tải lên chỉ nằm trong bộ nhớ máy chủ, mất khi máy chủ
khởi động lại.

## Cấu trúc thư mục

| Thư mục, tệp | Nội dung |
|---|---|
| `app.py` | Máy chủ Flask: định tuyến API, xác thực phiên, kiểm tra chủ sở hữu tệp, giữ bản đang làm việc |
| `attribute_noise/` | Phát hiện và xử lý attribute noise, ngôn ngữ biểu thức, phụ thuộc hàm, các công cụ nhóm Tự động |
| `class_noise/` | Bước chuẩn bị dữ liệu, Boruta, Confident Learning, Mutual k-NN và bộ kết hợp hai thuật toán |
| `converters/` | Đổi dấu phân cách, chuyển CSV sang JSON và ngược lại |
| `accounts/` | Đăng ký, đăng nhập, băm mật khẩu, lưu tài khoản trong SQLite |
| `frontend/` | Giao diện: `workspace.html`, `workspace.css`, `style.css`, `workspace.js`, `workspace-flow.js` |
| `tests/` | Kiểm thử tự động cho Boruta, luật đa số của phụ thuộc hàm và việc tự xóa dữ liệu cũ khỏi bộ nhớ |
| `experiments/` | Script tạo các số liệu ở Chương 4 của khóa luận (xem `experiments/README.md`) |
| `data/benchmarks/` | Năm bộ dữ liệu dùng để đánh giá (xem bên dưới) |
| `requirements.txt` | Danh sách thư viện |

## Dữ liệu đánh giá (`data/benchmarks/`)

| Tệp | Nội dung | Nguồn |
|---|---|---|
| `beers_dirty.csv`, `beers_clean.csv` | Beers, 2.410 dòng × 11 cột, bản chứa lỗi và bản sạch | Kho mã của Raha (Mahdavi và cộng sự, SIGMOD 2019) |
| `hospital_dirty.csv`, `hospital_clean.csv` | Hospital, 1.000 dòng × 20 cột, bản chứa lỗi và bản sạch | Kho mã của Raha |
| `hospital_constraints.txt` | 15 ràng buộc của Hospital (dùng 13 ràng buộc một cột xác định) | Kho mã của HoloClean |
| `pendigits.csv` | Pendigits, 10.992 dòng × 16 cột đặc trưng, 10 lớp, cột nhãn `target` | UCI, bản của PMLB |
| `letter.csv` | Letter Recognition, 20.000 dòng × 16 cột, 26 lớp | UCI, bản của PMLB |
| `waveform_40.csv` | Waveform-40, 5.000 dòng × 40 cột, 3 lớp | UCI, bản của PMLB |

Các tệp này tải thẳng lên giao diện được để thử.

## Chạy lại thực nghiệm và kiểm thử

Chạy từ thư mục gốc, không cần bật máy chủ:

```bash
python experiments/attribute_beers.py        # Bảng 4.3 phần Beers (vài giây)
python experiments/attribute_hospital.py     # Bảng 4.3 phần Hospital và Bảng 4.4 (vài giây)
python experiments/class_noise_web.py        # 90 lần phát hiện nhãn sai (khoảng 25 phút, máy 2 nhân)
python experiments/class_noise_report.py     # Bảng 4.5, 4.6, 4.7 và kiểm định Wilcoxon

python tests/test_boruta.py
python tests/test_fd_majority.py
python tests/test_purge.py
```

Kết quả class noise được ghi vào `results/class_noise.jsonl`. Cách đổi nhãn cố định theo hạt giống và mức nhiễu, nên cùng
phiên bản thư viện cho đúng các số đã báo cáo; số trong khóa luận đo với pandas 3.0 và scikit-learn 1.9.
