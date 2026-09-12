# SPARK — Noise Detection & Handling Tool

Web app phát hiện và xử lý noise trong dataset do người dùng upload (CSV/Excel).
Luồng: upload file → chọn "Attribute noise" hoặc "Class noise" (đang làm Attribute
trước, Class làm sau) → chọn từng cột + loại noise áp dụng cho cột đó → hệ thống
detect → người dùng chọn xử lý (replace/remove) từng ô/dòng lỗi → xuất file CSV mới.

## Kiến trúc hiện tại

- `attribute_noise/` — core logic Python thuần, không phụ thuộc web framework.
  - `config.py` — `NoiseType`, `ColumnDType` (enum); `ColumnNoiseConfig`,
    `DuplicateRowConfig` (dataclass cấu hình theo cột / theo dòng).
  - `detectors.py` — 7 hàm detect: `missing_value`, `format_noise`,
    `out_of_range`, `outlier`, `inconsistent_category`, `whitespace_noise`,
    `duplicate_row` + registry `DETECTORS`.
  - `pipeline.py` — `load_data()`, `detect_noise()`, `get_flagged_rows()`.
- `app.py` — Flask backend, CHỈ đóng vai trò "phiên dịch" JSON ⟷ Python object,
  KHÔNG chứa logic detect (logic nằm hết ở `attribute_noise/`).
  Endpoints: `POST /api/upload`, `POST /api/detect-noise`.
- `frontend/` — HTML/CSS/JS thuần (chưa dùng framework), demo UI có 3 bước
  (upload → chọn noise theo cột → xem kết quả). Hiện form FE mới hỗ trợ 3/7
  loại noise (missing/format/out_of_range) để demo gọn; backend đã hỗ trợ đủ 7.
- `demo.py` — script test CLI cho logic detect, KHÔNG phải sản phẩm cuối.
- `data/` — sample data test (`noisy_employee_dataset.csv`) + file đáp án
  (`noise_ground_truth.csv`) để đối chiếu kết quả detect.

## Quyết định thiết kế quan trọng (đã thống nhất)

1. Attribute noise code trước, class noise code sau.
2. Mỗi cột có 1 `ColumnNoiseConfig` riêng (dtype + noise_types + tham số) —
   sẽ được build ĐỘNG từ lựa chọn của user trên UI, không hardcode. `demo.py`
   hardcode chỉ vì mục đích test, không phải thiết kế cuối cùng.
3. `duplicate_row` là noise CẤP DÒNG (so sánh giữa các dòng), xử lý riêng qua
   `DuplicateRowConfig`, không nằm trong `ColumnNoiseConfig` (vì signature hàm
   detect khác: nhận cả DataFrame thay vì 1 Series).
4. Dòng nào có ≥1 ô lỗi thì lấy NGUYÊN CẢ DÒNG vào `flagged_rows` (yêu cầu gốc
   của user).
5. `row_number` trả cho FE là 1-based (`index + 1`) để khớp cách đếm dòng của
   Excel/CSV viewer thông thường — pandas dùng 0-based nội bộ, đã từng gây
   nhầm lẫn "lệch 1 dòng" cho user, đã fix ở commit `d49728e`.
6. Quy tắc quan trọng cho phần HANDLE (đang thiết kế, chưa code):
   hành động xử lý khả dụng (remove/replace/auto-clean) phải được quyết định
   dựa trên **cặp (ColumnDType, NoiseType)** — tổng quát, áp dụng cho MỌI cột,
   KHÔNG hardcode theo tên cột cụ thể (vd không được viết cứng "nếu cột tên là
   age thì..."). Bảng quyết định đã thống nhất:

   | dtype | noise_type | Hành động khả dụng |
   |---|---|---|
   | INTEGER/FLOAT | missing_value, format_noise | remove row / impute (mean, median, KNN) / giá trị cố định |
   | INTEGER/FLOAT | out_of_range | remove row / cap về min-max / impute / giá trị cố định |
   | INTEGER/FLOAT | outlier | remove row / cap về biên IQR / impute / giữ nguyên |
   | CATEGORY | missing_value | remove row / mode / giá trị cố định |
   | CATEGORY | inconsistent_category | tự động chuẩn hóa về giá trị chuẩn đã khớp (an toàn, ưu tiên mặc định) |
   | TEXT | whitespace_noise | tự động clean (strip/xóa ký tự lạ) — an toàn, mặc định luôn bật |
   | EMAIL/PHONE | missing_value, format_noise | CHỈ remove row hoặc giá trị cố định — KHÔNG impute (không thể đoán định danh cá nhân) |
   | DATE | missing_value, format_noise | remove row / giá trị cố định |
   | (cấp dòng) | duplicate_row | giữ 1 bản (đầu/cuối), xóa các bản còn lại |

## Kế hoạch tiếp theo (chưa code)

- [ ] `attribute_handling.py` — implement bảng quyết định ở trên qua hàm
      `get_available_actions(dtype, noise_type) -> list[str]`, cộng các hàm
      thực thi (remove_rows, impute_mean/median/knn, cap_to_range,
      normalize_category, clean_whitespace, dedupe_rows...).
- [ ] API endpoint áp dụng xử lý + xuất file CSV mới cho user tải về.
- [ ] Mở rộng frontend form để chọn được đủ cả 7 loại noise (hiện tại FE mới
      làm 3 loại cho gọn: missing/format/out_of_range).
- [ ] Class noise: detect (distance-based / ensemble-based / single-learner)
      + handle (robust / filtering / polishing) — theo đúng phân loại trong
      bài báo "Dealing with Noise Problem in ML Data-sets: A Systematic
      Review" (Gupta & Gupta, 2019) mà project này dựa theo.

## Môi trường chạy của user

- Anaconda (`(base)` env), Ubuntu, có cả VS Code lẫn PyCharm.
- User có 2 bản clone trên máy: `~/SPARK` (dùng chính thức) và
  `~/PycharmProjects/SPARK` (bản cũ/dễ lệch code — tránh dùng để đỡ nhầm lẫn).
- Chạy: `pip install -r requirements.txt` → `python3 app.py` (port 5000) →
  mở `frontend/index.html` bằng trình duyệt. Backend cần chạy ở 1 terminal
  riêng, để yên không gõ lệnh khác vào đó.

## Ghi chú giao tiếp

- User CHƯA từng học frontend/backend — khi giải thích khái niệm mới, cần
  nói rõ nguyên lý (client-server, request/response, API...), không giả định
  đã biết.
- User yêu cầu code phải có chú thích (comment) giải thích rõ, không viết
  code trần trụi không comment (khác quy ước comment tối giản mặc định).
- Giao tiếp bằng tiếng Việt.
