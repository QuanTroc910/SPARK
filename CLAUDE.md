# Web app Dò & Xử Lý Nhiễu Dữ Liệu

Web app phát hiện và xử lý noise trong dataset do người dùng upload (CSV/Excel).
Luồng: upload file → chọn "Attribute noise" hoặc "Class noise" → (Attribute) chọn
từng cột + loại noise áp dụng cho cột đó / (Class) chọn cột nhãn + đặc trưng →
hệ thống detect → người dùng xem kết quả (Attribute: xử lý replace/remove từng
ô/dòng lỗi rồi xuất file; Class: xem danh sách dòng nghi ngờ sai nhãn — phần xử
lý/handling cho Class noise CHƯA làm, xem roadmap cuối file).

Tên hiển thị trên UI đã đổi từ "SPARK" (tên đặt tạm lúc đầu, không có ý nghĩa gì)
thành "Dò & Xử Lý Nhiễu Dữ Liệu", rồi thành thương hiệu **"Denoise"** (giao diện mới
`frontend/workspace.html`, xem mục 18 và bullet `frontend/` bên dưới) — code/thư mục
vẫn giữ nguyên tên `SPARK` cho tới khi có nhu cầu đổi tên repo thật sự.

**TRẠNG THÁI HIỆN TẠI (đọc trước):** giao diện chính là **Denoise** (`workspace.html` +
`workspace.js` + `workspace.css` + `workspace-flow.js`), `GET /` trả thẳng trang này.
Phần mô tả "5 bước" dài ở mục `frontend/` bên dưới là của giao diện CŨ (`index.html` +
`script.js` + `style.css`, vẫn mở được qua `/index.html`) — còn đúng cho file cũ đó nhưng
KHÔNG còn là luồng người dùng thấy. Việc nợ chưa làm xem mục 23 + cuối file.

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
    `eval()`/`exec()` (đã test kỹ, xem `FormulaError`). `describe_rule(cfg, df=None)`
    nhận thêm `df` để rule biểu thức đổi tên cột người dùng gõ sang ĐÚNG tên cột thật.
  - `expression_rules.py` — **MỚI (mục 24): bộ máy "Biểu thức"** gộp rule So sánh + Công thức
    (`RuleType.EXPRESSION`, field `CrossFieldRuleConfig.expression`; dùng thêm `tolerance`,
    `date_format`). Bộ tách từ + bộ phân tích tự viết (KHÔNG `eval`), tính theo CẢ CỘT bằng
    pandas/numpy (100k dòng < 0,3s). API: `parse_expression()`, `expression_columns(df, expr)`,
    `evaluate_expression(df, expr, tolerance, date_format) -> ExpressionResult` (violations,
    unknown, columns_used, columns = cách đọc từng cột, zero_division_rows, text_order_columns),
    `detect_expression_rule()` (đăng ký vào `CROSS_FIELD_RULE_DETECTORS`), `ExpressionError`
    (message tiếng Việt chỉ rõ vị trí). **Đợt 2 (mục 25)**: thêm toán tử `=>`/`->` (kéo theo) và `<=>`/`<->`
    (tương đương), hàm `có(cột)`, `evaluate_conditional(df, if_expr, then_expr, ...)` + `detect_if_then_rule()`
    (`RuleType.IF_THEN`, field `if_expression`/`then_expression`), `if_then_columns()`/`if_then_column_names()`.
    **Mục 28**: `column_value_counts(series, limit)` (giá trị chữ + số dòng theo ĐÚNG cách bộ máy đọc chữ: cắt khoảng trắng, bỏ ô thiếu,
    phân biệt hoa/thường) cho "chip giá trị"; câu báo lỗi "không có cột «X»" nối thêm gợi ý viết trong dấu nháy khi gõ chữ trần.
    **Mục 29**: `bind_bare_values(node, text, df, resolver)` tự nhận CHỮ TRẦN (không nháy) là giá trị của cột đứng cạnh trong phép so sánh (xem mục 29);
    `_clean_text()` = cách đọc 1 cột chữ dùng chung cho tính biểu thức, chip giá trị và chữ trần.
    Chỉ import `config.py` để `cross_field_rules.py` import được mà không vòng tròn.
  - `pipeline.py` — `load_data()`, `detect_noise()` (nhận thêm
    `cross_field_rules` tuỳ chọn), `get_flagged_rows()`, `guess_column_dtype()`
    — **MỚI (mục 12)**: đoán `ColumnDType` hợp lý nhất cho 1 cột dựa trên GIÁ
    TRỊ THẬT (không phải tên cột) -- kiểm tra thứ tự email → phone → date (thử
    4 định dạng phổ biến) → integer → float → category (≤50 giá trị khác nhau
    VÀ chiếm ≤50% số dòng không rỗng) → text (mặc định cuối). Ngưỡng 90% khớp
    (không bắt buộc 100%) để chấp nhận vài ô lỗi định dạng trong cột mà vẫn
    đoán đúng kiểu tổng thể. CHỈ dùng để TỰ CHỌN SẴN dropdown "Kiểu dữ liệu" ở
    Bước 3 FE, KHÔNG ảnh hưởng gì tới logic detect thật (`cfg.dtype` vẫn lấy
    từ lựa chọn cuối cùng của người dùng lúc bấm "Detect Noise").
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
  - `quick_tools.py` — **MỚI (mục 17 dưới đây): logic 4 "Free Tools"** (Xoá
    dòng trùng/Cắt khoảng trắng thừa/Điền-xoá ô trống đơn giản/Xoá dòng trống
    hoàn toàn) -- KHÁC HẲN `apply_handling()` ở chỗ KHÔNG cần
    `ColumnNoiseConfig`/`NoiseFinding` gì cả, chạy NGAY trên DataFrame trong
    1 lần gọi (`quick_remove_duplicates()`, `quick_trim_whitespace()`,
    `quick_fill_or_remove_blanks()`, `quick_remove_empty_rows()`, đều trả về
    `(df đã xử lý, stats dict)`). TÁI DÙNG trực tiếp
    `_clean_whitespace_value()`/`_is_missing_text()` đã có sẵn trong
    `attribute_handling.py` (import thẳng dù có dấu `_` ở đầu -- quy ước
    "riêng tư" của Python chỉ là quy ước, 2 module cùng nằm trong package
    `attribute_noise` nên chia sẻ nội bộ là hợp lý) để Free Tools và
    Workspace đầy đủ ra CÙNG 1 định nghĩa "thiếu"/"khoảng trắng thừa", không
    lệch kết quả giữa 2 luồng. `is_row_fully_empty()` là detector HOÀN TOÀN
    MỚI (dòng mà MỌI cột đều thiếu) -- cố tình KHÔNG đăng ký vào `NoiseType`
    enum/`DETECTORS` registry của `detectors.py` để không ảnh hưởng gì tới
    luồng detect chính/hệ thống chip UI Bước 3 (noise cấp dòng riêng của Free
    Tools, khác `duplicate_row` ở chỗ xét 1 dòng tự nó trống hay không,
    không so sánh GIỮA các dòng). `QuickToolError` là exception riêng
    (app.py bắt để trả HTTP 400), cùng cách `AccountError`/`ConversionError`
    đã làm cho các module khác.
  - **Cập nhật sau mục 17 (mục 19-21):**
    - `config.py`: `ColumnNoiseConfig.outlier_rules` (list `(phương pháp, ngưỡng)`,
      mặc định `None`) + `get_outlier_rules()` — kiểm NHIỀU phương pháp outlier cùng
      lúc trên 1 cột; `None`/rỗng thì dùng đúng cặp `outlier_method`/`outlier_threshold`
      cũ (kết quả giữ nguyên, đã đối chiếu với bản cũ trên 360 ca).
    - `detectors.py`: `outlier_bounds(valid_numeric, method, threshold)` là công thức
      biên IQR/Z-score DÙNG CHUNG (trả `None` nếu z-score suy biến std=0);
      `detect_outlier()` = HỢP các phương pháp (ô bị gắn cờ nếu bất thường theo BẤT KỲ
      phương pháp nào).
    - `attribute_handling.py::_resolve_cap_bounds()`: biên "kéo về biên" của outlier =
      GIAO các khoảng (biên dưới = max các biên dưới, biên trên = min các biên trên),
      vì ô bị gắn cờ khi ra ngoài khoảng của BẤT KỲ phương pháp nào.
    - `quick_tools.py` thêm cho tool "Ô trống" (gộp 3 tool cũ) và "Sai định dạng":
      `quick_handle_blanks()` (xử lý theo TỪNG cột: `column_actions` {cột: {dtype,
      action, fixed_value, cell_values}}; `cell_values` = giá trị RIÊNG từng ô cho cách
      "Điền tay từng ô"), `blank_column_summary()`, `blank_rows_for_column()`,
      `preview_blank_changes()`, `blank_mask()`; `auto_column_types()`,
      `find_format_errors()`, `quick_fix_format_noise()`, `preview_format_errors()` (Sai
      định dạng quét MỌI cột); `preview_duplicate_rows()`, `preview_trim_changes()` (cho
      nút "Xem các dòng trùng / ô đã sửa"). `quick_fill_or_remove_blanks()` và
      `quick_remove_empty_rows()` vẫn còn trong file nhưng route riêng của chúng đã gỡ.
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
  - `distance_based.py` — **MỚI, thuật toán DETECT thứ 2** cho Class noise,
    theo paper **N13** trong Bảng 6 Gupta & Gupta (2019) -- nhóm
    "Distance based" (Liu & Zhang, 2012, "Noisy data elimination using
    mutual k-nearest neighbor for classification mining", 9/9 điểm chất
    lượng trong review đó, xem mục 10 dưới đây để biết đầy đủ lý do chọn).
    KHÁC HẲN `confident_learning.py` ở chỗ KHÔNG train model học máy nào --
    thuần dựa vào khoảng cách Euclid (sau chuẩn hoá z-score) giữa các dòng:
    `detect_class_noise_distance(df, config, k=5, disagreement_threshold=0.5)`
    tìm k láng giềng gần nhất mỗi dòng (`sklearn.neighbors.NearestNeighbors`),
    lọc còn láng giềng LẪN NHAU (quan hệ 2 CHIỀU -- A trong top-k của B VÀ B
    trong top-k của A, tránh báo nhầm do vùng dữ liệu thưa), gắn cờ dòng nào
    có tỉ lệ láng giềng lẫn nhau mang nhãn khác > 50%. Trả về
    `DistanceNoiseResult(findings, diagnostics)` -- `DistanceNoiseFinding`
    (`row_number`, `recorded_label`, `suggested_label`, `disagreement_ratio`)
    + `DistanceNoiseDiagnostics` (`k`, `n_rows_with_mutual_neighbors` -- chỉ
    số "độ phủ" PHẢI xem trước khi tin findings, vai trò tương đương
    `cv_accuracy` bên Confident Learning nhưng khác bản chất vì không có
    model để đo accuracy). `_prepare_usable_subset()` CỐ TÌNH lặp lại logic
    lọc dòng y hệt `confident_learning.py` (không import dùng chung) để 2
    module độc lập nhau, không bị ràng buộc chéo khi sửa sau này.
  - `ensemble_based.py` — **MỚI, thuật toán DETECT thứ 3** cho Class noise,
    theo paper **N29** trong Bảng 6 Gupta & Gupta (2019) -- nhóm "Ensemble
    based" (Khoshgoftaar, Zhong, Joshi, 2005, "Enhancing software quality
    estimation using ensemble-classifier based noise filtering", 9/9 điểm
    chất lượng; xem mục 11 dưới đây để biết đầy đủ lý do chọn 3 classifier
    cụ thể). KHÁC CẢ 2 module trên: train **3 classifier THUỘC HỌ THUẬT
    TOÁN KHÁC NHAU** (không phải nhiều lần cùng 1 loại như Random Forest) --
    `LogisticRegression` (tuyến tính), `GaussianNB` (xác suất), `LinearSVC`
    (biên cực đại/margin-based) -- CỐ TÌNH không trùng họ với Random Forest
    (tree-based, confident_learning.py) lẫn Mutual k-NN (instance-based,
    distance_based.py), để 3 phương pháp trong hệ thống là 3 góc nhìn ĐỘC
    LẬP thật sự, không trùng điểm mù nhau. Mỗi classifier tự dự đoán qua
    `StratifiedKFold` + `cross_val_predict` (out-of-fold, cùng cơ chế
    confident_learning.py); dòng nào bị ĐA SỐ (>50%, tức ≥2/3) classifier dự
    đoán KHÁC nhãn ghi thì gắn cờ. Xử lý mất cân bằng lớp: `LogisticRegression`/
    `LinearSVC` dùng `class_weight="balanced"`; `GaussianNB` không hỗ trợ
    tham số này nên ép `priors` đều nhau giữa các lớp thay vì theo đúng tỉ lệ
    thật. `detect_class_noise_ensemble(df, config, cv_folds=5, random_state=42)`
    trả về `EnsembleNoiseResult(findings, diagnostics)` -- `EnsembleNoiseFinding`
    (`row_number`, `recorded_label`, `suggested_label` = nhãn đa số classifier
    chọn, `disagree_ratio`) + `EnsembleNoiseDiagnostics` (`classifier_names`,
    `per_classifier_accuracy` -- accuracy RIÊNG từng classifier so với nhãn
    ghi, PHẢI xem cả 3 trước khi tin findings giống hệt lý do cv_accuracy ở
    Confident Learning; `majority_baseline_accuracy`). **Tốc độ**: tuy train
    tới 3 model (so với 1 model của Confident Learning), vẫn NHANH HƠN HẲN
    Random Forest 300 cây -- đã đo thật trên Adult Income (32.561 dòng):
    Random Forest 12.72-13.47s, còn LogisticRegression+GaussianNB+LinearSVC
    cộng lại chỉ 2.15-2.40s (nhanh hơn ~6 lần) -- vì Random Forest thực chất
    là 300 cây con cộng lại (mỗi cây phải mọc qua nhiều bước chia nhánh tốn
    kém), còn 3 classifier kia đều là bài toán tối ưu LỒI (hoặc không cần
    tối ưu gì như GaussianNB) nên hội tụ rất nhanh dù "có train".
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
- `accounts/` — module quản lý tài khoản (Multi-User THẬT, xem mục 14 dưới
  đây), thuần Python + SQLite, không phụ thuộc Flask (giống triết lý
  `attribute_noise/`).
  - `db.py` — `get_connection()`/`init_db()`. 1 file SQLite DUY NHẤT
    (`spark_accounts.db`, tự tạo ở gốc repo lúc `init_db()` chạy, KHÔNG
    commit vào git — xem `.gitignore`), bảng `users` (id, username UNIQUE,
    password_hash, created_at). SQLite đủ tải cho quy mô demo khoá luận
    (tài liệu chính thức sqlite.org ghi nhận chịu được tới hàng trăm nghìn
    lượt truy cập/ngày, thừa sức cho vài người dùng cùng lúc).
  - `service.py` — `register()`/`authenticate()`/`get_user()`/
    `change_password()` + `AccountError` (app.py bắt lỗi này trả HTTP 400,
    cùng cách `FormulaError` được xử lý). Băm mật khẩu bằng
    `werkzeug.security.generate_password_hash`/`check_password_hash` (có
    sẵn trong Flask, không cài thêm) — KHÔNG tự viết công thức băm (khác
    triết lý "tự viết tay" ở `attribute_handling.py::impute_knn` chẳng
    hạn, vì bảo mật mật khẩu là lĩnh vực rủi ro cao nếu tự chế sai mà
    không nhận ra). `authenticate()` cố tình trả CHUNG 1 message lỗi
    ("Tên đăng nhập hoặc mật khẩu không đúng") cho cả 2 trường hợp "không
    có tài khoản này" lẫn "có tài khoản nhưng sai mật khẩu" — không tiết
    lộ username nào đã tồn tại qua nội dung lỗi.
- `converters/` — logic 3 tool "Convert File" (đổi delimiter CSV, CSV ⇄
  JSON — xem mục 15 dưới đây), thuần Python, không phụ thuộc Flask.
  - `transform.py` — `convert_csv_delimiter()`, `csv_text_to_json()`,
    `json_text_to_csv()` + `detect_delimiter()` (thử `csv.Sniffer` trước,
    dự phòng bằng cách tự đếm ký tự nào xuất hiện ĐỀU nhất qua các dòng nếu
    Sniffer bó tay) + `ConversionError`. CỐ TÌNH dùng module `csv`/`json`
    chuẩn của Python thay vì pandas — khác `attribute_noise`/`class_noise`
    (đọc dữ liệu BẢNG để tìm/sửa noise, cần hiểu dtype nên dùng pandas hợp
    lý), 3 tool này chỉ đổi ĐỊNH DẠNG chứ không cần hiểu ý nghĩa cột, mà
    pandas hay "giúp đỡ" quá tay lúc đọc/ghi (vd tự ép "007" thành số 7).
    `csv_text_to_json()` tự ép kiểu số/true-false khi bật `convert_types`
    nhưng GIỮ NGUYÊN DẠNG CHUỖI nếu giá trị có số 0 ở đầu (vd "007", số
    điện thoại "0912...") — ép thành số sẽ xoá mất số 0 đó, đổi hẳn ý
    nghĩa dữ liệu. `json_text_to_csv()` chấp nhận CẢ 2 dạng JSON array lẫn
    JSON Lines (mỗi dòng 1 object riêng); cột xuất ra = HỢP (union) mọi
    khoá có ở BẤT KỲ object nào (không chỉ object đầu tiên), object thiếu
    khoá thì để ô trống; object lồng nhau tự làm phẳng thành "cha.con"
    (vd `address.city`), list lồng bên trong KHÔNG làm phẳng tiếp (giữ
    nguyên dạng chuỗi JSON khi ghi ra CSV).
