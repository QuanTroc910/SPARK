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
  - `POST /api/apply-handling-partial` — **MỚI, cách xử lý CHÍNH ở Bước 5**:
    xử lý TỪNG PHẦN cho ĐÚNG 1 cặp (`column`, `noise_type`) mỗi lần gọi (xem
    mục 8 dưới đây). Payload có field `rows`: danh sách
    `{row_number, action, fixed_value?}` (1-based) — MỖI DÒNG tự chọn 1
    `action` RIÊNG (không dùng chung 1 action cho cả lượt gọi nữa), server
    gom các dòng theo TỪNG action rồi chạy `apply_handling()` tuần tự từng
    nhóm trên CÙNG 1 df. Sửa trực tiếp lên `WORKING_FILES[file_id]` (bản
    "đang làm việc", tách khỏi `UPLOADED_FILES` gốc — tạo lười qua
    `_get_working_df()`), rồi detect lại trên bản mới, trả về NGUYÊN DẠNG
    response giống `/api/detect-noise` (FE tái dùng thẳng `renderStep4()`).
  - `GET /api/working-data/<file_id>` — **MỚI**: trả TOÀN BỘ dữ liệu ở trạng
    thái HIỆN TẠI (không chỉ các dòng còn lỗi) — dùng cho nút "Xem sau xử lý".
  - `POST /api/export-working` — **MỚI**: đóng gói `WORKING_FILES[file_id]`
    hiện tại (hoặc bản gốc nếu chưa xử lý gì) thành `download_id`, dùng chung
    `/api/download/<id>` để tải — đây là nút "Xuất file CSV" cuối Bước 5.
  - `POST /api/apply-handling` — bản CŨ (xử lý HẾT 1 lượt theo danh sách
    `handling_choices`), KHÔNG còn được FE gọi nữa (đã thay bằng
    `/api/apply-handling-partial` theo từng nhóm), nhưng vẫn giữ lại trong
    code vì không sai gì, không có gì phải xoá.
  - `GET /api/download/<download_id>` — trả file CSV (lưu tạm trong
    `CLEANED_FILES`, tách riêng khỏi `UPLOADED_FILES`/`WORKING_FILES`).
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
  5. Xử lý & xuất file — **XỬ LÝ TỪNG PHẦN, TỪNG DÒNG** (xem mục 8 dưới),
     KHÔNG bắt buộc xử lý hết mọi nhóm 1 lượt: mỗi nhóm (cột, loại noise) là
     1 `.handling-row` có nút "▸ tên cột" bấm để xổ bảng chi tiết
     (`renderHandlingDetail()`). Bảng chi tiết có CHECKBOX riêng từng dòng +
     1 CỘT "Xử lý" RIÊNG cho từng dòng (`pendingRowHTML()`, nằm ngay bên phải
     `noise_reasons`) — MỖI DÒNG tự chọn 1 hành động khác nhau nếu muốn, dropdown
     "Đặt hàng loạt" ở đầu nhóm chỉ để TIỆN gán nhanh cùng 1 hành động cho mọi
     dòng đang hiển thị (không phải nơi lưu lựa chọn thật). Bấm "Áp dụng"
     (`handleGroupApply()`) gửi ĐÚNG các dòng đang tick + hành động của riêng
     từng dòng lên `/api/apply-handling-partial`.
     **Sau khi Apply, bảng chi tiết KHÔNG bị đóng lại/rebuild** —
     `refreshHandledRowsInPlace()` gọi `/api/working-data/<id>` lấy giá trị
     MỚI của đúng các dòng vừa xử lý rồi thay `<tr>` tại chỗ: dòng bị XOÁ hẳn
     (remove_row/duplicate) thì gỡ khỏi bảng, dòng chỉ sửa giá trị thì hiện
     giá trị mới + nhãn "Đã xử lý" (`.handling-row-done`), dòng chưa tick vẫn
     giữ nguyên checkbox + dropdown để xử lý tiếp — người dùng thấy kết quả
     NGAY TRONG bảng đang mở, không có cảm giác "cả nhóm biến mất".
     `updateGroupSummaryAfterApply()` cập nhật lại chữ đếm ở đầu nhóm dựa
     trên số checkbox CÒN LẠI trong bảng (không cần hỏi lại server); hết
     checkbox thì khoá nốt nút Áp dụng/dropdown hàng loạt, đổi chữ thành
     "Đã xử lý xong toàn bộ ✓" (group KHÔNG bị xoá khỏi danh sách như trước).
     Sau khi 1 nhóm được Apply lần đầu, nút "👁 Xem sau xử lý" hiện ra cạnh
     nút Áp dụng (trạng thái nhớ qua `state.appliedGroups`, vì
     `renderHandlingSection()` CHỈ chạy lại khi vào Bước 5 lần đầu/sau detect
     mới, không chạy lại sau mỗi lần Apply nữa) — bấm vào mở 1 panel riêng
     (`#panel-preview`, không nằm trong 5 bước chính) xem lại TOÀN BỘ dữ liệu
     hiện tại (`/api/working-data/<id>`, có phân trang), có nút
     "← Quay lại xử lý". Nhóm `duplicate_row` dùng CHUNG cơ chế này nhưng
     KHÔNG có cột "Xử lý" (chỉ có đúng 1 việc hợp lý: xoá dòng được tick) —
     mặc định TICK SẴN các bản trùng ĐẾN SAU trong mỗi nhóm trùng, bỏ tick
     bản ĐẦU TIÊN (giữ lại), tính qua `computeDuplicateDefaultChecks()`.
     Nút "✅ Xuất file CSV" ở cuối trang KHÔNG tự xử lý gì thêm — chỉ đóng gói
     bản đang làm việc hiện tại qua `/api/export-working` rồi tải về.

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

