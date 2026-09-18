// Địa chỉ backend Flask. Đổi lại nếu bạn chạy backend ở port/host khác.
const API_BASE = "http://localhost:5000";

// Biến "nhớ" trạng thái hiện tại của trang (giống như state trong React,
// nhưng ở đây làm bằng tay vì chưa dùng framework).
let currentFileId = null;
// Lưu lại danh sách cột của file đã upload, để dùng khi user bấm "+ Thêm
// rule" SAU KHI đã upload (lúc đó mới biết có cột nào để đổ vào <select>).
let currentColumns = [];

const fileInput = document.getElementById("file-input");
const dropZone = document.getElementById("drop-zone");
const dropZoneText = document.getElementById("drop-zone-text");
const uploadBtn = document.getElementById("upload-btn");
const detectBtn = document.getElementById("detect-btn");

// ====== KÉO-THẢ FILE (chỉ để tiện, không bắt buộc phải dùng) ======
dropZone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropZone.classList.add("drag-over");
});
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("drag-over"));
dropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropZone.classList.remove("drag-over");
  if (e.dataTransfer.files.length > 0) {
    fileInput.files = e.dataTransfer.files;
    dropZoneText.textContent = `📄 Đã chọn: ${fileInput.files[0].name}`;
  }
});
fileInput.addEventListener("change", () => {
  if (fileInput.files.length > 0) {
    dropZoneText.textContent = `📄 Đã chọn: ${fileInput.files[0].name}`;
  }
});

function setStepActive(stepNumber) {
  [1, 2, 3, 4].forEach((n) => {
    document.getElementById(`step-indicator-${n}`).classList.toggle("active", n <= stepNumber);
  });
}

function setButtonLoading(button, isLoading, loadingText, normalText) {
  button.disabled = isLoading;
  button.textContent = isLoading ? loadingText : normalText;
}

// ====== BƯỚC 1: UPLOAD FILE ======
uploadBtn.addEventListener("click", async () => {
  const file = fileInput.files[0];
  if (!file) {
    alert("Hãy chọn 1 file trước đã");
    return;
  }

  setButtonLoading(uploadBtn, true, "Đang upload...", "Upload");

  // FormData: cách trình duyệt gửi FILE lên server (không dùng JSON thường
  // được vì JSON không chứa được dữ liệu nhị phân của file).
  const formData = new FormData();
  formData.append("file", file);

  let response;
  try {
    response = await fetch(`${API_BASE}/api/upload`, { method: "POST", body: formData });
  } catch (err) {
    alert("Không gọi được backend. Kiểm tra xem python3 app.py có đang chạy không.");
    setButtonLoading(uploadBtn, false, "Đang upload...", "Upload");
    return;
  }

  setButtonLoading(uploadBtn, false, "Đang upload...", "Upload");

  if (!response.ok) {
    alert("Upload thất bại, kiểm tra lại file hoặc log của backend.");
    return;
  }

  const data = await response.json(); // { file_id, columns, row_count }
  currentFileId = data.file_id;

  document.getElementById("upload-status").textContent =
    `✅ Đã upload: ${data.row_count} dòng, ${data.columns.length} cột.`;

  renderColumnConfigForm(data.columns);
  renderCrossFieldRuleBuilder(data.columns);
  document.getElementById("config-section").hidden = false;
  setStepActive(2);
});

