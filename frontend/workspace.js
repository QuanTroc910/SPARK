"use strict";

/* ============================================================
   workspace.js -- logic cho trang workspace.html.

   ĐÃ GỘP (xem comment đầu workspace.html): phần thân trang giờ có 2 KHỐI
   cùng tồn tại trên 1 trang -- #section-free-tools (trước ở tools.js) và
   #section-convert (trước ở convert.js) -- chuyển khối bằng switchSection(),
   KHÔNG còn điều hướng sang trang khác nữa. Nhờ gộp vào 1 trang, cơ chế
   "nối tiếp" sang Convert (trước phải gửi qua sessionStorage + query param
   vì convert.js là JS của 1 trang KHÁC) giờ chỉ cần gán trực tiếp text đang
   xử lý sang ô dán text của Convert (cùng 1 bộ nhớ JS, xem phần cuối
   renderContinuePanel() bên dưới) -- đơn giản hơn, ít lỗi hơn hẳn.

   QUY ƯỚC ĐẶT TÊN để 2 khối không đụng nhau trên CÙNG 1 trang:
   - ID phần tử nào TRÙNG TÊN giữa 2 khối (vd cũ cùng là "convert-tabs",
     "convert-dropzone"...) thì khối Free Tools đổi sang tiền tố "ft-"
     (ft-tabs, ft-dropzone...), khối Convert giữ nguyên tên cũ.
   - ID/class nào KHÔNG trùng (convert-options-*, opt-*, tool-hero,
     pipeline-*, continue-*) giữ nguyên, không đổi.
   - Lớp CSS DÙNG CHUNG (.convert-tab, .convert-options, .convert-panel...)
     vẫn style giống nhau cho cả 2 khối -- khi querySelectorAll theo CLASS có
     thể khớp nhầm sang khối kia, phải SCOPE bằng container (#ft-tabs/
     #convert-tabs cho tab, #section-free-tools/#section-convert cho
     .convert-options) -- xem activateFtTool()/activateCvTool() bên dưới.
   ============================================================ */

const $ = (id) => document.getElementById(id);

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

// Hàm dùng CHUNG cho cả 2 khối (tham số hoá bằng phần tử DOM cụ thể, thay vì
// tự tìm ID bên trong -- tránh phải viết 2 bản y hệt cho 2 khối).
function setStatus(el, text, cls) {
  el.textContent = text;
  el.className = "status-text" + (cls ? ` ${cls}` : "");
}
function setError(el, message) {
  el.textContent = message || "";
  el.hidden = !message;
}
function renderPreviewTable(table, rows) {
  if (!rows || !rows.length) {
    table.innerHTML = "";
    return;
  }
  const [header, ...body] = rows;
  table.innerHTML =
    "<thead><tr>" + header.map((h) => `<th>${escapeHtml(h)}</th>`).join("") + "</tr></thead>" +
    "<tbody>" + body.map((row) => "<tr>" + row.map((cell) => `<td>${escapeHtml(cell)}</td>`).join("") + "</tr>").join("") + "</tbody>";
}
function wireDropzone(dropzoneEl, fileInputEl, onFile) {
  dropzoneEl.addEventListener("click", () => fileInputEl.click());
  dropzoneEl.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropzoneEl.classList.add("is-dragover");
  });
  dropzoneEl.addEventListener("dragleave", () => dropzoneEl.classList.remove("is-dragover"));
  dropzoneEl.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzoneEl.classList.remove("is-dragover");
    if (e.dataTransfer.files.length > 0) onFile(e.dataTransfer.files[0]);
  });
  fileInputEl.addEventListener("change", () => {
    if (fileInputEl.files.length > 0) onFile(fileInputEl.files[0]);
  });
}
function wireInputToggle(toggleEl, dropzoneEl, pasteEl, onModeChange) {
  toggleEl.querySelectorAll("button").forEach((btn) => {
    btn.addEventListener("click", () => {
      toggleEl.querySelectorAll("button").forEach((b) => b.classList.remove("is-active"));
      btn.classList.add("is-active");
      const mode = btn.dataset.mode;
      dropzoneEl.hidden = mode !== "file";
      pasteEl.hidden = mode !== "paste";
      onModeChange(mode);
    });
  });
}

