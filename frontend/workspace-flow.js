"use strict";

/* ============================================================
   workspace-flow.js -- logic LUỒNG 5 BƯỚC (Attribute Noise + Class Noise)
   chạy bên trong khối #section-workspace của workspace.html (bước 6 của
   việc dựng lại giao diện Denoise).

   NGUỒN GỐC: đây là script.js (trang index.html cũ) sao chép sang, GIỮ
   NGUYÊN toàn bộ logic đã test kỹ (upload, chip cấu hình, rule liên cột,
   detect, xử lý từng dòng, chạy thử, hoàn tác, class noise 3 thuật toán),
   chỉ khác 3 điểm:
   1. BỌC TRONG 1 HÀM (IIFE) -- workspace.js cũng khai báo `state`, `$`,
      `escapeHtml`... ở mức toàn cục; 2 file cùng nạp vào 1 trang mà cùng
      khai báo `const state` là trình duyệt báo lỗi "đã khai báo rồi". Bọc
      lại thì mọi biến ở đây là biến cục bộ, không đụng gì tới workspace.js.
   2. BỎ phần đăng nhập/đăng ký/đăng xuất/hồ sơ -- workspace.js đã lo
      (#ws-auth, #section-profile). Chấm tròn trạng thái backend ở header
      cũng do workspace.js vẽ.
   3. Lộ ra 1 "cửa" nhỏ `window.DenoiseFlow` để workspace.js gọi vào (vd
      pill "Class Noise" ở header chọn sẵn hướng Class Noise).

   QUAN TRỌNG (giữ nguyên từ script.js): file này KHÔNG có chế độ "phân tích
   cục bộ trong trình duyệt". Mọi detect/xử lý đều gọi backend Flask thật
   (attribute_noise/, class_noise/), backend chưa chạy thì báo rõ, không
   âm thầm tính bằng JS.
   ============================================================ */