// ====== BƯỚC 2: DỰNG FORM CHỌN NOISE CHO TỪNG CỘT (ĐỦ 7 LOẠI) ======
// Mỗi loại noise có 1 checkbox riêng + (tuỳ loại) ô tham số đi kèm. Các khối
// tham số CHỈ HỢP LÝ với 1 số dtype nhất định (vd out_of_range/outlier chỉ
// hợp lý với số, inconsistent_category chỉ hợp lý với category...) nên được
// ẩn/hiện động theo <select class="dtype"> đang chọn -- xem toggleColumnFieldsByDtype().
function renderColumnConfigForm(columns) {
  const container = document.getElementById("column-config-list");
  container.innerHTML = "";

  columns.forEach((col) => {
    const div = document.createElement("div");
    div.className = "column-config";
    div.dataset.col = col; // gắn tên cột vào chính div để lát nữa dễ đọc lại
    div.innerHTML = `
      <span class="col-name">${col}</span>
      <label>Kiểu:
        <select class="dtype">
          <option value="text">text</option>
          <option value="integer">integer</option>
          <option value="float">float</option>
          <option value="email">email</option>
          <option value="phone">phone</option>
          <option value="date">date</option>
          <option value="category">category</option>
        </select>
      </label>

      <label><input type="checkbox" class="nt-missing" checked /> Missing value</label>

      <span class="field-group">
        <label><input type="checkbox" class="nt-format" /> Format noise</label>
        <input type="text" class="date-format-input" placeholder="Format ngày, vd %Y-%m-%d" value="%Y-%m-%d" hidden />
      </span>

      <span class="field-group nt-numeric-only">
        <label><input type="checkbox" class="nt-range" /> Out of range</label>
        min <input type="number" class="min-value" />
        max <input type="number" class="max-value" />
      </span>

      <span class="field-group nt-numeric-only">
        <label><input type="checkbox" class="nt-outlier" /> Outlier</label>
        <select class="outlier-method">
          <option value="iqr">IQR</option>
          <option value="zscore">Z-score</option>
        </select>
        hệ số <input type="number" class="outlier-threshold" value="1.5" step="0.1" />
      </span>

      <span class="field-group nt-category-only">
        <label><input type="checkbox" class="nt-category" /> Inconsistent category</label>
        <input type="text" class="valid-categories" placeholder="giá trị chuẩn, cách nhau bởi dấu phẩy, vd Male,Female" />
        ngưỡng giống <input type="number" class="category-threshold" value="0.85" step="0.05" min="0" max="1" />
      </span>

      <span class="field-group nt-text-only">
        <label><input type="checkbox" class="nt-whitespace" /> Whitespace noise</label>
        ký tự cấm (regex, tuỳ chọn) <input type="text" class="disallowed-chars" placeholder="vd [#@$%]" />
      </span>
    `;
    container.appendChild(div);

    const dtypeSelect = div.querySelector(".dtype");
    const formatCheckbox = div.querySelector(".nt-format");
    const dateFormatInput = div.querySelector(".date-format-input");

    function toggleColumnFieldsByDtype() {
      const dtype = dtypeSelect.value;
      const isNumeric = dtype === "integer" || dtype === "float";
      div.querySelectorAll(".nt-numeric-only").forEach((el) => (el.hidden = !isNumeric));
      div.querySelectorAll(".nt-category-only").forEach((el) => (el.hidden = dtype !== "category"));
      div.querySelectorAll(".nt-text-only").forEach((el) => (el.hidden = dtype !== "text"));
      dateFormatInput.hidden = !(dtype === "date" && formatCheckbox.checked);
    }
    dtypeSelect.addEventListener("change", toggleColumnFieldsByDtype);
    formatCheckbox.addEventListener("change", toggleColumnFieldsByDtype);
    toggleColumnFieldsByDtype(); // ẩn/hiện đúng ngay từ đầu (mặc định dtype = text)
  });
}

// Đọc lại toàn bộ form -> dựng thành mảng JSON config, ĐÚNG format mà
// backend (_config_from_json trong app.py) đang mong đợi.
function buildColumnConfigs() {
  const configs = [];

  document.querySelectorAll(".column-config").forEach((div) => {
    const column = div.dataset.col;
    const dtype = div.querySelector(".dtype").value;
    const noiseTypes = [];

    if (div.querySelector(".nt-missing").checked) {
      noiseTypes.push("missing_value");
    }

    let dateFormat = null;
    if (div.querySelector(".nt-format").checked) {
      noiseTypes.push("format_noise");
      const dateFormatRaw = div.querySelector(".date-format-input").value.trim();
      dateFormat = dateFormatRaw || null;
    }

    let minValue = null;
    let maxValue = null;
    if (div.querySelector(".nt-range").checked) {
      noiseTypes.push("out_of_range");
      const minRaw = div.querySelector(".min-value").value;
      const maxRaw = div.querySelector(".max-value").value;
      minValue = minRaw === "" ? null : parseFloat(minRaw);
      maxValue = maxRaw === "" ? null : parseFloat(maxRaw);
    }

    let outlierMethod = "iqr";
    let outlierThreshold = 1.5;
    if (div.querySelector(".nt-outlier").checked) {
      noiseTypes.push("outlier");
      outlierMethod = div.querySelector(".outlier-method").value;
      outlierThreshold = parseFloat(div.querySelector(".outlier-threshold").value) || 1.5;
    }

    let validCategories = null;
    let categoryThreshold = 0.85;
    if (div.querySelector(".nt-category").checked) {
      noiseTypes.push("inconsistent_category");
      const raw = div.querySelector(".valid-categories").value.trim();
      validCategories = raw ? raw.split(",").map((s) => s.trim()).filter(Boolean) : [];
      categoryThreshold = parseFloat(div.querySelector(".category-threshold").value) || 0.85;
    }

    let disallowedChars = null;
    if (div.querySelector(".nt-whitespace").checked) {
      noiseTypes.push("whitespace_noise");
      const raw = div.querySelector(".disallowed-chars").value.trim();
      disallowedChars = raw || null;
    }

    // Cột nào user không tick gì cả thì bỏ qua, không gửi lên backend.
    if (noiseTypes.length === 0) return;

    configs.push({
      column,
      dtype,
      noise_types: noiseTypes,
      min_value: minValue,
      max_value: maxValue,
      date_format: dateFormat,
      outlier_method: outlierMethod,
      outlier_threshold: outlierThreshold,
      valid_categories: validCategories,
      category_similarity_threshold: categoryThreshold,
      disallowed_chars_pattern: disallowedChars,
    });
  });

  return configs;
}

