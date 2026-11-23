# Web app Dò & Xử Lý Nhiễu Dữ Liệu

Web app phát hiện và xử lý noise trong dataset do người dùng upload (CSV/Excel).
Luồng: upload file → chọn "Attribute noise" hoặc "Class noise" → (Attribute) chọn
từng cột + loại noise áp dụng cho cột đó / (Class) chọn cột nhãn + đặc trưng →
hệ thống detect → người dùng xem kết quả (Attribute: xử lý replace/remove từng
ô/dòng lỗi rồi xuất file; Class: xem danh sách dòng nghi ngờ sai nhãn rồi xử lý
từng dòng/hàng loạt: giữ / xoá / sửa nhãn, chạy thử + xác nhận + hoàn tác + xuất file — mục 37).

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
    `feature_columns`, `n_estimators=300`, `cv_folds=5`, `random_state=42`, + **mục 3**:
    `min_samples_leaf=5`, `balanced=False` — chỉ Confident Learning dùng, xem bullet bên dưới).
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
  - **CẢI TIẾN `confident_learning.py` (22/11/2026, kế hoạch mục 3)**: (1) Random Forest có `min_samples_leaf` (mặc định 5) và
    `balanced` (mặc định **False**, trước đây luôn bật `class_weight="balanced"`); (2) vector hoá 2 vòng lặp từng dòng (kết quả giống
    hệt bản cũ, đã đối chiếu); (3) `diagnostics` thêm `excess_over_baseline` (mức vượt mốc), `mcc`, `pr_auc_per_class`/`pr_auc_macro`,
    `estimated_noise_rate`, `estimated_label_errors`, `calibrated_joint` (Q̂), `params`, `warnings`; (4) `result.scores` (`ClassNoiseScores`)
    cho MỌI dòng: `suspicion` = 1 − P(nhãn ghi), `suggested_labels` (nhãn khác nhãn ghi có xác suất cao nhất), `confident_labels`;
    (5) **ước lượng tỷ lệ nhãn sai** bằng hiệu chỉnh ma trận đếm đúng theo Northcutt 2021 (`_calibrated_joint()`: kéo mỗi hàng về số dòng
    mang nhãn ghi đó rồi chia tổng; tỷ lệ = 1 − trace(Q̂)); (6) docstring "dòng thật sự thuộc lớp" → "dòng mang nhãn lớp"; chỉ 1 lớp → ValueError.
    `app.py` (route single_learning) vẫn đọc các trường cũ, chưa trả các trường mới ra JSON (việc của mục 6).
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
    **CẢI TIẾN (22/11/2026, kế hoạch mục 2) — viết lại bằng numpy, mặc định cho ra ĐÚNG kết quả bản cũ:**
    `detect_class_noise_distance(df, config, k=5 | "auto", disagreement_threshold=0.5, *, metric="euclidean"|"manhattan",
    weighting="count"|"distance", pca=False|"auto"|True, keep_binary=True, coverage_target=0.9, k_candidates=K_CANDIDATES)`.
    (1) **Cột nhị phân** (đúng 2 giá trị) KHÔNG z-score mà đưa về 0/1 (`_scale_features`): z-score làm cột nhị phân lệch (vd giá trị
    hiếm thành ~9,95) nên át cột số; kết quả không phụ thuộc cách mã hoá (0/1 hay 5/9). (2) **Điểm cho MỌI dòng**: `result.scores`
    (`DistanceNoiseScores`: `row_numbers`, `disagreement` (NaN = không có láng giềng lẫn nhau), `n_mutual`, `suggested_labels`) —
    `findings` chỉ là các dòng điểm > ngưỡng; để so các ngưỡng 0,5/0,8/1,0 không phải chạy lại. (3) **`k="auto"`**: tìm láng giềng 1 lần
    với k lớn nhất (15), lấy k NHỎ NHẤT trong {3,5,7,9,11,15} có độ phủ >= `coverage_target` (không k nào đạt → lấy k lớn nhất + cảnh báo);
    chẩn đoán có `k_mode`, `coverage`, `coverage_by_k`, `warnings`. Số nguyên vẫn đặt tay được. (4) Biến thể: `weighting="distance"`
    (phiếu = 1/(d + eps), eps = 0,1 × trung vị khoảng cách dương trên các cạnh lẫn nhau), `metric="manhattan"`, `pca` (95% biến thiên;
    `"auto"` chỉ bật khi số thành phần < 1/2 số cột). Chẩn đoán ghi `metric`, `weighting`, `binary_columns`, `pca`. (5) **Sửa lỗi cũ**: nhãn
    gợi ý trước đây đếm phiếu trên TẤT CẢ láng giềng nên nhiều lớp có thể ra nhãn gợi ý TRÙNG nhãn ghi (11 dòng trên Car 5%); nay chỉ bỏ
    phiếu giữa các nhãn KHÁC nhãn ghi, hoà phiếu → nhãn nhỏ nhất (lặp lại được). (6) Tìm láng giềng loại chính nó theo CHỈ SỐ (không
    theo "cột đầu") nên đúng cả khi có điểm trùng hệt. `app.py`, `run_class_noise.py`, các script `evaluate_*` vẫn gọi `k=<số>` như cũ.
    `run_class_noise.py` thêm `--k auto`, `--metric`, `--weighting`, `--pca`.
  - **CẢI TIẾN `ensemble_based.py` (22/11/2026, kế hoạch mục 4)**: thêm `result.scores` (`EnsembleNoiseScores`: `disagreement` cho MỌI dòng, chỉ
    nhận 0/⅓/⅔/1 nên rất nhiều dòng hoà điểm; `suggested_labels`), `diagnostics.per_classifier_excess` + `best_excess_over_baseline`
    (mức vượt mốc từng classifier và của classifier tốt nhất), vector hoá vòng lặp. **Sửa lỗi cũ**: nhãn gợi ý đếm phiếu cả phiếu trùng
    nhãn ghi nên nhiều lớp có thể ra gợi ý TRÙNG nhãn ghi (cùng lỗi đã sửa ở Distance); nay chỉ bỏ phiếu giữa nhãn khác nhãn ghi, hoà → nhãn
    có chỉ số nhỏ nhất. Tập dòng gắn cờ và `disagree_ratio` KHÔNG đổi (32 kiểm tra đạt, giống bản cũ từng dòng).
  - `combined.py` — **MỚI (22/11/2026, kế hoạch mục 4) — PHƯƠNG PHÁP KẾT HỢP, đóng góp riêng của đề tài**: gộp 3 phương pháp thành 1 danh sách.
    (1) mỗi phương pháp đổi điểm sang HẠNG PHẦN TRĂM (hoà → hạng trung bình); (2) CỔNG CHẤT LƯỢNG: Confident Learning và Ensemble bị loại
    nếu mức vượt mốc <= 0 (Ensemble lấy của classifier tốt nhất), Mutual k-NN luôn có mặt (không có mô hình để đo); (3) trọng số theo tham số
    `alpha`: `w = (1−α)·(1/số phương pháp bật) + α·(q/Σq)` (k-NN lấy q = trung bình q các phương pháp còn lại) — **α = 0 là bản "công tắc"**,
    α > 0 là bản "pha trộn"; (4) điểm kết hợp = trung bình có trọng số các hạng, chỉ tính phương pháp CÓ ý kiến về dòng đó; (5) **K = số dòng
    phương pháp có trọng số LỚN NHẤT tự gắn cờ** (hoà trọng số → thứ tự cố định single, distance, ensemble), trả K dòng điểm cao nhất kèm
    `supporters` (phương pháp cùng gắn cờ), `ranks` từng phương pháp, nhãn gợi ý bỏ phiếu có trọng số, `diagnostics.methods` (trọng số, bật/tắt + lý do).
    API: `MethodOutput`, `from_single/from_distance/from_ensemble`, `combine_methods(outputs, alpha, recorded_labels)` (gộp từ điểm đã lưu,
    không chạy lại), `detect_class_noise_combined(df, config, alpha, k_neighbors, prepare_features)` (chạy cả 3 rồi gộp; `prepare_features`
    = cap + log chỉ cho Distance và Ensemble). **Cách hiểu "công tắc / pha trộn" là của mình (kế hoạch chỉ ghi 1 dòng) — đối chiếu lại với thầy.**
    α KHÔNG chọn ở đây (việc của mục 5: chọn trên 1 seed rồi giữ cố định). Đã nối vào web ở mục 45.
    **[CẬP NHẬT 23/11/2026, mục 48]** trên web bộ kết hợp CHỈ gộp Confident Learning + Mutual k-NN: `detect_class_noise_combined(..., methods=DEFAULT_METHODS)` với
    `DEFAULT_METHODS = ("single_learning", "distance_based")` (nhận cả tên gọi tắt "single" / "distance" / "ensemble", `normalize_methods()` kiểm + xếp theo `METHOD_ORDER`);
    Ensemble KHÔNG chạy nếu không chọn nhưng vẫn gộp được (dùng cho thực nghiệm). Phần "gộp điểm + chọn K" tách riêng thành `merge_scores_and_select_k()` (công thức + luật K
    KHÔNG đổi, chờ thực nghiệm; đối chiếu bản cũ trên 600 cấu hình ngẫu nhiên = từng trường giống hệt). Thêm `MethodFinding` + `method_findings(output, recorded)` (dòng MÀ CHÍNH 1 phương pháp tự gắn cờ, xếp
    theo điểm nghi của nó), và `CombinedResult.method_outputs` / `.recorded_labels`.
    **THỰC NGHIỆM ĐẦY ĐỦ (mục 5) KHÔNG ỦNG HỘ bộ kết hợp:** thua đối chứng `naive_cv`, không hơn cách chỉ cắt top-K theo điểm của Confident Learning, α gần như vô nghĩa; xem mục 5 trước khi trích dẫn.
  - `ensemble_diverse.py` — **MỚI (22/11/2026, kế hoạch mục 7) — ENSEMBLE 5 HỌ**, làm lại `ensemble_based.py` (bản cũ GIỮ NGUYÊN làm đối chứng):
    `detect_class_noise_ensemble_diverse(df, config, cv_folds=5, random_state=42, min_votes=3, balance_thresholds=True)` -> `EnsembleDiverseResult(findings, diagnostics, scores)`.
    (1) 5 họ đều có `predict_proba`: LogisticRegression, GaussianNB, KNeighbors (k=15), MLP (1 lớp 64, early stopping), HistGradientBoosting
    (`make_classifiers()`); KNeighbors cùng "họ láng giềng" với Mutual k-NN, HistGradientBoosting cùng "họ cây" với Random Forest — mục 11 từng LOẠI 2 họ này vì sợ trùng
    góc nhìn, kế hoạch mục 7 đưa lại nên có `pairwise_agreement` để đo trùng thật. (2) BỎ `class_weight="balanced"` và bỏ ép tiên nghiệm đều của GaussianNB.
    (3) CÂN HAI LOẠI LỖI bằng ngưỡng (`balanced_predictions()`): 2 lớp -> chọn ngưỡng cho TỪNG mô hình để tỉ lệ dương giả = tỉ lệ âm giả (điểm EER trên ROC, xác suất out-of-fold so với
    nhãn ghi, lớp hiếm là "dương"); nhiều lớp -> argmax p(c)/tần suất(c). **CHƯA đọc bài Khoshgoftaar 2005**: đây là cách hiểu "cân 2 loại lỗi" của dự án, chưa kiểm là đúng từng chi tiết.
    (4) `min_votes` 3/5, 4/5, 5/5 (số mô hình phản đối nhãn ghi để gắn cờ). Điểm cho MỌI dòng: `scores.suspicion` = trung bình 5 mô hình của (1 − P(nhãn ghi)) (bỏ phiếu mềm, liên tục, dùng xếp
    hạng) + `scores.votes` (phiếu cứng 0..5) + `suggested_labels`. Chẩn đoán: accuracy / mức vượt mốc từng mô hình (argmax THUẦN, không qua ngưỡng cân bằng để so được với baseline), `best_excess_over_baseline`,
    `thresholds`, `pairwise_agreement` (ma trận 5×5 tỉ lệ dự đoán giống nhau) + `mean_pairwise_agreement`, `vote_distribution`. 37 kiểm tra đơn vị đạt (ngưỡng EER dò tay, luật p/prior,
    tập cờ 5/5 ⊆ 4/5 ⊆ 3/5, ma trận đa dạng khớp tính tay...). `combined.py::from_ensemble_diverse()` nối vào bộ kết hợp (thay đúng chỗ Ensemble cũ).
    **Chạy chậm hơn Ensemble cũ** (có MLP, KNN, HistGradientBoosting); chưa nối vào `app.py`/giao diện.
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
  - `web_adapter.py` — **MỚI (mục 45)**: hàm phụ cho route Class Noise của web (`expand_findings`, `quality_assessment` theo MỨC VƯỢT MỐC, `preprocess_info`, `string_frame`, `finite`; mục 48 thêm
    `method_list_json()` = danh sách riêng 1 phương pháp ở dạng JSON đã mở ra cả nhóm dòng trùng, và `COMPONENT_LABELS`); thuần Python, không phụ thuộc Flask.
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
  - `preprocess.py` — **MỚI (22/11/2026, kế hoạch mục 1)**: pipeline chuẩn bị chung, KHÔNG dùng nhãn để chọn cột:
    `prepare_for_class_noise(df, PreprocessConfig)` -> `PreparedData` (df chỉ gồm nhãn + cột số, giữ index gốc; `groups`
    nhóm dòng trùng; `expand_row_numbers()` trả kết quả về cả nhóm) + `PreprocessReport.to_dict()` (cột bị bỏ kèm lý do,
    dòng bị loại, lớp ít dòng, nhóm mâu thuẫn, cảnh báo). Chưa nối vào `app.py`.
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
  - `POST /api/class-noise/detect` — **[CẬP NHẬT mục 48: giao diện Denoise CHỈ còn gọi `method="combined"` (Confident Learning + Mutual k-NN), không gửi k / alpha / n_estimators /
    cv_folds, `reduce_columns=false`; backend dùng mặc định k = 5, alpha = 0, n_estimators = 100, cv_folds = 5. Các method khác + `reduce_columns` + `k` / `alpha` vẫn được route nhận.]**
    **Hướng Class noise (mục 10+11):
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
    vì người dùng tick tay feature chữ được, đã fix bổ sung). Chạy
    `cap_outliers()` + `log_transform()` (Bước 3, xem `feature_selection.py`)
    lên `feature_columns` TRƯỚC khi chạy — **[ĐỔI 22/11/2026, mục 3] CHỈ cho `distance_based` và `ensemble_based`; `single_learning`
    dùng giá trị NGUYÊN** (cây quyết định: log là phép đơn điệu nên không đổi gì, cap có thể xoá tín hiệu ở giá trị cực đoan; đã đo
    raw/cap/cap+log trên Car, Adult, Credit Card, 3 seed: chênh trong vòng dao động giữa các seed). Câu mô tả ở `workspace.html`
    (`#panel-3-class-desc`) đã sửa cho khớp.
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
    Denoise chỉ nhánh **Class Noise 4 bước** được dùng (Tải file → Nhãn & đặc
    trưng → Kết quả → Xử lý, đã làm ở mục 37; từ mục 48 KHÔNG còn bước chọn phương pháp). Phần logic Attribute 5 bước còn nằm trong file
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
  - Bước 5 (class): bước **Xử lý** đã làm ở mục 37 (`#panel-5-class`, hàm tiền tố `ch*` + object
    `classHandling` trong `workspace-flow.js`; backend `/api/class-noise/apply|undo|reset`).

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

  - `test_attribute_noise.csv` + `.xlsx` + `test_attribute_noise_ground_truth.csv` (sinh bằng `generate_test_attribute_noise.py`, hạt giống cố định) —
    file nhân viên 552 dòng × 20 cột chỉ cho ATTRIBUTE NOISE, đủ mọi loại lỗi, CÓ đáp án từng ô (mục 36). Kèm file nhỏ cho Convert / file xấu
    (`test_semicolon.csv`, `test_tab.txt`, `test_convert_nested.json`, `test_convert_lines.jsonl`, `test_empty.csv`, `test_header_only.csv`, `test_bad.json`).
  - `demo_attribute_noise_2000.csv` + `.xlsx` + `demo_attribute_noise_2000_ground_truth.csv` — bộ DEMO để chạy lúc bảo vệ và trích vào báo cáo: nhân viên, 1997 dòng × 20 cột, đủ mọi loại lỗi
    Attribute, có đáp án từng ô (mục 39). Tài liệu số kỳ vọng + kịch bản demo: `data/DEMO_ATTRIBUTE_2000.md`.
  - `kaggle_creditcard_fraud.csv` — bộ dùng cho CLASS NOISE (mục 35).

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

32. **Chỉnh giao diện sau mục 31 — ĐÃ XONG (commit `6fa2794` + đợt sau chưa commit lúc ghi):**
    - Bỏ nhãn dạng `[ ... ]` (eyebrow) ở mọi trang trừ `[ Bước N / 4 ]` của Class Noise; thanh đường dẫn + 3 chỉ số góc phải (`.ft-topbar`) tăng chữ 10,5px → 14px (commit `6fa2794`).
    - Menu "Product" chữ to hơn (nhãn cột 13px, tên tool 18px, mô tả 13px, ô icon 44px, chữ "Class Noise" 34px). 3 thẻ chọn thuật toán Class Noise: bỏ nhãn `N13` / `CL` / `N29`,
      chữ tiêu đề 19px, mô tả 15px; mô tả Ensemble thêm "Lâu hơn Distance-based nhưng thường chính xác hơn" (đo thật 30.000 dòng × 6 cột: Distance 1,2s, Ensemble 1,9s, Single/Random Forest 23s —
      nên Ensemble vẫn NHANH hơn Single learning, chỉ chậm hơn Distance).
    - **Guide viết lại thành hướng dẫn thao tác** (8 mục, mục lục đổi tên mục 01 "Bắt đầu nhanh", mục 07 "Nối tiếp và hoàn tác"): 4 bước làm sạch 1 file, bảng "gặp gì → dùng tool nào", cách dùng từng tool
      theo đúng tên nút / ô trên giao diện, 2 nhịp Phát hiện → Áp dụng, cách viết biểu thức, 4 bước Class Noise, dải nối tiếp + Hoàn tác, FAQ. Đọc ≈ 5 phút.

