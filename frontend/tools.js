"use strict";

/* ============================================================
   Free Tools -- bản thiết kế lại theo ĐÚNG format trang tham khảo (CYD):
   mỗi tool có hero/before-after/cách hoạt động/giải thích RIÊNG (TOOL_INFO
   bên dưới, render vào #tool-hero/#tool-steps/#tool-explainer khi đổi tab),
   cộng tuỳ chọn RIÊNG từng tool (Ignore case/Ignore extra spaces cho xoá
   trùng, Collapse repeated spaces/Remove zero-width cho cắt khoảng trắng,
   fill_down cho điền ô trống, also_remove_empty_columns cho xoá dòng trống).

   KHÁC trang tham khảo ở đúng 1 chỗ (yêu cầu của người dùng): có thêm cơ chế
   "nối tiếp" (state.pipeline) -- sau khi 1 tool chạy xong, KHÔNG bắt tải
   file về rồi tải lên lại mới xử lý tiếp bằng tool khác được; kết quả được
   giữ trong bộ nhớ trình duyệt, xử lý tiếp tool nào cũng dùng luôn kết quả
   đó làm đầu vào. Panel "Xử lý tiếp" sau kết quả có ĐÚNG 3 danh mục
   (Cần cấu hình/Convert/Tự động) giống hệt dropdown "Product" ở header
   workspace.html -- 2 danh mục đó không shared qua module (dự án không có
   hệ thống module JS dùng chung, theo đúng quy ước đã có: mỗi trang tự
   chứa JS của mình, xem checkAuth()/checkBackendHealth() cũng lặp lại y hệt
   ở convert.js/workspace.js).
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
  activeContinueCategory: null,
  // "Nối tiếp" -- xem mô tả ở đầu file. originalText/originalLabel là kết
  // quả của LẦN CHẠY ĐẦU TIÊN (không phải file gốc trước khi qua tool nào --
  // với file Excel sẽ không có sẵn "text CSV" phía trình duyệt nếu chưa
  // chạy qua backend 1 lần, nên lấy mốc "gốc" là ngay sau bước đầu tiên).
  pipeline: { active: false, originalText: null, originalLabel: "", currentText: null, steps: [], forceNewUpload: false },
};

// ====== Cổng xác thực: giống convert.js/workspace.js -- bắt buộc đăng
// nhập, dùng chung session với trang chính. ======
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

/* ====== Nội dung RIÊNG từng tool (hero + before/after + cách hoạt động +
   giải thích 3 cột) -- khớp ĐÚNG format trang tham khảo, dịch/điều chỉnh
   cho đúng SỰ THẬT cách SPARK hoạt động (vd "riêng tư" không thể nói "xử lý
   trong trình duyệt" như trang tham khảo vì SPARK LUÔN gọi backend thật). ====== */
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