// ====== DUPLICATE_ROW (noise cấp DÒNG, tách khỏi form theo cột ở trên) ======
function buildDuplicateHandlingBase() {
  const enabled = document.getElementById("dup-check").checked;
  if (!enabled) return null;
  const raw = document.getElementById("dup-subset-columns").value.trim();
  const subsetColumns = raw ? raw.split(",").map((s) => s.trim()).filter(Boolean) : null;
  return { subset_columns: subsetColumns };
}

// ====== RULE LIÊN CỘT (4 loại: compare / conditional / functional_dependency / formula) ======
// Khác hẳn checkbox noise theo cột ở trên: đây là kiểm tra MÂU THUẪN LOGIC
// GIỮA 2 CỘT, nên bắt buộc người dùng phải tự chọn cột + quan hệ (xem
// CLAUDE.md mục 7 -- máy không tự suy ra được, vì mỗi file có ý nghĩa khác
// nhau, ví dụ y hệt "chuc_vu -> muc_luong" hợp lý ở file này nhưng vô lý ở
// file khác).

// Markup các <option> phép so sánh, dùng lại cho cả rule COMPARE và 2 vế
// NẾU/THÌ của rule CONDITIONAL -- viết thành hằng số để không phải lặp lại.
const OPERATOR_OPTIONS_HTML = `
  <option value="<=">&le; (nhỏ hơn hoặc bằng)</option>
  <option value="<">&lt; (nhỏ hơn)</option>
  <option value=">=">&ge; (lớn hơn hoặc bằng)</option>
  <option value=">">&gt; (lớn hơn)</option>
  <option value="==">= (bằng)</option>
  <option value="!=">&ne; (khác)</option>
`;

function columnOptionsHTML(columns) {
  return columns.map((c) => `<option value="${c}">${c}</option>`).join("");
}