- `app.py` — Flask backend, CHỈ đóng vai trò "phiên dịch" JSON ⟷ Python object,
  KHÔNG chứa logic detect/handle (logic nằm hết ở `attribute_noise/`).
  Endpoints:
  - `POST /api/upload` — response **MỚI (mục 12)** có thêm field
    `guessed_dtypes` (dict tên cột → dtype đoán được qua `guess_column_dtype()`)
    để FE tự chọn sẵn dropdown kiểu dữ liệu ở Bước 3, thay vì mặc định "text"
    cho mọi cột như trước.
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
  - **Bước 5 AN TOÀN (mục 13)** — 3 thay đổi quanh `/api/apply-handling-partial`:
    (1) nhận thêm `dry_run: true` = CHẠY THỬ (tính trên bản sao, KHÔNG ghi gì, trả
    `{dry_run, rows_before, rows_after, rows_removed, cells_changed}`); (2) chạy thật thì
    response có thêm `history` (nhật ký + `can_undo`) và `applied` (tác động THẬT:
    `rows_removed`/`cells_changed`, để FE không báo "đã xử lý" khi thực tế không đổi gì);
    (3) route mới `POST /api/undo-handling` (lùi 1 bước) và `POST /api/reset-working`
    (về bản upload gốc) -- cả hai trả response dạng `/api/detect-noise` + `history`.
    `/api/detect-noise` giờ detect trên BẢN ĐANG LÀM VIỆC nếu đã xử lý (`_peek_working_df()`),
    trước đây luôn detect trên bản gốc nên Detect lại sau khi xử lý hiện lại các lỗi đã sửa.
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
  - `POST /api/class-noise/detect` — **hướng Class noise (mục 10+11):
    field `method`** dispatch sang 1 trong **ĐỦ CẢ 3** thuật toán DETECT
    (`"single_learning"` mặc định = Confident Learning, `"distance_based"`
    = Mutual k-NN N13, `"ensemble_based"` = N29 — **MỚI, mục 11, vừa nối
    xong**). Payload chung: `file_id` (DÙNG CHUNG `/api/upload` với hướng
    attribute, không có upload riêng) + `label_column` + `feature_columns`;
    `method="single_learning"` nhận thêm tuỳ chọn `n_estimators`/`cv_folds`,
    `method="distance_based"` nhận thêm tuỳ chọn `k` (mặc định 5),
    `method="ensemble_based"` nhận thêm tuỳ chọn `cv_folds` (mặc định 5).
    Response LUÔN có field `"method"` ở gốc để FE biết nên render kiểu
    diagnostics nào (3 thuật toán có hình dạng diagnostics KHÁC NHAU hẳn —
    distance-based không có cv_accuracy/per_class_report/confusion_matrix vì
    không train model; ensemble-based có `per_classifier_accuracy` (accuracy
    RIÊNG từng trong 3 classifier) thay vì 1 `cv_accuracy` duy nhất, cũng
    không có confusion_matrix). `findings` được CHUẨN HOÁ chung tên trường
    cho CẢ 3 method (`suggested_label` thay `confident_label`, `score` thay
    `margin`/`disagreement_ratio`/`disagree_ratio`) để FE dùng CHUNG 1 cách
    render bảng "danh sách dòng nghi ngờ", chỉ đổi chữ header theo method.
    CHẠY ĐỒNG BỘ (block request); `single_learning` có thể mất VÀI PHÚT với
    file lớn (train Random Forest 300 cây qua CV), `distance_based`/
    `ensemble_based` thường nhanh hơn nhiều (đã đo thật, xem mục 11) — không
    có thanh tiến trình, chấp nhận được cho quy mô demo khoá luận.
    `app.run(..., threaded=True)` để request này không chặn các request
    khác trong lúc chờ. Validate
    `feature_columns` đều "đủ số" (`_is_mostly_numeric()`) TRƯỚC khi chạy
    (áp dụng cho CẢ 2 method, cùng 1 validate), báo lỗi nêu đúng tên cột
    chữ nếu sai (cùng lỗi "0 dòng dùng được" như `reduce-features`, lúc đầu
    CHỈ fix ở `reduce-features`, sau phát hiện endpoint này cũng dính y hệt
    vì người dùng tick tay feature chữ được, đã fix bổ sung). **LUÔN** chạy
    `cap_outliers()` + `log_transform()` (Bước 3, xem `feature_selection.py`)
    lên `feature_columns` TRƯỚC khi chạy — áp dụng cho CẢ 2 method, không
    phải tuỳ chọn, vì 2 hàm này chỉ sửa giá trị, không xoá dòng/cột.
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
  - **Tài khoản đăng nhập (Multi-User THẬT, mục 14):** Flask app khởi tạo
    với `static_folder="frontend", static_url_path=""` + route `GET /`
    PHỤC VỤ LUÔN frontend từ chính Flask này (lý do bắt buộc: cookie session
    chỉ đáng tin cậy khi frontend/backend CÙNG 1 origin, xem giải thích đầy
    đủ trong comment ở đầu app.py) -- **MỚI (mục 16)**: `GET /` giờ trả
    `frontend/landing.html` (trang giới thiệu công khai) thay vì
    `index.html` trực tiếp như lúc mới làm xong mục 14; `index.html`
    (app thật) vẫn phục vụ bình thường tại `/index.html` nhờ
    `static_folder`, không cần route riêng. `app.secret_key`
    đọc từ biến môi trường `SPARK_SECRET_KEY` nếu có, không có thì tự sinh
    ngẫu nhiên mỗi lần khởi động (giới hạn đã biết: restart server là mọi
    người đăng nhập bị đăng xuất, chấp nhận được cho demo 1 người dùng).
    5 route: `POST /api/auth/register` (tự đăng nhập luôn sau khi đăng ký
    thành công), `POST /api/auth/login`, `POST /api/auth/logout`,
    `GET /api/auth/me` (trả `{"user": null}` khi chưa đăng nhập — trạng
    thái BÌNH THƯỜNG, không phải lỗi 401 — FE dùng route này lúc tải trang
    để quyết định hiện thẳng app hay bắt đăng nhập trước), `POST
    /api/auth/change-password` (`@login_required`). `register`/`login` trả
    về CÙNG 1 shape `{"user": {id, username, created_at}}` như `/api/auth/me`
    để FE đọc response theo đúng 1 cách cho cả 3 route. `login_required`
    (decorator) chặn HTTP 401 ngay nếu `session` chưa có `user_id`, dùng
    cho route không gắn với 1 `file_id`/`download_id` có sẵn (vd
    `/api/upload`). `FILE_OWNERS`/`DOWNLOAD_OWNERS` (dict RAM, key = id,
    value = `user_id`) ghi nhớ "file/download này của ai" — helper
    `_require_file_owner(file_id)`/`_require_download_owner(download_id)`
    gắn ở ĐẦU của TẤT CẢ route cũ có dùng `file_id`/`download_id` (detect-
    noise, apply-handling-partial, undo/reset-working, working-data,
    export-working, download, class-noise/detect, class-noise/reduce-
    features — 9 route), trả CÙNG 1 lỗi "not found" chung chung dù file
    thật sự không tồn tại HAY tồn tại nhưng thuộc người khác (không tiết lộ
    sự tồn tại của file người khác, khớp pattern bảo mật phổ biến).
  - **Convert File (mục 15):** 3 route `POST /api/convert/delimiter`,
    `POST /api/convert/csv-to-json`, `POST /api/convert/json-to-csv`
    (`@login_required` cả 3) — chỉ "phiên dịch" multipart/form-data ⟷ gọi
    hàm ở `converters/transform.py`, KHÔNG dùng `file_id`/`UPLOADED_FILES`
    gì cả vì xong trong ĐÚNG 1 request (đọc file hoặc text dán tay → convert
    → trả kết quả luôn), khác hẳn luồng Attribute/Class Noise nhiều bước.
    `_extract_convert_text()` chấp nhận field `file` (multipart) HOẶC field
    `text` (dán tay) — FE luôn gửi multipart cho cả 2 tab để route chỉ cần
    đọc 1 kiểu; tự decode `utf-8-sig` (bỏ BOM nếu Excel/Windows thêm vào).
    `_delimiter_param()` validate CHẶT delimiter gửi lên phải nằm trong
    `DELIMITER_LABELS` (`,`/`;`/tab/`|`) hoặc `"auto"` — converters/transform.py
    tự nó không giới hạn gì, validate nằm ở RANH GIỚI API (route) theo đúng
    nguyên tắc "chỉ validate ở biên hệ thống" của dự án. `_csv_preview_rows()`
    đọc trước tối đa 21 dòng (1 header + 20 data) của CSV kết quả để FE hiện
    bảng xem trước, tránh FE phải tự viết 1 bộ phân tích CSV bằng JS.
  - **Free Tools (mục 17) — ĐÃ ĐỔI, xem bullet "Routes cho giao diện Denoise" ngay dưới:** 4 route `POST /api/noise-tools/remove-duplicates`,
    `/trim-whitespace`, `/fill-blanks`, `/remove-empty-rows` (`@login_required`
    cả 4) — vận hành GIỐNG 3 route Convert File ở trên (không cần `file_id`/
    `UPLOADED_FILES`, xong trong ĐÚNG 1 request) nhưng KHÁC ở chỗ cần hiểu
    DỮ LIỆU DẠNG BẢNG nên đọc qua pandas (`_read_df_for_noise_tool()`: file
    tải lên dùng `load_data()` giống Workspace rồi XOÁ NGAY file tạm sau khi
    đọc; text dán tay dùng thẳng `pd.read_csv()` cùng tham số `load_data()`
    dùng cho CSV) thay vì module `csv`/`json` chuẩn như `converters/transform.py`.
    `_noise_tool_response()` đóng gói kết quả CÙNG SHAPE 3 route Convert
    (`result_text` để tải về + `preview_rows` tái dùng `_csv_preview_rows()`),
    cộng `stats` (từ `quick_tools.py`) để FE hiện số dòng/số ô đã đổi. Bắt
    `QuickToolError` trả 400 kèm message rõ, bắt thêm `Exception` chung (file
    hỏng/parse lỗi...) cũng trả 400 thay vì để lộ lỗi 500 thô.
  - **Routes cho giao diện Denoise (mục 18-21), tất cả `@login_required`, KHÔNG có
    `file_id`, xong trong 1 request:** `GET /` giờ trả `frontend/workspace.html`
    (không còn `landing.html`; 2 file cũ vẫn mở được qua `/landing.html`,
    `/index.html`). Nhóm "Tự động"/Free Tools: `POST /api/noise-tools/remove-duplicates`,
    `/trim-whitespace`, `/format-noise`, `/blanks` (gộp Xoá dòng trống + Điền/xoá ô
    trống + Thiếu giá trị nâng cao — 2 route cũ `/fill-blanks` và `/remove-empty-rows`
    ĐÃ GỠ), `/blank-rows` (bảng các dòng có ô trống cho "Điền tay từng ô").
    Dùng chung: `/inspect` (đọc tên cột + `guessed_dtypes` + 20 dòng xem trước của
    file/text vừa chọn; gửi `include_values=true` thì trả thêm `column_values` = {cột Nhóm: {values:[{value,count}] tối đa 30, more}} cho chip
    giá trị của rule Biểu thức, mục 28), `/check-expression` (kiểm tra nhanh 1 biểu thức khi đang gõ, mục 30), `/normalize` (đọc lại đầu vào GỐC thành CSV chuẩn, dùng cho nút
    "Bắt đầu lại từ gốc"). Nhóm "Cần cấu hình": MỘT route `POST /api/noise-tools/configured`
    với field `mode` = `detect` | `apply` và `config` (JSON) — `config.tool` ∈
    `out-of-range` | `outlier` | `inconsistent-category` | `cross-rule`. Tool theo cột
    gửi `config.items` = danh sách {column, dtype, params} (NHIỀU cột 1 lượt; không có
    `items` thì dùng cách gửi 1 cột cũ ở gốc config); detect trả `per_column` (số ô lỗi,
    số dòng, `available_actions` từng cột; cột outlier có ≥2 phương pháp thêm `methods`
    + `both_count`); apply nhận `actions` {cột: {action, fixed_value}} và gọi
    `apply_handling()` MỘT lần với nhiều `HandlingChoice` (nhiều cột cùng chọn
    `remove_row` thì xoá HỢP các dòng). `_checked_fixed_value()` kiểm giá trị cố định
    theo kiểu cột (số nguyên phải là số nguyên; số thực phải là số hữu hạn, loại
    `nan`/`inf`/`1_000`); `_checked_outlier_rules()` kiểm danh sách phương pháp (chỉ
    `iqr`/`zscore`, không trùng, ngưỡng số > 0). Rule liên cột (`cross-rule`) vẫn 1 rule
    mỗi lần, cách xử lý chỉ có xoá dòng vi phạm / giữ nguyên. Giao diện Denoise gửi
    `rule_type` ∈ `expression` | `functional_dependency` (từ mục 28 giao diện Denoise không còn gửi `if_then`; compare/formula/conditional/if_then
    vẫn được backend nhận cho giao diện cũ). Rule `expression` và `if_then` trả thêm `expression_info` (xem mục 24-25). NGOẠI LỆ Phụ thuộc hàm: `rule`
    nhận `dependent_columns` (danh sách) = 1 cột xác định → NHIỀU cột phụ thuộc;
    `_cross_rules_from_config()` tách thành từng rule A → Bi (dùng lại đúng hàm detect cũ, kiểm
    ĐỘC LẬP từng cột, báo lỗi 400 nếu cột không tồn tại / trùng cột xác định / chọn 2 lần), response
    thêm `rule_breakdown` = [{column, flagged_rows_count}]. Không có `dependent_columns` thì chạy như
    cũ (`dependent_column`, kể cả `/api/detect-noise` của giao diện cũ). Xoá dòng vi phạm = HỢP các cột.
    **Đoán ô sai (Phụ thuộc hàm):** `cross_field_rules.py::analyze_functional_dependency()` (dùng chung
    `_fd_working_frame()` với detect nên luôn cùng tập dòng; chỉ là GỢI Ý, không đổi dòng bị gắn cờ).
    Mỗi nhóm mâu thuẫn (cùng A, nhiều B) so thêm CÁC CỘT CÒN LẠI: >= 50% giống nhau (`FD_SAME_ENTITY_RATIO`)
    → cùng 1 đối tượng, ô sai là B (giá trị đa số = "mốc đúng", giá trị lệch = nghi sai, hoà số lượng = "chưa rõ");
    < 50% → nhiều khả năng 2 đối tượng khác nhau dùng chung A → nghi sai ô A, KHÔNG biết dòng nào; không cột nào so
    được → "chưa xác định". Chỉ dùng cột "ổn định" làm bằng chứng (ở các nhóm KHÔNG vi phạm vẫn thường giống nhau,
    `FD_STABLE_COLUMN_RATIO`) để bảng chấm công/lương (lương, tháng khác nhau là bình thường) không bị coi là "khác
    đối tượng". Route trả thêm: `flagged_rows[].ref` (ô mốc, tô nhạt), `hint` (câu ngắn), `notes` (lý do, tooltip) và
    `fd_analysis` {determinant, rules:[{column, groups, determinant, dependent, unknown}]}; FE thêm cột "Gợi ý" +
    chú thích `.ft-table-note.is-long`. Kiểm chứng trên `noisy_employee_dataset_large.csv`: `id → full_name` ra đúng 5
    nhóm = 5 id `duplicate_id_conflicting_data` trong file đáp án, cả 5 đều kết luận nghi sai `id`.
    **Cách xử lý Phụ thuộc hàm (4 cách, `FD_ACTIONS` ở app.py; mặc định "— Chọn cách xử lý —", không chọn sẵn cách đổi
    dữ liệu):** `fix_to_majority` "Sửa về giá trị phổ biến nhất" (ghi các ô lệch về giá trị đa số, không xoá dòng),
    `remove_suspect_rows` "Chỉ xoá dòng nghi sai", `remove_row` "Xoá cả dòng" (xoá HẾT dòng trong nhóm, kể cả dòng đúng),
    `keep`. 2 cách đầu CHỈ đụng các nhóm "xác định được" (kết luận cột B sai + có giá trị đa số, không hoà — `_fd_plan()`);
    nhóm hoà / nghi sai cột A / chưa xác định giữ nguyên và báo `stats.unresolved_groups`. Xem trước tác động không cần
    gọi lại backend: detect trả `fd_plan` {fix_to_majority.cells, remove_suspect_rows.rows, remove_row.rows,
    unresolved_groups}, FE hiện ở `#cf-action-preview` (cách xoá cả nhóm hiện đỏ). Rule liên cột khác (Biểu thức/Nếu–thì)
    vẫn chỉ Xoá cả dòng / Giữ nguyên NHƯNG từ mục 25 cũng mặc định "— Chọn cách xử lý —" và có xem trước
    "Sẽ xoá N dòng vi phạm (a → b)" (`fdPlan.generic`, FE tự dựng từ `flagged_rows_count`).
    **Chưa làm:** vế xác định vẫn 1 cột; chưa có "giữ dòng đầu, xoá các dòng sau" cho nhóm nghi sai cột A (id trùng,
    không suy ra được dòng nào sai); hoàn tác cho tool này.
- `frontend/` — **GIAO DIỆN HIỆN HÀNH "Denoise" (mục 18-22):** 4 file
  `workspace.html` + `workspace.css` + `workspace.js` + `workspace-flow.js`, HTML/CSS/JS
  thuần, MỘT trang duy nhất `GET /` gồm 9 khối đổi bằng `switchSection()` (KHÔNG điều
  hướng sang trang khác): công khai — `#section-home` (hero, ticker, lưới tính năng, demo
  tĩnh), `#section-guide`, `#section-security`, `#section-privacy`; cần đăng nhập — 3 nhóm
  tool `#section-config` (Cần cấu hình), `#section-free-tools` (nhóm "Tự động"),
  `#section-convert`, cộng `#section-class-noise` (4 bước) và `#section-profile`.
  Chưa đăng nhập mà bấm khối cần tài khoản thì `#ws-auth` (đăng nhập/đăng ký chia đôi
  màn hình) hiện đè lên. Header: Home / Product (menu lớn 3 nhóm tool) / Class Noise /
  Guide + cụm tài khoản. Màu nhấn cobalt `#2f4bff`, chữ IBM Plex; khung rộng tối đa 1760px.
  - `workspace.js`: trang chủ + 3 nhóm tool + auth + hồ sơ. Ba nhóm tool DÙNG CHUNG một bộ
    máy (tiền tố `ft-` Free Tools, `cv-`/`convert-` Convert, `cf-` Cần cấu hình), bố cục
    "01 · ĐẦU VÀO / 02 · KẾT QUẢ", mỗi tool một tab (`data-tool`). Nhóm Free Tools: tab
    `remove-duplicates`, `trim-whitespace`, `format-noise` (Sai định dạng), `blanks` (Ô
    trống). Nhóm Cần cấu hình: `out-of-range`, `outlier`, `inconsistent-category`,
    `cross-rule` (2 kiểu từ mục 28: Biểu thức, gồm cả nếu–thì viết bằng `=>` / Phụ thuộc hàm). Nhóm Convert: `delimiter`,
    `csv-to-json`, `json-to-csv`.
  - **Bộ nhớ NỐI TIẾP (`state.pipe`, `recordPipeStep()`, `renderPipeStrips()`)**: kết
    quả 1 tool thành đầu vào của tool kế tiếp, xuyên cả 3 nhóm (bảng "Xử lý tiếp bằng"
    + dải đen "đã qua: …" với nút "Bắt đầu lại từ gốc" / "Tải file khác"). Khi đầu vào
    đổi thì Cần cấu hình tự đọc lại danh sách cột (`refreshCfColumns`, chống chạy chồng
    bằng `colSig`/`colSeq`). "Về gốc" gọi `/api/noise-tools/normalize` với file gốc
    trình duyệt còn giữ (`originalSource`). "Tải file khác" PHẢI quên file cũ ở cả 3 nhóm
    (`forgetSelectedFile`) — đã từng sót, gây lỗi chạy lại file cũ.
  - **Khung kiểm NHIỀU cột `CF_MULTI` (mục 20-21)**: 3 tool Cần cấu hình theo cột dùng
    chung 1 khung: mỗi form = 1 cột + ô riêng của tool; nút "＋ Thêm cột kiểm tra" (mỗi
    cột khai 1 lần, danh sách chọn loại cột đã dùng); "Phát hiện" gửi tất cả form 1
    lượt; kết quả là bảng "Lỗi theo từng cột" (cột nào, bao nhiêu lỗi, ô chọn cách xử lý
    RIÊNG từng cột) + bảng bên phải tô ô lỗi của MỌI cột. Mỗi mục CF_MULTI khai: `dtypes`
    (kiểu cột được liệt kê), `waitFile`/`noColumns` (lời nhắc), `preselect`, `defaults`,
    `fieldsHTML`, `toItem`, tuỳ chọn `onClick`/`onInput` cho nút/ô riêng trong form.
    `inconsistent-category`: chỉ cột Nhóm, kiểu khoá, ngưỡng giống nhau mặc định 1,
    `preselect:true`. `out-of-range`: chỉ cột số, kiểu chỉnh được, nhỏ nhất/lớn nhất
    riêng (bỏ trống 1 bên được). `outlier`: chỉ cột số, mỗi form có 1-2 hàng
    "Phương pháp" (nút gạt IQR/Z-score + ngưỡng; nút "＋ Thêm phương pháp"; mặc định IQR
    1.5, Z-score 3). Hai tool có `remove_row` (out-of-range, outlier) để `preselect:false`:
    ô cách xử lý mặc định "— Chọn cách xử lý —" và cột chưa chọn thì KHÔNG bị đụng (tránh
    xoá nhầm hàng loạt, cùng bài học mục 13).
  - `workspace-flow.js` (IIFE, copy từ `script.js`, API `window.DenoiseFlow`): trong
    Denoise chỉ nhánh **Class Noise 4 bước** được dùng (File & phương pháp → Nhãn & đặc
    trưng → Kết quả → Xử lý=placeholder). Phần logic Attribute 5 bước còn nằm trong file
    nhưng giao diện Denoise không còn mở nó (thay bằng 3 nhóm tool).
  - `workspace.css`: biến CSS bề rộng khung; class dùng chung `.cyd-table*`, `.convert-*`,
    `.ft-*`, `.cf-form*`, `.cf-sum*`, `.cf-method-*`; `@container` cho bảng lỗi theo cột.
  - Cũ vẫn giữ (chưa xoá, chờ user nói): `index.html`, `script.js`, `style.css`,
    `landing.html`, `landing.js` — lệnh đã dặn: KHÔNG sửa các file này nếu không được yêu cầu.