8. **Xử lý từng phần ở Bước 5 (đã đổi từ "1 lần bấm áp dụng hết" sang xử lý
   theo TỪNG NHÓM, TỪNG DÒNG được tick) + quy tắc khi 1 dòng dính nhiều lỗi:**
   - Lý do đổi: nếu bắt người dùng cấu hình xong HẾT mọi nhóm rồi mới bấm 1
     nút áp dụng chung, họ không kiểm soát được xử lý dòng nào bằng cách nào
     một cách linh hoạt (vd 2 dòng cùng thiếu `age` nhưng muốn xử lý khác
     nhau: 1 dòng điền trung bình, 1 dòng điền tay). Giải pháp: mỗi nhóm
     (cột, loại noise) tự có nút "Áp dụng" RIÊNG + bảng chi tiết có checkbox
     từng dòng — người dùng tick 1 phần hoặc tick hết rồi Áp dụng, xong quay
     lại tick phần còn lại với hành động khác, KHÔNG giới hạn số lần.
   - Backend giữ 1 bản **"đang làm việc"** riêng cho mỗi `file_id`
     (`WORKING_FILES`, tách khỏi `UPLOADED_FILES` gốc — không bao giờ đổi),
     mỗi lần gọi `/api/apply-handling-partial` sửa TRỰC TIẾP lên bản này rồi
     detect lại để biết còn lỗi gì. `row_number` (1-based, = `index + 1`)
     ỔN ĐỊNH qua nhiều lần sửa vì `DataFrame.drop()` KHÔNG tự đánh số lại index
     còn lại — đây là lý do cả hệ thống dựa vào `row_number` để tham chiếu
     dòng xuyên suốt nhiều lần gọi API mà không bị lệch.
   - **1 dòng dính lỗi ở ≥2 cột khác nhau, được xử lý bằng 2 lượt Apply khác
     nhau (vd `join_date` chọn xoá dòng, `performance_score` chọn cap về biên)
     thì dòng đó VẪN BỊ XOÁ** — nguyên tắc **HỢP NHẤT (UNION)**: hành động
     `remove_row` luôn "thắng", vì ý nghĩa của việc chọn xoá dòng cho 1 loại
     lỗi là "không tin bất kỳ dòng nào dính lỗi này", không phụ thuộc các cột
     khác đã được sửa hay chưa. Đã giải thích rõ cho user, KHÔNG cần sửa gì
     thêm cho case này (hành vi hiện tại đã đúng ý, chỉ cần biết để giải
     thích trong khoá luận).
   - Nút "👁 Xem dữ liệu sau xử lý" mở 1 panel riêng NGOÀI 5 bước chính
     (`#panel-preview`) xem TOÀN BỘ dữ liệu hiện tại (không chỉ dòng còn lỗi)
     qua `GET /api/working-data/<file_id>`, có nút quay lại Bước 5.
   - Nút "Xuất file CSV" cuối Bước 5 CHỈ đóng gói bản đang làm việc hiện tại
     (`POST /api/export-working`) để tải về — không tự chạy thêm xử lý nào.

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