(function () {

const API_BASE = ""; // cùng origin với Flask (Flask tự phục vụ frontend), xem CLAUDE.md

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
  "rule:compare": { label: "Quy tắc so sánh", family: "indigo" },
  "rule:conditional": { label: "Quy tắc điều kiện", family: "brown" },
  "rule:formula": { label: "Quy tắc công thức", family: "orange" },
  "rule:functional_dependency": { label: "Quy tắc phụ thuộc hàm", family: "green" },
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
  category: { label: "Phân loại", noises: ["missing_value", "format_noise", "inconsistent_category"] },
};

// dtype mặc định ĐƯỢC BACKEND ĐOÁN SẴN (guess_column_dtype(), xem
// attribute_noise/pipeline.py) dựa trên GIÁ TRỊ THẬT của cột -- đỡ người
// dùng phải tự đổi dropdown cho từng cột một khi file nhiều cột. Chỉ là gợi
// ý mặc định, người dùng vẫn đổi lại bình thường qua đúng dropdown đã có.
function defaultColumnConfig(dtype = "text") {
  return {
    dtype,
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
  direction: "class", // giao diện Denoise: luồng này CHỈ còn Class Noise (Attribute Noise đã thành 6 tool riêng)
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
  // Lịch sử các lần Áp dụng ở Bước 5 (server giữ bản thật, đây là bản sao để
  // vẽ thanh "Lịch sử" + biết nút Hoàn tác có bấm được không) -- dạng
  // { entries: [...], can_undo: bool, undo_limit: số }, xem _history_payload()
  // trong app.py. Rỗng khi chưa xử lý gì hoặc vừa upload file mới.
  history: { entries: [], can_undo: false, undo_limit: 5 },
  // true khi Bước 5 đang chờ server trả lời 1 lệnh (chạy thử / áp dụng / hoàn tác /
  // về dữ liệu gốc) -- xem withHandlingLock(): trong lúc đó mọi lệnh khác bị chặn.
  handlingBusy: false,

  // ---- Riêng cho hướng Class Noise (song song, KHÔNG dùng chung state
  // attribute ở trên vì cấu trúc dữ liệu hoàn toàn khác) ----
  classLabelColumn: null,
  classFeatureColumns: new Set(),
  // Class Noise chỉ còn MỘT cách phát hiện: bộ kết hợp Confident Learning + Mutual k-NN (backend method
  // "combined"), nên không còn state "đang chọn phương pháp nào".
  classDiagnostics: null,
  // Báo cáo bước chuẩn bị chung (cột bị bỏ, dòng gộp/mâu thuẫn...) của lần phát hiện đang hiện.
  classPreprocess: null,
  // Danh sách KẾT HỢP (bảng chính, cũng là danh sách đưa sang bước Xử lý).
  classFindings: [],
  // Danh sách RIÊNG của từng phương pháp thành phần cho phần "Xem thêm": { single_learning: [...], distance_based: [...] }.
  classMethodFindings: {},
  // Phần "Xem thêm": mở/đóng (mặc định ĐÓNG) + trang hiện tại của từng danh sách riêng.
  classMoreOpen: false,
  classMorePages: {},
  classFindingsPage: 1,
  classFindingsPerPage: 20,
  classFindingsFilterText: "",
};

// ====== Stepper (5 bước) ======
function renderStepper() {
  document.querySelectorAll(".step").forEach((el, idx) => {
    const n = parseInt(el.dataset.step, 10);
    const complete = n < state.maxReached;
    const active = n === state.currentStep;
    const reachable = n <= state.maxReached;
    el.classList.toggle("is-complete", complete);
    el.classList.toggle("is-active", active);
    el.classList.toggle("is-reachable", reachable);
    // Số hiển thị = thứ tự ô trên thanh (1-4), không phải data-step nội bộ
    // (1,3,4,5 -- panel-2 không còn dùng trong giao diện Denoise).
    el.querySelector(".step-circle").textContent = complete && !active ? "✓" : String(idx + 1);
  });
}
function goStep(n) {
  if (n > state.maxReached) return;
  state.currentStep = n;
  document.querySelectorAll(".panel").forEach((p) => p.classList.remove("is-active"));
  $("panel-" + n).classList.add("is-active");
  // Rời Bước 5 thì đóng mọi hộp xác nhận đang mở (xoá nhóm / về dữ liệu gốc): con số
  // trong hộp chỉ đúng tại thời điểm tính, quay lại sau đó có thể đã cũ.
  if (n !== 5) {
    dismissResetConfirm();
    dismissAllHandlingConfirms();
    chDismissConfirm(); // hộp xác nhận xử lý Class Noise cũng đóng khi rời bước (số liệu trong hộp có thể cũ)
  }
  // Bước 3/4/5 có 2 khung con (attribute/class) nằm chung trong cùng 1
  // panel -- luôn gọi lại hàm chuyển nhánh mỗi lần VÀO bước đó, bất kể đi
  // tới bằng cách nào (bấm "Tiếp tục" hay bấm thẳng vào stepper phía trên),
  // để không bao giờ hiện sai nhánh.
  if (n === 3) toggleStep3Direction();
  if (n === 4) toggleStep4Direction();
  if (n === 5) toggleStep5Direction();
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
  // Chấm tròn trạng thái ở header do workspace.js lo (checkBackendHealth()
  // bên đó) -- ở đây chỉ cập nhật dòng ghi chú dưới ô kéo-thả của Bước 1.
  const notice = $("upload-notice");
  // Kết nối bình thường thì không hiện gì; chỉ báo khi mất kết nối.
  notice.hidden = state.backendAvailable;
  notice.textContent = state.backendAvailable
    ? ""
    : `Không kết nối được backend. Hãy chạy "python3 app.py" rồi thử lại.`;
}
function updateUploadButtonState() {
  // Chỉ cần đã chọn file. Trước đây còn đòi state.backendAvailable (kiểm tra kết nối chờ tối đa 1,5 giây):
  // server chậm lúc mới bật thì nút bị khoá và phải chọn file lần 2. Mất kết nối thật thì bấm tải lên sẽ báo lỗi rõ.
  $("upload-btn").disabled = !state.selectedFile;
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
  loadClassPreview(file); // hiện bảng xem trước dữ liệu như các tool khác
}

// ----- Xem trước dữ liệu ở Bước 1 (cùng cách các tool khác làm: workspace.js, cfInspect/showRawPreview) -----
// Nhờ backend đọc file (/api/noise-tools/inspect: dùng chung bộ đọc CSV/Excel với mọi tool nên cả Excel cũng xem được)
// rồi vẽ bảng bằng renderClassPreviewTable() bên dưới (KHÔNG dùng renderPreviewTable() của workspace.js: file này đã có 1 hàm
// cùng tên cho panel xem dữ liệu cũ, trong IIFE nên đè lên hàm kia). Chỉ để XEM -- tải lên thật vẫn qua /api/upload.
// classPreviewSeq: chọn file khác khi lần đọc trước chưa xong thì kết quả về muộn của file cũ bị bỏ.
let classPreviewSeq = 0;
// rows = [header, ...dòng], mọi ô là chuỗi. Cột đầu "Dòng" = số thứ tự 1,2,3... (cùng bảng xem trước của các tool khác).
function renderClassPreviewTable(table, rows) {
  const [header, ...body] = rows;
  table.innerHTML =
    "<thead><tr><th>Dòng</th>" + header.map((h) => `<th>${escapeHtml(h)}</th>`).join("") + "</tr></thead>" +
    "<tbody>" + body.map((row, i) => `<tr><td>${i + 1}</td>` + row.map((c) => `<td>${escapeHtml(c)}</td>`).join("") + "</tr>").join("") + "</tbody>";
}
function showClassPreview(label, dims, rows, note) {
  $("dropzone").hidden = true;
  $("class-raw-preview").hidden = false;
  $("class-raw-preview-label").textContent = label;
  $("class-raw-preview-dims").textContent = dims || "";
  const hasTable = !!(rows && rows.length);
  $("class-raw-preview-table-wrap").hidden = !hasTable;
  if (hasTable) renderClassPreviewTable($("class-raw-preview-table"), rows);
  else $("class-raw-preview-table").innerHTML = "";
  const noteEl = $("class-raw-preview-note");
  noteEl.hidden = !note;
  noteEl.textContent = note || "";
  noteEl.classList.toggle("is-only", !hasTable);
}
async function loadClassPreview(file) {
  const seq = ++classPreviewSeq;
  const sizeText = `${(file.size / 1024).toFixed(1)} KB`;
  showClassPreview(file.name, sizeText, null, "Đang đọc file…");
  const fd = new FormData();
  fd.append("file", file);
  let response, data;
  try {
    response = await fetch(`${API_BASE}/api/noise-tools/inspect`, { method: "POST", body: fd });
    data = await response.json();
  } catch (err) {
    if (seq === classPreviewSeq) showClassPreview(file.name, sizeText, null, "Không xem trước được file, nhưng vẫn tải lên được.");
    return;
  }
  if (seq !== classPreviewSeq) return;
  if (!response.ok) {
    showClassPreview(file.name, sizeText, null, data.error || "Không đọc được file.");
    return;
  }
  showClassPreview(file.name, `${data.row_count} dòng × ${data.columns.length} cột`, data.preview_rows, "");
}
// "↺ Đổi file": bỏ file đang chọn, trả lại ô kéo-thả. (Dữ liệu đã tải lên ở các bước sau không đổi cho tới khi tải file mới.)
$("class-change-file-btn").addEventListener("click", () => {
  classPreviewSeq++; // bỏ lần đọc đang chờ (nếu có)
  state.selectedFile = null;
  fileInput.value = "";
  $("class-raw-preview").hidden = true;
  $("dropzone").hidden = false;
  $("dropzone-idle").hidden = false;
  $("dropzone-file").hidden = true;
  setStatusMessage($("upload-status"), "", "");
  updateUploadButtonState();
});

$("upload-btn").addEventListener("click", async () => {
  const file = state.selectedFile;
  if (!file) return;

  setButtonLoading($("upload-btn"), true, "Đang tải lên…", "Tải lên & tiếp tục");

  const formData = new FormData();
  formData.append("file", file);

  let response;
  try {
    response = await fetch(`${API_BASE}/api/upload`, { method: "POST", body: formData });
  } catch (err) {
    setStatusMessage($("upload-status"), "Không gọi được backend. Kiểm tra xem python3 app.py có đang chạy không.", "error");
    setButtonLoading($("upload-btn"), false, "Đang tải lên…", "Tải lên & tiếp tục");
    return;
  }
  setButtonLoading($("upload-btn"), false, "Đang tải lên…", "Tải lên & tiếp tục");

  if (!response.ok) {
    let msg = "Tải lên thất bại, hãy kiểm tra lại file.";
    try { const err = await response.json(); if (err && err.error) msg = err.error; } catch (e) { /* giữ msg mặc định */ }
    setStatusMessage($("upload-status"), msg, "error");
    return;
  }

  const data = await response.json(); // { file_id, columns, row_count, guessed_dtypes }
  state.fileId = data.file_id;
  state.headers = data.columns;
  state.columnConfig = {};
  // guessed_dtypes: backend đã tự đoán kiểu dữ liệu hợp lý nhất cho từng cột
  // dựa trên giá trị thật (xem guess_column_dtype() trong app.py) -- dùng
  // làm dtype KHỞI ĐẦU cho mỗi cột, người dùng vẫn đổi lại được bình thường.
  state.headers.forEach(
    (h) => (state.columnConfig[h] = defaultColumnConfig((data.guessed_dtypes && data.guessed_dtypes[h]) || "text"))
  );
  $("rules-list").innerHTML = ""; // reset rule liên cột khi upload file mới
  state.hasWorkingCopy = false;
  state.appliedGroups = new Set();
  state.history = { entries: [], can_undo: false, undo_limit: 5 };
  // Upload file MỚI = bắt đầu lại từ đầu: phải xoá hết kết quả/cấu hình/lịch sử của
  // file CŨ và KHOÁ lại các bước phía sau (maxReached). Trước đây quên 2 việc này nên
  // bấm thẳng vào thanh bước 5 vẫn thấy nhóm lỗi + lịch sử của file cũ, và bấm
  // "Áp dụng" sẽ sửa nhầm lên dữ liệu file mới (cùng số dòng nhưng khác nội dung).
  state.maxReached = 1;
  state.lastColumnConfigs = [];
  state.lastDuplicateConfig = null;
  state.lastFindings = [];
  state.lastFlaggedRows = [];
  state.rowFindingsMap = new Map();
  state.handlingBusy = false;
  $("handling-list").innerHTML = "";
  dismissResetConfirm();
  setStatusMessage($("history-status"), "", "");
  renderHistoryBar();

  // Reset TOÀN BỘ state riêng của Class Noise khi upload file MỚI -- nếu
  // không, cột đã tích (classFeatureColumns) hoặc cột nhãn (classLabelColumn)
  // của file CŨ sẽ sót lại nguyên vẹn (vd "V44" của bộ dữ liệu thầy) và bị
  // gửi nhầm lên server khi detect trên file MỚI, dù UI không hề hiện nó
  // trong danh sách (chỉ các cột của file mới mới được vẽ ra) -- nhẹ thì bị
  // chặn báo lỗi "cột không tồn tại", nặng hơn là ÂM THẦM dùng nhầm lựa chọn
  // cũ nếu 2 file tình cờ trùng tên cột, cho kết quả sai mà không ai biết.
  state.classLabelColumn = null;
  state.classFeatureColumns = new Set();
  state.classDiagnostics = null;
  state.classFindings = [];
  state.classMethodFindings = {};
  state.classMoreOpen = false;
  state.classMorePages = {};
  state.classFindingsPage = 1;
  state.classFindingsFilterText = "";
  chResetAll(); // file mới -> bỏ lựa chọn/lịch sử xử lý Class Noise của file cũ
  state.classPreprocess = null;

  setStatusMessage($("upload-status"), `Đã tải lên: ${data.row_count} dòng, ${data.columns.length} cột.`, "ok");
  // Không còn bước "Hướng xử lý": hướng luôn là Class Noise, sang thẳng bước
  // chọn nhãn & đặc trưng (panel nội bộ số 3 = ô thứ 2 trên thanh).
  state.direction = "class";
  unlockStep(3);
  goStep(3);
});

// ====== BƯỚC 2 (cũ): chọn hướng xử lý ======
// KHÔNG còn dùng trong Denoise: hướng luôn là Class Noise và Class Noise chỉ còn 1 cách phát hiện (bộ kết hợp),
// nên không còn thẻ hướng / thẻ phương pháp. Giữ nút ẩn #continue-step2-btn vì HTML vẫn có (panel-2 rỗng).
$("continue-step2-btn").addEventListener("click", () => {
  if (!state.direction) return;
  unlockStep(3);
  if (state.direction === "attribute") renderColumnList();
  goStep(3); // goStep() tự gọi toggleStep3Direction() -> dựng form class nếu cần
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
  // Bỏ khỏi bộ lọc các loại đã biến mất (vd vừa xoá hết dòng trùng ở Bước 5): nếu không,
  // bảng cứ trống vì lọc theo 1 loại mà chip của loại đó không còn để bấm bỏ lọc.
  state.resultsFilter.types.forEach((t) => {
    if (!present.has(t)) state.resultsFilter.types.delete(t);
  });
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
  renderNoiseTypeChart(data.findings);
  renderResultsTable();
}

// Biểu đồ cột ngang: đếm số finding theo từng loại noise, sắp xếp giảm dần.
// CHỈ đọc lại data.findings đã có sẵn trong bộ nhớ (không gọi thêm API nào,
// không thay đổi logic detect/xử lý) -- thuần hiển thị trực quan hơn.
function renderNoiseTypeChart(findings) {
  const card = $("noise-chart-card");
  const wrap = $("noise-chart");
  if (!findings.length) {
    card.hidden = true;
    wrap.innerHTML = "";
    return;
  }

  const counts = new Map();
  findings.forEach((f) => counts.set(f.noise_type, (counts.get(f.noise_type) || 0) + 1));
  const rows = Array.from(counts.entries()).sort((a, b) => b[1] - a[1]);
  const maxCount = rows[0][1];

  wrap.innerHTML = rows
    .map(([type, count]) => {
      const meta = noiseMeta(type);
      const pct = Math.max(4, Math.round((count / maxCount) * 100));
      return `
        <div class="chart-row">
          <span class="chart-label">${meta.label}</span>
          <span class="chart-bar-track"><span class="chart-bar-fill" style="width:${pct}%; background: var(--${meta.family}-border);"></span></span>
          <span class="chart-count">${count}</span>
        </div>`;
    })
    .join("");
  card.hidden = false;
}

$("goto-handling-btn").addEventListener("click", () => {
  unlockStep(5);
  renderHandlingSection();
  setStatusMessage($("history-status"), "", ""); // thông báo "Đã hoàn tác..." của lần trước không còn nghĩa nữa
  renderHistoryBar();
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
  fixed_value: "✏️ Tự nhập tay (giá trị cố định)",
  cap_to_range: "Cắt về biên hợp lệ (cap)",
  auto_normalize_category: "Tự động chuẩn hoá về giá trị chuẩn",
  auto_clean_whitespace: "Tự động dọn khoảng trắng/ký tự lạ",
  keep: "Giữ nguyên (không sửa)",
};

// ---- Bước 5 AN TOÀN: không có hành động mặc định nguy hiểm ----
// Trước đây dropdown luôn lấy hành động ĐẦU TIÊN trong ACTION_TABLE, tức
// "Xoá cả dòng" (remove_row) -- cộng với việc mọi checkbox đều tick sẵn, chỉ
// 1 cú bấm "Áp dụng" là xoá sạch cả nhóm. Giờ dropdown mặc định là lựa chọn
// trống "— Chọn cách xử lý —" (value rỗng, bị disabled nên không chọn lại
// được sau khi đã chọn); người dùng PHẢI chọn rõ ràng thì mới Áp dụng được.
// NGOẠI LỆ: hành động tự động an toàn (auto_*, vd dọn khoảng trắng, chuẩn hoá
// category) thì chọn sẵn -- theo quyết định #6 trong CLAUDE.md đó là xử lý
// "an toàn, mặc định luôn bật", không xoá dữ liệu.
function pickDefaultAction(availableActions) {
  return availableActions.find((a) => a.startsWith("auto_")) || "";
}
function actionOptionsHTML(availableActions, selectedAction) {
  const placeholder = `<option value="" disabled ${selectedAction ? "" : "selected"}>— Chọn cách xử lý —</option>`;
  const options = availableActions
    .map((a) => `<option value="${a}" ${a === selectedAction ? "selected" : ""}>${ACTION_LABELS[a]}</option>`)
    .join("");
  return placeholder + options;
}

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
    // key = "tên cột|loại noise". Tên CỘT có thể chứa "|" (vd "a|b") còn loại noise thì
    // không bao giờ chứa -> cắt tại dấu "|" CUỐI CÙNG, không phải dấu đầu tiên (cắt ở dấu
    // đầu làm nhóm của cột đó biến mất khỏi Bước 5, không xử lý được).
    const sep = key.lastIndexOf("|");
    const column = key.slice(0, sep);
    const noiseType = key.slice(sep + 1);
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
            ${actionOptionsHTML(availableActions, pickDefaultAction(availableActions))}
          </select>
        </label>
        <button type="button" class="btn btn-ghost handling-apply-btn">Áp dụng</button>
        <button type="button" class="btn btn-ghost handling-preview-btn" ${alreadyApplied ? "" : "hidden"}>👁 Xem sau xử lý</button>
      </div>
      <p class="status-text handling-row-status" aria-live="polite"></p>
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
      <p class="status-text handling-row-status" aria-live="polite"></p>
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
//   2. Có thêm 1 cột "Tự điều chỉnh" bên PHẢI noise_reasons -- mỗi dòng có 1
//      dropdown hành động RIÊNG (không dùng chung 1 hành động cho cả nhóm
//      như trước), để 2 dòng cùng loại lỗi vẫn có thể xử lý khác nhau trong
//      CÙNG 1 lần bấm Áp dụng -- kể cả sửa TAY (chọn "Tự nhập tay" rồi gõ
//      thẳng giá trị cho riêng dòng đó). Cột này CỐ ĐỊNH bên phải
//      (position: sticky, xem .handling-action-col trong style.css) để luôn
//      nhìn thấy được mà không cần cuộn ngang qua hết chục cột dữ liệu --
//      trước đó bị khuất bên phải khiến người dùng tưởng chưa có tính năng
//      này. availableActions = null (dùng cho duplicate_row) thì bỏ hẳn cột
//      này -- trùng dòng chỉ có đúng 1 việc hợp lý là xoá.
function pendingRowHTML(r, dataColumns, availableActions, defaultChecked, defaultAction) {
  const checkboxCell = `<td><input type="checkbox" class="handling-row-check" data-row-number="${r.row_number}" ${defaultChecked ? "checked" : ""} /></td>`;
  let html = rowToTableRowHTML(r, dataColumns).replace(
    "<tr>",
    `<tr data-row-number="${r.row_number}">${checkboxCell}`
  );
  if (availableActions) {
    const options = actionOptionsHTML(availableActions, defaultAction);
    const actionCell = `<td class="handling-action-col">
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
    (availableActions ? '<th class="handling-action-col">Tự điều chỉnh</th>' : "") +
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
    // Bỏ lựa chọn trống "— Chọn cách xử lý —" (value rỗng) khỏi danh sách hành động thật.
    const availableActions = Array.from(row.querySelectorAll(".handling-action option"))
      .map((o) => o.value)
      .filter(Boolean);
    const defaultAction = row.querySelector(".handling-action").value; // "" nếu người dùng chưa chọn hàng loạt
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
  // Người dùng vừa đổi tick/dropdown trong 1 nhóm -> hộp "Sẽ xoá N dòng..." đang
  // hiện (nếu có) đã tính cho lựa chọn CŨ, không còn đúng nữa -> đóng lại, bắt
  // buộc bấm "Áp dụng" lần nữa để xem con số mới (tránh xác nhận nhầm số cũ).
  const changedGroup = e.target.closest(".handling-row");
  if (changedGroup) {
    dismissHandlingConfirm(changedGroup);
    clearGroupError(changedGroup);
  }

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
    e.target.classList.remove("is-invalid"); // đã chọn rồi -> bỏ viền đỏ "chưa chọn"
    tr.querySelector(".handling-row-fixed-value").classList.remove("is-invalid"); // đổi hành động thì ô giá trị không còn bị tính là "thiếu"
  }
});
// Gõ vào ô "giá trị" của 1 dòng: bỏ viền đỏ "chưa nhập" và đóng hộp xác nhận cũ.
$("handling-list").addEventListener("input", (e) => {
  if (!e.target.classList.contains("handling-row-fixed-value")) return;
  e.target.classList.remove("is-invalid");
  const group = e.target.closest(".handling-row");
  if (group) {
    dismissHandlingConfirm(group);
    clearGroupError(group);
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
  applyFreshRowsToGroupTable(row, rowNumbers, byRowNumber);

  // 1 dòng có thể dính NHIỀU loại lỗi khác nhau -> xuất hiện ở NHIỀU khung
  // riêng biệt cùng lúc (xem rowsForHandlingKey()). Khung vừa Áp dụng đã cập
  // nhật ở trên rồi, nhưng các khung KHÁC đang mở sẵn (đã render từ trước)
  // nếu cũng đang hiện CHÍNH các dòng vừa xử lý thì bảng của chúng sẽ bị "cũ"
  // (vẫn hiện dòng đã xoá/giá trị cũ) -- quét qua, CHỈ cập nhật đúng những
  // khung thật sự có liên quan (dò bằng querySelector `tr[data-row-number]`),
  // KHÔNG rebuild/tính lại các khung không dính dáng gì, và dùng lại ĐÚNG 1
  // lần gọi API ở trên (byRowNumber) thay vì gọi lại cho từng khung -- đỡ tốn
  // tài nguyên cả phía trình duyệt lẫn server.
  document.querySelectorAll("#handling-list > .handling-row").forEach((otherRow) => {
    if (otherRow === row) return;
    const otherDetail = otherRow.querySelector(".handling-detail");
    if (!otherDetail || otherDetail.dataset.rendered !== "true") return; // chưa mở -> lần mở đầu tiên sẽ tự đọc state mới nhất, không cần đụng vào
    const touchesSharedRow = rowNumbers.some((rn) => otherDetail.querySelector(`tr[data-row-number="${rn}"]`));
    if (!touchesSharedRow) return;
    applyFreshRowsToGroupTable(otherRow, rowNumbers, byRowNumber);
    updateGroupSummaryAfterApply(otherRow);
  });
}

// Phần "ghi dữ liệu mới vào đúng các <tr> trong 1 bảng chi tiết" -- tách
// riêng khỏi refreshHandledRowsInPlace() để dùng lại được cho CẢ khung vừa
// Áp dụng LẪN các khung khác đang mở sẵn có chung dòng, mà chỉ cần 1 lần gọi
// API (xem comment ở refreshHandledRowsInPlace()).
function applyFreshRowsToGroupTable(row, rowNumbers, byRowNumber) {
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
    // Vẫn còn bị gắn cờ ĐÚNG loại lỗi của CHÍNH khung này (vd dòng này dính
    // cả age lẫn gender, vừa xử lý xong age thì khung age đánh dấu "đã xử
    // lý", nhưng khung gender vẫn phải giữ checkbox/dropdown hoạt động bình
    // thường vì gender CHƯA được xử lý) -- không đánh dấu "Đã xử lý" vội.
    if (stillFlagged) return;
    const cells = dataColumns
      .map((c) => `<td>${escapeHtml(String(freshRow[c] === undefined || freshRow[c] === null ? "" : freshRow[c]))}</td>`)
      .join("");
    const trailingCell = isDuplicate ? "" : '<td class="handling-action-col"></td>'; // giữ đúng số cột + đúng vị trí dính bên phải với cột "Tự điều chỉnh" (nếu có)
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

// ---- Thông báo inline cho từng nhóm (thay cho alert() của trình duyệt) ----
// kind: "error" (chữ đỏ) | "ok" (chữ teal) | "" (mặc định, xám). Hiện ngay
// trong nhóm gây ra thông báo nên người dùng không phải đóng hộp thoại nào,
// và vẫn nhìn thấy bảng + dòng bị lỗi khi đọc.
function setStatusMessage(el, text, kind) {
  el.textContent = text;
  el.classList.toggle("is-error", kind === "error");
  el.classList.toggle("is-ok", kind === "ok");
}

// Bước 5 AN TOÀN, lớp 1 (xem pickDefaultAction): trước khi gửi bất cứ thứ gì
// lên server, kiểm tra MỌI dòng đang tick đã chọn cách xử lý chưa, và nếu chọn
// "Tự nhập tay" thì đã gõ giá trị chưa (giá trị rỗng sẽ GHI ĐÈ ô thành chuỗi
// rỗng -- tức là âm thầm biến ô thành "thiếu giá trị"). Dòng nào thiếu thì
// tô viền đỏ ô đó. Trả về số lỗi + ô đầu tiên bị thiếu (để focus).
function validateRowActions(checkedTrs) {
  let missingAction = 0;
  let missingValue = 0;
  let firstInvalid = null;
  checkedTrs.forEach((tr) => {
    const actionSelect = tr.querySelector(".handling-row-action");
    const valueInput = tr.querySelector(".handling-row-fixed-value");
    actionSelect.classList.remove("is-invalid");
    valueInput.classList.remove("is-invalid");
    if (!actionSelect.value) {
      actionSelect.classList.add("is-invalid");
      missingAction += 1;
      firstInvalid = firstInvalid || actionSelect;
    } else if (actionSelect.value === "fixed_value" && valueInput.value.trim() === "") {
      valueInput.classList.add("is-invalid");
      missingValue += 1;
      firstInvalid = firstInvalid || valueInput;
    }
  });
  return { missingAction, missingValue, firstInvalid };
}

// Body gửi lên /api/apply-handling-partial -- dùng CHUNG cho lượt chạy thử
// (dry_run: true, chỉ tính "sẽ xoá bao nhiêu") lẫn lượt chạy thật, để 2 lượt
// luôn gửi đúng cùng 1 nội dung và con số xem trước khớp với kết quả thật.
function buildApplyBody(row, rowsPayload, isDuplicate, dryRun) {
  return {
    file_id: state.fileId,
    column_configs: state.lastColumnConfigs,
    cross_field_rules: [],
    duplicate_row: state.lastDuplicateConfig,
    column: isDuplicate ? null : row.dataset.column,
    noise_type: isDuplicate ? "duplicate_row" : row.dataset.noiseType,
    rows: rowsPayload,
    dry_run: dryRun,
  };
}

// Gọi /api/apply-handling-partial, trả về { data } nếu thành công hoặc { error }
// (chuỗi thông báo đã sẵn sàng hiện cho người dùng) nếu lỗi mạng/backend.
async function postApplyHandling(body) {
  let response;
  try {
    response = await fetch(`${API_BASE}/api/apply-handling-partial`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch (err) {
    return { error: "Không gọi được backend. Kiểm tra xem python3 app.py có đang chạy không." };
  }
  if (!response.ok) {
    let message = "Xử lý thất bại, kiểm tra console/backend log.";
    try {
      const errorData = await response.json();
      if (errorData.error) message = errorData.error;
    } catch (parseErr) {
      /* giữ message mặc định */
    }
    return { error: message };
  }
  return { data: await response.json() };
}

// ---- Khoá thao tác khi server đang bận ----
// Mọi lệnh làm đổi dữ liệu ở Bước 5 (chạy thử, áp dụng, hoàn tác, về dữ liệu gốc) chạy
// TUẦN TỰ từng lệnh một: bấm lệnh thứ hai khi lệnh đầu chưa xong sẽ bị bỏ qua. Nếu cho
// chạy chồng nhau thì 2 phản hồi có thể về lệch thứ tự và giao diện hiện trạng thái khác
// hẳn server (vd bấm Hoàn tác lúc Áp dụng còn đang chờ -> giao diện hiện 2 bước lịch
// sử trong khi server chỉ có 1). Class `is-busy` (xem style.css) chặn thêm chuột; còn
// phím Enter/Space vẫn bấm được nút nên PHẢI chặn cả ở đây bằng cờ state.handlingBusy.
async function withHandlingLock(task) {
  if (state.handlingBusy) return undefined;
  state.handlingBusy = true;
  $("panel-5-attribute").classList.add("is-busy");
  try {
    return await task();
  } finally {
    state.handlingBusy = false;
    $("panel-5-attribute").classList.remove("is-busy");
  }
}

// Các <tr> đang được tick trong bảng chi tiết của 1 nhóm + payload gửi server tương ứng
// (mỗi dòng 1 hành động riêng). Tách riêng để có thể TÍNH LẠI sau khi chạy thử và so
// với lúc bấm (xem applyGroupFlow()).
function getCheckedRows(row) {
  return Array.from(row.querySelectorAll(".handling-detail .handling-row-check:checked")).map((cb) =>
    cb.closest("tr")
  );
}
function buildRowsPayload(checkedTrs, isDuplicate) {
  return checkedTrs.map((tr) => {
    const rowNumber = parseInt(tr.dataset.rowNumber, 10);
    if (isDuplicate) return { row_number: rowNumber, action: "remove_row" };
    const action = tr.querySelector(".handling-row-action").value;
    const item = { row_number: rowNumber, action };
    if (action === "fixed_value") item.fixed_value = tr.querySelector(".handling-row-fixed-value").value;
    return item;
  });
}

// ---- Bước 5 AN TOÀN, lớp 2: xem trước tác động rồi mới xác nhận ----
// Hộp "Sẽ xoá N dòng (a → b). [Xác nhận xoá] [Huỷ]" hiện NGAY TRONG nhóm vừa
// bấm Áp dụng, chỉ xuất hiện khi hành động thật sự xoá dòng (sửa giá trị thì
// chạy luôn, vì đã có nút Hoàn tác và dòng "Đã xử lý").
function dismissHandlingConfirm(row) {
  const box = row.querySelector(".handling-confirm");
  if (box) box.remove();
}
// Đóng hộp xác nhận của MỌI nhóm -- gọi sau khi dữ liệu đã đổi (do nhóm khác Áp dụng):
// con số "313 → 309" trong các hộp còn lại đã cũ, xác nhận theo số cũ sẽ gây hiểu nhầm.
function dismissAllHandlingConfirms() {
  document.querySelectorAll("#handling-list .handling-confirm").forEach((box) => box.remove());
}
// Xoá thông báo LỖI cũ của nhóm khi người dùng bắt đầu sửa lựa chọn (thông báo thành
// công/trung tính thì giữ nguyên).
function clearGroupError(group) {
  const statusEl = group.querySelector(".handling-row-status");
  if (statusEl && statusEl.classList.contains("is-error")) setStatusMessage(statusEl, "", "");
}

function showHandlingConfirm(row, preview, rowsPayload, isDuplicate) {
  dismissHandlingConfirm(row);
  const rowsRemoved = Number(preview.rows_removed);
  const cellsChanged = Number(preview.cells_changed);
  const effects = [`xoá <strong>${rowsRemoved}</strong> dòng`];
  if (cellsChanged > 0) effects.push(`sửa <strong>${cellsChanged}</strong> ô`);

  const box = document.createElement("div");
  box.className = "handling-confirm";
  box.setAttribute("role", "alert");
  box.innerHTML = `
    <span class="handling-confirm-text">⚠ Sẽ ${effects.join(" và ")}
      (${Number(preview.rows_before)} → ${Number(preview.rows_after)} dòng).</span>
    <button type="button" class="btn btn-danger btn-small handling-confirm-yes">Xác nhận xoá</button>
    <button type="button" class="btn btn-ghost btn-small handling-confirm-no">Huỷ</button>
  `;
  row.querySelector(".handling-row-top").insertAdjacentElement("afterend", box);

  const yesBtn = box.querySelector(".handling-confirm-yes");
  const noBtn = box.querySelector(".handling-confirm-no");
  noBtn.addEventListener("click", () => dismissHandlingConfirm(row));
  yesBtn.addEventListener("click", async () => {
    if (state.handlingBusy) return; // có lệnh khác đang chạy -> bỏ qua cú bấm này
    yesBtn.disabled = true;
    noBtn.disabled = true;
    await withHandlingLock(() => runGroupApply(row, rowsPayload, isDuplicate));
    dismissHandlingConfirm(row);
  });
  noBtn.focus(); // focus vào "Huỷ" (lựa chọn an toàn) -- muốn xoá phải chủ động bấm "Xác nhận xoá"
}

// Bấm "Áp dụng" trên 1 nhóm cụ thể -- CHỈ xử lý các dòng đang được tick trong
// bảng chi tiết của CHÍNH nhóm đó (mở ra hộ nếu đang đóng), MỖI DÒNG dùng
// đúng hành động dropdown RIÊNG của chính nó (không còn dùng chung 1 hành
// động cho cả nhóm). Luồng an toàn (xem pickDefaultAction):
//   1. mọi dòng tick phải ĐÃ chọn cách xử lý (validateRowActions), thiếu thì dừng;
//   2. nếu có hành động XOÁ dòng (hoặc là nhóm trùng dòng) -> chạy thử (dry_run)
//      để hiện "Sẽ xoá N dòng", chỉ chạy thật khi người dùng bấm "Xác nhận xoá";
//   3. sửa giá trị thì chạy thật luôn.
// Cả luồng chạy trong withHandlingLock() nên không bị lệnh khác chen vào giữa.
async function handleGroupApply(row) {
  await withHandlingLock(() => applyGroupFlow(row));
}

async function applyGroupFlow(row) {
  const isDuplicate = row.dataset.duplicateRow === "true";
  const statusEl = row.querySelector(".handling-row-status");
  dismissHandlingConfirm(row);
  setStatusMessage(statusEl, "", "");
  if (row.querySelector(".handling-detail").hidden) openHandlingDetail(row);

  const checkedTrs = getCheckedRows(row);
  if (checkedTrs.length === 0) {
    setStatusMessage(statusEl, "Hãy tick ít nhất 1 dòng để xử lý.", "error");
    return;
  }

  if (!isDuplicate) {
    const check = validateRowActions(checkedTrs);
    if (check.missingAction + check.missingValue > 0) {
      const problems = [];
      if (check.missingAction > 0) {
        problems.push(
          `còn ${check.missingAction} dòng chưa chọn cách xử lý (chọn ở cột "Tự điều chỉnh" hoặc dùng "Đặt hàng loạt")`
        );
      }
      if (check.missingValue > 0) {
        problems.push(`${check.missingValue} dòng chọn "Tự nhập tay" nhưng chưa nhập giá trị`);
      }
      setStatusMessage(statusEl, `⚠ Chưa thể áp dụng: ${problems.join("; ")}.`, "error");
      check.firstInvalid.focus();
      return;
    }
  }

  const rowsPayload = buildRowsPayload(checkedTrs, isDuplicate);
  const needsConfirm = isDuplicate || rowsPayload.some((r) => r.action === "remove_row");
  if (!needsConfirm) {
    await runGroupApply(row, rowsPayload, isDuplicate);
    return;
  }

  // Có xoá dòng -> chạy thử trước. Lượt chạy thử KHÔNG ghi gì lên server.
  const applyBtn = row.querySelector(".handling-apply-btn");
  const normalLabel = applyBtn.textContent;
  setButtonLoading(applyBtn, true, "Đang kiểm tra...", normalLabel);
  const result = await postApplyHandling(buildApplyBody(row, rowsPayload, isDuplicate, true));
  setButtonLoading(applyBtn, false, "Đang kiểm tra...", normalLabel);
  if (result.error) {
    setStatusMessage(statusEl, result.error, "error");
    return;
  }

  // Trong lúc chờ chạy thử, người dùng vẫn có thể đổi tick/dropdown bằng bàn phím. Con số
  // vừa tính là cho lựa chọn CŨ -> nếu lựa chọn đã khác thì bỏ, bắt bấm Áp dụng lại, để
  // nút "Xác nhận xoá" không bao giờ xoá khác với điều người dùng đang thấy trên màn hình.
  const nowPayload = buildRowsPayload(getCheckedRows(row), isDuplicate);
  if (JSON.stringify(nowPayload) !== JSON.stringify(rowsPayload)) {
    setStatusMessage(statusEl, 'Lựa chọn đã thay đổi trong lúc kiểm tra — hãy bấm "Áp dụng" lại.', "error");
    return;
  }

  const preview = result.data;
  if (preview.rows_removed === 0 && preview.cells_changed === 0) {
    setStatusMessage(statusEl, "Không có thay đổi nào để áp dụng (các dòng đã chọn không còn trong dữ liệu).", "");
    return;
  }
  if (preview.rows_removed === 0) {
    // Có hành động "xoá" nhưng dòng đó đã bị xoá từ trước -> thực tế chỉ sửa ô, không mất dòng nào.
    await runGroupApply(row, rowsPayload, isDuplicate);
    return;
  }
  showHandlingConfirm(row, preview, rowsPayload, isDuplicate);
}

// Cập nhật chữ đếm ở đầu các nhóm CHƯA MỞ bảng chi tiết, dựa trên kết quả detect mới nhất
// (state.lastFindings). Nhóm đã mở có đường cập nhật riêng (updateGroupSummaryAfterApply);
// còn nhóm chưa mở sẽ hiện số cũ nếu không làm bước này (vd dòng của nó vừa bị xoá ở nhóm khác).
function refreshUnopenedGroupSummaries() {
  document.querySelectorAll("#handling-list > .handling-row").forEach((groupRow) => {
    const detail = groupRow.querySelector(".handling-detail");
    if (detail && detail.dataset.rendered === "true") return;
    const isDuplicate = groupRow.dataset.duplicateRow === "true";
    const count = state.lastFindings.filter((f) =>
      isDuplicate
        ? f.noise_type === "duplicate_row"
        : f.column === groupRow.dataset.column && f.noise_type === groupRow.dataset.noiseType
    ).length;
    const summaryText = groupRow.querySelector(".handling-row-summary .status-text");
    if (count === 0) {
      summaryText.textContent = "(Đã xử lý xong toàn bộ ✓)";
      groupRow.querySelector(".handling-apply-btn").disabled = true;
      const bulkSelect = groupRow.querySelector(".handling-action");
      if (bulkSelect) bulkSelect.disabled = true;
    } else {
      summaryText.textContent = isDuplicate
        ? `(${count} dòng — mặc định tick sẵn các bản TRÙNG SAU, bỏ tick bản bạn muốn giữ)`
        : `(${count} ô — bấm để xem/tick từng dòng)`;
    }
  });
}

// Gửi lệnh Áp dụng THẬT lên server rồi cập nhật giao diện tại chỗ. Luôn gọi bên trong
// withHandlingLock().
async function runGroupApply(row, rowsPayload, isDuplicate) {
  const applyBtn = row.querySelector(".handling-apply-btn");
  const statusEl = row.querySelector(".handling-row-status");
  const normalLabel = applyBtn.textContent;
  setButtonLoading(applyBtn, true, "Đang xử lý...", normalLabel);
  setStatusMessage(statusEl, "", "");
  setStatusMessage($("history-status"), "", ""); // thông báo "Đã hoàn tác..." cũ hết nghĩa khi có thao tác mới

  const result = await postApplyHandling(buildApplyBody(row, rowsPayload, isDuplicate, false));
  setButtonLoading(applyBtn, false, "Đang xử lý...", normalLabel);
  if (result.error) {
    setStatusMessage(statusEl, result.error, "error");
    return;
  }

  const data = result.data;
  // Server báo tác động THẬT của lần này. Nếu cả 2 đều bằng 0 (vd chọn "Giữ nguyên", hoặc
  // các dòng đã được xử lý từ trước) thì KHÔNG được báo "✅ Đã xử lý" -- sai sự thật.
  // Server cũ không có field này -> coi như có thay đổi để giữ hành vi cũ.
  const applied = data.applied || { rows_removed: 1, cells_changed: 0 };
  const changedAnything = applied.rows_removed > 0 || applied.cells_changed > 0;

  state.lastFindings = data.findings;
  state.lastFlaggedRows = data.flagged_rows;
  state.rowFindingsMap = buildRowFindingsMap(data.findings);
  if (data.history) state.history = data.history;
  if (changedAnything) {
    state.hasWorkingCopy = true;
    state.appliedGroups.add(isDuplicate ? "duplicate_row" : `${row.dataset.column}|${row.dataset.noiseType}`);
    dismissAllHandlingConfirms(); // dữ liệu đã đổi -> số liệu trong hộp xác nhận của nhóm khác đã cũ
  }
  renderHistoryBar();

  await refreshHandledRowsInPlace(row, rowsPayload.map((r) => r.row_number));
  updateGroupSummaryAfterApply(row);
  refreshUnopenedGroupSummaries();

  if (changedAnything) {
    const effects = [];
    if (applied.rows_removed > 0) effects.push(`xoá ${applied.rows_removed} dòng`);
    if (applied.cells_changed > 0) effects.push(`sửa ${applied.cells_changed} ô`);
    setStatusMessage(statusEl, `✅ Đã áp dụng: ${effects.join(", ")}.`, "ok");
    row.querySelector(".handling-preview-btn").hidden = false;
  } else {
    setStatusMessage(
      statusEl,
      'Không có thay đổi nào được ghi (vd chọn "Giữ nguyên", hoặc các dòng đã chọn đã được xử lý trước đó).',
      ""
    );
  }

  // Chỉ cập nhật số liệu Bước 4 (để xem lại vẫn đúng), KHÔNG rebuild lại
  // Bước 5 -- bảng chi tiết vừa cập nhật ở trên vẫn giữ nguyên, không "biến mất".
  renderStep4({ total_rows: data.total_rows, total_flagged_rows: data.total_flagged_rows, findings: data.findings });
}

// ---- Bước 5 AN TOÀN, lớp 3: thanh "Lịch sử" + Hoàn tác + Về dữ liệu gốc ----
// Mô tả 1 bước trong nhật ký bằng chữ dễ đọc, vd "age (Thiếu giá trị): xoá 4 dòng".
// Mọi chuỗi từ server đều đi qua escapeHtml() trước khi chèn vào HTML.
function describeHistoryEntry(entry) {
  const target = entry.column
    ? `<strong>${escapeHtml(entry.column)}</strong> (${escapeHtml(noiseMeta(entry.noise_type).label)})`
    : "<strong>Trùng dòng</strong>";
  const effects = [];
  if (entry.rows_removed > 0) effects.push(`xoá ${Number(entry.rows_removed)} dòng`);
  if (entry.cells_changed > 0) effects.push(`sửa ${Number(entry.cells_changed)} ô`);
  const actions = Object.entries(entry.actions || {})
    .map(([action, count]) => `${escapeHtml(ACTION_LABELS[action] || action)} ×${Number(count)}`)
    .join("; ");
  return `${target}: ${effects.join(", ")} <span class="history-actions">— ${actions}</span>`;
}

function renderHistoryBar() {
  // Lịch sử vừa đổi (áp dụng thêm, hoàn tác, upload file mới...) -> hộp xác nhận "Về dữ
  // liệu gốc" đang mở (nếu có) đã ghi số bước cũ, đóng lại cho khỏi xác nhận nhầm số cũ.
  dismissResetConfirm();
  const entries = state.history.entries;
  const list = $("history-log");
  if (entries.length === 0) {
    list.innerHTML = '<li class="history-log-empty">Chưa có thay đổi nào — dữ liệu đang là bản gốc.</li>';
  } else {
    // Mới nhất ở trên cùng; bước trên cùng chính là bước nút "Hoàn tác" sẽ lùi lại.
    list.innerHTML = entries
      .slice()
      .reverse()
      .map((entry, i) => {
        const note = entry.undoable ? "" : ' <span class="history-actions">(không hoàn tác được)</span>';
        return `<li class="history-log-item${i === 0 ? " is-latest" : ""}">${describeHistoryEntry(entry)}${note}</li>`;
      })
      .join("");
  }
  $("undo-btn").disabled = !state.history.can_undo;
  $("reset-btn").disabled = entries.length === 0;
  // Còn bước trong nhật ký mà hết hoàn tác được (quá 5 bước, hoặc bảng quá lớn) -> nói rõ
  // lý do nút Hoàn tác bị tắt thay vì để người dùng tự đoán.
  $("history-hint").textContent =
    entries.length > 0 && !state.history.can_undo
      ? 'Không hoàn tác thêm được (chỉ nhớ ' + state.history.undo_limit + ' bước gần nhất, hoặc bảng quá lớn) — dùng "Về dữ liệu gốc".'
      : `Hoàn tác được ${state.history.undo_limit} bước gần nhất.`;
}

function dismissResetConfirm() {
  $("history-confirm").hidden = true;
  $("history-confirm").innerHTML = "";
}

// Gọi 1 trong 2 route lùi lại (/api/undo-handling hoặc /api/reset-working). Server
// trả về kết quả detect trên dữ liệu SAU khi lùi lại + lịch sử mới -> dựng lại
// toàn bộ danh sách nhóm ở Bước 5 và số liệu Bước 4 cho khớp (khác "Áp dụng" là
// chỉ cập nhật tại chỗ, vì lùi lại có thể làm 1 nhóm đã "xong" có lỗi trở lại).
// Chạy trong withHandlingLock() nên không bị Áp dụng/lệnh khác chen vào giữa.
async function runHistoryAction(path, successMessage) {
  await withHandlingLock(async () => {
    const statusEl = $("history-status");
    $("undo-btn").disabled = true;
    $("reset-btn").disabled = true;
    setStatusMessage(statusEl, "Đang xử lý...", "");

    let response;
    try {
      response = await fetch(`${API_BASE}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          file_id: state.fileId,
          column_configs: state.lastColumnConfigs,
          cross_field_rules: [],
          duplicate_row: state.lastDuplicateConfig,
        }),
      });
    } catch (err) {
      setStatusMessage(statusEl, "Không gọi được backend.", "error");
      renderHistoryBar();
      return;
    }
    if (!response.ok) {
      let message = "Thao tác thất bại, kiểm tra console/backend log.";
      try {
        const errorData = await response.json();
        if (errorData.error) message = errorData.error;
      } catch (parseErr) {
        /* giữ message mặc định */
      }
      setStatusMessage(statusEl, message, "error");
      renderHistoryBar();
      return;
    }

    const data = await response.json();
    state.lastFindings = data.findings;
    state.lastFlaggedRows = data.flagged_rows;
    state.rowFindingsMap = buildRowFindingsMap(data.findings);
    state.history = data.history;
    state.hasWorkingCopy = data.history.entries.length > 0;
    // Nhóm nào còn nằm trong lịch sử thì vẫn coi là "đã xử lý" (hiện nút "Xem sau xử lý").
    state.appliedGroups = new Set(data.history.entries.map((e) => e.group_key));

    renderStep4({ total_rows: data.total_rows, total_flagged_rows: data.total_flagged_rows, findings: data.findings });
    renderHandlingSection();
    renderHistoryBar();
    setStatusMessage(statusEl, successMessage, "ok");
  });
}

