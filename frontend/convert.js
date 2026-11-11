"use strict";

/* ============================================================
   Convert File -- 3 tool đổi ĐỊNH DẠNG (delimiter CSV, CSV<->JSON), TÁCH
   RIÊNG khỏi script.js (luồng Dò & Xử Lý Nhiễu 5 bước). Trang này không có
   "file_id" nào cả -- mỗi lần Convert là 1 request độc lập, xong ngay,
   không có bước "xem rồi xử lý tiếp" nhiều lượt. Vẫn LUÔN gọi backend Flask
   thật (không có chế độ phân tích cục bộ bằng JS), đúng quyết định kiến
   trúc đã chốt chung cho toàn bộ web app (xem CLAUDE.md).
   ============================================================ */

const $ = (id) => document.getElementById(id);

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

const DELIMITER_LABELS = { ",": "dấu phẩy (,)", ";": "dấu chấm phẩy (;)", "\t": "tab", "|": "dấu gạch đứng (|)" };
function delimiterLabel(d) {
  return DELIMITER_LABELS[d] || d;
}

const state = {
  tool: "delimiter", // "delimiter" | "csv-to-json" | "json-to-csv"
  inputMode: "file", // "file" | "paste"
  selectedFile: null,
  lastResult: null,
};

// ====== Cổng xác thực: trang này bắt buộc đăng nhập, DÙNG CHUNG session với
// trang chính (cookie cùng origin) -- không viết lại form đăng nhập ở đây,
// chưa đăng nhập thì chuyển thẳng về index.html (nơi có form thật). ======
async function checkAuth() {
  let data = { user: null };
  try {
    const res = await fetch("/api/auth/me");
    data = await res.json();
  } catch (err) {
    // Không gọi được backend -- checkBackendHealth() bên dưới sẽ tự báo rõ,
    // ở đây không chặn hẳn trang (có thể chỉ là mất mạng tạm thời).
  }
  if (!data.user) {
    window.location.href = "index.html";
    return false;
  }
  $("account-area").hidden = false;
  $("account-username-text").textContent = `👤 ${data.user.username}`;
  return true;
}

// ====== Nhận "nối tiếp" (handoff) từ Free Tools -- tools.html gửi kết quả
// đang xử lý dở sang đây qua sessionStorage (2 trang KHÁC NHAU, không còn
// chung bộ nhớ JS, không dùng được state.pipeline như trong tools.js nữa)
// để người dùng không phải tải file về/tải lên lại. CHỈ áp dụng 1 LẦN DUY
// NHẤT (xoá khỏi sessionStorage ngay sau khi đọc) -- F5 lại trang không bị
// áp lại, không bị "dính" dữ liệu cũ nếu người dùng muốn bắt đầu việc mới. ======
function applyHandoffIfAny() {
  const params = new URLSearchParams(window.location.search);
  if (params.get("handoff") !== "1") return;
  const handoffText = sessionStorage.getItem("spark_handoff_csv");
  sessionStorage.removeItem("spark_handoff_csv");
  if (!handoffText) return;

  const tool = params.get("tool");
  if (tool) {
    const tabBtn = document.querySelector(`.convert-tab[data-tool="${tool}"]`);
    if (tabBtn) tabBtn.click();
  }
  document.querySelector('.convert-input-toggle button[data-mode="paste"]').click();
  $("convert-paste-input").value = handoffText;
  setStatus("📥 Đang dùng kết quả từ Free Tools trước đó -- bấm \"Convert\" để tiếp tục.", "is-ok");

  // Xoá query string khỏi URL -- F5 lại trang sẽ không cố áp dụng lần nữa
  // (dù sessionStorage đã xoá nên có cố cũng không còn gì để đọc, chỉ là
  // dọn URL cho sạch).
  window.history.replaceState({}, "", window.location.pathname);
}
$("logout-btn").addEventListener("click", async () => {
  try {
    await fetch("/api/auth/logout", { method: "POST" });
  } catch (err) {
    // vẫn chuyển trang dù gọi API lỗi -- không giữ người dùng kẹt lại.
  }
  window.location.href = "index.html";
});
// Hồ sơ tài khoản chỉ sống ở trang chính -- ?open=profile để index.html tự
// mở panel đó ngay khi tải xong, đỡ phải bấm "Hồ sơ" thêm 1 lần nữa.
$("open-profile-btn").addEventListener("click", () => {
  window.location.href = "index.html?open=profile";
});

async function checkBackendHealth() {
  const dot = $("backend-dot");
  const text = $("backend-status-text");
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 1500);
    const res = await fetch("/", { method: "GET", signal: ctrl.signal });
    clearTimeout(t);
    dot.className = res ? "status-dot is-online" : "status-dot is-offline";
    text.textContent = res ? "Backend: đã kết nối" : "Backend: chưa kết nối";
  } catch (err) {
    dot.className = "status-dot is-offline";
    text.textContent = "Backend: chưa kết nối";
  }
}

// ====== Chọn tool (3 tab) ======
document.querySelectorAll(".convert-tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".convert-tab").forEach((b) => b.classList.remove("is-active"));
    btn.classList.add("is-active");
    state.tool = btn.dataset.tool;
    document.querySelectorAll(".convert-options").forEach((el) => (el.hidden = true));
    $("convert-options-" + state.tool).hidden = false;
    resetResult();
  });
});

// ====== Chọn kiểu nhập (File / Dán text) ======
$("convert-input-toggle").querySelectorAll("button").forEach((btn) => {
  btn.addEventListener("click", () => {
    $("convert-input-toggle").querySelectorAll("button").forEach((b) => b.classList.remove("is-active"));
    btn.classList.add("is-active");
    state.inputMode = btn.dataset.mode;
    $("convert-dropzone").hidden = state.inputMode !== "file";
    $("convert-paste-input").hidden = state.inputMode !== "paste";
  });
});

