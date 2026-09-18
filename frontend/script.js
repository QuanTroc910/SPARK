"use strict";

/* ============================================================
   SPARK — Attribute Noise Detection, frontend logic.

   QUAN TRỌNG (khác với bản mockup tham khảo): file này KHÔNG có chế độ
   "phân tích cục bộ trong trình duyệt" khi backend không kết nối được.
   Toàn bộ logic detect/xử lý CHỈ được phép sống trong attribute_noise/
   (Python) -- đây là quyết định kiến trúc đã ghi trong CLAUDE.md
   ("app.py KHÔNG chứa logic detect/handle"). Nếu viết thêm 1 bộ máy detect
   bằng JS chạy song song, sớm muộn 2 bộ máy sẽ lệch kết quả với nhau (khác
   ngôn ngữ, khác thư viện số học) và không ai biết tin bộ nào -- nên trang
   này LUÔN gọi backend thật, và báo lỗi rõ ràng nếu backend chưa chạy thay
   vì âm thầm tính sai bằng JS.
   ============================================================ */

const API_BASE = "http://localhost:5000";

const $ = (id) => document.getElementById(id);

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}
const escapeAttr = escapeHtml;
function cssEscape(s) {
  return window.CSS && CSS.escape ? CSS.escape(s) : String(s).replace(/["\\]/g, "\\$&");
}
function debounce(fn, ms) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}
function setButtonLoading(button, isLoading, loadingText, normalText) {
  button.disabled = isLoading;
  button.textContent = isLoading ? loadingText : normalText;
}

// ====== Bảng metadata 11 loại (7 attribute noise + 4 rule liên cột) ======
// Dùng chung cho badge/tag/chip lọc/tô màu ô trong bảng kết quả -- family
// phải khớp đúng tên trong style.css (.tag-<family>, .cell-flag-<family>).
const NOISE_TYPE_META = {
  missing_value: { label: "Thiếu giá trị", family: "slate" },
  format_noise: { label: "Sai định dạng", family: "amber" },
  out_of_range: { label: "Ngoài khoảng", family: "crimson" },
  outlier: { label: "Giá trị bất thường", family: "violet" },
  inconsistent_category: { label: "Không nhất quán", family: "teal" },
  whitespace_noise: { label: "Khoảng trắng thừa", family: "rose" },
  duplicate_row: { label: "Trùng dòng", family: "maroon" },
  "rule:compare": { label: "Rule so sánh", family: "indigo" },
  "rule:conditional": { label: "Rule điều kiện", family: "brown" },
  "rule:formula": { label: "Rule công thức", family: "orange" },
  "rule:functional_dependency": { label: "Rule phụ thuộc hàm", family: "green" },
};
function noiseMeta(noiseType) {
  return NOISE_TYPE_META[noiseType] || { label: noiseType, family: "slate" };
}
function tagHTML(column, noiseType) {
  const meta = noiseMeta(noiseType);
  return `<span class="tag tag-${meta.family}">${escapeHtml(column)} <b>${meta.label}</b></span>`;
}

// 7 dtype thật của backend (attribute_noise/config.py::ColumnDType) -> nhãn
// hiển thị + danh sách noise_type khả dụng cho dtype đó (khớp CLAUDE.md mục 6:
// hành động HANDLE chỉ định nghĩa cho các cặp cụ thể, nên DETECT cũng chỉ nên
// cho chọn những loại thực sự hợp lý với dtype, tránh người dùng tick nhầm).
const COLUMN_TYPES = {
  text: { label: "Văn bản (text)", noises: ["missing_value", "format_noise", "whitespace_noise"] },
  integer: { label: "Số nguyên (integer)", noises: ["missing_value", "format_noise", "out_of_range", "outlier"] },
  float: { label: "Số thực (float)", noises: ["missing_value", "format_noise", "out_of_range", "outlier"] },
  email: { label: "Email", noises: ["missing_value", "format_noise"] },
  phone: { label: "Số điện thoại", noises: ["missing_value", "format_noise"] },
  date: { label: "Ngày tháng (date)", noises: ["missing_value", "format_noise"] },
  category: { label: "Phân loại (category)", noises: ["missing_value", "format_noise", "inconsistent_category"] },
};

function defaultColumnConfig() {
  return {
    dtype: "text",
    missing_value: true,
    format_noise: true,
    out_of_range: { enabled: false, min: "", max: "" },
    outlier: { enabled: false, method: "iqr", coef: 1.5 },
    inconsistent_category: { enabled: false, standard: "", threshold: 0.85 },
    whitespace_noise: { enabled: false, regex: "" },
    date_format: "%Y-%m-%d",
  };
}

// ====== State chung của trang (giống "state" trong React nhưng viết tay) ======
const state = {
  selectedFile: null,
  fileId: null,
  headers: [],
  columnConfig: {}, // { [tên cột]: cấu hình -- xem defaultColumnConfig() }
  direction: null,
  backendAvailable: false,
  currentStep: 1,
  maxReached: 1,
  // Nhớ lại đúng config + kết quả lần detect gần nhất -- Bước 5 (xử lý) cần
  // dùng lại NGUYÊN VẸN config này (backend tự chạy lại detect_noise() với
  // đúng config đó để đảm bảo xử lý khớp với những gì người dùng đã thấy).
  lastColumnConfigs: [],
  lastDuplicateConfig: null, // { subset_columns } hoặc null
  lastFindings: [],
  lastFlaggedRows: [],
  rowFindingsMap: new Map(), // row_number -> [{column, noise_type, value}, ...]
  resultsPage: 1,
  resultsPerPage: 20,
  resultsFilter: { text: "", types: new Set() },
};

// ====== Stepper (5 bước) ======
function renderStepper() {
  document.querySelectorAll(".step").forEach((el) => {
    const n = parseInt(el.dataset.step, 10);
    const complete = n < state.maxReached;
    const active = n === state.currentStep;
    const reachable = n <= state.maxReached;
    el.classList.toggle("is-complete", complete);
    el.classList.toggle("is-active", active);
    el.classList.toggle("is-reachable", reachable);
    el.querySelector(".step-circle").textContent = complete && !active ? "✓" : String(n);
  });
}
function goStep(n) {
  if (n > state.maxReached) return;
  state.currentStep = n;
  document.querySelectorAll(".panel").forEach((p) => p.classList.remove("is-active"));
  $("panel-" + n).classList.add("is-active");
  renderStepper();
  window.scrollTo({ top: 0, behavior: "smooth" });
}
function unlockStep(n) {
  if (n > state.maxReached) state.maxReached = n;
  renderStepper();
}
$("stepper").addEventListener("click", (e) => {
  const el = e.target.closest(".step");
  if (!el) return;
  const n = parseInt(el.dataset.step, 10);
  if (n <= state.maxReached) goStep(n);
});

// ====== BƯỚC 1: kiểm tra backend + upload ======
function renderBackendStatus() {
  const dot = $("backend-dot");
  const text = $("backend-status-text");
  const notice = $("upload-notice");
  if (state.backendAvailable) {
    dot.className = "status-dot is-online";
    text.textContent = "Backend: đã kết nối";
    notice.textContent = `Đã kết nối backend Flask tại ${API_BASE}.`;
  } else {
    dot.className = "status-dot is-offline";
    text.textContent = "Backend: chưa kết nối";
    notice.textContent =
      `Không kết nối được backend tại ${API_BASE}. Hãy chạy "python3 app.py" ở 1 terminal riêng rồi thử lại ` +
      `-- trang này không có chế độ phân tích cục bộ, mọi phép detect/xử lý đều phải qua backend thật (attribute_noise/).`;
  }
}
function updateUploadButtonState() {
  $("upload-btn").disabled = !(state.selectedFile && state.backendAvailable);
}
async function checkBackendHealth() {
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 1500);
    const res = await fetch(`${API_BASE}/`, { method: "GET", signal: ctrl.signal });
    clearTimeout(t);
    state.backendAvailable = !!res; // chỉ cần server phản hồi (kể cả 404) là coi như "đang chạy"
  } catch (err) {
    state.backendAvailable = false;
  }
  renderBackendStatus();
  updateUploadButtonState();
}

