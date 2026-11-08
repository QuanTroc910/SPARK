"use strict";

/* ============================================================
   Free Tools -- 4 công cụ xử lý nhiễu KHÔNG cần cấu hình tay (Xoá dòng
   trùng / Cắt khoảng trắng thừa / Điền-xoá ô trống / Xoá dòng trống hoàn
   toàn), TÁCH RIÊNG khỏi script.js (luồng Workspace 5 bước) -- giống
   convert.js, trang này không có "file_id" nào cả, mỗi lần Chạy là 1
   request độc lập, xong ngay. Vẫn LUÔN gọi backend Flask thật (không có
   chế độ phân tích cục bộ bằng JS), đúng quyết định kiến trúc đã chốt
   chung cho toàn bộ web app (xem CLAUDE.md).
   ============================================================ */

const $ = (id) => document.getElementById(id);

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

const state = {
  tool: "remove-duplicates", // khớp ĐÚNG hậu tố route /api/noise-tools/<tool>
  inputMode: "file", // "file" | "paste"
  selectedFile: null,
  lastResult: null,
};

// ====== Cổng xác thực: giống convert.js -- bắt buộc đăng nhập, dùng chung
// session với trang chính, chưa đăng nhập thì chuyển thẳng về index.html. ======
async function checkAuth() {
  let data = { user: null };
  try {
    const res = await fetch("/api/auth/me");
    data = await res.json();
  } catch (err) {
    // Không gọi được backend -- checkBackendHealth() bên dưới sẽ tự báo rõ.
  }
  if (!data.user) {
    window.location.href = "index.html";
    return;
  }
  $("account-area").hidden = false;
  $("account-username-text").textContent = `👤 ${data.user.username}`;
}
$("logout-btn").addEventListener("click", async () => {
  try {
    await fetch("/api/auth/logout", { method: "POST" });
  } catch (err) {
    // vẫn chuyển trang dù gọi API lỗi -- không giữ người dùng kẹt lại.
  }
  window.location.href = "index.html";
});
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

// ====== Chọn tool (4 tab) ======
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

// ====== Tuỳ chọn riêng tool "Điền/xoá ô trống": ô "Giá trị điền vào" chỉ
// hiện khi chọn "Điền giá trị cố định" ======
$("opt-action").addEventListener("change", () => {
  $("opt-fixed-value-wrap").hidden = $("opt-action").value !== "fixed_value";
});

// ====== Kết quả ======
function resetResult() {
  state.lastResult = null;
  $("convert-result-empty").hidden = false;
  $("convert-result-table-wrap").hidden = true;
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

// Gộp stats (original_row_count/removed_row_count/final_row_count/cells_changed)
// thành 1 câu dễ hiểu cho người dùng KHÔNG rành kỹ thuật -- ưu tiên nói về
// SỐ DÒNG trước (dễ cảm nhận hơn "số ô"), chỉ nói thêm "số ô đã sửa" nếu có.
function statusFromStats(stats) {
  const parts = [];
  if (stats.removed_row_count > 0) {
    parts.push(`đã xoá ${stats.removed_row_count} dòng (${stats.original_row_count} → ${stats.final_row_count})`);
  } else {
    parts.push(`giữ nguyên ${stats.final_row_count} dòng`);
  }
  if (stats.cells_changed > 0) {
    parts.push(`đã sửa ${stats.cells_changed} ô`);
  }
  return `✅ ${parts.join(" · ")}`;
}

function showResult(data) {
  state.lastResult = data;
  $("convert-result-empty").hidden = true;
  $("convert-download-btn").disabled = false;
  $("convert-result-table-wrap").hidden = false;
  renderPreviewTable(data.preview_rows);
  setStatus(statusFromStats(data.stats), "is-ok");
}

// ====== Bấm Chạy ======
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

  if (state.tool === "remove-duplicates") {
    formData.append("subset_columns", $("opt-subset-columns").value);
    formData.append("keep", $("opt-keep").value);
  } else if (state.tool === "fill-blanks") {
    const column = $("opt-column").value.trim();
    if (!column) return setError("Chưa gõ tên cột cần xử lý.");
    const action = $("opt-action").value;
    if (action === "fixed_value" && !$("opt-fixed-value").value) {
      return setError("Chưa nhập giá trị để điền vào ô trống.");
    }
    formData.append("column", column);
    formData.append("action", action);
    formData.append("fixed_value", $("opt-fixed-value").value);
  }
  // "trim-whitespace" và "remove-empty-rows" không có tham số nào thêm.

  const url = "/api/noise-tools/" + state.tool;
  const btn = $("convert-run-btn");
  btn.disabled = true;
  btn.textContent = "Đang chạy...";
  setStatus("");

  let response, data;
  try {
    response = await fetch(url, { method: "POST", body: formData });
    data = await response.json();
  } catch (err) {
    btn.disabled = false;
    btn.textContent = "Chạy";
    setError("Không gọi được backend. Kiểm tra xem python3 app.py có đang chạy không.");
    return;
  }
  btn.disabled = false;
  btn.textContent = "Chạy";

  if (!response.ok) {
    setError(data.error || "Xử lý thất bại.");
    return;
  }
  showResult(data);
});

// ====== Tải xuống kết quả (xử lý ngay trên trình duyệt bằng Blob, không
// cần gọi thêm API nào -- result_text server đã trả đủ ở bước Chạy) ======
$("convert-download-btn").addEventListener("click", () => {
  if (!state.lastResult) return;
  const blob = new Blob([state.lastResult.result_text], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${state.tool}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
});

// ====== Khởi động ======
checkAuth();
checkBackendHealth();
