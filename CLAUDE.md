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
  - `cross_field_rules.py` — 4 hàm detect RULE LIÊN CỘT (mục 7 dưới đây):
    `detect_compare_rule`, `detect_conditional_rule`, `detect_formula_rule`,
    `detect_functional_dependency_rule` + registry `CROSS_FIELD_RULE_DETECTORS`
    + `describe_rule()`. Formula dùng "máy diễn giải" `ast` tự viết tay
    (whitelist theo NODE TYPE: chỉ +,-,*,/, số, tên cột) -- KHÔNG dùng
    `eval()`/`exec()` (đã test kỹ, xem `FormulaError`).
  - `pipeline.py` — `load_data()`, `detect_noise()` (nhận thêm
    `cross_field_rules` tuỳ chọn), `get_flagged_rows()`.
  - `attribute_handling.py` — **ĐÃ CODE XONG** bảng quyết định dtype×noise_type
    (mục 6 dưới đây): `get_available_actions(dtype, noise_type)` +
    `HandlingAction` (enum: remove_row/impute_mean/impute_median/impute_knn/
    impute_mode/fixed_value/cap_to_range/auto_normalize_category/
    auto_clean_whitespace/keep) + `apply_handling(df, column_configs, findings,
    handling_choices, duplicate_handling=None)` thực thi xử lý thật, trả về
    (df đã làm sạch, stats). `impute_knn` tự viết tay (KHÔNG phụ thuộc
    scikit-learn) -- KNN thủ công dựa trên khoảng cách Euclid trên các cột số
    khác đã chuẩn hoá z-score. Mọi giá trị số tính ra đều được ép về CHUỖI
    trước khi gán lại (DataFrame gốc đọc bằng `dtype=str`, xem
    `_format_numeric_for_column()`).
- `app.py` — Flask backend, CHỈ đóng vai trò "phiên dịch" JSON ⟷ Python object,
  KHÔNG chứa logic detect/handle (logic nằm hết ở `attribute_noise/`).
  Endpoints:
  - `POST /api/upload`
  - `POST /api/detect-noise` (payload có thêm field `cross_field_rules`,
    `check_duplicate_row`, `duplicate_subset_columns`; xem mẫu JSON trong
    `_cross_field_rule_from_json()`).
  - `POST /api/apply-handling` — **MỚI**: nhận `file_id` + LẠI đúng
    `column_configs` đã dùng ở bước detect (để backend tự chạy lại
    `detect_noise()`, không tin tưởng findings do FE tự gửi) + danh sách
    `handling_choices` + `duplicate_handling` tuỳ chọn. Trả về stats
    (`original_row_count`/`removed_row_count`/`final_row_count`) +
    `download_id`.
  - `GET /api/download/<download_id>` — **MỚI**: trả file CSV đã làm sạch
    (lưu tạm trong `CLEANED_FILES`, tách riêng khỏi `UPLOADED_FILES` để không
    ghi đè bản gốc).
  Rule/config sai (formula lỗi cú pháp, cột không tồn tại...) trả HTTP 400
  kèm message rõ ràng, không crash 500.