33. **Bộ dữ liệu test toàn diện + kịch bản thao tác người dùng — ĐÃ XONG [file `test_all_noise.*` đã được THAY bằng `test_attribute_noise.*` ở mục 36]:**
    - **Nguồn gốc:** user nhờ tạo 1 file chứa MỌI loại lỗi của sản phẩm (nhiều dòng) và liệt kê mọi trường hợp thao tác để tự test như người dùng thật, xem có lỗi ở đâu không.
    - **File** (trong `data/`): `generate_test_all_noise.py` (hạt giống cố định, chạy lại ra đúng cùng file) sinh `test_all_noise.csv` + `.xlsx` (552 dòng × 26 cột: 400 nhân viên, 100 người có 2 hợp đồng,
      12 người có 3 hợp đồng; 18 dòng trùng hệt, 6 gần trùng, 4 dòng trống hoàn toàn, cột `cot_trong` trống 100%, cột `Hệ số lương` có dấu cách + tiếng Việt, cột `thuong` zero-inflated, `xep_loai` đổi nhãn
      sai 45 dòng), `test_all_noise_ground_truth.csv` (đáp án từng ô cấy lỗi: dòng, cột, loại lỗi, giá trị gốc / đã cấy, tool nên bắt), và file nhỏ `test_semicolon.csv`, `test_tab.txt`,
      `test_convert_nested.json`, `test_convert_lines.jsonl`, `test_empty.csv`, `test_header_only.csv`, `test_bad.json`. Nhóm Phụ thuộc hàm cố ý có đủ 3 loại: nhóm 3 dòng 1 dòng sai (sửa về giá trị phổ biến
      được), nhóm 2 dòng hoà (chưa xác định được), 2 mã dùng chung cho 2 người (nghi sai `ma_nv`); dòng của các nhóm này KHÔNG bị nhân bản thành dòng trùng (sẽ làm lệch phép đếm đa số).
    - **`data/KICH_BAN_TEST.md`:** checklist ~150 ô theo nhóm (tài khoản, điều hướng, 4 Free Tools, Convert, 4 tool Cần cấu hình, nối tiếp + hoàn tác, Class Noise, trường hợp biên), mỗi mục kèm số kỳ vọng.
    - **Đối chiếu độc lập (script trong scratchpad, không nằm trong repo):** mọi tool chạy qua Flask test client trên file test, so với số tính bằng pandas độc lập: 0 lệch (trùng 21/27, cắt trắng 35/45,
      sai định dạng 38 ô ở 8 cột, ngoài khoảng 9/4/6/2, IQR 9 + Z-score 1, thuong IQR=0 80 ô, không nhất quán 14/5/15→19, 5 biểu thức 10/8/5/7/2, FD 32 dòng, Excel = CSV, Convert). Class Noise trên dữ liệu
      có nhãn cấy sai: Distance recall ~0,87, Ensemble ~0,89, Single ~0,60 (nhiều dòng nghi ngờ hơn thì recall cao hơn, precision thấp hơn).
    - **Mô phỏng người dùng bằng Playwright** (~170 kiểm tra: đăng ký/đăng nhập/đổi mật khẩu, mọi mục menu, 4 Free Tools + xem danh sách + nối tiếp + hoàn tác + tải file, Ô trống nhiều cột + điền tay, 4 tool Cần
      cấu hình + hộp xác nhận, Convert, Class Noise 4 bước 3 thuật toán, tải lại trang): sau khi sửa lỗi script test, không còn lỗi của app ngoài các điểm dưới đây.
    - **Lỗi thật tìm được + đã sửa:** (1) file rỗng báo tiếng Anh "No columns to parse from file" → `File rỗng: không có tên cột hay dòng dữ liệu nào.` (`_read_df_for_noise_tool`); (2) Class Noise chỉ chọn cột chữ
      nhiều giá trị (vd `ho_ten`) báo lỗi thư viện tiếng Anh "Found array with 0 feature(s)" → câu tiếng Việt rõ ràng (kiểm `detect_feature_columns` rỗng trong `class_noise_detect_api`);
      (3) trang tràn ngang ~260px ở màn 390px: header không xuống dòng và hình minh hoạ "trước → sau" của trang tool đặt ngang (thêm 2 `@media (max-width: 640px)` ở `workspace.css`);
      (4) Guide + mô tả Class Noise ghi "chỉ cột số" trong khi cột chữ đã chọn được (tự one-hot) → sửa chữ. [ĐÃ ĐẢO NGƯỢC ở mục 35: One-Hot đã gỡ khỏi web, chữ lại ghi "chỉ cột số".]
    - **Ghi nhận, chưa sửa (nhỏ):** Class Noise báo thiếu cột đặc trưng bằng `alert()` của trình duyệt (các nơi khác dùng dòng báo trong trang); đổi mật khẩu sang CHÍNH mật khẩu cũ vẫn được chấp nhận;
      dán / chọn file chỉ có dòng tiêu đề cho kết quả "giữ nguyên 0 dòng" không kèm giải thích; "Sửa về giá trị phổ biến nhất" luôn bỏ qua nhóm 2 dòng (hoà) — đúng thiết kế nhưng người dùng dễ tưởng lỗi.

34. **Class Noise Bước 1: hiện bảng xem trước dữ liệu như các tool khác — ĐÃ XONG, ĐÃ TEST (chưa commit lúc ghi):**
    - **Nguồn gốc:** user chụp Bước 1 Class Noise: chọn file xong chỉ thấy tên file + KB trong ô kéo-thả, không thấy dữ liệu như Free Tools / Cần cấu hình / Convert (các tool đó hiện bảng 100 dòng đầu + nút "↺ Đổi file").
    - **Làm gì:** `workspace.html` thêm khối `#class-raw-preview` (cùng class `.ft-raw-preview .cyd-table` với `#cf-raw-preview`) ngay dưới ô kéo-thả trong khung 01. `workspace-flow.js`: `handleFileSelected()` gọi `loadClassPreview(file)` → `POST /api/noise-tools/inspect`
      (dùng chung bộ đọc CSV/Excel với mọi tool nên Excel cũng xem được; route cũ, không sửa backend) → `showClassPreview()` ẩn ô kéo-thả và hiện bảng + "N dòng × M cột" + ghi chú "Xem trước 100/N dòng đầu · M cột". Nút `#class-change-file-btn`
      bỏ file đang chọn, trả lại ô kéo-thả, khoá nút Tải lên. File lỗi (rỗng...) thì khung hiện đúng lời báo của backend, không có bảng. `classPreviewSeq` bỏ kết quả về muộn khi chọn file khác giữa chừng. Tải lên thật vẫn qua `/api/upload` (xem trước chỉ để XEM); quay lại Bước 1 sau khi tải lên vẫn thấy bảng.
    - **Bẫy đã gặp:** `workspace-flow.js` (IIFE) đã có sẵn 1 hàm `renderPreviewTable()` riêng cho panel xem dữ liệu cũ, đè lên hàm cùng tên ở `workspace.js` → bảng rỗng, không báo lỗi gì. Nên Class Noise dùng hàm riêng `renderClassPreviewTable()`; ĐỪNG gọi các hàm của workspace.js từ trong workspace-flow.js mà không kiểm tra tên có bị trùng.
    - **Kiểm chứng:** Playwright `test_class_preview_ui.js` (21 kiểm tra: ô kéo-thả ↔ xem trước, Adult Income 32561 × 15 hiện 100 dòng, Excel 552 × 26, chọn lại đúng file cũ sau Đổi file, file rỗng, tải lên thật sang Bước 2 rồi quay lại, màn 390px không tràn ngang, không lỗi JS).

35. **CHỐT BỘ DỮ LIỆU: Credit Card Fraud (nguyên bộ); GỠ One-Hot khỏi web — ĐÃ XONG, ĐÃ TEST (chưa commit lúc ghi):**
    - **Quyết định của user:** "chốt Credit Card, bỏ phần One-Hot khỏi web, ghi vào file MD". Dùng NGUYÊN bộ `data/kaggle_creditcard_fraud.csv`
      (284.807 dòng × 31 cột: `Time`, `V1`–`V28` (PCA), `Amount`, `Class`; 492 gian lận = 0,173%; không ô thiếu, không cột chữ, 1.081 dòng trùng hệt).
      Adult Income thành bộ PHỤ (tuỳ chọn). Việc nên hỏi thầy xác nhận vì file gốc ~35 cột của thầy vẫn chưa có.
    - **Vì sao Credit Card:** (1) khớp quy trình thầy dặn (giảm cột → tương quan → cap outlier + log) và cùng LOẠI dữ liệu với dữ liệu thầy (toàn số, nhiều cột `V`,
      lớn); (2) không cần encode nên khỏi phình cột; (3) đặc trưng MẠNH: chạy web Single learning ra CV accuracy 99,94% vs baseline 99,83%, F1 lớp gian lận 0,825
      (Precision 0,875, Recall 0,780), 96 dòng bị gắn cờ (51 nhãn 0 → model tin 1, 45 nhãn 1 → model tin 0). **Nhược điểm phải nói rõ:** mất cân bằng cực lớn (0,17%);
      bước lọc tương quan sẽ KHÔNG loại cột nào (các cột `V` là PCA nên tương quan ≈ 0 — đúng kỳ vọng, không phải lỗi; dữ liệu thầy KHÔNG phải PCA vì tương quan 0,6–0,76);
      không tìm thấy bài nào về nhiễu nhãn trên bộ này; lớn nên Single learning (Random Forest) chậm.
    - **Gỡ One-Hot (đã làm):** `app.py` bỏ `import one_hot_encode_columns` + khối mã hoá, KHÔI PHỤC kiểm tra "cột đặc trưng phải là cột SỐ" (HTTP 400, nêu đúng tên cột chữ);
      `cap_outliers()` + `log_transform()` lại áp lên `feature_columns`. `workspace-flow.js`: `isClassFeatureUsable()` KHOÁ ô tick của cột chữ (kiểu đoán category/text/email/date)
      kèm ghi chú "cột chữ, chưa hỗ trợ", nút "Tích tất cả" chỉ tick cột số. `workspace.html`: Guide + mô tả Bước 2 ghi "chỉ cột số". KHÔNG xoá `categorical_encoding.py`
      và `evaluate_adult_*.py` (mã nghiên cứu, không còn được web gọi).
    - **Hạn chế để nói với hội đồng:** chưa xử lý được cột chữ/category; hướng phát triển: One-Hot (có chọn ngưỡng gộp), Frequency encoding, hoặc encoding theo từng thuật toán. Số đo đã có để dẫn:
      Adult 14 cột → 52 cột one-hot ở ngưỡng gộp 1% (27 ở 5%, 20 ở 10%); `education` trùng 1–1 với `education.num` (bỏ được 14 cột con không mất tin); cột chữ chiếm 47,4% tổng importance
      (Random Forest) so 52,6% của 6 cột số; Distance-based chuẩn hoá z-score nên cột one-hot hiếm cho giá trị tới ~9,95 (ngưỡng 1%) → át cột số; Random Forest ít bị ảnh hưởng nhất, Distance-based nhiều nhất
      (thứ tự này là suy luận + gợi ý yếu từ 1 lần chạy, CHƯA có thí nghiệm đối chứng riêng cho One-Hot).
    - **BÀI HỌC QUAN TRỌNG khi viết báo cáo:** bộ Credit Card (và Adult) KHÔNG có đáp án về dòng nhiễu; nhãn `Class` là nhãn thật ghi lại, không phải "đáp án nhiễu". Các chỉ số trên màn hình
      kết quả web (CV accuracy, Precision/Recall/F1 từng lớp, ma trận đếm) là chất lượng bộ phân loại dự đoán nhãn, KHÔNG phải độ chính xác của việc tìm nhiễu. Muốn chứng minh hiệu quả PHẢI cấy nhiễu có
      kiểm soát (đổi nhãn các dòng đã biết rồi đo Precision/Recall/F1 tìm lại) — script cấy nhiễu đã có sẵn cho Adult (`evaluate_distance_vs_confident.py`, `evaluate_ensemble_vs_others.py`), CHƯA chạy cho Credit Card.
      Khi cấy nhiễu vào Credit Card nhớ báo cáo theo cả 2 lớp (đổi 10% nhãn ngẫu nhiên sẽ tạo ~28.000 "gian lận giả", gấp ~57 lần gian lận thật).
    - **Tài liệu tham khảo (từ phiên đọc báo, CHƯA tự kiểm lại):** Adult có vài bài phát hiện nhiễu nhãn (gồm so với Confident Learning của cleanlab); không thấy bài nào cho Credit Card; cả 3 bài không thấy giảm cột / lọc tương quan;
      không so thẳng số được (khác thước đo FPR/FNR, "detection accuracy"...). Phiên đó chạy SPARK trên Adult đủ 58 cột (cấy nhiễu ngẫu nhiên, 1 seed): F1 CL 0,49/0,55/0,56, N13 0,44/0,51/0,52, N29 0,40/0,55/0,63 ở nhiễu 10/20/30% →
      kết luận "N13 thắng CL" ở mục 10 CHỈ ĐÚNG với bộ 6 cột số yếu, đủ cột thì N13 không còn thắng. Script phiên đó chưa nằm trong repo.
    - **Ghi chú môi trường:** phiên Default chặn `arxiv.org` (proxy 403); để đọc bài báo phải mở phiên mới với môi trường "SPARK - đọc bài báo học thuật" (đã cho phép arxiv.org). Cài thư viện cần `python3 -m pip install --ignore-installed blinker -r requirements.txt`.
    - **Kiểm chứng:** Playwright `test_no_onehot.js` (Credit Card mẫu 5.000 dòng gồm đủ 492 gian lận: tick đủ 30 cột số, chạy được CẢ 3 phương pháp ra kết quả; Adult: 8 cột chữ bị khoá + ghi chú, 6 cột số tick được,
      "Tích tất cả" chỉ tick 6 cột số; gọi API với cột chữ → 400 "Cột đặc trưng phải là cột SỐ…"; không lỗi JS).
    - **Việc tiếp theo đã đề xuất:** thiết kế + chạy thí nghiệm cấy nhiễu trên Credit Card nguyên bộ (5% / 10%, 2 kiểu, báo cáo cả 2 lớp, đo thời gian; Single learning có thể phải giảm số cây); xin thầy file dữ liệu thật;
      (tuỳ chọn) thí nghiệm đối chứng giảm cột trên Adult.

36. **Tách bộ test: file Attribute riêng (chủ đề nhân viên) + Class Noise dùng Credit Card — ĐÃ XONG, ĐÃ KIỂM CHỨNG (chưa commit lúc ghi):**
    - **Nguồn gốc:** user thấy file `test_all_noise.csv` (mục 33) gượng: đang là dữ liệu NHÂN VIÊN lại có cột điểm toán/lý/hoá + `xep_loai` (do mình chèn để thử Class Noise) và cột bán hàng
      (`so_luong_ban`, `don_gia`, `thanh_tien`, để thử rule công thức). Chốt: "1 file chứa Attribute Noise để làm được mọi loại lỗi bên Attribute, Class Noise dùng Credit Card".
    - **Làm gì:** thay bằng `data/generate_test_attribute_noise.py` → `test_attribute_noise.csv/.xlsx` (552 dòng × **20** cột) + `test_attribute_noise_ground_truth.csv` (302 dòng đáp án). Đã BỎ: cột điểm + `xep_loai`
      (Class Noise), cột bán hàng. THÊM `tong_thu_nhap = luong + thuong` để rule công thức vẫn có (`luong + thuong == tong_thu_nhap`, 8 dòng vi phạm); `luong` bị đổi thành số khác thì tổng được tính lại để không
      phát sinh vi phạm ngoài ý muốn. 20 cột: id, ma_nv, ho_ten, gioi_tinh, tuoi, ngay_sinh, email, so_dien_thoai, phong_ban, loai_hd, ngay_vao, ngay_ra, luong, thuong, tong_thu_nhap, hoa_hong, diem_dg, `Hệ số lương`, ghi_chu, cot_trong.
    - **Số kỳ vọng (đã đối chiếu: chạy qua route + tính độc lập bằng pandas, 0 lệch):** dòng trùng xoá 21 (27 nếu bỏ qua hoa/thường + khoảng trắng); cắt khoảng trắng 35 ô (45 nếu gộp lặp); sai định dạng 38 ô / 37 dòng
      (tuoi 3, luong 5, email 6, so_dien_thoai 6, ngay_sinh 10, ngay_vao 3, diem_dg 3, Hệ số lương 2); 4 dòng trống hoàn toàn + cột `cot_trong` trống 100%; ô trống mẫu 5 cột điền 53 ô; ngoài khoảng 9/4/6/2 (xoá HỢP tuoi+luong 13 dòng → 539);
      bất thường luong IQR 9 / Z-score 1, `thuong` IQR = 0 → 80 ô + cảnh báo; không nhất quán 14/5/15 (19 ở ngưỡng 0,85); Biểu thức 10/5/7/2/8/9; Phụ thuộc hàm 32 dòng (ho_ten 22 + ngay_sinh 14), sửa về giá trị phổ biến 6 ô, 9 nhóm chưa xác định.
      Excel ra đúng như CSV. Đoán kiểu cột đúng (số nguyên/số thực/email/SĐT/ngày/nhóm).
    - `data/KICH_BAN_TEST.md` cập nhật theo file mới; mục 7 Class Noise viết lại theo Credit Card (không còn số kỳ vọng riêng của file test cũ).
    - **Dirty Cafe Sales (Kaggle) thử trên web:** file người dùng tải về (10.000 dòng × 8 cột, DỮ LIỆU TỰ TẠO, giá trị giả `ERROR`/`UNKNOWN`) KHÔNG demo được hết tool: chỉ Sai định dạng (1.325 ô ở cột số + ngày), Ô trống,
      Convert có kết quả thật; Xoá trùng / Cắt khoảng trắng / Ngoài khoảng / Không nhất quán đều 0; Giá trị bất thường báo 259 dòng nhưng toàn giá trị 25 (= 5×5, hợp lệ) nên là báo nhầm của IQR trên dữ liệu rời rạc;
      Phụ thuộc hàm Item→Price báo 9.495 dòng nhưng sau khi bỏ ô `ERROR`/`UNKNOWN`/trống thì 0 vi phạm thật. **LỖ HỔNG phát hiện:** `ERROR`/`UNKNOWN` KHÔNG được coi là "thiếu" (`_is_missing_text` chỉ nhận rỗng, N/A, ?, null...) và Sai định dạng
      chỉ quét cột số/ngày nên 1.931 ô giả ở 3 cột chữ (Item 636, Payment Method 599, Location 696) không tool nào bắt; đề xuất (CHƯA làm): cho người dùng tự khai danh sách "giá trị coi như thiếu" ở tool Ô trống (không mặc định coi `UNKNOWN` là thiếu vì với dữ liệu khác có thể là nhóm hợp lệ).
    - **Student Admission Records (Kaggle, 157 dòng, tự tạo, có dòng trùng / ô thiếu / tuổi ngoại lai):** user chưa tải về, chưa thử.