// Dựng HTML cho 1 dòng rule. Mỗi dòng có ĐỦ 4 khối field cho 4 loại rule
// (compare/conditional/functional_dependency/formula) nhưng CHỈ khối khớp
// với <select class="rule-type-select"> đang chọn mới hiện ra -- cách này
// đơn giản hơn việc render lại DOM mỗi lần user đổi loại rule.
function createRuleRow(columns) {
  const row = document.createElement("div");
  row.className = "rule-row";
  const colOptions = columnOptionsHTML(columns);

  row.innerHTML = `
    <div class="rule-row-header">
      <select class="rule-type-select">
        <option value="compare">So sánh 2 cột (A lớn hơn/nhỏ hơn/bằng B)</option>
        <option value="conditional">Điều kiện (NẾU cột này... THÌ cột kia...)</option>
        <option value="functional_dependency">1 cột luôn xác định đúng 1 cột kia (functional dependency)</option>
        <option value="formula">Công thức tính toán (vd C = A × B)</option>
      </select>
      <input type="text" class="rule-label" placeholder="Tên rule (tuỳ chọn)" />
      <button type="button" class="remove-rule-btn" title="Xoá rule này">✕</button>
    </div>

    <!-- Khối field cho COMPARE -->
    <div class="rule-fields rule-fields-compare">
      <p class="hint rule-hint">
        So sánh giá trị giữa 2 cột trên CÙNG 1 dòng. Vd: cột "ngày bắt đầu làm"
        phải ≤ cột "ngày nghỉ việc".
      </p>
      <div class="rule-fields-row">
        <select class="column-a">${colOptions}</select>
        <select class="compare-operator">${OPERATOR_OPTIONS_HTML}</select>
        <select class="column-b">${colOptions}</select>
        <label>Kiểu so sánh:
          <select class="value-type">
            <option value="number">Số</option>
            <option value="date">Ngày</option>
            <option value="text">Chữ</option>
          </select>
        </label>
        <input type="text" class="date-format" placeholder="Format ngày, vd %Y-%m-%d" value="%Y-%m-%d" hidden />
      </div>
    </div>

    <!-- Khối field cho CONDITIONAL -->
    <div class="rule-fields rule-fields-conditional" hidden>
      <p class="hint rule-hint">
        Chỉ kiểm tra vế "THÌ" khi vế "NẾU" đúng. Vd: NẾU chức_vụ = "Giám đốc"
        THÌ tuổi phải ≥ 25.
      </p>
      <div class="rule-fields-row">
        <span class="rule-word">NẾU</span>
        <select class="if-column">${colOptions}</select>
        <select class="if-operator">${OPERATOR_OPTIONS_HTML}</select>
        <input type="text" class="if-value" placeholder="giá trị" />
        <select class="if-value-type">
          <option value="text">Chữ</option>
          <option value="number">Số</option>
        </select>
      </div>
      <div class="rule-fields-row">
        <span class="rule-word">THÌ</span>
        <select class="then-column">${colOptions}</select>
        <select class="then-operator">${OPERATOR_OPTIONS_HTML}</select>
        <input type="text" class="then-value" placeholder="giá trị" />
        <select class="then-value-type">
          <option value="text">Chữ</option>
          <option value="number">Số</option>
        </select>
      </div>
    </div>

    <!-- Khối field cho FUNCTIONAL_DEPENDENCY -->
    <div class="rule-fields rule-fields-functional_dependency" hidden>
      <p class="hint rule-hint">
        Mỗi giá trị của cột thứ 1 chỉ nên gắn với ĐÚNG 1 giá trị của cột thứ
        2 trong toàn bộ file. Vd: mỗi "mã nhân viên" chỉ nên ứng với 1 "tên
        nhân viên" duy nhất — nếu cùng mã mà tên khác nhau ở 2 dòng thì bị
        tính là lỗi.
      </p>
      <div class="rule-fields-row">
        <label>Cột thứ 1: <select class="determinant-column">${colOptions}</select></label>
        <span class="rule-word">→ luôn tương ứng đúng 1 giá trị của →</span>
        <label>Cột thứ 2: <select class="dependent-column">${colOptions}</select></label>
      </div>
    </div>

    <!-- Khối field cho FORMULA -->
    <div class="rule-fields rule-fields-formula" hidden>
      <p class="hint rule-hint">
        Biểu thức TOÁN HỌC so sánh giữa các cột SỐ (chỉ dùng +, -, *, / và
        tên cột). Vd: "thanh_tien == so_luong * don_gia".
      </p>
      <div class="rule-fields-row">
        <input type="text" class="formula-input" placeholder="vd: thanh_tien == so_luong * don_gia" />
        <label>Sai số cho phép:
          <input type="number" class="formula-tolerance" value="0.01" step="0.01" />
        </label>
      </div>
    </div>
  `;

  // Chỉ hiện đúng 1 khối field khớp với loại rule đang chọn trong dropdown.
  const typeSelect = row.querySelector(".rule-type-select");
  function toggleRuleFields() {
    const selected = typeSelect.value;
    row.querySelectorAll(".rule-fields").forEach((div) => {
      div.hidden = !div.classList.contains(`rule-fields-${selected}`);
    });
  }
  typeSelect.addEventListener("change", toggleRuleFields);
  toggleRuleFields(); // hiện đúng khối mặc định (compare) ngay khi tạo dòng

  // Ô "date-format" chỉ cần hiện khi value_type = date (chỉ dùng cho compare
  // -- conditional dùng if/then-value-type riêng, hiện chỉ number/text vì
  // literal người dùng gõ tay ít khi cần so sánh theo ngày).
  const valueTypeSelect = row.querySelector(".value-type");
  const dateFormatInput = row.querySelector(".date-format");
  valueTypeSelect.addEventListener("change", () => {
    dateFormatInput.hidden = valueTypeSelect.value !== "date";
  });

  row.querySelector(".remove-rule-btn").addEventListener("click", () => row.remove());

  return row;
}