- `frontend/` — HTML/CSS/JS thuần (chưa dùng framework), UI dạng "panel theo
  bước" (chỉ 1 `.panel.is-active` hiện tại 1 thời điểm) với **5 bước**:
  1. Tải file lên → `POST /api/upload`.
  2. Hướng xử lý — chọn Attribute noise hay Class noise (thẻ Class noise bị
     khoá "Sắp làm", chỉ Attribute bấm được — khớp đúng roadmap ở trên).
  3. Cấu hình noise — mỗi cột hiện dạng "chip" (nút bo tròn bật/tắt) cho ĐỦ 7
     loại noise, chỉ hiện chip hợp lý với dtype đang chọn (`COLUMN_TYPES` map
     dtype → danh sách noise khả dụng trong `script.js`); tick chip nào thì
     panel tham số của chip đó (`param-panel`) mới xổ ra. State mỗi cột lưu
     trong `state.columnConfig[tên cột]` (object, KHÔNG đọc lại DOM mỗi lần
     submit — khác cách làm cũ), đồng bộ qua 1 listener `change` gắn trên
     `#col-list` (event delegation, xem `role`/`data-role`). Cộng khối
     `duplicate_row` riêng + "Rule liên cột" (đủ 4 loại, y hệt logic cũ, chỉ
     đổi class CSS: `createRuleRow()`/`buildCrossFieldRules()`).
  4. Kết quả — 3 thẻ thống kê, ô tìm kiếm (debounce) + chip lọc theo loại
     noise (dựng động từ các loại THỰC SỰ có trong `findings`), bảng có phân
     trang (20 dòng/trang) và TÔ MÀU TỪNG Ô theo đúng loại noise của ô đó
     (dựng trực tiếp từ `findings` qua `state.rowFindingsMap`, KHÔNG parse
     chuỗi `noise_reasons` bằng string-split nữa như bản cũ — mạnh hơn hẳn).
  5. Xử lý & xuất file — y hệt logic `renderHandlingSection()`/
     `apply-handling-btn` bản trước, chỉ đổi giao diện: chỉ hiện đúng cặp
     (cột, loại noise) THỰC SỰ có trong kết quả, dropdown hành động dựng từ
     `ACTION_TABLE` ở FE (PHẢI khớp `_ACTION_TABLE` trong
     `attribute_handling.py`), bấm áp dụng gọi `/api/apply-handling` rồi tự
     tải file CSV về qua `/api/download/<id>`.

  11 "family" màu (`NOISE_TYPE_META` trong `script.js`, khớp biến CSS
  `--<family>-text/soft/border` trong `style.css`) dùng chung cho chip/badge/
  tag/tô màu ô — 1 màu riêng cho mỗi loại trong 7 attribute noise + 4 rule
  liên cột.

  **QUAN TRỌNG — quyết định kiến trúc đã chốt:** trang KHÔNG có chế độ "phân
  tích cục bộ trong trình duyệt" (không viết lại IQR/regex/... bằng JS). Mọi
  detect/xử lý LUÔN gọi backend Flask thật; nếu backend chưa chạy,
  `checkBackendHealth()` sẽ báo rõ ràng ở góc trên bên phải + khoá nút Upload,
  KHÔNG âm thầm tính bằng 1 bộ máy JS khác (tránh 2 bộ máy lệch kết quả nhau).

  CSS có 1 rule CHUNG `[hidden] { display: none !important }` ở đầu
  `style.css` để tránh lặp lại bug "mọi khối field cùng hiện" đã từng gặp
  thực tế ở phần rule liên cột (author stylesheet luôn thắng user-agent
  stylesheet mặc định của trình duyệt).
