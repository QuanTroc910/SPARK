# Web app Dò & Xử Lý Nhiễu Dữ Liệu

Web app phát hiện và xử lý noise trong dataset do người dùng upload (CSV/Excel).
Luồng: upload file → chọn "Attribute noise" hoặc "Class noise" → (Attribute) chọn
từng cột + loại noise áp dụng cho cột đó / (Class) chọn cột nhãn + đặc trưng →
hệ thống detect → người dùng xem kết quả (Attribute: xử lý replace/remove từng
ô/dòng lỗi rồi xuất file; Class: xem danh sách dòng nghi ngờ sai nhãn — phần xử
lý/handling cho Class noise CHƯA làm, xem roadmap cuối file).

Tên hiển thị trên UI đã đổi từ "SPARK" (tên đặt tạm lúc đầu, không có ý nghĩa gì)
thành "Dò & Xử Lý Nhiễu Dữ Liệu" — code/thư mục vẫn giữ nguyên tên `SPARK` cho
tới khi có nhu cầu đổi tên repo thật sự.

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
- `class_noise/` — core logic phát hiện CLASS NOISE, cũng thuần Python,
  không phụ thuộc Flask (giống triết lý `attribute_noise/`). Dùng thuật
  toán **Confident Learning** (Northcutt et al., JAIR 2021) với **Random
  Forest** (scikit-learn) làm model nền:
  - `config.py` — `ClassNoiseConfig` (dataclass: `label_column`,
    `feature_columns`, `n_estimators=300`, `cv_folds=5`, `random_state=42`).
    Khác attribute noise, class noise là bài toán supervised học CÓ GIÁM
    SÁT — người dùng PHẢI tự khai cột nào là nhãn, cột nào là đặc trưng
    (hệ thống không tự suy ra được, giống tinh thần rule liên cột ở mục 7).
  - `confident_learning.py` — 4 bước: (1) `get_out_of_fold_probs()` train
    Random Forest (`class_weight="balanced"`) qua `StratifiedKFold` +
    `cross_val_predict` lấy xác suất "trung thực" (out-of-fold) cho MỌI
    dòng; (2) `_compute_class_thresholds()` tính ngưỡng tự tin riêng từng
    lớp = trung bình `P(lớp đó)` trên các dòng THẬT thuộc lớp đó; (3)
    `_find_confident_classes()` với mỗi dòng, lọc lớp vượt ngưỡng riêng
    của chính nó, chọn lớp xác suất cao nhất; (4) trong
    `detect_class_noise()` so với nhãn ghi — lệch thì gắn cờ
    (`ClassNoiseFinding`: `row_number` 1-based, `recorded_label`,
    `confident_label`, `margin`). Trả về `ClassNoiseResult` gồm `findings`
    (đã sắp theo `margin` giảm dần) + `diagnostics`
    (`ClassNoiseDiagnostics`: `cv_accuracy`, `majority_baseline_accuracy`,
    `class_thresholds`, `per_class_report` từ
    `sklearn.metrics.classification_report`, `confusion_count_matrix`) —
    **PHẢI xem diagnostics trước khi tin findings**: nếu `cv_accuracy` chỉ
    nhỉnh hơn/thấp hơn `majority_baseline_accuracy` thì model gần như
    không học được gì từ `feature_columns`, findings không đáng tin (bài
    học rút ra từ thử nghiệm thật trên dữ liệu thầy cung cấp — xem lịch sử
    chat, dữ liệu đó chỉ có 3 đặc trưng, recall lớp hiếm ~30%, thấp hơn hẳn
    khi thử trên 2 bộ Kaggle khác có nhiều đặc trưng hơn — KHÔNG phải lỗi
    thuật toán, đã kiểm chứng bằng thí nghiệm có đối chứng).
  - `feature_selection.py` — **MỚI, GIẢM SỐ CỘT trước khi chạy Confident
    Learning** (theo yêu cầu thầy sau buổi báo cáo — xem mục 9 dưới đây để
    biết đầy đủ lý do/lịch sử quyết định): `rank_by_importance()` (Bước 1 —
    train 1 Random Forest, đọc `feature_importances_`, xếp hạng cột theo mức
    LIÊN QUAN TỚI NHÃN) + `select_by_elbow()` (TỰ chọn giữ bao nhiêu cột
    bằng Elbow Method — tìm vị trí tỉ lệ `importance[i]/importance[i-1]`
    THẤP NHẤT, KHÔNG cần tự chọn tay % hay số cột nào) + `filter_correlated()`
    (Bước 2 — loại cột THỪA THÔNG TIN LẪN NHAU, tương quan ≥ 0.8 giữa 2 cột
    CÒN LẠI với nhau, không liên quan nhãn) + `cap_outliers()` (Bước 3a —
    cap outlier về biên IQR/Z-score, TÁI DÙNG `detect_outlier()` +
    `apply_handling()` có sẵn ở `attribute_noise/`; BỎ QUA cột có IQR/độ
    lệch chuẩn SUY BIẾN = 0 — lỗi thật đã gặp: `capital.gain`/`capital.loss`
    của Adult Income "zero-inflated" (Q1=Q3=0) khiến mọi giá trị khác 0 bị
    ép về 0, xoá sạch tín hiệu quan trọng nhất, làm CV accuracy tụt DƯỚI
    baseline — đã fix bằng cách bỏ qua cột suy biến thay vì cap sai) +
    `log_transform()` (Bước 3b — `ln(x+1)` cho cột KHÔNG có giá trị âm, giữ
    nguyên cột có âm; bản đầu lặp Python từng dòng GẦN TREO MÁY trên 284k
    dòng, đã sửa sang gán vector hoá, còn 0.53s).
  Dùng lại `attribute_noise/pipeline.py::load_data()` để đọc file (không
  viết lại hàm đọc CSV/Excel riêng). Có `demo_class_noise.py` ở gốc repo để
  chạy thử CLI, và 1 loạt file `demo_*.py` KHÁC (`demo_model_don_gian.py`,
  `demo_decision_tree_tu_viet.py`, `demo_random_forest_tu_viet.py`,
  `demo_random_forest_ra_gi.py`, `demo_test_accuracy.py`,
  `demo_ablation_3features.py`, `demo_kaggle_comparison.py`) — các file này
  THUẦN PHỤC VỤ GIẢI THÍCH/HỌC (viết tay lại Decision Tree/Random Forest
  không dùng sklearn, so sánh với dữ liệu Kaggle...), KHÔNG phải code sản
  phẩm, không bị import bởi `app.py`/`class_noise/`.
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
  - `POST /api/class-noise/detect` — **MỚI, hướng Class noise**: nhận
    `file_id` (DÙNG CHUNG `/api/upload` với hướng attribute, không có upload
    riêng) + `label_column` + `feature_columns` (+ tuỳ chọn `n_estimators`,
    `cv_folds`), gọi thẳng `class_noise/confident_learning.py::detect_class_noise()`,
    trả về `diagnostics` (cv_accuracy, baseline, ngưỡng từng lớp, precision/
    recall/F1, ma trận đếm — JSON-hoá bằng `.values.tolist()` vì
    `confusion_count_matrix` là `pd.DataFrame`) + `findings` (đã sắp theo
    margin giảm dần). CHẠY ĐỒNG BỘ (block request), có thể mất VÀI PHÚT với
    file lớn — không có thanh tiến trình, chấp nhận được cho quy mô demo
    khoá luận. `app.run(..., threaded=True)` để request này không chặn các
    request khác trong lúc chờ. Validate `feature_columns` đều "đủ số"
    (`_is_mostly_numeric()`) TRƯỚC khi chạy, báo lỗi nêu đúng tên cột chữ
    nếu sai (cùng lỗi "0 dòng dùng được" như `reduce-features`, lúc đầu CHỈ
    fix ở `reduce-features`, sau phát hiện endpoint này cũng dính y hệt vì
    người dùng tick tay feature chữ được, đã fix bổ sung). **LUÔN** chạy
    `cap_outliers()` + `log_transform()` (Bước 3, xem `feature_selection.py`)
    lên `feature_columns` TRƯỚC khi train — không phải tuỳ chọn, vì 2 hàm
    này chỉ sửa giá trị, không xoá dòng/cột.
  - `POST /api/class-noise/reduce-features` — **MỚI**: chạy
    `rank_by_importance()` → `select_by_elbow()` → `filter_correlated()`
    (xem `class_noise/feature_selection.py` ở mục kiến trúc trên) trên TẤT
    CẢ cột trừ cột đang là nhãn, trả về cả bảng xếp hạng đầy đủ lẫn 2 danh
    sách cột sau mỗi bước. TỰ LỌC BỎ cột không "đủ số" (`_is_mostly_numeric()`
    — ít nhất 90% ô không rỗng ép được thành số) khỏi candidate TRƯỚC khi
    đưa vào `rank_by_importance()` — thiếu bước này sẽ lỗi "0 dòng dùng
    được" nếu lỡ lẫn cột chữ (vd `workclass` của Adult Income) vào, vì hàm
    đó yêu cầu MỌI candidate đều là số trên CÙNG 1 dòng mới tính dòng đó
    dùng được (lỗi thật đã gặp lúc code, đã fix). CHỈ TÍNH TOÁN, KHÔNG tự
    áp dụng xuống cấu hình detect thật — FE nhận kết quả rồi tự tick lại
    checkbox đặc trưng sẵn có.
  Rule/config sai (formula lỗi cú pháp, cột không tồn tại...) trả HTTP 400
  kèm message rõ ràng, không crash 500.
