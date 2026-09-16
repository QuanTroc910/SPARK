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
  [1, 2, 3].forEach((n) => {
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

// ====== BƯỚC 2: DỰNG FORM CHỌN NOISE CHO TỪNG CỘT ======
// Demo này chỉ làm 3 loại noise cơ bản (missing_value, format_noise,
// out_of_range) cho dễ nhìn. Muốn thêm outlier/inconsistent_category/... thì
// làm tương tự: thêm checkbox + input tham số, rồi đọc lại trong
// buildColumnConfigs() bên dưới.
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
      <label><input type="checkbox" class="nt-missing" /> Missing value</label>
      <label><input type="checkbox" class="nt-format" /> Format noise</label>
      <label>
        <input type="checkbox" class="nt-range" /> Out of range
        min <input type="number" class="min-value" />
        max <input type="number" class="max-value" />
      </label>
    `;
    container.appendChild(div);
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
    if (div.querySelector(".nt-format").checked) {
      noiseTypes.push("format_noise");
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

    // Cột nào user không tick gì cả thì bỏ qua, không gửi lên backend.
    if (noiseTypes.length === 0) return;

    configs.push({
      column,
      dtype,
      noise_types: noiseTypes,
      min_value: minValue,
      max_value: maxValue,
    });
  });

  return configs;
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
detectBtn.addEventListener("click", async () => {
  const columnConfigs = buildColumnConfigs();
  const crossFieldRules = buildCrossFieldRules();
  if (columnConfigs.length === 0 && crossFieldRules.length === 0) {
    alert("Hãy chọn ít nhất 1 loại noise cho 1 cột, hoặc thêm ít nhất 1 rule liên cột");
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
  renderResults(data);
  setStepActive(3);
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