function renderCrossFieldRuleBuilder(columns) {
  currentColumns = columns;
  document.getElementById("cross-field-rule-list").innerHTML = ""; // reset khi upload file mới
}

document.getElementById("add-rule-btn").addEventListener("click", () => {
  document.getElementById("cross-field-rule-list").appendChild(createRuleRow(currentColumns));
});

// Đọc lại toàn bộ các dòng rule đang có trên form -> dựng thành mảng JSON,
// ĐÚNG format mà backend (_cross_field_rule_from_json trong app.py) mong
// đợi. Field nào rule_type không dùng tới thì không gửi -- backend dùng
// .get(key, default) nên thiếu field không sao.
function buildCrossFieldRules() {
  const rules = [];

  document.querySelectorAll(".rule-row").forEach((row) => {
    const ruleType = row.querySelector(".rule-type-select").value;
    const label = row.querySelector(".rule-label").value || null;
    const base = { rule_type: ruleType, label };

    if (ruleType === "compare") {
      rules.push({
        ...base,
        column_a: row.querySelector(".column-a").value,
        operator: row.querySelector(".compare-operator").value,
        column_b: row.querySelector(".column-b").value,
        value_type: row.querySelector(".value-type").value,
        date_format: row.querySelector(".date-format").value || null,
      });
    } else if (ruleType === "conditional") {
      rules.push({
        ...base,
        if_column: row.querySelector(".if-column").value,
        if_operator: row.querySelector(".if-operator").value,
        if_value: row.querySelector(".if-value").value,
        if_value_type: row.querySelector(".if-value-type").value,
        then_column: row.querySelector(".then-column").value,
        then_operator: row.querySelector(".then-operator").value,
        then_value: row.querySelector(".then-value").value,
        then_value_type: row.querySelector(".then-value-type").value,
      });
    } else if (ruleType === "functional_dependency") {
      rules.push({
        ...base,
        determinant_column: row.querySelector(".determinant-column").value,
        dependent_column: row.querySelector(".dependent-column").value,
      });
    } else if (ruleType === "formula") {
      const formula = row.querySelector(".formula-input").value.trim();
      if (!formula) return; // formula rỗng -> bỏ qua dòng rule này, tránh gửi lên backend gây lỗi
      rules.push({
        ...base,
        formula,
        tolerance: parseFloat(row.querySelector(".formula-tolerance").value) || 0.01,
      });
    }
  });

  return rules;
}

// ====== BƯỚC 3: GỌI BACKEND DETECT + HIỂN THỊ KẾT QUẢ ======
// Nhớ lại đúng config/kết quả lần detect gần nhất -- Bước 4 (xử lý) cần dùng
// lại NGUYÊN VẸN các config này (backend sẽ tự chạy lại detect_noise() với
// đúng config đó để đảm bảo xử lý khớp với những gì người dùng đã thấy).
let lastColumnConfigs = [];
let lastDuplicateConfig = null; // { subset_columns } hoặc null nếu không bật
let lastFindings = [];

detectBtn.addEventListener("click", async () => {
  const columnConfigs = buildColumnConfigs();
  const crossFieldRules = buildCrossFieldRules();
  const duplicateConfig = buildDuplicateHandlingBase();
  if (columnConfigs.length === 0 && crossFieldRules.length === 0 && !duplicateConfig) {
    alert("Hãy chọn ít nhất 1 loại noise cho 1 cột, thêm 1 rule liên cột, hoặc bật kiểm tra trùng dòng");
    return;
  }

  setButtonLoading(detectBtn, true, "Đang detect...", "🔍 Detect Noise");

  let response;
  try {
    response = await fetch(`${API_BASE}/api/detect-noise`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        file_id: currentFileId,
        column_configs: columnConfigs,
        cross_field_rules: crossFieldRules,
        check_duplicate_row: duplicateConfig !== null,
        duplicate_subset_columns: duplicateConfig ? duplicateConfig.subset_columns : null,
      }),
    });
  } catch (err) {
    alert("Không gọi được backend.");
    setButtonLoading(detectBtn, false, "Đang detect...", "🔍 Detect Noise");
    return;
  }

  setButtonLoading(detectBtn, false, "Đang detect...", "🔍 Detect Noise");

  if (!response.ok) {
    // Backend trả {"error": "..."} kèm lý do cụ thể (vd formula sai cú pháp,
    // cột không tồn tại) -- hiển thị đúng lý do đó thay vì thông báo chung.
    let message = "Detect thất bại, kiểm tra console/backend log.";
    try {
      const errorData = await response.json();
      if (errorData.error) message = errorData.error;
    } catch (parseErr) {
      // Backend không trả JSON (vd lỗi 500 không mong muốn) -- giữ message mặc định.
    }
    alert(message);
    return;
  }

  const data = await response.json();
  lastColumnConfigs = columnConfigs;
  lastDuplicateConfig = duplicateConfig;
  lastFindings = data.findings;

  renderResults(data);
  setStepActive(3);

  const gotoHandlingBtn = document.getElementById("goto-handling-btn");
  gotoHandlingBtn.hidden = data.findings.length === 0; // không có gì để xử lý thì ẩn nút đi
});