const dropzone = $("dropzone");
const fileInput = $("file-input");
dropzone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropzone.classList.add("is-dragover");
});
dropzone.addEventListener("dragleave", () => dropzone.classList.remove("is-dragover"));
dropzone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropzone.classList.remove("is-dragover");
  if (e.dataTransfer.files.length > 0) handleFileSelected(e.dataTransfer.files[0]);
});
fileInput.addEventListener("change", () => {
  if (fileInput.files.length > 0) handleFileSelected(fileInput.files[0]);
});

function handleFileSelected(file) {
  state.selectedFile = file;
  $("dropzone-idle").hidden = true;
  $("dropzone-file").hidden = false;
  $("file-name-text").textContent = file.name;
  $("file-meta-text").textContent = `${(file.size / 1024).toFixed(1)} KB`;
  checkBackendHealth(); // re-check phòng khi user vừa bật backend lên
}

$("upload-btn").addEventListener("click", async () => {
  const file = state.selectedFile;
  if (!file) return;

  setButtonLoading($("upload-btn"), true, "Đang upload...", "Tải lên & tiếp tục");

  const formData = new FormData();
  formData.append("file", file);

  let response;
  try {
    response = await fetch(`${API_BASE}/api/upload`, { method: "POST", body: formData });
  } catch (err) {
    alert("Không gọi được backend. Kiểm tra xem python3 app.py có đang chạy không.");
    setButtonLoading($("upload-btn"), false, "Đang upload...", "Tải lên & tiếp tục");
    return;
  }
  setButtonLoading($("upload-btn"), false, "Đang upload...", "Tải lên & tiếp tục");

  if (!response.ok) {
    alert("Upload thất bại, kiểm tra lại file hoặc log của backend.");
    return;
  }

  const data = await response.json(); // { file_id, columns, row_count }
  state.fileId = data.file_id;
  state.headers = data.columns;
  state.columnConfig = {};
  state.headers.forEach((h) => (state.columnConfig[h] = defaultColumnConfig()));
  $("rules-list").innerHTML = ""; // reset rule liên cột khi upload file mới

  $("upload-status").textContent = `✅ Đã upload: ${data.row_count} dòng, ${data.columns.length} cột.`;
  unlockStep(2);
  goStep(2);
});