37. **Class Noise — bước XỬ LÝ (Bước 4/4 của giao diện Denoise) — ĐÃ XONG, ĐÃ TEST (chưa commit lúc ghi):**
    - **Nguồn gốc:** user yêu cầu "cùng làm bước cuối của web là handling", chọn **cách B**: phát hiện lại sau khi xử lý thì chạy trên BẢN ĐÃ XỬ LÝ
      (giống nhánh Attribute, CLAUDE.md mục 13). Các lựa chọn còn lại do mình đề xuất theo khuyến nghị: 3 cách xử lý + gán hàng loạt theo ngưỡng
      (user chưa phản hồi riêng, đổi được nếu muốn).
    - **3 cách xử lý mỗi dòng** (theo phân loại Gupta & Gupta 2019): `keep` (Robust, coi là báo nhầm), `remove_row` (Filtering), `relabel` (Polishing,
      đổi nhãn sang nhãn gợi ý hoặc nhãn khác ĐÃ CÓ trong cột nhãn). Mặc định ô chọn = "— Chọn cách xử lý —" (bài học mục 13). Nhãn mới KHÔNG cho gõ
      tự do (gõ sai sẽ âm thầm tạo lớp mới): backend chỉ nhận nhãn đã có trong cột, nếu không báo 400.
    - **Backend** (`app.py`, khối "XỬ LÝ CLASS NOISE"): `POST /api/class-noise/apply` {file_id, label_column, dry_run, rows:[{row_number, action, new_label?,
      expected_label?}]}. `expected_label` = nhãn lúc phát hiện: nếu nhãn hiện tại đã khác (đã đổi ở lần trước) hoặc dòng đã bị xoá thì BỎ QUA dòng đó và
      báo `skipped_rows` (FE không đánh dấu "đã xử lý"). Dòng bị chọn 2 lần → 400. `dry_run=true` KHÔNG tạo bản đang làm việc/lịch sử, chỉ trả tác động
      (`rows_removed`, `labels_changed`, `relabel_directions` {"0→1": n}, `removed_by_label`, `label_counts_before/after`...). Chạy thật: dùng CHUNG
      `WORKING_FILES` + `HANDLING_HISTORY` + `HANDLING_LOCK` với nhánh Attribute (entry `group_key: "class_noise"`, snapshot bằng tham chiếu), bước không đổi gì
      thì không ghi lịch sử. `POST /api/class-noise/undo` và `/reset` (không detect lại, nhẹ hơn route Attribute), xuất file dùng lại `/api/export-working`.
      Chỉ cột NHÃN bị đổi hoặc xoá dòng; cột đặc trưng không bao giờ bị sửa (cap outlier + log chỉ chạy trên bản sao lúc detect).
      `/api/class-noise/detect` và `/reduce-features` giờ đọc `_peek_working_df()` (bản đang làm việc nếu có) và trả thêm `source`
      {is_processed, history_steps, rows, original_rows}. `row_number` vẫn là số dòng của FILE GỐC (index giữ nguyên sau khi xoá).
    - **Giao diện** (`workspace.html` `#panel-5-class`, `workspace-flow.js` đoạn "BƯỚC XỬ LÝ cho CLASS NOISE", `workspace.css` cuối file): thanh lịch sử
      (Hoàn tác / Về dữ liệu gốc, id `ch-*`, dùng lại class `history-bar`), khung **Gán hàng loạt** (hướng nhãn ghi → gợi ý + "Mức đáng ngờ từ" + cách xử lý),
      bảng từng dòng (ô chọn riêng, phân trang 20, tìm kiếm; dòng đã xử lý hiện "✅ Đã …"), nút Áp dụng ghi số dòng đã chọn. Áp dụng = chạy thử → hộp xác nhận
      (số dòng xoá/đổi nhãn, hướng đổi, phân bố nhãn trước → sau, **cảnh báo lớp hiếm** khi lớp chiếm < 5%: đổi nhãn sang lớp hiếm hoặc xoá dòng lớp hiếm,
      cảnh báo khi xoá ≥ 20% số dòng) → "Xác nhận và áp dụng" (focus mặc định ở Huỷ). Chỉ chọn "Giữ nguyên" thì không hỏi. Hộp tự đóng khi đổi lựa chọn / rời bước;
      so chữ ký lựa chọn trước và sau khi chạy thử để không áp dụng lệch. Khoá chạy chồng bằng `classHandling.busy`. Hoàn tác trả đúng các dòng của bước đó về
      "chưa xử lý" (`classHandling.steps`); nếu danh sách đã cũ (hoàn tác bước từ trước lần phát hiện) thì nhắc bấm "Phát hiện lại". Phát hiện lại → xoá lựa chọn
      cũ (`chResetForNewFindings`); tải file mới → `chResetAll`. Bước chọn nhãn hiện dòng "Đang chạy trên dữ liệu đã xử lý (N bước)" khi đã có xử lý.
    - **Bẫy cần nhớ:** `workspace-flow.js` là một IIFE chung, nên hàm/biến của khối này đều có tiền tố `ch`/`classHandling` để không đè tên hàm Attribute
      (từng gặp ở mục 34).
    - **Kiểm chứng:** `test_class_handling_api.py` (Flask test client, ~35 kiểm tra đạt toàn bộ: dry_run không ghi gì, nhãn/dòng đổi đúng, file gốc nguyên vẹn, cột đặc trưng
      không đổi, dòng đã xoá/nhãn đã đổi bị bỏ qua, nhãn không tồn tại/action lạ/chọn 2 lần/thiếu row_number → 400, người khác → 404, undo/reset, xuất file, detect
      trên bản đã xử lý giữ nguyên số dòng gốc) và Playwright `test_class_handling_ui.js` (~40 kiểm tra trên file mẫu 600 dòng: gán hàng loạt theo hướng + ngưỡng, hộp
      xác nhận, Huỷ không đổi gì, áp dụng, hoàn tác, xoá, xuất CSV 593 dòng, phát hiện lại ra đúng 593 dòng dùng được, về gốc; không lỗi JS). Hai file test nằm ở thư mục tạm, không trong repo.
    - **Chưa làm:** "mức tin cậy cao" (đánh dấu dòng cả 3 thuật toán cùng gắn cờ), nút xem dữ liệu sau xử lý như Attribute, chọn nhãn tự do cho trường hợp
      nhiều lớp ngoài danh sách nhãn hiện có.

38. **Thí nghiệm cấy nhiễu có kiểm soát trên Credit Card nguyên bộ — ĐÃ CHẠY XONG (chưa commit lúc ghi):**
    - **Script + dữ liệu:** `evaluate_creditcard_noise_injection.py` (gốc repo) ghi kết quả 30 dòng JSON vào `data/creditcard_noise_experiment_results.jsonl`
      (mỗi dòng: kịch bản, bộ cột, thuật toán, TP/FP/FN, P/R/F1 tổng và theo chiều đảo, thời gian, chẩn đoán). Chạy lại: `python3 evaluate_creditcard_noise_injection.py
      --scenarios base:0,A:0.05,A:0.10,B:0.10,B:0.30 --columns all,reduced --methods ensemble,distance,single --single-trees 300 --k 5`.
    - **Cách làm:** 284.807 dòng × 30 cột đặc trưng (Time, V1–V28, Amount), nhãn Class (0: 284.315, 1: 492). Tiền xử lý y hệt web (cap outlier IQR 1,5 + log1p),
      bước cap dùng bản VECTOR HOÁ (`fast_cap_outliers`) đã đối chiếu từng ô với `cap_outliers()` gốc ở cột V1, V14: GIỐNG HỆT. LÝ DO: `cap_outliers()` gốc mất 20–85 giây
      MỖI CỘT trên Credit Card (lặp `.loc` từng ô), tức hơn 20 phút cho 30 cột mỗi lần bấm Phát hiện trên web (bản vector hoá: 6,3 giây). **ĐÃ VÁ vào code web (sau mục này):** `class_noise/feature_selection.py::cap_outliers()` giờ cap cả cột bằng một phép gán
      vector hoá, vẫn tái dùng đúng `detect_outlier()`, `_resolve_cap_bounds()`, `_format_numeric_for_column()` của nhánh Attribute (chỉ thay vòng lặp `.loc` từng ô). Đối chiếu bản mới với bản
      cũ TỪNG Ô: dữ liệu bẩn tổng hợp (ô rỗng/chữ/`nan`/`inf`/`1e3`, cột hằng, cột zero-inflated, cột < 4 ô số, cả IQR 1,5 và 3, Z-score 3 và 2) = giống hệt; Credit Card thật cột Time, V1, V14,
      V20, Amount = giống hệt (bản cũ 0,3 / 19,8 / 38,8 / 75,8 / 86,8 giây, bản mới 0,3–0,5 giây); cả 30 cột: 8,1 giây (trước đó hơn 20 phút). Test backend + Playwright Class Noise chạy lại đều đạt.
      `fast_cap_outliers()` trong script thí nghiệm giờ chỉ còn là bản sao tương đương (giữ nguyên để kết quả mục này tái lập được).
      Cấy nhiễu (seed 42, cùng một tập dòng đảo cho cả 3 thuật toán và cả 2 bộ cột): **A** đảo đồng đều p% mọi dòng (5% = 14.240 dòng, 10% = 28.481; gần như toàn "gian lận giả");
      **B** đảo q% gian lận thật sang 0 và ĐÚNG BẰNG ẤY dòng bình thường sang 1 (10% = 49+49, 30% = 148+148; số nhãn "1" vẫn 492). Bộ cột: đủ 30, và "giảm cột" = xếp hạng
      Random Forest 300 cây trên nhãn ĐÃ cấy nhiễu của kịch bản đó rồi Elbow (KHÔNG chạy lọc tương quan, vì cột V là PCA nên vốn không loại được cột nào). Tham số như web:
      Single 300 cây 5-fold, Distance k=5, Ensemble 5-fold. Dòng không bị đảo mà vẫn bị gắn cờ tính là báo nhầm (FP) dù có thể là nhiễu thật sẵn có -> Precision là cận dưới.
    - **Kết quả F1 (Precision / Recall), đủ 30 cột:**
      | Kịch bản | Single | Distance | Ensemble |
      |---|---|---|---|
      | A 5% | 0,201 (0,120/0,630) | **0,862** (0,831/0,896) | 0,173 (0,099/0,679) |
      | A 10% | 0,248 (0,156/0,599) | **0,824** (0,796/0,854) | 0,260 (0,163/0,638) |
      | B 10% | **0,704** (0,614/0,827) | 0,567 (0,421/0,867) | 0,022 (0,011/0,980) |
      | B 30% | **0,732** (0,760/0,706) | 0,663 (0,609/0,726) | 0,045 (0,023/0,919) |
    - **Bộ cột giảm (F1):** B 10%: Single 0,570, Distance 0,471, Ensemble 0,024; B 30%: Single 0,699, Distance 0,578, Ensemble 0,051 (8 cột V14, V10, V4, V12, V17, V11, V3, V16).
      Ở kịch bản A, Elbow chỉ giữ **1 cột (`Time`)** vì nhiễu nhãn chôn tín hiệu thật -> F1 tụt (Distance 0,495/0,475, Single 0,085/0,122, Ensemble 0,115/0,207).
    - **Thời gian (đủ 30 cột):** Ensemble 5–9 giây; Distance 82–87 giây (8 cột: 15–18 giây); Single 252 giây (sạch), 287–304 giây (B), 652–747 giây (A, nhãn "1" rất nhiều;
      lần A 5% có thể bị chậm thêm do máy chạy test song song). 8 cột giúp Single nhanh gấp đôi, Distance 5–6 lần.
    - **Dữ liệu gốc chưa cấy nhiễu (số dòng gắn cờ, đủ 30 cột):** Single 42 (CV accuracy 99,95% > baseline 99,83%), Distance 96 (độ phủ 92,4%), Ensemble 7.599 (ba classifier đều có accuracy
      DƯỚI baseline: LogisticRegression 97,04%, GaussianNB 99,59%, LinearSVC 97,23%) -> kết quả Ensemble trên bộ này không đáng tin theo đúng quy tắc chẩn đoán đã ghi. Lần chạy web trước ra Single 96 dòng
      (khác 42): chưa làm rõ (có thể khác bộ cột hoặc số cây).
    - **Kết luận có căn cứ:** (1) KHÔNG có thuật toán thắng ở mọi kiểu nhiễu: nhiễu đảo đồng đều -> Distance dẫn rất xa; nhiễu sát thực tế (lớp hiếm giữ nguyên) -> Single dẫn, Distance thứ hai,
      Ensemble gần như vô dụng (Recall 0,92–0,98 nhưng Precision 0,01–0,05). (2) Distance bắt tốt "gian lận giả" (đảo 0 -> 1, Recall 0,94–0,96 ở kịch bản B) nhưng bỏ sót gian lận thật bị ghi 0
      (Recall 1 -> 0 chỉ 0,49 ở B 30%); Single cân bằng hơn (0,72 và 0,69). (3) Giảm cột không miễn phí: giảm F1 để đổi lấy tốc độ, và Elbow sụp (1 cột) khi nhãn quá bẩn.
      Phần giải thích "vì sao" (gian lận giả nằm giữa hàng xóm bình thường nên Distance thấy ngay) là suy luận hợp lý, CHƯA có thí nghiệm riêng kiểm chứng.
    - **Hạn chế khi trích dẫn:** một seed (42), không có khoảng tin cậy; B chỉ 98/296 dòng đảo nên Recall nhảy từng bước ~2 điểm %; nhiễu đảo ngẫu nhiên không phụ thuộc đặc trưng (kiểu nhiễu khác chưa thử);
      k cố định 5; Precision là cận dưới (nhiễu gốc sẵn có không có đáp án).

39. **Bộ DEMO Attribute Noise 1997 dòng cho buổi bảo vệ + báo cáo — ĐÃ XONG, ĐÃ KIỂM CHỨNG (chưa commit lúc ghi):**
    - **Nguồn gốc:** user nhờ "tạo bộ dữ liệu nhân viên tầm 2000 dòng chứa đủ tất cả các lỗi của phần attribute noise (phần Product) để chạy lúc bảo vệ và viết vào báo cáo".
    - **Cách làm:** KHÔNG viết script mới mà nâng `data/generate_test_attribute_noise.py` (mục 36) bằng hệ số `SCALE` (biến môi trường) + `OUT_NAME`: `sc(x)` nhân số lượng mọi loại lỗi và số nhân viên,
      `cyc()`/`ztake()` lặp vòng các giá trị lỗi mẫu cho đủ số lượng. `SCALE=1` (mặc định) ra ĐÚNG từng ô bộ test 552 dòng cũ (đã so csv + đáp án bằng `git diff`: giống hệt). `SCALE=3.62
      OUT_NAME=demo_attribute_noise_2000` ra 1997 dòng × 20 cột, 1087 dòng đáp án (65 trùng hệt + 22 gần trùng, 14 dòng trống hoàn toàn, 138 sai định dạng, 311 ô trống cấy, 141 khoảng trắng, 76 ngoài khoảng,
      29 bất thường, 135 không nhất quán, 115 vi phạm biểu thức, 47 ô phụ thuộc hàm). Cùng hạt giống nên chạy lại ra đúng cùng file.
    - **Kiểm chứng:** mỗi tool chạy qua ĐÚNG route của web (Flask test client) rồi so với (a) phép tính độc lập bằng pandas, (b) đáp án cấy sẵn: 35 phép đo trên file gốc + chạy lại trên dữ liệu NỐI TIẾP
      (xoá trùng → cắt khoảng trắng → xoá dòng trống): tất cả khớp 100%. Bản Excel ra cùng số với CSV. Playwright trên giao diện thật: xoá trùng 78, cắt khoảng trắng 127, sai định dạng 138, biểu thức 36 dòng.
      Số chính (file gốc): trùng 78 (100 khi bỏ qua hoa/thường), khoảng trắng 127 (163 khi gộp), sai định dạng 138 ô/132 dòng, ô trống 602 + 14 dòng trống + cột `cot_trong`; ngoài khoảng 33/14/22/7;
      bất thường luong IQR 32 và Z-score 3 (Z-score bị chính giá trị cực đoan kéo phình độ lệch chuẩn), thuong IQR 306 + cảnh báo; không nhất quán 50/18/53 (phong_ban 67 ở ngưỡng 0,85); biểu thức 36/29/18/25/7;
      phụ thuộc hàm 116 dòng (78 + 52). Chạy nối tiếp: chỉ khác thuong IQR (295) và số dòng sau mỗi bước (1997 → 1919 → 1918).
    - **Bài học khi demo:** các tool NỐI TIẾP nhau nên số thay đổi (14 dòng trống giống nhau bị "Xoá dòng trùng" xoá 13 trước, "Ô trống" chỉ còn xoá 1) — tài liệu ghi cả hai bộ số, trước mỗi tool nên bấm "Bắt đầu lại từ gốc".
    - **Lưu ý kỹ thuật:** tool "Không nhất quán" cần người dùng khai danh sách giá trị chuẩn (`valid_categories`), không tự đoán; không khai thì trả 0 ô.
    - **Tài liệu:** `data/DEMO_ATTRIBUTE_2000.md` (bảng lỗi cấy, số kỳ vọng từng tool + cấu hình nhập, số khi nối tiếp, kịch bản demo ≈ 10–12 phút, đoạn gợi ý ghi vào báo cáo + hạn chế).