const state = {
  section: "free-tools", // "free-tools" | "convert" -- khối đang hiện
  ft: {
    tool: "remove-duplicates", // khớp ĐÚNG hậu tố route /api/noise-tools/<tool>
    inputMode: "file",
    selectedFile: null,
    activeContinueCategory: null,
    // "Nối tiếp" trong CHÍNH khối Free Tools (chạy nhiều tool liên tiếp mà
    // không cần tải file về/tải lên lại) -- xem showFtResult() bên dưới.
    pipeline: { active: false, originalText: null, originalLabel: "", currentText: null, steps: [], forceNewUpload: false },
  },
  cv: {
    tool: "delimiter", // "delimiter" | "csv-to-json" | "json-to-csv"
    inputMode: "file",
    selectedFile: null,
    lastResult: null,
  },
};

// ====== Cổng xác thực: bắt buộc đăng nhập, dùng chung session với trang
// chính, chưa đăng nhập thì chuyển thẳng về index.html (nơi có form đăng
// nhập thật). ======
async function checkAuth() {
  let data = { user: null };
  try {
    const res = await fetch("/api/auth/me");
    data = await res.json();
  } catch (err) {
    // Không gọi được backend -- checkBackendHealth() bên dưới tự báo rõ.
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
  // Header chỉ còn 1 chấm tròn màu, không có chữ đi kèm -- giữ thông tin đó
  // dưới dạng `title` (tooltip khi rê chuột vào chấm tròn).
  const dot = $("backend-dot");
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 1500);
    const res = await fetch("/", { method: "GET", signal: ctrl.signal });
    clearTimeout(t);
    dot.className = res ? "status-dot is-online" : "status-dot is-offline";
    dot.title = res ? "Backend: đã kết nối" : "Backend: chưa kết nối";
  } catch (err) {
    dot.className = "status-dot is-offline";
    dot.title = "Backend: chưa kết nối";
  }
}

// ====== Chuyển khối (Free Tools <-> Convert) -- thay cho việc điều hướng
// sang trang khác trước đây. Cuộn lên đầu trang để người dùng không bị lạc
// khi nội dung đổi hẳn bên dưới header. ======
function switchSection(section) {
  state.section = section;
  $("section-free-tools").hidden = section !== "free-tools";
  $("section-convert").hidden = section !== "convert";
  window.scrollTo({ top: 0, behavior: "smooth" });
}

// ====== Dropdown "Product" -- bấm để mở/đóng, bấm ra ngoài hoặc nhấn Esc
// thì tự đóng (kiểu dropdown chuẩn, không cần thư viện ngoài). ======
const productWrap = $("ws-product-wrap");
const productBtn = $("ws-product-btn");
const productMenu = $("ws-product-menu");

function setProductMenuOpen(open) {
  productMenu.hidden = !open;
  productWrap.classList.toggle("is-open", open);
  productBtn.setAttribute("aria-expanded", open ? "true" : "false");
}

productBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  setProductMenuOpen(productMenu.hidden);
});

document.addEventListener("click", (e) => {
  if (!productWrap.contains(e.target)) setProductMenuOpen(false);
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") setProductMenuOpen(false);
});

// Cột "Tự động" -- chuyển sang khối Free Tools + đúng tab. Cột "Convert" --
// chuyển sang khối Convert + đúng tab. Cả 2 đều CHUYỂN TẠI CHỖ (không điều
// hướng đi đâu), xem activateFtTool()/activateCvTool() định nghĩa bên dưới.
productMenu.querySelectorAll("a.ws-megamenu-item[data-tool]").forEach((a) => {
  a.addEventListener("click", (e) => {
    e.preventDefault();
    switchSection("free-tools");
    activateFtTool(a.dataset.tool);
    setProductMenuOpen(false);
  });
});
productMenu.querySelectorAll("a.ws-megamenu-item[data-convert-tool]").forEach((a) => {
  a.addEventListener("click", (e) => {
    e.preventDefault();
    switchSection("convert");
    activateCvTool(a.dataset.convertTool);
    setProductMenuOpen(false);
  });
});

/* ============================================================
   KHỐI: FREE TOOLS -- gộp từ tools.js, giữ nguyên toàn bộ logic, chỉ đổi
   tên phần tử trùng ID sang tiền tố "ft-" (xem quy ước đầu file) + đổi tên
   hàm thêm "Ft" để phân biệt với khối Convert bên dưới.
   ============================================================ */

function mockRow(cellClasses, removed) {
  const cells = cellClasses.map((c) => `<span class="tool-mock-cell${c ? " " + c : ""}"></span>`).join("");
  return `<div class="tool-mock-row${removed ? " is-removed" : ""}">${cells}</div>`;
}
function mockBox(label, rowsHtml) {
  return `<div class="tool-mock-box"><span class="tool-mock-label">${label}</span>${rowsHtml}</div>`;
}
function mockPair(beforeRows, afterRows, delta) {
  return (
    `<div class="tool-mock">${mockBox("TRƯỚC", beforeRows)}` +
    `<span class="tool-mock-delta">→<span class="tool-mock-delta-label">${delta}</span></span>` +
    `${mockBox("SAU", afterRows)}</div>`
  );
}