document.getElementById("goto-handling-btn").addEventListener("click", () => {
  renderHandlingSection();
  document.getElementById("handling-section").hidden = false;
  document.getElementById("handling-section").scrollIntoView({ behavior: "smooth" });
  setStepActive(4);
});

// Map noise_type -> tên class badge CSS tương ứng (định nghĩa màu trong
// style.css). noise_type của rule liên cột có dạng "rule:compare" (chứa dấu
// ":") -- CSS không cho phép ":" trong tên class 1 cách an toàn, nên thay
// hết ký tự không phải chữ/số/"_" thành "-" khi ghép class (vd "rule:compare"
// -> "rule-compare"), còn TEXT hiển thị vẫn giữ nguyên "rule:compare".
function noiseBadge(noiseType) {
  const cssClass = noiseType.replace(/[^a-zA-Z0-9_]/g, "-");
  return `<span class="badge badge-${cssClass}">${noiseType}</span>`;
}

// Cột "noise_reasons" backend trả về dạng chuỗi ghép nhiều lý do bằng ", ",
// mỗi lý do dạng "cột:loại_noise" (vd "age:out_of_range, email:format_noise").
// Với rule liên cột, "cột" có thể là "cot_a & cot_b" và "loại_noise" có thể
// tự chứa dấu ":" (vd "rule:compare") -- nên KHÔNG dùng split(":") thô (sẽ
// cắt nhầm ngay dấu ":" đầu của "rule:compare"), mà tự tìm vị trí dấu ":"
// ĐẦU TIÊN bằng indexOf() để tách đúng "cột" và "phần còn lại".
function formatNoiseReasons(value) {
  if (!value) return "";
  return value
    .split(", ")
    .map((part) => {
      const trimmed = part.trim();
      const sepIndex = trimmed.indexOf(":");
      if (sepIndex === -1) return trimmed;
      const column = trimmed.slice(0, sepIndex);
      const noiseType = trimmed.slice(sepIndex + 1);
      return `<strong>${column}</strong> ${noiseBadge(noiseType)}`;
    })
    .join(" ");
}

function renderResults(data) {
  document.getElementById("result-section").hidden = false;

  document.getElementById("stat-total-rows").textContent = data.total_rows;
  document.getElementById("stat-flagged-rows").textContent = data.total_flagged_rows;
  document.getElementById("stat-total-findings").textContent = data.findings.length;

  const rows = data.flagged_rows;
  const head = document.getElementById("result-table-head");
  const body = document.getElementById("result-table-body");
  const emptyMsg = document.getElementById("result-empty");
  head.innerHTML = "";
  body.innerHTML = "";

  if (rows.length === 0) {
    emptyMsg.hidden = false;
    document.getElementById("result-table").hidden = true;
    return;
  }
  emptyMsg.hidden = true;
  document.getElementById("result-table").hidden = false;

  // Dùng chính các key của object đầu tiên để làm tên cột cho bảng HTML.
  const columns = Object.keys(rows[0]);
  columns.forEach((c) => {
    const th = document.createElement("th");
    th.textContent = c;
    head.appendChild(th);
  });

  rows.forEach((row) => {
    const tr = document.createElement("tr");
    columns.forEach((c) => {
      const td = document.createElement("td");
      if (c === "noise_reasons") {
        td.innerHTML = formatNoiseReasons(row[c]); // render badge màu thay vì text thô
      } else {
        td.textContent = row[c];
      }
      tr.appendChild(td);
    });
    body.appendChild(tr);
  });
}