40. **Class Noise: khung lưu ý "nên xử lý Attribute noise trước" — ĐÃ XONG, ĐÃ TEST (chưa commit lúc ghi):**
    - **Nguồn gốc:** user yêu cầu "khi bấm vào Class Noise thì có chỗ lưu ý là nên xử lý attribute trước khi chạy class noise".
    - **Làm gì:** `workspace.html` thêm khối `#class-attr-note` (class `.cn-attr-note`, nền vàng nhạt + vạch vàng, cùng tông `.cf-stale-note`) ở đầu Bước 1 của `#section-class-noise`, ngay dưới `panel-desc`, trên 2 khung 01/02.
      Nội dung ngắn: nên làm sạch ô trống / sai định dạng / dòng trùng / giá trị bất thường trước vì chúng làm cột đặc trưng sai → tìm nhãn sai kém tin cậy. Hai link `data-section="free-tools"` («Tự động») và
      `data-section="config"` («Cần cấu hình») dùng bộ chuyển khối sẵn có (`switchSection`), không cần JS mới. CSS ở `workspace.css` (`#section-class-noise .cn-attr-note`).
    - **Vì sao chữ dặn "tải file kết quả về rồi tải lên ở đây":** các tool Tự động / Cần cấu hình chạy stateless qua dải nối tiếp (`state.pipe`), KHÔNG chia sẻ `file_id` với Class Noise (Class Noise dùng `/api/upload`);
      muốn nối thẳng phải làm thêm nút "Xử lý tiếp bằng Class Noise" [ĐÃ LÀM ở mục 42].
    - **Kiểm chứng:** Playwright (khung hiện khi vào Class Noise, đúng vị trí, nền đúng, 2 link chuyển đúng khối, quay lại vẫn thấy, nút Tải lên + 3 thẻ phương pháp không đổi, màn 390px không tràn ngang, không lỗi JS) + xem ảnh chụp.

41. **Class Noise bước Xử lý: bỏ nút "Phát hiện lại", STT, lọc bảng theo hướng, ô mức đáng ngờ bị kẹp khoảng, rút gọn chữ — ĐÃ XONG, ĐÃ TEST (chưa commit lúc ghi):**
    - **Nguồn gốc:** user hỏi ý kiến về nút "Phát hiện lại trên dữ liệu hiện tại →" (chỉ gọi `goStep(3)`, vẫn phải bấm Phát hiện ở bước 2), mình đồng ý nên bỏ; user bảo "code bỏ phần đấy đi" + 3 việc kèm theo + "có nhiều chữ quá".
    - **Bỏ nút** `#ch-redetect-btn` (HTML + listener). Phát hiện lại trên bản đã xử lý VẪN dùng được: "← Quay lại kết quả" hoặc bấm thanh bước 2 → Phát hiện (server vẫn đọc `_peek_working_df`); dòng ghi chú ở bước chọn nhãn vẫn báo "Đang chạy trên dữ liệu đã xử lý (N bước)".
    - **STT:** bảng `#ch-table` có cột "STT" (số thứ tự trong danh sách đang hiện, đếm tiếp qua các trang) trước cột "Dòng" (số dòng trong file). Bảng ở bước Kết quả (`#class-findings-table`) CHƯA thêm STT.
    - **Lọc bảng theo hướng:** `chFiltered()` lọc theo ô "Hướng đổi nhãn" của khung Gán hàng loạt (+ ô tìm kiếm); đổi hướng thì về trang 1; tiêu đề `#ch-list-title` ghi "Dòng nghi ngờ (N)". Số trong ngoặc của từng hướng nay đếm CẢ dòng đã xử lý (= số dòng bảng hiện), trước đây chỉ đếm dòng chưa xử lý. Ô "Mức đáng ngờ từ" KHÔNG lọc bảng, chỉ giới hạn nhóm dòng được Gán.
    - **Ô "Mức đáng ngờ từ":** `chScoreRange()` lấy khoảng điểm thật của danh sách (làm tròn ra 3 số lẻ) → đặt `min`/`max`/`placeholder`; chặn gõ `e + -`; gõ quá lớn kẹp ngay về max, rời ô/Enter kẹp cả phía nhỏ về min; bỏ trống = tất cả; `chMinScoreValue()` luôn trả giá trị đã kẹp nên số dòng "Khớp N" luôn đúng khoảng.
    - **Rút gọn chữ:** mô tả đầu bước còn 1 câu, tóm tắt "N dòng nghi ngờ. Chưa chọn dòng nào.", bỏ câu giải thích dài ở lịch sử / khung gán / hộp xác nhận / thông báo sau Áp dụng (bỏ mọi chỗ nhắc nút «Phát hiện lại»).
    - **Kiểm chứng:** Playwright `test_ch_filters.js` (2 bộ: 12 dòng nghi ngờ và 203 dòng / 6 trang: không còn nút, 3 nút cuối, STT liên tục kể cả trang 2 bắt đầu từ 21, mỗi hướng bảng đúng 106 / 97 dòng, ô mức kẹp đúng min/max, mũi tên spinner, không lỗi JS) + chạy lại `test_class_handling_ui.js` (~45 kiểm tra, sửa 3 câu theo chữ mới) = đạt.

42. **Nút «Class Noise» ở "Xong · xử lý tiếp bằng": chuyển kết quả của chuỗi tool sang Class Noise — ĐÃ XONG, ĐÃ TEST (chưa commit lúc ghi):**
    - **Nguồn gốc:** user chụp dải 3 nút (Cần cấu hình / Convert / Tự động) và muốn thêm Class Noise bên phải "Tự động" để xử lý xong có thể đưa dữ liệu sang Class Noise.
    - **Cách làm:** `workspace.js`: `CONTINUE_GROUPS` thêm mục `{key:"class-noise", special:true}` (hiện ở CẢ 3 nhóm vì dải dùng chung); bấm thì gọi `sendPipeToClassNoise()` (không mở danh sách tool): `switchSection("class-noise")` + `DenoiseFlow.loadCsvText(state.pipe.currentText, "<tên gốc>_da-xu-ly.csv")`.
      `workspace-flow.js`: `loadCsvText()` dựng `File` từ chuỗi CSV, `goStep(1)` rồi gọi đúng `handleFileSelected()` như vừa chọn file (có bảng xem trước, đọc bằng `/api/noise-tools/inspect`); người dùng chọn phương pháp + Tải lên như thường nên đi qua `/api/upload` bình thường (không thêm route backend).
      Dữ liệu JSON (sau CSV → JSON) thì nút bị khoá như các nhóm khác. Khung lưu ý đầu Class Noise (mục 40) đổi chữ: chỉ cách bấm «Class Noise» thay vì "tải về rồi tải lên".
    - **Giới hạn:** file Class Noise sinh ra là BẢN SAO tại thời điểm bấm (xử lý tiếp bằng tool khác sau đó không tự cập nhật sang Class Noise); nếu Class Noise đang có file cũ ở các bước sau thì chỉ khi Tải lên file mới nó mới đổi.
    - **Kiểm chứng:** Playwright `test_to_class_noise.js`: Xoá dòng trùng 2030 → 2000 dòng, 4 nút đúng thứ tự, bấm Class Noise → bước 1 hiện "class_dup_da-xu-ly.csv · 2000 dòng × 4 cột", Tải lên + phát hiện Distance-based chạy trên đúng 2.000 dòng, sau Convert CSV → JSON nút bị khoá, không lỗi JS.

43. **Thông báo trạng thái dùng chung đổi màu cho hợp Denoise — ĐÃ XONG, ĐÃ XEM ẢNH CHỤP (chưa commit lúc ghi):**
    - **Nguồn gốc:** user chụp "✅ Đã áp dụng: xoá 3.738 dòng." chữ xanh cobalt (là `--signal` của Denoise, trông như link) và nhờ kiểm tra MỌI thông báo kiểu đó để đổi màu cho hợp web.
    - **Cách làm** (cuối `workspace.css`, không đụng logic JS): token `--ok-*` (xanh lá), `--bad-*` (đỏ), `--warn-*` (vàng) cùng bộ màu với `.cf-live` / `.cf-stale-note` sẵn có. `.status-text.is-ok / is-error / is-warn` thành "thanh màu" (nền nhạt + vạch trái 3px, vuông góc); trong ô bảng (`td`) chỉ đổi màu chữ.
      `.form-error` và `.handling-confirm` (hộp xác nhận xoá) cùng kiểu thanh đỏ; `#class-warning-card` (cảnh báo độ phủ thấp / mô hình học yếu của Class Noise) đổi từ chữ đỏ inline sang thanh vàng (bỏ `color:var(--danger)` inline ở 3 chỗ trong `workspace-flow.js`). Đã xoá rule ép `#section-class-noise .status-text.is-ok { color: var(--signal) }`.
    - **Quy ước giữ cho nhất quán:** xong = xanh lá, lỗi = đỏ, cảnh báo = vàng; màu cobalt (`--signal`) chỉ dùng cho nhấn thương hiệu / nút / link, KHÔNG dùng cho thông báo kết quả. Giao diện cũ (`style.css`) không đụng.
    - **Bổ sung sau khi user hỏi "cả bên attribute noise nữa":** chụp Cần cấu hình (Giá trị bất thường: cảnh báo IQR = 0, xem trước, hộp xác nhận). Các thanh vàng / đỏ / xanh lá sẵn có (`.cf-live`, `.cf-stale-note`, `.cf-confirm`, `.cf-sum-warn`) đã đúng tông; sửa 3 chỗ còn lệch:
      `.cf-action-preview` ("Sẽ xoá N dòng… vì chọn…") từ thanh cobalt → vàng (báo trước = vàng, đỏ khi ≥ 20% số dòng như cũ); `.cf-sum-risk` thêm vạch đỏ bên trái cho khớp; nút «Xác nhận xoá và áp dụng» (`#cf-confirm-yes`) từ `btn-accent` cobalt → `btn-danger` đỏ (giống hộp xác nhận của Class Noise).

44. **`/api/upload` xoá tệp trên đĩa ngay sau khi đọc — ĐÃ XONG, ĐÃ TEST:**
    - **Nguồn gốc:** khi viết mục 3.4.1 khoá luận phát hiện `/api/upload` (luồng Class Noise) ghi tệp vào `uploads/<file_id>_<tên>` rồi KHÔNG BAO GIỜ xoá, trái với trang Guide ("Chỉ trong bộ nhớ server lúc đang xử lý, không ghi ra đĩa") và Privacy ("Khởi động lại server là file biến mất"). User chọn sửa code thay vì ghi hạn chế vào bài.
    - **Cách làm:** `app.py::upload_file()` bọc `load_data(save_path)` trong `try/finally: save_path.unlink(missing_ok=True)` — giống `_read_df_for_noise_tool()` của các tool. Bảng chỉ còn trong `UPLOADED_FILES` (RAM); thư mục `uploads/` vẫn được tạo vì các tool dùng làm chỗ lưu tạm.
    - **Kiểm chứng:** Flask test client: đăng ký + đăng nhập → `/api/upload` (200, 3 dòng) → không còn tệp mới trong `uploads/` → `/api/class-noise/detect` (distance_based) 200 → `/api/class-noise/apply` xoá 1 dòng 200 → `/api/export-working` 200; tệp rỗng vẫn lỗi 500 như trước nhưng tệp cũng đã bị xoá. Máy đã chạy bản cũ thì tự xoá các tệp cũ còn trong `uploads/`.

45. **Class Noise trên web: bước chuẩn bị chung, "Bộ kết hợp", Giảm số cột là lựa chọn, báo cáo cột bị bỏ, cảnh báo theo mức vượt mốc — ĐÃ XONG (22/11/2026), CHỈ chạy thử bằng tay, KHÔNG viết test mới (chưa commit lúc ghi):**
    - **Nguồn gốc:** mục "7. Web" trong bản yêu cầu của user (= mục 6 của kế hoạch cải tiến Class Noise ở cuối file); user nói "Làm mục 7 đi, không cần test đâu".
    - **Backend `/api/class-noise/detect` (`app.py`):** MỌI phương pháp giờ đi qua `class_noise/preprocess.py::prepare_for_class_noise()` TRƯỚC khi chạy (bỏ cột hằng / gần toàn trống / định danh / tương quan >= 0,8
      KHÔNG dùng nhãn; bỏ dòng còn ô trống; gộp dòng trùng đặc trưng cùng nhãn; báo nhóm mâu thuẫn). Payload thêm `reduce_columns` (mặc định false = "Không giảm số cột"; true = giảm theo nhãn bằng Random Forest +
      điểm gãy, kèm cảnh báo trong `preprocess.warnings`). Thêm `method="combined"` (`detect_class_noise_combined`, tham số `alpha` 0 = công tắc / 0,5 = pha trộn, `n_estimators` mặc định 100, k của Mutual k-NN = "auto").
      `k` của Distance-based: không gửi khoá `k` = 5 như cũ; gửi `null` / `""` / `"auto"` = tự chọn theo độ phủ (ô k trên web để trống = tự động, mặc định ô vẫn là 5 vì thực nghiệm mục 5 cho thấy "k theo độ phủ" kém k = 5 ở 3/4 bộ).
      Distance + Ensemble vẫn cap outlier + log (trên bản chuỗi của bảng đã chuẩn bị), Confident Learning dùng giá trị nguyên.
    - **Response mới:** `preprocess` (cột bị bỏ + mã luật + chi tiết, cột giữ, số dòng nhãn trống / ô trống / gộp / nhóm mâu thuẫn, danh sách nhóm mâu thuẫn cắt ở 50 nhóm, `label_reduction`, `warnings`);
      `diagnostics.quality` = {level `none` (mức vượt mốc <= 0) | `low` (< 20%) | `ok`, excess, message} (Single: Random Forest; Ensemble: classifier tốt nhất; Distance không có vì không có mô hình, vẫn dùng độ phủ < 50%);
      Single thêm `excess_over_baseline`, `mcc`, `pr_auc_macro`, `estimated_noise_rate`, `estimated_label_errors`, `params`, `warnings`; Distance thêm `k_mode`, `coverage`, `coverage_by_k`, `binary_columns`, `pca`, `warnings`;
      Ensemble thêm `per_classifier_excess`, `best_excess_over_baseline`; Combined có `diagnostics.methods` {bật/tắt, mức vượt mốc, trọng số, số dòng tự gắn cờ, lý do} + `single`/`distance`/`ensemble` và mỗi dòng Top-K có
      `supporters`, `ranks`, `distance_disagreement`, `model_probability_recorded` (xác suất mô hình cho NHÃN ĐANG GHI), `ensemble_disagreement`. `diagnostics.n_rows_total` luôn là tổng dòng của FILE (không phải sau khi gộp).
    - **Dòng trùng đã gộp được trả về cả nhóm:** dòng đại diện bị gắn cờ thì mọi dòng cùng nhóm cũng có mặt trong `findings` kèm `duplicate_of` (`web_adapter.expand_findings`); `row_number` vẫn là số dòng của file gốc.
    - **File mới `class_noise/web_adapter.py`** (thuần Python): `string_frame`, `expand_findings`, `quality_assessment`, `preprocess_info`, `finite` — tách khỏi `app.py` để `app.py` chỉ "phiên dịch" JSON. Ngưỡng cảnh báo `LOW_EXCESS` = 0,2 lấy chung với
      `PreprocessConfig.low_margin_warning` (con số TỰ ĐỀ XUẤT, chưa có căn cứ thống kê). **Khác yêu cầu gốc:** yêu cầu ghi cảnh báo khi mức vượt mốc "<= 0"; mình cảnh báo thêm mức vàng cho < 20% (đỏ vẫn là <= 0).
    - **Sửa lỗi tìm thấy khi chạy thử:** `preprocess.py::_margin_over_baseline` báo "classes ... are not in class_weight" với nhãn dạng chuỗi trên scikit-learn 1.9 (cross_val_predict + class_weight="balanced") → mã hoá nhãn bằng `LabelEncoder` trước khi đưa vào.
    - **[PHẦN GIAO DIỆN NÀY ĐÃ ĐƯỢC THAY Ở MỤC 48: không còn 4 thẻ phương pháp, 2 ô Giảm số cột, ô tham số; chỉ còn 1 nút "Phát hiện nhãn sai"]** **Giao diện (`workspace.html`, `workspace-flow.js`, `workspace.css`):** thẻ phương pháp thứ 4 "Bộ kết hợp (thử nghiệm)"; khối "Giảm số cột" = 2 ô chọn (radio) thay nút "Chạy giảm cột tự động" (route cũ `/api/class-noise/reduce-features` VẪN CÒN trong `app.py` nhưng giao diện không gọi nữa);
      ô tham số "Cách kết hợp" (công tắc / pha trộn); thẻ `#class-preprocess-card` ở bước Kết quả (cột bị bỏ + luật, dòng gộp / mâu thuẫn, xếp hạng khi giảm theo nhãn, cảnh báo); thẻ chỉ số Single có Mức vượt mốc, MCC, PR-AUC, ước lượng nhãn sai;
      khung cảnh báo `#class-warning-card` dùng `diag.quality` (đỏ khi `none`, vàng khi `low`); bảng danh sách của Bộ kết hợp có cột "Cùng nghi" (2 dòng: phương pháp cùng gắn cờ + chỉ số thành phần); bảng ghi chú "trùng dòng X" cho dòng thêm từ nhóm trùng;
      nhãn gợi ý rỗng (Bộ kết hợp có thể không có gợi ý) được xử lý ở bước Xử lý (không có lựa chọn "gợi ý", gán hàng loạt bỏ qua dòng đó); Guide + dòng "Thuật toán 4 lựa chọn" cập nhật.
    - **Bộ kết hợp trên web dùng Ensemble 3 mô hình CŨ** (không phải bản 5 họ): bản 5 họ chậm hơn (MLP, KNN, HistGradientBoosting) và chạy ĐỒNG BỘ; thực nghiệm mục 7 cho thấy cả hai bản đều không vượt `naive_cv`. Ensemble 5 họ vẫn CHƯA nối vào web.
    - **Chạy thử bằng tay (không phải test chính thức):** Flask test client + trình duyệt thật (Playwright) trên Car (`car_noisy_5.csv`) cho cả 4 phương pháp (không lỗi JS, bảng + thẻ hiện đúng, sang được bước Xử lý) và lựa chọn "Giảm số cột";
      mẫu Credit Card 4.513 dòng (có thêm 20 dòng trùng + 1 nhóm mâu thuẫn): gộp 49 dòng vào 41 nhóm, 1 nhóm mâu thuẫn, cột `Time` bị bỏ vì "giống mã định danh" (mẫu nhỏ nên 95% giá trị khác nhau — trên file đầy đủ 284.807 dòng tỉ lệ chỉ ~44% nên cột được giữ),
      cột V7, V12, V17... bị bỏ vì tương quan; ép mô hình yếu (chỉ cột `doors`) → cảnh báo đỏ ở cả Single, Ensemble, Bộ kết hợp. KHÔNG chạy lại các bộ test cũ (user bảo bỏ qua; test cũ vốn nằm ngoài repo).
    - **Giới hạn / chưa làm:** chạy đồng bộ, chưa có thanh tiến độ (Bộ kết hợp chạy cả 3 phương pháp nên lâu hơn); chưa hiện `calibrated_joint` hay `pr_auc_per_class` trên web; danh sách nhóm mâu thuẫn chỉ cắt 50 nhóm; Guide bước 4 ("Xử lý") vẫn ghi
      "chưa có xử lý tự động" dù mục 37 đã làm (sai từ trước, chưa sửa); bộ lọc ở bước Xử lý vẫn dựa trên `suggested_label` nên với Bộ kết hợp các dòng không có gợi ý nằm chung nhóm "→ —"; chưa push.