// ====== Dropzone chọn file (kéo-thả + bấm chọn) ======
const dropzone = $("convert-dropzone");
const fileInput = $("convert-file-input");
dropzone.addEventListener("click", () => fileInput.click());
dropzone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropzone.classList.add("is-dragover");
});
dropzone.addEventListener("dragleave", () => dropzone.classList.remove("is-dragover"));
dropzone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropzone.classList.remove("is-dragover");
  if (e.dataTransfer.files.length > 0) setSelectedFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener("change", () => {
  if (fileInput.files.length > 0) setSelectedFile(fileInput.files[0]);
});
function setSelectedFile(file) {
  state.selectedFile = file;
  $("convert-file-name").textContent = `${file.name} · ${(file.size / 1024).toFixed(1)} KB`;
}

// ====== Kết quả ======
function resetResult() {
  state.lastResult = null;
  $("convert-result-empty").hidden = false;
  $("convert-result-table-wrap").hidden = true;
  $("convert-result-text").hidden = true;
  $("convert-download-btn").disabled = true;
  setStatus("", "");
  setError("");
}
function setStatus(text, cls) {
  const el = $("convert-status");
  el.textContent = text;
  el.className = "status-text" + (cls ? ` ${cls}` : "");
}
function setError(message) {
  $("convert-error").textContent = message || "";
  $("convert-error").hidden = !message;
}

function renderPreviewTable(rows) {
  const table = $("convert-result-table");
  if (!rows || !rows.length) {
    table.innerHTML = "";
    return;
  }
  const [header, ...body] = rows;
  table.innerHTML =
    "<thead><tr>" + header.map((h) => `<th>${escapeHtml(h)}</th>`).join("") + "</tr></thead>" +
    "<tbody>" + body.map((row) => "<tr>" + row.map((cell) => `<td>${escapeHtml(cell)}</td>`).join("") + "</tr>").join("") + "</tbody>";
}

function showResult(data) {
  state.lastResult = data;
  $("convert-result-empty").hidden = true;
  $("convert-download-btn").disabled = false;

  if (state.tool === "csv-to-json") {
    $("convert-result-table-wrap").hidden = true;
    $("convert-result-text").hidden = false;
    $("convert-result-text").textContent = data.result_text;
    setStatus(`✅ ${data.record_count} record (delimiter: ${delimiterLabel(data.used_delimiter)})`, "is-ok");
    return;
  }

  $("convert-result-text").hidden = true;
  $("convert-result-table-wrap").hidden = false;
  renderPreviewTable(data.preview_rows);
  if (state.tool === "delimiter") {
    setStatus(`✅ ${data.row_count} dòng · đã nhận diện delimiter gốc: ${delimiterLabel(data.used_from_delimiter)}`, "is-ok");
  } else {
    setStatus(`✅ ${data.row_count} dòng · ${data.columns.length} cột`, "is-ok");
  }
}

// ====== Bấm Convert ======
$("convert-run-btn").addEventListener("click", async () => {
  setError("");
  const formData = new FormData();

  if (state.inputMode === "file") {
    if (!state.selectedFile) return setError("Chưa chọn file nào.");
    formData.append("file", state.selectedFile);
  } else {
    const text = $("convert-paste-input").value;
    if (!text.trim()) return setError("Chưa dán nội dung nào.");
    formData.append("text", text);
  }

  let url;
  if (state.tool === "delimiter") {
    url = "/api/convert/delimiter";
    formData.append("from_delimiter", $("opt-from-delim").value);
    formData.append("to_delimiter", $("opt-to-delim").value);
  } else if (state.tool === "csv-to-json") {
    url = "/api/convert/csv-to-json";
    formData.append("has_header", $("opt-has-header-c2j").checked ? "true" : "false");
    formData.append("delimiter", $("opt-delim-c2j").value);
    formData.append("shape", $("opt-shape-c2j").value);
    formData.append("convert_types", $("opt-convert-types").checked ? "true" : "false");
    formData.append("indent", $("opt-indent").checked ? "true" : "false");
  } else {
    url = "/api/convert/json-to-csv";
    formData.append("output_delimiter", $("opt-out-delim").value);
  }

  const btn = $("convert-run-btn");
  btn.disabled = true;
  btn.textContent = "Đang convert...";
  setStatus("");

  let response, data;
  try {
    response = await fetch(url, { method: "POST", body: formData });
    data = await response.json();
  } catch (err) {
    btn.disabled = false;
    btn.textContent = "Convert";
    setError("Không gọi được backend. Kiểm tra xem python3 app.py có đang chạy không.");
    return;
  }
  btn.disabled = false;
  btn.textContent = "Convert";

  if (!response.ok) {
    setError(data.error || "Convert thất bại.");
    return;
  }
  showResult(data);
});

// ====== Tải xuống kết quả (xử lý ngay trên trình duyệt bằng Blob, không
// cần gọi thêm API nào -- result_text server đã trả đủ ở bước Convert) ======
$("convert-download-btn").addEventListener("click", () => {
  if (!state.lastResult) return;
  const isJson = state.tool === "csv-to-json";
  const blob = new Blob([state.lastResult.result_text], {
    type: (isJson ? "application/json" : "text/csv") + ";charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `converted.${isJson ? "json" : "csv"}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
});

// ====== Khởi động ======
checkAuth().then((loggedIn) => {
  if (loggedIn) applyHandoffIfAny();
});
checkBackendHealth();