// ====== BƯỚC 2: chọn hướng xử lý ======
document.querySelectorAll(".direction-card").forEach((card) => {
  card.addEventListener("click", () => {
    if (card.classList.contains("is-disabled")) return;
    document.querySelectorAll(".direction-card").forEach((c) => c.classList.remove("is-selected"));
    card.classList.add("is-selected");
    state.direction = card.dataset.direction;
    $("continue-step2-btn").disabled = false;
  });
});
$("continue-step2-btn").addEventListener("click", () => {
  if (state.direction !== "attribute") return;
  unlockStep(3);
  renderColumnList();
  goStep(3);
});

// ====== BƯỚC 3: cấu hình noise theo cột (chip UI, đủ 7 loại) ======
function paramTemplate(noiseKey, c) {
  switch (noiseKey) {
    case "format_noise":
      if (c.dtype !== "date") return "";
      return `<div class="field"><label>Định dạng chuẩn</label><input type="text" class="input mono" data-role="dateFormat" value="${escapeAttr(c.date_format)}" placeholder="%Y-%m-%d" /></div>`;
    case "out_of_range":
      return `<div class="field-row">
        <div class="field"><label>Min</label><input type="number" class="input" data-role="orMin" value="${escapeAttr(c.out_of_range.min)}" /></div>
        <div class="field"><label>Max</label><input type="number" class="input" data-role="orMax" value="${escapeAttr(c.out_of_range.max)}" /></div>
      </div>`;
    case "outlier":
      return `<div class="field-row">
        <div class="field"><label>Phương pháp</label>
          <select class="select" data-role="outMethod">
            <option value="iqr" ${c.outlier.method === "iqr" ? "selected" : ""}>IQR</option>
            <option value="zscore" ${c.outlier.method === "zscore" ? "selected" : ""}>Z-score</option>
          </select>
        </div>
        <div class="field"><label>Hệ số</label><input type="number" step="0.1" class="input" data-role="outCoef" value="${escapeAttr(c.outlier.coef)}" /></div>
      </div>`;
    case "inconsistent_category":
      return `<div class="field-row">
        <div class="field field-grow"><label>Giá trị chuẩn (cách nhau bởi dấu phẩy)</label><input type="text" class="input" data-role="incStandard" value="${escapeAttr(c.inconsistent_category.standard)}" placeholder="vd Male,Female" /></div>
        <div class="field"><label>Ngưỡng giống</label><input type="number" step="0.05" min="0" max="1" class="input" data-role="incThreshold" value="${escapeAttr(c.inconsistent_category.threshold)}" /></div>
      </div>`;
    case "whitespace_noise":
      return `<div class="field"><label>Ký tự cấm (regex, tuỳ chọn)</label><input type="text" class="input mono" data-role="wsRegex" value="${escapeAttr(c.whitespace_noise.regex)}" placeholder="vd [#@$%]" /></div>`;
    default:
      return "";
  }
}
function chipChecked(c, noiseKey) {
  if (noiseKey === "missing_value") return c.missing_value;
  if (noiseKey === "format_noise") return c.format_noise;
  return c[noiseKey] && c[noiseKey].enabled;
}
function chipTemplate(noiseKey, c) {
  const meta = noiseMeta(noiseKey);
  const checked = chipChecked(c, noiseKey);
  const paramHtml = paramTemplate(noiseKey, c);
  return `<div class="chip-wrap">
    <label class="chip tag-${meta.family} ${checked ? "is-checked" : ""}">
      <input type="checkbox" data-role="noise" data-noise="${noiseKey}" ${checked ? "checked" : ""} />
      <span>${meta.label}</span>
    </label>
    ${paramHtml ? `<div class="param-panel ${checked ? "is-open" : ""}" data-role="param-${noiseKey}">${paramHtml}</div>` : ""}
  </div>`;
}
function columnRowTemplate(h) {
  const c = state.columnConfig[h];
  const typeOptions = Object.keys(COLUMN_TYPES)
    .map((t) => `<option value="${t}" ${c.dtype === t ? "selected" : ""}>${COLUMN_TYPES[t].label}</option>`)
    .join("");
  const chips = COLUMN_TYPES[c.dtype].noises.map((nKey) => chipTemplate(nKey, c)).join("");
  return `<div class="col-row" data-col="${escapeAttr(h)}">
    <div class="col-row-head">
      <span class="col-name mono">${escapeHtml(h)}</span>
      <select class="select col-type-select" data-role="dtype">${typeOptions}</select>
    </div>
    <div class="chip-row" data-role="chips">${chips}</div>
  </div>`;
}
function renderColumnList() {
  const wrap = $("col-list");
  const empty = $("col-list-empty");
  if (!state.headers.length) {
    wrap.innerHTML = "";
    empty.hidden = false;
    return;
  }
  empty.hidden = true;
  wrap.innerHTML = state.headers.map((h) => columnRowTemplate(h)).join("");
}
function renderSingleColumnRow(h) {
  const wrap = $("col-list");
  const old = wrap.querySelector(`.col-row[data-col="${cssEscape(h)}"]`);
  if (!old) return;
  const tmp = document.createElement("div");
  tmp.innerHTML = columnRowTemplate(h).trim();
  old.replaceWith(tmp.firstElementChild);
}
$("col-list").addEventListener("change", (e) => {
  const row = e.target.closest(".col-row");
  if (!row) return;
  const h = row.dataset.col;
  const c = state.columnConfig[h];
  const role = e.target.dataset.role;

  if (role === "dtype") {
    c.dtype = e.target.value;
    renderSingleColumnRow(h);
    return;
  }
  if (role === "noise") {
    const nKey = e.target.dataset.noise;
    const checked = e.target.checked;
    if (nKey === "missing_value") c.missing_value = checked;
    else if (nKey === "format_noise") c.format_noise = checked;
    else c[nKey].enabled = checked;
    e.target.closest(".chip").classList.toggle("is-checked", checked);
    const panel = row.querySelector(`[data-role="param-${nKey}"]`);
    if (panel) panel.classList.toggle("is-open", checked);
    return;
  }
  if (role === "dateFormat") c.date_format = e.target.value;
  else if (role === "orMin") c.out_of_range.min = e.target.value;
  else if (role === "orMax") c.out_of_range.max = e.target.value;
  else if (role === "outMethod") c.outlier.method = e.target.value;
  else if (role === "outCoef") c.outlier.coef = e.target.value;
  else if (role === "wsRegex") c.whitespace_noise.regex = e.target.value;
  else if (role === "incStandard") c.inconsistent_category.standard = e.target.value;
  else if (role === "incThreshold") c.inconsistent_category.threshold = e.target.value;
});