- `demo.py` — script test CLI cho logic detect, KHÔNG phải sản phẩm cuối.
- `data/` — sample data test:
  - `noisy_employee_dataset.csv` + `noise_ground_truth.csv` — bộ gốc, 114 dòng.
  - `noisy_employee_dataset_large.csv` + `noise_ground_truth_large.csv` — bộ
    lớn hơn (313 dòng, 145 lỗi cấy sẵn), cùng schema 10 cột với bộ gốc nên
    `demo.py`/`COLUMN_CONFIGS` chạy thẳng không cần sửa. Ground truth ghi
    theo GIÁ TRỊ cột `id` (ổn định dù dòng bị xáo trộn), không theo vị trí
    dòng như bộ gốc.

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
6. Quy tắc quan trọng cho phần HANDLE (**ĐÃ CODE XONG** — `attribute_handling.py`
   + `POST /api/apply-handling` + `GET /api/download/<id>` + Bước 4 trên FE):
   hành động xử lý khả dụng (remove/replace/auto-clean) phải được quyết định
   dựa trên **cặp (ColumnDType, NoiseType)** — tổng quát, áp dụng cho MỌI cột,
   KHÔNG hardcode theo tên cột cụ thể (vd không được viết cứng "nếu cột tên là
   age thì..."). Bảng quyết định đã thống nhất (khớp `get_available_actions()`):

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

7. **Cross-field rule (mâu thuẫn LOGIC giữa các cột) — ĐÃ CODE XONG cả backend
   + frontend cho đủ 4 loại (`attribute_noise/cross_field_rules.py` +
   phần "Rule liên cột" ở Bước 2 trên FE):**
   7 detector hiện tại + `duplicate_row` đều KHÔNG kiểm tra quan hệ giữa 2 cột
   khác nhau (mỗi detector chỉ nhận 1 `Series`, hoặc so khớp y hệt cả dòng
   chứ không hiểu ý nghĩa quan hệ). Đây là khoảng trống thật sự cần thêm 1
   loại config mới.
   - **Bắt buộc do người dùng tự khai** (giống cách khai `min_value`/
     `valid_categories` hiện tại) — hệ thống KHÔNG thể tự suy ra quan hệ giữa
     2 cột bất kỳ chỉ từ dữ liệu, vì đó là domain knowledge riêng của từng
     file, không phổ quát như dtype.
   - 2 kiểu rule nên làm trước (dễ implement, an toàn — không cần `eval()`):
     - **Compare**: `cột_A <operator> cột_B` (`<, <=, >, >=, ==, !=`). Ví dụ:
       `ngay_bat_dau_lam <= ngay_nghi_viec`.
     - **Functional dependency**: `cột_A → cột_B` — mỗi GIÁ TRỊ của A chỉ nên
       ánh xạ tới đúng 1 GIÁ TRỊ của B (check bằng `groupby(A)[B].nunique() > 1`).
       Đây là quan hệ **1 CHIỀU** (A xác định B, không cần B xác định lại A) —
       KHÔNG phải quan hệ 1:1 hai chiều. Chỉ hợp lý khi B là thuộc tính CỐ ĐỊNH
       của thực thể mà A đại diện (vd `ma_nv → ten_nv`), TUYỆT ĐỐI không dùng
       cho cột B là kết quả 1 giao dịch/sự kiện lặp lại được (vd
       `(ten, sdt) → san_pham_mua` là SAI vì 1 khách mua nhiều đơn hàng khác
       nhau là bình thường, không phải noise).
     - Kiểu "conditional" (IF...THEN...) và "formula" (`cột_C == A op B`) để
       sau — formula cần eval biểu thức an toàn (không dùng `eval()` trần vì
       lỗ hổng code injection), phức tạp hơn nên chưa ưu tiên.
   - Rule liên cột phải TỰ BỎ QUA (coi là N/A, không kết luận đúng/sai) các ô
     đã bị `missing_value`/`format_noise` ở 1 trong 2 cột liên quan — giống
     cách `out_of_range`/`outlier` hiện tại dùng `numeric.notna()` để bỏ qua ô
     không ép được thành số. Không cần đợi user xử lý (handle) xong mới detect
     được, chỉ cần tự loại ô hỏng ra khỏi phạm vi so sánh.
   - Về mặt workflow: nên khuyến khích user xử lý (handle) xong lỗi cấp-cột
     của các cột liên quan TRƯỚC, rồi mới chạy rule liên cột — kết quả sẽ đáng
     tin hơn (ít N/A, ít nhiễu giả do dữ liệu bẩn).

## Kế hoạch tiếp theo (chưa code) — THỨ TỰ đã thống nhất

- [x] Tạo bộ dữ liệu lớn hơn để luyện lại 7 detector hiện có
      (`noisy_employee_dataset_large.csv`).
- [x] Cross-field rule detection (mục 7 ở trên) — backend
      (`cross_field_rules.py`, tích hợp vào `pipeline.py`/`app.py`) + frontend
      (phần "Rule liên cột" ở Bước 2) đã xong cho đủ 4 loại, đã test qua
      HTTP thật (upload + detect-noise) và test riêng khả năng chống code
      injection của formula (whitelist theo AST node type).
- [x] `attribute_handling.py` — bảng quyết định dtype×noise_type qua
      `get_available_actions(dtype, noise_type) -> list[HandlingAction]`,
      cộng hàm thực thi `apply_handling()` (remove_row, impute_mean/median/
      knn/mode, fixed_value, cap_to_range, auto_normalize_category,
      auto_clean_whitespace, duplicate_row keep first/last). Đã test qua
      script riêng + qua HTTP thật (Flask test client) + qua UI thật
      (Playwright, luồng đủ 4 bước, tải file CSV về thành công).
- [x] API endpoint áp dụng xử lý + xuất file CSV mới cho user tải về
      (`POST /api/apply-handling` + `GET /api/download/<id>`).
- [x] Mở rộng frontend form để chọn được đủ cả 7 loại noise + khối bật/tắt
      `duplicate_row` riêng + bước chọn cách xử lý & tải file.
- [x] Thiết kế lại giao diện frontend theo mockup người dùng gửi: 5 bước
      (thêm bước "Hướng xử lý" chọn Attribute/Class), chip UI cho noise theo
      cột, bảng kết quả có tìm kiếm + lọc theo loại + phân trang + tô màu ô,
      khung rộng hơn (1440px). KHÔNG mang theo bộ máy detect cục bộ bằng JS
      của mockup (xem lý do ở mục `frontend/` trên).
- [ ] Class noise: CHỈ bắt đầu sau khi xong HẾT các mục trên (rule + handling
      + FE đủ 7 loại — nay đã xong cả 3). Detect (distance-based / ensemble-
      based / single-learner) + handle (robust / filtering / polishing) —
      theo đúng phân loại trong bài báo "Dealing with Noise Problem in ML
      Data-sets: A Systematic Review" (Gupta & Gupta, 2019) mà project này
      dựa theo.
- [ ] (Khuyến nghị, chưa có yêu cầu code cụ thể) Đánh giá định lượng: tính
      precision/recall/F1 của 7 detector + rule liên cột so với
      `noise_ground_truth.csv`/`noise_ground_truth_large.csv` — rủi ro lớn
      nhất hiện tại cho điểm khoá luận là CHƯA có bước đánh giá định lượng nào.

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