- `frontend/` — HTML/CSS/JS thuần (chưa dùng framework), UI dạng "panel theo
  bước" (chỉ 1 `.panel.is-active` hiện tại 1 thời điểm) với **5 bước**:
  1. Tải file lên → `POST /api/upload`.
  2. Hướng xử lý — chọn Attribute noise hay Class noise (cả 2 thẻ đều bấm
     được từ khi có backend `/api/class-noise/detect`).
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
     1 CỘT **"Tự điều chỉnh"** RIÊNG cho từng dòng (`pendingRowHTML()`, nằm
     ngay bên phải `noise_reasons`, gồm cả lựa chọn "✏️ Tự nhập tay" =
     `fixed_value` để gõ tay giá trị áp dụng cho ĐÚNG dòng đó) — MỖI DÒNG tự
     chọn 1 hành động khác nhau nếu muốn, dropdown "Đặt hàng loạt" ở đầu nhóm
     chỉ để TIỆN gán nhanh cùng 1 hành động cho mọi dòng đang hiển thị (không
     phải nơi lưu lựa chọn thật). Cột "Tự điều chỉnh" dùng
     `position: sticky; right: 0` (class `.handling-action-col`) để LUÔN hiện
     trong tầm nhìn, không cần cuộn ngang qua chục cột dữ liệu mới thấy —
     user đã phản hồi thực tế là tưởng chưa có tính năng này chỉ vì nó bị
     khuất bên phải trước khi thêm sticky (đánh đổi: ở vị trí cuộn mặc định,
     cột này có thể đè lên phần cuối `salary`/`noise_reasons`, cuộn ngang là
     thấy lại đủ — không mất dữ liệu, chỉ là trade-off hiển thị). Bấm
     "Áp dụng" (`handleGroupApply()`) gửi ĐÚNG các dòng đang tick + hành động
     của riêng từng dòng lên `/api/apply-handling-partial`.
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
     KHÔNG có cột "Tự điều chỉnh" (chỉ có đúng 1 việc hợp lý: xoá dòng được tick) —
     mặc định TICK SẴN các bản trùng ĐẾN SAU trong mỗi nhóm trùng, bỏ tick
     bản ĐẦU TIÊN (giữ lại), tính qua `computeDuplicateDefaultChecks()`.
     Nút "✅ Xuất file CSV" ở cuối trang KHÔNG tự xử lý gì thêm — chỉ đóng gói
     bản đang làm việc hiện tại qua `/api/export-working` rồi tải về.

  **Nhánh CLASS NOISE ở Bước 3/4/5** — Bước 3/4/5 mỗi bước có 2 khung con
  nằm CHUNG 1 panel, đổi `hidden` theo `state.direction`
  (`#panel-N-attribute` / `#panel-N-class`, toggle qua `toggleStep3Direction()`/
  `toggleStep4Direction()`/`toggleStep5Direction()`, được `goStep()` tự gọi
  mỗi lần VÀO bước đó dù đi bằng nút "Tiếp tục" hay bấm thẳng stepper):
  - Bước 3 (class): dropdown chọn `label_column` (mặc định CỘT CUỐI — quy
    ước phổ biến của dữ liệu phân loại), **MỚI** khối "🪄 Giảm cột tự động"
    (nằm GIỮA ô chọn nhãn và danh sách checkbox đặc trưng — phải chọn nhãn
    trước mới bấm được) gọi `POST /api/class-noise/reduce-features`, hiện
    dòng tóm tắt "X cột gốc → Y cột (Bước 1) → Z cột (Bước 2)" + biểu đồ cột
    ngang `renderFeatureReductionChart()` (tái dùng ĐÚNG pattern
    `.chart-row`/`.chart-bar-fill` có sẵn của `renderNoiseTypeChart()`, không
    viết cơ chế vẽ mới — 1 màu `--signal` duy nhất, 3 MỨC ĐỘ ĐẬM khác nhau:
    1.0 = qua được cả 2 bước, 0.5 = qua Bước 1 nhưng bị loại Bước 2, 0.18 =
    loại ngay Bước 1) rồi TỰ TICK kết quả vào danh sách checkbox bên dưới
    (vẫn sửa tay thêm được, không khoá cứng). Đổi nhãn hoặc upload file mới
    thì ẩn kết quả cũ (tránh hiểu nhầm là ứng với nhãn/file đang chọn). Sau
    đó mới tới danh sách checkbox chọn `feature_columns` (loại trừ cột đang
    là nhãn), tham số nâng cao `n_estimators`/`cv_folds` (mặc định 300/5,
    khớp `ClassNoiseConfig`). `panel-desc` đầu Bước 3 có ghi rõ: các cột đặc
    trưng sẽ TỰ ĐỘNG được cap outlier + log-transform (Bước 3 ở mục 9) ngay
    lúc bấm "Phát hiện Class Noise" — không phải khối riêng, không cần bấm
    thêm nút nào, chỉ 1 dòng mô tả cho người dùng biết việc đang xảy ra.
  - Bước 4 (class): 3 thẻ thống kê (dòng dùng được, CV accuracy so baseline,
    số dòng nghi ngờ) + khung CẢNH BÁO màu đỏ nếu chênh lệch accuracy-baseline
    ≤ 2 điểm % (`isWeak` trong `renderClassResults()`) + bảng precision/
    recall/F1 từng lớp + ma trận đếm + bảng danh sách dòng nghi ngờ (tìm
    kiếm + phân trang 20 dòng/trang, đã sắp theo margin giảm dần từ backend).
  - Bước 5 (class): CHỈ có placeholder "đang phát triển" — xử lý/handling
    cho class noise CHƯA code (xem roadmap cuối file), nút quay lại Bước 4.

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