$("undo-btn").addEventListener("click", () => {
  if (state.handlingBusy) return;
  dismissResetConfirm();
  runHistoryAction("/api/undo-handling", "✅ Đã hoàn tác 1 bước.");
});
$("reset-btn").addEventListener("click", () => {
  if (state.handlingBusy) return;
  const box = $("history-confirm");
  const count = state.history.entries.length;
  box.innerHTML = `
    <span class="handling-confirm-text">⚠ Bỏ toàn bộ <strong>${count}</strong> bước xử lý và quay về dữ liệu gốc đã tải lên?</span>
    <button type="button" class="btn btn-danger btn-small" id="reset-confirm-yes">Xác nhận</button>
    <button type="button" class="btn btn-ghost btn-small" id="reset-confirm-no">Huỷ</button>
  `;
  box.hidden = false;
  $("reset-confirm-no").addEventListener("click", dismissResetConfirm);
  $("reset-confirm-yes").addEventListener("click", async () => {
    if (state.handlingBusy) return;
    dismissResetConfirm();
    await runHistoryAction("/api/reset-working", "✅ Đã quay về dữ liệu gốc.");
  });
  $("reset-confirm-no").focus(); // focus vào "Huỷ" (lựa chọn an toàn)
});

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

// ================================================================
// HƯỚNG CLASS NOISE (Bước 3-4-5) -- song song với nhánh attribute phía
// trên, dùng CHUNG file_id/headers đã có từ Bước 1, nhưng cấu hình +
// hiển thị kết quả hoàn toàn khác (không có cột/noise_type, chỉ có
// label_column/feature_columns + diagnostics + findings xếp theo margin).
// Gọi backend thật qua /api/class-noise/detect (class_noise/confident_learning.py),
// không tính toán gì ở JS -- đúng nguyên tắc chung của toàn trang.
// ================================================================