function renderToolHero(tool) {
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
function renderToolSteps(tool) {
  const info = TOOL_INFO[tool];
  $("tool-steps").innerHTML = info.steps
    .map((s, i) => `<div><p class="tool-step-num">0${i + 1}</p><p class="tool-step-text">${escapeHtml(s)}</p></div>`)
    .join("");
}
function renderToolExplainer(tool) {
  const info = TOOL_INFO[tool];
  $("tool-explainer").innerHTML = info.explainer
    .map((e) => `<div><p class="tool-explainer-title">${escapeHtml(e.t)}</p><p class="tool-explainer-body">${escapeHtml(e.b)}</p></div>`)
    .join("");
}

/* ====== Chọn tool (4 tab) -- activateTool() dùng chung cho cả bấm tab
   thật LẪN bấm 1 mục "Tự động" trong panel "Xử lý tiếp" bên dưới. ====== */
function activateTool(tool) {
  document.querySelectorAll(".convert-tab").forEach((b) => b.classList.toggle("is-active", b.dataset.tool === tool));
  state.tool = tool;
  document.querySelectorAll(".convert-options").forEach((el) => (el.hidden = el.id !== "convert-options-" + tool));
  renderToolHero(tool);
  renderToolSteps(tool);
  renderToolExplainer(tool);
  resetResult();
}
document.querySelectorAll(".convert-tab").forEach((btn) => {
  btn.addEventListener("click", () => activateTool(btn.dataset.tool));
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

/* ====== Thanh "nối tiếp" (pipeline) ====== */
function renderPipelineStrip() {
  const p = state.pipeline;
  const strip = $("pipeline-strip");
  const showUpload = !p.active || p.forceNewUpload;
  $("convert-input-toggle").hidden = !showUpload;
  dropzone.hidden = !showUpload || state.inputMode !== "file";
  $("convert-paste-input").hidden = !showUpload || state.inputMode !== "paste";

  if (!p.active) {
    strip.hidden = true;
    return;
  }
  strip.hidden = false;
  const stepsText = p.steps.length ? ` · đã qua: ${p.steps.map((s) => s.label).join(" → ")}` : " · chưa xử lý bước nào";
  $("pipeline-strip-text").innerHTML = `📄 Đang dùng: <strong>${escapeHtml(p.originalLabel)}</strong>${escapeHtml(stepsText)}`;
}
$("pipeline-new-file-btn").addEventListener("click", () => {
  state.pipeline.forceNewUpload = true;
  renderPipelineStrip();
});
$("pipeline-reset-btn").addEventListener("click", () => {
  state.pipeline.currentText = state.pipeline.originalText;
  state.pipeline.steps = [];
  state.pipeline.forceNewUpload = false;
  renderPipelineStrip();
  resetResult();
});

/* ====== Kết quả ====== */
function resetResult() {
  $("convert-result-empty").hidden = false;
  $("convert-result-table-wrap").hidden = true;
  $("convert-download-btn").disabled = true;
  $("continue-panel").hidden = true;
  state.activeContinueCategory = null;
  $("continue-list").innerHTML = "";
  document.querySelectorAll(".continue-pill").forEach((b) => b.classList.remove("is-active"));
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

function showResult(data, inputLabel) {
  $("convert-result-empty").hidden = true;
  $("convert-download-btn").disabled = false;
  $("convert-result-table-wrap").hidden = false;
  renderPreviewTable(data.preview_rows);
  setStatus(statusFromStats(data.stats), "is-ok");

  const p = state.pipeline;
  if (!p.active) {
    p.active = true;
    p.originalText = data.result_text;
    p.originalLabel = inputLabel;
    p.currentText = data.result_text;
    p.steps = [{ label: TOOL_TAB_LABEL[state.tool] }];
  } else {
    p.currentText = data.result_text;
    p.steps.push({ label: TOOL_TAB_LABEL[state.tool] });
  }
  p.forceNewUpload = false;
  renderPipelineStrip();
  renderContinuePanel();
}

/* ====== Panel "Xử lý tiếp" -- 3 danh mục y hệt dropdown Product ở header.
   "Cần cấu hình" KHÔNG bấm được (chưa có trang đích, xem workspace.html);
   "Tự động" chuyển tab NGAY TRONG trang này, dùng luôn state.pipeline;
   "Convert" chuyển SANG convert.html, chuyển dữ liệu qua sessionStorage
   (handoff) vì đó là trang KHÁC, không còn chung bộ nhớ JS nữa. ====== */
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
    const isReopening = state.activeContinueCategory === category;
    state.activeContinueCategory = isReopening ? null : category;
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
        activateTool(a.dataset.tool);
      });
    });
    list.querySelectorAll("a[data-convert-tool]").forEach((a) => {
      a.addEventListener("click", (e) => {
        e.preventDefault();
        // Chuyển SANG convert.html -- trang KHÁC nên JS state ở đây sẽ mất,
        // phải gửi kèm text qua sessionStorage (dùng 1 lần, convert.js tự
        // đọc + xoá đi ngay khi áp dụng xong, xem applyHandoffIfAny()).
        sessionStorage.setItem("spark_handoff_csv", state.pipeline.currentText);
        window.location.href = `convert.html?handoff=1&tool=${encodeURIComponent(a.dataset.convertTool)}`;
      });
    });
  });
});

// ====== Bấm Chạy ======
$("convert-run-btn").addEventListener("click", async () => {
  setError("");
  const formData = new FormData();
  const p = state.pipeline;
  const usePipeline = p.active && !p.forceNewUpload;
  let inputLabel = p.originalLabel;

  if (usePipeline) {
    formData.append("text", p.currentText);
  } else if (state.inputMode === "file") {
    if (!state.selectedFile) return setError("Chưa chọn file nào.");
    formData.append("file", state.selectedFile);
    inputLabel = state.selectedFile.name;
  } else {
    const text = $("convert-paste-input").value;
    if (!text.trim()) return setError("Chưa dán nội dung nào.");
    formData.append("text", text);
    inputLabel = "văn bản dán tay";
  }

  if (state.tool === "remove-duplicates") {
    formData.append("subset_columns", $("opt-subset-columns").value);
    formData.append("keep", $("opt-keep").value);
    formData.append("ignore_case", $("opt-ignore-case").checked ? "true" : "false");
    formData.append("ignore_whitespace", $("opt-ignore-whitespace").checked ? "true" : "false");
  } else if (state.tool === "trim-whitespace") {
    formData.append("collapse_repeated", $("opt-collapse-repeated").checked ? "true" : "false");
    formData.append("remove_zero_width", $("opt-remove-zero-width").checked ? "true" : "false");
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
  } else if (state.tool === "remove-empty-rows") {
    formData.append("also_remove_empty_columns", $("opt-remove-empty-columns").checked ? "true" : "false");
  }

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
  showResult(data, inputLabel);
});

// ====== Tải xuống kết quả hiện tại (dùng pipeline.currentText -- LUÔN là
// kết quả MỚI NHẤT, dù đã nối tiếp qua bao nhiêu tool) ======
$("convert-download-btn").addEventListener("click", () => {
  if (!state.pipeline.currentText) return;
  const blob = new Blob([state.pipeline.currentText], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = state.pipeline.steps.length > 1 ? "da-xu-ly.csv" : `${state.tool}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
});

// ====== Khởi động ======
checkAuth();
checkBackendHealth();
renderToolHero(state.tool);
renderToolSteps(state.tool);
renderToolExplainer(state.tool);
renderPipelineStrip();