function buildColumnConfigsFromState() {
  const configs = [];
  state.headers.forEach((h) => {
    const c = state.columnConfig[h];
    const noiseTypes = [];
    if (c.missing_value) noiseTypes.push("missing_value");
    if (c.format_noise) noiseTypes.push("format_noise");
    if (c.out_of_range.enabled) noiseTypes.push("out_of_range");
    if (c.outlier.enabled) noiseTypes.push("outlier");
    if (c.inconsistent_category.enabled) noiseTypes.push("inconsistent_category");
    if (c.whitespace_noise.enabled) noiseTypes.push("whitespace_noise");
    if (noiseTypes.length === 0) return; // cột không tick gì -> không gửi lên backend

    configs.push({
      column: h,
      dtype: c.dtype,
      noise_types: noiseTypes,
      min_value: c.out_of_range.min === "" ? null : parseFloat(c.out_of_range.min),
      max_value: c.out_of_range.max === "" ? null : parseFloat(c.out_of_range.max),
      date_format: c.date_format || null,
      outlier_method: c.outlier.method,
      outlier_threshold: parseFloat(c.outlier.coef) || 1.5,
      valid_categories: c.inconsistent_category.standard
        ? c.inconsistent_category.standard.split(",").map((s) => s.trim()).filter(Boolean)
        : null,
      category_similarity_threshold: parseFloat(c.inconsistent_category.threshold) || 0.85,
      disallowed_chars_pattern: c.whitespace_noise.regex || null,
    });
  });
  return configs;
}

// ====== Trùng dòng (duplicate_row) -- noise cấp DÒNG, đọc trực tiếp từ DOM ======
function buildDuplicateConfig() {
  if (!$("dup-enable").checked) return null;
  const raw = $("dup-subset-columns").value.trim();
  const subsetColumns = raw ? raw.split(",").map((s) => s.trim()).filter(Boolean) : null;
  return { subset_columns: subsetColumns };
}

// ====== Rule liên cột (4 loại: compare / conditional / functional_dependency / formula) ======
const OPERATOR_OPTIONS_HTML = `
  <option value="<=">&le; (nhỏ hơn hoặc bằng)</option>
  <option value="<">&lt; (nhỏ hơn)</option>
  <option value=">=">&ge; (lớn hơn hoặc bằng)</option>
  <option value=">">&gt; (lớn hơn)</option>
  <option value="==">= (bằng)</option>
  <option value="!=">&ne; (khác)</option>
`;
function columnOptionsHTML(columns) {
  return columns.map((c) => `<option value="${escapeAttr(c)}">${escapeHtml(c)}</option>`).join("");
}