const TOOL_INFO = {
  "remove-duplicates": {
    headline: "XOÁ DÒNG TRÙNG<br>TRONG FILE CSV",
    desc: "Tìm và xoá các dòng lặp lại chỉ trong vài giây. So khớp trên mọi cột, hoặc chỉ những cột xác định 1 bản ghi (vd email) -- bản đầu tiên (hoặc cuối cùng) luôn được giữ lại.",
    mock: mockPair(
      mockRow([]) + mockRow(["is-hit"]) + mockRow([]),
      mockRow([]) + mockRow([]),
      "-1 DÒNG"
    ),
    steps: [
      "Thả file CSV/Excel vào, hoặc dán text.",
      "Chọn cột xác định trùng lặp (để trống = so toàn bộ cột).",
      "Xem số dòng đã xoá, rồi tải file đã làm sạch.",
    ],
    explainer: [
      {
        t: "Thế nào là trùng",
        b: "Mặc định, 1 dòng bị coi là trùng khi MỌI cột khớp y hệt dòng trước đó. Chọn cột cụ thể để coi 2 dòng là cùng 1 bản ghi dù các cột khác khác nhau.",
      },
      {
        t: "Vì sao gần-trùng lọt lưới",
        b: `"an@x.com" và "AN@X.com" giống nhau với người nhưng khác nhau với máy. Bật "Bỏ qua hoa/thường" và "Bỏ qua khoảng trắng thừa" để bắt được cả 2 trường hợp đó.`,
      },
      PRIVACY_COLUMN(),
    ],
  },
  "trim-whitespace": {
    headline: "CẮT KHOẢNG TRẮNG THỪA<br>TRONG FILE CSV",
    desc: "Cắt khoảng trắng vô hình làm 2 giá trị tưởng giống nhau mà máy tính lại coi là khác nhau: khoảng trắng đầu/cuối, non-breaking space, và ký tự zero-width.",
    mock: mockPair(
      mockRow(["is-hit"]) + mockRow(["", "is-hit"]) + mockRow([]),
      mockRow(["is-fixed"]) + mockRow(["", "is-fixed"]) + mockRow([]),
      "3 Ô"
    ),
    steps: [
      "Thả file CSV/Excel vào, hoặc dán text.",
      "Chọn có gộp khoảng trắng lặp lại/xoá ký tự vô hình hay không.",
      "Xem số ô đã đổi, rồi tải file đã làm sạch.",
    ],
    explainer: [
      {
        t: "Những gì bị xoá",
        b: `Khoảng trắng đầu/cuối MỌI ô (kể cả non-breaking space) luôn bị cắt. "Gộp khoảng trắng lặp lại" biến "a␣␣b" thành "a␣b"; "Xoá ký tự vô hình" bỏ các ký tự zero-width không nhìn thấy nhưng vẫn tính là ký tự.`,
      },
      {
        t: "Vì sao quan trọng",
        b: `1 khoảng trắng thừa biến "Hà Nội " thành giá trị KHÁC "Hà Nội" -- lookup/so khớp sẽ thất bại, kiểm tra trùng lặp sẽ bỏ sót. Cắt khoảng trắng trước giúp mọi bước xử lý sau đáng tin hơn.`,
      },
      PRIVACY_COLUMN(),
    ],
  },
  "fill-blanks": {
    headline: "ĐIỀN / XOÁ Ô TRỐNG<br>TRONG FILE CSV",
    desc: "Thay ô trống bằng giá trị bạn chọn, điền theo giá trị ở dòng gần nhất phía trên, hoặc xoá hẳn cả dòng thiếu -- áp dụng cho ĐÚNG 1 cột bạn chỉ định.",
    mock: mockPair(
      mockRow([]) + mockRow(["is-hit"]) + mockRow([]),
      mockRow([]) + mockRow(["is-fixed"]) + mockRow([]),
      "1 Ô"
    ),
    steps: [
      "Thả file CSV/Excel vào, hoặc dán text.",
      "Gõ tên cột cần xử lý, chọn cách điền/xoá.",
      "Xem số ô đã đổi (hoặc số dòng đã xoá), rồi tải file.",
    ],
    explainer: [
      {
        t: "3 cách điền/xoá",
        b: `"Điền theo giá trị phía trên" copy giá trị KHÔNG trống GẦN NHẤT phía trên xuống (hợp với báo cáo theo nhóm, mỗi nhóm chỉ ghi tên 1 lần). "Điền giá trị cố định" dùng ĐÚNG 1 giá trị bạn gõ (vd "Không rõ"). "Xoá cả dòng" bỏ hẳn dòng thiếu.`,
      },
      {
        t: "Dòng đầu tiên trống thì sao",
        b: `"Điền theo giá trị phía trên" cần 1 giá trị PHÍA TRÊN để điền -- dòng đầu tiên (hoặc cả nhóm đầu) trống thì KHÔNG có gì để điền, SPARK giữ nguyên trống thay vì đoán bừa.`,
      },
      PRIVACY_COLUMN(),
    ],
  },
  "remove-empty-rows": {
    headline: "XOÁ DÒNG TRỐNG<br>TRONG FILE CSV",
    desc: "Xoá các dòng không có giá trị nào cả, kể cả dòng chỉ toàn khoảng trắng/dấu phẩy rỗng -- tuỳ chọn thêm: xoá luôn cột nào trống hoàn toàn từ trên xuống dưới.",
    mock: mockPair(
      mockRow([]) + mockRow([], true) + mockRow([]),
      mockRow([]) + mockRow([]),
      "-1 DÒNG"
    ),
    steps: [
      "Thả file CSV/Excel vào, hoặc dán text.",
      "Chọn có xoá luôn cột trống hoàn toàn hay không.",
      "Tải file không còn dòng/cột trống.",
    ],
    explainer: [
      {
        t: "Thế nào là trống",
        b: "1 dòng bị coi là trống khi MỌI cột đều trống hoặc chỉ chứa khoảng trắng -- dòng còn ít nhất 1 giá trị thì vẫn được giữ lại, dù phần lớn ô khác trống.",
      },
      {
        t: "Cột trống hoàn toàn",
        b: "File xuất ra đôi khi có cột chưa từng được điền gì (lỗi mẫu/thiếu dữ liệu nguồn). Bật tuỳ chọn này để xoá luôn cột đó, không chỉ dòng.",
      },
      PRIVACY_COLUMN(),
    ],
  },
};