// ---- Bước 2: chọn nhãn + đặc trưng ----
// Tên ngắn của từng phương pháp thành phần của bộ kết hợp (phần "Xem thêm").
const CLASS_METHOD_SHORT = {
  single_learning: "Confident Learning",
  distance_based: "Mutual k-NN",
};

function toggleStep3Direction() {
  const isClass = state.direction === "class";
  $("panel-3-attribute").hidden = isClass;
  $("panel-3-class").hidden = !isClass;
  $("panel-3-title").textContent = isClass ? "Chọn nhãn & đặc trưng" : "Cấu hình noise cho từng cột";
  $("panel-3-eyebrow").textContent = "[ Bước 2 / 4 ]";
  if (isClass) {
    renderClassNoiseConfigForm();
    chRenderSourceNote();
  }
}

function renderClassNoiseConfigForm() {
  const labelSelect = $("class-label-select");
  labelSelect.innerHTML = state.headers
    .map((h) => `<option value="${escapeAttr(h)}">${escapeHtml(h)}</option>`)
    .join("");
  // Mặc định chọn CỘT CUỐI làm nhãn -- quy ước phổ biến của nhiều bộ dữ
  // liệu phân loại (label thường là cột cuối cùng), người dùng đổi lại
  // được ngay nếu file của họ không theo quy ước này.
  if (!state.classLabelColumn || !state.headers.includes(state.classLabelColumn)) {
    state.classLabelColumn = state.headers[state.headers.length - 1];
  }
  labelSelect.value = state.classLabelColumn;
  renderClassFeatureList();
}