function createRuleRow(columns) {
  const row = document.createElement("div");
  row.className = "rule-row";
  const colOptions = columnOptionsHTML(columns);

  row.innerHTML = `
    <div class="rule-row-header">
      <select class="select rule-type-select">
        <option value="compare">So sánh 2 cột (A lớn hơn/nhỏ hơn/bằng B)</option>
        <option value="conditional">Điều kiện (NẾU cột này... THÌ cột kia...)</option>
        <option value="functional_dependency">1 cột luôn xác định đúng 1 cột kia (functional dependency)</option>
        <option value="formula">Công thức tính toán (vd C = A × B)</option>
      </select>
      <input type="text" class="input rule-label" placeholder="Tên rule (tuỳ chọn)" />
      <button type="button" class="btn-icon remove-rule-btn" title="Xoá rule này">✕</button>
    </div>

    <div class="rule-fields rule-fields-compare">
      <p class="rule-hint">So sánh giá trị giữa 2 cột trên CÙNG 1 dòng. Vd: cột "ngày bắt đầu làm" phải ≤ cột "ngày nghỉ việc".</p>
      <div class="rule-fields-row">
        <select class="select column-a">${colOptions}</select>
        <select class="select compare-operator">${OPERATOR_OPTIONS_HTML}</select>
        <select class="select column-b">${colOptions}</select>
        <label>Kiểu so sánh:
          <select class="select value-type">
            <option value="number">Số</option>
            <option value="date">Ngày</option>
            <option value="text">Chữ</option>
          </select>
        </label>
        <input type="text" class="input date-format" placeholder="Format ngày, vd %Y-%m-%d" value="%Y-%m-%d" hidden />
      </div>
    </div>

    <div class="rule-fields rule-fields-conditional" hidden>
      <p class="rule-hint">Chỉ kiểm tra vế "THÌ" khi vế "NẾU" đúng. Vd: NẾU chức_vụ = "Giám đốc" THÌ tuổi phải ≥ 25.</p>
      <div class="rule-fields-row">
        <span class="rule-word">NẾU</span>
        <select class="select if-column">${colOptions}</select>
        <select class="select if-operator">${OPERATOR_OPTIONS_HTML}</select>
        <input type="text" class="input if-value" placeholder="giá trị" />
        <select class="select if-value-type">
          <option value="text">Chữ</option>
          <option value="number">Số</option>
        </select>
      </div>
      <div class="rule-fields-row">
        <span class="rule-word">THÌ</span>
        <select class="select then-column">${colOptions}</select>
        <select class="select then-operator">${OPERATOR_OPTIONS_HTML}</select>
        <input type="text" class="input then-value" placeholder="giá trị" />
        <select class="select then-value-type">
          <option value="text">Chữ</option>
          <option value="number">Số</option>
        </select>
      </div>
    </div>

    <div class="rule-fields rule-fields-functional_dependency" hidden>
      <p class="rule-hint">Mỗi giá trị của cột thứ 1 chỉ nên gắn với ĐÚNG 1 giá trị của cột thứ 2 trong toàn bộ file. Vd: mỗi "mã nhân viên" chỉ nên ứng với 1 "tên nhân viên" duy nhất — nếu cùng mã mà tên khác nhau ở 2 dòng thì bị tính là lỗi.</p>
      <div class="rule-fields-row">
        <label>Cột thứ 1: <select class="select determinant-column">${colOptions}</select></label>
        <span class="rule-word">→ luôn tương ứng đúng 1 giá trị của →</span>
        <label>Cột thứ 2: <select class="select dependent-column">${colOptions}</select></label>
      </div>
    </div>

    <div class="rule-fields rule-fields-formula" hidden>
      <p class="rule-hint">Biểu thức TOÁN HỌC so sánh giữa các cột SỐ (chỉ dùng +, -, *, / và tên cột). Vd: "thanh_tien == so_luong * don_gia".</p>
      <div class="rule-fields-row">
        <input type="text" class="input formula-input" placeholder="vd: thanh_tien == so_luong * don_gia" />
        <label>Sai số cho phép:
          <input type="number" class="input formula-tolerance" value="0.01" step="0.01" />
        </label>
      </div>
    </div>
  `;

  const typeSelect = row.querySelector(".rule-type-select");
  function toggleRuleFields() {
    const selected = typeSelect.value;
    row.querySelectorAll(".rule-fields").forEach((div) => {
      div.hidden = !div.classList.contains(`rule-fields-${selected}`);
    });
  }
  typeSelect.addEventListener("change", toggleRuleFields);
  toggleRuleFields();

  const valueTypeSelect = row.querySelector(".value-type");
  const dateFormatInput = row.querySelector(".date-format");
  valueTypeSelect.addEventListener("change", () => {
    dateFormatInput.hidden = valueTypeSelect.value !== "date";
  });

  row.querySelector(".remove-rule-btn").addEventListener("click", () => row.remove());

  return row;
}
$("add-rule-btn").addEventListener("click", () => {
  $("rules-list").appendChild(createRuleRow(state.headers));
});

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
      if (!formula) return;
      rules.push({
        ...base,
        formula,
        tolerance: parseFloat(row.querySelector(".formula-tolerance").value) || 0.01,
      });
    }
  });
  return rules;
}

