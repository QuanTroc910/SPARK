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
  // Bước 5 (xử lý từng phần): true khi đã có ít nhất 1 lần Apply thành công
  // (tức backend đã tạo "bản đang làm việc" riêng, khác file gốc).
  hasWorkingCopy: false,
  // Các nhóm (key "cột|loại noise", hoặc "duplicate_row") ĐÃ được Apply ít
  // nhất 1 lần -- dùng để biết nút "Xem sau xử lý" của nhóm nào nên hiện sẵn
  // ngay khi renderHandlingSection() DỰNG LẠI TOÀN BỘ DOM (mỗi lần dựng lại
  // các nút đều bắt đầu từ mặc định "ẩn", nên phải tự nhớ lại qua state này).
  appliedGroups: new Set(),
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
    const alreadyApplied = state.appliedGroups.has(key);
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
          <span class="status-text">(${count} ô — bấm để xem/tick từng dòng)</span>
        </button>
        <label class="handling-bulk-label">Đặt hàng loạt:
          <select class="select handling-action">
            ${availableActions.map((a) => `<option value="${a}">${ACTION_LABELS[a]}</option>`).join("")}
          </select>
        </label>
        <button type="button" class="btn btn-ghost handling-apply-btn">Áp dụng</button>
        <button type="button" class="btn btn-ghost handling-preview-btn" ${alreadyApplied ? "" : "hidden"}>👁 Xem sau xử lý</button>
      </div>
      <p class="status-text handling-row-status"></p>
      <div class="handling-detail" hidden></div>
    `;
    container.appendChild(row);
  });

  if (duplicateCount > 0) {
    const meta = noiseMeta("duplicate_row");
    const dupAlreadyApplied = state.appliedGroups.has("duplicate_row");
    const row = document.createElement("div");
    row.className = "handling-row";
    row.dataset.duplicateRow = "true";
    row.innerHTML = `
      <div class="handling-row-top">
        <button type="button" class="handling-row-summary" aria-expanded="false">
          <span class="handling-toggle-icon">▸</span>
          <strong>Duplicate row</strong>
          <span class="tag tag-${meta.family}">${meta.label}</span>
          <span class="status-text">(${duplicateCount} dòng — mặc định tick sẵn các bản TRÙNG SAU, bỏ tick bản bạn muốn giữ)</span>
        </button>
        <button type="button" class="btn btn-ghost handling-apply-btn">Xoá các dòng đã tick</button>
        <button type="button" class="btn btn-ghost handling-preview-btn" ${dupAlreadyApplied ? "" : "hidden"}>👁 Xem sau xử lý</button>
      </div>
      <p class="status-text handling-row-status"></p>
      <div class="handling-detail" hidden></div>
    `;
    container.appendChild(row);
  }

  if (!container.children.length) {
    const message = state.hasWorkingCopy
      ? 'Đã xử lý hết mọi loại noise có thể xử lý được ở đây! Bấm "Xuất file CSV" bên dưới để tải kết quả, hoặc xem lại trước.'
      : "Không có loại noise nào (ngoài rule liên cột) có hành động xử lý khả dụng.";
    container.innerHTML = `<p class="empty-state">${message}</p>`;
    if (state.hasWorkingCopy) {
      // Dùng CHUNG class .handling-preview-btn -- listener delegate trên
      // #handling-list đã bắt sẵn class này, không cần wire thêm gì.
      container.innerHTML += '<button type="button" class="btn btn-ghost handling-preview-btn">👁 Xem dữ liệu sau xử lý</button>';
    }
  }
}

// Lấy đúng các dòng (từ state.lastFlaggedRows) đang bị 1 cặp (cột, loại
// noise) cụ thể -- dùng để xổ ra bảng chi tiết khi người dùng bấm vào 1 dòng
// xử lý ở Bước 5, để họ tự xem lại dữ liệu thật rồi TỰ TICK CHỌN dòng muốn xử lý.
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

// Với riêng duplicate_row: mặc định TICK các bản trùng đến SAU (sẽ bị xoá),
// bỏ tick bản ĐẦU TIÊN của mỗi nhóm trùng (giữ lại) -- người dùng vẫn tự
// tick/bỏ tick lại từng dòng để tuỳ chỉnh, đây chỉ là gợi ý mặc định hợp lý.
function computeDuplicateDefaultChecks(rows) {
  const subsetCols =
    state.lastDuplicateConfig && state.lastDuplicateConfig.subset_columns
      ? state.lastDuplicateConfig.subset_columns
      : getDataColumns().filter((c) => c !== "row_number");
  const seen = new Set();
  const checkByRowNumber = new Map();
  rows.forEach((r) => {
    const key = subsetCols.map((c) => r[c]).join("␟");
    if (seen.has(key)) checkByRowNumber.set(r.row_number, true); // bản trùng sau -> tick để xoá
    else {
      seen.add(key);
      checkByRowNumber.set(r.row_number, false); // bản đầu tiên -> giữ lại
    }
  });
  return checkByRowNumber;
}

// Bảng chi tiết ở Bước 5 khác bảng Kết quả (Bước 4) ở 2 chỗ:
//   1. Có thêm 1 cột CHECKBOX bên trái mỗi dòng -- chọn CHÍNH XÁC dòng nào
//      muốn xử lý, không bắt buộc cả nhóm 1 lượt.
//   2. Có thêm 1 cột "Xử lý" bên PHẢI noise_reasons -- mỗi dòng có 1 dropdown
//      hành động RIÊNG (không dùng chung 1 hành động cho cả nhóm như trước),
//      để 2 dòng cùng loại lỗi vẫn có thể xử lý khác nhau trong CÙNG 1 lần
//      bấm Áp dụng. availableActions = null (dùng cho duplicate_row) thì bỏ
//      hẳn cột này -- trùng dòng chỉ có đúng 1 việc hợp lý là xoá.
function pendingRowHTML(r, dataColumns, availableActions, defaultChecked, defaultAction) {
  const checkboxCell = `<td><input type="checkbox" class="handling-row-check" data-row-number="${r.row_number}" ${defaultChecked ? "checked" : ""} /></td>`;
  let html = rowToTableRowHTML(r, dataColumns).replace(
    "<tr>",
    `<tr data-row-number="${r.row_number}">${checkboxCell}`
  );
  if (availableActions) {
    const options = availableActions
      .map((a) => `<option value="${a}" ${a === defaultAction ? "selected" : ""}>${ACTION_LABELS[a]}</option>`)
      .join("");
    const actionCell = `<td>
      <select class="select handling-row-action">${options}</select>
      <input type="text" class="input handling-row-fixed-value" placeholder="giá trị" ${defaultAction === "fixed_value" ? "" : "hidden"} />
    </td>`;
    html = html.replace("</tr>", `${actionCell}</tr>`);
  }
  return html;
}
function handlingDetailTableHTML(rows, availableActions, defaultChecks, defaultAction) {
  if (!rows.length) return '<p class="empty-state">Không có dòng nào.</p>';
  const dataColumns = getDataColumns();
  const head =
    '<tr><th><input type="checkbox" class="handling-check-all" checked /></th>' +
    dataColumns.map((c) => `<th>${escapeHtml(c)}</th>`).join("") +
    "<th>noise_reasons</th>" +
    (availableActions ? "<th>Xử lý</th>" : "") +
    "</tr>";
  const body = rows
    .map((r) =>
      pendingRowHTML(r, dataColumns, availableActions, defaultChecks ? defaultChecks.get(r.row_number) : true, defaultAction)
    )
    .join("");
  return `<div class="table-wrap handling-detail-table"><table class="results-table"><thead>${head}</thead><tbody>${body}</tbody></table></div>`;
}

function renderHandlingDetail(row) {
  const detail = row.querySelector(".handling-detail");
  const isDuplicate = row.dataset.duplicateRow === "true";
  if (isDuplicate) {
    const rows = rowsForDuplicateHandling();
    detail.innerHTML = handlingDetailTableHTML(rows, null, computeDuplicateDefaultChecks(rows));
  } else {
    const column = row.dataset.column;
    const noiseType = row.dataset.noiseType;
    const availableActions = Array.from(row.querySelectorAll(".handling-action option")).map((o) => o.value);
    const defaultAction = row.querySelector(".handling-action").value;
    detail.innerHTML = handlingDetailTableHTML(rowsForHandlingKey(column, noiseType), availableActions, null, defaultAction);
  }
  detail.dataset.rendered = "true";
}
function openHandlingDetail(row) {
  const detail = row.querySelector(".handling-detail");
  if (!detail.dataset.rendered) renderHandlingDetail(row);
  detail.hidden = false;
  const btn = row.querySelector(".handling-row-summary");
  btn.setAttribute("aria-expanded", "true");
  btn.querySelector(".handling-toggle-icon").textContent = "▾";
}

// Bấm vào tên cột/loại noise (nút .handling-row-summary) -> xổ/thu gọn bảng
// chi tiết ngay bên dưới. Chỉ render nội dung bảng LẦN ĐẦU mở ra (lazy), lần
// sau chỉ ẩn/hiện lại cho nhanh. "Chọn tất cả" ở đầu bảng bật/tắt hết checkbox.
$("handling-list").addEventListener("click", async (e) => {
  const summaryBtn = e.target.closest(".handling-row-summary");
  if (summaryBtn) {
    const row = summaryBtn.closest(".handling-row");
    const detail = row.querySelector(".handling-detail");
    const expanded = summaryBtn.getAttribute("aria-expanded") === "true";
    if (expanded) {
      detail.hidden = true;
      summaryBtn.setAttribute("aria-expanded", "false");
      summaryBtn.querySelector(".handling-toggle-icon").textContent = "▸";
    } else {
      openHandlingDetail(row);
    }
    return;
  }

  const applyBtn = e.target.closest(".handling-apply-btn");
  if (applyBtn) {
    await handleGroupApply(applyBtn.closest(".handling-row"));
    return;
  }

  const previewBtn = e.target.closest(".handling-preview-btn");
  if (previewBtn) {
    openPreviewPanel();
    return;
  }
});
$("handling-list").addEventListener("change", (e) => {
  if (e.target.classList.contains("handling-check-all")) {
    const table = e.target.closest("table");
    table.querySelectorAll(".handling-row-check").forEach((cb) => (cb.checked = e.target.checked));
    return;
  }

  if (e.target.classList.contains("handling-action")) {
    // Dropdown "Đặt hàng loạt" ở đầu nhóm đổi -- áp hành động này cho MỌI
    // dòng đang có trong bảng chi tiết (tiện cho case "xử lý cả đống giống
    // nhau"), từng dòng sau đó vẫn tự đổi lại dropdown RIÊNG của nó được.
    const groupRow = e.target.closest(".handling-row");
    const detail = groupRow.querySelector(".handling-detail");
    detail.querySelectorAll(".handling-row-action").forEach((sel) => {
      sel.value = e.target.value;
      sel.dispatchEvent(new Event("change", { bubbles: true }));
    });
    return;
  }

  if (e.target.classList.contains("handling-row-action")) {
    // Dropdown RIÊNG của 1 dòng trong bảng chi tiết -- chỉ hiện ô "giá trị"
    // khi chính dòng đó chọn hành động "Điền giá trị cố định".
    const tr = e.target.closest("tr");
    tr.querySelector(".handling-row-fixed-value").hidden = e.target.value !== "fixed_value";
  }
});

// Sau khi Apply thành công, lấy lại dữ liệu MỚI của đúng các dòng vừa xử lý
// (qua /api/working-data, đã có sẵn) rồi cập nhật NGAY TẠI CHỖ trong bảng chi
// tiết đang mở -- dòng nào bị XOÁ (remove_row/duplicate) thì gỡ khỏi bảng,
// dòng nào chỉ sửa GIÁ TRỊ thì hiện giá trị mới + đánh dấu "Đã xử lý", thay vì
// rebuild lại cả nhóm khiến người dùng có cảm giác "cả nhóm biến mất".
async function refreshHandledRowsInPlace(row, rowNumbers) {
  let response;
  try {
    response = await fetch(`${API_BASE}/api/working-data/${state.fileId}`);
  } catch (err) {
    return;
  }
  if (!response.ok) return;
  const data = await response.json();
  const byRowNumber = new Map(data.rows.map((r) => [r.row_number, r]));
  const detail = row.querySelector(".handling-detail");
  const dataColumns = getDataColumns();
  const isDuplicate = row.dataset.duplicateRow === "true";

  rowNumbers.forEach((rn) => {
    const tr = detail.querySelector(`tr[data-row-number="${rn}"]`);
    if (!tr) return;
    const freshRow = byRowNumber.get(rn);
    if (!freshRow) {
      tr.remove(); // dòng đã bị XOÁ hẳn (remove_row hoặc duplicate) -- gỡ khỏi bảng
      return;
    }
    const stillFlagged =
      !isDuplicate &&
      (state.rowFindingsMap.get(rn) || []).some(
        (f) => f.column === row.dataset.column && f.noise_type === row.dataset.noiseType
      );
    if (stillFlagged) return; // hiếm khi xảy ra -- giữ nguyên dòng để user thử xử lý lại
    const cells = dataColumns
      .map((c) => `<td>${escapeHtml(String(freshRow[c] === undefined || freshRow[c] === null ? "" : freshRow[c]))}</td>`)
      .join("");
    const trailingCell = isDuplicate ? "" : "<td></td>"; // giữ đúng số cột với cột "Xử lý" (nếu có)
    tr.className = "handling-row-done";
    tr.innerHTML = `<td>✓</td>${cells}<td class="reasons-cell"><span class="tag tag-teal">Đã xử lý</span></td>${trailingCell}`;
  });
}

// Sau khi Apply, cập nhật lại chữ đếm ở đầu nhóm dựa trên SỐ CHECKBOX CÒN LẠI
// trong bảng chi tiết (không cần hỏi lại server) -- hết checkbox nghĩa là
// nhóm đã xử lý xong toàn bộ, khoá nốt nút Áp dụng/dropdown hàng loạt lại.
function updateGroupSummaryAfterApply(row) {
  const detail = row.querySelector(".handling-detail");
  const remaining = detail.querySelectorAll(".handling-row-check").length;
  const summaryText = row.querySelector(".handling-row-summary .status-text");
  const isDuplicate = row.dataset.duplicateRow === "true";
  if (remaining === 0) {
    summaryText.textContent = "(Đã xử lý xong toàn bộ ✓)";
    row.querySelector(".handling-apply-btn").disabled = true;
    const bulkSelect = row.querySelector(".handling-action");
    if (bulkSelect) bulkSelect.disabled = true;
  } else {
    summaryText.textContent = isDuplicate
      ? `(còn ${remaining} dòng — mặc định tick sẵn các bản TRÙNG SAU, bỏ tick bản bạn muốn giữ)`
      : `(còn ${remaining} ô — bấm để xem/tick từng dòng)`;
  }
}

// Bấm "Áp dụng" trên 1 nhóm cụ thể -- CHỈ xử lý các dòng đang được tick trong
// bảng chi tiết của CHÍNH nhóm đó (mở ra hộ nếu đang đóng), MỖI DÒNG dùng
// đúng hành động dropdown RIÊNG của chính nó (không còn dùng chung 1 hành
// động cho cả nhóm). Sau khi xong, cập nhật NGAY TẠI CHỖ (không rebuild lại
// toàn bộ Bước 5) để người dùng thấy kết quả ngay trong bảng đang mở.
async function handleGroupApply(row) {
  const isDuplicate = row.dataset.duplicateRow === "true";
  if (row.querySelector(".handling-detail").hidden) openHandlingDetail(row);

  const detail = row.querySelector(".handling-detail");
  const checkedTrs = Array.from(detail.querySelectorAll(".handling-row-check:checked")).map((cb) => cb.closest("tr"));
  if (checkedTrs.length === 0) {
    alert("Hãy tick ít nhất 1 dòng để xử lý.");
    return;
  }

  const rowsPayload = checkedTrs.map((tr) => {
    const rowNumber = parseInt(tr.dataset.rowNumber, 10);
    if (isDuplicate) return { row_number: rowNumber, action: "remove_row" };
    const action = tr.querySelector(".handling-row-action").value;
    const item = { row_number: rowNumber, action };
    if (action === "fixed_value") item.fixed_value = tr.querySelector(".handling-row-fixed-value").value;
    return item;
  });

  const applyBtn = row.querySelector(".handling-apply-btn");
  const statusEl = row.querySelector(".handling-row-status");
  const normalLabel = applyBtn.textContent;
  setButtonLoading(applyBtn, true, "Đang xử lý...", normalLabel);
  statusEl.textContent = "";

  let response;
  try {
    response = await fetch(`${API_BASE}/api/apply-handling-partial`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        file_id: state.fileId,
        column_configs: state.lastColumnConfigs,
        cross_field_rules: [],
        duplicate_row: state.lastDuplicateConfig,
        column: isDuplicate ? null : row.dataset.column,
        noise_type: isDuplicate ? "duplicate_row" : row.dataset.noiseType,
        rows: rowsPayload,
      }),
    });
  } catch (err) {
    alert("Không gọi được backend.");
    setButtonLoading(applyBtn, false, "Đang xử lý...", normalLabel);
    return;
  }
  setButtonLoading(applyBtn, false, "Đang xử lý...", normalLabel);

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
  state.lastFindings = data.findings;
  state.lastFlaggedRows = data.flagged_rows;
  state.rowFindingsMap = buildRowFindingsMap(data.findings);
  state.hasWorkingCopy = true;
  state.appliedGroups.add(isDuplicate ? "duplicate_row" : `${row.dataset.column}|${row.dataset.noiseType}`);

  await refreshHandledRowsInPlace(row, rowsPayload.map((r) => r.row_number));
  updateGroupSummaryAfterApply(row);

  statusEl.textContent = `✅ Đã xử lý ${rowsPayload.length} dòng.`;
  row.querySelector(".handling-preview-btn").hidden = false;

  // Chỉ cập nhật số liệu Bước 4 (để xem lại vẫn đúng), KHÔNG rebuild lại
  // Bước 5 -- bảng chi tiết vừa cập nhật ở trên vẫn giữ nguyên, không "biến mất".
  renderStep4({ total_rows: data.total_rows, total_flagged_rows: data.total_flagged_rows, findings: data.findings });
}

// ====== Xem dữ liệu sau xử lý (panel riêng, không nằm trong 5 bước) ======
state.previewRows = [];
state.previewPage = 1;
state.previewPerPage = 30;

async function openPreviewPanel() {
  let response;
  try {
    response = await fetch(`${API_BASE}/api/working-data/${state.fileId}`);
  } catch (err) {
    alert("Không gọi được backend.");
    return;
  }
  if (!response.ok) {
    alert("Không lấy được dữ liệu xem trước.");
    return;
  }
  const data = await response.json();
  state.previewRows = data.rows;
  state.previewPage = 1;
  renderPreviewTable();

  document.querySelectorAll(".panel").forEach((p) => p.classList.remove("is-active"));
  $("panel-preview").classList.add("is-active");
  window.scrollTo({ top: 0, behavior: "smooth" });
}
function closePreviewPanel() {
  goStep(5);
}
function renderPreviewTable() {
  const dataColumns = state.previewRows.length ? Object.keys(state.previewRows[0]) : [];
  $("preview-table-head").innerHTML = "<tr>" + dataColumns.map((c) => `<th>${escapeHtml(c)}</th>`).join("") + "</tr>";

  const perPage = state.previewPerPage;
  const totalPages = Math.max(1, Math.ceil(state.previewRows.length / perPage));
  if (state.previewPage > totalPages) state.previewPage = totalPages;
  const start = (state.previewPage - 1) * perPage;
  const pageRows = state.previewRows.slice(start, start + perPage);

  $("preview-table-body").innerHTML = pageRows
    .map((row) => {
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
      return `<tr>${cells}</tr>`;
    })
    .join("");

  $("preview-page-indicator").textContent = `Trang ${state.previewPage}/${totalPages} · ${state.previewRows.length} dòng`;
  $("preview-page-prev").disabled = state.previewPage <= 1;
  $("preview-page-next").disabled = state.previewPage >= totalPages;
}
$("preview-page-prev").addEventListener("click", () => {
  if (state.previewPage > 1) {
    state.previewPage--;
    renderPreviewTable();
  }
});
$("preview-page-next").addEventListener("click", () => {
  state.previewPage++;
  renderPreviewTable();
});
$("preview-back-btn").addEventListener("click", closePreviewPanel);

// ====== Xuất file CSV cuối cùng (dùng bản đang làm việc hiện tại) ======
$("apply-handling-btn").addEventListener("click", async () => {
  const btn = $("apply-handling-btn");
  const statusEl = $("handling-status");
  setButtonLoading(btn, true, "Đang xuất file...", "✅ Xuất file CSV");
  statusEl.textContent = "";

  let response;
  try {
    response = await fetch(`${API_BASE}/api/export-working`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file_id: state.fileId }),
    });
  } catch (err) {
    alert("Không gọi được backend.");
    setButtonLoading(btn, false, "Đang xuất file...", "✅ Xuất file CSV");
    return;
  }
  setButtonLoading(btn, false, "Đang xuất file...", "✅ Xuất file CSV");

  if (!response.ok) {
    let message = "Xuất file thất bại, kiểm tra console/backend log.";
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
  statusEl.textContent = `✅ File hiện có ${data.final_row_count} dòng. Đang tải...`;

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