function renderClassFeatureList() {
  const wrap = $("class-feature-list");
  const label = state.classLabelColumn;
  const candidates = state.headers.filter((h) => h !== label);
  if (!candidates.length) {
    wrap.innerHTML = `<p class="empty-state">File chỉ có 1 cột, không còn cột nào để làm đặc trưng.</p>`;
    return;
  }
  wrap.innerHTML = candidates
    .map((h) => {
      // Cột chữ chưa hỗ trợ làm đặc trưng (không mã hoá One-Hot, xem CLAUDE.md mục 35): khoá ô tick + ghi chú,
      // để người dùng khỏi tick rồi mới bị backend báo lỗi.
      if (!isClassFeatureUsable(h)) {
        state.classFeatureColumns.delete(h);
        return `<label class="switch-row"><input type="checkbox" data-feature="${escapeAttr(h)}" disabled/> <span class="mono">${escapeHtml(h)}</span> <span class="hint-note">cột chữ, chưa hỗ trợ</span></label>`;
      }
      const checked = state.classFeatureColumns.has(h);
      return `<label class="switch-row"><input type="checkbox" data-feature="${escapeAttr(h)}" ${checked ? "checked" : ""}/> <span class="mono">${escapeHtml(h)}</span></label>`;
    })
    .join("");
}
// Cột đặc trưng Class Noise chỉ nhận cột SỐ. Dựa trên kiểu backend đã đoán lúc upload (guessed_dtypes): chữ/nhóm/email/ngày thì không dùng được.
function isClassFeatureUsable(h) {
  const cfg = state.columnConfig && state.columnConfig[h];
  const dtype = cfg ? cfg.dtype : "integer";
  return !["category", "text", "email", "date"].includes(dtype);
}

$("class-label-select").addEventListener("change", (e) => {
  state.classLabelColumn = e.target.value;
  state.classFeatureColumns.delete(e.target.value); // nhãn không được trùng đặc trưng
  renderClassFeatureList();
});

// Nút "Tích tất cả"/"Bỏ tích tất cả" -- tiện cho file nhiều cột (vd Credit
// Card Fraud 29 cột), đỡ phải bấm từng ô 1 như trước.
$("class-feature-select-all").addEventListener("click", () => {
  state.headers.filter((h) => h !== state.classLabelColumn && isClassFeatureUsable(h)).forEach((h) => state.classFeatureColumns.add(h));
  renderClassFeatureList();
});
$("class-feature-select-none").addEventListener("click", () => {
  state.classFeatureColumns.clear();
  renderClassFeatureList();
});

$("class-feature-list").addEventListener("change", (e) => {
  const h = e.target.dataset.feature;
  if (!h) return;
  if (e.target.checked) state.classFeatureColumns.add(h);
  else state.classFeatureColumns.delete(h);
});

// Chữ trên nút (cố định) và lời báo trong lúc chờ. Chạy ĐỒNG BỘ (không chạy nền, không thanh tiến độ).
const CLASS_DETECT_LABEL = "Phát hiện nhãn sai →";
const CLASS_DETECT_WAIT = "Đang chạy Mutual k-NN và Confident Learning, có thể mất vài phút với file lớn…";

$("class-detect-btn").addEventListener("click", async () => {
  const btn = $("class-detect-btn");
  const statusEl = $("class-detect-status");
  const featureColumns = Array.from(state.classFeatureColumns);

  if (!state.classLabelColumn) {
    alert("Hãy chọn cột nhãn.");
    return;
  }
  if (featureColumns.length === 0) {
    alert("Hãy chọn ít nhất 1 cột đặc trưng.");
    return;
  }

  setButtonLoading(btn, true, "Đang phát hiện...", CLASS_DETECT_LABEL);
  statusEl.textContent = CLASS_DETECT_WAIT;

  // Chỉ còn 1 cách phát hiện: bộ kết hợp. Không gửi k / alpha / n_estimators (backend dùng mặc định k = 5,
  // alpha = 0, n_estimators = 100). Bước chuẩn bị chung chạy ở backend: bỏ cột hằng / định danh / tương quan
  // (không dùng nhãn), giảm số cột bằng Boruta (luôn chạy, người dùng không chọn), gộp dòng trùng...
  const requestBody = {
    file_id: state.fileId,
    label_column: state.classLabelColumn,
    feature_columns: featureColumns,
    method: "combined",
  };

  let response;
  try {
    response = await fetch(`${API_BASE}/api/class-noise/detect`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestBody),
    });
  } catch (err) {
    alert("Không gọi được backend.");
    setButtonLoading(btn, false, "Đang phát hiện...", CLASS_DETECT_LABEL);
    statusEl.textContent = "";
    return;
  }
  setButtonLoading(btn, false, "Đang phát hiện...", CLASS_DETECT_LABEL);
  statusEl.textContent = "";

  if (!response.ok) {
    let message = "Phát hiện thất bại, kiểm tra console/backend log.";
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
  state.classDiagnostics = data.diagnostics;
  state.classPreprocess = data.preprocess || null;
  state.classFindings = data.findings;
  state.classMethodFindings = data.method_findings || {};
  state.classMoreOpen = false; // kết quả mới -> "Xem thêm" đóng lại, về trang 1
  state.classMorePages = {};
  state.classFindingsPage = 1;
  state.classFindingsFilterText = "";
  $("class-findings-search").value = "";
  chResetForNewFindings(); // danh sách nghi ngờ mới -> lựa chọn xử lý cũ không còn ứng với nó
  classHandling.source = data.source || null;

  unlockStep(4);
  goStep(4); // goStep() tự gọi toggleStep4Direction() -> renderClassResults()
});

// ---- Bước 3: kết quả = danh sách kết hợp + (tuỳ chọn) "Xem thêm" từng phương pháp ----
function toggleStep4Direction() {
  const isClass = state.direction === "class";
  $("panel-4-attribute").hidden = isClass;
  $("panel-4-class").hidden = !isClass;
  if (isClass && state.classDiagnostics) renderClassResults();
}

function renderClassResults() {
  const diag = state.classDiagnostics;
  if (!diag) return;
  renderClassSummary(diag);
  $("class-preprocess-card").hidden = true;   // thẻ báo cáo bước chuẩn bị đã bỏ khỏi giao diện (24/11/2026)
  renderClassFindingsTable();
  renderClassMore();
}

// ---- Tiện ích dùng chung ----
const classNum = (n) => Number(n).toLocaleString("vi-VN");
const classPct = (x, digits = 1) => `${(x * 100).toFixed(digits)}%`;

// Nhận xét độ tin cậy của backend (diag.quality, dựa trên MỨC VƯỢT MỐC): none (không hơn đoán bừa) -> đỏ;
// low (hơn rất ít) -> vàng; ok -> không cần cảnh báo.
function classQualityWarning(q) {
  return q && q.level !== "ok" ? { level: q.level === "none" ? "bad" : "warn", text: q.message } : null;
}
// Khung cảnh báo chung: đỏ nếu có cảnh báo mức "bad", vàng nếu chỉ có "warn", ẩn nếu rỗng.
function setClassWarnings(items) {
  const list = items.filter(Boolean);
  const card = $("class-warning-card");
  if (!list.length) {
    card.hidden = true;
    card.innerHTML = "";
    card.classList.remove("is-bad");
    return;
  }
  card.hidden = false;
  card.classList.toggle("is-bad", list.some((i) => i.level === "bad"));
  card.innerHTML = list.map((i) => `<p class="class-warn-line">⚠️ ${escapeHtml(i.text)}</p>`).join("");
}

// ---- Báo cáo bước chuẩn bị chung (cột nào bị bỏ vì luật gì, dòng bị loại/gộp, nhóm dòng mâu thuẫn) ----
const PREPROCESS_REASONS = {
  all_blank: "Toàn ô trống",
  not_numeric: "Cột chữ",
  mostly_blank: "Quá nhiều ô trống",
  constant: "Cột hằng",
  identifier: "Giống mã định danh",
  correlated: "Trùng thông tin với cột khác",
  label_reduction: "Giảm số cột (Boruta)",
};
function renderClassPreprocess() {
  const card = $("class-preprocess-card");
  const pp = state.classPreprocess;
  if (!pp) {
    card.hidden = true;
    return;
  }
  card.hidden = false;
  const dropped = pp.dropped_columns || [];
  const kept = pp.kept_columns || [];

  const lines = [
    `<strong>${classNum(pp.n_rows_input)}</strong> dòng → <strong>${classNum(pp.n_rows_final)}</strong> dòng đưa vào thuật toán · ` +
      `<strong>${kept.length}</strong> cột giữ lại, <strong>${dropped.length}</strong> cột bị bỏ`,
  ];
  if (pp.n_rows_blank_label) lines.push(`${classNum(pp.n_rows_blank_label)} dòng bị bỏ vì nhãn trống`);
  if (pp.n_rows_blank_feature) lines.push(`${classNum(pp.n_rows_blank_feature)} dòng bị bỏ vì còn ô trống ở các cột đã giữ`);
  if (pp.n_rows_merged_away) {
    lines.push(
      `${classNum(pp.n_rows_merged_away)} dòng trùng đặc trưng và cùng nhãn được gộp vào ${classNum(pp.n_duplicate_groups_merged)} dòng đại diện ` +
        "(dòng đại diện bị gắn cờ thì cả nhóm đều bị gắn cờ)"
    );
  }
  if (pp.n_conflict_groups) {
    lines.push(
      `<strong>${classNum(pp.n_conflict_groups)}</strong> nhóm dòng cùng đặc trưng nhưng khác nhãn (${classNum(pp.n_conflict_rows)} dòng, giữ nguyên để thuật toán xét)`
    );
  }

  const droppedTable = dropped.length
    ? `<div class="table-wrap"><table class="results-table">
        <thead><tr><th>Cột bị bỏ</th><th>Luật</th><th>Chi tiết</th></tr></thead>
        <tbody>${dropped
          .map(
            (d) =>
              `<tr><td class="mono">${escapeHtml(d.column)}</td><td>${escapeHtml(PREPROCESS_REASONS[d.reason] || d.reason)}</td><td>${escapeHtml(d.detail)}</td></tr>`
          )
          .join("")}</tbody></table></div>`
    : "";

  const groups = pp.conflict_groups || [];
  const conflictList = groups.length
    ? `<details class="class-conflict-details"><summary>Xem các nhóm mâu thuẫn (${groups.length}${pp.conflict_groups_total > groups.length ? ` đầu tiên trong ${classNum(pp.conflict_groups_total)}` : ""})</summary>
        <ul>${groups
          .map((g) => {
            const rows = g.rows.slice(0, 8).join(", ") + (g.rows.length > 8 ? `, … (${g.rows.length} dòng)` : "");
            const labels = Object.entries(g.labels)
              .map(([k, v]) => `«${escapeHtml(k)}» ×${v}`)
              .join(", ");
            return `<li>Dòng ${escapeHtml(rows)}: nhãn ${labels}</li>`;
          })
          .join("")}</ul></details>`
    : "";

  // Giảm số cột bằng Boruta (luôn chạy): giữ X / Y cột, liệt kê cột bị bỏ, số vòng.
  let reduction = "";
  const lr = pp.label_reduction;
  if (lr && lr.applied) {
    const total = lr.n_columns_in || (lr.kept.length + lr.rejected.length + (lr.tentative || []).length);
    const rejected = (lr.rejected || []).map((c) => `<span class="mono">${escapeHtml(c)}</span>`).join(", ");
    reduction = `<h4 class="sub-title">Giảm số cột (Boruta): giữ ${lr.kept.length} / ${total} cột</h4>
      <p class="class-prep-line">${lr.n_iter} vòng${lr.seconds != null ? `, ${lr.seconds} giây` : ""}.${
        rejected ? ` Cột bị bỏ vì không quan trọng hơn cột ngẫu nhiên: ${rejected}.` : " Không cột nào bị bỏ."
      }${(lr.tentative || []).length ? ` ${lr.tentative.length} cột chưa kết luận được vẫn được giữ.` : ""}</p>`;
  } else if (lr) {
    reduction = `<h4 class="sub-title">Giảm số cột (Boruta): không áp dụng được, giữ nguyên các cột</h4>`;
  }

  const warns = (pp.warnings || []).map((w) => `<p class="hint-note">⚠️ ${escapeHtml(w)}</p>`).join("");

  card.innerHTML = `
    <h3 class="sub-title">Bước chuẩn bị dữ liệu (dùng chung cho mọi phương pháp)</h3>
    ${lines.map((l) => `<p class="class-prep-line">${l}</p>`).join("")}
    ${droppedTable}
    ${conflictList}
    ${reduction}
    ${warns}`;
}