// ====== Gọi backend detect ======
function buildRowFindingsMap(findings) {
  const map = new Map();
  findings.forEach((f) => {
    if (!map.has(f.row_number)) map.set(f.row_number, []);
    map.get(f.row_number).push(f);
  });
  return map;
}

$("detect-btn").addEventListener("click", async () => {
  const columnConfigs = buildColumnConfigsFromState();
  const crossFieldRules = buildCrossFieldRules();
  const duplicateConfig = buildDuplicateConfig();
  if (columnConfigs.length === 0 && crossFieldRules.length === 0 && !duplicateConfig) {
    alert("Hãy chọn ít nhất 1 loại noise cho 1 cột, thêm 1 rule liên cột, hoặc bật kiểm tra trùng dòng");
    return;
  }

  const btn = $("detect-btn");
  setButtonLoading(btn, true, "Đang detect...", "🔍 Detect Noise");
  $("detect-status").textContent = "";

  let response;
  try {
    response = await fetch(`${API_BASE}/api/detect-noise`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        file_id: state.fileId,
        column_configs: columnConfigs,
        cross_field_rules: crossFieldRules,
        check_duplicate_row: duplicateConfig !== null,
        duplicate_subset_columns: duplicateConfig ? duplicateConfig.subset_columns : null,
      }),
    });
  } catch (err) {
    alert("Không gọi được backend.");
    setButtonLoading(btn, false, "Đang detect...", "🔍 Detect Noise");
    return;
  }
  setButtonLoading(btn, false, "Đang detect...", "🔍 Detect Noise");

  if (!response.ok) {
    let message = "Detect thất bại, kiểm tra console/backend log.";
    try {
      const errorData = await response.json();
      if (errorData.error) message = errorData.error;
    } catch (parseErr) {
      /* backend không trả JSON -- giữ message mặc định */
    }
    alert(message);
    return;
  }

  const data = await response.json();
  state.lastColumnConfigs = columnConfigs;
  state.lastDuplicateConfig = duplicateConfig;
  state.lastFindings = data.findings;
  state.lastFlaggedRows = data.flagged_rows;
  state.rowFindingsMap = buildRowFindingsMap(data.findings);
  state.resultsPage = 1;
  state.resultsFilter = { text: "", types: new Set() };
  $("search-input").value = "";

  unlockStep(4);
  renderStep4(data);
  goStep(4);
  $("goto-handling-btn").disabled = data.findings.length === 0;
});

// ====== BƯỚC 4: kết quả (tìm kiếm + lọc theo loại + phân trang) ======
function renderFilterChips() {
  const present = new Set();
  state.lastFindings.forEach((f) => present.add(f.noise_type));
  const wrap = $("filter-chips");
  wrap.innerHTML = Array.from(present)
    .map((t) => {
      const meta = noiseMeta(t);
      const checked = state.resultsFilter.types.has(t);
      return `<label class="filter-chip tag-${meta.family} ${checked ? "is-checked" : ""}"><input type="checkbox" value="${escapeAttr(t)}" ${checked ? "checked" : ""}/><span>${meta.label}</span></label>`;
    })
    .join("");
}
$("filter-chips").addEventListener("change", (e) => {
  if (e.target.type !== "checkbox") return;
  if (e.target.checked) state.resultsFilter.types.add(e.target.value);
  else state.resultsFilter.types.delete(e.target.value);
  e.target.closest(".filter-chip").classList.toggle("is-checked", e.target.checked);
  state.resultsPage = 1;
  renderResultsTable();
});
$("search-input").addEventListener(
  "input",
  debounce((e) => {
    state.resultsFilter.text = e.target.value;
    state.resultsPage = 1;
    renderResultsTable();
  }, 200)
);

function getFilteredRows() {
  const text = state.resultsFilter.text.trim().toLowerCase();
  const types = state.resultsFilter.types;
  return state.lastFlaggedRows.filter((row) => {
    const rowFindings = state.rowFindingsMap.get(row.row_number) || [];
    if (types.size) {
      const matched = rowFindings.some((f) => types.has(f.noise_type));
      if (!matched) return false;
    }
    if (text) {
      const hay = (JSON.stringify(row) + " " + rowFindings.map((f) => f.column + " " + f.noise_type).join(" ")).toLowerCase();
      if (!hay.includes(text)) return false;
    }
    return true;
  });
}

// Cột hiển thị: dùng đúng thứ tự key backend trả (row_number, các cột gốc,
// noise_reasons) -- bỏ noise_reasons thô, tự render lại thành tag màu.
// Dùng chung cho cả bảng Kết quả (Bước 4) lẫn bảng chi tiết xổ ra ở Bước 5.
function getDataColumns() {
  return state.lastFlaggedRows.length
    ? Object.keys(state.lastFlaggedRows[0]).filter((k) => k !== "noise_reasons")
    : [];
}