- `frontend/` — **(GIAO DIỆN CŨ — `index.html` + `script.js` + `style.css`; giao diện
  hiện hành là Denoise, xem bullet ngay dưới)** HTML/CSS/JS thuần (chưa dùng framework), UI dạng "panel theo
  bước" (chỉ 1 `.panel.is-active` hiện tại 1 thời điểm) với **5 bước**:
  1. Tải file lên → `POST /api/upload`.
  2. Hướng xử lý — chọn Attribute noise hay Class noise. **MỚI (mục 10):**
     chọn Class Noise xong hiện thêm khối "Chọn phương pháp phát hiện" (3
     thẻ, `#class-method-section`) khớp đúng Bảng 6 Gupta & Gupta (2019):
     **MỚI (mục 11) cả 3 thẻ đều bấm được** — Distance-based, Single
     learning-based, Ensemble-based (CSS `.is-disabled`/`.badge-soon` vẫn
     giữ nguyên trong `style.css` phòng khi cần khoá tạm 1 phương pháp
     khác sau này, chỉ không còn gắn vào thẻ nào). Nút "Tiếp tục" chỉ mở khi
     ĐÃ chọn xong cả hướng LẪN phương pháp (nếu là Class Noise) —
     `updateContinueStep2Button()`. `state.classMethod` lưu lựa chọn này,
     `state.classResultMethod` lưu riêng method CỦA KẾT QUẢ đang hiển thị
     (2 giá trị có thể lệch nhau nếu đổi lựa chọn sau khi đã detect xong).
  3. Cấu hình noise — mỗi cột hiện dạng "chip" (nút bo tròn bật/tắt) cho ĐỦ 7
     loại noise, chỉ hiện chip hợp lý với dtype đang chọn (`COLUMN_TYPES` map
     dtype → danh sách noise khả dụng trong `script.js`). **MỚI (mục 12)**:
     dropdown "Kiểu dữ liệu" của mỗi cột TỰ CHỌN SẴN theo `guessed_dtypes` từ
     `/api/upload` (thay vì luôn mặc định "text" như trước) — `defaultColumnConfig(dtype)`
     nhận dtype đoán được làm giá trị khởi đầu, người dùng vẫn đổi lại bình
     thường qua đúng dropdown, không khoá gì. Tick chip nào thì
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

     **Bước 5 AN TOÀN (mục 13)**: dropdown "Đặt hàng loạt" và "Tự điều chỉnh" mặc định
     "— Chọn cách xử lý —" (trừ hành động `auto_*` an toàn thì chọn sẵn), bấm Áp dụng khi còn
     dòng chưa chọn → báo lỗi ngay trong nhóm (không `alert`), có xoá dòng → chạy thử
     (`dry_run`) rồi hiện hộp "Sẽ xoá N dòng (a → b)" xin xác nhận, thanh "Lịch sử xử lý" ở đầu
     bước có Hoàn tác (5 bước gần nhất) và Về dữ liệu gốc. Mọi lệnh làm đổi dữ liệu chạy tuần tự
     qua `withHandlingLock()` (cờ `state.handlingBusy` + class `is-busy`).

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
    là nhãn), khối "Tham số nâng cao" **(mục 10+11) đổi theo `state.classMethod`**:
    `#class-params-single` (n_estimators/cv_folds, mặc định 300/5, khớp
    `ClassNoiseConfig`) hiện khi `single_learning`, `#class-params-distance`
    (chỉ số `k`, mặc định 5) hiện khi `distance_based`, `#class-params-ensemble`
    (chỉ số `cv_folds`, mặc định 5 — **MỚI, mục 11**) hiện khi `ensemble_based`
    — `renderClassNoiseConfigForm()` ẩn/hiện đúng khối + dòng cảnh báo "có
    thể mất vài phút" (`#class-wait-hint`, chỉ ẩn khi `distance_based` vì đây
    là method duy nhất không train model nào). `panel-desc` đầu Bước 3 có ghi
    rõ: các cột đặc trưng sẽ TỰ ĐỘNG được cap outlier + log-transform (Bước 3
    ở mục 9) ngay lúc bấm "Phát hiện Class Noise" — áp dụng cho CẢ 3 method,
    không phải khối riêng, không cần bấm thêm nút nào, chỉ 1 dòng mô tả cho
    người dùng biết việc đang xảy ra.
  - Bước 4 (class): `renderClassResults()` dispatch theo
    `state.classResultMethod`, render **3 kiểu khác hẳn nhau** (mục 10+11)
    vì 3 thuật toán có diagnostics khác bản chất:
    - `single_learning` (`renderClassResultsSingleLearning()`, hành vi gốc):
      5 thẻ thống kê (dòng dùng được, CV accuracy, baseline, chênh lệch,
      số dòng nghi ngờ) + khung CẢNH BÁO màu đỏ nếu chênh lệch accuracy-
      baseline ≤ 2 điểm % VÀ dưới 30% "mức trần tối đa" (`isWeak`) + bảng
      precision/recall/F1 từng lớp (`#class-report-card`, tiêu đề đặt qua
      `#class-report-title`) + ma trận đếm (`#class-confusion-card`).
    - `distance_based` (`renderClassResultsDistance()`): 4 thẻ thống kê
      (dòng dùng được, k, % dòng có láng giềng lẫn nhau — "độ phủ", số dòng
      nghi ngờ) + khung CẢNH BÁO nếu độ phủ < 50% (dữ liệu quá thưa/k quá
      nhỏ). `#class-report-card`/`#class-confusion-card` bị ẨN HẲN (không
      có precision/recall/confusion matrix vì không train model nào).
    - `ensemble_based` (`renderClassResultsEnsemble()`, **MỚI, mục 11**):
      4 thẻ thống kê (dòng dùng được, số classifier = 3, baseline + chênh
      lệch của classifier TỐT NHẤT trong 3 cái, số dòng nghi ngờ) + khung
      CẢNH BÁO nếu ngay cả classifier tốt nhất cũng chỉ nhỉnh hơn baseline
      ≤ 2 điểm % (`isWeak` riêng, so TỪNG classifier chứ không phải 1
      cv_accuracy duy nhất). `#class-report-card` đổi tiêu đề thành
      "Accuracy từng classifier (so với nhãn ghi)" (qua `#class-report-title`),
      bảng liệt kê accuracy + chênh lệch baseline của TỪNG trong 3 classifier
      (`per_classifier_accuracy`) — không phải precision/recall/F1 theo
      lớp như single_learning. `#class-confusion-card` bị ẨN HẲN (không có
      1 "model" duy nhất để tính ma trận đếm nhãn-ghi-vs-dự-đoán).
    - Bảng danh sách dòng nghi ngờ dùng CHUNG 1 hàm `renderClassFindingsTable()`
      cho CẢ 3 method (đọc `f.suggested_label`/`f.score` đã CHUẨN HOÁ từ
      backend), chỉ đổi chữ header qua `CLASS_SCORE_LABELS` ("Model tự
      tin"/"Margin" cho single_learning, "Gợi ý nhãn (đa số láng giềng)"/
      "Tỉ lệ láng giềng bất đồng" cho distance_based, "Gợi ý nhãn (đa số
      classifier)"/"Tỉ lệ classifier bất đồng" cho ensemble_based — MỚI) —
      tìm kiếm + phân trang 20 dòng/trang, đã
      sắp theo score giảm dần từ backend.
  - Bước 5 (class): CHỈ có placeholder "đang phát triển" — xử lý/handling
    cho class noise CHƯA code (xem roadmap cuối file), nút quay lại Bước 4.

  11 "family" màu (`NOISE_TYPE_META` trong `script.js`, khớp biến CSS
  `--<family>-text/soft/border` trong `style.css`) dùng chung cho chip/badge/
  tag/tô màu ô — 1 màu riêng cho mỗi loại trong 7 attribute noise + 4 rule
  liên cột.

  **Tài khoản đăng nhập (Multi-User THẬT, mục 14) — cổng xác thực trước TẤT
  CẢ panel khác:** `index.html` có thêm `#panel-auth` (đăng nhập/đăng ký,
  bố cục chia đôi màn hình — nửa trái form thật, nửa phải demo tĩnh dùng
  ĐÚNG 11 màu `.cell-flag-*` nói trên thay vì ảnh trang trí rời rạc) và
  `#panel-profile` (xem username/ngày tạo + đổi mật khẩu) — cả 2 KHÔNG nằm
  trong thanh 5 bước, giống cách `#panel-preview` đã có từ trước.
  `checkAuthStatus()` (`script.js`) gọi `GET /api/auth/me` NGAY LÚC TẢI
  TRANG, trước `checkBackendHealth()`: chưa đăng nhập thì ẩn `#stepper` +
  MỌI panel số, chỉ hiện `#panel-auth`; đã đăng nhập thì hiện app bình
  thường + badge tài khoản ở header (`#account-area`, có nút "Hồ sơ"/"Đăng
  xuất"). CSS `body:not(.auth-ready) .panel:not(#panel-auth) { display:
  none !important }` che tạm mọi panel trong lúc chờ `checkAuthStatus()`
  trả lời, tránh nhoáng `#panel-1` (mặc định `is-active` trong HTML) trước
  khi kịp biết đã đăng nhập hay chưa — `checkAuthStatus()` thêm class
  `auth-ready` vào `<body>` SAU KHI đã quyết định xong hiện panel nào mới
  bỏ rule che này. `API_BASE` đổi từ URL tuyệt đối `"http://localhost:5000"`
  sang chuỗi RỖNG `""` (cùng origin với Flask giờ tự phục vụ frontend) —
  ĐÂY LÀ THAY ĐỔI HÀNH VI QUAN TRỌNG: phải mở `http://localhost:5000/` sau
  khi chạy `python3 app.py`, KHÔNG mở trực tiếp file `frontend/index.html`
  nữa (cookie session chỉ gửi kèm đáng tin cậy khi cùng origin — mở theo
  kiểu `file://` cũ sẽ báo "chưa kết nối backend" dù server vẫn chạy bình
  thường, vì `fetch("/api/...")` lúc đó bị hiểu là tìm file trên ổ cứng).

  **Convert File (mục 15) — `convert.html` + `convert.js`, trang RIÊNG tách
  khỏi `index.html`:** giống "Free Tools" của 1 trang tham khảo (CYD) —
  KHÔNG thuộc luồng 5 bước Dò & Xử Lý Nhiễu, không có `file_id`, mỗi lần
  Convert xong ngay trong 1 request. Khác CYD ở chỗ BẮT BUỘC đăng nhập
  (quyết định có chủ đích của người dùng dự án, không phải mặc định kiến
  trúc) — `checkAuth()` trong `convert.js` gọi `GET /api/auth/me`, chưa
  đăng nhập thì CHUYỂN HƯỚNG thẳng về `index.html` (route `/` + `GET
  /api/auth/me` DÙNG CHUNG session cookie, cùng origin) thay vì viết lại 1
  form đăng nhập riêng ở đây — trang đăng nhập CHỈ sống ở `index.html`. Bố
  cục 2 cột "01 · ĐẦU VÀO / 02 · KẾT QUẢ" + 3 tab chọn tool (Đổi delimiter/
  CSV→JSON/JSON→CSV) lấy cảm hứng bố cục CYD nhưng GIỮ NGUYÊN token màu/
  font của SPARK (`--signal` teal, `--bg` kem, IBM Plex — xem mục 13 câu
  chuyện đã quyết định tương tự cho `#panel-auth`), tái dùng `.dropzone`/
  `.results-table`/`.table-wrap` đã có thay vì viết lại. Mỗi tab tự chọn
  `file`/`text` (toggle File/Dán text, luôn gửi multipart) + tham số riêng,
  bấm "Convert" gọi đúng 1 trong 3 route `/api/convert/*`; kết quả
  CSV (đổi delimiter, JSON→CSV) hiện dạng BẢNG (`preview_rows` từ backend),
  kết quả JSON (CSV→JSON) hiện dạng text thô cuộn được. Nút "Tải xuống" xử
  lý HOÀN TOÀN trên trình duyệt bằng `Blob`/`URL.createObjectURL` — không
  gọi thêm API nào vì `result_text` server đã trả đủ ngay lúc Convert.
  Link "🔀 Convert File" đặt trong `#account-area` ở header `index.html`
  (chỉ hiện khi đã đăng nhập); nút "Hồ sơ" ở `convert.html` điều hướng về
  `index.html?open=profile` — `onLoggedIn()` tự đọc query param này và mở
  luôn `#panel-profile`, đỡ phải bấm "Hồ sơ" thêm 1 lần nữa.

  **Free Tools (mục 17) — `tools.html` + `tools.js`, trang riêng tách khỏi
  `index.html`, dựng Y HỆT bố cục `convert.html` (01 ĐẦU VÀO/02 KẾT QUẢ, toggle
  File/Dán text, tab chọn tool) + tái dùng NGUYÊN CSS `.convert-*` không đổi
  tên class (giống cách `landing.html` tái dùng `.auth-demo-card` mà không
  đổi tên) -- chỉ khác Ý NGHĨA 4 tab (xử lý NHIỄU dữ liệu, không phải đổi
  định dạng) và luôn hiện bảng preview CSV (không có nhánh "kết quả là JSON
  dạng text thô" như tool CSV→JSON của Convert, vì cả 4 Free Tools đều xuất
  CSV).** `state.tool` khớp ĐÚNG hậu tố route (`remove-duplicates`/
  `trim-whitespace`/`fill-blanks`/`remove-empty-rows`), bấm "Chạy" gọi thẳng
  `/api/noise-tools/${state.tool}`. `statusFromStats()` gộp `stats` trả về
  (xem `_noise_tool_response()` ở app.py) thành 1 câu dễ hiểu ưu tiên nói SỐ
  DÒNG trước ("đã xoá N dòng (a → b)" hoặc "giữ nguyên N dòng"), chỉ thêm
  "đã sửa N ô" nếu có (tool Cắt khoảng trắng/Điền giá trị không xoá dòng nào,
  chỉ sửa ô). Tool "Điền/xoá ô trống" dùng Ô TEXT để gõ TÊN CỘT (không phải
  dropdown chọn từ danh sách cột) -- quyết định có chủ đích để KHÔNG cần
  thêm 1 API "xem trước danh sách cột" riêng (phá vỡ tính "1 request là
  xong" của Free Tools): gõ sai tên cột thì backend trả lỗi 400 rõ ràng
  ("Cột 'x' không tồn tại trong file"), chấp nhận được cho mức độ đơn giản
  Free Tools hướng tới. Link "🧹 Free Tools" đặt CẠNH link "🔀 Convert File"
  trong `#account-area` ở header `index.html`.

  **Nâng cấp visual 5 bước chính (áp mẫu eyebrow/badge của `#panel-auth`/
  `convert.html` lên toàn app)** — sau khi xem lại giao diện tham khảo
  (CYD) 1 lần nữa, user thấy UI 5 bước (Bước 1-5) trông "dởm" so với trang
  đăng nhập/Convert vừa làm đẹp lại, muốn đồng bộ CẢ APP theo cùng 1 phân
  cấp chữ. Đã làm: class `.eyebrow` (gộp chung định nghĩa với `.auth-eyebrow`
  cũ, 1 rule 2 selector, không tạo trùng lặp CSS) + `.badge-row`/`.badge-pill`
  (gộp chung với `.convert-badges`/`.convert-badge` cũ theo cùng cách) —
  dùng lại CHO MỌI panel thay vì viết CSS riêng mỗi nơi. Mỗi panel-N (1-5)
  + `#panel-profile` + `#panel-preview` đều thêm `<p class="eyebrow">[ BƯỚC
  N / 5 ]</p>` ngay trước `.panel-title`, đồng thời BỎ tiền tố "Bước N: "
  khỏi chính `.panel-title` (cả HTML tĩnh lẫn chỗ `script.js` tự set
  `textContent` cho `#panel-3-title` theo hướng Attribute/Class) vì eyebrow
  đã thay thế vai trò đó. `.panel-title` tăng từ 20px/600 lên 24px/650 cho
  "headline" hơn. Bước 1 thêm `.badge-row` 3 badge (qua backend thật/7+4
  loại lỗi/bảo mật theo tài khoản) làm ấn tượng đầu tiên rõ ràng hơn — CHỈ
  thêm ở Bước 1 (không rải đều cả 5 bước) để tránh lặp lại thông tin không
  cần thiết. Thuần sửa CSS/HTML (+2 dòng JS đổi text), KHÔNG đổi cấu trúc/
  logic nào — đã test lại đủ 39 kịch bản Playwright cũ (23 luồng chính +
  16 Convert), không hồi quy.

  **Trang giới thiệu (mục 16) — `landing.html` + `landing.js`, "mặt tiền"
  công khai mới của web:** sau khi xem lại trang tham khảo (CYD) LẦN NỮA,
  user KHÔNG muốn `http://localhost:5000/` vào thẳng "Bước 1: Tải dữ liệu
  lên" nữa — muốn 1 trang giới thiệu đầy đủ trước (hero to, danh sách tính
  năng, quy trình xử lý file...) rồi mới bấm "Bắt đầu" vào app thật, đồng ý
  đổi cả giao diện cũ miễn chức năng vẫn đúng với SPARK (không copy máy móc
  chức năng của trang tham khảo). `app.py::serve_frontend()` (route `GET /`)
  đổi sang trả `landing.html` thay vì `index.html` — `index.html` (app thật,
  bắt đăng nhập) lùi về phục vụ tại `/index.html` qua `static_folder`, mọi
  CTA trên `landing.html` ("Bắt đầu", "Đăng nhập"...) chỉ là link `<a
  href="index.html">` thuần, KHÔNG cần `landing.js` biết gì về trạng thái
  đăng nhập — `index.html` tự quyết định hiện app hay hiện form đăng nhập
  như cũ. Gồm: hero (tái dùng tagline "DỮ LIỆU NHIỄU VÀO. DỮ LIỆU SẠCH RA."
  từ `#panel-auth`) + ticker chạy chữ liệt kê đủ 9 loại noise (CSS
  `@keyframes`, 2 bản sao nội dung nối liền để cuộn không giật) + lưới 9
  thẻ "Phát hiện được gì" (7 attribute noise + rule liên cột + class noise)
  + demo TĨNH (tái dùng NGUYÊN `.auth-demo-card`/`.cell-flag-*`, theo đúng
  lựa chọn user chọn khi được hỏi: demo minh hoạ nhanh thay vì demo tương
  tác gọi backend thật không cần đăng nhập — tránh phải mở 1 route công
  khai mới chỉ để phục vụ demo, giữ đúng nguyên tắc mọi route xử lý dữ liệu
  đều bắt đăng nhập) + "Quy trình xử lý dữ liệu của bạn" (3 bước, bước giữa
  tô đậm `--signal-dark`, nói đúng sự thật kiến trúc đã làm ở mục 14: mỗi
  tài khoản 1 không gian riêng, không qua bên thứ 3 — không phải marketing
  suông) + khối "Về dự án" (giới thiệu đây là sản phẩm khoá luận, THAY cho
  phần "Ai nên dùng" kiểu persona Marketing/Sales của trang tham khảo vì
  không hợp bối cảnh 1 công cụ khoá luận). CỐ TÌNH bỏ phần demo tương tác
  thật (toggle rồi gọi `/api/detect-noise` trên file mẫu không cần đăng
  nhập) dù đã cân nhắc — user chọn hướng đơn giản/an toàn hơn.
  **1 lỗi CSS thật đã gặp + đã fix**: `.btn` (dùng chung cho cả `<button>`
  lẫn `<a>`, vd link "Bắt đầu"/"← Trang chính") thiếu `text-decoration:
  none` nên mọi nút dạng `<a>` bị gạch chân mặc định của trình duyệt — phát
  hiện qua ảnh chụp Playwright, fix 1 chỗ DUY NHẤT ở rule `.btn` gốc (thêm
  `display: inline-block; text-decoration: none;`) thay vì vá riêng từng
  trang, nên cũng tự fix luôn cho `convert.html`/`index.html` (chưa ai để ý
  trước đó vì gạch chân mờ, dễ bỏ sót khi chỉ nhìn lướt qua). Đã test lại
  đủ 39 kịch bản Playwright cũ (sau khi sửa 2 chỗ `page.goto(BASE + "/")`
  thành `BASE + "/index.html"` cho khớp route mới) + 6 kịch bản Playwright
  mới cho `landing.html` (vào `/` ra đúng landing không bắt đăng nhập, bấm
  "Bắt đầu" sang đúng `index.html`, đăng nhập xong quay lại `/` vẫn ra
  landing chứ không tự nhảy vào app) — không hồi quy.

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
  - `sample_zero_inflated.csv` — 100 dòng, cột `capital_gain` có 80 ô = 0 + 20 ô 500-9000: mẫu để thử cảnh báo
    IQR = 0 ở tool Giá trị bất thường (mục 23).
  - `sample_dates_vn.csv` — 30 dòng, tên cột tiếng Việt có dấu cách (`Mã`, `Ngày vào`, `Ngày ra`, `Lương`), ngày
    dd/mm/yyyy, dòng 5 và 9 có Ngày ra TRƯỚC Ngày vào: mẫu để thử tab "Biểu thức" (`[Ngày ra] >= [Ngày vào]`,
    tự nhận khuôn ngày, ép sai khuôn `%Y-%m-%d` thì báo mọi dòng chưa kiểm được; mục 24).

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