// ---- Phần chính: thẻ tóm tắt + khung cảnh báo ----
// Chỉ 2 thẻ (dòng dùng được, dòng nghi ngờ). Các chỉ số tin cậy của từng phương pháp (mức vượt mốc của Confident
// Learning, độ phủ của Mutual k-NN, trọng số...) nằm ở phần "Xem thêm" bên dưới danh sách.
function renderClassSummary(diag) {
  $("class-stats-grid").innerHTML = `
    <div class="stat-card">
      <span class="stat-value mono">${classNum(diag.n_rows_used)}</span>
      <span class="stat-label">Dòng dùng được / ${classNum(diag.n_rows_total)} tổng</span>
    </div>
    <div class="stat-card stat-amber">
      <span class="stat-value mono">${classNum(state.classFindings.length)}</span>
      <span class="stat-label">Dòng nghi sai nhãn</span>
    </div>
  `;
  setClassWarnings([
    classQualityWarning(diag.quality),
    ...(diag.warnings || []).map((w) => ({ level: "warn", text: w })),
  ]);
}

// ---- Bảng danh sách kết hợp ----
function getFilteredClassFindings() {
  const text = state.classFindingsFilterText.trim().toLowerCase();
  if (!text) return state.classFindings;
  return state.classFindings.filter((f) =>
    `${f.row_number} ${f.recorded_label} ${f.suggested_label}`.toLowerCase().includes(text)
  );
}

// Tên cột của bảng danh sách kết hợp (dùng cả ở bước Xử lý). Nhãn gợi ý = bỏ phiếu có trọng số giữa các phương
// pháp đang dùng; độ tin cậy (tên hiển thị) = điểm kết hợp = trung bình có trọng số hạng phần trăm của các phương pháp.
const CLASS_COLUMN_LABELS = { suggested: "Nhãn gợi ý", score: "Độ tin cậy" };

// Số dòng hiển thị kèm ghi chú nếu dòng này là bản trùng của 1 dòng đại diện đã bị gắn cờ (bước chuẩn bị đã gộp).
function classRowCell(f) {
  return f.duplicate_of ? `${f.row_number} <span class="hint-note">trùng dòng ${f.duplicate_of}</span>` : `${f.row_number}`;
}
function renderClassFindingsTable() {
  const all = getFilteredClassFindings();
  const perPage = state.classFindingsPerPage;
  const totalPages = Math.max(1, Math.ceil(all.length / perPage));
  state.classFindingsPage = Math.min(state.classFindingsPage, totalPages);
  const start = (state.classFindingsPage - 1) * perPage;
  const pageRows = all.slice(start, start + perPage);

  const table = $("class-findings-table");
  const headHtml = `<thead><tr><th>Dòng</th><th>Nhãn ghi</th><th>${CLASS_COLUMN_LABELS.suggested}</th><th>${CLASS_COLUMN_LABELS.score}</th></tr></thead>`;
  if (!pageRows.length) {
    const empty = state.classFindings.length ? "Không có dòng nào khớp." : "Không phát hiện dòng nào nghi sai nhãn.";
    table.innerHTML = `${headHtml}<tbody><tr><td colspan="4" class="empty-cell">${empty}</td></tr></tbody>`;
  } else {
    table.innerHTML = `${headHtml}<tbody>${pageRows
      .map((f) => {
        return `<tr><td class="mono">${classRowCell(f)}</td><td>${escapeHtml(f.recorded_label)}</td><td>${escapeHtml(f.suggested_label || "—")}</td><td class="mono">${f.score.toFixed(2)}</td></tr>`;
      })
      .join("")}</tbody>`;
  }

  const pag = $("class-findings-pagination");
  pag.hidden = totalPages <= 1;
  $("class-page-indicator").textContent = `Trang ${state.classFindingsPage}/${totalPages}`;
}

// ---- "Xem thêm" (mặc định ĐÓNG): mức tin cậy + danh sách RIÊNG của từng phương pháp ----
const CLASS_MORE_PER_PAGE = 10;
// Thứ tự hiện: Confident Learning trước, Mutual k-NN sau. Mỗi phương pháp có cách tính điểm nghi riêng.
const CLASS_MORE_METHODS = [
  { key: "single_learning", score: "Điểm nghi (1 − xác suất mô hình cho nhãn ghi)" },
  { key: "distance_based", score: "Điểm nghi (tỉ lệ láng giềng lẫn nhau khác nhãn)" },
];

// Bảng "Mức tin cậy": mỗi phương pháp một hàng -- chỉ số đo độ tin cậy, trọng số, đang dùng hay bị loại (+ lý do).
function classTrustTableHTML(diag) {
  const rows = CLASS_MORE_METHODS.filter(({ key }) => diag.methods && diag.methods[key])
    .map(({ key }) => {
      const m = diag.methods[key];
      let metric = "—";
      if (key === "single_learning" && diag.single) {
        metric = `Mức vượt mốc <strong>${m.quality === null || m.quality === undefined ? "—" : classPct(m.quality)}</strong>`;
      } else if (key === "distance_based" && diag.distance) {
        const d = diag.distance;
        metric = `Độ phủ <strong>${d.coverage === null || d.coverage === undefined ? "—" : classPct(d.coverage)}</strong>`;
      }
      const status = m.on
        ? `<strong>Đang dùng</strong>`
        : `<strong class="class-method-off">Bị loại</strong>`;
      return `<tr>
        <td>${escapeHtml(CLASS_METHOD_SHORT[key])}</td>
        <td class="class-reason-cell">${metric}</td>
        <td class="mono">${m.on && m.weight !== null && m.weight !== undefined ? m.weight.toFixed(2) : "—"}</td>
        <td class="class-reason-cell">${status}</td>
        <td class="mono">${classNum(m.n_flagged_rows !== undefined ? m.n_flagged_rows : m.n_flagged)}</td>
      </tr>`;
    })
    .join("");
  return `<section class="class-more-block">
    <h4 class="sub-title">Mức tin cậy</h4>
    <div class="table-wrap"><table class="results-table">
      <thead><tr><th>Phương pháp</th><th>Chỉ số tin cậy</th><th>Trọng số</th><th>Trạng thái</th><th>Tự gắn cờ</th></tr></thead>
      <tbody>${rows}</tbody>
    </table></div>
  </section>`;
}

// Danh sách riêng của 1 phương pháp: các dòng chính nó tự gắn cờ + điểm nghi của nó (phân trang).
function classMethodListHTML(def, diag) {
  const info = diag.methods && diag.methods[def.key];
  if (!info) return "";
  const list = state.classMethodFindings[def.key] || [];
  const totalPages = Math.max(1, Math.ceil(list.length / CLASS_MORE_PER_PAGE));
  const page = Math.min(Math.max(1, state.classMorePages[def.key] || 1), totalPages);
  state.classMorePages[def.key] = page;
  const start = (page - 1) * CLASS_MORE_PER_PAGE;
  const rows = list.slice(start, start + CLASS_MORE_PER_PAGE);
  const name = CLASS_METHOD_SHORT[def.key];

  const note = info.on
    ? ""
    : `<p class="hint-note">Phương pháp này bị loại khỏi bộ kết hợp (${escapeHtml(info.reason || "")}), danh sách chỉ để tham khảo.</p>`;
  const body = rows.length
    ? `<div class="table-wrap"><table class="results-table" data-more-table="${def.key}">
        <thead><tr><th>Dòng</th><th>Nhãn ghi</th><th>Nhãn gợi ý</th><th>${def.score}</th></tr></thead>
        <tbody>${rows
          .map(
            (f) =>
              `<tr><td class="mono">${classRowCell(f)}</td><td>${escapeHtml(f.recorded_label)}</td><td>${escapeHtml(f.suggested_label || "—")}</td><td class="mono">${f.score === null || f.score === undefined ? "—" : f.score.toFixed(4)}</td></tr>`
          )
          .join("")}</tbody>
      </table></div>`
    : `<p class="empty-state">${escapeHtml(name)} không tự gắn cờ dòng nào.</p>`;
  const pager =
    totalPages > 1
      ? `<div class="pagination">
          <button class="btn btn-ghost btn-small" type="button" data-more-page="${def.key}" data-dir="-1"${page <= 1 ? " disabled" : ""}>← Trước</button>
          <span class="mono">Trang ${page}/${totalPages}</span>
          <button class="btn btn-ghost btn-small" type="button" data-more-page="${def.key}" data-dir="1"${page >= totalPages ? " disabled" : ""}>Sau →</button>
        </div>`
      : "";
  return `<section class="class-more-block" data-more-method="${def.key}">
    <h4 class="sub-title">${escapeHtml(name)} · ${classNum(list.length)} dòng tự gắn cờ</h4>
    ${note}${body}${pager}
  </section>`;
}

function renderClassMore() {
  const btn = $("class-more-btn");
  const panel = $("class-more-panel");
  btn.setAttribute("aria-expanded", state.classMoreOpen ? "true" : "false");
  btn.textContent = state.classMoreOpen ? "Thu gọn ▴" : "Xem thêm ▾";
  panel.hidden = !state.classMoreOpen;
  const diag = state.classDiagnostics;
  if (!state.classMoreOpen || !diag) {
    panel.innerHTML = ""; // đóng thì không dựng gì (nhẹ khi danh sách rất dài)
    return;
  }
  panel.innerHTML = classTrustTableHTML(diag) + CLASS_MORE_METHODS.map((def) => classMethodListHTML(def, diag)).join("");
}
$("class-more-btn").addEventListener("click", () => {
  state.classMoreOpen = !state.classMoreOpen;
  renderClassMore();
});
$("class-more-panel").addEventListener("click", (e) => {
  const btn = e.target.closest("[data-more-page]");
  if (!btn || btn.disabled) return;
  const key = btn.dataset.morePage;
  state.classMorePages[key] = (state.classMorePages[key] || 1) + parseInt(btn.dataset.dir, 10);
  renderClassMore();
});

$("class-findings-search").addEventListener(
  "input",
  debounce((e) => {
    state.classFindingsFilterText = e.target.value;
    state.classFindingsPage = 1;
    renderClassFindingsTable();
  }, 200)
);
$("class-page-prev").addEventListener("click", () => {
  if (state.classFindingsPage > 1) {
    state.classFindingsPage--;
    renderClassFindingsTable();
  }
});
$("class-page-next").addEventListener("click", () => {
  state.classFindingsPage++;
  renderClassFindingsTable();
});

$("class-goto-handling-btn").addEventListener("click", () => {
  unlockStep(5);
  goStep(5); // goStep() tự gọi toggleStep5Direction()
});

// ====== BƯỚC XỬ LÝ cho CLASS NOISE (CLAUDE.md mục 37) ======
// Mỗi dòng nghi sai nhãn có 3 cách: giữ nguyên / xoá dòng / sửa nhãn (theo gợi ý hoặc sang nhãn
// khác đã có). Người dùng chọn từng dòng hoặc gán HÀNG LOẠT theo hướng (nhãn ghi → gợi ý) +
// ngưỡng mức đáng ngờ; bấm Áp dụng thì chạy thử (dry_run), hỏi xác nhận, rồi mới ghi thật.
// Tiền tố `ch` / `classHandling` để KHÔNG trùng tên hàm của nhánh Attribute trong cùng IIFE.
const classHandling = {
  plan: new Map(), // row_number -> { action: "keep" | "remove_row" | "relabel", newLabel }
  done: new Map(), // row_number -> { action, newLabel }: dòng đã áp dụng (trong lần phát hiện hiện tại)
  steps: [], // mỗi lần áp dụng có đổi dữ liệu: danh sách row_number (để hoàn tác trả dòng về "chưa xử lý")
  page: 1,
  perPage: 20,
  filterText: "",
  history: { entries: [], can_undo: false, undo_limit: 5 },
  source: null, // { is_processed, history_steps, rows, original_rows } từ lần phát hiện cuối
  busy: false,
  pendingRows: null, // payload + chữ ký lựa chọn của hộp xác nhận đang mở
};
const CH_RARE_SHARE = 0.05; // lớp chiếm dưới 5% số dòng coi là "lớp hiếm" -> cảnh báo riêng

const chNum = (n) => Number(n).toLocaleString("vi-VN");

function chResetAll() {
  classHandling.history = { entries: [], can_undo: false, undo_limit: 5 };
  classHandling.source = null;
  chResetForNewFindings();
}
// Phát hiện xong (danh sách nghi ngờ MỚI) -> lựa chọn cũ không còn ứng với danh sách nữa.
function chResetForNewFindings() {
  classHandling.plan = new Map();
  classHandling.done = new Map();
  classHandling.steps = [];
  classHandling.page = 1;
  classHandling.filterText = "";
  classHandling.pendingRows = null;
  $("ch-search").value = "";
  $("ch-bulk-min-score").value = "";
  $("ch-bulk-action").value = "";
  $("ch-bulk-direction").value = ""; // danh sách mới -> bỏ lọc hướng cũ
  chDismissConfirm();
  setStatusMessage($("ch-status"), "", "");
  chRenderSourceNote();
}

function toggleStep5Direction() {
  const isClass = state.direction === "class";
  $("panel-5-attribute").hidden = isClass;
  $("panel-5-class").hidden = !isClass;
  if (isClass) renderClassHandling();
}
$("class-back-to-results-btn").addEventListener("click", () => goStep(4));

// Dòng ghi chú ở bước chọn nhãn & đặc trưng: lần phát hiện kế tiếp sẽ chạy trên dữ liệu nào.
function chRenderSourceNote() {
  const el = $("class-source-note");
  const steps = classHandling.history.entries.length;
  if (steps === 0) {
    el.hidden = true;
    el.textContent = "";
    return;
  }
  el.hidden = false;
  el.textContent =
    `Đang chạy trên dữ liệu đã xử lý (${steps} bước). Muốn dùng file gốc: bước Xử lý → Về dữ liệu gốc.`;
}

function chClassNames() {
  return (state.classDiagnostics && state.classDiagnostics.class_names) || [];
}
const chDirectionKey = (f) => `${f.recorded_label} → ${f.suggested_label}`;
function chFindingByRow(rowNumber) {
  return state.classFindings.find((f) => f.row_number === rowNumber);
}