// ====== BƯỚC 4: XỬ LÝ NOISE + TẢI FILE ĐÃ LÀM SẠCH ======
// Bảng quyết định (dtype, noise_type) -> hành động khả dụng -- PHẢI khớp
// đúng _ACTION_TABLE trong attribute_noise/attribute_handling.py (xem
// CLAUDE.md mục 6). Trùng lặp logic này ở FE là chấp nhận được vì đây chỉ là
// bảng tra cứu TĨNH dùng để dựng dropdown cho người dùng chọn -- backend vẫn
// là nơi THỰC SỰ áp dụng xử lý, FE sai bảng nhiều lắm chỉ khiến dropdown
// thiếu/thừa lựa chọn, không gây sai dữ liệu.
const ACTION_TABLE = {
  "integer|missing_value": ["remove_row", "impute_mean", "impute_median", "impute_knn", "fixed_value"],
  "integer|format_noise": ["remove_row", "impute_mean", "impute_median", "impute_knn", "fixed_value"],
  "integer|out_of_range": ["remove_row", "cap_to_range", "impute_mean", "impute_median", "impute_knn", "fixed_value"],
  "integer|outlier": ["remove_row", "cap_to_range", "impute_mean", "impute_median", "impute_knn", "keep"],
  "float|missing_value": ["remove_row", "impute_mean", "impute_median", "impute_knn", "fixed_value"],
  "float|format_noise": ["remove_row", "impute_mean", "impute_median", "impute_knn", "fixed_value"],
  "float|out_of_range": ["remove_row", "cap_to_range", "impute_mean", "impute_median", "impute_knn", "fixed_value"],
  "float|outlier": ["remove_row", "cap_to_range", "impute_mean", "impute_median", "impute_knn", "keep"],
  "category|missing_value": ["remove_row", "impute_mode", "fixed_value"],
  "category|inconsistent_category": ["auto_normalize_category"],
  "text|whitespace_noise": ["auto_clean_whitespace"],
  "email|missing_value": ["remove_row", "fixed_value"],
  "email|format_noise": ["remove_row", "fixed_value"],
  "phone|missing_value": ["remove_row", "fixed_value"],
  "phone|format_noise": ["remove_row", "fixed_value"],
  "date|missing_value": ["remove_row", "fixed_value"],
  "date|format_noise": ["remove_row", "fixed_value"],
};

const ACTION_LABELS = {
  remove_row: "Xoá cả dòng",
  impute_mean: "Điền = trung bình (mean)",
  impute_median: "Điền = trung vị (median)",
  impute_knn: "Điền = KNN (dựa vào dòng gần giống nhất)",
  impute_mode: "Điền = giá trị phổ biến nhất (mode)",
  fixed_value: "Điền giá trị cố định",
  cap_to_range: "Cắt về biên hợp lệ (cap)",
  auto_normalize_category: "Tự động chuẩn hoá về giá trị chuẩn",
  auto_clean_whitespace: "Tự động dọn khoảng trắng/ký tự lạ",
  keep: "Giữ nguyên (không sửa)",
};

// Dựng danh sách các cặp (cột, loại noise) THỰC SỰ có trong lastFindings, kèm
// số lượng ô bị lỗi -- chỉ hiện đúng những gì người dùng đã thấy ở Bước 3,
// không hiện sẵn mọi khả năng để tránh rối. Bỏ qua noise_type dạng "rule:..."
// (rule liên cột) và "duplicate_row" (xử lý riêng, xem bên dưới).
function summarizeFindingsForHandling() {
  const counts = new Map(); // key "column|noise_type" -> số lượng
  let duplicateCount = 0;

  lastFindings.forEach((f) => {
    if (f.noise_type === "duplicate_row") {
      duplicateCount += 1;
      return;
    }
    if (f.noise_type.startsWith("rule:")) return;
    const key = `${f.column}|${f.noise_type}`;
    counts.set(key, (counts.get(key) || 0) + 1);
  });

  return { counts, duplicateCount };
}