function rowToTableRowHTML(row, dataColumns) {
  const rowFindings = state.rowFindingsMap.get(row.row_number) || [];
  const flagByColumn = {};
  rowFindings.forEach((f) => {
    if (!flagByColumn[f.column]) flagByColumn[f.column] = f.noise_type;
  });
  const cells = dataColumns
    .map((c) => {
      const type = flagByColumn[c];
      const cls = type ? ` class="cell-flag-${noiseMeta(type).family}"` : "";
      const value = row[c] === undefined || row[c] === null ? "" : row[c];
      return `<td${cls}>${escapeHtml(String(value))}</td>`;
    })
    .join("");
  const tags = rowFindings.map((f) => tagHTML(f.column, f.noise_type)).join(" ");
  return `<tr>${cells}<td class="reasons-cell">${tags}</td></tr>`;
}

function renderResultsTable() {
  const table = $("result-table");
  const emptyMsg = $("result-empty");
  const pagination = $("pagination");

  if (!state.lastFlaggedRows.length) {
    table.hidden = true;
    pagination.hidden = true;
    emptyMsg.hidden = false;
    return;
  }
  emptyMsg.hidden = true;
  table.hidden = false;
  pagination.hidden = false;

  const dataColumns = getDataColumns();
  $("result-table-head").innerHTML =
    "<tr>" + dataColumns.map((c) => `<th>${escapeHtml(c)}</th>`).join("") + "<th>noise_reasons</th></tr>";

  const filtered = getFilteredRows();
  const perPage = state.resultsPerPage;
  const totalPages = Math.max(1, Math.ceil(filtered.length / perPage));
  if (state.resultsPage > totalPages) state.resultsPage = totalPages;
  const start = (state.resultsPage - 1) * perPage;
  const pageRows = filtered.slice(start, start + perPage);
  const tbody = $("result-table-body");

  if (!pageRows.length) {
    tbody.innerHTML = `<tr><td colspan="${dataColumns.length + 1}" class="empty-cell">Không có dòng nào khớp bộ lọc.</td></tr>`;
  } else {
    tbody.innerHTML = pageRows.map((row) => rowToTableRowHTML(row, dataColumns)).join("");
  }

  $("page-indicator").textContent = `Trang ${state.resultsPage}/${totalPages} · ${filtered.length} dòng`;
  $("page-prev").disabled = state.resultsPage <= 1;
  $("page-next").disabled = state.resultsPage >= totalPages;
}
$("page-prev").addEventListener("click", () => {
  if (state.resultsPage > 1) {
    state.resultsPage--;
    renderResultsTable();
  }
});
$("page-next").addEventListener("click", () => {
  state.resultsPage++;
  renderResultsTable();
});

function renderStep4(data) {
  $("stat-total-rows").textContent = data.total_rows;
  $("stat-flagged-rows").textContent = data.total_flagged_rows;
  $("stat-total-findings").textContent = data.findings.length;
  renderFilterChips();
  renderResultsTable();
}

$("goto-handling-btn").addEventListener("click", () => {
  unlockStep(5);
  renderHandlingSection();
  goStep(5);
});

// ====== BƯỚC 5: xử lý noise + tải file đã làm sạch ======
// Bảng quyết định (dtype, noise_type) -> hành động khả dụng -- PHẢI khớp
// đúng _ACTION_TABLE trong attribute_noise/attribute_handling.py (xem
// CLAUDE.md mục 6). Trùng lặp bảng TĨNH này ở FE là chấp nhận được (chỉ dùng
// để dựng dropdown, KHÔNG tự thực thi xử lý) -- backend vẫn là nơi DUY NHẤT
// thực sự áp dụng thay đổi lên dữ liệu.
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