// ---- Thanh lịch sử ----
function chDescribeEntry(entry) {
  const effects = [];
  if (entry.rows_removed > 0) effects.push(`xoá ${chNum(entry.rows_removed)} dòng`);
  if (entry.cells_changed > 0) effects.push(`đổi nhãn ${chNum(entry.cells_changed)} dòng`);
  const parts = [];
  Object.entries(entry.relabel_directions || {}).forEach(([k, v]) => parts.push(`${escapeHtml(k)} ×${Number(v)}`));
  Object.entries(entry.removed_by_label || {}).forEach(([k, v]) => parts.push(`xoá nhãn «${escapeHtml(k)}» ×${Number(v)}`));
  return `<strong>Nhãn «${escapeHtml(entry.column || "")}»</strong>: ${effects.join(", ")} <span class="history-actions">— ${parts.join("; ")}</span>`;
}
function chRenderHistory() {
  const h = classHandling.history;
  const list = $("ch-history-log");
  if (h.entries.length === 0) {
    list.innerHTML = "";
  } else {
    list.innerHTML = h.entries
      .slice()
      .reverse()
      .map((e, i) => {
        const note = e.undoable ? "" : ' <span class="history-actions">(không hoàn tác được)</span>';
        return `<li class="history-log-item${i === 0 ? " is-latest" : ""}">${chDescribeEntry(e)}${note}</li>`;
      })
      .join("");
  }
  $("ch-undo-btn").disabled = !h.can_undo || classHandling.busy;
  $("ch-reset-btn").disabled = h.entries.length === 0 || classHandling.busy;
  $("ch-history-hint").textContent =
    h.entries.length > 0 && !h.can_undo
      ? `Hết bước để hoàn tác (nhớ ${h.undo_limit} bước gần nhất).`
      : `Hoàn tác tối đa ${h.undo_limit} bước.`;
}

// ---- Gán hàng loạt ----
function chBulkMatches() {
  const dir = $("ch-bulk-direction").value;
  const minScore = chMinScoreValue();
  return state.classFindings.filter((f) => {
    if (classHandling.done.has(f.row_number)) return false;
    if (dir && chDirectionKey(f) !== dir) return false;
    if (minScore !== null && f.score < minScore) return false;
    return true;
  });
}
// Khoảng mức đáng ngờ THẬT của danh sách (làm tròn ra 3 số lẻ để bao trọn). null nếu chưa có danh sách.
function chScoreRange() {
  const scores = state.classFindings.map((f) => f.score).filter((s) => Number.isFinite(s));
  if (!scores.length) return null;
  return { min: Math.floor(Math.min(...scores) * 1000) / 1000, max: Math.ceil(Math.max(...scores) * 1000) / 1000 };
}
// Giá trị ô "Mức đáng ngờ từ" đã kẹp vào khoảng cho phép; null = bỏ trống (lấy tất cả).
function chMinScoreValue() {
  const raw = $("ch-bulk-min-score").value.trim();
  const range = chScoreRange();
  if (raw === "" || !range) return null;
  const n = Number(raw);
  if (!Number.isFinite(n)) return null;
  return Math.min(range.max, Math.max(range.min, n));
}
function chRenderBulk() {
  const sel = $("ch-bulk-direction");
  const previous = sel.value;
  // Số trong ngoặc = số dòng của hướng đó trong cả danh sách, đúng bằng số dòng bảng bên dưới hiện khi chọn hướng này.
  const counts = new Map();
  state.classFindings.forEach((f) => counts.set(chDirectionKey(f), (counts.get(chDirectionKey(f)) || 0) + 1));
  sel.innerHTML =
    `<option value="">Tất cả (${chNum(state.classFindings.length)})</option>` +
    Array.from(counts.entries())
      .map(([k, n]) => `<option value="${escapeAttr(k)}">${escapeHtml(k)} (${chNum(n)})</option>`)
      .join("");
  if (counts.has(previous)) sel.value = previous;

  const input = $("ch-bulk-min-score");
  const range = chScoreRange();
  if (range) {
    input.min = String(range.min);
    input.max = String(range.max);
    input.placeholder = `${range.min.toFixed(3)} – ${range.max.toFixed(3)}`;
  } else {
    input.removeAttribute("min");
    input.removeAttribute("max");
    input.placeholder = "tất cả";
  }
  chRenderBulkInfo();
}
function chRenderBulkInfo() {
  const matches = chBulkMatches();
  const action = $("ch-bulk-action").value;
  $("ch-bulk-info").textContent = "";
  $("ch-bulk-assign-btn").disabled = classHandling.busy || !action || matches.length === 0;
}
// Đổi hướng -> bảng bên dưới chỉ hiện các dòng của hướng đó, về trang 1.
$("ch-bulk-direction").addEventListener("change", () => {
  classHandling.page = 1;
  chRenderTable();
  chRenderBulkInfo();
});
// Ô "Mức đáng ngờ từ" chỉ nhận số trong khoảng [nhỏ nhất, lớn nhất] của danh sách:
// chặn gõ e / + / - ; gõ quá lớn thì kẹp ngay về mức lớn nhất; rời ô hoặc Enter thì kẹp luôn cả phía nhỏ.
$("ch-bulk-min-score").addEventListener("keydown", (e) => {
  if (["e", "E", "+", "-"].includes(e.key)) e.preventDefault();
});
$("ch-bulk-min-score").addEventListener("input", () => {
  const range = chScoreRange();
  const input = $("ch-bulk-min-score");
  if (range && input.value !== "" && Number(input.value) > range.max) input.value = String(range.max);
  chRenderBulkInfo();
});
$("ch-bulk-min-score").addEventListener("change", () => {
  const input = $("ch-bulk-min-score");
  const clamped = chMinScoreValue();
  input.value = clamped === null ? "" : String(Number(clamped.toFixed(3)));
  chRenderBulkInfo();
});
$("ch-bulk-action").addEventListener("change", chRenderBulkInfo);
$("ch-bulk-assign-btn").addEventListener("click", () => {
  if (classHandling.busy) return;
  const action = $("ch-bulk-action").value;
  const matches = chBulkMatches();
  if (!action || matches.length === 0) return;
  chDismissConfirm();
  // "Sửa nhãn theo gợi ý" bỏ qua dòng không có nhãn gợi ý (bộ kết hợp có thể không gợi ý được); đếm đúng số dòng THỰC SỰ gán.
  let assigned = 0;
  matches.forEach((f) => {
    if (action === "relabel_suggested") {
      if (!f.suggested_label) return;
      classHandling.plan.set(f.row_number, { action: "relabel", newLabel: f.suggested_label });
    } else classHandling.plan.set(f.row_number, { action, newLabel: null });
    assigned++;
  });
  const skipped = matches.length - assigned;
  const names = { keep: "Giữ nguyên", remove_row: "Xoá dòng", relabel_suggested: "Sửa nhãn theo gợi ý" };
  setStatusMessage(
    $("ch-status"),
    `Đã gán «${names[action]}» cho ${chNum(assigned)} dòng` +
      (skipped ? `, bỏ qua ${chNum(skipped)} dòng không có nhãn gợi ý` : "") +
      " (chưa áp dụng).",
    assigned ? "ok" : "error"
  );
  chRenderTable();
  chRenderSummary();
  chRenderBulkInfo();
});

// ---- Bảng từng dòng ----
// Bảng hiện các dòng của hướng đang chọn ở khung "Gán hàng loạt" (nếu có) và khớp ô tìm kiếm.
function chFiltered() {
  const dir = $("ch-bulk-direction").value;
  const text = classHandling.filterText.trim().toLowerCase();
  return state.classFindings.filter((f) => {
    if (dir && chDirectionKey(f) !== dir) return false;
    return !text || `${f.row_number} ${f.recorded_label} ${f.suggested_label}`.toLowerCase().includes(text);
  });
}
function chRowOptions(f, current) {
  const val = current ? (current.action === "relabel" ? `relabel:${current.newLabel}` : current.action) : "";
  const opts = [
    ["", "— Chọn cách xử lý —"],
    ["keep", "Giữ nguyên"],
    ["remove_row", "Xoá dòng"],
  ];
  // Bộ kết hợp có thể không có nhãn gợi ý cho 1 dòng (suggested_label rỗng): khi đó chỉ còn các nhãn có sẵn bên dưới.
  if (f.suggested_label) opts.push([`relabel:${f.suggested_label}`, `Sửa thành «${f.suggested_label}» (gợi ý)`]);
  chClassNames()
    .filter((c) => c !== f.recorded_label && c !== f.suggested_label)
    .forEach((c) => opts.push([`relabel:${c}`, `Sửa thành «${c}»`]));
  return opts
    .map(([v, t]) => `<option value="${escapeAttr(v)}"${v === val ? " selected" : ""}>${escapeHtml(t)}</option>`)
    .join("");
}
function chDoneText(d) {
  if (d.action === "remove_row") return "✅ Đã xoá dòng";
  if (d.action === "relabel") return `✅ Đã đổi nhãn → «${escapeHtml(d.newLabel)}»`;
  return "✅ Đã giữ nguyên";
}
function chRenderTable() {
  const all = chFiltered();
  const totalPages = Math.max(1, Math.ceil(all.length / classHandling.perPage));
  classHandling.page = Math.min(classHandling.page, totalPages);
  const start = (classHandling.page - 1) * classHandling.perPage;
  const pageRows = all.slice(start, start + classHandling.perPage);
  // STT = số thứ tự trong danh sách đang hiện (đếm tiếp qua các trang); "Dòng" = số dòng trong file.
  const head = `<thead><tr><th>STT</th><th>Dòng</th><th>Nhãn ghi</th><th>${CLASS_COLUMN_LABELS.suggested}</th><th>${CLASS_COLUMN_LABELS.score}</th><th>Cách xử lý</th></tr></thead>`;
  $("ch-list-title").textContent = state.classFindings.length ? `Dòng nghi ngờ (${chNum(all.length)})` : "Dòng nghi ngờ";
  if (!pageRows.length) {
    $("ch-table").innerHTML = `${head}<tbody><tr><td colspan="6" class="empty-cell">${
      state.classFindings.length ? "Không có dòng nào khớp." : "Chưa có danh sách nghi ngờ."
    }</td></tr></tbody>`;
  } else {
    $("ch-table").innerHTML =
      head +
      "<tbody>" +
      pageRows
        .map((f, i) => {
          const d = classHandling.done.get(f.row_number);
          const cell = d
            ? `<span class="status-text is-ok">${chDoneText(d)}</span>`
            : `<select class="select ch-row-action" data-row="${f.row_number}" aria-label="Cách xử lý dòng ${f.row_number}">${chRowOptions(f, classHandling.plan.get(f.row_number))}</select>`;
          return `<tr><td class="mono">${start + i + 1}</td><td class="mono">${classRowCell(f)}</td><td>${escapeHtml(f.recorded_label)}</td><td>${escapeHtml(f.suggested_label || "—")}</td><td class="mono">${f.score.toFixed(2)}</td><td>${cell}</td></tr>`;
        })
        .join("") +
      "</tbody>";
  }
  $("ch-pagination").hidden = totalPages <= 1;
  $("ch-page-indicator").textContent = `Trang ${classHandling.page}/${totalPages}`;
}
$("ch-table").addEventListener("change", (e) => {
  const sel = e.target.closest(".ch-row-action");
  if (!sel) return;
  if (classHandling.busy) {
    chRenderTable(); // đang chờ server: trả ô chọn về giá trị cũ
    return;
  }
  const rowNumber = parseInt(sel.dataset.row, 10);
  chDismissConfirm();
  const v = sel.value;
  if (v === "") classHandling.plan.delete(rowNumber);
  else if (v.startsWith("relabel:")) classHandling.plan.set(rowNumber, { action: "relabel", newLabel: v.slice("relabel:".length) });
  else classHandling.plan.set(rowNumber, { action: v, newLabel: null });
  chRenderSummary();
});
$("ch-search").addEventListener(
  "input",
  debounce((e) => {
    classHandling.filterText = e.target.value;
    classHandling.page = 1;
    chRenderTable();
  }, 200)
);
$("ch-page-prev").addEventListener("click", () => {
  if (classHandling.page > 1) {
    classHandling.page--;
    chRenderTable();
  }
});
$("ch-page-next").addEventListener("click", () => {
  classHandling.page++;
  chRenderTable();
});
$("ch-clear-plan-btn").addEventListener("click", () => {
  if (classHandling.busy) return;
  chDismissConfirm();
  classHandling.plan = new Map();
  chRenderTable();
  chRenderSummary();
  chRenderBulkInfo();
});

// ---- Tóm tắt + nút Áp dụng ----
function chPlanCounts() {
  const c = { remove: 0, relabel: 0, keep: 0 };
  classHandling.plan.forEach((p) => {
    if (p.action === "remove_row") c.remove++;
    else if (p.action === "relabel") c.relabel++;
    else c.keep++;
  });
  return c;
}
function chRenderSummary() {
  const chosen = classHandling.plan.size;
  // Không còn dòng tóm tắt "N dòng nghi ngờ / Chưa chọn dòng nào" (24/11/2026); chỉ giữ lời nhắc khi chưa có kết quả.
  $("ch-summary").textContent = state.classDiagnostics ? "" : "Chưa có kết quả phát hiện. Quay lại bước Kết quả.";
  $("ch-apply-btn").disabled = classHandling.busy || chosen === 0;
  $("ch-apply-btn").textContent = chosen ? `Áp dụng ${chNum(chosen)} dòng đã chọn` : "Áp dụng các dòng đã chọn";
  $("ch-clear-plan-btn").disabled = classHandling.busy || chosen === 0;
}
function renderClassHandling() {
  chDismissConfirm();
  chRenderHistory();
  chRenderBulk();
  chRenderTable();
  chRenderSummary();
  chRenderSourceNote();
}