function PRIVACY_COLUMN() {
  return {
    t: "Riêng tư theo thiết kế",
    b: "File được backend Flask thật đọc để xử lý rồi xoá file tạm NGAY sau khi đọc xong (xem _read_df_for_noise_tool() -- không giữ lại bản nào) -- vẫn cần đăng nhập như mọi chỗ khác trong Denoise, nhưng không lưu file bạn gửi lên.",
  };
}

function renderFtToolHero(tool) {
  const info = TOOL_INFO[tool];
  $("tool-hero").innerHTML = `
    <div class="tool-hero-grid">
      <div>
        <p class="auth-eyebrow">[ FREE TOOLS ]</p>
        <h1 class="tool-hero-headline">${info.headline}</h1>
        <p class="tool-hero-desc">${info.desc}</p>
      </div>
      ${info.mock}
    </div>`;
}
function renderFtToolSteps(tool) {
  const info = TOOL_INFO[tool];
  $("tool-steps").innerHTML = info.steps
    .map((s, i) => `<div><p class="tool-step-num">0${i + 1}</p><p class="tool-step-text">${escapeHtml(s)}</p></div>`)
    .join("");
}
function renderFtToolExplainer(tool) {
  const info = TOOL_INFO[tool];
  $("tool-explainer").innerHTML = info.explainer
    .map((e) => `<div><p class="tool-explainer-title">${escapeHtml(e.t)}</p><p class="tool-explainer-body">${escapeHtml(e.b)}</p></div>`)
    .join("");
}

/* ====== Chọn tool (4 tab) -- activateFtTool() dùng chung cho cả bấm tab
   thật LẪN bấm 1 mục "Tự động" trong panel "Xử lý tiếp" / dropdown Product. ====== */
function activateFtTool(tool) {
  document.querySelectorAll("#ft-tabs .convert-tab").forEach((b) => b.classList.toggle("is-active", b.dataset.tool === tool));
  state.ft.tool = tool;
  // SCOPE theo #section-free-tools -- ".convert-options" là class DÙNG
  // CHUNG với khối Convert, không scope sẽ ẩn/hiện nhầm cả options của Convert.
  document.querySelectorAll("#section-free-tools .convert-options").forEach((el) => (el.hidden = el.id !== "convert-options-" + tool));
  renderFtToolHero(tool);
  renderFtToolSteps(tool);
  renderFtToolExplainer(tool);
  resetFtResult();
}
document.querySelectorAll("#ft-tabs .convert-tab").forEach((btn) => {
  btn.addEventListener("click", () => activateFtTool(btn.dataset.tool));
});