46. **So sánh mô hình nền của Confident Learning: Random Forest (bagging) vs LightGBM (boosting) — ĐÃ CHẠY XONG (22/11/2026); CHỈ là thực nghiệm, KHÔNG đổi code web / `confident_learning.py` (chưa commit lúc ghi):**
    - **Nguồn gốc:** user muốn "chạy Confident Learning lấy lõi là LightGBM và Random Forest rồi kiểm tra xem LightGBM (boosting) hay Random Forest (bagging) tốt hơn", dùng cả bộ Car có đáp án (`car_noisy_5/10.csv` + `car_noise_ground_truth.csv`).
    - **File mới:** `evaluate_cl_rf_vs_lightgbm.py`, `data/cl_rf_vs_lightgbm_results.jsonl` (120 bản ghi), `data/cl_rf_vs_lightgbm_summary.md` — **CẢ 3 FILE ĐÃ BỊ XOÁ (23/11/2026, user bảo không cần giữ, chưa từng commit nên không khôi phục được)**; chỉ còn các con số ghi ngay dưới đây trong CLAUDE.md.
      Dùng lại ĐÚNG `_compute_class_thresholds` + `_find_confident_classes` của `class_noise/confident_learning.py` và cùng chia fold (StratifiedKFold 5 fold, `random_state=42`), chỉ thay mô hình sinh xác suất out-of-fold.
      Đã kiểm: đường tính với Random Forest ra đúng 70 dòng như `detect_class_noise` trên Car 5% (giống hệt tập dòng).
    - **4 cấu hình khai báo TRƯỚC khi chạy (không chỉnh theo kết quả):** `RF` (300 cây, `min_samples_leaf=5`, không bù lớp = mặc định web); `LGBM_default` (mặc định LightGBM: 100 vòng, lr 0,1, 31 lá, min_child_samples 20);
      `LGBM_leaf5` (min_child_samples=5, tương ứng leaf 5 của RF); `LGBM_slow` (lr 0,05, 8 lá, 100 vòng). **LightGBM có 3 cấu hình, RF chỉ 1** nên số chính nên lấy từ `LGBM_default` (chưa chỉnh gì); RF cũng CHƯA được chỉnh thêm (leaf 10/20, `max_features`).
    - **Bộ dữ liệu:** `car_given` (2 file nhiễu cho sẵn, 4 nhãn, mỗi file chỉ 1 lần cấy); `car_multi` (car_clean 4 nhãn, nhiễu 5%/10% đổi sang 1 nhãn khác đều ngẫu nhiên, 5 seed); `adult`, `thay`, `creditcard` (mẫu 30.000 dòng, 2 lớp, nhiễu A 10% và B 30%, 3 seed).
    - **Kết quả (28 ô nhiều seed, không tính 2 file Car cho sẵn), RF − LightGBM, kiểm định Wilcoxon bắt cặp:** F1: so `LGBM_default` −0,041 (RF kém ở 21/28 ô, p = 0,0011), so `LGBM_leaf5` −0,045 (21/28, p = 0,0065), so `LGBM_slow` −0,080 (26/28, p < 0,0001).
      **Xếp hạng gần như NGANG:** AP so default −0,004 (p = 0,31), so leaf5 +0,001 (p = 0,85); P@K ≈ 0 ở cả hai (p ≥ 0,49); chỉ `LGBM_slow` hơn có ý nghĩa về AP (−0,016, p = 0,0004). Recall RF thấp hơn (−0,043 so default), Precision cũng thấp hơn nhưng p = 0,05 so default, 0,23 so leaf5.
      => LightGBM thắng chủ yếu ở LUẬT CẮT (danh sách gắn cờ chính xác hơn: vd Adult A10% RF cờ 4.462 dòng Precision 0,41, LightGBM ~3.990 dòng Precision 0,46), KHÔNG phải ở khả năng xếp hạng dòng đáng ngờ. Giải thích "xác suất của boosting hiệu chỉnh tốt hơn nên ngưỡng tự tin chia tốt hơn" chỉ là GIẢ THUYẾT, chưa kiểm.
    - **Hai file Car cho sẵn (1 lần cấy mỗi file):** 5%: F1 RF 0,713 (tìm đúng 56/86), `LGBM_default` 0,830 (66/86), leaf5 0,783, slow 0,768; 10%: RF 0,768, default 0,746, leaf5 0,750, slow 0,773 (gần như hoà). Car 5 seed trung bình: 5% RF 0,733 / default 0,815 / leaf5 0,828 / slow 0,752; 10% RF 0,756 / default 0,769 / leaf5 0,777 / slow 0,778. Gợi ý nhãn đúng (`fix_accuracy`) ~0,98–1,0 ở mọi mô hình.
    - **KHÔNG phải ô nào LightGBM cũng thắng:** Credit Card B 30%: RF F1 0,841 và AP 0,772, hơn default (0,806 / 0,724) và leaf5 (0,769 / 0,687), chỉ `LGBM_slow` hơn về F1 (0,851); RF dẫn AP ở 5/6 ô Credit Card. thay B 30%: RF 0,456 hơn default (0,437) và leaf5 (0,414), kém slow (0,506).
      Cấu hình LightGBM tốt nhất đổi theo bộ dữ liệu (slow tốt nhất ở thay và Credit Card A, default/leaf5 ở Car và Adult). Credit Card A 10%: slow 0,803, default 0,638, RF 0,559.
    - **Tốc độ:** LightGBM nhanh hơn nhiều (Car 1,1 giây so với 4,6; Adult 0,6 so với 7,9; thay 0,5 so với 9–12; Credit Card 1,2 so với ~55–64 giây).
    - **Hạn chế khi trích dẫn:** nhiễu cấy ngẫu nhiên (A, B; nhiễu phụ thuộc đặc trưng chưa thử); 3 seed mỗi ô lớn, 5 seed Car; các ô cùng một bộ không độc lập hẳn nên p chỉ là gợi ý; 4 cấu hình khai báo trước nhưng không có tìm kiếm siêu tham số cho cả hai bên; chỉ 4 bộ dữ liệu, mẫu con 30.000 dòng.
    - **Cài đặt:** môi trường chạy cần `lightgbm` (đã cài 4.7.0) và `tabulate` (chỉ cho `--summarize`); CHƯA thêm vào `requirements.txt` vì web chưa dùng LightGBM. Nếu sau này đưa LightGBM vào `confident_learning.py` / web thì phải thêm.
    - **Chưa làm:** thêm tham số chọn mô hình nền vào `ClassNoiseConfig` / web; thử RF với `min_samples_leaf` 10/20 và `max_features`; kiểm tra giả thuyết về hiệu chỉnh xác suất (vd so log-loss / đường cong hiệu chỉnh của hai mô hình); nhiễu phụ thuộc đặc trưng.

47. **Dọn repo: xoá toàn bộ script `demo*.py` và `evaluate*.py` ở thư mục gốc — ĐÃ XOÁ (23/11/2026), chưa commit lúc ghi:**
    - **Nguồn gốc:** user hỏi 2 nhóm file này là gì rồi bảo "xoá hết các file có chữ demo và evaluate". Web (`app.py`, `accounts/`, `attribute_noise/`, `class_noise/`, `converters/`, `frontend/`) KHÔNG import file nào trong số này; đã kiểm `python3 -c "import app"` vẫn chạy.
    - **Đã xoá (25 file):** `demo.py` + 9 file `demo_*.py` (ablation_3features, class_noise, class_noise_feature_selection, decision_tree_tu_viet, kaggle_comparison, model_don_gian, random_forest_ra_gi, random_forest_tu_viet, test_accuracy);
      15 file `evaluate_*.py`: `adult_categorical_importance`, `adult_categorical_vs_numeric`, `adult_official_uci_split`, `attribute_detectors`, `class_noise_multiseed` (harness mục 5/7), `class_noise_reduced_features`, `class_noise_richer_datasets`,
      `class_noise_synthetic`, `class_noise_train_test`, `creditcard_noise_injection` (mục 38), `distance_train_test`, `distance_vs_confident`, `distance_vs_confident_creditcard`, `ensemble_vs_others`, `cl_rf_vs_lightgbm` (mục 46; file này CHƯA từng vào git nên không khôi phục được từ lịch sử).
      24 file đã nằm trong git (khôi phục bằng `git checkout <commit-trước-khi-xoá> -- <tên file>`).
    - **Hệ quả cho các mục cũ (đừng đọc nhầm):** mọi chỗ trong file này nhắc tới các script trên (mục 5, 7, 10, 11, 35, 36, 38, 46, phần "Kế hoạch cải tiến Class Noise", dòng `demo.py` ở mục kiến trúc) chỉ còn là LỊCH SỬ: các con số vẫn đúng nhưng script sinh ra chúng không còn trong repo;
      không thể chạy lại thí nghiệm mục 5/7/38/46 từ repo này nữa (muốn thì phải lấy lại script từ lịch sử git, riêng `evaluate_cl_rf_vs_lightgbm.py` không có trong git).
    - **Còn lại và bị ảnh hưởng:** `analyze_class_noise_same_k.py` import từ `evaluate_class_noise_multiseed` (đã xoá) nên KHÔNG chạy được nữa; `summarize_class_noise_multiseed.py` chỉ đọc file `data/class_noise_multiseed_v2.jsonl` nên vẫn chạy.
      Các file kết quả vẫn giữ: `data/class_noise_multiseed_v2.jsonl`, `data/class_noise_experiment_summary.md`, `data/creditcard_noise_experiment_results.jsonl` (2 file `cl_rf_vs_lightgbm_*` của mục 46 đã xoá theo ý user).
    - **Sau đó user bảo xoá luôn** `data/demo_attribute_noise_2000.csv/.xlsx/_ground_truth.csv` + `data/DEMO_ATTRIBUTE_2000.md` (bộ DEMO bảo vệ, mục 39): ĐÃ XOÁ. Muốn có lại thì sinh lại bằng `SCALE=3.62 OUT_NAME=demo_attribute_noise_2000 python3 data/generate_test_attribute_noise.py` (script còn, hạt giống cố định nên ra đúng file cũ; tài liệu `DEMO_ATTRIBUTE_2000.md` thì lấy từ lịch sử git). Các mục 39, 46 và mục `data/` ở đầu file nhắc tới các file này chỉ còn là lịch sử.