// ---- Gọi server ----
async function chRequest(path, body) {
  const statusEl = $("ch-status");
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file_id: state.fileId, label_column: state.classLabelColumn, ...body }),
    });
  } catch (err) {
    setStatusMessage(statusEl, "Không gọi được backend.", "error");
    return null;
  }
  let data = null;
  try {
    data = await response.json();
  } catch (err) {
    /* giữ null */
  }
  if (!response.ok) {
    setStatusMessage(statusEl, (data && data.error) || "Thao tác thất bại, kiểm tra console/backend log.", "error");
    return null;
  }
  return data;
}
// Mọi lệnh làm đổi dữ liệu chạy TUẦN TỰ (giống withHandlingLock của nhánh Attribute).
async function chWithLock(task) {
  if (classHandling.busy) return undefined;
  classHandling.busy = true;
  $("panel-5-class").classList.add("is-busy");
  renderClassHandlingButtons();
  try {
    return await task();
  } finally {
    classHandling.busy = false;
    $("panel-5-class").classList.remove("is-busy");
    renderClassHandlingButtons();
  }
}
function renderClassHandlingButtons() {
  chRenderHistory();
  chRenderSummary();
  chRenderBulkInfo();
}

function chBuildRows() {
  const rows = [];
  classHandling.plan.forEach((p, rowNumber) => {
    const f = chFindingByRow(rowNumber);
    if (!f) return;
    const item = { row_number: rowNumber, action: p.action, expected_label: f.recorded_label };
    if (p.action === "relabel") item.new_label = p.newLabel;
    rows.push(item);
  });
  return rows;
}
function chPlanSignature() {
  return JSON.stringify(Array.from(classHandling.plan.entries()).sort((a, b) => a[0] - b[0]));
}

function chDismissConfirm() {
  const box = $("ch-confirm");
  box.hidden = true;
  box.innerHTML = "";
  classHandling.pendingRows = null;
}

// Bấm "Áp dụng": chạy thử -> hộp xác nhận (nếu có đổi dữ liệu) -> áp dụng thật.
$("ch-apply-btn").addEventListener("click", async () => {
  await chWithLock(async () => {
    chDismissConfirm();
    const rows = chBuildRows();
    if (rows.length === 0) return;
    const hasChange = rows.some((r) => r.action !== "keep");
    if (!hasChange) {
      await chCommit(rows); // chỉ "Giữ nguyên": không đổi dữ liệu, khỏi hỏi
      return;
    }
    setStatusMessage($("ch-status"), "Đang chạy thử (chưa đổi gì)…", "");
    const sig = chPlanSignature();
    const preview = await chRequest("/api/class-noise/apply", { rows, dry_run: true });
    if (!preview) return;
    if (chPlanSignature() !== sig) {
      setStatusMessage($("ch-status"), "Lựa chọn đã đổi trong lúc chạy thử — bấm Áp dụng lại.", "error");
      return;
    }
    if (preview.rows_removed === 0 && preview.labels_changed === 0) {
      setStatusMessage(
        $("ch-status"),
        `Không có thay đổi nào để ghi (${chNum(preview.skipped_missing)} dòng đã bị xoá, ${chNum(preview.skipped_stale)} dòng nhãn đã đổi từ trước).`,
        ""
      );
      return;
    }
    chShowConfirm(preview, rows, sig);
    setStatusMessage($("ch-status"), "", "");
  });
});

function chRareLabels(counts) {
  const total = Object.values(counts).reduce((a, b) => a + b, 0) || 1;
  return new Set(Object.entries(counts).filter(([, n]) => n / total < CH_RARE_SHARE).map(([k]) => k));
}
function chShowConfirm(p, rows, sig) {
  const rare = chRareLabels(p.label_counts_before);
  const lines = [];
  const summary = [];
  if (p.rows_removed > 0) summary.push(`xoá <strong>${chNum(p.rows_removed)}</strong> dòng (${chNum(p.rows_before)} → ${chNum(p.rows_after)} dòng)`);
  if (p.labels_changed > 0) summary.push(`đổi nhãn <strong>${chNum(p.labels_changed)}</strong> dòng`);
  lines.push(`⚠ Sẽ ${summary.join(" và ")}.`);
  const dirs = Object.entries(p.relabel_directions);
  if (dirs.length) lines.push("Đổi nhãn theo hướng: " + dirs.map(([k, v]) => `${escapeHtml(k)}: ${chNum(v)} dòng`).join(" · ") + ".");
  const rem = Object.entries(p.removed_by_label);
  if (rem.length) lines.push("Xoá theo nhãn đang ghi: " + rem.map(([k, v]) => `«${escapeHtml(k)}»: ${chNum(v)} dòng`).join(" · ") + ".");
  lines.push(
    "Phân bố nhãn: " +
      Object.keys({ ...p.label_counts_before, ...p.label_counts_after })
        .map((k) => `«${escapeHtml(k)}» ${chNum(p.label_counts_before[k] || 0)} → ${chNum(p.label_counts_after[k] || 0)}`)
        .join(" · ") +
      "."
  );
  dirs.forEach(([k, v]) => {
    const target = k.split(" → ")[1];
    const targetNote = target;
    if (rare.has(target)) {
      lines.push(`<strong>Lớp hiếm:</strong> đổi ${chNum(v)} dòng sang «${escapeHtml(targetNote)}» (lớp này chỉ có ${chNum(p.label_counts_before[target] || 0)} dòng), nên xem kỹ các dòng đó.`);
    }
  });
  rem.forEach(([k, v]) => {
    if (rare.has(k)) lines.push(`<strong>Lớp hiếm:</strong> xoá ${chNum(v)} dòng nhãn «${escapeHtml(k)}» (lớp này chỉ có ${chNum(p.label_counts_before[k] || 0)} dòng).`);
  });
  if (p.rows_removed / Math.max(1, p.rows_before) >= 0.2) lines.push("<strong>Xoá từ 20% số dòng trở lên</strong>, hãy chắc chắn.");
  if (p.skipped_missing + p.skipped_stale > 0) {
    lines.push(`Bỏ qua ${chNum(p.skipped_missing + p.skipped_stale)} dòng (đã xoá hoặc đã đổi nhãn).`);
  }
  lines.push("Chỉ khi bấm «Xác nhận» dữ liệu mới đổi.");

  const box = $("ch-confirm");
  box.innerHTML = `
    <span class="handling-confirm-text">${lines.join("<br>")}</span>
    <button type="button" class="btn btn-danger btn-small" id="ch-confirm-yes">Xác nhận và áp dụng</button>
    <button type="button" class="btn btn-ghost btn-small" id="ch-confirm-no">Huỷ</button>`;
  box.hidden = false;
  classHandling.pendingRows = { rows, sig };
  $("ch-confirm-no").addEventListener("click", () => {
    chDismissConfirm();
    setStatusMessage($("ch-status"), "Đã huỷ, dữ liệu chưa đổi.", "");
  });
  $("ch-confirm-yes").addEventListener("click", async () => {
    const pending = classHandling.pendingRows;
    if (!pending || classHandling.busy) return;
    await chWithLock(async () => {
      if (chPlanSignature() !== pending.sig) {
        chDismissConfirm();
        setStatusMessage($("ch-status"), "Lựa chọn đã đổi — bấm Áp dụng lại.", "error");
        return;
      }
      chDismissConfirm();
      await chCommit(pending.rows);
    });
  });
  $("ch-confirm-no").focus(); // focus vào "Huỷ" (lựa chọn an toàn)
}

async function chCommit(rows) {
  const prevSteps = classHandling.history.entries.length;
  setStatusMessage($("ch-status"), "Đang áp dụng…", "");
  const data = await chRequest("/api/class-noise/apply", { rows, dry_run: false });
  if (!data) return;
  classHandling.history = data.history;
  classHandling.source = data.source;
  const skipped = new Set(data.skipped_rows || []);
  const changedRows = [];
  rows.forEach((r) => {
    if (skipped.has(r.row_number)) return;
    classHandling.done.set(r.row_number, { action: r.action, newLabel: r.new_label || null });
    if (r.action !== "keep") changedRows.push(r.row_number);
  });
  if (data.history.entries.length > prevSteps) classHandling.steps.push(changedRows);
  rows.forEach((r) => classHandling.plan.delete(r.row_number));
  const effects = [];
  if (data.rows_removed) effects.push(`xoá ${chNum(data.rows_removed)} dòng`);
  if (data.labels_changed) effects.push(`đổi nhãn ${chNum(data.labels_changed)} dòng`);
  if (!effects.length) effects.push("không đổi dữ liệu (chỉ ghi nhận giữ nguyên)");
  const extra = data.skipped_missing + data.skipped_stale > 0 ? ` Bỏ qua ${chNum(data.skipped_missing + data.skipped_stale)} dòng (đã xoá hoặc đã đổi nhãn).` : "";
  setStatusMessage($("ch-status"), `✅ Đã áp dụng: ${effects.join(", ")}.${extra}`, "ok");
  renderClassHandling();
}

// ---- Hoàn tác / Về dữ liệu gốc ----
async function chHistoryAction(path, isReset) {
  await chWithLock(async () => {
    chDismissConfirm();
    const prevSteps = classHandling.history.entries.length;
    setStatusMessage($("ch-status"), "Đang xử lý…", "");
    const data = await chRequest(path, {});
    if (!data) return;
    classHandling.history = data.history;
    classHandling.source = data.source;
    let note = "";
    if (isReset) {
      // Về gốc: mọi dòng đã sửa/xoá trở lại "chưa xử lý"; dòng chỉ "giữ nguyên" thì vẫn là quyết định của người dùng.
      Array.from(classHandling.done.entries()).forEach(([rn, d]) => {
        if (d.action !== "keep") classHandling.done.delete(rn);
      });
      classHandling.steps = [];
    } else if (classHandling.steps.length === prevSteps && prevSteps > 0) {
      classHandling.steps.pop().forEach((rn) => classHandling.done.delete(rn));
    } else {
      note = " Danh sách nghi ngờ đã cũ, hãy chạy lại phát hiện ở bước Nhãn & đặc trưng.";
    }
    setStatusMessage($("ch-status"), (isReset ? "✅ Đã quay về dữ liệu gốc." : "✅ Đã hoàn tác 1 bước.") + note, "ok");
    renderClassHandling();
  });
}
$("ch-undo-btn").addEventListener("click", () => {
  if (classHandling.busy) return;
  chHistoryAction("/api/class-noise/undo", false);
});
$("ch-reset-btn").addEventListener("click", () => {
  if (classHandling.busy) return;
  const box = $("ch-reset-confirm");
  box.innerHTML = `
    <span class="handling-confirm-text">⚠ Bỏ toàn bộ <strong>${classHandling.history.entries.length}</strong> bước xử lý và quay về dữ liệu gốc đã tải lên?</span>
    <button type="button" class="btn btn-danger btn-small" id="ch-reset-yes">Xác nhận</button>
    <button type="button" class="btn btn-ghost btn-small" id="ch-reset-no">Huỷ</button>`;
  box.hidden = false;
  $("ch-reset-no").addEventListener("click", () => {
    box.hidden = true;
    box.innerHTML = "";
  });
  $("ch-reset-yes").addEventListener("click", async () => {
    if (classHandling.busy) return;
    box.hidden = true;
    box.innerHTML = "";
    await chHistoryAction("/api/class-noise/reset", true);
  });
  $("ch-reset-no").focus();
});

// ---- Xuất file CSV (bản đang làm việc hiện tại) ----
$("ch-export-btn").addEventListener("click", async () => {
  const btn = $("ch-export-btn");
  setButtonLoading(btn, true, "Đang xuất file...", "Xuất file CSV ↓");
  const data = await chRequest("/api/export-working", {});
  setButtonLoading(btn, false, "Đang xuất file...", "Xuất file CSV ↓");
  if (!data) return;
  setStatusMessage($("ch-status"), `✅ File hiện có ${chNum(data.final_row_count)} dòng. Đang tải...`, "ok");
  const downloadResponse = await fetch(`${API_BASE}/api/download/${data.download_id}`);
  const blob = await downloadResponse.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "spark_class_cleaned.csv";
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
});

// ====== "Cửa" cho workspace.js gọi vào ======
// presetDirection(dir): chọn sẵn thẻ hướng (chỉ còn trong giao diện cũ; Denoise không có thẻ hướng nên là no-op).
window.DenoiseFlow = {
  presetDirection(dir) {
    const card = document.querySelector(`.direction-grid .direction-card[data-direction="${dir}"]`);
    if (card) card.click();
  },
  currentStep() { return state.currentStep; },
  // Nhận dữ liệu CSV từ chuỗi xử lý của 3 nhóm tool (nút "Class Noise" ở "Xong · xử lý tiếp bằng"): dựng thành File
  // rồi coi như người dùng vừa chọn file đó ở bước 1 (có bảng xem trước, chờ bấm Tải lên).
  loadCsvText(text, name) {
    const file = new File([text], name, { type: "text/csv" });
    fileInput.value = "";
    goStep(1);
    handleFileSelected(file);
    setStatusMessage($("upload-status"), "Đã nhận dữ liệu vừa xử lý. Bấm Tải lên để tiếp tục.", "ok");
  },
};

// ====== Khởi động ======
renderStepper();
checkBackendHealth();

})();