// ====== Chọn kiểu nhập (File / Dán text) ======
wireInputToggle($("ft-input-toggle"), $("ft-dropzone"), $("ft-paste-input"), (mode) => {
  state.ft.inputMode = mode;
});

// ====== Dropzone chọn file (kéo-thả + bấm chọn) ======
wireDropzone($("ft-dropzone"), $("ft-file-input"), (file) => {
  state.ft.selectedFile = file;
  $("ft-file-name").textContent = `${file.name} · ${(file.size / 1024).toFixed(1)} KB`;
});

// ====== Tuỳ chọn riêng tool "Điền/xoá ô trống": ô "Giá trị điền vào" chỉ
// hiện khi chọn "Điền giá trị cố định" ======
$("opt-action").addEventListener("change", () => {
  $("opt-fixed-value-wrap").hidden = $("opt-action").value !== "fixed_value";
});

/* ====== Thanh "nối tiếp" (pipeline) ====== */
function renderFtPipelineStrip() {
  const p = state.ft.pipeline;
  const strip = $("pipeline-strip");
  const showUpload = !p.active || p.forceNewUpload;
  $("ft-input-toggle").hidden = !showUpload;
  $("ft-dropzone").hidden = !showUpload || state.ft.inputMode !== "file";
  $("ft-paste-input").hidden = !showUpload || state.ft.inputMode !== "paste";

  if (!p.active) {
    strip.hidden = true;
    return;
  }
  strip.hidden = false;
  const stepsText = p.steps.length ? ` · đã qua: ${p.steps.map((s) => s.label).join(" → ")}` : " · chưa xử lý bước nào";
  $("pipeline-strip-text").innerHTML = `📄 Đang dùng: <strong>${escapeHtml(p.originalLabel)}</strong>${escapeHtml(stepsText)}`;
}
$("pipeline-new-file-btn").addEventListener("click", () => {
  state.ft.pipeline.forceNewUpload = true;
  renderFtPipelineStrip();
});
$("pipeline-reset-btn").addEventListener("click", () => {
  state.ft.pipeline.currentText = state.ft.pipeline.originalText;
  state.ft.pipeline.steps = [];
  state.ft.pipeline.forceNewUpload = false;
  renderFtPipelineStrip();
  resetFtResult();
});

/* ====== Kết quả ====== */
function resetFtResult() {
  $("ft-result-empty").hidden = false;
  $("ft-result-table-wrap").hidden = true;
  $("ft-download-btn").disabled = true;
  $("continue-panel").hidden = true;
  state.ft.activeContinueCategory = null;
  $("continue-list").innerHTML = "";
  document.querySelectorAll(".continue-pill").forEach((b) => b.classList.remove("is-active"));
  setStatus($("ft-status"), "", "");
  setError($("ft-error"), "");
}

function statusFromStats(stats) {
  const parts = [];
  if (stats.removed_row_count > 0) {
    parts.push(`đã xoá ${stats.removed_row_count} dòng (${stats.original_row_count} → ${stats.final_row_count})`);
  } else {
    parts.push(`giữ nguyên ${stats.final_row_count} dòng`);
  }
  if (stats.cells_changed > 0) parts.push(`đã sửa ${stats.cells_changed} ô`);
  if (stats.columns_removed) parts.push(`đã xoá ${stats.columns_removed} cột`);
  return `✅ ${parts.join(" · ")}`;
}

const TOOL_TAB_LABEL = {
  "remove-duplicates": "Xoá dòng trùng",
  "trim-whitespace": "Cắt khoảng trắng",
  "fill-blanks": "Điền/xoá ô trống",
  "remove-empty-rows": "Xoá dòng trống",
};

function showFtResult(data, inputLabel) {
  $("ft-result-empty").hidden = true;
  $("ft-download-btn").disabled = false;
  $("ft-result-table-wrap").hidden = false;
  renderPreviewTable($("ft-result-table"), data.preview_rows);
  setStatus($("ft-status"), statusFromStats(data.stats), "is-ok");

  const p = state.ft.pipeline;
  if (!p.active) {
    p.active = true;
    p.originalText = data.result_text;
    p.originalLabel = inputLabel;
    p.currentText = data.result_text;
    p.steps = [{ label: TOOL_TAB_LABEL[state.ft.tool] }];
  } else {
    p.currentText = data.result_text;
    p.steps.push({ label: TOOL_TAB_LABEL[state.ft.tool] });
  }
  p.forceNewUpload = false;
  renderFtPipelineStrip();
  renderContinuePanel();
}