function renderHandlingSection() {
  const container = document.getElementById("handling-list");
  container.innerHTML = "";

  const configByColumn = {};
  lastColumnConfigs.forEach((cfg) => (configByColumn[cfg.column] = cfg));

  const { counts, duplicateCount } = summarizeFindingsForHandling();

  counts.forEach((count, key) => {
    const [column, noiseType] = key.split("|");
    const dtype = configByColumn[column] ? configByColumn[column].dtype : null;
    const availableActions = ACTION_TABLE[`${dtype}|${noiseType}`] || [];
    if (availableActions.length === 0) return; // chưa có hành động nào định nghĩa cho cặp này

    const row = document.createElement("div");
    row.className = "handling-row";
    row.dataset.column = column;
    row.dataset.noiseType = noiseType;
    row.innerHTML = `
      <div class="handling-row-header">
        <strong>${column}</strong> ${noiseBadge(noiseType)}
        <span class="hint">(${count} ô)</span>
      </div>
      <select class="handling-action">
        ${availableActions.map((a) => `<option value="${a}">${ACTION_LABELS[a]}</option>`).join("")}
      </select>
      <input type="text" class="handling-fixed-value" placeholder="giá trị cố định" hidden />
    `;
    const actionSelect = row.querySelector(".handling-action");
    const fixedValueInput = row.querySelector(".handling-fixed-value");
    function toggleFixedValue() {
      fixedValueInput.hidden = actionSelect.value !== "fixed_value";
    }
    actionSelect.addEventListener("change", toggleFixedValue);
    toggleFixedValue();

    container.appendChild(row);
  });

  if (duplicateCount > 0) {
    const row = document.createElement("div");
    row.className = "handling-row";
    row.dataset.duplicateRow = "true";
    row.innerHTML = `
      <div class="handling-row-header">
        <strong>Duplicate row</strong> ${noiseBadge("duplicate_row")}
        <span class="hint">(${duplicateCount} dòng)</span>
      </div>
      <label>Giữ lại bản:
        <select class="duplicate-keep">
          <option value="first">Đầu tiên</option>
          <option value="last">Cuối cùng</option>
        </select>
      </label>
    `;
    container.appendChild(row);
  }

  if (container.children.length === 0) {
    container.innerHTML =
      '<p class="hint">Không có loại noise nào (ngoài rule liên cột) có hành động xử lý khả dụng.</p>';
  }
}

document.getElementById("apply-handling-btn").addEventListener("click", async () => {
  const btn = document.getElementById("apply-handling-btn");
  const statusEl = document.getElementById("handling-status");
  const handlingChoices = [];
  let duplicateHandling = null;

  document.querySelectorAll(".handling-row").forEach((row) => {
    if (row.dataset.duplicateRow === "true") {
      duplicateHandling = {
        enabled: true,
        keep: row.querySelector(".duplicate-keep").value,
        subset_columns: lastDuplicateConfig ? lastDuplicateConfig.subset_columns : null,
      };
      return;
    }
    const action = row.querySelector(".handling-action").value;
    const choice = {
      column: row.dataset.column,
      noise_type: row.dataset.noiseType,
      action,
    };
    if (action === "fixed_value") {
      choice.fixed_value = row.querySelector(".handling-fixed-value").value;
    }
    handlingChoices.push(choice);
  });

  setButtonLoading(btn, true, "Đang xử lý...", "✅ Áp dụng xử lý & tải file CSV");
  statusEl.textContent = "";

  let response;
  try {
    response = await fetch(`${API_BASE}/api/apply-handling`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        file_id: currentFileId,
        column_configs: lastColumnConfigs,
        handling_choices: handlingChoices,
        duplicate_handling: duplicateHandling,
      }),
    });
  } catch (err) {
    alert("Không gọi được backend.");
    setButtonLoading(btn, false, "Đang xử lý...", "✅ Áp dụng xử lý & tải file CSV");
    return;
  }

  setButtonLoading(btn, false, "Đang xử lý...", "✅ Áp dụng xử lý & tải file CSV");

  if (!response.ok) {
    let message = "Xử lý thất bại, kiểm tra console/backend log.";
    try {
      const errorData = await response.json();
      if (errorData.error) message = errorData.error;
    } catch (parseErr) {
      // giữ message mặc định
    }
    alert(message);
    return;
  }

  const data = await response.json();
  statusEl.textContent =
    `✅ Đã xử lý xong: ${data.original_row_count} dòng gốc -> ` +
    `${data.final_row_count} dòng còn lại (đã xoá ${data.removed_row_count} dòng). Đang tải file...`;

  // Tải file CSV về: gọi /api/download/<id>, đọc thành blob, rồi tạo 1 thẻ
  // <a> ẩn để "click hộ" người dùng -- cách chuẩn để tải file bằng JS mà
  // không cần điều hướng cả trang sang URL khác.
  const downloadResponse = await fetch(`${API_BASE}/api/download/${data.download_id}`);
  const blob = await downloadResponse.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "spark_cleaned.csv";
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
});