48. **Class Noise trên web chỉ còn MỘT cách phát hiện: "Phát hiện nhãn sai" = bộ kết hợp Confident Learning + Mutual k-NN — ĐÃ XONG (23/11/2026), ĐÃ TEST (chưa commit lúc ghi):**
    - **Nguồn gốc:** user chốt "sửa bước PHÁT HIỆN của Class Noise trên web thành MỘT lựa chọn duy nhất 'Bộ kết hợp'" (4 việc: giao diện chọn phương pháp, backend, màn hình kết quả, chữ hướng dẫn).
      Công thức gộp điểm và luật chọn K CHƯA chốt (sẽ chốt sau thực nghiệm) nên KHÔNG đổi lần này, chỉ tách ra 1 hàm để sau đổi dễ.
    - **Giao diện bước chọn (`workspace.html`, `workspace-flow.js`, `workspace.css`):** bỏ 4 thẻ phương pháp + khung "02 · Phương pháp phát hiện" (bước 1 còn đúng 1 khung "01 · File của bạn", lớp `.convert-grid--single` cho khung trải hết hàng;
      nhãn thanh bước 1 = "Tải file", tiêu đề "Tải dữ liệu"; tải lên KHÔNG còn đòi chọn phương pháp); bỏ khối 2 nút "Giảm số cột / Không giảm số cột" và 4 khối tham số (k, "Cách kết hợp", số cây, fold) + dòng
      "có thể mất vài phút" tĩnh; nút `#class-detect-btn` = "Phát hiện nhãn sai →" luôn gửi `{method:"combined", reduce_columns:false}` (KHÔNG gửi k / alpha / n_estimators). Lúc chạy hiện đúng câu
      "Đang chạy Mutual k-NN và Confident Learning, có thể mất vài phút với file lớn…" (chạy ĐỒNG BỘ, chưa có chạy nền / thanh tiến độ). Bước chuẩn bị chung (không dùng nhãn) vẫn chạy ở backend và vẫn có thẻ báo cáo.
      Đã xoá hẳn khỏi JS (còn trong git, commit `ce34446`): `state.classMethod`, `state.classResultMethod`, các hàm hiển thị riêng Distance / Ensemble / Single learning, `CLASS_SCORE_LABELS`, `classReduceChosen`, `CLASS_METHOD_LABELS`;
      khỏi CSS: các luật `.method-grid`, `.reduce-choice`.
    - **Backend:** `class_noise/combined.py` (xem bullet kiến trúc: `methods`, `merge_scores_and_select_k`, `method_findings`); `class_noise/web_adapter.py` (`method_list_json`, `COMPONENT_LABELS`); `app.py`: nhánh `combined` dùng mặc định
      k = 5 (`_neighbors_from_payload()`, dùng chung với nhánh `distance_based`: không gửi `k` = 5, `null` / `""` / `"auto"` = tự chọn theo độ phủ), alpha = 0, n_estimators = 100, KHÔNG chạy Ensemble. KHÔNG xoá `ensemble_based.py`,
      `ensemble_diverse.py`, các nhánh `single_learning` / `distance_based` / `ensemble_based` của route (mặc định khi không gửi `method` vẫn là `single_learning` như cũ), route `/api/class-noise/reduce-features`.
    - **Response mới của `combined`:** `method_findings` = {`single_learning`: [...], `distance_based`: [...]} — danh sách RIÊNG của từng phương pháp (dòng chính nó tự gắn cờ, mỗi dòng `row_number`, `recorded_label`,
      `suggested_label`, `score` = điểm nghi của chính nó: Confident Learning = 1 − xác suất mô hình cho nhãn ghi, Mutual k-NN = tỉ lệ láng giềng lẫn nhau khác nhãn; xếp giảm dần; đã mở ra cả nhóm dòng trùng như danh sách kết hợp, có
      `duplicate_of`); `diagnostics.methods[m].n_flagged_rows` (số dòng đó tính cả bản trùng; `n_flagged` giữ nghĩa cũ); `diagnostics.quality` = None nếu bộ không có mô hình nào; câu nhận xét khi Confident Learning bị loại ghi tên
      "Confident Learning (Random Forest)" và "chỉ dựa vào Mutual k-NN". `diagnostics.ensemble` / `ensemble_disagreement` chỉ có khi gọi `detect_class_noise_combined` với Ensemble (web không gọi).
    - **Màn hình kết quả (bước 3/4):** phần chính = 2 thẻ (dòng dùng được, dòng nghi sai nhãn) + khung cảnh báo (GIỮ NHƯ CŨ, gồm dòng "Bộ kết hợp là phương pháp thử nghiệm…" + nhận xét theo mức vượt mốc + cảnh báo của backend) + thẻ báo cáo bước chuẩn bị
      (giữ như cũ) + bảng danh sách kết hợp (Dòng / Nhãn ghi / Nhãn gợi ý / Điểm kết hợp / Cùng nghi). Bỏ bảng precision/recall và ma trận đếm. Nút `#class-more-btn` "Xem thêm ▾" (mặc định ĐÓNG, `aria-expanded`, đóng thì không dựng gì)
      mở `#class-more-panel` gồm: (a) bảng "Mức tin cậy" (mỗi phương pháp: mức vượt mốc + CV accuracy + mốc đoán bừa của Confident Learning, độ phủ + k của Mutual k-NN, trọng số, Đang dùng / Bị loại + lý do, số dòng tự gắn cờ);
      (b) danh sách riêng Confident Learning; (c) danh sách riêng Mutual k-NN — mỗi danh sách 10 dòng/trang, có cột điểm nghi của chính phương pháp, phương pháp bị loại có ghi chú "chỉ để tham khảo". Thứ tự: bảng chính → Xem thêm → "Tiếp tục".
    - **Bước Xử lý:** dùng danh sách KẾT HỢP (không đổi); cột hiện "Nhãn gợi ý" / "Điểm kết hợp". Dòng không có nhãn gợi ý: không có lựa chọn "(gợi ý)", gán hàng loạt "Sửa nhãn theo gợi ý" bỏ qua (như mục 45). **Sửa kèm:** lời báo sau khi gán hàng loạt
      trước đây ghi tổng số dòng khớp dù đã bỏ qua dòng không có gợi ý; nay ghi đúng số đã gán + "bỏ qua N dòng không có nhãn gợi ý" (báo lỗi nếu gán được 0 dòng).
    - **Chữ hướng dẫn:** trang chủ ("2 phương pháp gộp", "gộp hai phương pháp", bảng thông số), menu, Guide mục 06 viết lại 4 bước (Tải file → Nhãn & đặc trưng → Kết quả có "Xem thêm" → Xử lý); **sửa kèm** câu sai từ trước
      "Xử lý: chưa có xử lý tự động" (bước Xử lý đã có từ mục 37).
    - **Kiểm chứng (script ở thư mục tạm, KHÔNG nằm trong repo):** (1) `combine_methods` mới = bản cũ (lấy từ git) từng trường trên 600 cấu hình ngẫu nhiên (có NaN, hoà điểm, cổng bật/tắt, alpha 0 / 0,25 / 0,5 / 1, có / không nhãn ghi) và
      `detect_class_noise_combined` 3 phương pháp trên Car 5% = bản cũ từng dòng; mặc định = gộp tay Confident Learning + Mutual k-NN; Ensemble không chạy khi không chọn (38 kiểm tra đạt); (2) Flask test client 64 kiểm tra (cấu trúc response,
      mặc định k = 5 / alpha = 0 / n_estimators = 100, `k=null` → auto, các method khác vẫn 200, file có dòng trùng, đặc trưng vô nghĩa → Confident Learning bị loại + cảnh báo đỏ, `_combined_json` với 3 / 1 phương pháp, JSON không NaN);
      (3) Playwright trình duyệt thật 98 kiểm tra (không còn thẻ / ô tham số, request đúng, lời báo đang chạy, bảng chính, "Xem thêm" mở / đóng / phân trang / điểm khớp response, dòng không có gợi ý, cảnh báo đỏ, chạy lại không giữ Xem thêm cũ,
      bước Xử lý đổi nhãn + xác nhận + hoàn tác + xoá + xuất CSV đúng số dòng, chuyển dữ liệu từ chuỗi tool sang Class Noise); (4) chụp ảnh xem bố cục các bước 1–4. Không lỗi JS.
    - **Dọn chữ giao diện (23/11/2026, sau commit `effdeca`):** khung lưu ý đầu Class Noise rút còn 1 câu; mô tả bước chọn nhãn chỉ còn "Chọn cột làm nhãn và các cột số làm đặc trưng."; bỏ 3 mục góc phải
      (Chạy trên Backend Flask / Thuật toán / Bản gốc) của khối Class Noise (các tool khác vẫn còn `.ft-meta` riêng); bỏ dòng "Đã kết nối backend Flask." dưới ô tải file (`#upload-notice` ẩn sẵn, chỉ hiện khi MẤT kết nối);
      bỏ dòng cảnh báo "Bộ kết hợp là phương pháp thử nghiệm…" ở màn kết quả (khung cảnh báo vẫn hiện khi mức vượt mốc thấp / `diag.warnings`, tự ẩn nếu không có gì); bỏ 2 dòng chân trang
      ("Riêng tư theo tài khoản…", "Xử lý qua backend Flask"), chỉ còn "Denoise · khoá luận tốt nghiệp 2026". Cũng bỏ: dòng "Nhãn có thể bị gán sai? 2 phương pháp gộp, 4 bước" trong thẻ Class Noise của menu Product, và dải 3 nhãn bo tròn (`.convert-badges`: "Khai cột & tham số / Xem lỗi trước khi sửa / Xử lý qua backend thật", "Không cần cấu hình / Cần đăng nhập / …", "Kết quả tức thì / …") ở đầu 3 nhóm tool (CSS `.convert-badge*` còn trong file nhưng không dùng nữa). Sau đó bỏ luôn cụm 3 mục góc phải (`.ft-meta`: Chạy trên Backend Flask / Hai nhịp / Giá / Đăng nhập bắt buộc) ở 3 trang tool (Tự động, Cần cấu hình, Convert); `.ft-meta` của Guide / Bảo mật / Quyền riêng tư / Hồ sơ giữ nguyên. Commit `ffc53d7`. Trang chủ, lưới "Bắt đầu từ một tool nhỏ": bỏ chữ "Bấm là chạy" ở góc phải và dòng chú thích nhỏ trong 8 ô (chỉ còn nhãn nhóm, tên tool, mũi tên); chú thích nhỏ trong MENU Product giữ nguyên. Cũng bỏ: chữ "Không tự sửa khi chưa hỏi" ở góc phải mục "Bốn bước, bạn giữ quyền quyết định" và nhãn "Free Tools / Cần cấu hình / Class Noise" ở đáy 9 thẻ "Denoise sửa được gì" (nhãn "9 loại lỗi" giữ nguyên). Commit `8e4faeb`. Form đăng nhập / đăng ký: bỏ chữ "Xử lý qua backend Flask" ở góc trên nửa phải (xoá `.ws-auth-right-top` trong HTML, luật CSS còn nhưng không dùng) và bỏ dòng "Tải lên, làm sạch và xuất file." dưới tiêu đề "Tạo tài khoản" (`setAuthMode()` trong `workspace.js` ẩn `#ws-auth-desc` ở chế độ đăng ký; chế độ đăng nhập vẫn có "Tiếp tục việc đang dở."). Chưa commit lúc ghi.
    - **Giới hạn / việc nợ:** chạy đồng bộ, chưa chạy nền / thanh tiến độ; danh sách riêng trả về ĐẦY ĐỦ trong response (file rất nhiễu có thể hàng chục nghìn dòng mỗi danh sách); dòng cảnh báo "thử nghiệm" vẫn còn trên màn kết quả
      (hỏi user có muốn bỏ không); công thức gộp điểm + luật chọn K chưa chốt (`merge_scores_and_select_k`); mục "Giảm số cột theo nhãn" chỉ còn là tham số của route (`reduce_columns`), giao diện không dùng.

49. **Lỗi "mới chạy web phải tải file lần thứ 2 mới được" — ĐÃ TÌM RA NGUYÊN NHÂN VÀ SỬA (23/11/2026, chưa commit lúc ghi):**
    - **Nguyên nhân (tái hiện được bằng Playwright):** `app.secret_key` trước đây `os.urandom(32)` mỗi lần khởi động, mà `app.run(debug=True)` TỰ KHỞI ĐỘNG LẠI mỗi khi 1 file `.py` đổi (vd sau `git pull`)
      hoặc khi user bật lại `python3 app.py` -> cookie đăng nhập cũ hết hiệu lực. Trang đang mở / cookie cũ gọi `/api/upload` ra 401 "Cần đăng nhập trước" chỉ hiện chữ dưới nút, KHÔNG hiện form đăng nhập
      (frontend không xử lý 401 ở đâu cả) nên phải tải lại trang + đăng nhập rồi tải lần 2. Đây là "giới hạn đã biết" ghi ở mục 14 nhưng hoá ra gây khó chịu thật.
    - **Sửa 3 chỗ:** (1) `app.py::_load_secret_key()`: lấy từ `SPARK_SECRET_KEY`, không có thì từ file `.spark_secret_key` ở gốc repo (tự tạo lần đầu bằng `O_EXCL` vì Flask debug nạp app.py ở 2 tiến trình; quyền 600;
      đã thêm vào `.gitignore`), không ghi được file thì key ngẫu nhiên như cũ -> đăng nhập GIỮ qua các lần restart. (2) `workspace.js`: bọc `window.fetch` (dùng chung cả `workspace-flow.js`): gặp 401 ở `/api/*` (trừ `/api/auth/*`)
      khi đang đăng nhập thì `handleSessionExpired()` đưa về form đăng nhập kèm lời "Phiên đăng nhập đã hết hạn (có thể do server vừa khởi động lại)", đăng nhập xong quay lại đúng khối, file đã chọn vẫn còn.
      (3) `workspace-flow.js::updateUploadButtonState()`: nút "Tải lên & tiếp tục" của Class Noise chỉ cần đã chọn file (trước còn đòi `backendAvailable` từ lần kiểm tra kết nối chờ tối đa 1,5 giây -> server chậm lúc mới bật thì nút bị khoá).
    - **Bỏ dòng ghi chú dưới bảng xem trước (23/11/2026):** "Xem trước 100/114 dòng đầu · 10 cột đã đọc được." đã bỏ ở Free Tools, Cần cấu hình, Convert và Class Noise (`workspace.js`, `workspace-flow.js`); số "N dòng × M cột" ở đầu bảng giữ nguyên. Các ghi chú khác (đang đọc file, không xem trước được, file JSON) vẫn hiện. Chưa commit lúc ghi.
    - **Bỏ biểu tượng cờ ⚑ (23/11/2026):** ở lời báo kết quả nút "Phát hiện" của các tool Cần cấu hình ("4 ô lỗi ở 1 cột · 4 dòng (tổng 114)…"), 2 chỗ trong `workspace.js`. Chưa commit lúc ghi.
    - **Việt hoá chữ trên giao diện (23/11/2026, chưa commit lúc ghi):** chỉ đổi CHỮ HIỂN THỊ, không đổi id / class / khoá (`data-section="free-tools"`, `data-tool`, `"cross-rule"`, `"delimiter"`... giữ nguyên).
      Bảng đổi: Guide -> Hướng dẫn, Home -> Trang chủ, Product -> Sản phẩm, Free Tools -> Tự động, Convert -> Chuyển đổi (cả nút chạy, `callBackend(..., "Chuyển đổi", ...)`, nhãn "Xong · xử lý tiếp bằng"),
      delimiter -> dấu phân cách (tab "Đổi dấu phân cách CSV", các nhãn ô, lời báo trạng thái; bỏ "(FROM)" / "(TO)"), Rule liên cột -> Quy tắc liên cột (tab, menu, Guide, Riêng tư, nhãn `rule:*` của luồng cũ),
      "Dòng đầu là header" -> "Dòng đầu là tên cột", "Nhóm (category)" -> "Nhóm", "Đang upload..." -> "Đang tải lên…", "đã upload" -> "đã tải lên", `<title>` -> "Denoise — Làm sạch dữ liệu".
      GIỮ NGUYÊN: Denoise, Class Noise, CSV / JSON / Excel / Objects / Arrays, IQR, Z-score, outlier, Confident Learning, Mutual k-NN, Cookie, Tracker, Backend Flask (bảng công nghệ), tên cột / giá trị trong dữ liệu mẫu.
      Chữ "tool" (vd "Bắt đầu từ một tool nhỏ", "Chọn tool") và từ "backend" trong câu giải thích CHƯA đổi. Chạy quét từng khối bằng trình duyệt: không còn chữ Anh trong danh sách trên. **Sau đó đổi luôn "Class Noise" -> "Nhãn sai" ở chữ hiển thị** (menu, thẻ trang chủ, bảng công nghệ, Hướng dẫn, Riêng tư, thanh đường dẫn, chân trang, nút "Xong · xử lý tiếp bằng"; thẻ menu thành "Nhãn / sai"); key `data-section=\"class-noise\"`, id `section-class-noise` và tên module `class_noise` giữ nguyên. Các chỗ trong CLAUDE.md nói "Class Noise" vẫn là tên kỹ thuật của hướng này. Lưu ý khi viết lại bằng regex: dùng `>([^<>]*)(?=<)` (lookahead), không dùng `<` thường vì bỏ sót text node nằm liền nhau.
      Backend: thông báo duy nhất còn tiếng Anh ("Unsupported file type") đã dịch ở `attribute_noise/pipeline.py::load_data`; `/api/upload` giờ trả 400 kèm lý do tiếng Việt khi file sai định dạng / rỗng (trước ra 500 không nội dung).
    - **Còn lại (không sửa):** dữ liệu file nằm trong RAM nên restart server vẫn mất `file_id` đang làm dở (các bước sau báo không tìm thấy file, phải tải lại); đổi mật khẩu/`SPARK_SECRET_KEY` hoặc xoá `.spark_secret_key` sẽ đăng xuất mọi người (đúng ý).
    - **Kiểm chứng:** Playwright: (a) mở trang + chọn file, restart server, bấm Tải lên: trước sửa 401 không form, sau sửa tải lên thành công ngay lần đầu; (b) ép đổi key bằng biến môi trường: hiện form + lời giải thích, đăng nhập lại về Class Noise,
      file vẫn chọn, tải lên được; (c) luồng khách -> đăng ký -> Free Tools chạy lần đầu bình thường; chạy lại bộ kiểm tra giao diện Class Noise 96 đạt (2 mục "lỗi" còn lại do bài kiểm tra cũ vẫn mong chữ đã bỏ).

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
- [x] Bộ dữ liệu test toàn diện `data/test_all_noise.*` + kịch bản thao tác `data/KICH_BAN_TEST.md` + sửa 4 lỗi nhỏ tìm được — xem mục 33.
- [x] Phụ thuộc hàm: 1 cột xác định → nhiều cột phụ thuộc, đoán ô sai (so các cột còn lại), 2 cách xử lý
      "Sửa về giá trị phổ biến nhất" / "Chỉ xoá dòng nghi sai" + xem trước (mục 23, commit `3ee977f`, `73978bc`).
- [x] Rule liên cột ĐỢT 1: tab "Biểu thức" thay So sánh + Công thức (mục 24).
- [x] Rule liên cột ĐỢT 2: Nếu–thì chạy chung bộ máy biểu thức (2 ô NẾU/THÌ đầy đủ), `=>`, `<=>`, `có(cột)`, mặc định
      "— Chọn cách xử lý —" + xem trước cho mọi rule liên cột (mục 25).
- [x] Chốt bộ dữ liệu = Credit Card Fraud (nguyên bộ) + gỡ One-Hot khỏi web — xem mục 35.
- [x] Thí nghiệm cấy nhiễu có kiểm soát trên Credit Card nguyên bộ (3 phương pháp, 2 kiểu nhiễu, 2 bộ cột, đo thời gian) — ĐÃ CHẠY, xem mục 38. Còn thiếu: nhiều seed, nhiễu phụ thuộc đặc trưng.
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
- [x] Class noise — HANDLE (mục 37): 3 cách xử lý (giữ / xoá / sửa nhãn theo gợi ý hoặc sang nhãn khác đã có), gán hàng loạt theo
      hướng + ngưỡng mức đáng ngờ, chạy thử + hộp xác nhận + cảnh báo lớp hiếm, hoàn tác 5 bước, về dữ liệu gốc, xuất CSV, phát hiện
      lại trên bản đã xử lý (cách B). Chưa làm: "mức tin cậy cao" (dòng cả 3 thuật toán cùng gắn cờ), xem trước dữ liệu sau xử lý.
- [x] One-Hot Encoding cho cột CHỮ làm đặc trưng Class Noise — ĐÃ LÀM RỒI ĐÃ GỠ KHỎI WEB (mục 35): user chốt dùng
      Credit Card (toàn số) nên không cần encode; cột chữ ghi là HẠN CHẾ + hướng phát triển. Module
      `class_noise/categorical_encoding.py` + các script `evaluate_adult_*` GIỮ LẠI làm mã nghiên cứu, `app.py` KHÔNG import nữa.
- [ ] (Khuyến nghị, chưa có yêu cầu code cụ thể) Đánh giá định lượng: tính
      precision/recall/F1 của 7 detector + rule liên cột so với
      `noise_ground_truth.csv`/`noise_ground_truth_large.csv` — rủi ro lớn
      nhất hiện tại cho điểm khoá luận là CHƯA có bước đánh giá định lượng nào.

## Kế hoạch cải tiến Class Noise (chốt 22/11/2026, theo góp ý của thầy) — THỨ TỰ

Mục tiêu: có đóng góp riêng ở 2 tầng (cải tiến từng phương pháp + bộ kết hợp), không chỉ gọi 3
phương pháp có sẵn. Mọi bước thiết kế cho BẤT KỲ bảng nào; bộ dữ liệu chỉ dùng để thực nghiệm.
Khung thí nghiệm nhiều seed `evaluate_class_noise_multiseed.py` (A/B/IDN, downstream, naive_cv) đã có
từ 21/11 — dùng lại, không viết mới.

**Việc của Quân**
- [ ] Q1. Gửi thầy tin nhắn chốt hướng (bản soạn sẵn trong chat).
- [x] Q2. Chốt bộ dữ liệu nhãn đúng 100% để cấy nhiễu có kiểm soát: Car Evaluation (UCI) — đã thêm
        `data/car_evaluation.csv`. (KEEL bị loại: bản nhiễu của KEEL không kèm file đáp án dòng nào bị đổi.)