/* ====== Panel "Xử lý tiếp" -- 3 danh mục y hệt dropdown Product ở header.
   "Cần cấu hình" KHÔNG bấm được (chưa có khối đích); "Tự động" chuyển tab
   NGAY TRONG khối Free Tools; "Convert" giờ CHUYỂN KHỐI tại chỗ (thay cho
   điều hướng sang convert.html + sessionStorage trước đây -- 2 khối giờ
   chung 1 trang, chung bộ nhớ JS, gán trực tiếp pipeline.currentText sang
   ô dán text của Convert là đủ). ====== */
const CONTINUE_CATEGORIES = {
  configure: {
    items: [
      { icon: "📝", label: "Sai định dạng", sub: "Cần vào Workspace" },
      { icon: "📏", label: "Ngoài khoảng", sub: "Cần vào Workspace" },
      { icon: "📈", label: "Giá trị bất thường", sub: "Cần vào Workspace" },
      { icon: "🧩", label: "Không nhất quán", sub: "Cần vào Workspace" },
      { icon: "🧮", label: "Thiếu giá trị (nâng cao)", sub: "Cần vào Workspace" },
      { icon: "🔗", label: "Rule liên cột", sub: "Cần vào Workspace" },
    ],
  },
  convert: {
    items: [
      { icon: "↔", label: "Đổi delimiter CSV", convertTool: "delimiter" },
      { icon: "{ }", label: "CSV → JSON", convertTool: "csv-to-json" },
      { icon: "{ }", label: "JSON → CSV", convertTool: "json-to-csv" },
    ],
  },
  auto: {
    items: [
      { icon: "🧬", label: "Xoá dòng trùng", tool: "remove-duplicates" },
      { icon: "✂️", label: "Cắt khoảng trắng thừa", tool: "trim-whitespace" },
      { icon: "🩹", label: "Điền/xoá ô trống", tool: "fill-blanks" },
      { icon: "🗑️", label: "Xoá dòng trống hoàn toàn", tool: "remove-empty-rows" },
    ],
  },
};

function renderContinuePanel() {
  $("continue-panel").hidden = false;
}
document.querySelectorAll(".continue-pill").forEach((pill) => {
  pill.addEventListener("click", () => {
    const category = pill.dataset.category;
    const isReopening = state.ft.activeContinueCategory === category;
    state.ft.activeContinueCategory = isReopening ? null : category;
    document.querySelectorAll(".continue-pill").forEach((b) => b.classList.toggle("is-active", b === pill && !isReopening));
    const list = $("continue-list");
    if (isReopening) {
      list.innerHTML = "";
      return;
    }
    const items = CONTINUE_CATEGORIES[category].items;
    list.innerHTML = items
      .map((item) => {
        const inner = `<span class="continue-item-icon">${item.icon}</span><span>${escapeHtml(item.label)}${item.sub ? `<small>${escapeHtml(item.sub)}</small>` : ""}</span>`;
        if (item.tool) return `<a class="continue-item" href="#" data-tool="${item.tool}">${inner}</a>`;
        if (item.convertTool) return `<a class="continue-item" href="#" data-convert-tool="${item.convertTool}">${inner}</a>`;
        return `<div class="continue-item continue-item--static">${inner}</div>`;
      })
      .join("");
    list.querySelectorAll("a[data-tool]").forEach((a) => {
      a.addEventListener("click", (e) => {
        e.preventDefault();
        activateFtTool(a.dataset.tool);
      });
    });
    list.querySelectorAll("a[data-convert-tool]").forEach((a) => {
      a.addEventListener("click", (e) => {
        e.preventDefault();
        const tool = a.dataset.convertTool;
        switchSection("convert");
        activateCvTool(tool);
        // Gán trực tiếp kết quả Free Tools đang có sang ô dán text của
        // Convert -- cùng 1 trang, cùng 1 bộ nhớ JS, không cần sessionStorage.
        const text = state.ft.pipeline.currentText;
        if (text) {
          document.querySelector('#convert-input-toggle button[data-mode="paste"]').click();
          $("convert-paste-input").value = text;
          setStatus($("convert-status"), '📥 Đang dùng kết quả từ Free Tools trước đó -- bấm "Convert" để tiếp tục.', "is-ok");
        }
      });
    });
  });
});