9. **Giảm số cột (feature selection) cho Class Noise — ĐÃ CODE XONG ĐỦ CẢ 3
   BƯỚC (`feature_selection.py`), ĐÃ NỐI VÀO WEB:**
   - Bước 1+2 (`rank_by_importance`/`select_by_elbow`/`filter_correlated`):
     nối qua `POST /api/class-noise/reduce-features` + khối "Giảm cột tự
     động" ở Bước 3 FE (TUỲ CHỌN, người dùng bấm nút, vẫn sửa tay thêm được).
   - Bước 3 (`cap_outliers`/`log_transform`): nối TRỰC TIẾP vào
     `POST /api/class-noise/detect` — LUÔN chạy tự động (KHÔNG phải tuỳ
     chọn/nút riêng), vì 2 hàm này chỉ sửa GIÁ TRỊ chứ không xoá dòng/cột
     nào nên không có rủi ro mất dữ liệu khi luôn bật. Áp dụng lên ĐÚNG
     `feature_columns` mà request gửi lên tại thời điểm detect (không phải
     cố định theo kết quả "Giảm cột tự động" trước đó), nên vẫn đúng dù
     người dùng tick tay thêm/bớt cột sau khi chạy giảm cột tự động.
   - Nguồn gốc yêu cầu: sau buổi báo cáo, thầy nói Attribute noise được
     rồi nhưng Class noise CHƯA, bước đầu phải giảm số biến — đúng với phát
     hiện đã có từ trước (dữ liệu thầy chỉ 3 đặc trưng nên model học kém).
     Thầy mô tả quy trình 3 bước: (1) giảm sơ bộ còn "tầm 8, dưới 10" biến,
     (2) kiểm tra tương quan giữa các biến còn lại, giảm thêm còn ~3-5 cột,
     (3) kiểm tra outlier + biến đổi logarit (chuẩn hoá phân phối) — có gửi
     kèm 1 ảnh chụp tài liệu khác (KHÔNG phải bài báo Gupta & Gupta ở trên,
     nguồn gốc cụ thể chưa xác định) cho thấy ma trận tương quan 3 cột
     `V44/V12/V4` (0.76/0.60/0.67, tất cả < 0.8) của chính dữ liệu thầy.
   - **Bước 1 (chọn cột liên quan tới NHÃN)** dùng Feature Importance của
     Random Forest (`rf.feature_importances_`, đo mức giảm độ "lẫn lộn"
     Gini qua các lần rẽ nhánh của 300 cây) — chọn cách này thay vì
     Permutation Importance (model-agnostic nhưng chậm hơn, cần train xong
     rồi xáo trộn từng cột đo lại accuracy) vì đây đúng use-case
     "Quick ranking in Random Forest" theo chính tài liệu tham khảo so sánh
     4 phương pháp Feature Importance phổ biến (Feature Importance Scores,
     Permutation Importance, SHAP, Information Gain).
   - **Cách chọn GIỮ BAO NHIÊU cột sau khi xếp hạng — lịch sử 3 phương án,
     2 phương án đầu đã bị LOẠI vì phát hiện lỗi/thiếu căn cứ khi kiểm
     chứng thật:**
     1. ~~Lấy cứng đúng top-8~~ — "8" chỉ là ước lượng miệng của thầy
        ("tầm 8, dưới 10"), không phải quy tắc toán học, không thích ứng
        được với dữ liệu khác.
     2. ~~`select_top_features()`: lấy đủ cột để đạt 90% importance cộng
        dồn, chặn trần `max_count=10`~~ — mượn ý tưởng quy ước PCA ("giữ đủ
        thành phần giải thích 90-95% biến thiên") nên 90% tưởng có căn cứ,
        nhưng kiểm chứng thật trên Credit Card Fraud thì `max_count=10`
        LUÔN chặn TRƯỚC khi đạt 90% thật (chỉ đạt ~80-81%) — nghĩa là cap
        10 mới là thứ quyết định kết quả, mà cap 10 cũng chỉ là ước lượng
        chưa có căn cứ vững hơn "8" cũ là bao. Đã XOÁ hẳn hàm này khỏi code
        (không giữ lại làm dự phòng, vì có lỗi thiết kế thật chứ không chỉ
        là bị thay thế).
     3. **`select_by_elbow()` — Elbow Method, ĐANG DÙNG:** tìm vị trí tỉ lệ
        `importance[cột sau] / importance[cột trước]` THẤP NHẤT trong toàn
        bộ bảng xếp hạng (điểm "gãy khúc" rõ nhất), giữ mọi cột TRƯỚC điểm
        gãy. KHÔNG cần tự chọn tay bất kỳ % hay số cột nào — cùng kỹ thuật
        dùng để chọn số thành phần trong PCA (scree plot) hay số cụm K
        trong K-means (mượn Ý TƯỞNG "elbow", KHÔNG dùng PCA/K-means thật
        trong code — chỉ là 1 ví dụ khác cho thấy kỹ thuật này có căn cứ).
        Đã verify: điểm gãy mạnh nhất trên Credit Card Fraud rơi đúng cột
        8→9 (V3→V2, tỉ lệ tụt còn ~53.5%) ở CẢ 3 mức n_estimators thử
        (200/300/500) — không phải ngẫu nhiên 1 lần; phép thử tạo cột giả
        TRÙNG LẶP y hệt 1 cột thật (tương quan = 1.0) xác nhận cơ chế lọc
        tương quan ở Bước 2 hoạt động đúng.
   - **Credit Card Fraud (29 cột `V1-28`+`Amount`, PCA-transformed) là bộ
     test TẠM THỜI, không phải dữ liệu thầy thật** (vẫn chưa xin được file
     gốc ~35 cột) — vì các cột `V` của bộ này đã qua PCA nên LUÔN có tương
     quan ~0.00 với nhau (đúng tính chất toán học của PCA: mỗi thành phần
     mới luôn trực giao/không liên quan các thành phần trước nó), khiến
     Bước 2 (lọc tương quan) không loại được cột nào trên bộ này — ĐÂY LÀ
     KẾT QUẢ ĐÚNG KỲ VỌNG, không phải lỗi, chỉ là Credit Card Fraud không
     phải bộ dữ liệu phù hợp để CHO THẤY Bước 2 có tác dụng (ngược lại, ảnh
     ma trận tương quan thật của thầy có số 0.6-0.76, không phải PCA, nên
     Bước 2 sẽ thực sự lọc được gì đó trên đúng dữ liệu mục tiêu).
   - `n_estimators` cho `rank_by_importance()` giữ mặc định 300 (khớp
     `ClassNoiseConfig`) dù đã test riêng không cần tới mức đó (100 cây đã
     cho ra ĐÚNG tập cột y hệt 500 cây trên Credit Card Fraud, chỉ thứ tự
     nội bộ các cột gần ngang nhau bị xáo trộn) — chọn 300 vì nhất quán với
     số cây dùng ở bước detect chính, dễ giải thích hơn là 2 con số khác
     nhau cho 2 chỗ train Random Forest trong cùng hệ thống.
   - **Thứ tự nội bộ Bước 3 (cap outlier TRƯỚC, log-transform SAU) + KHÔNG
     đổi chỗ Bước 3 lên trước Bước 2 — đã cân nhắc kỹ, có đánh đổi thật ở cả
     2 hướng:** nếu log TRƯỚC cap outlier thì tránh được IQR suy biến trên
     dữ liệu lệch nặng, nhưng lại khó phát hiện lỗi nhập liệu thật hơn (giá
     trị sai bị log "nén" bớt độ cực đoan, dễ lọt lưới outlier detector) —
     chọn ưu tiên bắt lỗi nhập liệu thật (cap trước) vì hậu quả bỏ sót lỗi
     thật nguy hiểm hơn hậu quả cap nhầm vài giá trị lệch-nhưng-hợp-lệ (cap
     chỉ kéo về biên, không xoá mất dữ liệu). Đổi chỗ với Bước 2 (lọc tương
     quan) thì CÀNG không nên — thầy đã mô tả thứ tự rõ ràng ("đầu tiên...
     bước tiếp theo... công việc CUỐI CÙNG là log-transform"), không phải
     chỗ mơ hồ để tự quyết, nên để nguyên, khác với thứ tự NỘI BỘ bước 3 là
     chỗ thầy không chỉ định rõ.
   - **LỖI NGHIÊM TRỌNG đã gặp + đã fix khi nối Bước 3 vào
     `/api/class-noise/detect` (luôn bật tự động)**: `cap_outliers()` lúc
     đầu áp dụng mù quáng IQR cho MỌI cột, kể cả cột có IQR SUY BIẾN (Q1=Q3,
     vd `capital.gain`/`capital.loss` của Adult Income "zero-inflated" —
     đa số = 0) — biên cap suy biến thành `[0, 0]`, khiến MỌI giá trị khác 0
     (chính là tín hiệu quan trọng nhất của 2 cột này) bị ép về 0, xoá sạch
     2.712/1.519 giá trị có ý nghĩa thật. Hậu quả đo được: CV accuracy tụt
     từ ~78% xuống **73.11%, THẤP HƠN CẢ baseline (75.92%)** — tức là sau
     "làm sạch", model tệ hơn cả đoán bừa. Đã fix: `cap_outliers()` giờ
     BỎ QUA cột có IQR (hoặc độ lệch chuẩn, nếu dùng Z-score) = 0, không cap
     gì cho cột đó — verify lại CV accuracy về 77.8% (trên baseline, hợp lý
     trở lại). Bài học: PHẢI test kỹ với dữ liệu có đặc tính "lệch/suy biến"
     (zero-inflated, ít giá trị khác nhau...) trước khi coi 1 phép biến đổi
     thống kê là "luôn an toàn" — đây là LẦN THỨ 2 vấp phải vấn đề IQR suy
     biến trên CHÍNH 2 cột này (lần đầu là lúc cân nhắc có nên chạy Attribute
     Noise outlier-cleanup cho Adult Income hay không, đã kết luận KHÔNG nên
     vì lý do tương tự — nhưng lúc nối Bước 3 vào đây lại quên mất bài học
     cũ, phải phát hiện lại lần 2 bằng thực nghiệm).

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
- [x] Class noise — DETECT: `class_noise/confident_learning.py` (Confident
      Learning + Random Forest, xem mục kiến trúc ở trên) + backend
      `POST /api/class-noise/detect` + frontend Bước 2 (bật thẻ Class
      Noise)/3 (chọn nhãn+đặc trưng)/4 (chẩn đoán + danh sách nghi ngờ). Đã
      test qua Playwright (luồng thật, không lỗi JS) + đã thử nghiệm thật
      trên dữ liệu thầy cung cấp VÀ 2 bộ Kaggle khác (Credit Card Fraud,
      Adult Income) để xác nhận thuật toán hoạt động đúng, vấn đề accuracy
      thấp trên dữ liệu thầy là do ĐẶC TRƯNG (chỉ 3 cột) chứ không phải lỗi
      code (thí nghiệm có đối chứng: tách 3/29 cột trên CÙNG 1 bộ Kaggle).
- [x] Class noise — GIẢM CỘT (mục 9 ở trên): `class_noise/feature_selection.py`
      (`rank_by_importance()` + `select_by_elbow()` + `filter_correlated()`)
      + backend `POST /api/class-noise/reduce-features` + khối "🪄 Giảm cột
      tự động" ở Bước 3 FE. Đã test qua Playwright (Adult Income, nhãn
      `income`, đúng 5/6 cột số được tự động tick) + verify kỹ bằng script
      riêng (sanity check cột trùng lặp, so sánh 200/300/500 cây, biểu đồ
      Pareto) trên Credit Card Fraud.
- [x] Class noise — GIẢM CỘT, Bước 3 (mục 9): `cap_outliers()` +
      `log_transform()` trong `feature_selection.py`, nối TRỰC TIẾP vào
      `POST /api/class-noise/detect` (LUÔN chạy tự động, không phải nút
      riêng). Đã test qua HTTP thật + bắt được VÀ FIX 1 lỗi nghiêm trọng
      (cap outlier xoá sạch tín hiệu `capital.gain`/`capital.loss` do IQR
      suy biến, CV accuracy từng tụt dưới cả baseline — xem chi tiết mục 9).
- [ ] Vẫn CHƯA có file gốc ~35 cột thật của thầy (đang chờ xin) — mọi kiểm
      chứng ở mục 9 mới chạy trên Credit Card Fraud/Adult Income (dữ liệu
      thay thế tạm thầy đồng ý dùng), chưa chạy được trên đúng dữ liệu mục
      tiêu. Cần chạy lại + đối chiếu kết quả khi có file thật.
- [ ] Class noise — HANDLE: Bước 5 hiện CHỈ có placeholder "đang phát
      triển". Cần thiết kế: hành động nào hợp lý cho 1 dòng bị gắn cờ sai
      nhãn (xoá dòng? sửa lại nhãn theo `confident_label` model gợi ý? để
      người dùng tự sửa tay?) — xem phân loại robust/filtering/polishing
      trong bài báo "Dealing with Noise Problem in ML Data-sets: A
      Systematic Review" (Gupta & Gupta, 2019) mà project này dựa theo. Đã
      so sánh kỹ 3N đại diện mỗi nhóm (Robust: Sabzevari et al. 2015,
      Filtering: Kubica & Moore 2003, Polishing: Liebchen et al. 2007) —
      Polishing có căn cứ thực nghiệm tốt nhất (kết hợp Filtering+Polishing
      cho accuracy cao nhất, ít mất dữ liệu nhất) và khớp tự nhiên với
      `confident_label` đã có sẵn trong `ClassNoiseFinding`.
- [ ] One-Hot Encoding cho cột CHỮ (category) làm đặc trưng Class Noise —
      vẫn để dành chờ ý kiến thầy; hiện tại cả danh sách checkbox đặc trưng
      LẪN endpoint `reduce-features` mới đều chỉ chấp nhận cột SỐ, cột chữ
      hoàn toàn không dùng được làm đặc trưng.
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