- [ ] Q3. (Tùy) Tải bài gốc Mutual k-NN (Liu & Zhang 2012) qua thư viện trường.
- [ ] Q4. Cuối cùng: cập nhật mục lục, xuất PDF từ Word, đóng gói nộp.

**Việc của Claude (code), theo thứ tự**
1. Pipeline chuẩn bị chung, KHÔNG dùng nhãn — file mới `class_noise/preprocess.py`:
   - [x] chuẩn hoá cột nhãn (cắt khoảng trắng); báo lớp có ít dòng hơn số fold;
   - [x] loại dòng có ô trống ở cột đã chọn, báo rõ số dòng bị loại;
   - [x] bỏ cột hằng; cột gần như toàn ô trống (mặc định > 50%); cột định danh (số nguyên/chữ có
         ≥ 95% giá trị khác nhau — KHÔNG áp cho cột số thực);
   - [x] lọc tương quan |r| ≥ 0,8, chọn cột giữ KHÔNG dùng nhãn (ít ô trống hơn → ít tương quan với
         các cột khác hơn → đứng trước); viết lại `filter_correlated()`;
   - [x] (phần BACKEND xong; 2 nút trên giao diện còn ở mục 6) giảm số cột theo nhãn (Random Forest + điểm gãy, đúng bước 1 thầy yêu cầu) thành LỰA CHỌN của
         người dùng: 2 nút "Giảm số cột" / "Không giảm số cột", mặc định "Không giảm". Khi chọn "Giảm"
         mà mức vượt mốc của mô hình thấp hoặc lớp hiếm quá ít dòng → hiện cảnh báo nhãn có thể chưa đủ
         tin cậy để chọn cột theo nhãn;
   - [x] gom dòng trùng theo cột đặc trưng: nhóm khác nhãn → báo "dòng mâu thuẫn"; nhóm cùng nhãn →
         gộp 1 đại diện trước khi chạy, trả kết quả về cả nhóm.
   → ĐÃ CODE (22/11/2026, chưa nối vào web): `class_noise/preprocess.py` (`prepare_for_class_noise()`, `PreprocessConfig`,
     `PreparedData`, `PreprocessReport`) + `feature_selection.py::filter_correlated()` viết lại tại chỗ
     (`prioritized=False` = chọn cột KHÔNG dùng nhãn, `method="spearman"`, `return_report=True`; `prioritized=True` giữ
     đúng hành vi cũ nên `app.py`/các script cũ không phải đổi) + `order_columns_without_labels()`.
     Kiểm chứng: 37 kiểm tra đơn vị (nhãn, luật cột, lọc tương quan: cột giữ KHÔNG đổi khi xáo trộn nhãn, bản cũ = mới
     trên 20 bộ ngẫu nhiên, ô trống, nhóm trùng/mâu thuẫn, giảm cột theo nhãn + cảnh báo, lỗi, JSON) + chạy 4 bộ thật:
     Credit Card (6,2s; giữ đủ 30 cột, gộp 1.081 dòng trùng -> 283.726 dòng), Adult (bỏ 8 cột chữ; gộp 186 dòng; 40 nhóm
     mâu thuẫn/81 dòng), Car (không đổi gì), dữ liệu thầy (111 nhóm mâu thuẫn/7.409 dòng vì chỉ có 3 đặc trưng) + Distance chạy
     được trên dữ liệu đã chuẩn bị; route cũ `/api/class-noise/reduce-features` vẫn 200.
     Quyết định tạm (chưa chốt với Quân): `low_margin_warning` = 20% mức vượt mốc, `min_minority_rows` = 50, định danh chỉ xét
     từ 30 dòng; nhóm mâu thuẫn được GIỮ nguyên (không gộp). "Nhóm mâu thuẫn" KHÔNG đồng nghĩa chắc chắn sai nhãn: với
     Adult/dữ liệu thầy đặc trưng không đủ phân biệt nên cùng đặc trưng khác nhãn là bình thường (khác Car, nhãn sinh từ luật).
     Chưa làm: nối vào `/api/class-noise/detect` + giao diện (mục 6), mở rộng kết quả về cả nhóm trùng khi trả response.
2. Mutual k-NN (`class_noise/distance_based.py`) — ĐÃ CODE + TEST (22/11/2026, chưa nối vào web):
   - [x] z-score trừ cột nhị phân (cột 2 giá trị giữ 0/1);
   - [x] trả điểm bất đồng cho MỌI dòng (không chỉ dòng > 0,5);
   - [x] chọn k theo độ phủ: tìm láng giềng 1 lần với k = 15, lấy k nhỏ nhất trong {3,5,7,9,11,15}
         đạt ngưỡng độ phủ (mặc định 90%); người dùng vẫn sửa tay được;
   - [x] biến thể để đo: bỏ phiếu theo khoảng cách, khoảng cách Manhattan, PCA (tự bật khi số thành
         phần giữ 95% biến thiên < 1/2 số cột) — đã có tham số `weighting` / `metric` / `pca`;
   - [ ] có/không kéo biên + log: hàm detect KHÔNG tự kéo biên/log, do nơi gọi quyết định (web, bộ thí nghiệm) → đo ở mục 5.
   Kiểm chứng: 56 kiểm tra đơn vị đạt (giống bản cũ khi tham số mặc định trên 3 bộ ngẫu nhiên; điểm MỌI dòng khớp cài đặt độc lập bằng
   ma trận khoảng cách đầy đủ cho cả 4 tổ hợp euclid/manhattan × đếm/theo khoảng cách; bất biến mã hoá nhị phân; công thức trọng số;
   PCA tự bật/tắt đúng; `k="auto"` khớp k nhỏ nhất khi chạy k cố định từng giá trị; điểm trùng hệt; index gốc; tham số sai). Trên Car
   (`car_noisy_5/10.csv` + `car_noise_ground_truth.csv`) bản mới = bản cũ TỪNG DÒNG ở k=5 và k=7 (không hồi quy).
   **Số đo thật (22/11/2026, sau cap outlier + log như web):** Credit Card 284.807 dòng × 30 cột: k=5 mất 73,4 giây (bản cũ ~82–87 giây),
   96 dòng gắn cờ, độ phủ 92,4% (đúng số đã ghi ở mục 38); `k="auto"` thử k=3 (độ phủ 84,1% < 90%) rồi k=5 (92,4%) → chọn 5, 78,3 giây.
   Dữ liệu thầy 588.393 dòng × 3 cột: k=5 mất 9,0 giây (độ phủ 97,3%, 14.351 dòng gắn cờ), `auto` chọn k=3 (độ phủ 94,2%, 15.134 dòng).
   Car 5% (có đáp án, 86 dòng cấy): k=5 → 141 dòng cờ, tìm 84/86; k=7 → 162 dòng, 85/86; theo ngưỡng điểm (k=7): > 0,5 → 52% đúng,
   ≥ 0,8 → 91% (72/79), = 1,0 → 100% (59/59). Biến thể weighting/manhattan/PCA/keep_binary khác k=7 mặc định chỉ vài dòng (TP 85–86).
   **Hai phát hiện cần nhớ:** (1) `k="auto"` theo ĐỘ PHỦ chỉ chọn k nhỏ nhất đạt 90% nên trên dữ liệu dày (Car, độ phủ ~99% ngay ở k=3)
   luôn ra k=3 và KÉM hơn k=5/7: Car 5% Precision 0,40 (198 dòng cờ, 80/86) so với 0,60 ở k=5 và 0,52 ở k=7. Độ phủ chỉ đảm bảo "đủ láng giềng
   lẫn nhau để kết luận", KHÔNG đảm bảo độ chính xác; chưa đổi luật (đúng kế hoạch), cần đo ở mục 5 trên nhiều bộ + nhiều seed, và KHÔNG chọn
   luật bằng cách nhìn đáp án của đúng file đang đánh giá (peeking). Ứng viên luật: k tối thiểu 5, hoặc đòi mỗi dòng có >= 2 láng giềng lẫn nhau.
   (2) Car là lưới rời rạc nên 83% số dòng (1440/1728 ở k=7) bị HOÀ khoảng cách ở ranh giới top-k; láng giềng nào lọt top-k khi hoà là tuỳ
   thứ tự nội bộ của sklearn. Lặp lại được trên cùng máy/phiên bản nhưng không "chắc chắn theo toán học"; khi báo cáo số trên Car nên nói rõ.
3. Confident Learning (`class_noise/confident_learning.py`) — ĐÃ CODE + TEST (22/11/2026, chưa nối vào giao diện):
   - [x] bỏ kéo biên/log khỏi nhánh CL (mô hình cây không cần) — làm ở NƠI GỌI (`app.py`, `run_class_noise.py`); hàm detect vốn không cap/log;
   - [x] Random Forest thêm `min_samples_leaf` (mặc định 5) + tham số số cây; tuỳ chọn bật/tắt `balanced` (mặc định tắt);
   - [x] trả mức vượt mốc, MCC, PR-AUC; trả điểm nghi ngờ MỌI dòng (1 − xác suất nhãn ghi);
   - [x] hiệu chỉnh ma trận đếm → ước lượng tỷ lệ nhãn sai (theo bài gốc Northcutt 2021);
   - [x] sửa docstring "dòng thật sự thuộc lớp" → "dòng mang nhãn lớp".
   **Kiểm chứng:** 45 kiểm tra đơn vị (với `min_samples_leaf=1, balanced=True` = bản cũ từng dòng, từng margin; vector hoá = vòng lặp cũ kể cả hoà phiếu;
   điểm/chỉ số tính lại độc lập bằng sklearn; hiệu chỉnh ma trận đếm khớp ví dụ tính tay; ước lượng nhiễu), 16 kiểm tra route `/api/class-noise/detect`
   qua Flask test client (cả 3 phương pháp khớp gọi hàm trực tiếp), CLI chạy được.
   **Số đo (cấy nhiễu có kiểm soát; kịch bản A = đảo đồng đều, B = đảo lớp hiếm ↔ lớp đông; 3 seed; 100 cây; Credit Card = MẪU 492 gian lận + 30.000
   dòng bình thường = 30.492 dòng, cap tính trên cả file rồi mới lấy mẫu; Adult = 6 cột số):**
   · *Cap/log có cần cho CL không?* F1 raw / cap / cap+log: Credit Card B10 0,785 / 0,779 / 0,778; B30 0,808 / 0,810 / 0,811; A5 0,449 / 0,446 / 0,445;
     Adult A10 0,434 / 0,433 / 0,432; A30 0,561 / 0,562 / 0,562; Car y hệt nhau — độ lệch chuẩn giữa seed 0,002–0,027 nên KHÔNG khác biệt đo được → bỏ.
     (Trên Car: cùng tập dòng gắn cờ và cùng accuracy, nhưng xác suất lệch tối đa 0,011 giữa raw và cap+log; nguyên nhân CHƯA tìm, chưa kiểm giả thuyết log làm tròn 4 số lẻ.)
   · *Chọn `min_samples_leaf` × `balanced`* (F1 trung bình 3 seed; "mặc định cũ" = leaf 1 + bật bù; mặc định mới = leaf 5 + tắt bù):
     Credit Card A5 0,715 (mới) so với 0,449 (leaf 5 + bù) và 0,519 (leaf 1 + bù); B10 0,782 / 0,785 / 0,786; B30 0,834 / 0,808 / 0,815;
     Adult A10 0,483 / 0,434 / 0,354; A30 0,576 / 0,560 / 0,490; Car 5% 0,713 / 0,573 / 0,720; Car 10% 0,765 / 0,629 / 0,624 (Car 1 lần cấy, không seed).
     Mặc định mới tốt nhất hoặc trong vòng dao động của tốt nhất ở cả 7 kịch bản. **Không đúng cho mọi `leaf`:** với leaf=1, Credit Card B10 bật bù
     lại tốt hơn (0,786 so với 0,740). Kết luận chỉ cho mặc định leaf=5.
   · *Ước lượng tỷ lệ nhãn sai* (mặc định mới): dữ liệu tổng hợp tách rõ 0 / 5 / 10 / 20% → 0,0 / 5,3 / 10,0 / 20,6%; Credit Card A5 5,3% (thật 5,0%), B10 0,4%
     (0,3%), B30 1,1% (1,0%); Car 5,4% (4,98%) và 11,2% (10,0%). **Lệch cao khi đặc trưng yếu:** Adult A10 21% (thật 10%), A30 41% (30%) — mô hình sai
     và nhiễu sẵn có của Adult đều bị tính là nhãn sai. Dùng cùng "mức vượt mốc": chỉ đáng tin khi mức vượt mốc cao; coi là cận trên.
   **Chưa làm / việc nợ:** `evaluate_class_noise_multiseed.py` vẫn cap + log một lần cho CẢ 3 phương pháp (dòng ~85) nên đưa dữ liệu đã cap/log cho CL —
   không hại (đã đo bằng nhau) nhưng không khớp web, sửa khi mở rộng harness (mục 5); giao diện/JSON chưa hiển thị mức vượt mốc, MCC, PR-AUC, ước lượng nhiễu (mục 6).
4. Bộ kết hợp — file mới `class_noise/combined.py` (ĐÓNG GÓP CHÍNH) — ĐÃ CODE + TEST (22/11/2026, chưa nối vào web, chưa chọn α):
   - [x] đổi điểm từng phương pháp về thứ hạng phần trăm;
   - [x] trọng số từ mức vượt mốc (mức vượt mốc ≤ 0 → loại); k-NN luôn có mặt; 2 bản: công tắc + pha trộn (α chọn trên
         seed 0 rồi giữ cố định) — hai bản = α = 0 và α > 0; việc CHỌN α vẫn chờ mục 5;
   - [x] K = số dòng phương pháp trọng số lớn nhất tự gắn cờ; trả Top-K kèm phương pháp nào cùng nghi
         + lý do (mức vượt mốc).
   **Kiểm chứng:** 40 kiểm tra đơn vị (hạng phần trăm hoà, trọng số 3 giá trị α khớp tính tay, cổng chất lượng gồm đúng ngưỡng 0, ví dụ tay 6 dòng,
   K theo phương pháp nặng nhất, dòng NaN, điểm hằng số, hợp số dòng, bỏ phiếu nhãn, tham số sai) + chạy đầu-cuối trên Car có đáp án.
   **Thử đầu-cuối trên Car (mặc định mới, 100 cây, 1 lần cấy — KHÔNG phải đánh giá chính thức):** Car 5% (86 dòng cấy): Confident Learning F1 0,713 (71 cờ),
   Distance (k=auto→3) 0,527 (225 cờ), Ensemble 0,266 (501 cờ); KẾT HỢP 71 dòng (K từ Confident Learning) P 0,944 R 0,779 F1 0,854 với cả α = 0 / 0,5 / 1.
   Car 10% (173 dòng cấy): 0,765 / 0,651 / 0,381; KẾT HỢP F1 0,819 (α=0), 0,855 (0,5), 0,898 (1). Dòng có cả 3 phương pháp cùng nghi: 108/117 đúng ở Car 10%,
   chỉ 2 phương pháp: 28/42 → số phương pháp cùng nghi là tín hiệu tin cậy hữu ích (ứng viên cho nhãn "mức tin cậy" trên giao diện).
   **Đọc kết quả này thận trọng:** (a) MỘT bộ dữ liệu, nhãn sinh từ luật (đặc trưng quyết định nhãn nên mô hình học rất tốt), 1 lần cấy nhiễu; chưa chạy Adult/Credit Card;
   (b) K lấy từ Confident Learning nên so với CL là CÙNG số dòng cờ — phần cải thiện là nhờ xếp hạng lại bằng thông tin 2 phương pháp kia, không phải gắn cờ nhiều hơn;
   (c) so với Distance/Ensemble không công bằng về số dòng (chúng cờ 225–657 dòng, K của chúng không bị cắt), đừng trích như "kết hợp thắng Distance/Ensemble";
   (d) điểm Ensemble chỉ có 4 mức nên đóng góp xếp hạng thô — kế hoạch mục 7 (5 họ có xác suất) sẽ cải thiện;
   (e) `k="auto"` cho Distance chọn k=3 trên Car (xem mục 2), có thể làm Distance yếu hơn mức có thể; (f) α chưa được chọn theo giao thức nên các số theo α chỉ để xem xu hướng.
   **(g) CẢI CHÍNH SAU MỤC 5:** kết quả "kết hợp F1 0,854 so với Confident Learning 0,713" trên Car KHÔNG tổng quát hoá khi chạy 4 bộ x 4 seed giữ lại — xem mục 5 (bộ kết hợp thua `naive_cv` và không hơn cách cắt top-K theo điểm của Confident Learning).