// ====== Bấm Chạy ======
$("ft-run-btn").addEventListener("click", async () => {
  setError($("ft-error"), "");
  const formData = new FormData();
  const p = state.ft.pipeline;
  const usePipeline = p.active && !p.forceNewUpload;
  let inputLabel = p.originalLabel;

  if (usePipeline) {
    formData.append("text", p.currentText);
  } else if (state.ft.inputMode === "file") {
    if (!state.ft.selectedFile) return setError($("ft-error"), "Chưa chọn file nào.");
    formData.append("file", state.ft.selectedFile);
    inputLabel = state.ft.selectedFile.name;
  } else {
    const text = $("ft-paste-input").value;
    if (!text.trim()) return setError($("ft-error"), "Chưa dán nội dung nào.");
    formData.append("text", text);
    inputLabel = "văn bản dán tay";
  }

  if (state.ft.tool === "remove-duplicates") {
    formData.append("subset_columns", $("opt-subset-columns").value);
    formData.append("keep", $("opt-keep").value);
    formData.append("ignore_case", $("opt-ignore-case").checked ? "true" : "false");
    formData.append("ignore_whitespace", $("opt-ignore-whitespace").checked ? "true" : "false");
  } else if (state.ft.tool === "trim-whitespace") {
    formData.append("collapse_repeated", $("opt-collapse-repeated").checked ? "true" : "false");
    formData.append("remove_zero_width", $("opt-remove-zero-width").checked ? "true" : "false");
  } else if (state.ft.tool === "fill-blanks") {
    const column = $("opt-column").value.trim();
    if (!column) return setError($("ft-error"), "Chưa gõ tên cột cần xử lý.");
    const action = $("opt-action").value;
    if (action === "fixed_value" && !$("opt-fixed-value").value) {
      return setError($("ft-error"), "Chưa nhập giá trị để điền vào ô trống.");
    }
    formData.append("column", column);
    formData.append("action", action);
    formData.append("fixed_value", $("opt-fixed-value").value);
  } else if (state.ft.tool === "remove-empty-rows") {
    formData.append("also_remove_empty_columns", $("opt-remove-empty-columns").checked ? "true" : "false");
  }

  const url = "/api/noise-tools/" + state.ft.tool;
  const btn = $("ft-run-btn");
  btn.disabled = true;
  btn.textContent = "Đang chạy...";
  setStatus($("ft-status"), "");

  let response, data;
  try {
    response = await fetch(url, { method: "POST", body: formData });
    data = await response.json();
  } catch (err) {
    btn.disabled = false;
    btn.textContent = "Chạy";
    setError($("ft-error"), "Không gọi được backend. Kiểm tra xem python3 app.py có đang chạy không.");
    return;
  }
  btn.disabled = false;
  btn.textContent = "Chạy";

  if (!response.ok) {
    setError($("ft-error"), data.error || "Xử lý thất bại.");
    return;
  }
  showFtResult(data, inputLabel);
});