function renderHandlingSection() {
  const container = $("handling-list");
  container.innerHTML = "";

  const configByColumn = {};
  state.lastColumnConfigs.forEach((cfg) => (configByColumn[cfg.column] = cfg));

  const counts = new Map();
  let duplicateCount = 0;
  state.lastFindings.forEach((f) => {
    if (f.noise_type === "duplicate_row") {
      duplicateCount += 1;
      return;
    }
    if (f.noise_type.startsWith("rule:")) return;
    const key = `${f.column}|${f.noise_type}`;
    counts.set(key, (counts.get(key) || 0) + 1);
  });

  counts.forEach((count, key) => {
    const [column, noiseType] = key.split("|");
    const dtype = configByColumn[column] ? configByColumn[column].dtype : null;
    const availableActions = ACTION_TABLE[`${dtype}|${noiseType}`] || [];
    if (availableActions.length === 0) return;

    const meta = noiseMeta(noiseType);
    const row = document.createElement("div");
    row.className = "handling-row";
    row.dataset.column = column;
    row.dataset.noiseType = noiseType;
    row.innerHTML = `
      <div class="handling-row-top">
        <button type="button" class="handling-row-summary" aria-expanded="false">
          <span class="handling-toggle-icon">▸</span>
          <strong>${escapeHtml(column)}</strong>
          <span class="tag tag-${meta.family}">${meta.label}</span>
          <span class="status-text">(${count} ô — bấm để xem các dòng)</span>
        </button>
        <select class="select handling-action">
          ${availableActions.map((a) => `<option value="${a}">${ACTION_LABELS[a]}</option>`).join("")}
        </select>
        <input type="text" class="input handling-fixed-value" placeholder="giá trị cố định" hidden />
      </div>
      <div class="handling-detail" hidden></div>
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
    const meta = noiseMeta("duplicate_row");
    const row = document.createElement("div");
    row.className = "handling-row";
    row.dataset.duplicateRow = "true";
    row.innerHTML = `
      <div class="handling-row-top">
        <button type="button" class="handling-row-summary" aria-expanded="false">
          <span class="handling-toggle-icon">▸</span>
          <strong>Duplicate row</strong>
          <span class="tag tag-${meta.family}">${meta.label}</span>
          <span class="status-text">(${duplicateCount} dòng — bấm để xem các dòng)</span>
        </button>
        <label>Giữ lại bản:
          <select class="select duplicate-keep">
            <option value="first">Đầu tiên</option>
            <option value="last">Cuối cùng</option>
          </select>
        </label>
      </div>
      <div class="handling-detail" hidden></div>
    `;
    container.appendChild(row);
  }

  if (!container.children.length) {
    container.innerHTML = '<p class="empty-state">Không có loại noise nào (ngoài rule liên cột) có hành động xử lý khả dụng.</p>';
  }
}

// Lấy đúng các dòng (từ state.lastFlaggedRows) đang bị 1 cặp (cột, loại
// noise) cụ thể -- dùng để xổ ra bảng chi tiết khi người dùng bấm vào 1 dòng
// xử lý ở Bước 5, để họ tự xem lại dữ liệu thật trước khi chọn cách xử lý.
function rowsForHandlingKey(column, noiseType) {
  const rowNumbers = new Set(
    state.lastFindings.filter((f) => f.column === column && f.noise_type === noiseType).map((f) => f.row_number)
  );
  return state.lastFlaggedRows.filter((r) => rowNumbers.has(r.row_number));
}
function rowsForDuplicateHandling() {
  const rowNumbers = new Set(
    state.lastFindings.filter((f) => f.noise_type === "duplicate_row").map((f) => f.row_number)
  );
  return state.lastFlaggedRows.filter((r) => rowNumbers.has(r.row_number));
}
function handlingDetailTableHTML(rows) {
  if (!rows.length) return '<p class="empty-state">Không có dòng nào.</p>';
  const dataColumns = getDataColumns();
  const head = "<tr>" + dataColumns.map((c) => `<th>${escapeHtml(c)}</th>`).join("") + "<th>noise_reasons</th></tr>";
  const body = rows.map((r) => rowToTableRowHTML(r, dataColumns)).join("");
  return `<div class="table-wrap handling-detail-table"><table class="results-table"><thead>${head}</thead><tbody>${body}</tbody></table></div>`;
}

// Bấm vào tên cột/loại noise (nút .handling-row-summary) -> xổ/thu gọn bảng
// chi tiết ngay bên dưới. Chỉ render nội dung bảng LẦN ĐẦU mở ra (lazy), lần
// sau chỉ ẩn/hiện lại cho nhanh.
$("handling-list").addEventListener("click", (e) => {
  const btn = e.target.closest(".handling-row-summary");
  if (!btn) return;
  const row = btn.closest(".handling-row");
  const detail = row.querySelector(".handling-detail");
  const expanded = btn.getAttribute("aria-expanded") === "true";

  if (!expanded && !detail.dataset.rendered) {
    const rows = row.dataset.duplicateRow === "true"
      ? rowsForDuplicateHandling()
      : rowsForHandlingKey(row.dataset.column, row.dataset.noiseType);
    detail.innerHTML = handlingDetailTableHTML(rows);
    detail.dataset.rendered = "true";
  }
  detail.hidden = expanded;
  btn.setAttribute("aria-expanded", String(!expanded));
  btn.querySelector(".handling-toggle-icon").textContent = expanded ? "▸" : "▾";
});

$("apply-handling-btn").addEventListener("click", async () => {
  const btn = $("apply-handling-btn");
  const statusEl = $("handling-status");
  const handlingChoices = [];
  let duplicateHandling = null;

  document.querySelectorAll(".handling-row").forEach((row) => {
    if (row.dataset.duplicateRow === "true") {
      duplicateHandling = {
        enabled: true,
        keep: row.querySelector(".duplicate-keep").value,
        subset_columns: state.lastDuplicateConfig ? state.lastDuplicateConfig.subset_columns : null,
      };
      return;
    }
    const action = row.querySelector(".handling-action").value;
    const choice = { column: row.dataset.column, noise_type: row.dataset.noiseType, action };
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
        file_id: state.fileId,
        column_configs: state.lastColumnConfigs,
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
      /* giữ message mặc định */
    }
    alert(message);
    return;
  }

  const data = await response.json();
  statusEl.textContent =
    `✅ Đã xử lý xong: ${data.original_row_count} dòng gốc -> ${data.final_row_count} dòng còn lại ` +
    `(đã xoá ${data.removed_row_count} dòng). Đang tải file...`;

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

// ====== Khởi động ======
renderStepper();
checkBackendHealth();