5. Thực nghiệm — mở rộng `evaluate_class_noise_multiseed.py` — ĐÃ CHẠY XONG (22/11/2026): 4 bộ x 5 seed x 3 kiểu nhiễu = 60 ô, 900 bản ghi.
   **Thiết lập:** harness v2 ghi `data/class_noise_multiseed_v2.jsonl` (+ điểm từng dòng ở `data/class_noise_scores_v2/`, git bỏ qua, ~35 MB, sinh lại được);
   `summarize_class_noise_multiseed.py` ghi báo cáo đầy đủ `data/class_noise_experiment_summary.md` (bảng theo từng bộ x kiểu nhiễu, Wilcoxon, downstream, biến thể, cổng, thời gian);
   `analyze_class_noise_same_k.py` làm phân tích "cắt cùng K". Bộ dữ liệu: Car (1.728 dòng, 2 lớp, 7,75% hiếm, nhãn gốc đúng 100%), Adult (mẫu 30.000 dòng, 6 cột số), dữ liệu thầy (mẫu 30.000/588.393
   dòng, 3 cột yếu), Credit Card (mẫu 30.000 dòng gồm đủ 492 gian lận => 1,64%, cao hơn 0,17% của bộ gốc). Nhiễu: A 10% (đồng đều), B 30% (lớp hiếm <-> lớp đông), IDN 10% (phụ thuộc đặc trưng, SINH BẰNG
   HistGradientBoosting nên thiên vị có lợi cho đối chứng naive_cv). Chia 70/30 phân tầng, nhiễu chỉ cấy vào train. Giao thức: α chọn CHỈ trên seed 0, mọi so sánh chỉ trên seed 1–4 (12 cặp mỗi bộ,
   48 cặp gộp; các cặp trong cùng bộ KHÔNG độc lập hoàn toàn). Đặc trưng theo luồng web: Confident Learning dùng giá trị thô, các phương pháp còn lại dùng cap + log.
   **KẾT QUẢ CHÍNH — ĐÓNG GÓP "BỘ KẾT HỢP" KHÔNG ĐƯỢC SỐ LIỆU ỦNG HỘ:**
   (1) *α không có ý nghĩa:* F1 seed 0 theo α = 0 / 0,25 / 0,5 / 0,75 / 1 là 0,6390 / 0,6391 / 0,6395 / 0,6396 / 0,6398 (chênh 0,0008: α=1 được chọn nhưng thực chất là hoà). Ensemble cũ bị cổng loại ở
       100% ô của Car, dữ liệu thầy, Credit Card và 33% ô của Adult; Confident Learning chỉ bị loại 8% ô Car => thường chỉ còn Confident Learning + Mutual k-NN, mà theo cách định nghĩa trọng số (q của k-NN =
       trung bình q của các phương pháp còn lại) hai bên LUÔN chia đều dù α bao nhiêu. Bản "công tắc" và "pha trộn" gần như đồng nhất.
   (2) *So với đối chứng sklearn thuần `naive_cv` (1 mô hình HistGradientBoosting out-of-fold) bộ kết hợp THUA có ý nghĩa:* gộp 48 cặp, F1 −0,073 (thắng 12 / thua 36, p < 0,0001), AP −0,033 (8/40), P@K −0,022
       (p = 0,0027). Bỏ IDN (32 cặp A + B): F1 −0,051 (12/20, p = 0,024), AP −0,037 (7/25, p = 0,0002). Thắng đủ 4/4 seed (F1) chỉ ở Car A và Adult A (3/4 ở Credit Card B); 9/12 ô thắng không quá 1 trong 4 seed.
       Đây đúng chỗ thầy chê ("chỉ gọi model có sẵn"): đối chứng thư viện thuần là đường cơ sở rất khó thắng.
   (3) *So với Confident Learning:* F1 +0,111 (32/48, Holm 0,0011) NHƯNG AP −0,022 (thắng 4/48) và P@K −0,016 (8/48). Phân tích cắt cùng K (K = số dòng Confident Learning tự gắn cờ; trung bình 48 ô): Precision của luật gắn
       cờ riêng của Confident Learning = 0,531; cắt top-K theo CHÍNH điểm nghi ngờ của nó = 0,641; bộ kết hợp = 0,631; naive_cv cắt top-K = 0,649. Bộ kết hợp KÉM hơn chỉ cắt Confident Learning theo điểm của nó ở 39/48 ô
       (hơn ở 8, bằng 1). => Phần "hơn Confident Learning về F1" gần như HOÀN TOÀN do luật confident-joint là cách CẮT danh sách kém hơn xếp hạng của chính nó (cắt theo điểm tốt hơn luật ở 34/48 ô), KHÔNG do gộp thêm
       Mutual k-NN / Ensemble.
   (4) *Thắng rõ về xếp hạng so với các phương pháp yếu hơn:* AP hơn Mutual k-NN +0,161 (47/1/0), ENN +0,141 (48/0/0), Ensemble cũ +0,480 (48/0/0). Về F1 hơn Mutual k-NN +0,014 (Holm 0,07) và ENN +0,013 (p = 0,16): KHÔNG có ý nghĩa.
   (5) *Downstream (PR-AUC trên test sạch, HistGradientBoosting):* khoảng cách Oracle − nhiễu rất nhỏ ở Adult (0,014), dữ liệu thầy (0,025), Credit Card (0,036) so với Car (0,178) => mô hình bền với nhiễu ở các bộ đó, và lọc dòng bị cờ
       thường làm TỆ đi (Adult −0,013 đến −0,123; dữ liệu thầy −0,026 đến −0,202). Chỉ Car cải thiện (+0,07 đến +0,10 khi lọc, khoảng nửa khoảng cách tới Oracle). Ngoài Car không phương pháp nào có lợi downstream ổn định.
   (6) *Biến thể Mutual k-NN (mọi seed):* "k theo độ phủ" kém bản k=5 ở Car / Adult / dữ liệu thầy (F1 0,686 so với 0,754; 0,356 so với 0,385; 0,576 so với 0,647) nhưng TỐT hơn ở Credit Card (0,792 so với 0,742) => không có luật chọn k
       tốt cho mọi bộ; Manhattan ≈ gốc; bỏ phiếu theo khoảng cách không tốt hơn; KHÔNG cap + log cho kết quả ≈ hoặc nhỉnh hơn (dữ liệu thầy 0,685 so với 0,647; còn lại chênh <= 0,01) => cap + log không giúp Mutual k-NN.
   (7) *Ensemble CŨ vô dụng:* gắn cờ 308–7.833 dòng, Precision 0,06–0,33, AP gần tỉ lệ nền ở mọi bộ (bản làm lại: mục 7).
   (8) Thời gian trung bình mỗi ô (30.000 dòng): Confident Learning 1,5–14 giây, các phương pháp còn lại < 8 giây.
   **Hạn chế khi trích dẫn:** chỉ 4 seed giữ lại; mẫu con 30.000 dòng; IDN sinh bằng cùng họ mô hình với naive_cv; lưới α/k cố định; chỉ bài toán 2 lớp; Credit Card mẫu có 1,64% gian lận chứ không phải 0,17%; chưa chạy trên file gốc ~35 cột
   của thầy. KHÔNG nên viết "bộ kết hợp vượt các phương pháp thành phần" — số liệu không ủng hộ. Có thể viết: các thành phần bổ sung nhau yếu, đối chứng sklearn thuần rất mạnh, và luật CẮT danh sách quan trọng không kém điểm xếp hạng.
   **Hướng nên thử tiếp (CHƯA làm; nên đánh giá trên seed MỚI 5–9 để không tinh chỉnh theo seed đã xem):** (a) cắt danh sách theo xếp hạng với K = số dòng nhãn sai ước lượng từ ma trận đếm hiệu chỉnh (mục 3) thay cho luật
   confident-joint; (b) cho k-NN một trọng số độc lập với q của các phương pháp khác để α có tác dụng; (c) thay Ensemble cũ bằng Ensemble 5 họ (mục 7), vì Ensemble cũ gần như luôn bị cổng loại nên bộ kết hợp thực chất chỉ có 2 thành phần.
   - [x] thêm bộ Car Evaluation `data/car_evaluation.csv` (nhãn sinh từ bộ luật DEX → đúng 100%;
         1.728 dòng = mọi tổ hợp 4×4×4×3×3×3, không trùng). Đổi chữ → số theo thứ tự: buying/maint
         low=1 med=2 high=3 vhigh=4; doors 2/3/4/5more=2/3/4/5; persons 2/4/more=2/4/5; lug_boot
         small/med/big=1/2/3; safety low/med/high=1/2/3. Gộp 2 nhãn THEO THỨ TỰ: unacc+acc=0 (1.594),
         good+vgood=1 (134, ~7,8%). KHÔNG gộp lệch thứ tự (vd good+unacc) vì làm hỏng phép thử;
   - [x] thêm phương pháp: ENN k = 3 (đường cơ sở), combined (công tắc + pha trộn), các biến thể ở 2–3;
   - [x] lưu điểm từng phương pháp ra đĩa (gộp lại không phải chạy lại); lưu mức vượt mốc (MCC / PR-AUC của mô hình CHƯA lưu);
   - [x] chạy 5 seed; script tổng hợp mean ± std + kiểm định Wilcoxon bắt cặp.
6. Web — ĐÃ LÀM (22/11/2026, user bảo "làm mục 7 đi, không cần test"; chi tiết ở mục 45 phía trên):
   - [x] route + giao diện "Bộ kết hợp (thử nghiệm)": bảng các phương pháp thành phần (bật/tắt, mức vượt mốc, trọng số, lý do) + bảng Top-K kèm lý do từng dòng;
   - [x] luật cảnh báo theo mức vượt mốc (bỏ luật cũ "<= 2 điểm % và dưới 30% mức trần"): <= 0 đỏ, < 20% vàng;
   - [x] 2 lựa chọn "Giảm số cột" / "Không giảm số cột" (mặc định không giảm) thay nút "Giảm cột tự động" + báo cáo cột bị bỏ (luật nào, trùng với cột nào) + số dòng gộp / nhóm mâu thuẫn;
   - [ ] (nếu kịp) chạy nền + thanh tiến độ — CHƯA làm.
7. (Nếu còn giờ) Ensemble 5 họ — ĐÃ CODE + TEST (22/11/2026, user bảo bỏ qua mục 6 làm mục 7; CHƯA đánh giá chính thức, chưa nối vào web):
   - [x] LogisticRegression, GaussianNB, KNeighborsClassifier, MLPClassifier, HistGradientBoosting (`class_noise/ensemble_diverse.py`);
   - [x] bỏ `balanced`; chỉnh ngưỡng từng mô hình cho cân 2 loại lỗi (cách hiểu của dự án, chưa đọc bài Khoshgoftaar 2005);
   - [x] mức bỏ phiếu 3/5 – 4/5 – 5/5 (`min_votes`); đo độ đa dạng (ma trận tỉ lệ đoán giống nhau từng cặp);
   - [x] đánh giá chính thức so với Ensemble cũ trên đủ 4 bộ x 5 seed x 3 kiểu nhiễu (ĐÃ CHẠY, kết quả ngay bên dưới; báo cáo đầy đủ ở `data/class_noise_experiment_summary.md` mục 8): harness đã đăng ký `--methods ...,ensemble5` (KHÔNG nằm trong mặc định; tự sinh thêm `ensemble5_v4`, `ensemble5_v5`
     từ số phiếu đã lưu và `combined5_a<alpha>` = bộ kết hợp thay Ensemble cũ bằng bản mới), chạy SAU khi mục 5 xong để khỏi ghi chồng cùng file.
   **Xem sơ bộ trên Car (6 ô = seed 1, 2 x 3 kiểu nhiễu, 1 bộ dữ liệu, KHÔNG phải đánh giá):** thước đo XẾP HẠNG cải thiện rất mạnh so với Ensemble cũ: AP từ 0,17–0,21 lên 0,74–0,98, P@K từ 0,19–0,27
   lên 0,57–0,94 (điểm cũ chỉ có 4 mức nên xếp hạng gần như ngẫu nhiên, điểm mềm của 5 mô hình mịn). Còn DANH SÁCH GẮN CỜ theo phiếu vẫn gắn quá nhiều: 3/5 cờ 236–416 dòng so với 56–121 dòng thật
   (Precision 0,21–0,28, F1 ≈ bản cũ), vì ngưỡng cân FPR = FNR chấp nhận nhiều dương giả khi lớp hiếm ít; 5/5 gọn lại (cờ 64–113, Precision 0,34–0,59, Recall 0,32–0,68). Độ đa dạng: dự đoán giống nhau
   trung bình 0,66–0,78; MLP có mức vượt mốc ÂM ở các ô nhiễu B và IDN (−0,03 đến −0,18). **Hệ quả cho bộ kết hợp:** nếu để α lớn thì Ensemble mới thành phương pháp "nặng nhất" và K lấy từ số cờ của nó
   (366–416 dòng) nên `combined5_a1` có Precision 0,29–0,33 — luật "K = số cờ của phương pháp nặng nhất" dễ vỡ khi phương pháp đó gắn cờ quá tay.
   **ĐÁNH GIÁ CHÍNH THỨC (22/11/2026, cùng 60 ô và cùng nhiễu với mục 5; so trên seed 1–4, 48 cặp gộp; thiết kế Ensemble 5 họ KHÔNG chỉnh theo kết quả nào — chỉ có xem sơ bộ trên Car seed 1, 2 ở trên):**
   (1) *Xếp hạng cải thiện rất mạnh so với Ensemble cũ:* AP +0,506 (thắng 48/48), P@K +0,422 (48/48), p < 0,0001. So với `naive_cv`: AP −0,006 (25/23, p = 0,26) và P@K −0,004 (p = 0,36) => KHÔNG khác biệt có ý nghĩa; so với
       Confident Learning: AP +0,004 (p = 0,27), P@K +0,001 (p = 0,89) => cũng ngang nhau; so với Mutual k-NN: AP +0,188 (47/48), P@K +0,102. Tức điểm mềm của 5 họ xếp hạng ngang một mô hình sklearn thuần.
   (2) *Nhưng DANH SÁCH GẮN CỜ vẫn kém, thậm chí kém Ensemble cũ ở mức 3/5:* F1 −0,054 so với bản cũ (thắng 19 / thua 29, p = 0,002); ở mức 5/5 −0,012 (p = 0,93, ngang). F1 thua `naive_cv` ở CẢ 48/48 cặp (−0,455). Lý do: gắn cờ quá tay —
       mức 3/5 cờ 313 dòng (Car), 6.435 (Adult), 7.868 (dữ liệu thầy), 6.958 (Credit Card) trong khi số dòng thật bị đảo là ~56–121, ~2.100–3.034, ~322–2.100, ~206–2.100. Ngưỡng cân FPR = FNR tự nó chấp nhận nhiều dương giả khi lớp hiếm ít;
       tăng lên 4/5, 5/5 chỉ giảm số cờ chứ không đưa F1 lên mức `naive_cv`.
   (3) *Độ đa dạng (tỉ lệ dòng 2 mô hình dự đoán trùng, trung bình các cặp):* Car 0,730; Adult 0,867 (gần như cùng ý kiến); dữ liệu thầy 0,631; Credit Card 0,610. *Mức vượt mốc từng mô hình:* GaussianNB TỆ hơn đoán bừa ở dữ liệu thầy (−0,48) và
       Credit Card (−0,63) (xác suất quá cực đoan); MLP âm ở Car (−0,07); ở dữ liệu thầy (3 cột yếu) mọi mô hình ≈ 0 => Ensemble 5 họ bị cổng của bộ kết hợp loại ở 12% số ô.
   (4) *Bộ kết hợp dùng Ensemble 5 họ* (α chọn trên seed 0 = 0; K lấy từ Confident Learning ở 98% ô): hơn bộ kết hợp dùng Ensemble cũ một chút NHƯNG nhất quán — F1 +0,007 (thắng 35 / hoà 10 / thua 3), AP +0,012 (40/6/2), P@K +0,007 (34/7/7) —
       nhưng VẪN THUA `naive_cv`: F1 −0,066 (12/36, p = 0,0001), AP −0,021 (12/36, p = 0,0008), P@K −0,015 (p = 0,027); và vẫn không hơn chính xếp hạng của Confident Learning: AP −0,011 (10/38), P@K −0,009 (10/1/37), F1 +0,118 (32/48).
   **Kết luận cho mục 7:** Ensemble 5 họ là bản làm lại ĐÁNG KỂ về chất lượng xếp hạng (bản cũ gần như ngẫu nhiên), nhưng không làm thay đổi kết luận của mục 5: bộ kết hợp vẫn không vượt đối chứng `naive_cv`. Phần cần sửa tiếp là LUẬT CẮT
   danh sách (xem "Hướng nên thử tiếp" ở mục 5). Tiếp theo không nên lại thêm họ mô hình; nên dùng điểm mềm này với K lấy từ tỉ lệ nhãn sai ước lượng (mục 3). Chưa nối vào web.
8. Mỗi cụm code xong: test → ghi file này → push.
9. Sửa bài:
   - [ ] Mở đầu: bỏ câu "khoá luận không đưa ra thuật toán mới", viết lại đóng góp;
   - [ ] Chương 1: các phương pháp liên quan; Garcia 2016, Ali 2026, Nazaretyan 2025;
   - [ ] Chương 2: mệnh đề mức vượt mốc ≤ 1 − f/n₁ (gắn với điều kiện của CL); lý do bỏ chọn cột có giám sát
         (Frénay 2014); bagging chịu nhiễu (Dietterich 2000); chọn k (Hall 2008);
   - [ ] Chương 3: pipeline chuẩn bị mới, thiết kế bộ kết hợp (giả mã), giao diện mới;
   - [ ] Chương 4: số liệu mới (mean ± std), so với đường cơ sở, giả định nhãn gốc sạch, Ensemble kém
         vì cùng họ (Khoshgoftaar 2005; Sluban & Lavrač 2015);
   - [ ] Kết luận + hướng phát triển (Ensemble 5 họ nếu chưa làm, k theo từng điểm, tập sạch nhỏ /
         active learning, cột chữ, DuckDB/Parquet, chạy nền đầy đủ, xuất quy trình làm sạch).

Bắt buộc: 1, 2 (trừ phần biến thể), 3, 4, 5 (Car Evaluation + 5 seed), 6 (2 mục đầu), 9. Còn lại làm nếu kịp.

Ghi chú: chỉ số (độ chính xác CV − độ chính xác đoán toàn lớp đông nhất) / (1 − cùng mốc đó)
gọi là **mức vượt mốc** (trên web: "% mức trần tối đa"); KHÔNG viết tắt bằng chữ cái.
Chờ Quân quyết: thêm bộ dữ liệu nào ngoài Car Evaluation; lọc tương quan có đổi sang Spearman không.
File mới `class_noise/preprocess.py` chỉ chứa phần CHƯA có (cột hằng / định danh / gần toàn trống,
dòng mâu thuẫn); dùng lại `feature_selection.py` (sửa `filter_correlated()` tại chỗ) và
`attribute_noise/detectors.py::detect_duplicate_rows`.

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