// ====== Tải xuống kết quả hiện tại (dùng pipeline.currentText -- LUÔN là
// kết quả MỚI NHẤT, dù đã nối tiếp qua bao nhiêu tool) ======
$("ft-download-btn").addEventListener("click", () => {
  if (!state.ft.pipeline.currentText) return;
  const blob = new Blob([state.ft.pipeline.currentText], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = state.ft.pipeline.steps.length > 1 ? "da-xu-ly.csv" : `${state.ft.tool}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
});

/* ============================================================
   KHỐI: CONVERT FILE -- gộp từ convert.js, giữ nguyên ID/logic (không trùng
   tên với khối Free Tools nên không cần đổi tiền tố) + đổi tên hàm thêm
   "Cv" để phân biệt. Cơ chế "nhận nối tiếp" qua sessionStorage/query param
   (applyHandoffIfAny() cũ) đã BỎ -- xem renderContinuePanel() ở khối Free
   Tools phía trên, giờ gán trực tiếp qua bộ nhớ JS chung.
   ============================================================ */

const DELIMITER_LABELS = { ",": "dấu phẩy (,)", ";": "dấu chấm phẩy (;)", "\t": "tab", "|": "dấu gạch đứng (|)" };
function delimiterLabel(d) {
  return DELIMITER_LABELS[d] || d;
}

function activateCvTool(tool) {
  document.querySelectorAll("#convert-tabs .convert-tab").forEach((b) => b.classList.toggle("is-active", b.dataset.tool === tool));
  state.cv.tool = tool;
  // SCOPE theo #section-convert -- ".convert-options" dùng CHUNG với khối
  // Free Tools, không scope sẽ ẩn/hiện nhầm cả options của Free Tools.
  document.querySelectorAll("#section-convert .convert-options").forEach((el) => (el.hidden = el.id !== "convert-options-" + tool));
  resetCvResult();
}
document.querySelectorAll("#convert-tabs .convert-tab").forEach((btn) => {
  btn.addEventListener("click", () => activateCvTool(btn.dataset.tool));
});

// ====== Chọn kiểu nhập (File / Dán text) ======
wireInputToggle($("convert-input-toggle"), $("convert-dropzone"), $("convert-paste-input"), (mode) => {
  state.cv.inputMode = mode;
});

// ====== Dropzone chọn file (kéo-thả + bấm chọn) ======
wireDropzone($("convert-dropzone"), $("convert-file-input"), (file) => {
  state.cv.selectedFile = file;
  $("convert-file-name").textContent = `${file.name} · ${(file.size / 1024).toFixed(1)} KB`;
});

/* ====== Kết quả ====== */
function resetCvResult() {
  state.cv.lastResult = null;
  $("convert-result-empty").hidden = false;
  $("convert-result-table-wrap").hidden = true;
  $("convert-result-text").hidden = true;
  $("convert-download-btn").disabled = true;
  setStatus($("convert-status"), "", "");
  setError($("convert-error"), "");
}

function showCvResult(data) {
  state.cv.lastResult = data;
  $("convert-result-empty").hidden = true;
  $("convert-download-btn").disabled = false;

  if (state.cv.tool === "csv-to-json") {
    $("convert-result-table-wrap").hidden = true;
    $("convert-result-text").hidden = false;
    $("convert-result-text").textContent = data.result_text;
    setStatus($("convert-status"), `✅ ${data.record_count} record (delimiter: ${delimiterLabel(data.used_delimiter)})`, "is-ok");
    return;
  }

  $("convert-result-text").hidden = true;
  $("convert-result-table-wrap").hidden = false;
  renderPreviewTable($("convert-result-table"), data.preview_rows);
  if (state.cv.tool === "delimiter") {
    setStatus($("convert-status"), `✅ ${data.row_count} dòng · đã nhận diện delimiter gốc: ${delimiterLabel(data.used_from_delimiter)}`, "is-ok");
  } else {
    setStatus($("convert-status"), `✅ ${data.row_count} dòng · ${data.columns.length} cột`, "is-ok");
  }
}

// ====== Bấm Convert ======
$("convert-run-btn").addEventListener("click", async () => {
  setError($("convert-error"), "");
  const formData = new FormData();

  if (state.cv.inputMode === "file") {
    if (!state.cv.selectedFile) return setError($("convert-error"), "Chưa chọn file nào.");
    formData.append("file", state.cv.selectedFile);
  } else {
    const text = $("convert-paste-input").value;
    if (!text.trim()) return setError($("convert-error"), "Chưa dán nội dung nào.");
    formData.append("text", text);
  }

  let url;
  if (state.cv.tool === "delimiter") {
    url = "/api/convert/delimiter";
    formData.append("from_delimiter", $("opt-from-delim").value);
    formData.append("to_delimiter", $("opt-to-delim").value);
  } else if (state.cv.tool === "csv-to-json") {
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
  setStatus($("convert-status"), "");

  let response, data;
  try {
    response = await fetch(url, { method: "POST", body: formData });
    data = await response.json();
  } catch (err) {
    btn.disabled = false;
    btn.textContent = "Convert";
    setError($("convert-error"), "Không gọi được backend. Kiểm tra xem python3 app.py có đang chạy không.");
    return;
  }
  btn.disabled = false;
  btn.textContent = "Convert";

  if (!response.ok) {
    setError($("convert-error"), data.error || "Convert thất bại.");
    return;
  }
  showCvResult(data);
});

// ====== Tải xuống kết quả (xử lý ngay trên trình duyệt bằng Blob, không
// cần gọi thêm API nào -- result_text server đã trả đủ ở bước Convert) ======
$("convert-download-btn").addEventListener("click", () => {
  if (!state.cv.lastResult) return;
  const isJson = state.cv.tool === "csv-to-json";
  const blob = new Blob([state.cv.lastResult.result_text], {
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
// Hỗ trợ ?section=convert / ?section=free-tools -- index.html dùng để link
// trực tiếp vào đúng khối (thay cho link convert.html/tools.html cũ).
(function initSectionFromQuery() {
  const requested = new URLSearchParams(window.location.search).get("section");
  if (requested === "convert" || requested === "free-tools") state.section = requested;
})();

checkAuth();
checkBackendHealth();
renderFtToolHero(state.ft.tool);
renderFtToolSteps(state.ft.tool);
renderFtToolExplainer(state.ft.tool);
renderFtPipelineStrip();
switchSection(state.section);