10. **Thêm thuật toán DETECT thứ 2 cho Class Noise (Distance-based, N13) +
    khung chọn 1-trong-3 phương pháp ở Bước 2 — ĐÃ CODE XONG cả backend +
    frontend cho 2/3 phương pháp, đã nối vào web, đã test qua Playwright:**
    - **Nguồn gốc quyết định**: sau khi đọc kỹ Bảng 6 (Class Noise
      Identification studies) của chính bài báo Gupta & Gupta (2019) mà
      project dựa theo (3 nhóm: Distance based / Single learning-based /
      Ensemble based), user đổi ý từ "chỉ dùng Confident Learning + Random
      Forest" sang muốn triển khai đủ cả 3 nhóm để SO SÁNH THỰC NGHIỆM —
      đây là hướng mạnh hơn hẳn cho khoá luận (có số liệu đối chứng thay vì
      chọn 1 thuật toán theo cảm tính), đồng thời lấp được khoảng trống
      "đánh giá định lượng" đã ghi là rủi ro điểm số lớn nhất ở mục roadmap.
    - **Vì sao chọn chính xác N13 (Liu & Zhang, 2012) đại diện nhóm
      Distance-based**: soi lại điểm chất lượng QA1-9 (Bảng 4/5) của TẤT CẢ
      9 paper trong nhóm Distance-based (N12,N13,N14,N15,N16,N17,N18,N47,N50)
      — chỉ N13 và N17 đạt 9/9. N17 (Sluban, Gamberger, Lavrac 2012) bị LOẠI
      dù cùng 9/9 vì tên bài thật của nó là *"Ensemble-based noise
      detection..."* — mâu thuẫn với chính category Distance-based mà bài
      báo xếp nó vào (nghi là 1 điểm chưa nhất quán của review gốc, không tự
      ý diễn giải thêm). N13 ("Noisy data elimination using mutual
      k-nearest neighbor...") vừa 9/9 vừa tên bài khớp 100% với định nghĩa
      distance-based của chính bài báo (dùng thuần khoảng cách), lại là kỹ
      thuật tổng quát cho bài toán classification (không riêng domain nào
      như gene expression/software defect của vài paper khác trong nhóm).
    - **Vì sao Ensemble-based (N29, Khoshgoftaar/Zhong/Joshi 2005 — "nhiều
      classifier khác nhau biểu quyết") CHƯA code**: user yêu cầu tập trung
      làm xong Distance-based trước ("làm cái thuật toán vừa nãy vào trong
      web đi"), Ensemble-based để sau. Thẻ chọn Ensemble-based vẫn hiện sẵn
      trên UI (khoá "sắp có", tái dùng CSS `.is-disabled`/`.badge-soon`
      sẵn có) để khung 3-lựa-chọn đã đúng hình dạng cuối cùng ngay từ bây
      giờ, tránh phải thiết kế lại UI lần 2 khi code nốt sau này.
    - **Phương pháp đánh giá N13 vs Confident Learning**: KHÔNG tự tạo
      script đánh giá mới từ đầu — tái dùng NGUYÊN VẸN kỹ thuật "cấy nhiễu
      nhãn có kiểm soát" đã có sẵn ở `evaluate_class_noise_synthetic.py`
      (biết trước chính xác dòng nào bị flip nhãn → đo được Precision/
      Recall/F1 THẬT, không chỉ suy luận gián tiếp qua cv_accuracy/baseline
      như trước). Viết `evaluate_distance_vs_confident.py` (Adult Income) +
      `evaluate_distance_vs_confident_creditcard.py` (Credit Card Fraud,
      284.807 dòng — CHƯA chạy xong vì quá chậm, RF 300 cây × 5-fold CV ×
      2 mức nhiễu + Mutual k-NN × 2 mức nhiễu trên file lớn, đã huỷ giữa
      chừng theo yêu cầu user; nếu cần chạy lại nên giảm n_estimators hoặc
      lấy mẫu con).
    - **Kết quả đo được trên Adult Income (10%/30% nhiễu cấy thêm) — BẤT
      NGỜ: Mutual k-NN (N13) THẮNG Confident Learning về F1 ở CẢ 2 mức
      nhiễu** (10%: F1 0.410 vs 0.356; 30%: F1 0.510 vs 0.489), thắng cả
      Precision ở cả 2 mức, chỉ thua Recall ở mức 30%. Lý do khả dĩ (có căn
      cứ số liệu, không suy đoán suông): `cv_accuracy` của Confident
      Learning ở CẢ 2 mức nhiễu (0.6997/0.5582) THẤP HƠN CẢ `baseline`
      (0.7067/0.6010) — theo đúng quy tắc đã ghi ở mục kiến trúc
      `confident_learning.py` ("nếu cv_accuracy thấp hơn baseline thì
      model gần như không học được gì"), Confident Learning đang chạy
      trong vùng KHÔNG đáng tin trên bộ 6-đặc-trưng-số yếu này (đã biết từ
      trước). Mutual k-NN không cần học 1 ranh giới quyết định TOÀN CỤC,
      chỉ cần cấu trúc láng giềng CỤC BỘ còn giữ được, nên ít bị ảnh hưởng
      hơn khi tín hiệu toàn cục yếu — độ phủ (% dòng có láng giềng lẫn
      nhau) vẫn cao (97.1%), không bị lỗi do dữ liệu thưa. **Lưu ý khi
      trích dẫn trong khoá luận**: đây là kết quả trên ĐÚNG 1 bộ dữ liệu
      (đặc trưng yếu) + 1 kiểu cấy nhiễu (random flip đồng đều) — KHÔNG đủ
      để kết luận "N13 luôn tốt hơn Confident Learning nói chung", chỉ nên
      diễn đạt "trên dữ liệu có đặc trưng dự đoán yếu, phương pháp dựa
      khoảng cách tỏ ra ổn định hơn phương pháp dựa trên model học máy".
    - **Chuẩn hoá response JSON cho cả 2 method**: `app.py` đổi tên trường
      findings từ `confident_label`/`margin` (gốc, chỉ đúng với Confident
      Learning) sang `suggested_label`/`score` (trung lập, đúng với CẢ 2
      method) — nhờ vậy `renderClassFindingsTable()` ở FE dùng CHUNG được 1
      hàm cho cả 2 kiểu kết quả, chỉ đổi CHỮ header hiển thị
      (`CLASS_SCORE_LABELS`), không phải viết 2 hàm render bảng riêng biệt.
      Diagnostics thì KHÔNG chuẩn hoá chung được (2 thuật toán đo "độ tin
      cậy" theo 2 cách hoàn toàn khác bản chất — model accuracy vs coverage
      láng giềng), nên giữ response field `"method"` ở gốc để FE dispatch
      sang đúng hàm render (`renderClassResultsSingleLearning()` vs
      `renderClassResultsDistance()`).
    - **Đã test qua Playwright THẬT (không chỉ gọi API trực tiếp)** — 2
      luồng độc lập: (1) upload Adult Income → Class Noise → Distance-based
      → tick 6 cột số → detect → kiểm tra đúng card ẩn/hiện + bảng đúng
      header "Gợi ý nhãn"/"Tỉ lệ bất đồng"; (2) luồng y hệt nhưng chọn
      Single learning-based → verify CV accuracy 77.99%/baseline 75.92%
      KHỚP ĐÚNG số liệu lịch sử đã biết (không bị hồi quy sau khi sửa
      chung 1 endpoint cho cả 2 method) + bảng precision/recall/confusion
      matrix hiện đúng, header "Model tự tin"/"Margin" không đổi.

11. **Thêm thuật toán DETECT thứ 3 (Ensemble-based, N29) + nối ĐỦ CẢ 3
    phương pháp vào web — ĐÃ CODE XONG, ĐÃ NỐI VÀO WEB, ĐÃ TEST QUA
    PLAYWRIGHT cho cả 3 luồng:**
    - **Lý do chọn đúng 3 classifier `LogisticRegression`/`GaussianNB`/
      `LinearSVC`** — lúc đầu định dùng Decision Tree + KNN trong bộ 4, user
      TỰ PHÁT HIỆN 2 vấn đề trùng hướng nghiêm trọng trước khi code: (1)
      KNN trong ensemble sẽ trùng cơ chế với chính N13 (cùng hỏi "láng giềng
      gần nghĩ gì"), (2) Decision Tree sẽ trùng họ với Random Forest của
      Confident Learning (RF vốn LÀ nhiều Decision Tree gộp lại) — cả 2 sẽ
      làm 2/3 phương pháp trong hệ thống đưa ra phán đoán TƯƠNG QUAN nhau
      thay vì độc lập, làm yếu mục đích so sánh 3 góc nhìn tách biệt. Đã đổi
      sang `LogisticRegression` (tuyến tính) + `GaussianNB` (xác suất) +
      `LinearSVC` (biên cực đại) — 3 họ thuật toán không trùng cả Random
      Forest (tree-based) lẫn Mutual k-NN (instance-based). Cũng đã cân nhắc
      và LOẠI SVM kernel phi tuyến (vd RBF) dù có thể bắt ranh giới cong tốt
      hơn LinearSVC — lý do: `sklearn` tự ghi rõ SVM kernel có độ phức tạp
      O(n²) đến O(n³) theo số dòng, "hard to scale to datasets with more
      than a couple of 10000 samples" — với file thầy 588.393 dòng sẽ CHẬM
      GẤP HÀNG TRĂM/NGHÌN LẦN LinearSVC, lặp lại đúng kiểu vấn đề đã gặp với
      Random Forest trên Credit Card Fraud (phải huỷ giữa chừng).
    - **Kết quả thực nghiệm trên Adult Income** (`evaluate_ensemble_vs_others.py`,
      cấy nhiễu có kiểm soát, so cả 3 thuật toán): N29 THẮNG CẢ 2 CHỈ SỐ ở
      mức nhiễu 30% (Precision 0.495, Recall 0.691 → F1 0.576, cao nhất
      trong 3) — ở mức 10% ngang Confident Learning về F1 (0.358 vs 0.356)
      nhưng Recall cao nhất (0.730, đổi lại Precision thấp nhất 0.237).
      `per_classifier_accuracy` cho thấy điều đáng chú ý: chỉ `GaussianNB`
      học rõ ràng tốt hơn baseline (+1.8 đến +3.55 điểm %), còn
      `LogisticRegression`/`LinearSVC` đều THẤP HƠN baseline ở cả 2 mức
      nhiễu (ranh giới tuyến tính không hợp với dữ liệu Adult Income) — dù
      vậy kết quả TỔNG HỢP (biểu quyết) vẫn tốt hơn từng classifier riêng lẻ,
      cho thấy ngay cả khi 2/3 thành phần yếu, sự BẤT ĐỒNG giữa chúng vẫn
      mang tín hiệu hữu ích.
    - **Tốc độ — đã đo thật, xem lại mục kiến trúc `ensemble_based.py`**:
      dù train tới 3 model (so với 1 của Confident Learning), N29 vẫn nhanh
      hơn Random Forest ~6 lần (2.15-2.40s vs 12.72-13.47s trên Adult
      Income) — vì RF thực chất là 300 cây con cộng lại (mỗi cây tốn kém),
      còn 3 classifier kia là bài toán tối ưu LỒI (hoặc không cần tối ưu gì
      như GaussianNB, chỉ tính thống kê 1 lần) nên hội tụ rất nhanh.
    - **Nối vào web**: mở khoá thẻ Ensemble-based ở Bước 2 (gỡ `is-disabled`/
      `badge-soon` khỏi HTML, không xoá CSS class vì có thể cần lại sau),
      thêm `#class-params-ensemble` (chỉ `cv_folds`) ở Bước 3, thêm
      `renderClassResultsEnsemble()` ở Bước 4 (xem mục kiến trúc frontend ở
      trên), backend thêm nhánh `method == "ensemble_based"` trong
      `class_noise_detect_api()` gọi thẳng `detect_class_noise_ensemble()`.
      Đã test qua Playwright CẢ 3 luồng trong cùng 1 lượt (Ensemble-based
      mới + Single learning-based + Distance-based cũ) — không luồng nào
      hồi quy, số liệu CV accuracy/coverage của 2 luồng cũ khớp y hệt lịch
      sử đã biết trước đó.

12. **Tự đoán kiểu dữ liệu (dtype) cho từng cột ở Bước 3 Attribute Noise —
    ĐÃ CODE XONG, ĐÃ TEST QUA PLAYWRIGHT:**
    - **Nguồn gốc yêu cầu**: user tạm gác việc chỉnh thuật toán detect ("lú
      quá, lúc khác check và sửa sau"), chuyển sang xin cải thiện trải
      nghiệm giao diện. Yêu cầu cụ thể: dropdown "Kiểu dữ liệu" ở Bước 3
      lúc đó LUÔN mặc định "Văn bản (text)" cho MỌI cột (kể cả cột rõ ràng
      là số như `age`), bắt người dùng phải tự đổi tay từng cột một với file
      nhiều cột — muốn hệ thống TỰ ĐOÁN kiểu hợp lý, nhưng vẫn giữ nguyên
      dropdown để tự sửa lại được, không khoá cứng.
    - **Đặt logic đoán ở BACKEND** (`guess_column_dtype()` trong
      `attribute_noise/pipeline.py`), KHÔNG viết lại bằng JS — đúng quyết
      định kiến trúc đã chốt từ đầu dự án ("mọi detect/xử lý LUÔN gọi backend
      Flask thật", xem mục `frontend/` ở trên) — tái dùng NGUYÊN VẸN
      `EMAIL_RE`/`PHONE_RE`/`INTEGER_RE` đã có sẵn trong `detectors.py`
      thay vì viết regex riêng lần 2.
    - **Thứ tự kiểm tra kiểu (từ CHẶT nhất tới LỎNG nhất)**: email → phone →
      date (thử 4 định dạng phổ biến) → integer → float → category → text.
      Phải kiểm tra theo thứ tự này vì 1 giá trị có thể khớp NHIỀU kiểu cùng
      lúc (vd số điện thoại cũng toàn chữ số, nếu kiểm tra integer TRƯỚC
      phone sẽ đoán nhầm thành integer).
    - **Ngưỡng 90% khớp** (không bắt buộc 100%) cho mỗi kiểu — cố tình THẤP
      hơn 100% để chấp nhận vài ô lỗi định dạng trong cột (đó CHÍNH LÀ
      attribute noise mà hệ thống sẽ đi tìm ở bước sau) mà không làm hỏng
      việc đoán đúng kiểu tổng thể của cả cột.
    - **CATEGORY dùng ngưỡng cardinality** (≤50 giá trị khác nhau VÀ chiếm
      ≤50% tổng số dòng không rỗng) thay vì so khớp định dạng như các kiểu
      khác — vì category không có "định dạng" cố định (vd "Nam"/"Nữ" hay
      "Sales"/"HR"/"IT" trông không giống nhau về mặt ký tự), chỉ phân biệt
      được qua việc SỐ GIÁ TRỊ KHÁC NHAU ít so với tổng số dòng. Ngưỡng kép
      (vừa giới hạn SỐ TUYỆT ĐỐI vừa giới hạn TỈ LỆ) để không đoán nhầm 1 cột
      toàn giá trị khác nhau (vd `full_name`) thành category chỉ vì file nhỏ.
    - **Đã verify kỹ trên 2 bộ dữ liệu khác hẳn nhau**: Adult Income (6 cột
      số đều ra đúng `integer`, 9 cột chữ đều ra đúng `category`) và bộ nhân
      viên `noisy_employee_dataset.csv` (đủ cả 7 kiểu: `id`→integer,
      `full_name`→text, `age`→integer, `gender`→category, `email`→email,
      `department`→category, `salary`→float, `join_date`→date, `phone`→phone,
      `performance_score`→float) — ĐOÁN ĐÚNG TUYỆT ĐỐI cả 2 bộ, không sai
      cột nào. Đã test qua Playwright thật (không chỉ gọi hàm Python trực
      tiếp) — dropdown trên UI hiện đúng giá trị đoán được cho từng cột.
    - **Không ảnh hưởng logic detect thật**: `guessed_dtypes` CHỈ dùng để
      set `dtype` KHỞI ĐẦU của `state.columnConfig[cột]`
      (`defaultColumnConfig(dtype)`, đổi tham số mặc định từ cứng "text"
      sang nhận dtype đoán được) — khi người dùng bấm "Detect Noise", backend
      vẫn dùng ĐÚNG dtype người dùng đang chọn trên dropdown lúc đó (có thể
      đã tự sửa lại), không phải giá trị đoán ban đầu.

13. **Bước 5 AN TOÀN (không xoá nhầm, xem trước, hoàn tác) — ĐÃ CODE XONG, ĐÃ KIỂM CHỨNG:**
    - **Nguồn gốc**: đánh giá UX phát hiện 1 cú bấm "Áp dụng" ở Bước 5 xoá cả nhóm (đã chạy thật:
      313 → 309 dòng) vì 3 thứ cộng lại: dropdown mặc định `remove_row` (đứng đầu `ACTION_TABLE`),
      mọi checkbox tick sẵn, và `handleGroupApply` tự mở bảng rồi gửi luôn. Không có hoàn tác.
    - **Lớp 1 (mặc định an toàn)**: `pickDefaultAction()` + `actionOptionsHTML()` trong `script.js`;
      `validateRowActions()` chặn Áp dụng khi dòng chưa chọn cách xử lý HOẶC chọn "Tự nhập tay" mà
      để trống giá trị (giá trị rỗng sẽ ghi đè ô thành chuỗi rỗng = âm thầm tạo ô thiếu).
    - **Lớp 2 (xem trước)**: `dry_run` ở backend + hộp xác nhận ở FE, chỉ hỏi khi có XOÁ dòng.
      Sau khi chạy thử, FE tính lại danh sách dòng tick và so với lúc bấm: khác thì bỏ, bắt bấm lại.
    - **Lớp 3 (hoàn tác)**: `HANDLING_HISTORY[file_id]` giữ nhật ký (tối đa 20 bước) và snapshot
      DataFrame TRƯỚC mỗi bước (tối đa 5 bước gần nhất). Snapshot lưu bằng THAM CHIẾU, không `.copy()`,
      vì mọi lần sửa đều tạo DataFrame MỚI (`apply_handling()` bắt đầu bằng `df.copy()`, xoá trùng
      dùng `df.drop()`) -- không có chỗ nào sửa tại chỗ `WORKING_FILES`. Bảng quá lớn
      (`UNDO_MAX_CELLS` = 5.000.000 ô) thì không lưu snapshot, chỉ còn "Về dữ liệu gốc" (luôn dùng được
      vì `UPLOADED_FILES` không bao giờ đổi). Chỉ giữ lịch sử của 3 file thao tác gần nhất
      (`MAX_FILES_WITH_HISTORY`). Bước "rỗng" (không đổi gì) không ghi vào nhật ký.
    - **Độ an toàn khi chạy song song**: `HANDLING_LOCK` bao toàn bộ đọc-sửa-ghi ở 3 route; `detect_noise`
      chạy TRƯỚC khi ghi `WORKING_FILES`/lịch sử (detect lỗi thì dữ liệu nguyên vẹn); cờ `dry_run`
      đọc bằng `_as_bool()` (`bool("false")` là True trong Python). FE khoá thao tác khi đang chờ server.
    - **Quyết định đổi hành vi có chủ đích**: `/api/detect-noise` detect trên bản đang làm việc (xem
      mục endpoint). Lý do: Bước 5 luôn thao tác trên bản đang làm việc nên Bước 4 phải khớp; muốn
      detect lại từ đầu thì bấm "Về dữ liệu gốc". `/api/class-noise/*` vẫn đọc bản GỐC (chưa đổi).
    - **Cách kiểm chứng (để trích trong khoá luận)**: workflow 5 tác tử độc lập (2 reviewer đọc diff +
      3 tester Playwright/Flask), mỗi lỗi báo cáo được 1 tác tử khác thử tái hiện: 13 lỗi xác nhận
      (không lỗi nào bị bác bỏ) → sửa hết → 11 kịch bản tái hiện lỗi đều PASS + các bộ test cũ không
      hồi quy. Lỗi điển hình tìm được: ghi dữ liệu TRƯỚC khi detect (detect lỗi vẫn bị sửa), mất cập
      nhật khi 2 request chạy chồng, upload file mới không reset `maxReached` nên bấm thanh bước 5
      vẫn áp dụng nhóm lỗi của file CŨ lên file MỚI.
    - **Giới hạn đã biết** (chấp nhận cho demo 1 người dùng): lịch sử/snapshot nằm trong RAM nên mất khi
      server restart; không có "làm lại" (redo); `HANDLING_LOCK` là khoá toàn cục, không theo file_id.

14. **Tài khoản đăng nhập — Multi-User THẬT (không phải demo-login) — ĐÃ CODE
    XONG, ĐÃ KIỂM CHỨNG:**
    - **Nguồn gốc**: trước đây MỌI request gọi đúng `file_id` đều đọc/sửa
      được file đó, không phân biệt ai gửi request — người dùng yêu cầu
      thiết kế hệ thống tài khoản thật (có trang hồ sơ + đăng ký/đăng nhập
      riêng), kèm yêu cầu rõ ràng: phải kiểm tra kỹ các chức năng cũ KHÔNG
      bị hồi quy sau khi sửa.
    - **Vì sao SQLite, không phải PostgreSQL/MySQL**: quy mô demo khoá luận
      (vài người dùng cùng lúc) không cần 1 server database riêng —
      sqlite.org (nguồn chính thức) ghi nhận SQLite chịu được tới hàng trăm
      nghìn lượt truy cập/ngày. Tài khoản là dữ liệu DUY NHẤT trong dự án
      cần LƯU LÂU DÀI qua các lần restart server (khác `UPLOADED_FILES`/
      `WORKING_FILES` chỉ sống trong RAM theo thiết kế, xem mục kiến trúc
      `accounts/db.py`).
    - **Vì sao Flask phải tự phục vụ luôn frontend** (`static_folder=
      "frontend"`, route `GET /`): cookie session (cách lưu trạng thái đăng
      nhập) chỉ gửi kèm đáng tin cậy khi frontend + backend CÙNG 1 origin
      (cùng host:port) — trước đây frontend mở riêng (`file://` hoặc port
      khác) là 2 origin khác nhau với backend, trình duyệt hiện đại chặn/
      giới hạn khá chặt cookie "cross-site". Gộp chung origin giải quyết
      TẬN GỐC, chỉ cần đổi 1 hằng số `API_BASE` (từ URL tuyệt đối sang
      chuỗi rỗng) thay vì sửa hàng chục chỗ gọi `fetch()` rải rác trong
      `script.js` để thêm `credentials: "include"`.
    - **Mẫu kiểm tra quyền sở hữu dùng lại ĐƯỢC CHO MỌI route** (không viết
      riêng logic kiểm tra cho từng route): `_require_file_owner(file_id)`/
      `_require_download_owner(download_id)` trả về `None` (hợp lệ, route
      chạy tiếp) hoặc 1 response lỗi sẵn sàng `return` luôn — gắn ở ĐẦU của
      9 route cũ có dùng `file_id`/`download_id`. Lỗi trả về CỐ TÌNH giống
      hệt nhau dù file thật sự không tồn tại HAY tồn tại nhưng thuộc người
      khác (không tiết lộ sự tồn tại của file người khác) — khớp đúng
      pattern bảo mật đã tham khảo từ 1 trang web tương tự (CYD, trang
      Security: "requests for another account's dataset are answered as if
      it did not exist").
    - **Giao diện trang đăng nhập/đăng ký** (`#panel-auth`): lúc đầu dựng
      giống mọi panel khác (card đơn giản), sau đổi sang bố cục CHIA ĐÔI
      MÀN HÌNH lấy cảm hứng 1 trang landing tham khảo (CYD) theo yêu cầu
      làm đẹp giao diện — nhưng GIỮ NGUYÊN token màu/font của chính SPARK
      (kem/teal, IBM Plex) để không lệch tông với Bước 1-5, KHÔNG sao y hệt
      màu đen/trắng/cam của trang tham khảo (đã hỏi ý kiến người dùng trước
      khi chọn hướng này). Nửa phải demo tĩnh dùng ĐÚNG 11 màu `.cell-flag-*`
      thật của app thay vì ảnh trang trí rời rạc — vừa đẹp vừa cho thấy
      luôn tính năng cốt lõi ngay màn hình đầu tiên.
    - **1 lỗi CSS thật đã gặp + đã fix lúc làm giao diện mới**: class
      `field-grow` (vốn đặt `flex-basis: 220px` cho field nằm NGANG trong
      `.field-row`) bị gắn nhầm vào các field nằm DỌC trong form đăng nhập/
      hồ sơ — trong flex CỘT, `flex-basis` lại tính theo chiều CAO nên mỗi
      ô input bị kéo cao 220px, đẩy nút submit ra ngoài màn hình nhìn thấy
      được. Phát hiện qua `getBoundingClientRect()` debug bằng Playwright
      (không phải nhìn mắt thường), đã fix bằng cách bỏ class đó khỏi 2
      panel mới, giữ nguyên các chỗ dùng đúng mục đích khác trong file.
    - **Cách kiểm chứng**: 43 test Flask test client (gồm xác nhận 1 user
      KHÔNG đụng được file/download của user khác qua TẤT CẢ route liên
      quan) + 23 kịch bản Playwright trình duyệt thật (đăng ký/đăng nhập/
      đăng xuất/đổi mật khẩu + toàn bộ luồng Attribute Noise 5 bước cũ chạy
      lại sau khi bắt buộc đăng nhập, xác nhận không hồi quy) — cả 2 bộ
      PASS 100% trước khi commit.
    - **Giới hạn đã biết** (chấp nhận cho demo khoá luận): `secret_key`
      sinh ngẫu nhiên mỗi lần restart server (ai đang đăng nhập bị đăng
      xuất hết) trừ khi đặt biến môi trường `SPARK_SECRET_KEY` cố định;
      không có "quên mật khẩu"/email xác thực; dữ liệu file vẫn chỉ sống
      trong RAM như trước (chỉ TÀI KHOẢN mới lưu lâu dài).

15. **Convert File — 3 tool đổi định dạng (đổi delimiter CSV, CSV ⇄ JSON),
    trang riêng `convert.html` — ĐÃ CODE XONG, ĐÃ KIỂM CHỨNG:**
    - **Nguồn gốc**: sau khi xem trang "Free Tools" của 1 trang web tương tự
      (CYD) — các tool convert định dạng nhỏ, độc lập với sản phẩm chính —
      người dùng muốn SPARK có tương đương, nhưng CHỌN KHÁC CYD ở 2 điểm có
      chủ đích: (1) bắt buộc đăng nhập (CYD để công khai, không cần tài
      khoản), (2) gộp cả 3 tool vào 1 trang HTML duy nhất (CYD tách mỗi tool
      1 trang riêng) — quyết định dựa trên sở thích/quy mô của chính dự án
      này, không phải "đúng/sai" so với CYD.
    - **Vì sao dùng `csv`/`json` chuẩn của Python, KHÔNG dùng pandas**: 3
      tool này chỉ đổi ĐỊNH DẠNG, không cần hiểu ý nghĩa cột/dtype như
      `attribute_noise`/`class_noise` — pandas hay "giúp đỡ" quá tay lúc
      đọc/ghi (vd tự ép chuỗi "007" thành số 7, tự suy đoán ô rỗng là NaN),
      đúng kiểu rủi ro mà `attribute_noise/pipeline.py::load_data()` đã
      phải tắt bằng `dtype=str`/`keep_default_na=False` — ở đây đơn giản
      hơn hẳn là dùng thẳng `csv`/`json` chuẩn, giữ NGUYÊN VĂN từng giá trị.
    - **Copy giao diện KHÔNG sao y nguyên văn claim của CYD**: trang tham
      khảo ghi "nothing uploaded"/"no account needed" (xử lý hoàn toàn
      trong trình duyệt, không cần tài khoản) — SPARK CHỦ ĐỘNG chọn ngược
      lại (luôn qua backend Flask thật + bắt đăng nhập, đúng quyết định
      kiến trúc đã chốt từ đầu dự án), nên badge ở `convert.html` đổi thành
      "🔒 Cần đăng nhập"/"🧮 Luôn xử lý qua backend Flask thật" — KHÔNG giữ
      nguyên câu chữ cũ vì sẽ sai sự thật với chính cách SPARK hoạt động.
    - **`convert.html` là trang ĐỘC LẬP, không phải 1 panel trong 5 bước
      chính** — không có khái niệm `file_id`, mỗi lần Convert xong ngay
      trong 1 request. Vẫn bắt đăng nhập bằng cách DÙNG CHUNG cookie session
      với `index.html` (cùng origin) — `convert.js::checkAuth()` gọi `GET
      /api/auth/me`, chưa đăng nhập thì chuyển hướng thẳng về `index.html`
      thay vì viết lại 1 form đăng nhập lần 2. Nút "Hồ sơ" điều hướng về
      `index.html?open=profile` (query param để tự mở `#panel-profile` ngay
      khi tải xong, tránh phải bấm thêm 1 lần).
    - **Cách kiểm chứng**: 29 test độc lập cho `converters/transform.py`
      (không qua Flask) + 23 test Flask test client cho 3 route `/api/
      convert/*` (gồm chặn chưa đăng nhập → 401) + 16 kịch bản Playwright
      trình duyệt thật (cả 3 tool, cả 2 cách nhập file/dán text, tải file
      kết quả về, lỗi JSON sai cú pháp hiện đúng chỗ không vỡ trang) — cả 3
      bộ PASS 100% trước khi commit. Bộ test Playwright luồng Attribute
      Noise 5 bước cũ (23 kịch bản ở mục 14) chạy lại SAU KHI thêm tính
      năng này, xác nhận không hồi quy.

17. **Free Tools — 4 công cụ xử lý nhiễu KHÔNG cần cấu hình (Xoá dòng trùng/
    Cắt khoảng trắng thừa/Điền-xoá ô trống đơn giản/Xoá dòng trống hoàn
    toàn), trang riêng `tools.html` — ĐÃ CODE XONG, ĐÃ KIỂM CHỨNG:**
    - **Nguồn gốc**: sau khi xem lại trang tham khảo (CYD) có khối "Free
      Tools" ở header (dropdown các tool nhỏ, mỗi tool 1 trang bố cục trái
      upload/phải kết quả), user muốn SPARK có khối tương tự, nhưng nêu
      đúng vấn đề thật: SPARK đang có 11 loại attribute noise + Class Noise,
      TOÀN BỘ đều bắt cấu hình tay (chọn cột, chọn dtype, chọn tham số...) ở
      Workspace 5 bước — không giống CYD có sẵn vài thao tác "bấm phát ăn
      ngay". Hỏi "nên gộp cái nào với cái nào" → thống nhất chia 11 loại
      thành 2 nhóm theo TIÊU CHÍ DUY NHẤT "có cần cấu hình tay hay không":
      - **Free Tools (4 loại, KHÔNG cần khai gì)**: `duplicate_row` (xoá
        dòng trùng — chỉ cần chọn cột so sánh TUỲ CHỌN, không bắt buộc),
        `whitespace_noise` (cắt khoảng trắng — vốn đã "luôn an toàn, auto"
        ở Workspace), `missing_value` RÚT GỌN (chỉ còn remove row/giá trị cố
        định, bỏ impute mean/median/KNN/mode vì những lựa chọn đó CẦN hiểu
        dtype/ý nghĩa cột), và 1 loại HOÀN TOÀN MỚI "xoá dòng trống hoàn
        toàn" (tương đương "Remove empty rows" của CYD — SPARK trước đó
        CHƯA có detector cấp dòng nào xét "cả dòng tự nó trống" ngoài
        `duplicate_row`, vốn so sánh GIỮA các dòng chứ không xét 1 dòng).
      - **Giữ nguyên ở Workspace (7 loại + Class Noise, CẦN khai dtype/tham
        số/nhãn...)**: `format_noise`, `out_of_range`, `outlier`,
        `inconsistent_category`, `missing_value` BẢN ĐẦY ĐỦ (còn nguyên 5
        lựa chọn impute), 4 rule liên cột, Class Noise (3 thuật toán).
      - Lưu ý: "Thiếu giá trị" xuất hiện ở CẢ 2 nhóm — KHÔNG phải 2 detector
        khác nhau, mà CÙNG 1 khái niệm (`_is_missing_text`, giống định nghĩa
        `missing_value` ở Workspace) nhưng Free Tools chỉ lộ ra 2/5 hành
        động xử lý để giữ đúng tinh thần "không cấu hình".
      - Go-ahead cuối cùng: **"OKe làm luôn đi t xem nào."**
    - **Kiến trúc tái dùng tối đa, không viết lại logic đã có**:
      `attribute_noise/quick_tools.py` (xem mục kiến trúc ở trên) import
      trực tiếp `_clean_whitespace_value()`/`_is_missing_text()` từ
      `attribute_handling.py` thay vì copy lại — đảm bảo Free Tools và
      Workspace đầy đủ LUÔN ra cùng 1 kết quả cho cùng 1 dữ liệu, không bao
      giờ lệch nhau do 2 nơi định nghĩa "thiếu"/"khoảng trắng thừa" trôi
      dần theo thời gian. KHÔNG tái dùng `apply_handling()` (bản đầy đủ) vì
      hàm đó bắt buộc phải có `findings`/`ColumnNoiseConfig` — tức là phải
      chạy qua bước "detect" trước, đi ngược lại đúng tinh thần "1 request
      là xong" của Free Tools; viết 4 hàm trực tiếp thao tác DataFrame thay
      vào đó, ngắn gọn hơn hẳn so với dựng `findings` giả để gọi hàm cũ.
    - **4 route `/api/noise-tools/*` vận hành giống hệt 3 route Convert File**
      (mục 15) — KHÔNG có `file_id`, xong trong 1 request, `@login_required`
      (đúng nguyên tắc "mọi route xử lý dữ liệu đều bắt đăng nhập" đã chốt
      từ Convert File) — chỉ khác ở chỗ phải đọc dữ liệu bằng pandas
      (`_read_df_for_noise_tool()`) vì đây là thao tác BẢNG, không phải đổi
      định dạng văn bản thuần như converters/transform.py.
    - **`tools.html`/`tools.js` dựng Y HỆT bố cục `convert.html`** (xem mục
      kiến trúc frontend/ ở trên) — quyết định có chủ đích: người dùng vừa
      mới quen mắt với bố cục Convert File, giữ nguyên bố cục cho Free Tools
      giúp không phải học lại cách dùng trang mới; khác biệt DUY NHẤT về
      hành vi là luôn hiện bảng CSV (Free Tools không có tool nào xuất JSON).
    - **Quyết định riêng — ô TEXT gõ tên cột thay vì dropdown ở "Điền/xoá ô
      trống"**: đã cân nhắc thêm 1 API "xem trước danh sách cột" (giống
      `/api/upload` trả `columns`) để dựng dropdown, nhưng sẽ phá vỡ tính
      "1 request duy nhất" mà cả Convert File lẫn 3 Free Tools còn lại đều
      giữ được — chọn ô text đơn giản hơn, gõ sai tên cột thì backend trả
      lỗi 400 rõ ràng ngay, chấp nhận được cho mức độ "free tool" hướng tới.
    - **Cách kiểm chứng**: 23 test độc lập cho `quick_tools.py` (gọi thẳng
      hàm Python, không qua Flask) + 26 test Flask test client cho 4 route
      (gồm chặn chưa đăng nhập → 401, lỗi cột/giá trị → 400, upload file
      thật lẫn dán text) + 18 kịch bản Playwright trình duyệt thật (bounce
      về index.html khi chưa đăng nhập, điều hướng qua lại bằng link header,
      cả 4 tool chạy với dữ liệu thật, tải file CSV kết quả về, lỗi cột sai
      tên hiện đúng chỗ) — cả 3 bộ PASS 100% trước khi commit. Chạy lại bộ
      test Flask (`test_accounts_flow.py` 43 + `test_convert_routes.py` 23)
      và Playwright cũ (`playwright_test.js` 23 + `playwright_convert_test.js`
      16) SAU KHI thêm tính năng này, xác nhận không hồi quy.

18. **Dựng lại giao diện "Denoise" (workspace.html) thay giao diện 5 bước cũ — ĐÃ XONG, đang dùng:**
    - Nguồn gốc: user thấy UI cũ "dởm" so với trang tham khảo (CYD) → dựng lại theo khuôn
      CYD nhưng GIỮ chữ/ý riêng của SPARK (không sao y claim của CYD; badge ghi đúng sự thật
      "cần tài khoản, qua backend Flask"). Làm lần lượt: header + Free Tools → Convert +
      đăng nhập → trang chủ/Guide/Bảo mật/Quyền riêng tư → Cần cấu hình + Class Noise → các
      lần chỉnh sau phản hồi thật. 3 file cũ (`index/landing/convert/tools.html`) giữ lại.
    - Quyết định "KHÔNG có chế độ phân tích cục bộ bằng JS" vẫn đúng: mọi xử lý gọi backend.
    - Phân nhóm tool theo TIÊU CHÍ "có cần khai cấu hình không" (mục 17): "Tự động"/Free
      Tools (không cần khai) vs "Cần cấu hình" (phải khai cột/tham số) vs Convert. Sai định
      dạng chuyển sang Free Tools (quét MỌI cột, bảng kiểu dữ liệu từng cột sửa được).
19. **Tool "Ô trống" gộp 3 tool cũ + "Điền tay từng ô":** Xoá dòng trống + Điền/xoá ô trống
    + Thiếu giá trị nâng cao → 1 tool `/api/noise-tools/blanks`, cách xử lý đặt THEO TỪNG
    cột (xoá dòng / điền từ ô phía trên `fill_down` / giá trị cố định / trung bình / trung vị /
    KNN / giá trị phổ biến nhất — danh sách hợp lệ khác nhau theo kiểu cột, xem
    `BLANK_ACTIONS_BY_DTYPE`; email/SĐT/ngày/chữ không có cách điền trung bình). Cách "điền tay"
    mở bảng các dòng có ô trống (`/blank-rows`) để gõ riêng từng ô (`cell_values`). Giá trị
    điền được kiểm theo kiểu cột (số nguyên phải là số nguyên...). Lỗi thật đã gặp + sửa:
    `guess_column_dtype` từng đếm NA/-/? thành giá trị (đã dùng `_non_missing_values`);
    chạy chồng (dán text rồi bấm Chạy ngay) hiện bảng cũ; "Tải file khác" giữ file cũ;
    "Bắt đầu lại từ gốc" trả kết quả bước đầu thay vì gốc — đều đã sửa + test.
20. **3 tool Cần cấu hình kiểm NHIỀU cột (Không nhất quán → Ngoài khoảng → Giá trị bất
    thường):** yêu cầu của user: chỉ liệt kê cột đúng kiểu (hàm đoán kiểu cũ), có nút thêm
    form cột, sau Phát hiện có bảng "cột nào bao nhiêu lỗi", xử lý được từng cột, bảng bên
    phải tô lỗi của mọi cột. Làm 1 khung chung `CF_MULTI` (xem bullet frontend) + backend
    `items`/`per_column`/`actions` (xem bullet routes). Quyết định có chủ đích:
    - Cách xử lý mặc định "— Chọn cách xử lý —" với tool có `remove_row` (an toàn).
    - Nhiều cột cùng chọn `remove_row` → xoá HỢP (dòng lỗi ở BẤT KỲ cột đó đều bị xoá).
    - Giá trị cố định phải hợp kiểu cột (backend kiểm, kể cả cách gửi 1 cột cũ).
    - Tool nào cũng liệt kê cột theo KIỂU ĐOÁN: cột số lẫn >10% chữ bị đoán là text nên
      KHÔNG hiện ở tool số → xử lý bằng Sai định dạng trước rồi nối tiếp.
    - Form đầu mặc định là cột đầu tiên đúng kiểu (thường là `id`) — chưa tự bỏ qua cột id.
    - Kiểm chứng: dữ liệu nhân viên có đáp án (`noise_ground_truth_large.csv`): 3 cột 1
      lượt bắt đúng 16 ô out_of_range cấy sẵn, bằng tổng 3 lần kiểm từng cột riêng.
21. **Nhiều phương pháp (IQR + Z-score) trên 1 cột:** ô lỗi = HỢP các phương pháp; "kéo về biên"
    = GIAO các khoảng (biên chặt hơn). Công thức biên dùng chung ở `outlier_bounds()` để
    detect và cap không lệch. Backend trả `methods` + `both_count` (số ô cả hai cùng bắt)
    để bảng lỗi ghi "IQR 1.5 bắt 4 ô · Z-score 3 bắt 2 ô · cả hai cùng bắt 2 ô" (số ô lỗi
    của cột là HỢP nên không bằng tổng). Đã test đối chiếu bản cũ 360 ca + dữ liệu có ô
    mỗi phương pháp bắt riêng (cột `d` seed 16523).
22. **Chỉnh giao diện sau phản hồi thật:** tiêu đề chữ HOA to dùng `line-height` ≥ 1.2 (chữ
    hoa tiếng Việt có dấu chồng Ễ/Ệ/Ữ/Ạ; 0.95-1.1 làm dấu dòng dưới chạm dòng trên — đã sửa
    mọi tiêu đề lớn: hero, `.tx-title`, `.tool-hero-headline`, `.ft-h2`, class-noise,
    auth, menu); bỏ dòng ghi chú "Cần tài khoản · xử lý qua backend Flask · không qua bên
    thứ ba" dưới nút hero (giữ eyebrow "[ Denoise · dò & xử lý nhiễu dữ liệu ]"); chân trang
    tăng cỡ chữ (câu mời 30-44px, link cột 15-20px, tiêu đề cột 12.5-15px, dòng cuối
    12-14.5px, dùng `clamp` để co theo màn).
23. **VIỆC NỢ / ĐÃ ĐỀ XUẤT NHƯNG CHƯA LÀM (user bảo tạm gác, nhớ NHẮC lại):**
    - **[ĐÃ LÀM] Cảnh báo IQR suy biến ở tool Giá trị bất thường.** Cột "zero-inflated" (vd
      80% là 0, giống `capital.gain` của Adult Income) → Q1=Q3=0 → vùng bình thường `[0,0]`
      → IQR gắn cờ MỌI ô khác 0 (thử: 20/20) và "Kéo về biên" ép hết về 0 (mất dữ liệu thật);
      Z-score chỉ gắn cờ 5 ô. Class Noise đã có chốt chặn (bỏ qua cột IQR=0, tự bỏ cột đó).
      Tool này CỐ TÌNH KHÔNG tự bỏ qua cột mà chỉ CẢNH BÁO (người dùng quyết định): hàm
      `iqr_degenerate_info()` ở `detectors.py` (Q1==Q3 và ≥4 ô số → trả giá trị phổ biến + tỉ lệ),
      `/api/noise-tools/configured` (detect, tool outlier) trả `per_column[].warnings` =
      `[{code:"iqr_zero", threshold, value, share, valid_count}]` khi cột có ô lỗi VÀ có luật IQR;
      FE (`renderCfMultiSummary`) hiện khung vàng ".cf-sum-warn" + dòng đỏ ".cf-sum-risk" chỉ hiện
      khi chọn cách xử lý đổi dữ liệu (không phải "skip"/"keep"). Kết quả detect KHÔNG đổi.
      Mẫu để thử: `data/sample_zero_inflated.csv` (cột `capital_gain` 80 ô = 0 + 20 ô 500-9000).
    - [ĐÃ LÀM, mục 26] Hai việc nhỏ cùng đợt: báo "Cấu hình đã đổi, bấm Phát hiện lại" (Áp dụng
      dùng cấu hình lúc Phát hiện dù form đã sửa); báo "Sẽ xoá N dòng" trước khi Áp dụng. Hộp xác nhận +
      Hoàn tác như Bước 5 cũ cho 3 tool này: ĐÃ LÀM ở mục 27.
    - **Rule liên cột — đã rà, thiếu (cập nhật sau mục 24: (1), (5), (7) và lỗi chia cho 0 ĐÃ XONG ở
      tab "Biểu thức"; còn lại (2) một phần, (3), (4), vế xác định 1 cột):** (1) ~~không báo số dòng
      bị BỎ QUA~~ [ĐÃ LÀM cho Biểu thức: `expression_info`, riêng So sánh/Nếu–thì CŨ ở backend vẫn
      im lặng nhưng giao diện Denoise không còn dùng So sánh]; (2) Phụ thuộc hàm gắn cờ CẢ nhóm mâu thuẫn mà chỉ có xoá/giữ → xoá
      nhầm dòng đúng, nên thêm "sửa về giá trị phổ biến nhất"; (3) không có "bắt buộc có giá
      trị khi…" (ô trống luôn bị bỏ qua); (4) Nếu–thì chỉ 1 điều kiện mỗi vế, không VÀ/HOẶC;
      (5) ~~công thức chỉ số + − × ÷, không ngày/hàm/chữ, tên cột có dấu cách không gõ được~~ [ĐÃ LÀM: số/ngày/chữ, [tên có dấu cách], so/ngay/chu]; (6) ~~Phụ thuộc hàm chỉ 1 cột→1 cột~~ [ĐÃ LÀM: 1 cột xác định → nhiều cột phụ thuộc, nút "＋ Thêm cột phụ thuộc"; còn lại: vế xác định vẫn 1 cột, và vẫn gắn cờ CẢ nhóm mâu thuẫn]; (7) UI mỗi lần 1 rule [vẫn đúng]; ~~kiểu giá trị phải chọn tay~~ [ĐÃ LÀM: tự nhận Số/Ngày/Chữ theo dữ liệu].
      ~~Công thức chia cho 0 bị gắn cờ~~ [ĐÃ SỬA: chia cho 0 = chưa biết, được đếm riêng].
    - **Hướng đã thảo luận cho Rule liên cột — ĐỢT 1 ĐÃ LÀM (mục 24); ĐỢT 2 ĐÃ LÀM (mục 25: Nếu–thì chạy chung bộ máy, `=>`, `<=>`, `có(cột)`):** gộp thành NGÔN NGỮ
      BIỂU THỨC `Biểu thức` (số học + so sánh + `và/hoặc/không` + `=>` kéo theo + `<=>` tương
      đương + `có(cột)` + tên cột `[tên có dấu cách]`), tự viết bộ phân tích (Pratt parser, KHÔNG
      `eval`), đánh giá logic 3 giá trị (đúng/sai/chưa biết; chỉ gắn cờ khi chắc chắn sai),
      nhận cả ký hiệu lẫn chữ tiếng Việt. Nâng cấp tab "Công thức" thành "Biểu thức"; "So
      sánh"/"Nếu–thì" thành MẪU điền sẵn sinh ra biểu thức; Phụ thuộc hàm giữ riêng (xét theo
      nhóm dòng). Đợt 1 chưa có ngày/hàm (code So sánh/Nếu–thì cũ giữ lại vì còn lo ngày
      tháng tới đợt 2). Kèm 2 việc chung cho cả 4 kiểu: báo số dòng bỏ qua + tự điền kiểu
      giá trị theo kiểu cột đoán. Test cần: biểu thức cho kết quả y hệt So sánh/Nếu–thì/Công
      thức cũ, bảng chân trị 3 giá trị, thử nhét mã độc.
    - Gợi ý cải thiện 3 tool khác chưa làm: điền sẵn giá trị chuẩn gợi ý từ dữ liệu (Không
      nhất quán) và khoảng gợi ý (Ngoài khoảng); tick bỏ riêng từng dòng; chế độ "cả hai
      phương pháp cùng đồng ý" cho outlier; mục "cột khác" cho cột bị đoán nhầm kiểu; bỏ
      qua cột kiểu id khi tự chọn form đầu.
    - Giữ nguyên từ trước (mục "Kế hoạch" cuối file): TTL/auto-xoá dữ liệu RAM + giới hạn dung
      lượng upload (user: "làm sau"); hỗ trợ thêm TSV/ODS/Parquet (hiện CSV/Excel).

24. **Rule liên cột ĐỢT 1: tab "Biểu thức" gộp So sánh + Công thức — ĐÃ XONG, ĐÃ TEST (chưa commit lúc ghi):**
    - **Nguồn gốc:** user hỏi 3 rule còn lại (So sánh/Nếu–thì/Công thức) nên gộp ra sao → thống nhất:
      gộp So sánh + Công thức (Công thức ⊇ So sánh trên số; So sánh hơn ở ngày/chữ nên chỉ gộp khi bộ máy
      mới hiểu cả ngày/chữ), Nếu–thì để ĐỢT 2 (chạy chung bộ máy qua `=>`, giao diện vẫn là ô "nếu … thì …"),
      Phụ thuộc hàm giữ riêng (so GIỮA các dòng, 3 kiểu kia xét TỪNG dòng).
    - **Ngôn ngữ** (chi tiết ở docstring `expression_rules.py`): so sánh `< <= > >= = == != <>` (viết liền
      `0 <= tuoi <= 120` = hai phép so), `+ - * /`, `và/va/and/&&`, `hoặc/hoac/or/||`, `không/khong/not/!`,
      ngoặc, số, chữ `"..."`/`'...'` (nháy cong cũng được), cột `ten_cot` hoặc `[Tên có dấu cách]` (tên có
      dấu `.` viết trần được), 3 hàm ép kiểu `so()`, `ngay(x[, "%d/%m/%Y"])`, `chu()`. KHÔNG `eval`: hàm lạ,
      ký tự lạ, `=>` (để dành Nếu–thì) đều báo `ExpressionError`; đã chạy thử 3000 chuỗi rác ngẫu nhiên chỉ
      ra `ExpressionError`, và các ca nhét mã (`__import__('os')`, `a.__class__`, `open(...)`).
    - **Kiểu giá trị TỰ NHẬN theo dữ liệu** (`_Evaluator.infer`): Số nếu >= 90% ô đọc được và không phải
      mã có số 0 đứng đầu (007, SĐT -> Chữ); Ngày nếu >= 90% ô khớp 1 trong `DATE_FORMAT_CANDIDATES`
      (ISO, ISO+giờ kiểu Excel, dd/mm/yyyy ưu tiên hơn mm/dd khi hoà, dd-mm-yyyy, dd.mm.yyyy, yyyy/mm/dd);
      còn lại Chữ. Ngày chỉ so theo NGÀY (bỏ giờ). Ô trống/"N/A"/"?"... = thiếu (cả với kiểu Chữ -- KHÁC
      So sánh cũ, vốn coi ô trống kiểu Chữ là chuỗi rỗng). Hằng chữ tự đổi sang kiểu vế kia
      (`ngay_vao > "2024-01-31"`, `n == "5"`). Ngày - Ngày = số ngày; Ngày ± Số = Ngày. Sai kiểu (Chữ so với
      Số...) báo lỗi kèm gợi ý `so(cột)`/`ngay(cột)`.
    - **LOGIC 3 GIÁ TRỊ** (kiểu `boolean` nullable của pandas = bảng chân trị Kleene): ô thiếu/không đọc
      được/chia cho 0 -> "chưa biết", KHÔNG phải "sai". Chỉ gắn cờ khi CHẮC CHẮN sai (`sai và chưa biết` =
      sai -> vẫn gắn cờ; `đúng và chưa biết` = chưa biết -> bỏ qua). Chia cho 0 trước đây bị gắn cờ như
      vi phạm (lỗi của Công thức cũ), giờ là "chưa biết" và có đếm riêng (`zero_division_rows`).
    - **KHÔNG IM LẶNG KHI BỎ QUA DÒNG (lỗi cũ: sai khuôn ngày ra "0 lỗi"):** route trả `expression_info`
      {expression, total_rows, violating_rows, skipped_rows, zero_division_rows, columns:[{name, type,
      date_format, blank, unreadable, readable}], text_order_columns}. FE (`renderExprInfo`, khối
      `#cf-expr-info`) hiện: tóm tắt "N dòng · vi phạm · đạt · bỏ qua", "Cách đọc cột" (cột -> Số/Ngày/Chữ +
      khuôn dd/mm/yyyy), khung VÀNG số dòng bị bỏ qua + cột nào có bao nhiêu ô trống/không đọc được, khung ĐỎ
      khi một cột không đọc được ô nào (vd ép sai khuôn ngày) hoặc mọi dòng bị bỏ qua, cảnh báo khi cột Chữ
      bị so thứ tự (`< >`, nhiều khả năng là ngày/số bị nhận nhầm). 0 lỗi mà còn dòng bị bỏ qua thì trạng
      thái là "⚠ Không thấy dòng sai, nhưng K/N dòng chưa kiểm được" (KHÔNG báo ✅).
    - **Giao diện [ĐÃ ĐỔI Ở MỤC 28: bỏ mẫu so sánh hai cột, tab Nếu – thì gộp vào Biểu thức]:** `RULE_TYPES` = Biểu thức / Nếu – thì / Phụ thuộc hàm (đã bỏ nút So sánh, Công thức). Tab
      Biểu thức: ô nhập (textarea), nút chèn nhanh `và`/`hoặc`/`không`/`( )` và chip tên cột (bấm chèn tại
      con trỏ, `exprRef()` tự bọc `[ ]` khi tên có dấu cách/ký tự lạ/trùng từ khoá), mẫu "so sánh hai cột"
      (cột A, toán tử, cột B) chèn thành `A op B`, ô "Khuôn ngày" (trống = tự nhận) + "Sai số khi so bằng
      số" (mặc định 0.01, như Công thức cũ). `state.cf.ruleType` / `state.cf.expr` giữ kiểu rule và nội dung
      ô khi form dựng lại (đổi file, đổi kiểu rule) nên không phải gõ lại. Backend vẫn nhận compare/formula/
      conditional cho giao diện cũ (`index.html` dùng `/api/detect-noise`, đã kiểm tra cả 4 loại + expression).
    - **Kiểm chứng (số liệu để trích):** 2.580 phép đối chiếu với So sánh/Công thức cũ trên dữ liệu ngẫu nhiên
      (số, ngày ISO, chữ, 9 công thức; 6 phép so sánh; có ô trống/rác) = 0 khác biệt (so bằng dùng sai số 0 khi
      đối chiếu So sánh vì So sánh cũ so bằng chính xác); 124 kiểm tra lõi (cú pháp, ưu tiên, bảng chân trị 3
      giá trị, ngày/chữ/số, tên cột Unicode NFC/NFD, lỗi, fuzz); 100k dòng mỗi biểu thức < 0,3s (Công thức cũ
      lặp từng dòng ~1,4s); route đối chiếu với pandas độc lập trên `noisy_employee_dataset_large.csv`
      (`age >= 18 và age <= 65` -> 10 dòng vi phạm, 7 dòng bỏ qua); Playwright tab Biểu thức; lại chạy toàn bộ
      test Phụ thuộc hàm (backend + giao diện) vì dùng chung file.
    - **Giới hạn đã biết / chưa làm:** (`có(cột)`, `=>`, `<=>`, Nếu–thì nhiều điều kiện và cách xử lý mặc định ĐÃ LÀM
      ở mục 25); chữ so phân biệt hoa/thường (đã cắt khoảng trắng); `chu()`/`so()` không nhận định dạng số kiểu
      "1.000,5"; kiểm tra cú pháp khi đang gõ [ĐÃ LÀM ở mục 30].

25. **Rule liên cột ĐỢT 2: Nếu – thì chạy chung bộ máy biểu thức + mặc định "— Chọn cách xử lý —" — ĐÃ XONG, ĐÃ TEST (chưa commit lúc ghi):**
    - **Nguồn gốc:** user chốt đợt 2 sau đợt 1 ("OKe làm đi"). Gồm: `=>`, `<=>`, `có(cột)`, tab Nếu–thì làm lại, và đổi mặc định cách xử
      lý của các rule còn lại (việc đã ghi sẵn trong kế hoạch). 2 việc nhỏ ở mục 23 ("Cấu hình đã đổi", "Sẽ xoá N dòng" cho 3 tool khác)
      lúc đó chưa làm; user yêu cầu sau và đã làm ở mục 26.
    - **Ngôn ngữ thêm:** `a => b` (hoặc `a -> b`) = `không a hoặc b` theo logic 3 giá trị: CHỈ sai khi a đúng mà b sai; a sai thì luôn
      đạt; a hoặc b chưa biết mà chưa chắc sai thì "chưa biết" (bị bỏ qua + đếm). Kết hợp từ PHẢI sang trái, ưu tiên thấp hơn `hoặc`.
      `a <=> b` = `(a => b) và (b => a)`, thấp nhất. Gõ nhầm `age => 18` (muốn `>=`) báo lỗi kèm gợi ý "viết >=". `có(cột)` (hay
      `co(cột)`): Đúng nếu ô có giá trị, Sai nếu ô trống/"N/A"..., LUÔN biết chắc (không "chưa biết") nên bắt được "bắt buộc có giá trị khi…":
      `phong_ban == "Sales" => có(ma_khach)`. Chỉ nhận đúng 1 cột.
    - **Tab Nếu – thì (`RuleType.IF_THEN`) [ĐÃ BỎ KHỎI GIAO DIỆN Ở MỤC 28, backend giữ nguyên]:** 2 ô NẾU và THÌ, MỖI Ô LÀ 1 BIỂU THỨC ĐẦY ĐỦ (và/hoặc/không, so cột với cột — vế THÌ không còn
      bị giới hạn so với giá trị gõ tay —, tính toán, ngày, `có()`). Backend `evaluate_conditional()` tính từng vế bằng CÙNG 1 bộ đọc cột
      (cột dùng ở cả 2 vế chỉ đọc 1 lần), kết quả `~NẾU | THÌ`. Lỗi báo theo vế ("Vế NẾU: …" / "Vế THÌ: …") và vị trí ký tự tính theo RIÊNG
      vế đó (không tính trên chuỗi ghép). Nhãn cột để tô = hợp cột 2 vế (`if_then_columns()`). `expression_info` dùng chung với Biểu thức.
      Rule `conditional` cũ (if_column/then_column...) vẫn giữ cho giao diện cũ; đối chiếu với nó: 1.670 cấu hình ngẫu nhiên = 0 khác biệt.
    - **Giao diện [ĐÃ THAY Ở MỤC 28]:** khối chèn nhanh DÙNG CHUNG 2 tab (`exprHelperHTML`): nút `và`/`hoặc`/`không`/`( )`/`có( )` + chip cột chèn vào Ô ĐANG CHỌN
      (`state.cf.exprTarget`, theo `focusin`; dòng nhắc "Đang chèn vào ô NẾU/THÌ"). Mẫu "cột – toán tử – giá trị" có nút "Chèn vào NẾU/THÌ":
      `exprLiteral()` viết trần số cho cột số (`salary >= 10000000`), còn lại để trong nháy (`department == "Sales"`) -- bộ máy tự đổi chữ
      trong nháy sang kiểu vế kia nên nháy luôn an toàn. Nội dung 2 ô giữ khi đổi file/đổi tab (`state.cf.expr.ifText/thenText`).
    - **Mặc định cách xử lý (bài học mục 13) cho MỌI rule liên cột:** ô chọn luôn bắt đầu bằng "— Chọn cách xử lý —", Áp dụng khi chưa chọn thì
      báo lỗi, và có dòng xem trước dưới ô chọn ("Sẽ xoá N dòng vi phạm (a → b)"; Phụ thuộc hàm vẫn có kế hoạch riêng của nó).
    - **Kiểm chứng:** bảng chân trị `=>`/`<=>` với (Đúng/Sai/Chưa biết), kết hợp phải, ưu tiên, `có()`, 17 ca lỗi theo vế (125 + 34 kiểm tra
      lõi); route đối chiếu pandas độc lập trên `noisy_employee_dataset_large.csv` (NẾU department = Sales THÌ salary >= 10 triệu -> 6 dòng
      vi phạm, 2 bỏ qua; `department = Sales => có(phone)` -> 1 dòng); Playwright tab Nếu–thì (chèn đúng ô, mẫu, lỗi từng vế, giữ nội dung);
      chạy lại test Biểu thức đợt 1 + toàn bộ test Phụ thuộc hàm; đạt trên pandas 3.0 và 2.2.
    - **Chưa làm:** Nếu–thì không có chế độ "nhiều rule một lượt". (Kiểm tra cú pháp khi đang gõ: đã làm ở mục 30.)

26. **Cần cấu hình: báo "cấu hình đã đổi" + báo trước "Sẽ xoá N dòng" — ĐÃ XONG, ĐÃ TEST (chưa commit lúc ghi):**
    - **Nguồn gốc:** 2 việc nhỏ nợ từ mục 23, user bảo "làm hai việc nhỏ đó đi".
    - **Cấu hình đã đổi** (`workspace.js`: `cfSignature()`, `cfCheckStale()`, khối `#cf-stale-note`): nút Áp dụng luôn dùng
      cấu hình + bảng kết quả của lần Phát hiện cuối (`state.cf.detect`). Lúc Phát hiện lưu "chữ ký" = cấu hình đang khai
      (`buildCfConfig()`) + chữ ký đầu vào (`cfInputSource().sig`), tính TRƯỚC khi chờ server. Mọi `input`/`change`/`click` trong
      `#section-config` (hoãn `setTimeout 0` cho handler riêng chạy xong) và sau khi đọc lại cột (`cfInspect`) so lại: lệch thì hiện
      khung vàng "Bấm Phát hiện lại trước khi Áp dụng" và KHOÁ nút Áp dụng (chọn khoá thay vì chỉ báo, vì Áp dụng sẽ chạy cấu hình
      CŨ trên đầu vào có thể đã khác); sửa lại y như cũ thì hết báo. Áp dụng cho cả 3 tool theo cột lẫn Rule liên cột (cả 3 kiểu).
      Sau Phát hiện ra 0 lỗi mà `recordPipeStep` đổi đầu vào sang kết quả thì cập nhật lại chữ ký (không tính là "đã đổi").
    - **Sẽ xoá N dòng (a → b)** cho tool nhiều cột (`renderCfMultiPreview()`, `#cf-multi-preview`): backend
      `/api/noise-tools/configured` (detect) thêm `per_column[].flagged_row_numbers` (số dòng 1-based có ô lỗi ở cột đó; bỏ nếu quá
      `CONFIG_TOOL_ROW_LIST_LIMIT` = 300.000 dòng lỗi, khi đó FE nói "chưa tính trước được"). FE lấy HỢP các dòng của các cột đang
      chọn "Xoá dòng" (khớp cách backend xoá: dòng lỗi ở bất kỳ cột nào đó đều bị xoá, dòng lỗi ở 2 cột chỉ tính 1 lần), cập nhật mỗi
      lần đổi ô chọn cách xử lý, không gọi lại backend. Từ 20% số dòng trở lên thì tô đỏ + nhắc xem lại. Cách xử lý không xoá dòng
      thì không hiện gì. Rule liên cột đã có dòng xem trước riêng từ mục 25.
    - **Kiểm chứng:** Playwright `test_stale_ui.js` (sửa ngưỡng/thêm-xoá cột/sửa biểu thức → báo + khoá; sửa lại như cũ → hết báo;
      Phát hiện lại → hết báo; xem trước = số backend xoá thật; 3 cột nhân viên 10+2+11 → 23 dòng) + ca dòng lỗi ở CẢ 2 cột (2+2 → HỢP
      = 3, backend xoá đúng 3); chạy lại test IQR/Biểu thức/Nếu–thì/Phụ thuộc hàm (giao diện + backend) không hồi quy.
    - **Chưa làm:** xem trước cho cách sửa giá trị (chỉ báo khi xoá dòng). (Hộp xác nhận + hoàn tác: xem mục 27.)

27. **Cần cấu hình: hộp xác nhận xoá dòng + nút Hoàn tác ở dải nối tiếp — ĐÃ XONG, ĐÃ TEST (chưa commit lúc ghi):**
    - **Nguồn gốc:** user hỏi "hộp xác nhận là gì" (nợ ở mục 23/26) rồi bảo "Oke làm cái đấy đi". Đề xuất ban đầu của mình là có thể
      bỏ qua vì đã có dòng báo trước + mặc định "— Chọn cách xử lý —"; user vẫn chọn làm.
    - **Hộp xác nhận** (`workspace.js`: `cfSendApply()`, `cfFinishApply()`, `hideCfConfirm()`, khối `#cf-confirm`): bấm Áp dụng mà có XOÁ DÒNG
      (tool nhiều cột: có cột chọn `remove_row`; Rule liên cột: `remove_row` hoặc `remove_suspect_rows`) thì gửi `dry_run=true` trước.
      Backend (`/api/noise-tools/configured`, mode apply) chạy ĐÚNG đường tính như Áp dụng thật nhưng chỉ trả
      `{dry_run, rows_before, rows_after, rows_removed, cells_changed}` (không đóng gói CSV, route không giữ dữ liệu nên không để dấu vết).
      `rows_removed > 0` thì hiện hộp đỏ "Sẽ xoá N dòng (a → b). Bấm «Xác nhận» thì mới xoá thật." (kèm nhắc khi >= 20% số dòng, kèm "gồm cả
      các dòng có thể là đúng" cho Phụ thuộc hàm → Xoá cả dòng); chỉ khi bấm "Xác nhận xoá và áp dụng" mới gửi lệnh thật. Huỷ / đổi lựa chọn
      trong khối cách xử lý / Phát hiện lại / cấu hình đã đổi (stale) / đổi chuỗi nối tiếp → hộp tự ẩn. Cách chỉ sửa giá trị (điền, kéo về
      biên...) hoặc chạy thử báo 0 dòng bị xoá thì áp dụng thẳng, không hỏi (giống Bước 5 cũ).
    - **Hoàn tác** (nút `.pipe-undo-btn` "↶ Hoàn tác bước cuối" trong dải đen nối tiếp, có ở CẢ 3 nhóm vì chuỗi dùng chung): `state.pipe.undoStack`
      ghi snapshot {text, kind, steps} TRƯỚC mỗi bước mới (giữ tham chiếu chuỗi chữ, không copy; tối đa `PIPE_UNDO_MAX` = 5 bước gần nhất,
      khớp Bước 5 cũ). Bấm → lùi về snapshot cuối, dọn bảng kết quả (`resetResult`) và báo "↶ Đã hoàn tác «tên bước»". Bước ĐẦU TIÊN của
      chuỗi không có snapshot (trước nó là file gốc) nên hoàn tác bước đó = "về gốc" (`resetPipeToOriginal()`, tách ra từ nút "Bắt đầu lại từ
      gốc"). Hết snapshot mà còn > 1 bước thì nút ẩn (vẫn còn "Bắt đầu lại từ gốc"). Hoàn tác thuần phía trình duyệt, không gọi backend
      (trừ lúc về gốc). `state.cf.applyBusy` chặn hoàn tác/về gốc khi lệnh Áp dụng đang chạy dở (tránh đổi chuỗi giữa chừng).
    - **Giới hạn:** snapshot nằm trong RAM trình duyệt (mất khi tải lại trang, như cả chuỗi nối tiếp); không có "làm lại" (redo); hoàn tác
      áp dụng cho MỌI nhóm tool vì dùng chung chuỗi (không phải riêng Cần cấu hình).
    - **Kiểm chứng:** Playwright `test_confirm_undo_ui.js` (hộp hiện đúng số thật, Huỷ/đổi lựa chọn → ẩn, chạy thử KHÔNG ghi dấu vết
      (`pipe.active` vẫn false), Xác nhận → xoá thật, cách không xoá dòng → không hỏi, 3 bước nối tiếp rồi hoàn tác từng bước đúng số dòng
      313 → 311 → 311 → 303, hoàn tác bước đầu về gốc 313, làm lại sau hoàn tác); `test_pipe_other_groups.js` (Free Tools: xoá trùng +
      cắt khoảng trắng rồi hoàn tác từng bước, "Bắt đầu lại từ gốc" vẫn chạy, dải Convert có nút); các test cũ (`test_stale_ui`,
      `test_expr_ui`, `test_ifthen_ui`) phải bấm thêm "Xác nhận" khi Áp dụng có xoá dòng (hành vi mới, đã cập nhật test); IQR/Phụ thuộc hàm
      UI + backend không hồi quy.

28. **Rule Biểu thức dễ dùng hơn: bỏ 2 mẫu, gộp Nếu – thì vào Biểu thức, 3 hàng nút, chip giá trị — ĐÃ XONG, ĐÃ TEST (chưa commit lúc ghi):**
    - **Nguồn gốc:** user thấy tab Biểu thức "khó dùng quá" (ô trống to, không biết bắt đầu từ đâu, sợ gõ tay sai). Qua mấy lượt trao đổi chốt:
      (1) bỏ cả 2 "mẫu" vì chỉ là chèn chữ vào ô, gõ tay ra y hệt; (2) gộp tab Nếu – thì vào Biểu thức vì bản chất là toán tử `=>`
      (đối chiếu 480 cấu hình ngẫu nhiên, gõ có/không ngoặc: 0 khác biệt giữa `evaluate_conditional(A, B)` và `A => B`; `=>` có ưu tiên thấp
      nhất nên `A và B => C hoặc D` tự hiểu `(A và B) => (C hoặc D)`); (3) thêm nút cho dấu để khỏi gõ; (4) chip giá trị để khỏi gõ chữ.
    - **Giao diện** (`workspace.js`): `RULE_TYPES` chỉ còn Biểu thức / Phụ thuộc hàm; ô NẾU/THÌ, `state.cf.exprTarget`, `ifText/thenText`,
      `exprLiteral()`, `cfOperatorSelect()` và nhánh `if_then` của `buildCfConfig()` đã xoá. `EXPR_BUTTON_GROUPS` = 3 hàng nút (mỗi nút có `title`
      giải thích): (1) và · hoặc · không · ( ) · có( ) · **thì =>** (chèn `=>`), (2) < <= = != >= >, (3) + − × ÷ (chèn `-` `*` `/`) và `" "` (chèn
      cặp nháy, con trỏ nằm giữa; `insertIntoExpression` đặt con trỏ giữa cho `( )`, `có()`, `""`). KHÔNG có nút mũ `^` và phần trăm `%`:
      bộ máy không hỗ trợ (gõ vào báo lỗi), mũ hiếm dùng, `%` mơ hồ (10% hay chia dư) nên phần trăm viết `/ 100` (đã ghi trong dòng hướng dẫn).
      KHÔNG có nút `=>`/`<=>` riêng ngoài "thì =>" vì dễ nhầm với `>=`.
    - **Chip giá trị** (`renderCfValueChips()`, `state.cf.columnValues/valueCol`, khối `#cf-value-box`): bấm chip tên cột thì chèn tên cột và, nếu đó là
      cột Nhóm, hiện hàng "Giá trị trong cột «X»" gồm các giá trị kèm số dòng; bấm chip giá trị chèn `"giá trị"` có nháy (`exprString()` thêm `\` trước
      `\`, `"`, `“`, `”` vì bộ đọc coi cả 3 ký tự nháy là đóng chuỗi — kiểm bằng file có `5" pipe`, `C:\temp`, `He said “hi”`). Số đếm của chip =
      số dòng thật sự khớp khi viết `cột = "giá trị"` (đã đối chiếu, 0 lệch): `' HR'` gộp vào `HR`, ô thiếu (null/NA/?/None) không hiện, `hr`/`SALES`
      vẫn là giá trị riêng (so chữ PHÂN BIỆT hoa/thường: trên file nhân viên `department = "sales"` khớp 0 dòng, `"Sales"` khớp 59 dòng) nên chip
      còn giúp thấy các cách viết lệch. Chỉ cột được đoán là `category` (≤ 50 giá trị khác nhau và ≤ 50% số dòng) có chip; cột số/ngày/tên người thì ẩn.
      Backend: `/api/noise-tools/inspect` nhận `include_values` (FE `cfInspect` luôn gửi) → `column_values`, tối đa `INSPECT_VALUE_CHIP_LIMIT` = 30 giá trị
      phổ biến nhất mỗi cột + `more` = số giá trị còn lại; đoán kiểu cột 1 lần dùng cho cả 3 phần của response (trước đó đoán lặp 2 lần).
    - **Gợi ý thiếu nháy [ĐÃ THAY MỘT PHẦN Ở MỤC 29: chữ trần là giá trị thật của cột giờ chạy luôn]:** từ lạ KHÔNG đứng cạnh cột nào (vd `so(x) > abc`) vẫn báo
      "không có cột «X»... Nếu «X» là giá trị chữ chứ không phải tên cột, hãy viết trong dấu nháy" (không nhắc khi tên viết trong `[ ]`).
    - **Chữ hướng dẫn đã sửa** (trang chủ, menu, mục hướng dẫn "Cần cấu hình"): "Hai kiểu rule", nút THÌ =>, phần trăm viết /100, chữ phân biệt hoa/thường,
      hàm `có` trong danh sách hàm cho phép. [Phần chữ dài này đã được RÚT GỌN ở mục 31.]
    - **Kiểm chứng:** Playwright `test_expr_toolbar_ui.js` (2 tab, không còn mẫu/ô NẾU/THÌ, 3 hàng nút đúng nhãn + title, ghép bằng bấm ra `age >= 18 và
      age <= 65` = 10 dòng vi phạm, ký tự nút tính toán/so sánh, con trỏ giữa nháy và giữa `có()`, chip giá trị department 9 giá trị / gender 5 giá trị, ẩn ở
      cột số và cột tên, ghép `department = "Sales" => salary >= 10000000` bằng bấm = 6 dòng vi phạm khớp pandas độc lập, gợi ý nháy, 4 giá trị có ký tự đặc
      biệt khớp đúng số dòng); `test_expr_values.py` (hàm đếm + gợi ý nháy, đạt pandas 3.0.5 và 2.2.3); chạy lại toàn bộ test Biểu thức (lõi 125+34, route,
      2.580 đối chiếu = 0 khác biệt), Phụ thuộc hàm (lõi, hành động, nhiều cột, UI x3), IQR, báo cấu hình đã đổi, hộp xác nhận + hoàn tác, dải nối tiếp: không hồi quy.
      `test_ifthen_ui.js` (tab Nếu – thì) đã bỏ vì tab không còn; hai test UI cũ `test_expr_ui.js` / `test_stale_ui.js` phải sửa cho khớp (tab, mẫu).
    - **Giới hạn / chưa làm:** chip giá trị chỉ cho cột Nhóm (cột số nhiều giá trị ít như điểm 1–5 vẫn gõ số tay); không có "gợi ý điều kiện" dựng sẵn
      (đã đề xuất, user chưa yêu cầu); mũ `^` chưa có trong bộ máy. (Kiểm tra cú pháp khi đang gõ: mục 30.)

29. **Tự nhận chữ trần (không dấu nháy) là giá trị của cột đang so — ĐÃ XONG, ĐÃ TEST (chưa commit lúc ghi):**
    - **Nguồn gốc:** user mong "máy tự nhận số hay chữ", người dùng đỡ phải gõ nháy; sau khi mình giải thích hiện trạng (chữ trần bị hiểu là tên cột) và đề xuất
      "chỗ 1" thì user chốt "làm chỗ 1 đi". Chỗ 2 (kiểm tra cú pháp khi đang gõ, tự kiểm tra sau ~1s ngừng gõ) user yêu cầu sau ("làm chỗ hai đi") và đã làm ở mục 30.
    - **Luật** (`expression_rules.py::bind_bare_values`, chạy sau `parse_expression`, trước khi tính / liệt kê cột; trả CÂY MỚI, đổi nút `("col", từ, pos)` thành
      `("str", từ, pos)`): một từ được coi là chữ khi đồng thời (1) không phải tên cột nào (`_ColumnResolver.known()`, tên cột luôn thắng), (2) không viết trong
      `[ ]`, (3) đứng LIỀN KỀ một CỘT trong phép so sánh (`cmp`, kể cả chuỗi `a < b < c`, hai chiều `Sales = department`), (4) đúng là một giá trị thật của cột
      đó theo ĐÚNG phép so chữ (`_clean_text`: cắt khoảng trắng hai đầu, bỏ ô thiếu null/NA/?..., PHÂN BIỆT hoa/thường). Không thoả (4) thì KHÔNG đoán: báo lỗi
      "«Salse» cũng không phải giá trị nào của cột «department» (giá trị gần giống: «Sales»)" (gần giống = khác hoa/thường trước, rồi `difflib` cutoff 0.6, tối đa 3),
      và chỉ gợi ý tên cột khi giống rất sát (cutoff 0.75, `agee → age` có, `Salse → age` không). Lý do chọn "phải là giá trị thật" thay vì coi mọi từ lạ là chữ:
      gõ nhầm tên cột/giá trị sẽ không bị hiểu thầm thành chữ rồi gắn cờ CẢ FILE.
    - **Nối vào 4 nơi:** `evaluate_expression`, `evaluate_conditional` (lỗi ghi rõ "Vế NẾU/THÌ"), `expression_columns`, `if_then_columns` — nên `expression_info`, nhãn rule
      (`describe_rule(cfg, df)`) và ô tô màu không coi `Sales` là cột. Nhánh không có df (`expression_column_names`) không đổi.
    - **Giới hạn:** giá trị có dấu cách / ký tự đặc biệt / không có sẵn trong cột vẫn phải để trong nháy (hoặc bấm chip giá trị, luôn chèn kèm nháy đúng); chỉ cho
      phép so sánh có một vế là cột (không áp dụng trong `so(...)`, phép tính...); chữ vẫn phân biệt hoa/thường nên `department = sales` báo lỗi gợi ý «Sales», «SALES».
    - **Giao diện:** chỉ sửa chữ (dòng hướng dẫn dưới form, chú thích nút `" "`, mục giải thích "Cách viết biểu thức" [mục giải thích này đã bỏ ở mục 31]); chip giá trị vẫn chèn `"giá trị"` có nháy.
    - **Kiểm chứng:** `test_bare_values.py` (chữ trần = có nháy ở 8 cách viết, hai chiều, `!=`, `=>`, ' HR' có dấu cách, evaluate_conditional, expression_columns,
      if_then_columns, describe_rule; typo Salse / sales / agee / [Sales] / hai vế lạ / lỗi theo vế; tên cột thắng giá trị; giá trị có dấu cách vẫn cần nháy; đối chiếu ngẫu nhiên
      560 cấu hình `c = word` vs `c = "word"` = 0 khác biệt; đạt pandas 3.0.5 và 2.2.3); Playwright `test_expr_toolbar_ui.js` (gõ `department = Sales` = 253 dòng, nếu–thì gõ trần = 6 dòng,
      Salse / sales báo lỗi gợi ý); chạy lại toàn bộ test Biểu thức (lõi, route, 2.580 đối chiếu = 0 khác biệt), Phụ thuộc hàm, IQR, báo cấu hình đổi, xác nhận + hoàn tác: không hồi quy.

30. **Kiểm tra biểu thức khi đang gõ ("chỗ 2" của mục 29) — ĐÃ XONG, ĐÃ TEST (chưa commit lúc ghi):**
    - **Nguồn gốc:** mình từng đề xuất "báo lỗi ngay khi gõ, tự kiểm tra sau ~1 giây ngừng gõ" (user CHƯA yêu cầu lúc đó); sau đó user nhắn "làm chỗ hai đi, đang là làm gì đó t quên
      mất rồi" -> nhắc lại rồi làm.
    - **Backend** (`app.py::noise_tool_check_expression`, `POST /api/noise-tools/check-expression`, `@login_required`): form = `file`|`text` (như các route noise-tools khác) + `expression` +
      `date_format` + `tolerance` (trống = tự nhận / mặc định). Tính bằng ĐÚNG `evaluate_expression` của Phát hiện (nên lỗi nào Phát hiện báo thì ở đây cũng báo), NHƯNG không gắn cờ dòng nào,
      không đóng gói file, không giữ gì lại trên server (vẫn stateless). Biểu thức sai là trạng thái BÌNH THƯỜNG khi đang gõ dở nên trả HTTP 200 `{ok:false, error}`; thành công trả
      `{ok:true, columns:[{name,type,date_format}]}` (cách đọc từng cột); chỉ lỗi đọc file mới là 400. Sai số không phải số -> `ok:false`.
    - **Giao diện** (`workspace.js`: `scheduleLiveCheck()`, `runLiveCheck()`, `setLiveCheck()`; khối `#cf-live-check` dưới ô biểu thức; hằng `LIVE_CHECK_DELAY_MS` = 900,
      `LIVE_CHECK_MAX_BYTES` = 5MB): hẹn giờ ngừng-gõ rồi hiện 1 trong: xanh "✓ Biểu thức hợp lệ · cách đọc cột: age Số · join_date Ngày dd/mm/yyyy", đỏ "✗ <lỗi>", xám "Đang kiểm tra…"
      hoặc "Dữ liệu lớn nên không tự kiểm tra khi gõ: bấm «Phát hiện»". Kích hoạt khi: gõ, chèn bằng nút/chip/chip giá trị (`insertIntoExpression` không bắn sự kiện input nên tự gọi), đổi khuôn
      ngày / sai số, dựng lại form (đổi tab, đọc lại cột, đổi file). Mỗi lần gõ/chèn tăng `state.cf.liveSeq` nên kết quả về muộn của lần cũ bị bỏ; kết quả cũ bị làm mờ (`is-stale`) khi đang gõ tiếp;
      ô trống thì ẩn dòng; chưa có file thì không gọi. KHÔNG chặn nút Phát hiện. Đầu vào > 5MB không tự kiểm tra (mỗi lần kiểm tra phải gửi lại cả dữ liệu vì route stateless).
    - **Nhân tiện:** gõ ngày trần (`join_date > 2020-01-01`) bị hiểu là phép trừ nên báo "không so sánh được Ngày với Số" mà không nói cách sửa; đã thêm gợi ý "ngày viết trong dấu nháy, vd
      "2024-01-31"" (chỉ khi vế Số không phải 1 cột nguyên, nên `salary > join_date` không bị nhắc nhầm).
    - **Kiểm chứng:** `test_check_route.py` (Flask test client: 401 chưa đăng nhập, ok + cách đọc cột, chữ trần, số + chữ, gõ nhầm giá trị, dở dang, sai tên cột, sai số, khuôn ngày thiếu %, ô trống,
      400 thiếu dữ liệu, dán text, nhất quán với Phát hiện); Playwright `test_live_check_ui.js` (không file/ô trống không báo, xanh kèm cách đọc, gõ 23 ký tự liên tục chỉ 1 lần gọi máy chủ,
      mờ khi gõ tiếp, 4 loại lỗi đỏ, chèn bằng chip/nút/chip giá trị, đổi khuôn ngày gọi lại 1 lần, xoá ô ẩn dòng, đổi tab rồi quay lại kiểm tra lại, kết quả cũ về muộn không đè kết quả mới
      (giả lập chậm 2,6s), Phát hiện vẫn ra 10 dòng, file 6,5MB chỉ hiện lời nhắc và không gọi máy chủ); chạy lại toàn bộ test Biểu thức (lõi, route, 2.580 đối chiếu), Phụ thuộc hàm, IQR,
      báo cấu hình đã đổi, hộp xác nhận + hoàn tác, dải nối tiếp: không hồi quy.
    - **Giới hạn:** mỗi lần kiểm tra đọc lại toàn bộ dữ liệu (≤ 5MB); chỉ cho tab Biểu thức (Phụ thuộc hàm không có ô gõ); lỗi hiện dưới ô, chưa tô vị trí ký tự sai trong ô.

31. **Rút gọn chữ chú thích trên MỌI trang Denoise — ĐÃ XONG, ĐÃ TEST (chưa commit lúc ghi):**
    - **Nguồn gốc:** user gửi 5 ảnh chụp (trang chủ, các thẻ "Denoise sửa được gì", "Cách hoạt động" + khối giải thích của Free Tools và Ngoài khoảng, "Về dự án") và nói chú thích chữ bé
      quá nhiều, nhìn như AI viết; muốn ít hơn, đơn giản hơn, ngắn gọn xúc tích, kiểm tra TẤT CẢ trang, còn bố cục giữ nguyên.
    - **Quy ước đã áp dụng (giữ cho nhất quán khi thêm chữ mới):** (1) mỗi chú thích ngắn, một câu, thường ≤ ~100 ký tự; (2) mỗi tool chỉ 2–3 khối giải thích (trước 3–5), mỗi khối 1–2 câu;
      bỏ khối "Riêng tư theo thiết kế" lặp ở mọi tool (xoá hàm `PRIVACY_COLUMN`, thông tin này đã có ở trang Quyền riêng tư) và khối "Cách viết biểu thức" dài của rule liên cột (nút bấm có `title`,
      dòng xanh/đỏ kiểm tra khi gõ và thông báo lỗi đã đủ hướng dẫn); (3) "Cách hoạt động": 3 bước, mỗi bước một câu ngắn; (4) bỏ chữ thừa: `ft-section-meta` ("Ba bước · không cần cài gì"...),
      dòng nhỏ dưới các con số (`hm-number small`), `hint-note` lặp đúng chữ của nhãn (vd "Bỏ qua hoa/thường" + '"An" và "AN" tính là trùng'); (5) Guide / Bảo mật / Quyền riêng tư giữ nguyên
      mục lục và số mục, chỉ cô đọng thân mỗi mục (Guide "đọc trong ≈ 3 phút" thay vì 8); (6) chữ ĐỘNG (thông báo lỗi, cảnh báo, xem trước "Sẽ xoá N dòng") giữ nguyên ý, chỉ cắt câu thừa, và
      GIỮ NGUYÊN các câu test đang kiểm (`Bỏ qua N/M dòng vì chưa tính được`, `chưa chắc là dữ liệu sạch`, `phân biệt hoa/thường` ở tiêu đề chip giá trị, `Sẽ xoá N dòng (a → b dòng)`...).
    - **Không đổi:** bố cục / CSS (khối giải thích vẫn lưới 3 cột: tool chỉ có 2 khối thì cột thứ 3 để trống, thẳng hàng với 3 bước phía trên), logic, backend, id / class.
    - **Chỗ sửa:** `workspace.html` (đăng nhập, menu, trang chủ, 3 trang chữ, hồ sơ, form 3 nhóm tool, Class Noise), `workspace.js` (`TOOL_INFO` / `CV_INFO` / `CF_INFO` chỉ đổi `desc` / `steps` /
      `explainer`; hint-note, ghi chú dưới bảng, chữ "chọn file trước", cảnh báo IQR = 0, ghi chú Điền tay từng ô...), `workspace-flow.js` (3 cảnh báo Class Noise, thông báo backend, tóm tắt giảm cột).
      Giao diện CŨ (`index.html`, `script.js`, `style.css`...) không đụng tới.
    - **Kiểm chứng:** script quét mọi trang (bấm từng tab của 3 nhóm tool, liệt kê đoạn chữ dài; sau khi sửa chỉ còn vài đoạn ~100 ký tự) + chụp full-page xem tay trang chủ, 3 trang chữ, hồ sơ,
      Class Noise, các tab tool: không vỡ bố cục, không lỗi JS; chạy lại 10 test giao diện (Biểu thức, thanh nút + chip, kiểm tra khi gõ, Phụ thuộc hàm x3, báo cấu hình đã đổi, hộp xác nhận + hoàn tác,
      IQR, dải nối tiếp): PASS. Lỗi tìm ra khi chạy test: tiêu đề chip giá trị lỡ mất chữ "phân biệt hoa/thường" (thông tin thật) -> đã trả lại.
    - **Chưa sửa:** nhánh Attribute 5 bước ẩn trong khối Class Noise (`#panel-3-attribute`, `#panel-5-attribute`...) vẫn còn đoạn mô tả dài nhưng không bao giờ hiển thị trong Denoise.

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
- [x] Class noise — thuật toán DETECT thứ 2 (mục 10): Distance-based (N13,
      Mutual k-NN) `class_noise/distance_based.py` + khung chọn 1-trong-3
      phương pháp ở Bước 2 FE + backend `/api/class-noise/detect` dispatch
      theo `method`. Đã test qua Playwright (cả 2 luồng Distance-based và
      Single learning-based, không hồi quy). Đã viết script đánh giá so
      sánh thực nghiệm (`evaluate_distance_vs_confident.py`) trên Adult
      Income — N13 thắng Confident Learning về F1 (xem chi tiết mục 10).
- [x] Ensemble-based (N29) — nhóm thứ 3 trong Bảng 6: `class_noise/ensemble_based.py`
      (LogisticRegression + GaussianNB + LinearSVC biểu quyết) + nối vào web
      (Bước 2/3/4) + `evaluate_ensemble_vs_others.py` so sánh đủ cả 3 thuật
      toán. CẢ 3 phương pháp giờ đều bấm được trên UI (xem mục 11). N29
      thắng cả Precision/Recall ở mức nhiễu 30% trên Adult Income.
- [x] Bước 5 AN TOÀN (mục 13): mặc định "— Chọn cách xử lý —", xem trước tác động (`dry_run`) +
      hộp xác nhận khi xoá, lịch sử + Hoàn tác (5 bước) + Về dữ liệu gốc, khoá chạy chồng, sửa 13 lỗi do
      workflow kiểm chứng tìm ra. Đã test bằng Playwright thật (11 kịch bản tái hiện lỗi + hồi quy).
- [x] Tài khoản đăng nhập — Multi-User THẬT (mục 14): `accounts/` (SQLite + hash mật khẩu) + 5 route
      `/api/auth/*` + kiểm tra quyền sở hữu (`_require_file_owner`/`_require_download_owner`) ở toàn bộ
      9 route cũ dùng `file_id`/`download_id` + `#panel-auth`/`#panel-profile` (bố cục chia đôi màn hình,
      giữ màu SPARK). Flask tự phục vụ frontend (cùng origin cho cookie session). Đã test 43 Flask test
      client + 23 Playwright (không hồi quy luồng Attribute Noise 5 bước cũ).
- [x] Convert File (mục 15): `converters/transform.py` (đổi delimiter CSV, CSV⇄JSON, thuần `csv`/`json`
      chuẩn không dùng pandas) + 3 route `/api/convert/*` (`@login_required`) + trang riêng
      `convert.html`/`convert.js` (bố cục 2 cột kiểu tham khảo, màu SPARK, gộp cả 3 tool 1 trang). Đã test
      29 test độc lập + 23 Flask test client + 16 Playwright.
- [x] Trang giới thiệu (mục 16): `landing.html`/`landing.js` thành "mặt tiền" công khai mới tại `/`
      (không bắt đăng nhập) — hero, ticker 9 loại noise, lưới 9 tính năng, demo tĩnh, quy trình xử lý
      file 3 bước. `index.html` (app thật) lùi về `/index.html`. Nhân tiện fix 1 lỗi CSS (`.btn` trên
      `<a>` bị gạch chân mặc định trình duyệt). Đã test 6 kịch bản Playwright mới + 39 kịch bản cũ không
      hồi quy (sau khi cập nhật route trong chính script test).
- [x] Free Tools (mục 17): `attribute_noise/quick_tools.py` (4 hàm, tái dùng logic có sẵn trong
      `attribute_handling.py`, không qua `apply_handling()` đầy đủ) + 4 route `/api/noise-tools/*`
      (`@login_required`, stateless giống Convert File) + trang riêng `tools.html`/`tools.js` (bố cục
      y hệt `convert.html`) + link header "🧹 Free Tools". Gộp 11 loại attribute noise thành 4 "không
      cần cấu hình" (xoá dòng trùng/cắt khoảng trắng/điền-xoá ô trống đơn giản/xoá dòng trống hoàn
      toàn — loại cuối HOÀN TOÀN MỚI) vs 7+Class Noise vẫn ở Workspace (cần khai dtype/tham số/nhãn).
      Đã test 23 test độc lập + 26 Flask test client + 18 Playwright, không hồi quy bộ test cũ.
- [x] Giao diện Denoise (mục 18): `workspace.html/.css/.js` + `workspace-flow.js`, `GET /` trỏ
      thẳng vào đó; 3 nhóm tool nối tiếp được với nhau; đã test Playwright nhiều bộ.
- [x] Tool "Ô trống" gộp + "Điền tay từng ô" (mục 19); Sai định dạng chuyển sang Free Tools.
- [x] 3 tool Cần cấu hình kiểm nhiều cột (Không nhất quán, Ngoài khoảng, Giá trị bất thường)
      + nhiều phương pháp IQR/Z-score trên 1 cột (mục 20-21). Commit `ce458b1`, `d59faf0`, `e02f5de`.
- [x] Chỉnh giao diện: tiêu đề chữ hoa line-height 1.2, bỏ ghi chú hero, chân trang to hơn (mục 22).
- [x] Cảnh báo IQR=0 ở tool Giá trị bất thường (mục 23, đã làm).
- [x] 2 việc nhỏ cùng đợt: báo "Cấu hình đã đổi, bấm Phát hiện lại" (khoá Áp dụng) + báo "Sẽ xoá N dòng
      (a → b)" trước khi Áp dụng ở tool nhiều cột — xem mục 26.
- [x] Hộp xác nhận xoá dòng (chạy thử `dry_run`) + nút Hoàn tác 5 bước ở dải nối tiếp (3 nhóm tool) — xem mục 27.
- [x] Biểu thức dễ dùng hơn: bỏ 2 mẫu, gộp Nếu – thì vào Biểu thức (nút THÌ =>), 3 hàng nút dấu, chip giá trị cột Nhóm — xem mục 28.
- [x] Tự nhận chữ trần (không nháy) là giá trị thật của cột đang so; gõ nhầm thì báo lỗi kèm giá trị gần giống — xem mục 29.
- [x] Kiểm tra biểu thức khi đang gõ (dòng xanh/đỏ dưới ô, ngừng gõ ~1s) — xem mục 30.
- [x] Rút gọn chữ chú thích trên mọi trang Denoise (ít hơn, ngắn hơn, bỏ khối "Riêng tư" lặp ở mỗi tool) — xem mục 31.
- [x] Phụ thuộc hàm: 1 cột xác định → nhiều cột phụ thuộc, đoán ô sai (so các cột còn lại), 2 cách xử lý
      "Sửa về giá trị phổ biến nhất" / "Chỉ xoá dòng nghi sai" + xem trước (mục 23, commit `3ee977f`, `73978bc`).
- [x] Rule liên cột ĐỢT 1: tab "Biểu thức" thay So sánh + Công thức (mục 24).
- [x] Rule liên cột ĐỢT 2: Nếu–thì chạy chung bộ máy biểu thức (2 ô NẾU/THÌ đầy đủ), `=>`, `<=>`, `có(cột)`, mặc định
      "— Chọn cách xử lý —" + xem trước cho mọi rule liên cột (mục 25).
- [ ] Cập nhật lại file này mỗi khi làm xong 1 cụm việc lớn (lần này ghi bù mục 18-23 sau khi
      thấy file thiếu Denoise).
- [ ] `evaluate_distance_vs_confident_creditcard.py` chưa chạy xong (quá
      chậm trên 284.807 dòng, đã huỷ giữa chừng) — cần chạy lại với
      n_estimators thấp hơn hoặc lấy mẫu con nếu muốn có số liệu so sánh
      N13 vs Confident Learning trên bộ đặc trưng MẠNH hơn Adult Income.
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
  mở `http://localhost:5000/` bằng trình duyệt (**MỚI, mục 14**: KHÔNG còn
  mở trực tiếp file `frontend/index.html` nữa — từ khi có tài khoản đăng
  nhập, Flask tự phục vụ luôn frontend để cookie session hoạt động đúng,
  mở theo kiểu `file://` cũ sẽ báo "chưa kết nối backend" dù server vẫn
  chạy bình thường). **ĐÃ ĐỔI (mục 18)**: `http://localhost:5000/` giờ ra
  thẳng giao diện **Denoise** (`workspace.html`): trang chủ công khai, các tool
  cần đăng nhập (chưa đăng nhập thì form đăng nhập tự hiện). Giao diện cũ vẫn mở
  được: `http://localhost:5000/index.html` (app 5 bước cũ) và `/landing.html`.
  Backend cần chạy ở 1 terminal riêng, để yên không gõ lệnh khác vào đó.
- Test tự động KHÔNG nằm trong repo (viết ở thư mục tạm mỗi phiên, mất khi máy ảo dựng lại).
  Muốn chạy lại cần viết lại; các con số đã kiểm chứng ghi ở từng mục trên.

## Ghi chú giao tiếp

- User CHƯA từng học frontend/backend — khi giải thích khái niệm mới, cần
  nói rõ nguyên lý (client-server, request/response, API...), không giả định
  đã biết.
- User yêu cầu code phải có chú thích (comment) giải thích rõ, không viết
  code trần trụi không comment (khác quy ước comment tối giản mặc định).
- Giao tiếp bằng tiếng Việt.
