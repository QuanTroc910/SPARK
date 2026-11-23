"use strict";

/* ============================================================
   workspace.js -- logic cho trang workspace.html.

   Thân trang có 9 KHỐI cùng tồn tại trên 1 trang -- trang chủ, Guide, Bảo
   mật, Quyền riêng tư (công khai), 3 nhóm tool (#section-config cần cấu
   hình, #section-free-tools, #section-convert -- cùng 1 bộ máy, xem phần
   "BA NHÓM TOOL"), #section-class-noise (4 bước, logic ở workspace-flow.js)
   và #section-profile -- chuyển khối bằng switchSection(), KHÔNG điều
   hướng sang trang khác. Nhờ gộp vào 1 trang, cơ chế
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

const escapeAttr = (v) => escapeHtml(v); // giá trị đặt trong thuộc tính HTML (value="...")
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
// Bảng dữ liệu kiểu CYD: cột ĐẦU TIÊN là số thứ tự dòng (1-based, chữ mờ,
// có kẻ dọc ngăn -- xem .cyd-table trong workspace.css), các cột sau là dữ
// liệu thật. Dùng chung cho bảng xem trước, bảng kết quả Free Tools và
// bảng kết quả Convert.
// Số dòng DỮ LIỆU tối đa hiện ở các bảng xem trước (cả khung Đầu vào lẫn Kết quả). Phải KHỚP
// PREVIEW_DATA_ROWS trong app.py (khung Kết quả do backend cắt theo số đó, khung Đầu vào do trình
// duyệt cắt theo số này). Chỉ giới hạn HIỂN THỊ -- xử lý và file tải về luôn đủ toàn bộ dòng.
const PREVIEW_ROWS = 100;
// `opts` (tuỳ chọn): rowNumbers = số hiện ở cột "Dòng" thay cho 1,2,3... (vd số dòng GỐC trong file);
// rowClasses = class CSS cho từng dòng (vd tô dòng bị xoá); cellClasses = class CSS cho từng ô
// (mảng 2 chiều theo dòng x cột dữ liệu, vd tô ô đã sửa).
function renderPreviewTable(table, rows, opts) {
  if (!rows || !rows.length) {
    table.innerHTML = "";
    return;
  }
  const o = opts || {};
  const [header, ...body] = rows;
  table.innerHTML =
    "<thead><tr><th>Dòng</th>" + header.map((h) => `<th>${escapeHtml(h)}</th>`).join("") + "</tr></thead>" +
    "<tbody>" +
    body.map((row, i) => {
      const num = o.rowNumbers ? o.rowNumbers[i] : i + 1;
      const cls = o.rowClasses && o.rowClasses[i] ? ` class="${o.rowClasses[i]}"` : "";
      const cc = o.cellClasses && o.cellClasses[i];
      return `<tr${cls}><td>${num}</td>` + row.map((cell, k) => `<td${cc && cc[k] ? ` class="${cc[k]}"` : ""}>${escapeHtml(cell)}</td>`).join("") + "</tr>";
    }).join("") +
    "</tbody>";
}
// Chuỗi "N DÒNG × M CỘT" hiện ở góc phải thanh trên của bảng (CYD ghi
// "240 ROWS × 4 COLS").
function tableDims(rowCount, colCount) {
  return `${rowCount} dòng × ${colCount} cột`;
}
// Công tắc nhiều nửa nối liền (.ft-seg) thay cho <select> ở lựa chọn ngắn:
// bấm nút nào thì gán giá trị đó cho <select> gốc (đang ẩn) rồi phát sự
// kiện "change" để các listener cũ (vd ẩn/hiện ô "Giá trị điền vào") vẫn
// chạy y như khi người dùng chọn trong <select>.
function wireSegmented(segEl) {
  const select = $(segEl.dataset.segFor);
  const buttons = segEl.querySelectorAll("button");
  buttons.forEach((btn) => {
    btn.addEventListener("click", () => {
      buttons.forEach((b) => b.classList.toggle("is-active", b === btn));
      select.value = btn.dataset.value;
      select.dispatchEvent(new Event("change"));
    });
  });
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

// Danh sách khối trong <main>, đúng thứ tự xuất hiện. 4 khối đầu là trang
// CÔNG KHAI: chưa đăng nhập vẫn xem được. 5 khối sau cần đăng nhập (config =
// 4 tool cần cấu hình, class-noise = 4 bước ở workspace-flow.js, profile = hồ
// sơ, free-tools, convert).
const SECTIONS = ["home", "guide", "security", "privacy", "config", "class-noise", "profile", "free-tools", "convert"];
const PUBLIC_SECTIONS = new Set(["home", "guide", "security", "privacy"]);
const PIPE_UNDO_MAX = 5; // số bước gần nhất có thể Hoàn tác trong chuỗi nối tiếp (khớp Bước 5 cũ)
const LIVE_CHECK_DELAY_MS = 900; // ngừng gõ ngần này mili-giây thì tự kiểm tra biểu thức (báo lỗi sớm, khỏi đợi bấm Phát hiện)
const LIVE_CHECK_MAX_BYTES = 5 * 1024 * 1024; // đầu vào lớn hơn thì không tự kiểm tra khi gõ (mỗi lần kiểm tra phải gửi lại cả dữ liệu lên máy chủ)

const state = {
  section: "home", // 1 trong SECTIONS -- khối đang hiện (mặc định: trang chủ)
  // Bộ nhớ NỐI TIẾP dùng chung cho cả 3 nhóm tool (xem phần "BA NHÓM TOOL").
  // originalSource = ĐẦU VÀO THẬT lúc chuỗi bắt đầu ({file|text, kind}: file hoặc text người dùng đưa vào), "Bắt đầu lại từ gốc" quay về đây
  // (xem loadPipeOriginal). originalText/Kind = kết quả ĐẦU TIÊN của chuỗi, chỉ còn là DỰ PHÒNG khi không ghi nhớ được đầu vào thật.
  // currentText/Kind = kết quả mới nhất = đầu vào của tool kế tiếp
  // (kind "csv" hoặc "json" -- JSON chỉ nối tiếp được sang JSON → CSV).
  pipe: { active: false, originalLabel: "", originalSource: null, originalText: null, originalKind: "csv", currentText: null, currentKind: "csv", steps: [], forceNewUpload: false,
          // Nút "Hoàn tác": mỗi bước mới ghi lại TRẠNG THÁI TRƯỚC ĐÓ ({text, kind, steps}) vào đây, giữ tối đa PIPE_UNDO_MAX bước gần nhất.
          // Bước đầu tiên của chuỗi không có snapshot (trước nó là file gốc) nên hoàn tác bước đó = "về gốc" (loadPipeOriginal).
          undoStack: [] },
  // Trạng thái riêng từng nhóm: tool đang chọn, kiểu nhập, file đã chọn, bảng xem trước.
  // listView = danh sách của nút "Xem ..." sau lần chạy gần nhất: { kind: tên tool, data: dữ liệu backend trả, showing }
  // (kind "remove-duplicates" = các dòng trùng, "trim-whitespace" = các ô đã sửa; null = chưa có / đã bị xoá);
  // showing = khung 01 đang hiện danh sách đó thay cho đầu vào.
  ft: { tool: "remove-duplicates", inputMode: "file", selectedFile: null, rawPreviewActive: false, filePreview: null, listView: null,
        // Tool Sai định dạng: bảng kiểu dữ liệu từng cột. colTypes = [{name, guessed, guessedFmt, dtype, dateFormat}] (null = chưa có);
        // colState = idle|loading|ready|error; colSig = "chữ ký" đầu vào đã đọc cột (tránh đọc lại khi đầu vào không đổi);
        // colSeq/colPromise = chống chạy chồng; colCounts = {cột: số ô sai} của lần Chạy gần nhất (countsSig = chữ ký đầu vào lúc đó).
        colTypes: null, colState: "idle", colError: "", colSig: "", colSeq: 0, colPromise: null, colCounts: null, countsSig: "",
        // Tool Ô trống: bảng các cột CÓ ô trống. blankCols = [{name, blanks, guessed, dtype, action, fixedValue}] (null = chưa có);
        // blankInfo = {empty_row_count, empty_columns, blank_actions} từ backend; blankState/blankSig/blankSeq/blankPromise như colXxx ở trên.
        blankCols: null, blankInfo: null, blankState: "idle", blankError: "", blankSig: "", blankSeq: 0, blankPromise: null,
        // Bảng "Điền tay từng ô": blankEditing = tên cột đang mở bảng (null = đóng); blankRowsCache = {tên cột: {state, data}}
        // các dòng có ô trống backend trả về (đổi đầu vào thì làm mới cả object này); blankErrors = {tên cột: lỗi lần tải gần nhất}.
        blankEditing: null, blankRowsCache: {}, blankErrors: {} },
  cv: { tool: "delimiter", inputMode: "file", selectedFile: null, rawPreviewActive: false, filePreview: null, lastResult: null },
  // cf thêm: columns/guessed đọc từ /api/noise-tools/inspect, detect = kết quả nhịp "Phát hiện".
  cf: { tool: "out-of-range", inputMode: "file", selectedFile: null, rawPreviewActive: false, filePreview: null, columns: [], guessed: {}, detect: null,
        // Rule liên cột: kiểu rule đang chọn + nội dung ô Biểu thức (giữ lại khi dựng lại form do đổi file / đọc lại cột, đỡ phải gõ lại)
        ruleType: "expression", expr: { text: "", dateFormat: "", tolerance: "0.01" },
        // "Chip giá trị" của ô Biểu thức: columnValues = {tên cột: {values:[{value,count}], more}} backend trả cho cột Nhóm (chữ ít giá trị khác nhau);
        // valueCol = cột vừa bấm chip, đang hiện giá trị của nó ("" = ẩn).
        columnValues: {}, valueCol: "",
        // Kiểm tra biểu thức khi đang gõ: liveTimer = hẹn giờ ngừng-gõ, liveSeq = số thứ tự lần kiểm tra mới nhất (kết quả về muộn của lần cũ bị bỏ).
        liveTimer: null, liveSeq: 0,
        // colSig = "chữ ký" đầu vào mà cột hiện có được đọc từ đó; pendingSig = đầu vào đang được đọc dở; colSeq = chống chạy chồng.
        colSig: "", pendingSig: "", colSeq: 0,
        // Tool kiểm NHIỀU cột (Không nhất quán, Ngoài khoảng -- xem CF_MULTI): forms[tên tool] = các form đang khai
        // [{uid, column, dtype, ...ô riêng của tool}], formUid = bộ đếm uid dùng chung.
        forms: {}, formUid: 0 },
};

// ====== Đăng nhập / tạo tài khoản (bước 4) -- trang này TỰ lo, không đá về
// index.html nữa. Cùng session cookie với index.html (cùng origin) nên đăng
// nhập ở đây thì sang index.html cũng đã đăng nhập và ngược lại. ======
const authState = {
  mode: "login",      // "login" | "register" -- chế độ của form
  user: null,         // {id, username, created_at} khi đã đăng nhập
  checked: false,     // đã có kết quả GET /api/auth/me chưa (trước đó body.ws-auth-pending che hết)
  forceAuth: false,   // true khi khách TỰ bấm "Đăng nhập"/"Bắt đầu" dù đang ở trang công khai
  afterLogin: null,   // khối cần mở ngay sau khi đăng nhập xong (vd "free-tools" cho nút "Bắt đầu")
};

// Quyết định màn hình nào đang hiện, gọi lại mỗi khi đổi khối hoặc đổi trạng
// thái đăng nhập. Quy tắc (bước 5, giống CYD): trang công khai (PUBLIC_SECTIONS)
// ai cũng xem được; khối cần đăng nhập mà chưa đăng nhập thì form đăng nhập
// (#ws-auth) hiện đè lên; khách đang xem trang công khai thấy 2 nút "Đăng
// nhập"/"Bắt đầu" ở header thay cho khối tài khoản (body.ws-guest).
function applyAuthView() {
  if (!authState.checked) return; // chưa biết đã đăng nhập hay chưa -> giữ nguyên màn chờ
  const loggedIn = !!authState.user;
  const needLogin = !loggedIn && (authState.forceAuth || !PUBLIC_SECTIONS.has(state.section));
  document.body.classList.remove("ws-auth-pending");
  document.body.classList.toggle("ws-auth-mode", needLogin);
  document.body.classList.toggle("ws-guest", !loggedIn);
  $("account-area").hidden = !loggedIn;
  $("ws-guest-area").hidden = loggedIn;
}
// Khách tự mở form (nút "Đăng nhập"/"Bắt đầu" ở header, link ở chân trang).
function openAuth(mode, afterLogin) {
  setAuthMode(mode);
  authState.forceAuth = true;
  authState.afterLogin = afterLogin || null;
  applyAuthView();
  window.scrollTo(0, 0);
}
function onLoggedIn(user) {
  authState.user = user;
  authState.checked = true;
  authState.forceAuth = false;
  $("account-username-text").textContent = `👤 ${user.username}`;
  const next = authState.afterLogin;
  authState.afterLogin = null;
  if (next) switchSection(next); // switchSection() tự gọi applyAuthView()
  else applyAuthView();
}
function onLoggedOut() {
  authState.user = null;
  authState.checked = true;
  authState.forceAuth = false;
  authState.afterLogin = null;
  applyAuthView();
}

// Phiên đăng nhập hết hiệu lực giữa chừng (vd server vừa khởi động lại): mọi API khác /api/auth/*
// trả 401. Trước đây chỉ hiện chữ "Cần đăng nhập trước" dưới nút, form đăng nhập KHÔNG hiện nên người
// dùng phải tải lại trang mới đăng nhập được (thấy như "tải file lần 2 mới được"). Giờ bọc fetch dùng
// chung cho cả workspace.js lẫn workspace-flow.js: gặp 401 thì đưa về form đăng nhập kèm lời giải thích,
// đăng nhập xong quay lại đúng khối đang làm (file đã chọn vẫn còn trong trang, không phải chọn lại).
function handleSessionExpired() {
  if (!authState.user) return; // đã ở trạng thái chưa đăng nhập: form đăng nhập đã có sẵn
  const back = state.section;
  onLoggedOut();
  setAuthMode("login"); // setAuthMode xoá lời báo lỗi cũ nên đặt lời báo SAU nó
  authState.afterLogin = back;
  setError($("ws-auth-error"), "Phiên đăng nhập đã hết hạn (có thể do server vừa khởi động lại). Hãy đăng nhập lại.");
}
const nativeFetch = window.fetch.bind(window);
window.fetch = async function (input, init) {
  const res = await nativeFetch(input, init);
  if (res.status === 401) {
    const url = typeof input === "string" ? input : (input && input.url) || "";
    if (/^\/api\//.test(url) && !url.startsWith("/api/auth/")) handleSessionExpired();
  }
  return res;
};
// 1 form dùng cho cả 2 chế độ -- chỉ đổi chữ (tiêu đề, nút, dòng chuyển chế
// độ, gợi ý độ dài) để không phải nhân đôi HTML.
function setAuthMode(mode) {
  authState.mode = mode;
  const isLogin = mode === "login";
  $("ws-auth-title").textContent = isLogin ? "Đăng nhập" : "Tạo tài khoản";
  // Chế độ đăng ký không có dòng mô tả (ẩn hẳn, không để lại khoảng trống).
  $("ws-auth-desc").textContent = isLogin ? "Tiếp tục việc đang dở." : "";
  $("ws-auth-desc").hidden = !isLogin;
  $("ws-auth-submit").textContent = isLogin ? "Đăng nhập" : "Tạo tài khoản";
  $("ws-auth-switch-text").textContent = isLogin ? "Chưa có tài khoản?" : "Đã có tài khoản?";
  $("ws-auth-toggle").textContent = isLogin ? "Tạo tài khoản" : "Đăng nhập";
  $("ws-auth-hint").hidden = isLogin;
  $("ws-auth-password").autocomplete = isLogin ? "current-password" : "new-password";
  setError($("ws-auth-error"), "");
}
$("ws-auth-toggle").addEventListener("click", () => setAuthMode(authState.mode === "login" ? "register" : "login"));
$("ws-auth-show").addEventListener("click", () => {
  const input = $("ws-auth-password");
  const show = input.type === "password";
  input.type = show ? "text" : "password";
  $("ws-auth-show").textContent = show ? "Ẩn" : "Hiện";
});
$("ws-auth-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  setError($("ws-auth-error"), "");
  const username = $("ws-auth-username").value.trim();
  const password = $("ws-auth-password").value;
  if (!username || !password) return setError($("ws-auth-error"), "Nhập đủ tên đăng nhập và mật khẩu.");
  const btn = $("ws-auth-submit");
  btn.disabled = true;
  let response, data;
  try {
    response = await fetch(authState.mode === "login" ? "/api/auth/login" : "/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    data = await response.json();
  } catch (err) {
    btn.disabled = false;
    return setError($("ws-auth-error"), "Không gọi được backend. Kiểm tra xem python3 app.py có đang chạy không.");
  }
  btn.disabled = false;
  if (!response.ok) return setError($("ws-auth-error"), data.error || "Không thành công.");
  $("ws-auth-password").value = "";
  onLoggedIn(data.user);
});

async function checkAuth() {
  let data = { user: null };
  try {
    const res = await fetch("/api/auth/me");
    data = await res.json();
  } catch (err) {
    // Không gọi được backend -- checkBackendHealth() bên dưới tự báo rõ.
  }
  if (!data.user) {
    onLoggedOut(); // chưa đăng nhập: trang công khai vẫn hiện, khối cần đăng nhập thì ra form
    return;
  }
  onLoggedIn(data.user);
}
$("logout-btn").addEventListener("click", async () => {
  try {
    await fetch("/api/auth/logout", { method: "POST" });
  } catch (err) {
    // vẫn hiện form đăng nhập dù gọi API lỗi -- không giữ người dùng kẹt lại.
  }
  // Đăng xuất xong TẢI LẠI trang về trang chủ ở trạng thái khách (giống CYD):
  // tải lại để xoá sạch mọi trạng thái trong bộ nhớ JS của luồng 5 bước
  // (file_id, cấu hình, kết quả của người vừa đăng xuất) -- người đăng nhập
  // kế tiếp trên cùng trình duyệt bắt đầu từ Bước 1 sạch, không đụng file cũ.
  window.location.assign("workspace.html");
});
$("open-profile-btn").addEventListener("click", () => switchSection("profile"));
// Nút cho KHÁCH ở header + link ở chân trang: mở form ở đúng chế độ. "Bắt
// đầu" = tạo tài khoản rồi vào thẳng Free Tools sau khi xong.
$("ws-guest-login-btn").addEventListener("click", () => openAuth("login"));
$("ws-guest-start-btn").addEventListener("click", () => openAuth("register", "free-tools"));
$("footer-login-link").addEventListener("click", (e) => { e.preventDefault(); openAuth("login"); });
$("footer-register-link").addEventListener("click", (e) => { e.preventDefault(); openAuth("register", "free-tools"); });

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
  if (!SECTIONS.includes(section)) section = "home";
  state.section = section;
  SECTIONS.forEach((name) => { $("section-" + name).hidden = name !== section; });
  // Viền màu nhấn (.is-current) cho pill của "vùng" đang mở: Product chứa 3
  // nhóm tool (Cần cấu hình / Convert / Free Tools), Guide và Class Noise là
  // pill riêng; Home sáng khi ở trang chủ. Bảo mật/Riêng tư/Hồ sơ: không pill nào sáng.
  $("ws-nav-home").classList.toggle("is-current", section === "home");
  $("ws-product-btn").classList.toggle("is-current", ["free-tools", "convert", "config"].includes(section));
  $("ws-nav-guide").classList.toggle("is-current", section === "guide");
  $("ws-nav-class").classList.toggle("is-current", section === "class-noise");
  if (section === "profile") renderProfile();
  if (section === "config") refreshCfColumns(); // vào Cần cấu hình bằng cách nào cũng phải có đúng cột của đầu vào hiện tại
  // Đổi khối là thoát trạng thái "khách tự bấm Đăng nhập" (vd bấm "Về trang
  // chủ" trong form); khối cần đăng nhập thì applyAuthView() tự hiện form lại.
  authState.forceAuth = false;
  applyAuthView();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

// Mọi link có data-section (logo, pill Guide, chân trang, đường dẫn, nút
// trong trang chủ, link trong form đăng nhập) -> chuyển khối tại chỗ.
document.querySelectorAll("a[data-section]").forEach((a) => {
  a.addEventListener("click", (e) => {
    e.preventDefault();
    switchSection(a.dataset.section);
    setProductMenuOpen(false);
  });
});

// ====== Hồ sơ tài khoản (#section-profile, bước 6 -- chuyển từ panel-profile
// của index.html sang): hiện tên/ngày tạo từ authState.user, đổi mật khẩu
// qua POST /api/auth/change-password (cần mật khẩu hiện tại). ======
function renderProfile() {
  const user = authState.user;
  $("profile-username").textContent = user ? user.username : "—";
  $("profile-created-at").textContent = user ? new Date(user.created_at).toLocaleString("vi-VN") : "—";
  $("change-password-form").reset();
  setError($("change-password-error"), "");
  $("change-password-success").hidden = true;
}
$("change-password-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  setError($("change-password-error"), "");
  $("change-password-success").hidden = true;
  const old_password = $("old-password").value;
  const new_password = $("new-password").value;
  if (!old_password || !new_password) return setError($("change-password-error"), "Nhập đủ mật khẩu hiện tại và mật khẩu mới.");
  const btn = $("change-password-btn");
  btn.disabled = true;
  let response, data;
  try {
    response = await fetch("/api/auth/change-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ old_password, new_password }),
    });
    data = await response.json();
  } catch (err) {
    btn.disabled = false;
    return setError($("change-password-error"), "Không gọi được backend.");
  }
  btn.disabled = false;
  if (!response.ok) return setError($("change-password-error"), data.error || "Đổi mật khẩu thất bại.");
  $("change-password-form").reset();
  $("change-password-success").hidden = false;
});
$("profile-logout-btn").addEventListener("click", () => $("logout-btn").click());

// Mục lục dính "TRÊN TRANG NÀY" của 3 trang văn bản: bấm thì cuộn mượt tới
// mục, và tự tô đậm mục đang đọc khi người dùng cuộn (IntersectionObserver
// -- API có sẵn của trình duyệt, báo khi 1 phần tử lọt vào vùng nhìn thấy).
function wireTextPageToc() {
  document.querySelectorAll(".tx-toc").forEach((toc) => {
    const links = Array.from(toc.querySelectorAll('a[href^="#"]'));
    const targetOf = (a) => $(a.getAttribute("href").slice(1));
    const setActive = (id) => links.forEach((a) => a.classList.toggle("is-active", a.getAttribute("href") === "#" + id));
    links.forEach((a) => {
      a.addEventListener("click", (e) => {
        e.preventDefault();
        const target = targetOf(a);
        if (!target) return;
        target.scrollIntoView({ behavior: "smooth", block: "start" });
        setActive(target.id);
      });
    });
    const observer = new IntersectionObserver((entries) => {
      // Trong các mục đang lọt vào vùng quan sát, lấy mục ở gần đỉnh nhất.
      const visible = entries
        .filter((en) => en.isIntersecting)
        .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
      if (visible.length) setActive(visible[0].target.id);
    }, { rootMargin: "-90px 0px -55% 0px", threshold: 0 });
    links.map(targetOf).filter(Boolean).forEach((t) => observer.observe(t));
    if (links[0]) links[0].classList.add("is-active");
  });
}
wireTextPageToc();

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

// Chân trang: nút "Lên đầu trang" + link "Đăng xuất" (dùng chung hành vi với
// nút Đăng xuất ở header).
$("ws-backtop").addEventListener("click", () => window.scrollTo({ top: 0, behavior: "smooth" }));
$("footer-logout-link").addEventListener("click", (e) => {
  e.preventDefault();
  $("logout-btn").click();
});

/* ============================================================
   BA NHÓM TOOL -- Free Tools (ft) / Convert (cv) / Cần cấu hình (cf) --
   chạy trên CÙNG 1 BỘ MÁY: mỗi nhóm có bộ id riêng (TOOLSEC bên dưới)
   nhưng dùng chung các hàm: khu vực nhập liệu (file / dán text / bảng xem
   trước), dải "đang nối tiếp", bảng kết quả, panel "Xử lý tiếp".

   NỐI TIẾP (state.pipe): 1 bộ nhớ CHUNG cho cả 3 nhóm. Xong tool nào thì
   kết quả (CSV text, hoặc JSON text với CSV → JSON) trở thành
   pipe.currentText; panel "Xử lý tiếp" cho chọn BẤT KỲ tool nào ở cả 3
   nhóm, tool đích vào "chế độ nối tiếp": khung 01 hiện đầu vào = kết quả
   bước trước, bấm chạy là gửi đúng text đó lên backend. Dải đen phía trên
   ghi lại chuỗi bước; "Tải file khác" thoát tạm, "Bắt đầu lại từ gốc" quay
   về kết quả đầu tiên của chuỗi.
   ============================================================ */

/* ----- Hình minh hoạ TRƯỚC/SAU kiểu CYD (dùng chung cho mọi tool) ----- */
function mockRow(cellClasses, opts) {
  const o = opts || {};
  const classes = [cellClasses[0] || "", cellClasses[1] || "", cellClasses[2] || ""];
  const cells = classes.map((c) => `<span class="tool-mock-cell${c ? " " + c : ""}"></span>`).join("");
  const num = o.tag ? `<span class="tool-mock-tag">${o.tag}</span>` : `<span class="tool-mock-num">${o.n}</span>`;
  return `<div class="tool-mock-row${o.removed ? " is-removed" : ""}">${num}${cells}</div>`;
}
function mockBox(label, rows) {
  const html = rows.map((r, i) => mockRow(r[0], Object.assign({ n: i + 1 }, r[1] || {}))).join("");
  return `<div class="tool-mock-box"><span class="tool-mock-label">${label}</span>${html}</div>`;
}
function mockPair(beforeRows, afterRows, delta) {
  return (
    `<div class="tool-mock-frame"><span class="tool-mock-corner is-tr"></span><span class="tool-mock-corner is-bl"></span>` +
    `<div class="tool-mock">${mockBox("Trước", beforeRows)}` +
    `<span class="tool-mock-delta">→<span class="tool-mock-delta-label">${delta}</span></span>` +
    `${mockBox("Sau", afterRows)}</div></div>`
  );
}
function mockTextBox(label, lines) {
  const html = lines
    .map((l) => {
      const [text, hit] = Array.isArray(l) ? l : [l, false];
      return `<span class="tool-mock-line${hit ? " is-hit" : ""}">${escapeHtml(text)}</span>`;
    })
    .join("");
  return `<div class="tool-mock-box tool-mock-text"><span class="tool-mock-label">${label}</span>${html}</div>`;
}
function mockTextPair(beforeLabel, beforeLines, afterLabel, afterLines, delta) {
  return (
    `<div class="tool-mock-frame"><span class="tool-mock-corner is-tr"></span><span class="tool-mock-corner is-bl"></span>` +
    `<div class="tool-mock">${mockTextBox(beforeLabel, beforeLines)}` +
    `<span class="tool-mock-delta">→<span class="tool-mock-delta-label">${delta}</span></span>` +
    `${mockTextBox(afterLabel, afterLines)}</div></div>`
  );
}

/* ----- Nhãn dùng chung ----- */
const TOOL_TAB_LABEL = {
  "remove-duplicates": "Xoá dòng trùng",
  "trim-whitespace": "Cắt khoảng trắng",
  "blanks": "Ô trống",
  "format-noise": "Sai định dạng",
};
const CV_TAB_LABEL = { delimiter: "Đổi dấu phân cách CSV", "csv-to-json": "CSV → JSON", "json-to-csv": "JSON → CSV" };
const CF_TAB_LABEL = {
  "out-of-range": "Ngoài khoảng",
  outlier: "Giá trị bất thường",
  "inconsistent-category": "Không nhất quán",
  "cross-rule": "Quy tắc liên cột",
};
const DTYPE_LABELS = {
  integer: "Số nguyên", float: "Số thực", text: "Văn bản", email: "Email",
  phone: "Số điện thoại", date: "Ngày tháng", category: "Nhóm",
};
// Khớp HandlingAction ở attribute_handling.py -- backend trả danh sách hợp lệ
// theo cặp kiểu cột × loại lỗi, FE chỉ dịch sang chữ.
const ACTION_LABELS = {
  remove_row: "Xoá cả dòng",
  impute_mean: "Điền trung bình cột",
  impute_median: "Điền trung vị cột",
  impute_knn: "Điền theo KNN (5 dòng giống nhất)",
  impute_mode: "Điền giá trị phổ biến nhất",
  fixed_value: "Điền giá trị cố định",
  cap_to_range: "Kéo về biên gần nhất",
  auto_normalize_category: "Tự chuẩn hoá về giá trị chuẩn",
  auto_clean_whitespace: "Tự cắt khoảng trắng",
  keep: "Giữ nguyên (chỉ xem)",
  fix_to_majority: "Sửa về giá trị phổ biến nhất",
  remove_suspect_rows: "Chỉ xoá dòng nghi sai",
};
const DELIMITER_LABELS = { ",": "dấu phẩy (,)", ";": "dấu chấm phẩy (;)", "\t": "tab", "|": "dấu gạch đứng (|)" };
function delimiterLabel(d) {
  return DELIMITER_LABELS[d] || d;
}

/* ----- Nội dung trang (tiêu đề, mô tả, hình, 3 bước, 3 cột) từng tool ----- */
const TOOL_INFO = {
  "remove-duplicates": {
    headline: "XOÁ DÒNG TRÙNG<br>TRONG FILE CSV",
    desc: "Xoá các dòng lặp lại, giữ bản đầu hoặc bản cuối. So khớp mọi cột, hoặc chỉ vài cột bạn chọn.",
    mock: mockPair([[[]], [[]], [["is-hit", "is-hit", "is-hit"], { tag: "TRÙNG" }], [[]]], [[[]], [[]], [[]]], "-1 dòng"),
    steps: ["Thả file CSV / Excel hoặc dán text.", "Chọn cột để so (để trống = so mọi cột).", "Tải file đã làm sạch."],
    explainer: [
      { t: "Thế nào là trùng", b: "Mọi cột khớp hệt một dòng trước đó. Chọn cột cụ thể để chỉ so các cột đó." },
      { t: "Trùng gần giống", b: "Bật \"Bỏ qua hoa/thường\" và \"Bỏ qua khoảng trắng thừa\" để bắt cả \"an@x.com\" và \"AN@X.com \"." },
    ],
  },
  "trim-whitespace": {
    headline: "CẮT KHOẢNG TRẮNG THỪA<br>TRONG FILE CSV",
    desc: "Cắt khoảng trắng đầu / cuối và ký tự vô hình, thứ khiến hai giá trị giống nhau bị máy coi là khác.",
    mock: mockPair([[["is-hit"]], [["", "is-hit"]], [[]], [["", "", "is-hit"]]], [[["is-fixed"]], [["", "is-fixed"]], [[]], [["", "", "is-fixed"]]], "3 ô"),
    steps: ["Thả file CSV / Excel hoặc dán text.", "Chọn có gộp khoảng trắng lặp lại hay không.", "Tải file đã làm sạch."],
    explainer: [
      { t: "Những gì bị cắt", b: "Khoảng trắng đầu / cuối luôn bị cắt. Tuỳ chọn thêm: gộp khoảng trắng lặp, xoá ký tự vô hình." },
      { t: "Vì sao quan trọng", b: "\"Hà Nội \" khác \"Hà Nội\" với máy, nên so khớp và kiểm tra trùng sẽ sai." },
    ],
  },
  "blanks": {
    headline: "XỬ LÝ Ô TRỐNG<br>TRONG FILE CSV",
    desc: "Ô trống, \"NA\", \"null\", \"-\", \"?\" đều là thiếu. Xoá dòng / cột trống hoặc điền ô trống theo từng cột.",
    mock: mockPair([[[]], [["", "is-hit"]], [[], { removed: true, tag: "TRỐNG" }], [[]]], [[[]], [["", "is-fixed"]], [[]]], "Điền · -1 dòng"),
    steps: ["Thả file CSV / Excel hoặc dán text.", "Mỗi cột có ô trống chọn một cách xử lý.", "Bấm Chạy rồi tải file."],
    explainer: [
      { t: "Thế nào là ô trống", b: "Ô trống, chỉ có khoảng trắng, hoặc ghi \"NA\", \"null\", \"none\", \"?\", \"-\"." },
      { t: "Cách điền theo kiểu cột", b: "Cột số điền được trung bình, trung vị, KNN. Cột nhóm điền giá trị phổ biến nhất." },
    ],
  },
  "format-noise": {
    headline: "BẮT Ô SAI ĐỊNH DẠNG<br>TRONG FILE CSV",
    desc: "Email thiếu @, SĐT lẫn chữ, ngày sai khuôn. Denoise đoán kiểu từng cột rồi gắn cờ ô không khớp.",
    mock: mockPair([[[]], [["", "is-hit"]], [[]], [["", "is-hit"]]], [[[]], [["", "is-fixed"]], [[]], [["", "is-fixed"]]], "2 ô"),
    steps: ["Thả file CSV / Excel hoặc dán text.", "Xem kiểu Denoise đoán cho từng cột, sửa nếu sai.", "Chọn cách xử lý ô sai rồi bấm Chạy."],
    explainer: [
      { t: "Kiểu nào kiểm tra gì", b: "Email cần dạng ten@mien, SĐT chỉ gồm chữ số và + - khoảng trắng, ngày đúng khuôn, số phải ép được thành số." },
      { t: "Kiểu cột được đoán thế nào", b: "Từ giá trị thật của cột chứ không phải tên cột. Đoán sai thì sửa ở bảng dưới dữ liệu." },
    ],
  },
};

const CV_INFO = {
  delimiter: {
    headline: "ĐỔI DELIMITER<br>CỦA FILE CSV",
    desc: "Đổi dấu phân cách của CSV (phẩy, chấm phẩy, tab, gạch đứng) mà không làm hỏng giá trị có ngoặc kép.",
    mock: mockTextPair("export_eu.csv", ["ma;ten;gia", ["A01;But bi;12,50", true], "A02;Kep giay;3,00"], "export.csv", ["ma,ten,gia", ['A01,But bi,"12,50"', true], 'A02,Kep giay,"3,00"'], "; → ,"),
    dropTitle: "Thả file CSV vào đây", accept: ".csv,.txt",
    steps: ["Thêm file, dấu phân cách hiện tại tự nhận diện.", "Chọn dấu phân cách mới.", "Tải file đã đổi."],
    explainer: [
      { t: "Vì sao cần đổi", b: "Nhiều nơi dùng dấu phẩy làm dấu thập phân nên xuất CSV bằng chấm phẩy." },
      { t: "Ngoặc kép tự xử lý", b: "Giá trị chứa dấu phân cách mới, ngoặc kép hoặc xuống dòng được tự bọc trong ngoặc kép." },
    ],
  },
  "csv-to-json": {
    headline: "CHUYỂN CSV<br>SANG JSON",
    desc: "Biến CSV thành JSON, khoá theo tên cột, tuỳ chọn tự nhận số và true / false.",
    mock: mockTextPair("products.csv", ["sku,name,price", ["A-100,But bi,3.2", true], "A-101,Kep giay,0.5"], "products.json", ["[", "  {", ['    "sku": "A-100",', true], ['    "name": "But bi",', true], ['    "price": 3.2', true], "  },", "  …", "]"], "→ JSON"),
    dropTitle: "Thả file CSV vào đây", accept: ".csv,.txt",
    steps: ["Thêm file CSV.", "Chọn Objects hay Arrays, có ép kiểu hay không.", "Sao chép JSON hoặc tải về."],
    explainer: [
      { t: "Khoá lấy từ dòng tiêu đề", b: "Tên cột trống thành \"column_1\", tên trùng được thêm hậu tố như \"name_2\"." },
      { t: "Ép kiểu", b: "Số và true / false thành kiểu JSON thật. Giá trị bắt đầu bằng số 0 (SĐT, mã bưu điện) giữ dạng chuỗi." },
    ],
  },
  "json-to-csv": {
    headline: "CHUYỂN JSON<br>SANG CSV",
    desc: "Làm phẳng mảng JSON hoặc JSON Lines thành CSV mở được bằng bảng tính.",
    mock: mockTextPair("users.json", ["[", "  {", '    "id": 1,', ['    "address": {', true], ['      "city": "Ha Noi"', true], "    }", "  }", "]"], "users.csv", [["id,address.city", true], "1,Ha Noi"], "→ CSV"),
    dropTitle: "Thả file JSON vào đây", accept: ".json,.jsonl,.txt",
    steps: ["Dán JSON hoặc thả file .json / .jsonl.", "Xem lại cột, trường lồng nhau thành \"address.city\".", "Tải CSV về."],
    explainer: [
      { t: "Nhận những gì", b: "Mảng object, object đơn hoặc JSON Lines (mỗi dòng một object). Khoá thiếu thành ô trống." },
      { t: "Dữ liệu lồng nhau", b: "Object lồng nhau thành cột \"address.city\". Mảng bên trong được ghi nguyên dạng JSON trong một ô." },
    ],
  },
};

const CF_INFO = {
  "out-of-range": {
    headline: "BẮT GIÁ TRỊ<br>NGOÀI KHOẢNG",
    desc: "Tuổi 210, lương âm, điểm 11/10. Bạn khai min và max cho cột số, Denoise gắn cờ giá trị nằm ngoài.",
    mock: mockPair([[[]], [["is-hit"]], [[]], [[]], [["is-hit"]]], [[[]], [["is-fixed"]], [[]], [[]], [["is-fixed"]]], "Kéo về biên"),
    steps: ["Chọn file và cột số cần kiểm. Thêm cột để kiểm nhiều cột một lượt.", "Gõ giá trị nhỏ nhất và lớn nhất hợp lệ, bấm Phát hiện.", "Chọn cách xử lý từng cột rồi bấm Áp dụng."],
    explainer: [
      { t: "Khoảng do bạn khai", b: "Mỗi file một khác (tuổi nhân viên khác tuổi bệnh nhân), nên Denoise không tự đoán khoảng." },
      { t: "Kéo về biên", b: "Nhỏ hơn min thành min, lớn hơn max thành max. Giữ được dòng, chỉ sửa ô lỗi." },
    ],
  },
  outlier: {
    headline: "BẮT GIÁ TRỊ<br>BẤT THƯỜNG",
    desc: "Không cần biết trước khoảng hợp lý. Denoise tính biên từ chính dữ liệu bằng IQR hoặc Z-score.",
    mock: mockPair([[[]], [[]], [["", "", "is-hit"]], [[]], [[]]], [[[]], [[]], [["", "", "is-fixed"]], [[]], [[]]], "1 ô"),
    steps: ["Chọn file và cột số cần kiểm. Thêm cột để kiểm nhiều cột một lượt.", "Mỗi cột chọn IQR và / hoặc Z-score, bấm Phát hiện.", "Chọn cách xử lý từng cột rồi bấm Áp dụng."],
    explainer: [
      { t: "IQR và Z-score", b: "IQR dựa trên tứ phân vị, bền với dữ liệu lệch. Z-score đo số độ lệch chuẩn, hợp dữ liệu phân phối chuông." },
      { t: "Bất thường không chắc là sai", b: "Một đơn hàng rất lớn có thể là thật. Xem ô bị gắn cờ trước, và có lựa chọn Giữ nguyên." },
    ],
  },
  "inconsistent-category": {
    headline: "CHUẨN HOÁ GIÁ TRỊ<br>KHÔNG NHẤT QUÁN",
    desc: "\"Nam\", \"nam\", \"NAM\" là ba giá trị khác nhau với máy. Bạn khai giá trị chuẩn, Denoise đưa các biến thể về giá trị đó.",
    mock: mockPair([[["is-hit"]], [[]], [["is-hit"]], [[]]], [[["is-fixed"]], [[]], [["is-fixed"]], [[]]], "Chuẩn hoá"),
    steps: ["Chọn file và cột nhóm cần kiểm. Thêm cột để kiểm nhiều cột một lượt.", "Gõ danh sách giá trị chuẩn, cách nhau bởi dấu phẩy, bấm Phát hiện.", "Chọn cách xử lý từng cột rồi bấm Áp dụng."],
    explainer: [
      { t: "Thế nào là gần giống", b: "Ngưỡng 1 chỉ bắt biến thể khác hoa/thường. Hạ xuống khoảng 0.85 để bắt thêm lỗi gõ." },
      { t: "Không khớp giá trị chuẩn nào", b: "Vẫn bị gắn cờ nhưng không tự sửa vì không biết đưa về đâu." },
    ],
  },
  "cross-rule": {
    headline: "BẮT MÂU THUẪN<br>GIỮA CÁC CỘT",
    desc: "Ngày nghỉ trước ngày vào, tổng tiền sai, một mã gắn với hai tên. Bạn viết điều kiện, Denoise kiểm tra từng dòng.",
    mock: mockPair([[[]], [["is-hit", "", "is-hit"]], [[]], [[]]], [[[]], [[]], [[]]], "-1 dòng"),
    steps: ["Chọn file và kiểu quy tắc: biểu thức hoặc phụ thuộc hàm.", "Viết biểu thức bằng cách bấm tên cột và các nút, rồi bấm Phát hiện.", "Xoá dòng vi phạm hoặc giữ nguyên để rà tay."],
    explainer: [
      { t: "Hai kiểu quy tắc", b: "Biểu thức: điều kiện mọi dòng phải thoả. Phụ thuộc hàm: mỗi giá trị cột A chỉ đi với một giá trị của cột phụ thuộc." },
      { t: "Nếu … thì …", b: "Viết A => B (nút THÌ =>): dòng thoả A thì B phải đúng. Vd phong_ban = \"Sales\" => luong >= 10000000." },
      { t: "Dòng bị bỏ qua", b: "Ô trống, sai kiểu hoặc chia cho 0 thì chưa kết luận được nên bị bỏ qua, và Denoise báo lại số dòng đó." },
    ],
  },
};

/* ----- Bộ id của từng nhóm -- mọi hàm bên dưới đọc theo TOOLSEC[g] ----- */
const TOOLSEC = {
  ft: {
    section: "free-tools", labels: TOOL_TAB_LABEL, info: TOOL_INFO, kind: "csv",
    tabs: "ft-tabs", crumb: "ft-crumb-tool", hero: "tool-hero", steps: "tool-steps", explainer: "tool-explainer",
    toggle: "ft-input-toggle", dropzone: "ft-dropzone", fileInput: "ft-file-input", paste: "ft-paste-input",
    preview: "ft-raw-preview", previewLabel: "ft-raw-preview-label", previewDims: "ft-raw-preview-dims",
    previewWrap: "ft-raw-preview-table-wrap", previewTable: "ft-raw-preview-table", previewNote: "ft-raw-preview-note",
    changeBtn: "ft-change-file-btn", strip: "pipeline-strip", error: "ft-error", status: "ft-status",
    resultEmpty: "ft-result-empty", resultCard: "ft-result-card", resultTag: "ft-result-tag", resultDims: "ft-result-dims",
    resultTable: "ft-result-table", download: "ft-download-btn", cont: "continue-panel", optionsScope: "#section-free-tools",
  },
  cv: {
    section: "convert", labels: CV_TAB_LABEL, info: CV_INFO, kind: "csv",
    tabs: "convert-tabs", crumb: "cv-crumb-tool", hero: "cv-hero", steps: "cv-steps", explainer: "cv-explainer",
    toggle: "convert-input-toggle", dropzone: "convert-dropzone", fileInput: "convert-file-input", paste: "convert-paste-input",
    preview: "cv-raw-preview", previewLabel: "cv-raw-preview-label", previewDims: "cv-raw-preview-dims",
    previewWrap: "cv-raw-preview-table-wrap", previewTable: "cv-raw-preview-table", previewNote: "cv-raw-preview-note",
    changeBtn: "cv-change-file-btn", strip: "cv-pipe-strip", error: "convert-error", status: "convert-status",
    resultEmpty: "convert-result-empty", resultCard: "convert-result-card", resultTag: "convert-result-tag", resultDims: "convert-result-dims",
    resultTable: "convert-result-table", download: "convert-download-btn", cont: "cv-continue", optionsScope: "#section-convert",
    dropTitle: "cv-dropzone-title",
  },
  cf: {
    section: "config", labels: CF_TAB_LABEL, info: CF_INFO, kind: "csv",
    tabs: "cf-tabs", crumb: "cf-crumb-tool", hero: "cf-hero", steps: "cf-steps", explainer: "cf-explainer",
    toggle: "cf-input-toggle", dropzone: "cf-dropzone", fileInput: "cf-file-input", paste: "cf-paste-input",
    preview: "cf-raw-preview", previewLabel: "cf-raw-preview-label", previewDims: "cf-raw-preview-dims",
    previewWrap: "cf-raw-preview-table-wrap", previewTable: "cf-raw-preview-table", previewNote: "cf-raw-preview-note",
    changeBtn: "cf-change-file-btn", strip: "cf-pipe-strip", error: "cf-error", status: "cf-status",
    resultEmpty: "cf-result-empty", resultCard: "cf-result-card", resultTag: "cf-result-tag", resultDims: "cf-result-dims",
    resultTable: "cf-result-table", download: "cf-download-btn", cont: "cf-continue", optionsScope: null,
  },
};
const GROUP_OF_SECTION = { "free-tools": "ft", convert: "cv", config: "cf" };
// Tool nào nhận được loại dữ liệu nào trong chuỗi nối tiếp: chỉ JSON → CSV
// nhận JSON, mọi tool khác nhận CSV. Dùng để lọc panel "Xử lý tiếp" và để
// tự thoát chế độ nối tiếp khi người dùng bấm tab sang tool không hợp.
function toolAccepts(g, tool, kind) {
  if (g === "cv" && tool === "json-to-csv") return kind === "json";
  return kind === "csv";
}
function pipeUsable(g) {
  const p = state.pipe;
  return p.active && !p.forceNewUpload && toolAccepts(g, state[g].tool, p.currentKind);
}

/* ----- Đọc nhanh nội dung file để XEM TRƯỚC (chỉ hiển thị; xử lý thật luôn
   ở backend). Bộ tách CSV cố tình đơn giản (split theo dấu phẩy). ----- */
function readFileAsText(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(file);
  });
}
function naiveParseCsvPreview(text, maxRows) {
  const lines = text.split(/\r\n|\r|\n/).filter((l) => l.length > 0);
  const rows = lines.slice(0, maxRows + 1).map((line) => line.split(","));
  return { rows, totalDataRows: Math.max(0, lines.length - 1) };
}

/* ----- Khu vực nhập liệu (dùng chung 3 nhóm) ----- */
function fillPreviewCard(g, label, dims, rows, note, tableOpts) {
  const T = TOOLSEC[g];
  const hasTable = !!(rows && rows.length);
  $(T.previewLabel).textContent = label;
  $(T.previewDims).textContent = dims || "";
  $(T.previewWrap).hidden = !hasTable;
  if (hasTable) renderPreviewTable($(T.previewTable), rows, tableOpts);
  const noteEl = $(T.previewNote);
  noteEl.hidden = !note;
  noteEl.textContent = note || "";
  noteEl.classList.toggle("is-only", !hasTable);
}
// Chế độ nối tiếp: khung 01 hiện ĐẦU VÀO của lần chạy kế tiếp = kết quả bước
// trước. CSV thì tách bảng để xem, JSON thì chỉ ghi chú.
function renderPipePreview(g) {
  const p = state.pipe;
  const stepsText = p.steps.length ? `Đầu vào hiện tại = kết quả sau: ${p.steps.map((s) => s.label).join(" → ")}` : "";
  if (p.currentKind === "json") {
    fillPreviewCard(g, p.originalLabel, `JSON · ${(p.currentText || "").length} ký tự`, null, stepsText || "Đầu vào hiện tại là JSON.");
    return;
  }
  const { rows, totalDataRows } = naiveParseCsvPreview(p.currentText || "", PREVIEW_ROWS);
  const colCount = rows.length ? rows[0].length : 0;
  fillPreviewCard(g, p.originalLabel, tableDims(totalDataRows, colCount), rows, stepsText);
}
function renderInputArea(g) {
  const T = TOOLSEC[g];
  const st = state[g];
  // Đang bấm nút "Xem ..." (dòng trùng / ô đã sửa): khung 01 hiện danh sách đó thay cho đầu vào
  // (dù đầu vào đang là file, text dán hay kết quả bước trước). Bấm "Xem dữ liệu" thì cờ
  // showing tắt và các nhánh bên dưới dựng lại đúng trạng thái như trước.
  if (g === "ft" && st.listView && st.listView.showing) {
    renderListView();
    $(T.toggle).hidden = true;
    $(T.dropzone).hidden = true;
    $(T.paste).hidden = true;
    $(T.preview).hidden = false;
    $(T.changeBtn).hidden = true;
    return;
  }
  if (pipeUsable(g)) {
    renderPipePreview(g);
    $(T.toggle).hidden = true;
    $(T.dropzone).hidden = true;
    $(T.paste).hidden = true;
    $(T.preview).hidden = false;
    $(T.changeBtn).hidden = true;
    return;
  }
  const showRawPreview = st.rawPreviewActive && !!st.filePreview;
  if (showRawPreview) {
    const f = st.filePreview;
    fillPreviewCard(g, f.label, f.dims, f.rows, f.note);
  }
  $(T.toggle).hidden = showRawPreview;
  $(T.dropzone).hidden = showRawPreview || st.inputMode !== "file";
  $(T.paste).hidden = showRawPreview || st.inputMode !== "paste";
  $(T.preview).hidden = !showRawPreview;
  $(T.changeBtn).hidden = false;
}
function showRawPreview(g, label, dims, rows, note) {
  state[g].rawPreviewActive = true;
  state[g].filePreview = { label, dims, rows, note };
  renderInputArea(g);
}
function hideRawPreview(g) {
  if (g === "ft") clearListView();
  const st = state[g];
  st.rawPreviewActive = false;
  st.filePreview = null;
  st.selectedFile = null;
  $(TOOLSEC[g].fileInput).value = "";
  renderInputArea(g);
  if (g === "ft") refreshFtColumns();
  if (g === "cf") refreshCfColumns(); // bỏ file -> dropdown chọn cột không được còn cột của file cũ
}
async function handleFileSelected(g, file) {
  if (g === "ft") clearListView(); // đầu vào đổi -> danh sách của lần chạy trước không còn đúng
  const st = state[g];
  st.selectedFile = file;
  if (g === "ft") refreshFtColumns(); // tool Sai định dạng / Ô trống: đọc cột của file vừa chọn
  const sizeText = `${(file.size / 1024).toFixed(1)} KB`;
  if (g === "cf") {
    // Tool cần cấu hình: nhờ backend đọc (có tên cột + kiểu đoán sẵn + 20 dòng
    // xem trước) -- hoạt động cả với Excel, và là nguồn cho dropdown chọn cột.
    await cfInspect({ file }, file.name);
    return;
  }
  if (g === "cv" && (!/\.(csv|txt)$/i.test(file.name) || st.tool === "json-to-csv")) {
    showRawPreview(g, file.name, sizeText, null, 'File JSON. Bấm "Chuyển đổi" để xem kết quả.');
    return;
  }
  if (!/\.csv$/i.test(file.name) && g === "ft") {
    showRawPreview(g, file.name, sizeText, null, 'Không xem trước được file Excel. Bấm "Chạy" để xem kết quả.');
    return;
  }
  let text;
  try {
    text = await readFileAsText(file);
  } catch (err) {
    showRawPreview(g, file.name, sizeText, null, "Không xem trước được file, nhưng vẫn chạy bình thường.");
    return;
  }
  const { rows, totalDataRows } = naiveParseCsvPreview(text, PREVIEW_ROWS);
  showRawPreview(g, file.name, tableDims(totalDataRows, rows.length ? rows[0].length : 0), rows, "");
}
// Gom đầu vào cho 1 lần gọi backend: đang nối tiếp -> text của bước trước;
// không thì file hoặc text dán tay. Trả về { error } hoặc { label }.
function collectInput(g, formData) {
  const T = TOOLSEC[g];
  const st = state[g];
  const p = state.pipe;
  if (pipeUsable(g)) {
    formData.append("text", p.currentText);
    return { label: p.originalLabel };
  }
  // Loại đầu vào gốc: chỉ tool JSON → CSV của Convert nhận JSON, mọi tool khác nhận CSV/Excel.
  const kind = g === "cv" && st.tool === "json-to-csv" ? "json" : "csv";
  if (st.inputMode === "file") {
    if (!st.selectedFile) return { error: "Chưa chọn file nào." };
    formData.append("file", st.selectedFile);
    return { label: st.selectedFile.name, source: { file: st.selectedFile, kind } };
  }
  const text = $(T.paste).value;
  if (!text.trim()) return { error: "Chưa dán nội dung nào." };
  formData.append("text", text);
  return { label: "văn bản dán tay", source: { text, kind } };
}

/* ----- Dải "đang nối tiếp" + 2 nút trên dải (dùng chung 3 nhóm) ----- */
function renderPipeStrips() {
  const p = state.pipe;
  const stepsText = p.steps.length ? ` · đã qua: ${p.steps.map((s) => s.label).join(" → ")}` : " · chưa xử lý bước nào";
  Object.keys(TOOLSEC).forEach((g) => {
    const strip = $(TOOLSEC[g].strip);
    strip.hidden = !p.active;
    if (p.active) strip.querySelector(".pipe-strip-text").innerHTML = `📄 Đang dùng: <strong>${escapeHtml(p.originalLabel)}</strong>${escapeHtml(stepsText)}`;
    // Nút Hoàn tác: có bước để lùi (còn snapshot) hoặc đang ở đúng bước đầu (lùi = về dữ liệu gốc); hết thì ẩn.
    const undoBtn = strip.querySelector(".pipe-undo-btn");
    if (undoBtn) {
      const canUndo = p.active && p.steps.length > 0 && (p.undoStack.length > 0 || p.steps.length === 1);
      undoBtn.hidden = !canUndo;
      if (canUndo) undoBtn.title = `Hoàn tác «${p.steps[p.steps.length - 1].label}»${p.undoStack.length ? "" : " (quay về dữ liệu gốc)"}`;
    }
    renderInputArea(g);
  });
  refreshFtColumns(); // đầu vào nối tiếp đổi -> bảng cột của tool Sai định dạng / Ô trống cập nhật theo
  refreshCfColumns(); // ... và danh sách cột của khối Cần cấu hình (nếu đang mở)
}
// Quên file đang chọn của nhóm g: ô kéo-thả về trống như chưa chọn gì. Trước đây "Tải file khác" chỉ ẩn bản xem trước nhưng VẪN giữ
// st.selectedFile của file cũ, nên (1) hàm đọc cột đọc lại đúng file cũ -> bảng cột bên dưới hiện cột cũ, (2) bấm Chạy khi ô kéo-thả
// đang trống vẫn âm thầm xử lý lại file cũ rồi nối vào chuỗi cũ.
function forgetSelectedFile(g) {
  const st = state[g];
  st.rawPreviewActive = false;
  st.filePreview = null;
  st.selectedFile = null;
  $(TOOLSEC[g].fileInput).value = "";
  if (g === "ft") clearListView(); // danh sách "Xem ..." của lần chạy trước thuộc file cũ; đang xem nó thì khung 01 kẹt ở danh sách
}
document.querySelectorAll(".pipe-new-file-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    state.pipe.forceNewUpload = true;
    // Chuỗi nối tiếp dùng chung 3 nhóm nên file cũ phải bị quên ở CẢ 3 nhóm, không chỉ nhóm đang mở.
    Object.keys(TOOLSEC).forEach(forgetSelectedFile);
    renderPipeStrips();
  });
});
// Lấy lại dữ liệu GỐC của chuỗi (đầu vào người dùng đã đưa vào lúc bắt đầu, TRƯỚC mọi bước xử lý):
//  - text dán tay, hoặc file JSON: dùng lại nguyên văn (JSON là chữ, trình duyệt đọc được);
//  - file CSV/Excel: gửi lại file gốc (trình duyệt vẫn giữ) lên /api/noise-tools/normalize để backend đọc bằng ĐÚNG bộ đọc của lần
//    chạy đầu rồi trả CSV chuẩn -- Excel không đọc được dạng chữ trong trình duyệt, và CSV khác mã hoá cũng nên để backend đọc.
// Trước đây "về gốc" chỉ quay về KẾT QUẢ BƯỚC ĐẦU TIÊN (dòng đã xoá ở bước 1 không quay lại) dù dải ghi "chưa xử lý bước nào".
async function loadPipeOriginal() {
  const p = state.pipe;
  const src = p.originalSource;
  if (!src) return { text: p.originalText, kind: p.originalKind }; // dự phòng: chuỗi không ghi nhớ được đầu vào thật
  if (src.text !== undefined) return { text: src.text, kind: src.kind };
  if (src.kind === "json") {
    try {
      return { text: await readFileAsText(src.file), kind: "json" };
    } catch (err) {
      throw new Error("Không đọc lại được file gốc (có thể file đã bị đổi hoặc xoá trên máy). Bấm \"Tải file khác\" để chọn lại.");
    }
  }
  const fd = new FormData();
  fd.append("file", src.file);
  let response, data;
  try {
    response = await fetch("/api/noise-tools/normalize", { method: "POST", body: fd });
    data = await response.json();
  } catch (err) {
    throw new Error("Không gọi được backend để lấy lại file gốc. Kiểm tra xem python3 app.py có đang chạy không.");
  }
  if (!response.ok) throw new Error(data.error || "Không đọc lại được file gốc.");
  return { text: data.result_text, kind: "csv" };
}
// Quay về dữ liệu gốc của chuỗi (dùng cho nút "Bắt đầu lại từ gốc" và cho nút Hoàn tác khi chỉ còn bước đầu tiên). Trả về true nếu xong.
async function resetPipeToOriginal(btn, g) {
  const p = state.pipe;
  const errEl = $(TOOLSEC[g].error);
  setError(errEl, "");
  btn.disabled = true; // đang lấy lại file gốc từ backend: chặn bấm chồng
  let original;
  try {
    original = await loadPipeOriginal();
  } catch (err) {
    setError(errEl, err.message);
    return false;
  } finally {
    btn.disabled = false;
  }
  p.currentText = original.text;
  p.currentKind = original.kind;
  p.steps = [];
  p.undoStack = [];
  p.forceNewUpload = false;
  renderPipeStrips(); // đã tự đọc lại cột của Cần cấu hình theo đầu vào gốc (refreshCfColumns)
  Object.keys(TOOLSEC).forEach(resetResult);
  return true;
}
function pipeGroupOfButton(btn) {
  return Object.keys(TOOLSEC).find((k) => $(TOOLSEC[k].strip).contains(btn));
}
document.querySelectorAll(".pipe-reset-btn").forEach((btn) => {
  btn.addEventListener("click", async () => {
    if (state.cf.applyBusy) return; // đang chờ lệnh Áp dụng: không đổi chuỗi nối tiếp giữa chừng
    await resetPipeToOriginal(btn, pipeGroupOfButton(btn));
  });
});
// Hoàn tác BƯỚC CUỐI: quay về trạng thái ngay trước bước đó (tối đa PIPE_UNDO_MAX bước gần nhất). Còn đúng 1 bước thì quay về dữ liệu gốc.
document.querySelectorAll(".pipe-undo-btn").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const p = state.pipe;
    if (state.cf.applyBusy || !p.steps.length) return;
    const g = pipeGroupOfButton(btn);
    const undone = p.steps[p.steps.length - 1];
    if (p.undoStack.length) {
      const snap = p.undoStack.pop();
      p.currentText = snap.text;
      p.currentKind = snap.kind;
      p.steps = snap.steps;
      p.forceNewUpload = false;
      renderPipeStrips();
      Object.keys(TOOLSEC).forEach(resetResult); // bảng kết quả đang hiện là của bước vừa bị huỷ nên không còn đúng
    } else if (!(await resetPipeToOriginal(btn, g))) {
      return; // không lấy lại được file gốc (lỗi đã hiện ở khung lỗi của nhóm)
    }
    setStatus($(TOOLSEC[g].status), `↶ Đã hoàn tác «${undone.label}»`, "is-ok");
  });
});
// Ghi nhận 1 bước vừa xong: kết quả thành đầu vào kế tiếp của cả 3 nhóm.
// fresh = lần chạy này dùng file/text MỚI (không phải kết quả bước trước) ->
// bắt đầu 1 chuỗi mới, bỏ chuỗi cũ.
function recordPipeStep(label, text, kind, inputLabel, fresh, source) {
  const p = state.pipe;
  if (!p.active || fresh) {
    p.active = false;
    p.active = true;
    p.originalSource = source || null; // đầu vào THẬT của chuỗi mới (không có thì "về gốc" dùng dự phòng bên dưới)
    p.originalText = text;
    p.originalKind = kind;
    p.originalLabel = inputLabel;
    p.steps = [];
    p.undoStack = []; // chuỗi mới: không còn gì để hoàn tác của chuỗi cũ
  } else {
    // Ghi lại trạng thái TRƯỚC bước này để nút Hoàn tác quay về được (chỉ giữ THAM CHIẾU tới chuỗi chữ cũ, không copy dữ liệu).
    p.undoStack.push({ text: p.currentText, kind: p.currentKind, steps: p.steps.slice() });
    if (p.undoStack.length > PIPE_UNDO_MAX) p.undoStack.shift();
  }
  p.currentText = text;
  p.currentKind = kind;
  p.steps.push({ label });
  p.forceNewUpload = false;
  renderPipeStrips();
}

/* ----- Kết quả (khung 02) dùng chung ----- */
function resetResult(g) {
  const T = TOOLSEC[g];
  $(T.resultEmpty).hidden = false;
  $(T.resultCard).hidden = true;
  $(T.download).disabled = true;
  $(T.cont).hidden = true;
  setStatus($(T.status), "", "");
  setError($(T.error), "");
  if (g === "cv") $("convert-json-card").hidden = true;
  if (g === "ft") {
    clearListView();
    renderInputArea("ft"); // nếu đang hiện danh sách thì trả khung 01 về bình thường
  }
  if (g === "cf") {
    $("cf-handling").hidden = true;
    hideCfConfirm();
    $("cf-result-note").hidden = true;
    setError($("cf-apply-error"), "");
    setStatus($("cf-apply-status"), "", "");
    state.cf.detect = null;
  }
}
function showResultTable(g, tag, rows, dims) {
  const T = TOOLSEC[g];
  $(T.resultEmpty).hidden = true;
  $(T.resultCard).hidden = false;
  $(T.resultTag).textContent = tag;
  $(T.resultDims).textContent = dims;
  renderPreviewTable($(T.resultTable), rows);
}
function statusFromStats(stats) {
  const parts = [];
  if (stats.removed_row_count > 0) parts.push(`đã xoá ${stats.removed_row_count} dòng (${stats.original_row_count} → ${stats.final_row_count})`);
  else parts.push(`giữ nguyên ${stats.final_row_count} dòng`);
  if (stats.filled_cell_count !== undefined) {
    // Tool Ô trống: nói rõ số ô đã điền và số ô định điền mà vẫn trống.
    if (stats.filled_cell_count > 0) parts.push(`đã điền ${stats.filled_cell_count} ô`);
    if (stats.unfilled_cell_count > 0) parts.push(`${stats.unfilled_cell_count} ô chưa điền được`);
  } else if (stats.cells_changed > 0) parts.push(`đã sửa ${stats.cells_changed} ô`);
  // Tool Sai định dạng ở chế độ "chỉ báo" (không đổi gì): nói rõ đã tìm thấy bao nhiêu ô sai.
  if (stats.flagged_cell_count !== undefined && !stats.removed_row_count && !stats.cells_changed) {
    parts.push(stats.flagged_cell_count > 0 ? `tìm thấy ${stats.flagged_cell_count} ô sai định dạng` : "không thấy ô nào sai định dạng");
  }
  if (stats.columns_removed) parts.push(`đã xoá ${stats.columns_removed} cột`);
  // Phụ thuộc hàm (2 cách xử lý theo gợi ý): các nhóm không xác định được ô sai thì giữ nguyên, nói rõ để người dùng tự xử lý.
  if (stats.unresolved_groups) parts.push(`${stats.unresolved_groups} nhóm chưa xác định được ô sai, giữ nguyên`);
  return `✅ ${parts.join(" · ")}`;
}
// Tải xuống = kết quả MỚI NHẤT của chuỗi (pipe.currentText), đuôi theo loại.
Object.keys(TOOLSEC).forEach((g) => {
  $(TOOLSEC[g].download).addEventListener("click", () => {
    const p = state.pipe;
    if (!p.currentText) return;
    const isJson = p.currentKind === "json";
    const blob = new Blob([p.currentText], { type: isJson ? "application/json;charset=utf-8" : "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = (p.steps.length > 1 ? "da-xu-ly" : state[g].tool) + (isJson ? ".json" : ".csv");
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  });
});

/* ----- Panel "Xử lý tiếp": 3 danh mục, mọi mục đều bấm được ----- */
// Ký hiệu (icon) của từng tool PHẢI GIỐNG HỆT ký hiệu ở menu "Product" trên header (workspace.html,
// class ws-megamenu-icon) -- đơn sắc, cùng kiểu cho cả 3 nhóm. Sửa ký hiệu ở đâu thì sửa cả 2 nơi.
const CONTINUE_GROUPS = [
  { key: "configure", label: "Cần cấu hình", g: "cf", attr: "data-config-tool", items: [
    { icon: "[ ]", tool: "out-of-range", sub: "Khai min / max" },
    { icon: "↯", tool: "outlier", sub: "IQR · Z-score" },
    { icon: "≈", tool: "inconsistent-category", sub: "Về giá trị chuẩn" },
    { icon: "⋈", tool: "cross-rule", sub: "Mâu thuẫn giữa các cột" },
  ] },
  { key: "convert", label: "Chuyển đổi", g: "cv", attr: "data-convert-tool", items: [
    { icon: "⇄", tool: "delimiter" }, { icon: "{ }", tool: "csv-to-json" }, { icon: "{ }", tool: "json-to-csv" },
  ] },
  { key: "auto", label: "Tự động", g: "ft", attr: "data-tool", items: [
    { icon: "⧉", tool: "remove-duplicates" }, { icon: "⇥", tool: "trim-whitespace" },
    { icon: "□", tool: "blanks" },
    { icon: "@", tool: "format-noise" },
  ] },
  // Không phải tool trong chuỗi: bấm là chuyển kết quả hiện tại sang Class Noise (bước 1, như vừa chọn file đó). Chỉ nhận CSV.
  { key: "class-noise", label: "Nhãn sai", special: true, items: [] },
];
function renderContinuePanel(g) {
  const panel = $(TOOLSEC[g].cont);
  const pills = panel.querySelector(".continue-pills");
  const list = panel.querySelector(".continue-list");
  const isJson = state.pipe.currentKind === "json"; // sau CSV → JSON chỉ còn JSON → CSV nhận được
  panel.hidden = false;
  list.innerHTML = "";
  pills.innerHTML = CONTINUE_GROUPS.map((gr) =>
    `<button type="button" class="continue-pill" data-category="${gr.key}"${isJson && gr.key !== "convert" ? " disabled" : ""}${gr.special ? ' title="Dùng kết quả này làm file cho Nhãn sai"' : ""}>${gr.label}</button>`
  ).join("");
  pills.querySelectorAll(".continue-pill").forEach((pill) => {
    pill.addEventListener("click", () => {
      if (pill.dataset.category === "class-noise") {
        sendPipeToClassNoise();
        return;
      }
      const reopen = pill.classList.contains("is-active");
      pills.querySelectorAll(".continue-pill").forEach((b) => b.classList.toggle("is-active", b === pill && !reopen));
      if (reopen) { list.innerHTML = ""; return; }
      const gr = CONTINUE_GROUPS.find((x) => x.key === pill.dataset.category);
      const items = gr.items.filter((it) => toolAccepts(gr.g, it.tool, state.pipe.currentKind));
      list.innerHTML = items.map((it) => {
        const label = TOOLSEC[gr.g].labels[it.tool];
        return `<a class="continue-item" href="#" ${gr.attr}="${it.tool}" data-chain-group="${gr.g}"><span class="continue-item-icon">${it.icon}</span><span>${escapeHtml(label)}${it.sub ? `<small>${escapeHtml(it.sub)}</small>` : ""}</span></a>`;
      }).join("");
      list.querySelectorAll("a[data-chain-group]").forEach((a) => {
        a.addEventListener("click", (e) => {
          e.preventDefault();
          startChain(a.dataset.chainGroup, a.getAttribute(gr.attr));
        });
      });
    });
  });
}
// Chuyển kết quả hiện tại (CSV) sang Class Noise: mở khối Class Noise rồi nạp text như một file vừa chọn ở bước 1
// (workspace-flow.js: DenoiseFlow.loadCsvText). Người dùng bấm "Tải lên" như thường.
function sendPipeToClassNoise() {
  const p = state.pipe;
  if (!p.currentText || p.currentKind !== "csv") return;
  const base = (p.originalLabel || "").replace(/\.(csv|txt|xlsx|xls)$/i, "");
  const name = (base && base !== "văn bản dán tay" ? base : "du-lieu") + "_da-xu-ly.csv";
  switchSection("class-noise");
  if (window.DenoiseFlow && window.DenoiseFlow.loadCsvText) window.DenoiseFlow.loadCsvText(p.currentText, name);
}
// Mang kết quả hiện tại sang tool đích (có thể ở nhóm khác).
function startChain(g, tool) {
  switchSection(TOOLSEC[g].section);
  activateTool(g, tool);
  state.pipe.forceNewUpload = false;
  renderPipeStrips();
  const fromText = `📥 Đang dùng kết quả của bước trước (${state.pipe.steps.map((s) => s.label).join(" → ")}).`;
  setStatus($(TOOLSEC[g].status), fromText, "is-ok");
  // (Cần cấu hình: renderPipeStrips() ở trên đã đọc cột của đầu vào nối tiếp, xem refreshCfColumns)
}

/* ----- Chọn tool (tab) + nội dung trang theo tool ----- */
function renderToolInfo(g, tool) {
  const T = TOOLSEC[g];
  const info = T.info[tool];
  $(T.crumb).textContent = T.labels[tool];
  $(T.hero).innerHTML = `
    <div class="tool-hero-grid">
      <div>
        <h1 class="tool-hero-headline">${info.headline}</h1>
        <p class="tool-hero-desc">${info.desc}</p>
      </div>
      ${info.mock}
    </div>`;
  $(T.steps).innerHTML = info.steps
    .map((s, i) => `<div><p class="tool-step-num">0${i + 1}</p><p class="tool-step-text">${escapeHtml(s)}</p></div>`)
    .join("");
  $(T.explainer).innerHTML = info.explainer
    .map((e) => `<div><p class="tool-explainer-title">${escapeHtml(e.t)}</p><p class="tool-explainer-body">${escapeHtml(e.b)}</p></div>`)
    .join("");
  if (T.dropTitle && info.dropTitle) {
    $(T.dropTitle).textContent = info.dropTitle;
    $(T.fileInput).accept = info.accept;
  }
}
function activateTool(g, tool) {
  const T = TOOLSEC[g];
  state[g].tool = tool;
  document.querySelectorAll(`#${T.tabs} .convert-tab`).forEach((b) => b.classList.toggle("is-active", b.dataset.tool === tool));
  // Khối tuỳ chọn tĩnh (ft, cv): chỉ hiện đúng khối của tool. SCOPE theo khối
  // vì ".convert-options" dùng chung giữa các nhóm.
  if (T.optionsScope) {
    document.querySelectorAll(`${T.optionsScope} .convert-options`).forEach((el) => (el.hidden = el.id !== "convert-options-" + tool));
  }
  renderToolInfo(g, tool);
  if (g === "cv") hideRawPreview(g); // đổi tool Convert là đổi loại file nhận vào
  if (g === "cf") renderCfOptions();
  // Đang nối tiếp mà bấm sang tool không nhận loại dữ liệu hiện có (vd đổi
  // delimiter trên JSON) -> tự chuyển về chọn file mới cho tool đó.
  if (state.pipe.active && !toolAccepts(g, tool, state.pipe.currentKind)) state.pipe.forceNewUpload = true;
  renderInputArea(g);
  resetResult(g);
  if (g === "ft") refreshFtColumns();
}
Object.keys(TOOLSEC).forEach((g) => {
  const T = TOOLSEC[g];
  document.querySelectorAll(`#${T.tabs} .convert-tab`).forEach((btn) => btn.addEventListener("click", () => activateTool(g, btn.dataset.tool)));
  wireInputToggle($(T.toggle), $(T.dropzone), $(T.paste), (mode) => { state[g].inputMode = mode; if (g === "ft") refreshFtColumns(); });
  wireDropzone($(T.dropzone), $(T.fileInput), (file) => handleFileSelected(g, file));
  $(T.changeBtn).addEventListener("click", () => hideRawPreview(g));
});
// Link tĩnh (menu Product, chân trang, trang chủ) -> mở đúng nhóm + tab.
[["a[data-tool]", "ft", "tool"], ["a[data-convert-tool]", "cv", "convertTool"], ["a[data-config-tool]", "cf", "configTool"]].forEach(([sel, g, key]) => {
  document.querySelectorAll(sel).forEach((a) => {
    a.addEventListener("click", (e) => {
      e.preventDefault();
      switchSection(TOOLSEC[g].section);
      activateTool(g, a.dataset[key]);
      setProductMenuOpen(false);
    });
  });
});

/* ============================================================
   FREE TOOLS -- tuỳ chọn tĩnh + bấm Chạy
   ============================================================ */
document.querySelectorAll(".ft-seg[data-seg-for]").forEach(wireSegmented);

$("ft-run-btn").addEventListener("click", async () => {
  const T = TOOLSEC.ft;
  setError($(T.error), "");
  const formData = new FormData();
  const fresh = !pipeUsable("ft");
  const inp = collectInput("ft", formData);
  if (inp.error) return setError($(T.error), inp.error);
  const tool = state.ft.tool;
  if (tool === "remove-duplicates") {
    formData.append("subset_columns", $("opt-subset-columns").value);
    formData.append("keep", $("opt-keep").value);
    formData.append("ignore_case", $("opt-ignore-case").checked ? "true" : "false");
    formData.append("ignore_whitespace", $("opt-ignore-whitespace").checked ? "true" : "false");
  } else if (tool === "trim-whitespace") {
    formData.append("collapse_repeated", $("opt-collapse-repeated").checked ? "true" : "false");
    formData.append("remove_zero_width", $("opt-remove-zero-width").checked ? "true" : "false");
  } else if (tool === "blanks") {
    // Bảng phải KHỚP đầu vào hiện tại: đầu vào vừa đổi mà bảng chưa kịp đọc lại (vd dán text khác rồi bấm Chạy trong lúc đang
    // chờ 600ms) thì đọc lại ngay -- lựa chọn của bảng cũ bị bỏ, không gửi nhầm tên cột không có trong đầu vào mới. Rồi chờ lần
    // đọc đang chạy dở (vd vừa nối tiếp từ bước trước) xong để gửi đúng bảng mới nhất.
    await refreshFtBlankColumns();
    if (state.ft.blankPromise) await state.ft.blankPromise;
    const actions = {};
    for (const c of state.ft.blankCols || []) {
      if (c.action === "keep") continue;
      if (c.action === "fixed_value") {
        // Chỉ gửi các ô đã gõ (bỏ ô rỗng). Cần ít nhất 1 giá trị: gõ vào ô trống trong bảng "Điền tay" hoặc "Giá trị chung".
        const cells = Object.fromEntries(Object.entries(c.cellValues).filter(([, v]) => String(v).trim()));
        if (!String(c.fixedValue).trim() && !Object.keys(cells).length) {
          return setError($(T.error), `Cột "${c.name}": chưa điền giá trị nào. Bấm "✎ Điền tay" rồi gõ vào các ô trống, hoặc nhập "Giá trị chung".`);
        }
        actions[c.name] = { dtype: c.dtype, action: c.action, fixed_value: c.fixedValue, cell_values: cells };
      } else {
        actions[c.name] = { dtype: c.dtype, action: c.action, fixed_value: "" };
      }
    }
    formData.append("column_actions", JSON.stringify(actions));
    formData.append("remove_empty_rows", $("opt-blank-remove-empty-rows").checked ? "true" : "false");
    formData.append("remove_empty_columns", $("opt-blank-remove-empty-columns").checked ? "true" : "false");
  } else if (tool === "format-noise") {
    // Bảng kiểu cột phải KHỚP đầu vào hiện tại: đầu vào vừa đổi mà bảng chưa kịp đọc lại (vd dán text khác rồi bấm Chạy trong
    // lúc đang chờ 600ms) thì đọc lại ngay, bỏ kiểu của bảng cũ -- không gửi nhầm tên cột không có trong đầu vào mới. Rồi chờ lần
    // đọc đang chạy dở (vd vừa nối tiếp từ bước trước) xong để gửi đúng bảng mới nhất.
    await refreshFtColumnTypes();
    if (state.ft.colPromise) await state.ft.colPromise;
    const cols = state.ft.colTypes;
    const badDate = (cols || []).find((c) => c.dtype === "date" && !String(c.dateFormat).includes("%"));
    if (badDate) return setError($(T.error), `Khuôn ngày của cột "${badDate.name}" phải có dạng %Y-%m-%d (có dấu %).`);
    formData.append("action", $("opt-format-action").value);
    // Gửi kiểu từng cột người dùng đã xác nhận/sửa; không có bảng (đọc cột lỗi) thì backend tự đoán.
    if (cols) formData.append("column_types", JSON.stringify(Object.fromEntries(cols.map((c) => [c.name, { dtype: c.dtype, date_format: c.dtype === "date" ? c.dateFormat : "" }]))));
  }
  const data = await callBackend($("ft-run-btn"), "Chạy", "/api/noise-tools/" + tool, formData, $(T.error));
  if (!data) return;
  const colCount = data.preview_rows && data.preview_rows.length ? data.preview_rows[0].length : 0;
  showResultTable("ft", TOOL_TAB_LABEL[tool], data.preview_rows, tableDims(data.stats.final_row_count, colCount));
  $(T.download).disabled = false;
  setStatus($(T.status), statusFromStats(data.stats), "is-ok");
  // Phải đặt listView TRƯỚC recordPipeStep (hàm đó dựng lại khung 01). Chạy xong luôn về chế độ
  // xem bình thường (showing = false); chỉ 2 tool có danh sách để xem (xem LIST_VIEW).
  const lv = LIST_VIEW[tool];
  state.ft.listView = lv && data[lv.field] ? { kind: tool, data: data[lv.field], showing: false } : null;
  recordPipeStep(TOOL_TAB_LABEL[tool], data.result_text, "csv", inp.label, fresh, inp.source);
  renderListButton();
  if (tool === "format-noise") {
    // Hiện số ô sai cạnh từng cột trong bảng kiểu dữ liệu. countsSig = chữ ký đầu vào SAU bước này (đầu vào
    // đã chuyển sang kết quả bước này) để lần đọc lại cột ngay sau đó không xoá mất số liệu vừa có.
    const src = ftInputSource();
    state.ft.colCounts = data.format_preview ? data.format_preview.column_error_counts : null;
    state.ft.countsSig = src ? src.sig : "";
    renderFtColTypes();
  }
  renderContinuePanel("ft");
});

/* ----- Nút "Xem ..." ⇄ "Xem dữ liệu" (tool Xoá dòng trùng và Cắt khoảng trắng thừa, sau khi đã chạy) -----
   Bấm: khung 01 đổi từ đầu vào sang danh sách (dòng trùng / ô đã sửa), nút thành "Xem dữ liệu".
   Bấm lại: khung 01 về y hệt trước đó. Cấu hình riêng từng tool: */
const LIST_VIEW = {
  "remove-duplicates": {
    field: "duplicate_preview",        // tên field backend trả về
    open: "Xem các dòng trùng",         // chữ nút khi đang xem đầu vào
    none: "Không có dòng trùng",        // chữ nút (mờ) khi không có gì để xem
    count: (d) => d.group_row_count,
    totalRows: (d) => d.group_row_count,
    tag: "Dòng trùng",
    dims: (d) => `${d.group_row_count} dòng trùng · ${d.removed_row_count} dòng đã xoá`,
    truncated: (d) => `Hiện ${d.shown_count}/${d.group_row_count} dòng trùng đầu tiên. `,
    note: 'Các dòng cùng nhóm trùng nằm cạnh nhau · "Giữ" = bản được giữ, "Xoá" = bản đã bị xoá.',
    // Cột "Dòng" = số dòng GỐC, cột "Kết quả" = Giữ / Xoá; dòng bị xoá tô riêng (class is-removed).
    tableOpts: (d) => ({ rowNumbers: d.row_numbers, rowClasses: d.row_status.map((x) => (x === "remove" ? "is-removed" : "is-kept")) }),
  },
  "trim-whitespace": {
    field: "trim_preview",
    open: "Xem các ô đã sửa",
    none: "Không có ô nào cần sửa",
    count: (d) => d.changed_cell_count,
    totalRows: (d) => d.changed_row_count,
    tag: "Ô đã sửa",
    dims: (d) => `${d.changed_cell_count} ô đã sửa · ${d.changed_row_count} dòng`,
    truncated: (d) => `Hiện ${d.shown_count}/${d.changed_row_count} dòng có ô đã sửa đầu tiên. `,
    note: 'Ô tô nền = ô đã sửa, hiện giá trị trước khi sửa · ␣ dấu cách · ⇥ tab · ⏎ xuống dòng · ⍽ khoảng trắng cứng · ⟨ZW⟩ ký tự vô hình.',
    // Ô đã sửa tô nền (class is-changed).
    tableOpts: (d) => ({ rowNumbers: d.row_numbers, cellClasses: d.cell_changed.map((row) => row.map((c) => (c ? "is-changed" : ""))) }),
  },
  "blanks": {
    field: "blank_preview",
    open: "Xem các ô trống đã xử lý",
    none: "Không có ô trống nào bị xử lý",
    count: (d) => d.affected_row_count,
    totalRows: (d) => d.affected_row_count,
    tag: "Ô trống đã xử lý",
    dims: (d) => `${d.filled_cell_count} ô đã điền · ${d.removed_row_count} dòng đã xoá`,
    truncated: (d) => `Hiện ${d.shown_count}/${d.affected_row_count} dòng đầu tiên. `,
    note: (d) => 'Dòng gạch ngang = đã xoá · ô tô nền = ô trống đã xử lý ("trước → sau")' +
      (d.removed_columns && d.removed_columns.length ? ` · cột trống hoàn toàn đã xoá: ${d.removed_columns.join(", ")}` : "") + ".",
    // Dòng bị xoá gạch ngang (is-removed); ô trống đã xử lý tô nền (is-flagged).
    tableOpts: (d) => ({
      rowNumbers: d.row_numbers,
      rowClasses: d.row_status.map((x) => (x === "remove" ? "is-removed" : "")),
      cellClasses: d.cell_flagged.map((row) => row.map((c) => (c ? "is-flagged" : ""))),
    }),
  },
  "format-noise": {
    field: "format_preview",
    open: "Xem các ô sai định dạng",
    none: "Không có ô sai định dạng",
    count: (d) => d.flagged_cell_count,
    totalRows: (d) => d.flagged_row_count,
    tag: "Ô sai định dạng",
    dims: (d) => `${d.flagged_cell_count} ô sai · ${d.flagged_row_count} dòng`,
    truncated: (d) => `Hiện ${d.shown_count}/${d.flagged_row_count} dòng có ô sai đầu tiên. `,
    note: 'Ô tô nền = ô sai định dạng. Đoán sai kiểu cột thì sửa ở bảng bên dưới rồi chạy lại.',
    // Ô sai tô nền (class is-flagged).
    tableOpts: (d) => ({ rowNumbers: d.row_numbers, cellClasses: d.cell_flagged.map((row) => row.map((c) => (c ? "is-flagged" : ""))) }),
  },
};
function clearListView() {
  state.ft.listView = null;
  renderListButton();
}
// Hiện/ẩn nút và đặt chữ: chưa chạy (hoặc đang ở tab của tool khác) -> ẩn; chạy xong mà không có gì để xem
// -> mờ, báo "Không có ..."; có -> "Xem các ..." (đang xem đầu vào) hoặc "Xem dữ liệu" (đang xem danh sách).
function renderListButton() {
  const btn = $("ft-view-btn");
  const v = state.ft.listView;
  btn.hidden = !(v && state.ft.tool === v.kind);
  if (btn.hidden) return;
  const cfg = LIST_VIEW[v.kind];
  const empty = cfg.count(v.data) === 0;
  btn.disabled = empty;
  btn.textContent = empty ? cfg.none : v.showing ? "Xem dữ liệu" : cfg.open;
}
// Dựng danh sách vào thẻ xem trước của khung 01.
function renderListView() {
  const v = state.ft.listView;
  const cfg = LIST_VIEW[v.kind];
  const d = v.data;
  const shownAll = d.shown_count >= cfg.totalRows(d);
  fillPreviewCard("ft", cfg.tag, cfg.dims(d), d.rows, (shownAll ? "" : cfg.truncated(d)) + (typeof cfg.note === "function" ? cfg.note(d) : cfg.note), cfg.tableOpts(d));
}
/* ----- Sai định dạng: bảng KIỂU DỮ LIỆU TỪNG CỘT dưới bảng đầu vào (đoán sẵn, sửa được) -----
   Sau khi có đầu vào (file / text dán / kết quả bước trước), hỏi backend /api/noise-tools/inspect lấy tên cột + kiểu
   đoán sẵn (+ khuôn ngày) rồi dựng 1 dòng cho mỗi cột. Người dùng đổi kiểu nếu đoán sai; bấm Chạy thì gửi kiểu đã chọn
   lên (field column_types). Chỉ 5 kiểu Số nguyên / Số thực / Email / SĐT / Ngày có khuôn để kiểm tra. */
const FORMAT_DTYPE_OPTIONS = [
  ["integer", "Số nguyên"], ["float", "Số thực"], ["email", "Email"], ["phone", "Số điện thoại"],
  ["date", "Ngày tháng"], ["category", "Nhóm (không kiểm tra)"], ["text", "Văn bản (không kiểm tra)"],
];
const FORMAT_DTYPE_LABEL = Object.fromEntries(FORMAT_DTYPE_OPTIONS);
const DEFAULT_DATE_FORMAT = "%Y-%m-%d";

// Băm nhanh (djb2) để nhận ra "đầu vào đã đổi chưa" mà không phải giữ cả đoạn text.
function hashText(text) {
  let h = 5381;
  for (let i = 0; i < text.length; i++) h = ((h << 5) + h + text.charCodeAt(i)) | 0;
  return h;
}
// Đầu vào hiện tại của Free Tools, cùng thứ tự ưu tiên với collectInput(): kết quả bước trước > file > text dán.
// sig = "chữ ký" đầu vào (đổi khi đầu vào đổi); pipe = true nếu đang nối tiếp từ bước trước.
function ftInputSource() {
  const st = state.ft;
  const p = state.pipe;
  if (pipeUsable("ft")) return { text: p.currentText, pipe: true, sig: `pipe:${p.steps.length}:${p.currentText.length}:${hashText(p.currentText)}` };
  if (st.inputMode === "file") {
    const f = st.selectedFile;
    return f ? { file: f, pipe: false, sig: `file:${f.name}:${f.size}:${f.lastModified}` } : null;
  }
  const text = $("ft-paste-input").value;
  return text.trim() ? { text, pipe: false, sig: `text:${text.length}:${hashText(text)}` } : null;
}
function isFtColEdited(c) {
  return c.dtype !== c.guessed || (c.dtype === "date" && c.dateFormat !== c.guessedFmt);
}
// Đọc lại cột nếu đầu vào đã đổi (gọi mỗi khi chọn file / gõ text / đổi tab / đầu vào nối tiếp đổi). Chỉ chạy khi đang ở
// tool Sai định dạng; cùng đầu vào thì giữ nguyên bảng (và các kiểu người dùng đã sửa).
async function refreshFtColumnTypes() {
  const st = state.ft;
  if (st.tool !== "format-noise") return;
  const src = ftInputSource();
  if (!src) {
    st.colSig = "";
    st.colTypes = null;
    st.colState = "idle";
    st.colCounts = null;
    renderFtColTypes();
    return;
  }
  if (src.sig === st.colSig) return;
  st.colSig = src.sig;
  const seq = ++st.colSeq;
  const prev = st.colTypes;
  // Nối tiếp từ bước trước thì cột gần như không đổi: giữ bảng cũ trong lúc đọc lại cho đỡ nháy.
  if (!(src.pipe && prev)) {
    st.colTypes = null;
    st.colCounts = null;
    st.colState = "loading";
    renderFtColTypes();
  }
  const fd = new FormData();
  if (src.file) fd.append("file", src.file);
  else fd.append("text", src.text);
  st.colPromise = (async () => {
    let response, data;
    try {
      response = await fetch("/api/noise-tools/inspect", { method: "POST", body: fd });
      data = await response.json();
    } catch (err) {
      if (seq === st.colSeq) { st.colTypes = null; st.colState = "error"; st.colError = "Không gọi được backend để đọc cột."; renderFtColTypes(); }
      return;
    }
    if (seq !== st.colSeq) return; // đã có lần đọc mới hơn
    if (!response.ok) { st.colTypes = null; st.colState = "error"; st.colError = data.error || "Không đọc được nội dung."; renderFtColTypes(); return; }
    // Chuỗi nối tiếp: cột nào người dùng đã sửa kiểu thì giữ lựa chọn đó (tìm theo tên cột).
    const prevByName = new Map((src.pipe && prev ? prev : []).map((c) => [c.name, c]));
    st.colTypes = data.columns.map((name) => {
      const guessed = data.guessed_dtypes[name] || "text";
      const guessedFmt = (data.guessed_date_formats || {})[name] || DEFAULT_DATE_FORMAT;
      const old = prevByName.get(name);
      if (old && isFtColEdited(old)) return { name, guessed, guessedFmt, dtype: old.dtype, dateFormat: old.dateFormat };
      return { name, guessed, guessedFmt, dtype: guessed, dateFormat: guessedFmt };
    });
    st.colState = "ready";
    if (st.countsSig !== src.sig) st.colCounts = null; // số ô sai chỉ còn đúng nếu đầu vào vẫn là kết quả của lần Chạy đó
    renderFtColTypes();
  })();
  await st.colPromise;
}
function ftColRowHTML(c, i, counts) {
  const n = counts[c.name] || 0;
  const opts = FORMAT_DTYPE_OPTIONS.map(([v, l]) => `<option value="${v}"${v === c.dtype ? " selected" : ""}>${l}</option>`).join("");
  return `<div class="ft-coltype-row${isFtColEdited(c) ? " is-edited" : ""}${n ? " has-errors" : ""}" data-i="${i}">` +
    `<span class="ft-coltype-name" title="${escapeAttr(c.name)}">${escapeHtml(c.name)}</span>` +
    `<select class="select ft-coltype-select" data-role="dtype" title="Denoise đoán: ${escapeAttr(FORMAT_DTYPE_LABEL[c.guessed] || c.guessed)}">${opts}</select>` +
    `<input class="input mono ft-coltype-fmt" data-role="fmt" value="${escapeAttr(c.dateFormat)}" placeholder="${DEFAULT_DATE_FORMAT}" title="Khuôn ngày (chuẩn strptime)"${c.dtype === "date" ? "" : " hidden"} />` +
    `<span class="ft-coltype-count">${n ? `${n} ô sai` : ""}</span></div>`;
}
function renderFtColTypes() {
  const box = $("ft-coltypes");
  const st = state.ft;
  if (st.colState === "loading") { box.innerHTML = '<p class="ft-coltypes-msg">Đang đọc cột và đoán kiểu dữ liệu…</p>'; return; }
  if (st.colState === "error") { box.innerHTML = `<p class="ft-coltypes-msg is-error">${escapeHtml(st.colError || "Không đọc được cột.")}</p>`; return; }
  if (!st.colTypes) { box.innerHTML = '<p class="ft-coltypes-msg">Chọn file hoặc dán dữ liệu để xem kiểu từng cột.</p>'; return; }
  const counts = st.colCounts || {};
  box.innerHTML =
    `<div class="ft-coltypes-bar"><span class="ft-coltypes-title">Kiểu dữ liệu từng cột</span><span class="ft-coltypes-meta">${st.colTypes.length} cột</span>` +
    '<button type="button" class="btn btn-ghost btn-small" data-role="reset">↺ Về kiểu tự đoán</button></div>' +
    '<p class="ft-coltypes-hint">Kiểu do Denoise đoán, sai thì chọn lại. Cột Nhóm và Văn bản không bị kiểm tra.</p>' +
    `<div class="ft-coltypes-list">${st.colTypes.map((c, i) => ftColRowHTML(c, i, counts)).join("")}</div>`;
}
// Người dùng sửa 1 cột: cập nhật trạng thái + đánh dấu "đã sửa"; số ô sai cũ không còn đúng nên xoá.
function afterFtColEdit(row, c) {
  row.classList.toggle("is-edited", isFtColEdited(c));
  state.ft.colCounts = null;
  document.querySelectorAll("#ft-coltypes .ft-coltype-row").forEach((r) => {
    r.classList.remove("has-errors");
    r.querySelector(".ft-coltype-count").textContent = "";
  });
}
$("ft-coltypes").addEventListener("change", (e) => {
  const row = e.target.closest(".ft-coltype-row");
  if (!row || e.target.dataset.role !== "dtype") return;
  const c = state.ft.colTypes[Number(row.dataset.i)];
  c.dtype = e.target.value;
  if (!c.dateFormat) c.dateFormat = DEFAULT_DATE_FORMAT;
  row.querySelector('[data-role="fmt"]').hidden = c.dtype !== "date";
  afterFtColEdit(row, c);
});
$("ft-coltypes").addEventListener("input", (e) => {
  const row = e.target.closest(".ft-coltype-row");
  if (!row || e.target.dataset.role !== "fmt") return;
  const c = state.ft.colTypes[Number(row.dataset.i)];
  c.dateFormat = e.target.value;
  afterFtColEdit(row, c);
});
$("ft-coltypes").addEventListener("click", (e) => {
  if (!e.target.closest('[data-role="reset"]') || !state.ft.colTypes) return;
  state.ft.colTypes.forEach((c) => { c.dtype = c.guessed; c.dateFormat = c.guessedFmt; });
  state.ft.colCounts = null;
  renderFtColTypes();
});
/* ----- Ô trống: bảng "Ô TRỐNG TỪNG CỘT" dưới bảng đầu vào -----
   Tool này GỘP 3 tool cũ (Xoá dòng trống + Điền ô trống + Thiếu giá trị nâng cao). Cùng cách làm với bảng kiểu cột của
   tool Sai định dạng (đọc qua /api/noise-tools/inspect), khác ở chỗ:
   - chỉ liệt kê cột CÓ ô trống (backend trả blank_counts khi gửi include_blanks=true);
   - mỗi cột có 3 ô: kiểu (đoán sẵn, sửa được -> quyết định cách điền nào hợp lệ), cách xử lý (mặc định "Giữ nguyên"),
     giá trị cố định (chỉ hiện khi chọn "Điền giá trị cố định");
   - cột để "Giữ nguyên" không bị đụng tới, nên chỉ chọn file rồi bấm Chạy = chỉ xoá dòng trống hoàn toàn
     (đúng như tool "Xoá dòng trống" cũ); 2 ô tick bên dưới bảng là cài đặt chung cho cả file. */
const BLANK_DTYPE_OPTIONS = [
  ["integer", "Số nguyên"], ["float", "Số thực"], ["category", "Nhóm"], ["text", "Văn bản"],
  ["email", "Email"], ["phone", "Số điện thoại"], ["date", "Ngày tháng"],
];
const BLANK_DTYPE_LABEL = Object.fromEntries(BLANK_DTYPE_OPTIONS);
const BLANK_ACTION_LABELS = {
  keep: "Giữ nguyên",
  fill_down: "Điền từ ô phía trên",
  fixed_value: "Điền tay từng ô",
  impute_mean: "Điền trung bình",
  impute_median: "Điền trung vị",
  impute_knn: "Điền theo KNN",
  impute_mode: "Điền giá trị phổ biến nhất",
  remove_row: "Xoá cả dòng",
};
// Chữ gợi ý mặc định của 2 ô tick (HTML tĩnh) -- giữ lại để khôi phục khi chưa có đầu vào.
const BLANK_ROWS_HINT_DEFAULT = $("opt-blank-rows-hint").textContent;
const BLANK_COLS_HINT_DEFAULT = $("opt-blank-cols-hint").textContent;

// Cách xử lý hợp lệ cho 1 kiểu cột (danh sách do backend trả, giao diện không tự định nghĩa lại).
function blankActionsFor(dtype) {
  const info = state.ft.blankInfo;
  return (info && info.blank_actions && info.blank_actions[dtype]) || ["keep"];
}
function blankActionOptionsHTML(c) {
  return blankActionsFor(c.dtype).map((a) => `<option value="${a}"${a === c.action ? " selected" : ""}>${BLANK_ACTION_LABELS[a] || a}</option>`).join("");
}
// Ghi số dòng / cột trống hoàn toàn của đầu vào vào chữ gợi ý dưới 2 ô tick.
function updateBlankHints() {
  const info = state.ft.blankInfo;
  const rowsHint = $("opt-blank-rows-hint");
  const colsHint = $("opt-blank-cols-hint");
  if (!info) {
    rowsHint.textContent = BLANK_ROWS_HINT_DEFAULT;
    colsHint.textContent = BLANK_COLS_HINT_DEFAULT;
    return;
  }
  rowsHint.textContent = info.empty_row_count > 0
    ? `Đầu vào có ${info.empty_row_count} dòng trống hoàn toàn (mọi cột đều trống, kể cả "NA", "-", "?").`
    : "Đầu vào không có dòng nào trống hoàn toàn.";
  const cols = info.empty_columns;
  colsHint.textContent = cols.length > 0
    ? `Đầu vào có ${cols.length} cột trống hoàn toàn: ${cols.slice(0, 5).join(", ")}${cols.length > 5 ? ` và ${cols.length - 5} cột khác` : ""}.`
    : "Đầu vào không có cột nào trống hoàn toàn.";
}
// Đọc lại cột nếu đầu vào đã đổi. Chỉ chạy khi đang ở tool Ô trống; cùng đầu vào thì giữ nguyên bảng (và các lựa chọn).
async function refreshFtBlankColumns() {
  const st = state.ft;
  if (st.tool !== "blanks") return;
  const src = ftInputSource();
  if (!src) {
    st.blankSig = "";
    st.blankCols = null;
    st.blankInfo = null;
    st.blankState = "idle";
    resetBlankManual();
    updateBlankHints();
    renderFtBlanks();
    return;
  }
  if (src.sig === st.blankSig) return;
  st.blankSig = src.sig;
  const seq = ++st.blankSeq;
  const prev = st.blankCols;
  // Nối tiếp từ bước trước thì giữ bảng cũ trong lúc đọc lại cho đỡ nháy.
  if (!(src.pipe && prev)) {
    st.blankCols = null;
    st.blankInfo = null;
    st.blankState = "loading";
    resetBlankManual();
    updateBlankHints();
    renderFtBlanks();
  }
  const fd = new FormData();
  if (src.file) fd.append("file", src.file);
  else fd.append("text", src.text);
  fd.append("include_blanks", "true");
  st.blankPromise = (async () => {
    let response, data;
    try {
      response = await fetch("/api/noise-tools/inspect", { method: "POST", body: fd });
      data = await response.json();
    } catch (err) {
      if (seq === st.blankSeq) { st.blankSig = ""; st.blankCols = null; st.blankInfo = null; st.blankState = "error"; st.blankError = "Không gọi được backend để đọc cột."; updateBlankHints(); renderFtBlanks(); }
      return;
    }
    if (seq !== st.blankSeq) return; // đã có lần đọc mới hơn
    if (!response.ok) { st.blankSig = ""; st.blankCols = null; st.blankInfo = null; st.blankState = "error"; st.blankError = data.error || "Không đọc được nội dung."; updateBlankHints(); renderFtBlanks(); return; }
    st.blankInfo = { empty_row_count: data.empty_row_count || 0, empty_columns: data.empty_columns || [], blank_actions: data.blank_actions || {} };
    const counts = data.blank_counts || {};
    // Chuỗi nối tiếp: cột nào người dùng đã sửa kiểu thì giữ lựa chọn đó (tìm theo tên cột). Cách xử lý thì luôn về
    // "Giữ nguyên": ô trống đã được xử lý ở bước trước rồi, bảng chỉ còn liệt kê những cột còn ô trống.
    const prevByName = new Map((src.pipe && prev ? prev : []).map((c) => [c.name, c]));
    st.blankCols = data.columns.filter((name) => counts[name] > 0).map((name) => {
      const guessed = data.guessed_dtypes[name] || "text";
      const old = prevByName.get(name);
      const dtype = old && old.dtype !== old.guessed && st.blankInfo.blank_actions[old.dtype] ? old.dtype : guessed;
      return { name, blanks: counts[name], guessed, dtype, action: "keep", fixedValue: "", cellValues: {} };
    });
    resetBlankManual(); // bảng mới -> các dòng đã tải và lựa chọn mở bảng của đầu vào cũ không còn đúng
    st.blankState = "ready";
    updateBlankHints();
    renderFtBlanks();
  })();
  await st.blankPromise;
}
function ftBlankRowHTML(c, i) {
  const dtypeOpts = BLANK_DTYPE_OPTIONS.map(([v, l]) => `<option value="${v}"${v === c.dtype ? " selected" : ""}>${l}</option>`).join("");
  // Cột trống hoàn toàn: ghi chú xuống DÒNG RIÊNG (không nối vào "N ô trống") để chữ dài không làm tên cột bị cắt.
  const whole = state.ft.blankInfo.empty_columns.includes(c.name) ? '<span class="ft-blank-whole">cột trống hoàn toàn</span>' : "";
  return `<div class="ft-coltype-row ft-blank-row${c.action !== "keep" ? " is-edited" : ""}" data-i="${i}">` +
    `<span class="ft-blank-name" title="${escapeAttr(c.name)}"><span class="ft-coltype-name">${escapeHtml(c.name)}</span><span class="ft-blank-count">${c.blanks} ô trống</span>${whole}</span>` +
    `<select class="select ft-blank-dtype" data-role="dtype" title="Denoise đoán: ${escapeAttr(BLANK_DTYPE_LABEL[c.guessed] || c.guessed)}">${dtypeOpts}</select>` +
    `<select class="select ft-blank-action" data-role="action">${blankActionOptionsHTML(c)}</select>` +
    `<button type="button" class="btn btn-ghost ft-blank-fixed ft-blank-manual-btn${state.ft.blankEditing === c.name ? " is-open" : ""}" data-role="manual-open"${c.action === "fixed_value" ? "" : " hidden"}>${escapeHtml(blankManualBtnText(c))}</button>` +
    "</div>";
}
function renderFtBlanks() {
  renderFtBlanksList();
  renderBlankManual();
}
function renderFtBlanksList() {
  const box = $("ft-blanks");
  const st = state.ft;
  if (st.blankState === "loading") { box.innerHTML = '<p class="ft-coltypes-msg">Đang đọc cột và đếm ô trống…</p>'; return; }
  if (st.blankState === "error") { box.innerHTML = `<p class="ft-coltypes-msg is-error">${escapeHtml(st.blankError || "Không đọc được cột.")}</p>`; return; }
  if (!st.blankCols) { box.innerHTML = '<p class="ft-coltypes-msg">Chọn file hoặc dán dữ liệu để xem các cột có ô trống.</p>'; return; }
  box.innerHTML =
    `<div class="ft-coltypes-bar"><span class="ft-coltypes-title">Ô trống từng cột</span><span class="ft-coltypes-meta">${st.blankCols.length} cột có ô trống</span>` +
    '<button type="button" class="btn btn-ghost btn-small" data-role="reset">↺ Đặt lại</button></div>' +
    '<p class="ft-coltypes-hint">Chỉ liệt kê cột có ô trống. Cột để "Giữ nguyên" không bị đụng tới.</p>' +
    (st.blankCols.length
      ? `<div class="ft-coltypes-list">${st.blankCols.map((c, i) => ftBlankRowHTML(c, i)).join("")}</div>`
      : '<p class="ft-coltypes-msg">Không có cột nào có ô trống.</p>');
}
// Đồng bộ 1 dòng với state sau khi người dùng đổi kiểu / cách xử lý (cập nhật tại chỗ, không dựng lại cả bảng).
function syncBlankRow(row, c) {
  const sel = row.querySelector('[data-role="action"]');
  sel.innerHTML = blankActionOptionsHTML(c);
  sel.value = c.action;
  const btn = row.querySelector('[data-role="manual-open"]');
  btn.hidden = c.action !== "fixed_value";
  btn.textContent = blankManualBtnText(c);
  row.classList.toggle("is-edited", c.action !== "keep");
}
$("ft-blanks").addEventListener("change", (e) => {
  const row = e.target.closest(".ft-blank-row");
  if (!row || !state.ft.blankCols) return;
  const c = state.ft.blankCols[Number(row.dataset.i)];
  const role = e.target.dataset.role;
  if (role === "dtype") {
    c.dtype = e.target.value;
    // Cách xử lý đang chọn không còn hợp lệ với kiểu mới (vd "Điền trung bình" rồi đổi sang Văn bản) -> về "Giữ nguyên".
    if (!blankActionsFor(c.dtype).includes(c.action)) c.action = "keep";
    syncBlankRow(row, c);
    renderBlankManual(); // cột đang mở bảng điền tay mà không còn cách "Điền tay" -> bảng tự ẩn
  } else if (role === "action") {
    c.action = e.target.value;
    syncBlankRow(row, c);
    if (c.action === "fixed_value") openBlankManual(c);        // chọn "Điền tay từng ô" -> mở luôn bảng các dòng có ô trống
    else if (state.ft.blankEditing === c.name) closeBlankManual();
  }
});
$("ft-blanks").addEventListener("click", (e) => {
  const st = state.ft;
  if (!st.blankCols) return;
  if (e.target.closest('[data-role="reset"]')) {
    st.blankCols.forEach((c) => { c.dtype = c.guessed; c.action = "keep"; c.fixedValue = ""; c.cellValues = {}; });
    st.blankEditing = null;
    renderFtBlanks();
    return;
  }
  const btn = e.target.closest('[data-role="manual-open"]');
  if (!btn) return;
  const c = st.blankCols[Number(btn.closest(".ft-blank-row").dataset.i)];
  if (st.blankEditing === c.name) closeBlankManual();
  else openBlankManual(c);
});

/* ----- Bảng "Điền tay từng ô" -----
   Chọn cách "Điền tay từng ô" cho 1 cột (hoặc bấm nút "✎ Điền tay" trong dòng) -> bên dưới danh sách cột hiện bảng các DÒNG có
   ô trống ở cột đó (đủ mọi cột để nhìn ngữ cảnh; cột cần điền đứng ngay sau "Dòng" để luôn thấy dù bảng cuộn ngang). Gõ giá
   trị vào từng ô. Ô nào để trống thì lấy "Giá trị chung" (nếu có), không thì giữ trống. Chỉ hiện 100 dòng đầu mỗi cột (backend
   cắt); phần còn lại dùng giá trị chung. Giá trị gõ lưu ở c.cellValues {số dòng gốc: giá trị} và gửi lên khi bấm Chạy. */
function manualFilledCount(c) {
  return Object.values(c.cellValues).filter((v) => String(v).trim()).length;
}
// Tổng số ô trống của cột sẽ hiện trong bảng (đã trừ dòng trống hoàn toàn nếu đã tải xong; chưa tải thì dùng số ô trống thô).
function manualTotal(c) {
  const entry = state.ft.blankRowsCache[c.name];
  return entry && entry.state === "ready" ? entry.data.total_blank_rows : c.blanks;
}
function blankManualBtnText(c) {
  const common = String(c.fixedValue).trim() ? " + giá trị chung" : "";
  return `✎ Điền tay · đã điền ${manualFilledCount(c)}/${manualTotal(c)} ô${common}`;
}
function resetBlankManual() {
  state.ft.blankEditing = null;
  state.ft.blankRowsCache = {};
  state.ft.blankErrors = {};
}
function editingBlankCol() {
  const st = state.ft;
  return st.blankEditing && st.blankCols ? st.blankCols.find((x) => x.name === st.blankEditing && x.action === "fixed_value") || null : null;
}
// Cập nhật chữ của nút trong dòng và dòng đếm trên thanh tiêu đề bảng (không dựng lại bảng, để không mất con trỏ đang gõ).
function updateBlankManualCounts(c) {
  const i = state.ft.blankCols.indexOf(c);
  const btn = document.querySelector(`#ft-blanks .ft-blank-row[data-i="${i}"] [data-role="manual-open"]`);
  if (btn) btn.textContent = blankManualBtnText(c);
  const meta = document.querySelector('#ft-blank-manual [data-role="manual-count"]');
  if (meta && state.ft.blankEditing === c.name) meta.textContent = `${manualFilledCount(c)}/${manualTotal(c)} ô đã điền tay`;
}
// Nút của cột đang mở bảng thì tô viền (.is-open).
function refreshBlankManualButtons() {
  document.querySelectorAll("#ft-blanks .ft-blank-row").forEach((row) => {
    const c = state.ft.blankCols[Number(row.dataset.i)];
    const btn = row.querySelector('[data-role="manual-open"]');
    if (btn) btn.classList.toggle("is-open", state.ft.blankEditing === c.name);
  });
}
function openBlankManual(c) {
  state.ft.blankEditing = c.name;
  loadBlankRows(c.name);
  // Danh sách cột cao tối đa 300px và tự cuộn: cuộn trong danh sách cho dòng vừa chọn hiện đủ (không cuộn cả trang).
  const list = document.querySelector("#ft-blanks .ft-coltypes-list");
  const rowEl = list && list.querySelector(`.ft-blank-row[data-i="${state.ft.blankCols.indexOf(c)}"]`);
  if (rowEl) {
    const lr = list.getBoundingClientRect(), rr = rowEl.getBoundingClientRect();
    if (rr.bottom > lr.bottom) list.scrollTop += rr.bottom - lr.bottom;
    else if (rr.top < lr.top) list.scrollTop -= lr.top - rr.top;
  }
  refreshBlankManualButtons();
  renderBlankManual(true);
  $("ft-blank-manual").scrollIntoView({ block: "nearest", behavior: "smooth" });
}
function closeBlankManual() {
  state.ft.blankEditing = null;
  refreshBlankManualButtons();
  renderBlankManual();
}
// Lấy từ backend các dòng có ô trống ở cột `name` (1 lần cho mỗi cột / mỗi đầu vào, kết quả nhớ trong blankRowsCache).
async function loadBlankRows(name) {
  const st = state.ft;
  const cache = st.blankRowsCache;
  if (cache[name]) return;
  const src = ftInputSource();
  if (!src) return;
  cache[name] = { state: "loading" };
  st.blankErrors[name] = "";
  const fd = new FormData();
  if (src.file) fd.append("file", src.file);
  else fd.append("text", src.text);
  fd.append("column", name);
  let entry;
  try {
    const response = await fetch("/api/noise-tools/blank-rows", { method: "POST", body: fd });
    const data = await response.json();
    entry = response.ok ? { state: "ready", data } : { state: "error", error: data.error || "Không lấy được các dòng có ô trống." };
  } catch (err) {
    entry = { state: "error", error: "Không gọi được backend để lấy các dòng có ô trống." };
  }
  if (st.blankRowsCache !== cache) return; // đầu vào đã đổi trong lúc chờ: bỏ kết quả cũ
  if (entry.state === "error") { delete cache[name]; st.blankErrors[name] = entry.error; } // lỗi thì cho thử lại lần mở sau
  else cache[name] = entry;
  const c = editingBlankCol();
  if (c && c.name === name) renderBlankManual(true);
  const col = st.blankCols && st.blankCols.find((x) => x.name === name);
  if (col) updateBlankManualCounts(col);
}
function manualTableHTML(c, d) {
  const others = d.columns.map((_, i) => i).filter((i) => i !== d.column_index);
  const head = `<tr><th>Dòng</th><th class="is-target">${escapeHtml(c.name)}</th>${others.map((i) => `<th>${escapeHtml(d.columns[i])}</th>`).join("")}</tr>`;
  const body = d.rows.map((r, k) => {
    const n = d.row_numbers[k];
    const cells = others.map((i) => `<td title="${escapeAttr(r[i])}">${escapeHtml(r[i])}</td>`).join("");
    return `<tr><td class="ft-manual-num">${n}</td><td class="is-target"><input class="input ft-manual-input" data-row="${n}" value="${escapeAttr(c.cellValues[n] || "")}" placeholder="điền…" aria-label="Giá trị cho dòng ${n}, cột ${escapeAttr(c.name)}" /></td>${cells}</tr>`;
  }).join("");
  return `<div class="table-wrap ft-manual-wrap"><table class="results-table ft-manual-table"><thead>${head}</thead><tbody>${body}</tbody></table></div>`;
}
function renderBlankManual(focusFirst) {
  const box = $("ft-blank-manual");
  const c = editingBlankCol();
  if (!c) { box.hidden = true; box.innerHTML = ""; return; }
  box.hidden = false;
  const entry = state.ft.blankRowsCache[c.name];
  const err = state.ft.blankErrors[c.name];
  let inner;
  if (!entry && err) inner = `<p class="ft-coltypes-msg is-error">${escapeHtml(err)}</p>`;
  else if (!entry || entry.state === "loading") inner = '<p class="ft-coltypes-msg">Đang lấy các dòng có ô trống…</p>';
  else {
    const d = entry.data;
    const notes = [];
    if (d.shown_count < d.total_blank_rows) notes.push(`Cột này có ${d.total_blank_rows} ô trống, hiện ${d.shown_count} dòng đầu. Ô không điền lấy giá trị chung bên dưới, không có thì giữ trống.`);
    else notes.push("Gõ giá trị vào từng ô được tô nền. Ô để trống lấy giá trị chung bên dưới, không có thì giữ trống.");
    if (d.excluded_empty_rows > 0) notes.push(`${d.excluded_empty_rows} dòng trống hoàn toàn không được liệt kê.`);
    inner = d.total_blank_rows === 0
      ? '<p class="ft-coltypes-msg">Cột này không có dòng nào cần điền tay (chỉ còn các dòng trống hoàn toàn).</p>'
      : `<p class="ft-coltypes-hint">${escapeHtml(notes.join(" "))}</p>` +
        '<div class="ft-manual-general"><label for="ft-manual-general-input">Giá trị chung</label>' +
        `<input class="input" id="ft-manual-general-input" data-role="general" value="${escapeAttr(c.fixedValue)}" placeholder="vd 0 hoặc Chưa rõ" /></div>` +
        manualTableHTML(c, d);
  }
  box.innerHTML =
    `<div class="ft-coltypes-bar"><span class="ft-coltypes-title">Điền tay · ${escapeHtml(c.name)}</span>` +
    `<span class="ft-coltypes-meta" data-role="manual-count">${manualFilledCount(c)}/${manualTotal(c)} ô đã điền tay</span>` +
    '<button type="button" class="btn btn-ghost btn-small" data-role="manual-close">Đóng</button></div>' + inner;
  if (focusFirst) {
    const first = [...box.querySelectorAll(".ft-manual-input")].find((i) => !i.value) || box.querySelector(".ft-manual-input");
    if (first) first.focus({ preventScroll: true });
  }
}
$("ft-blank-manual").addEventListener("input", (e) => {
  const c = editingBlankCol();
  if (!c) return;
  if (e.target.classList.contains("ft-manual-input")) c.cellValues[e.target.dataset.row] = e.target.value;
  else if (e.target.dataset.role === "general") c.fixedValue = e.target.value;
  else return;
  updateBlankManualCounts(c);
});
$("ft-blank-manual").addEventListener("click", (e) => {
  if (e.target.closest('[data-role="manual-close"]')) closeBlankManual();
});
// Enter trong 1 ô -> nhảy xuống ô kế tiếp (dòng cuối thì ở nguyên), để gõ liền một mạch.
$("ft-blank-manual").addEventListener("keydown", (e) => {
  if (e.key !== "Enter" || !e.target.classList.contains("ft-manual-input")) return;
  e.preventDefault();
  const inputs = [...$("ft-blank-manual").querySelectorAll(".ft-manual-input")];
  const next = inputs[inputs.indexOf(e.target) + 1];
  if (next) next.focus();
});

// Hai tool Free Tools có bảng cột (Sai định dạng, Ô trống) đều đọc cột qua /api/noise-tools/inspect; mỗi hàm tự bỏ qua nếu
// tool đang mở không phải của nó. Gọi mỗi khi chọn file / gõ text / đổi tab / đầu vào nối tiếp đổi.
function refreshFtColumns() {
  refreshFtColumnTypes();
  refreshFtBlankColumns();
}
// Dán text: đọc cột sau khi người dùng ngừng gõ ~600ms.
let ftPasteTimer = null;
$("ft-paste-input").addEventListener("input", () => {
  clearTimeout(ftPasteTimer);
  ftPasteTimer = setTimeout(refreshFtColumns, 600);
});

// Bảng dữ liệu (khung 01) có thể nằm cách nút "Xem ..." cả nghìn px -- nhất là tool Sai định dạng, vì giữa bảng và nút còn có
// bảng kiểu dữ liệu từng cột. Bấm nút xong mà bảng nằm ngoài tầm nhìn thì người dùng không thấy gì đổi. Nên sau mỗi lần đổi
// giữa "đầu vào" ⇄ "danh sách", đưa bảng vào GIỮA màn hình (chỉ cuộn khi bảng chưa thấy trọn vẹn dưới thanh header dính).
function revealFtInputCard() {
  requestAnimationFrame(() => {
    const card = $("ft-raw-preview");
    const headerH = document.querySelector(".ws-header").offsetHeight;
    const r = card.getBoundingClientRect();
    if (r.top >= headerH && r.bottom <= window.innerHeight) return;
    card.scrollIntoView({ behavior: "smooth", block: "center" });
  });
}
$("ft-view-btn").addEventListener("click", () => {
  const v = state.ft.listView;
  if (!v || LIST_VIEW[v.kind].count(v.data) === 0) return;
  v.showing = !v.showing;
  renderInputArea("ft");
  renderListButton();
  revealFtInputCard();
});

// Gọi backend + khoá nút trong lúc chờ + báo lỗi inline. Trả data hoặc null.
async function callBackend(btn, idleText, url, formData, errorEl) {
  btn.disabled = true;
  const prev = btn.textContent;
  btn.textContent = "Đang chạy...";
  let response, data;
  try {
    response = await fetch(url, { method: "POST", body: formData });
    data = await response.json();
  } catch (err) {
    btn.disabled = false;
    btn.textContent = idleText || prev;
    setError(errorEl, "Không gọi được backend. Kiểm tra xem python3 app.py có đang chạy không.");
    return null;
  }
  btn.disabled = false;
  btn.textContent = idleText || prev;
  if (!response.ok) {
    setError(errorEl, data.error || "Xử lý thất bại.");
    return null;
  }
  return data;
}

/* ============================================================
   CONVERT -- tuỳ chọn tĩnh + bấm Convert (kết quả JSON thì ghi chú "json"
   vào chuỗi nối tiếp, chỉ JSON → CSV nhận tiếp được)
   ============================================================ */
$("convert-run-btn").addEventListener("click", async () => {
  const T = TOOLSEC.cv;
  setError($(T.error), "");
  const formData = new FormData();
  const fresh = !pipeUsable("cv");
  const inp = collectInput("cv", formData);
  if (inp.error) return setError($(T.error), inp.error);
  const tool = state.cv.tool;
  let url;
  if (tool === "delimiter") {
    url = "/api/convert/delimiter";
    formData.append("from_delimiter", $("opt-from-delim").value);
    formData.append("to_delimiter", $("opt-to-delim").value);
  } else if (tool === "csv-to-json") {
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
  const data = await callBackend($("convert-run-btn"), "Chuyển đổi", url, formData, $(T.error));
  if (!data) return;
  state.cv.lastResult = data;
  $(T.resultEmpty).hidden = true;
  $(T.download).disabled = false;
  if (tool === "csv-to-json") {
    $(T.resultCard).hidden = true;
    $("convert-json-card").hidden = false;
    $("convert-json-dims").textContent = `${data.record_count} record`;
    $("convert-result-text").textContent = data.result_text;
    setStatus($(T.status), `✅ ${data.record_count} record (dấu phân cách: ${delimiterLabel(data.used_delimiter)})`, "is-ok");
    recordPipeStep(CV_TAB_LABEL[tool], data.result_text, "json", inp.label, fresh, inp.source);
  } else {
    $("convert-json-card").hidden = true;
    const colCount = data.preview_rows && data.preview_rows.length ? data.preview_rows[0].length : 0;
    // row_count của backend đếm CẢ dòng tiêu đề -> số dòng dữ liệu = row_count - 1.
    const dataRows = Math.max(0, data.row_count - 1);
    showResultTable("cv", CV_TAB_LABEL[tool], data.preview_rows, tableDims(dataRows, colCount));
    setStatus($(T.status), tool === "delimiter"
      ? `✅ ${dataRows} dòng dữ liệu · đã nhận diện dấu phân cách gốc: ${delimiterLabel(data.used_from_delimiter)}`
      : `✅ ${dataRows} dòng dữ liệu · ${data.columns.length} cột`, "is-ok");
    recordPipeStep(CV_TAB_LABEL[tool], data.result_text, "csv", inp.label, fresh, inp.source);
  }
  renderContinuePanel("cv");
});

/* ============================================================
   CẦN CẤU HÌNH -- đọc cột từ backend, dựng tuỳ chọn theo tool, 2 nhịp
   Phát hiện -> Áp dụng (POST /api/noise-tools/configured, mode=detect|apply)
   ============================================================ */
// Đọc tên cột + kiểu đoán sẵn (+ xem trước) từ backend cho file/text hiện tại.
async function cfInspect(source, label, opts) {
  opts = opts || {};
  // sig = "chữ ký" của đầu vào hiện tại (xem cfInputSource). Chỉ lần gọi MỚI NHẤT (seq) được ghi kết quả; thành công thì
  // state.cf.colSig nhớ các cột đang hiện được đọc từ đầu vào nào, để refreshCfColumns() biết khi nào cần đọc lại.
  const seq = ++state.cf.colSeq;
  const sig = (cfInputSource() || {}).sig || "";
  state.cf.pendingSig = sig;
  const fd = new FormData();
  if (source.file) fd.append("file", source.file);
  else fd.append("text", source.text || "");
  fd.append("include_values", "true"); // kèm danh sách giá trị của cột Nhóm cho "chip giá trị" của ô Biểu thức
  let response, data;
  try {
    response = await fetch("/api/noise-tools/inspect", { method: "POST", body: fd });
    data = await response.json();
  } catch (err) {
    if (seq === state.cf.colSeq) {
      state.cf.pendingSig = "";
      setError($("cf-error"), "Không gọi được backend để đọc cột.");
    }
    return;
  }
  if (seq !== state.cf.colSeq) return; // đã có lần đọc mới hơn
  state.cf.pendingSig = "";
  if (!response.ok) {
    state.cf.colSig = "";
    state.cf.columns = [];
    state.cf.guessed = {};
    state.cf.columnValues = {};
    state.cf.valueCol = "";
    renderCfOptions();
    if (source.file) showRawPreview("cf", label, `${(source.file.size / 1024).toFixed(1)} KB`, null, data.error || "Không đọc được file.");
    else setError($("cf-error"), data.error || "Không đọc được nội dung.");
    return;
  }
  state.cf.colSig = sig;
  state.cf.columns = data.columns;
  state.cf.guessed = data.guessed_dtypes || {};
  state.cf.columnValues = data.column_values || {};
  if (!state.cf.columnValues[state.cf.valueCol]) state.cf.valueCol = ""; // cột đang hiện giá trị không còn (đầu vào mới) thì ẩn
  renderCfOptions();
  cfCheckStale(); // đọc xong cột của đầu vào mới: nếu khác lần Phát hiện cuối thì báo
  if (source.file && !opts.keepPreview) {
    showRawPreview("cf", label, tableDims(data.row_count, data.columns.length), data.preview_rows, "");
  }
}
// Đầu vào hiện tại của khối Cần cấu hình, cùng thứ tự ưu tiên với collectInput(): kết quả bước trước > file > text dán.
// sig = "chữ ký" đầu vào (đổi khi đầu vào đổi); pipe = true nếu đang nối tiếp từ bước trước.
function cfInputSource() {
  const st = state.cf;
  const p = state.pipe;
  if (pipeUsable("cf")) return { text: p.currentText, pipe: true, label: p.originalLabel, sig: `pipe:${p.steps.length}:${p.currentText.length}:${hashText(p.currentText)}` };
  if (st.inputMode === "file") {
    const f = st.selectedFile;
    return f ? { file: f, pipe: false, label: f.name, sig: `file:${f.name}:${f.size}:${f.lastModified}` } : null;
  }
  const text = $("cf-paste-input").value;
  return text.trim() ? { text, pipe: false, label: "văn bản dán tay", sig: `text:${text.length}:${hashText(text)}` } : null;
}
// Bảo đảm danh sách cột của Cần cấu hình KHỚP đầu vào đang hiện ở khung 01. Gọi mỗi khi vào khối và mỗi khi chuỗi nối tiếp đổi.
// Lỗi cũ nó sửa: vào Cần cấu hình bằng menu Product / chân trang (không qua bảng "Xử lý tiếp bằng") lúc đang có chuỗi thì
// khung 01 hiện dữ liệu của chuỗi nhưng ô chọn cột rỗng, hoặc còn cột của file cũ.
function refreshCfColumns() {
  if (state.section !== "config") return;
  const src = cfInputSource();
  if (!src) {
    // Không còn đầu vào nào (vd bấm "Tải file khác") -> không để lại cột của đầu vào cũ.
    if (state.cf.colSig) {
      state.cf.colSig = "";
      state.cf.columns = [];
      state.cf.guessed = {};
      state.cf.columnValues = {};
      state.cf.valueCol = "";
      renderCfOptions();
      cfCheckStale();
    }
    return;
  }
  if (src.sig === state.cf.colSig || src.sig === state.cf.pendingSig) return;
  cfInspect(src.file ? { file: src.file } : { text: src.text }, src.label, { keepPreview: !!src.pipe });
}
// Dán text: đọc cột sau khi người dùng ngừng gõ ~600ms.
let cfPasteTimer = null;
$("cf-paste-input").addEventListener("input", () => {
  clearTimeout(cfPasteTimer);
  cfPasteTimer = setTimeout(() => {
    const text = $("cf-paste-input").value;
    if (text.trim()) cfInspect({ text }, "văn bản dán tay");
  }, 600);
});

function cfColumnSelect(id, labelText, selected) {
  const cols = state.cf.columns;
  const opts = cols.length
    ? cols.map((c) => `<option value="${escapeAttr(c)}"${c === selected ? " selected" : ""}>${escapeHtml(c)}</option>`).join("")
    : '<option value="">(chọn file hoặc dán text trước)</option>';
  return `<div class="field"><label for="${id}">${labelText}</label><select class="select" id="${id}">${opts}</select></div>`;
}
// Kiểu mặc định cho 1 cột = kiểu backend đoán nếu tool cho phép, không thì kiểu đầu danh sách.
function cfDefaultDtype(column, allowed) {
  const guessed = state.cf.guessed[column];
  return allowed.includes(guessed) ? guessed : allowed[0];
}
// 2 kiểu rule liên cột trong giao diện Denoise. "Biểu thức" gộp So sánh + Công thức + Nếu–thì cũ (nếu–thì = toán tử kéo theo `=>`, có nút THÌ =>).
// Backend vẫn giữ compare/formula/conditional/if_then cho giao diện cũ.
const RULE_TYPES = [["expression", "Biểu thức"], ["functional_dependency", "Phụ thuộc hàm"]];
function renderCfOptions() {
  const tool = state.cf.tool;
  const wrap = $("cf-options");
  if (tool === "cross-rule") {
    // Kiểu rule giữ nguyên khi dựng lại form (đổi file, đọc lại cột): đỡ bị đưa về "Biểu thức" mỗi lần.
    const current = RULE_TYPES.some(([v]) => v === state.cf.ruleType) ? state.cf.ruleType : "expression";
    wrap.innerHTML = `
      <div class="field">
        <label>Kiểu quy tắc</label>
        <div class="ft-seg" data-seg-for="cf-rule-type">
          ${RULE_TYPES.map(([v, l]) => `<button type="button" class="${v === current ? "is-active" : ""}" data-value="${v}">${l}</button>`).join("")}
        </div>
        <select class="select" id="cf-rule-type" hidden>
          ${RULE_TYPES.map(([v, l]) => `<option value="${v}"${v === current ? " selected" : ""}>${l}</option>`).join("")}
        </select>
      </div>
      <div id="cf-rule-fields"></div>`;
    wireSegmented(wrap.querySelector(".ft-seg"));
    $("cf-rule-type").addEventListener("change", renderCfRuleFields);
    renderCfRuleFields();
    return;
  }
  if (CF_MULTI[tool]) {
    renderCfMultiForms(); // tool kiểm NHIỀU cột một lượt (xem khối CF_MULTI bên dưới)
    return;
  }
}
/* ----- Tool kiểm NHIỀU cột trong 1 lần phát hiện (Không nhất quán, Ngoài khoảng, Giá trị bất thường) -----
   Mỗi "form" = 1 cột + các ô riêng của cột đó (giá trị chuẩn + ngưỡng / nhỏ nhất + lớn nhất / các phương pháp). Nút "＋ Thêm cột kiểm tra"
   thêm form mới (mỗi cột chỉ khai 1 lần). "Phát hiện" gửi tất cả form 1 lượt; kết quả hiện bảng "cột nào, bao nhiêu lỗi" kèm chọn cách xử lý
   từng cột (renderCfMultiSummary). Mỗi tool chỉ liệt kê cột có kiểu hợp (kiểu do Denoise đoán): Không nhất quán = Nhóm, hai tool còn lại = số.
   Muốn tool khác kiểm nhiều cột thì thêm 1 mục vào CF_MULTI -- khung form, bảng tổng hợp, backend dùng chung.
   Mỗi mục: dtypes (kiểu cột được liệt kê; chỉ 1 kiểu thì ô "Kiểu dữ liệu" bị khoá), thông báo, preselect (bảng tổng hợp có chọn sẵn cách xử
   lý đầu tiên không -- chỉ bật cho tool KHÔNG xoá dữ liệu), defaults (ô riêng + giá trị mặc định), fieldsHTML, toItem (gom 1 form thành item
   gửi backend); tuỳ chọn onClick / onInput cho nút và ô riêng nằm trong form (vd các hàng phương pháp của Giá trị bất thường). */
const IC_DEFAULT_THRESHOLD = "1"; // 1 = chỉ bắt biến thể khác hoa/thường; hạ xuống để bắt thêm lỗi chính tả
const cfNumber = (v) => (String(v).trim() === "" ? null : Number(v));
// Phương pháp phát hiện giá trị bất thường: mỗi cột kiểm được 1 hoặc cả 2 (ô bị gắn cờ nếu bất thường theo BẤT KỲ phương pháp nào).
const OUTLIER_METHODS = ["iqr", "zscore"];
const OUTLIER_METHOD_LABELS = { iqr: "IQR", zscore: "Z-score" };
const OUTLIER_DEFAULT_THRESHOLD = { iqr: "1.5", zscore: "3" }; // IQR thường dùng 1.5, Z-score thường dùng 3
function outlierMethodRowHTML(f, m, j, i) {
  // Ô chọn phương pháp là nút gạt 2 lựa chọn; phương pháp đang dùng ở hàng khác thì khoá (mỗi phương pháp chỉ khai 1 lần / cột).
  const usedElsewhere = (v) => f.methods.some((x, k) => k !== j && x.method === v);
  const pick = OUTLIER_METHODS.map((v) =>
    `<button type="button" data-role="mf-method-pick" data-value="${v}" class="${v === m.method ? "is-active" : ""}"${usedElsewhere(v) ? " disabled" : ""}>${OUTLIER_METHOD_LABELS[v]}</button>`).join("");
  const remove = f.methods.length > 1
    ? `<button type="button" class="btn btn-ghost btn-small cf-method-remove" data-role="mf-method-remove" aria-label="Xoá phương pháp ${j + 1} của cột kiểm tra ${i + 1}">✕</button>` : "";
  return `<div class="cf-method-row${remove ? " has-remove" : ""}" data-index="${j}">` +
    `<div class="field cf-method-pick"><label>Phương pháp</label><div class="ft-seg">${pick}</div></div>` +
    `<div class="field"><label>Ngưỡng</label><input class="input" type="number" step="any" min="0" data-role="mf-threshold" value="${escapeAttr(m.threshold)}" aria-label="Ngưỡng phương pháp ${j + 1} của cột kiểm tra ${i + 1}" /></div>` +
    `${remove}</div>`;
}
const CF_MULTI = {
  "inconsistent-category": {
    dtypes: ["category"],
    waitFile: "Chọn file hoặc dán dữ liệu để chọn cột Nhóm.",
    noColumns: "Không có cột Nhóm nào (cột ít giá trị khác nhau, lặp lại nhiều, vd giới tính, phòng ban).",
    noColumnsError: "Không có cột Nhóm nào để kiểm tra.",
    freeWord: "cột Nhóm",
    preselect: true, // cách xử lý duy nhất là chuẩn hoá tự động, không xoá dữ liệu nên chọn sẵn
    defaults: () => ({ categories: "", threshold: IC_DEFAULT_THRESHOLD }),
    fieldsHTML: (f, i) =>
      `<div class="field"><label>Danh sách giá trị chuẩn (cách nhau bởi dấu phẩy)</label><textarea class="input" rows="2" data-field="categories" placeholder="vd: Nam, Nữ" aria-label="Danh sách giá trị chuẩn ${i + 1}">${escapeHtml(f.categories)}</textarea></div>` +
      `<div class="field"><label>Ngưỡng giống nhau (0.5 – 1)</label><input class="input" type="number" step="0.01" min="0.5" max="1" data-field="threshold" value="${escapeAttr(f.threshold)}" aria-label="Ngưỡng giống nhau ${i + 1}" /></div>` +
      '<p class="hint-note">1 = chỉ bắt biến thể khác hoa/thường. Hạ thấp (vd 0.85) để bắt thêm lỗi gõ.</p>',
    toItem: (f) => {
      const cats = f.categories.split(",").map((x) => x.trim()).filter(Boolean);
      if (!cats.length) return { error: `Cột "${f.column}": nhập ít nhất 1 giá trị chuẩn.` };
      const threshold = String(f.threshold).trim() === "" ? Number(IC_DEFAULT_THRESHOLD) : Number(f.threshold);
      if (!(threshold >= 0.5 && threshold <= 1)) return { error: `Cột "${f.column}": ngưỡng giống nhau phải từ 0.5 đến 1.` };
      return { item: { column: f.column, dtype: "category", params: { valid_categories: cats, category_similarity_threshold: threshold } } };
    },
  },
  "out-of-range": {
    dtypes: ["integer", "float"],
    waitFile: "Chọn file hoặc dán dữ liệu để chọn cột số.",
    noColumns: "Không có cột số nào (Số nguyên / Số thực) trong dữ liệu này.",
    noColumnsError: "Không có cột số nào để kiểm tra.",
    freeWord: "cột số",
    preselect: false, // có cách xử lý xoá dòng / điền giá trị: để người dùng chủ động chọn, bấm Áp dụng không xoá nhầm hàng loạt
    defaults: () => ({ min: "", max: "" }),
    fieldsHTML: (f, i) =>
      `<div class="cf-row"><div class="field"><label>Nhỏ nhất hợp lệ</label><input class="input" type="number" step="any" data-field="min" value="${escapeAttr(f.min)}" placeholder="vd: 18" aria-label="Nhỏ nhất hợp lệ ${i + 1}" /></div>` +
      `<div class="field"><label>Lớn nhất hợp lệ</label><input class="input" type="number" step="any" data-field="max" value="${escapeAttr(f.max)}" placeholder="vd: 65" aria-label="Lớn nhất hợp lệ ${i + 1}" /></div></div>` +
      '<p class="hint-note">Để trống một ô = không chặn phía đó.</p>',
    toItem: (f) => {
      const min = cfNumber(f.min);
      const max = cfNumber(f.max);
      if (Number.isNaN(min) || Number.isNaN(max)) return { error: `Cột "${f.column}": nhỏ nhất / lớn nhất phải là số.` };
      if (min === null && max === null) return { error: `Cột "${f.column}": nhập ít nhất 1 trong 2 giá trị nhỏ nhất / lớn nhất.` };
      if (min !== null && max !== null && min > max) return { error: `Cột "${f.column}": giá trị nhỏ nhất đang lớn hơn giá trị lớn nhất.` };
      return { item: { column: f.column, dtype: f.dtype, params: { min_value: min, max_value: max } } };
    },
  },
  outlier: {
    dtypes: ["integer", "float"],
    waitFile: "Chọn file hoặc dán dữ liệu để chọn cột số.",
    noColumns: "Không có cột số nào (Số nguyên / Số thực) trong dữ liệu này.",
    noColumnsError: "Không có cột số nào để kiểm tra.",
    freeWord: "cột số",
    preselect: false, // có xoá dòng / điền lại: để người dùng chủ động chọn, bấm Áp dụng không xoá nhầm hàng loạt
    defaults: () => ({ methods: [{ method: "iqr", threshold: OUTLIER_DEFAULT_THRESHOLD.iqr }] }),
    fieldsHTML: (f, i) => {
      const free = OUTLIER_METHODS.filter((v) => !f.methods.some((m) => m.method === v));
      return '<div class="cf-methods">' + f.methods.map((m, j) => outlierMethodRowHTML(f, m, j, i)).join("") +
        `<div class="cf-add-row"><button type="button" class="btn btn-ghost btn-small" data-role="mf-method-add"${free.length ? "" : " disabled"}>＋ Thêm phương pháp</button>` +
        `<span class="cf-add-hint">${free.length ? `Còn ${free.map((v) => OUTLIER_METHOD_LABELS[v]).join(", ")} chưa dùng` : "Đã dùng cả 2 phương pháp"}</span></div></div>` +
        '<p class="hint-note">Thường dùng IQR 1.5 hoặc Z-score 3. Chọn cả hai thì chỉ cần một bên gắn cờ.</p>';
    },
    // Nút / ô riêng trong form (nằm trong các hàng phương pháp). onClick trả true (dựng lại form) hoặc chuỗi selector (dựng lại rồi
    // đưa con trỏ vào ô đó) hoặc false (không làm gì); onInput chỉ ghi lại ngưỡng đang gõ, không dựng lại (để không mất con trỏ).
    onClick: (e, f) => {
      const row = e.target.closest(".cf-method-row");
      if (e.target.closest('[data-role="mf-method-add"]')) {
        const next = OUTLIER_METHODS.find((v) => !f.methods.some((m) => m.method === v));
        if (!next) return false;
        f.methods.push({ method: next, threshold: OUTLIER_DEFAULT_THRESHOLD[next] });
        return `.cf-method-row[data-index="${f.methods.length - 1}"] [data-role="mf-threshold"]`;
      }
      if (!row) return false;
      const j = Number(row.dataset.index);
      if (e.target.closest('[data-role="mf-method-remove"]')) {
        if (f.methods.length <= 1) return false; // luôn còn ít nhất 1 phương pháp
        f.methods.splice(j, 1);
        return true;
      }
      const pick = e.target.closest('[data-role="mf-method-pick"]');
      if (pick && !pick.disabled && f.methods[j].method !== pick.dataset.value) {
        f.methods[j] = { method: pick.dataset.value, threshold: OUTLIER_DEFAULT_THRESHOLD[pick.dataset.value] }; // đổi phương pháp -> ngưỡng mặc định của phương pháp mới
        return true;
      }
      return false;
    },
    onInput: (e, f) => {
      const row = e.target.closest(".cf-method-row");
      if (row && e.target.dataset.role === "mf-threshold" && f.methods[Number(row.dataset.index)]) f.methods[Number(row.dataset.index)].threshold = e.target.value;
    },
    toItem: (f) => {
      const rules = [];
      for (const m of f.methods) {
        const raw = String(m.threshold).trim();
        const threshold = raw === "" ? Number(OUTLIER_DEFAULT_THRESHOLD[m.method]) : Number(raw);
        if (!Number.isFinite(threshold) || threshold <= 0) return { error: `Cột "${f.column}": ngưỡng của ${OUTLIER_METHOD_LABELS[m.method]} phải là số lớn hơn 0.` };
        rules.push({ method: m.method, threshold });
      }
      return { item: { column: f.column, dtype: f.dtype, params: { outlier_rules: rules } } };
    },
  },
};
function cfForms(tool) {
  return state.cf.forms[tool] || (state.cf.forms[tool] = []);
}
// Cột được liệt kê cho tool: cột có kiểu (đoán từ dữ liệu) nằm trong dtypes của tool.
function cfMultiColumns(tool) {
  return state.cf.columns.filter((c) => CF_MULTI[tool].dtypes.includes(state.cf.guessed[c]));
}
function makeMultiForm(tool, column) {
  const cfg = CF_MULTI[tool];
  return Object.assign({ uid: ++state.cf.formUid, column, dtype: cfDefaultDtype(column, cfg.dtypes) }, cfg.defaults());
}
// Giữ các form còn hợp lệ với danh sách cột hiện tại (cột còn tồn tại, đúng kiểu, không trùng cột); chưa có form nào thì tạo 1 form cho
// cột đầu tiên. Gọi mỗi lần dựng lại khối tuỳ chọn (đổi tab, đọc lại cột sau khi chuỗi đổi...) nên giữ được những gì người dùng đã gõ.
function reconcileMultiForms(tool) {
  const cols = cfMultiColumns(tool);
  const seen = new Set();
  const kept = [];
  for (const f of cfForms(tool)) {
    if (cols.includes(f.column) && !seen.has(f.column)) { seen.add(f.column); kept.push(f); }
  }
  state.cf.forms[tool] = kept;
  if (!kept.length && cols.length) state.cf.forms[tool] = [makeMultiForm(tool, cols[0])];
}
function multiFormByUid(uid) {
  return cfForms(state.cf.tool).find((f) => String(f.uid) === String(uid));
}
function multiFormHTML(tool, f, i, cols, used) {
  const cfg = CF_MULTI[tool];
  // Ô chọn cột của form này chỉ liệt kê cột chưa được form khác dùng (cộng chính cột đang chọn).
  const colOpts = cols.filter((c) => c === f.column || !used.has(c))
    .map((c) => `<option value="${escapeAttr(c)}"${c === f.column ? " selected" : ""}>${escapeHtml(c)}</option>`).join("");
  // Kiểu dữ liệu: tool chỉ có 1 kiểu (Nhóm) thì khoá cố định; tool có nhiều kiểu (Số nguyên / Số thực) thì chọn được, mặc định theo kiểu đoán.
  const typeOpts = cfg.dtypes.map((d) => `<option value="${d}"${d === f.dtype ? " selected" : ""}>${DTYPE_LABELS[d]}</option>`).join("");
  const typeSelect = `<select class="select" data-role="mf-dtype"${cfg.dtypes.length > 1 ? "" : " disabled"} aria-label="Kiểu dữ liệu ${i + 1}">${typeOpts}</select>`;
  const remove = cfForms(tool).length > 1 ? '<button type="button" class="btn btn-ghost btn-small" data-role="mf-remove">✕ Xoá</button>' : "";
  return `<div class="cf-form" data-uid="${f.uid}">` +
    `<div class="cf-form-bar"><span class="cf-form-title">Cột kiểm tra ${i + 1}</span>${remove}</div>` +
    '<div class="cf-form-body">' +
    `<div class="cf-row"><div class="field"><label>Cột cần kiểm tra</label><select class="select" data-role="mf-column" aria-label="Cột cần kiểm tra ${i + 1}">${colOpts}</select></div>` +
    `<div class="field"><label>Kiểu dữ liệu</label>${typeSelect}</div></div>` +
    cfg.fieldsHTML(f, i) +
    '</div></div>';
}
function renderCfMultiForms() {
  const tool = state.cf.tool;
  const cfg = CF_MULTI[tool];
  const wrap = $("cf-options");
  reconcileMultiForms(tool);
  if (!state.cf.columns.length) {
    wrap.innerHTML = `<p class="ft-coltypes-msg">${cfg.waitFile}</p>`;
    return;
  }
  const cols = cfMultiColumns(tool);
  if (!cols.length) {
    wrap.innerHTML = `<p class="ft-coltypes-msg">${cfg.noColumns}</p>`;
    return;
  }
  const forms = cfForms(tool);
  const used = new Set(forms.map((f) => f.column));
  const free = cols.filter((c) => !used.has(c)).length;
  wrap.innerHTML = forms.map((f, i) => multiFormHTML(tool, f, i, cols, used)).join("") +
    `<div class="cf-add-row"><button type="button" class="btn btn-ghost btn-small" data-role="mf-add"${free ? "" : " disabled"}>＋ Thêm cột kiểm tra</button>` +
    `<span class="cf-add-hint">${free ? `Còn ${free} ${cfg.freeWord} chưa kiểm tra` : `Đã chọn hết các ${cfg.freeWord}`}</span></div>`;
}
// Sự kiện gắn 1 lần lên #cf-options (nội dung bên trong bị dựng lại liên tục); chỉ phản ứng khi tool đang mở là tool nhiều cột.
$("cf-options").addEventListener("change", (e) => {
  if (!CF_MULTI[state.cf.tool]) return;
  const role = e.target.dataset.role;
  if (role !== "mf-column" && role !== "mf-dtype") return;
  const f = multiFormByUid(e.target.closest(".cf-form").dataset.uid);
  if (!f) return;
  if (role === "mf-dtype") { f.dtype = e.target.value; return; }
  f.column = e.target.value;
  f.dtype = cfDefaultDtype(f.column, CF_MULTI[state.cf.tool].dtypes); // đổi cột -> kiểu theo kiểu đoán sẵn của cột đó
  renderCfMultiForms(); // danh sách cột của các form khác phải loại cột vừa chọn
});
$("cf-options").addEventListener("input", (e) => {
  const cfg = CF_MULTI[state.cf.tool];
  if (!cfg) return;
  const form = e.target.closest(".cf-form");
  const f = form && multiFormByUid(form.dataset.uid);
  if (!f) return;
  if (e.target.dataset.field) f[e.target.dataset.field] = e.target.value;
  else if (cfg.onInput) cfg.onInput(e, f); // ô riêng của tool (vd ngưỡng của từng phương pháp)
});
$("cf-options").addEventListener("click", (e) => {
  const tool = state.cf.tool;
  if (!CF_MULTI[tool]) return;
  if (e.target.closest('[data-role="mf-add"]')) {
    const used = new Set(cfForms(tool).map((f) => f.column));
    const next = cfMultiColumns(tool).find((c) => !used.has(c));
    if (!next) return;
    const f = makeMultiForm(tool, next);
    cfForms(tool).push(f);
    renderCfMultiForms();
    const box = document.querySelector(`#cf-options .cf-form[data-uid="${f.uid}"] [data-field]`);
    if (box) { box.focus(); box.scrollIntoView({ block: "nearest", behavior: "smooth" }); }
    return;
  }
  const remove = e.target.closest('[data-role="mf-remove"]');
  if (remove) {
    const uid = remove.closest(".cf-form").dataset.uid;
    state.cf.forms[tool] = cfForms(tool).filter((f) => String(f.uid) !== uid);
    renderCfMultiForms();
    return;
  }
  // Nút riêng của tool nằm trong form (vd Giá trị bất thường: thêm / xoá / đổi phương pháp).
  const cfg = CF_MULTI[tool];
  const formEl = e.target.closest(".cf-form");
  const f = formEl && multiFormByUid(formEl.dataset.uid);
  if (!f || !cfg.onClick) return;
  const result = cfg.onClick(e, f);
  if (!result) return;
  renderCfMultiForms();
  if (typeof result === "string") {
    const box = document.querySelector(`#cf-options .cf-form[data-uid="${f.uid}"] ${result}`);
    if (box) box.focus();
  }
});
// Bảng tổng hợp sau "Phát hiện" (tool nhiều cột): mỗi cột đã khai 1 dòng = tên cột | số ô lỗi (và số dòng) | cách xử lý chọn riêng từng
// cột. Tool preselect (không xoá dữ liệu): mặc định = cách đầu tiên backend cho phép, "Bỏ qua" ở cuối. Tool khác: mặc định "— Chọn cách
// xử lý —" (= bỏ qua) để bấm Áp dụng không xoá nhầm; cột nào chọn "điền giá trị cố định" thì hiện ô nhập ngay trong dòng.
// Cột không có lỗi thì không cần chọn gì.
function renderCfMultiSummary(perColumn, tool) {
  const cfg = CF_MULTI[tool];
  const total = perColumn.reduce((a, p) => a + p.findings_count, 0);
  const withErrors = perColumn.filter((p) => p.findings_count > 0).length;
  const rows = perColumn.map((p) => {
    const has = p.findings_count > 0;
    let action = '<span class="cf-sum-none">Không có lỗi</span>';
    let fixed = "";
    if (has) {
      const actionOpts = p.available_actions.map((a) => `<option value="${a}">${escapeHtml(ACTION_LABELS[a] || a)}</option>`).join("");
      const opts = cfg.preselect ? actionOpts + '<option value="skip">Bỏ qua, giữ nguyên</option>' : '<option value="skip">— Chọn cách xử lý —</option>' + actionOpts;
      action = `<select class="select cf-sum-action" data-role="sum-action" data-column="${escapeAttr(p.column)}" aria-label="Cách xử lý cột ${escapeAttr(p.column)}">${opts}</select>`;
      if (p.available_actions.includes("fixed_value")) {
        fixed = `<input class="input cf-sum-fixed" data-role="sum-fixed" placeholder="Giá trị điền vào các ô lỗi" aria-label="Giá trị cố định cho cột ${escapeAttr(p.column)}" hidden />`;
      }
    }
    // Cột kiểm nhiều phương pháp (backend chỉ trả khi >= 2): ghi mỗi phương pháp bắt bao nhiêu ô + bao nhiêu ô cả hai cùng bắt, vì số ô
    // lỗi của cột là HỢP của các phương pháp nên không bằng tổng.
    let methods = "";
    if (has && p.methods && p.methods.length > 1) {
      const parts = p.methods.map((m) => `${OUTLIER_METHOD_LABELS[m.method]} ${m.threshold} bắt ${m.findings_count} ô`);
      if (p.both_count !== undefined) parts.push(`cả hai cùng bắt ${p.both_count} ô`);
      methods = `<span class="cf-sum-methods">${escapeHtml(parts.join(" · "))}</span>`;
    }
    // IQR suy biến (backend báo `warnings` code iqr_zero): đa số ô cùng 1 giá trị nên IQR coi MỌI giá trị khác là bất thường. Hiện cảnh báo
    // luôn; còn dòng đỏ "cách xử lý đang chọn sẽ sửa/xoá dữ liệu thật" chỉ hiện khi người dùng chọn 1 cách thực sự đổi dữ liệu.
    let warn = "";
    const iqrZero = has && (p.warnings || []).find((w) => w.code === "iqr_zero");
    if (iqrZero) {
      const v = Number.isInteger(iqrZero.value) ? String(iqrZero.value) : String(Math.round(iqrZero.value * 1000) / 1000);
      warn = `<span class="cf-sum-warn">⚠ IQR của cột này bằng 0: ${Math.round(iqrZero.share * 100)}% ô đều bằng ${escapeHtml(v)}, nên mọi giá trị khác ${escapeHtml(v)} bị coi là bất thường, kể cả giá trị thật. ` +
        `Nên dùng Z-score, hoặc xem kỹ các ô bị gắn cờ trước khi sửa.</span>` +
        `<span class="cf-sum-risk" data-role="sum-risk" hidden>Cách xử lý này sẽ sửa hoặc xoá cả giá trị có thể là dữ liệu thật.</span>`;
    }
    return `<div class="cf-sum-row${has ? " has-errors" : ""}"><span class="cf-sum-name" title="${escapeAttr(p.column)}">${escapeHtml(p.column)}</span>` +
      `<span class="cf-sum-count">${p.findings_count} ô lỗi${has ? ` · ${p.flagged_rows_count} dòng` : ""}</span>${action}${fixed}${methods}${warn}</div>`;
  }).join("");
  $("cf-multi").innerHTML =
    `<div class="cf-sum"><div class="ft-coltypes-bar"><span class="ft-coltypes-title">Lỗi theo từng cột</span>` +
    `<span class="ft-coltypes-meta">${total} ô lỗi · ${withErrors}/${perColumn.length} cột</span></div><div class="cf-sum-list">${rows}</div></div>`;
  renderCfMultiPreview();
}
// Báo trước "Sẽ xoá N dòng (a → b)" cho tool nhiều cột: dòng bị xoá = HỢP các dòng lỗi của MỌI cột đang chọn "Xoá dòng" (khớp cách backend xoá:
// nhiều cột cùng chọn xoá thì dòng lỗi ở BẤT KỲ cột nào cũng bị xoá, một dòng lỗi ở 2 cột chỉ tính một lần). Cách khác (điền, kéo về biên...)
// không xoá dòng nên không hiện gì. Số dòng lấy từ per_column[].flagged_row_numbers của lần Phát hiện, không gọi lại backend.
function renderCfMultiPreview() {
  const box = $("cf-multi-preview");
  const det = state.cf.detect;
  box.classList.remove("is-risk");
  if (!det || !det.multi) { box.hidden = true; box.textContent = ""; return; }
  const byColumn = {};
  det.data.per_column.forEach((p) => { byColumn[p.column] = p; });
  const chosen = [];
  document.querySelectorAll('#cf-multi [data-role="sum-action"]').forEach((sel) => {
    if (sel.value === "remove_row") chosen.push(sel.dataset.column);
  });
  if (!chosen.length) { box.hidden = true; box.textContent = ""; return; }
  const names = chosen.map((c) => `«${c}»`).join(", ");
  if (chosen.some((c) => !byColumn[c] || !Array.isArray(byColumn[c].flagged_row_numbers))) {
    box.textContent = `Cột ${names} chọn xoá dòng. Dữ liệu lớn nên chưa tính trước được số dòng sẽ xoá.`;
    box.hidden = false;
    return;
  }
  const rows = new Set();
  chosen.forEach((c) => byColumn[c].flagged_row_numbers.forEach((n) => rows.add(n)));
  const total = det.data.total_rows;
  const n = rows.size;
  box.textContent = `Sẽ xoá ${n} dòng (${total} → ${total - n} dòng) vì chọn «Xoá dòng» ở cột ${names}.` +
    (total > 0 && n / total >= 0.2 ? ` Đây là ${Math.round((n / total) * 100)}% số dòng, hãy xem lại cho chắc.` : "");
  if (total > 0 && n / total >= 0.2) box.classList.add("is-risk");
  box.hidden = false;
}
// Chọn "điền giá trị cố định" ở 1 cột -> hiện ô nhập giá trị của đúng dòng đó (đổi cách khác thì ẩn).
$("cf-multi").addEventListener("change", (e) => {
  if (e.target.dataset.role !== "sum-action") return;
  renderCfMultiPreview();
  const row = e.target.closest(".cf-sum-row");
  // Cột có cảnh báo IQR = 0: chọn cách nào thực sự đổi dữ liệu (không phải "chưa chọn"/"giữ nguyên") thì hiện dòng đỏ nhắc nguy cơ mất dữ liệu thật.
  const risk = row.querySelector('[data-role="sum-risk"]');
  if (risk) risk.hidden = e.target.value === "skip" || e.target.value === "keep";
  const box = row.querySelector('[data-role="sum-fixed"]');
  if (!box) return;
  box.hidden = e.target.value !== "fixed_value";
  if (!box.hidden) box.focus();
});
// Khối "Cách xử lý" dưới nút Phát hiện có 2 kiểu: nhiều cột (bảng tổng hợp) hoặc 1 cột/rule (1 ô chọn cách xử lý như cũ).
function prepareCfHandling(multi, data, tool) {
  $("cf-handling-title").textContent = multi ? "Kết quả phát hiện theo từng cột" : "Cách xử lý mọi ô vừa bị gắn cờ";
  $("cf-multi").hidden = !multi;
  $("cf-single-handling").hidden = multi;
  $("cf-apply-row").hidden = multi && data.findings_count === 0; // không có lỗi nào thì không có gì để áp dụng
  if (multi) renderCfMultiSummary(data.per_column, tool);
}
// Các nút chèn nhanh của ô Biểu thức, chia 3 nhóm (mỗi nhóm 1 hàng): [chữ hiện trên nút, chữ chèn vào ô, giải thích khi rê chuột].
// Nút chỉ chèn chữ vào ô tại chỗ con trỏ: bấm hay gõ tay ra kết quả y hệt, có nút để khỏi gõ sai. Nút "thì =>" thay cho tab Nếu – thì cũ
// (nếu A thì B = A => B). Mũ (^) và phần trăm (%) cố tình không có: bộ máy không hỗ trợ; phần trăm thì chia 100.
const EXPR_BUTTON_GROUPS = [
  ["Nối điều kiện", [
    ["và", "và", "Cả hai điều kiện đều phải đúng"],
    ["hoặc", "hoặc", "Chỉ cần một trong hai điều kiện đúng"],
    ["không", "không", "Đảo điều kiện: đúng thành sai, sai thành đúng"],
    ["( )", "( )", "Ngoặc để gộp điều kiện, vd (a hoặc b) và c"],
    ["có( )", "có()", "Ô của cột đó có giá trị (không trống). Vd: có(email)"],
    ["thì =>", "=>", "NẾU … THÌ …: dòng thoả điều kiện trước thì điều kiện sau phải đúng. Vd: phong_ban = \"Sales\" => luong >= 10000000"],
  ]],
  ["So sánh", [
    ["<", "<", "nhỏ hơn"], ["<=", "<=", "nhỏ hơn hoặc bằng"], ["=", "=", "bằng"], ["!=", "!=", "khác"], [">=", ">=", "lớn hơn hoặc bằng"], [">", ">", "lớn hơn"],
  ]],
  ["Tính toán và chữ", [
    ["+", "+", "cộng"], ["−", "-", "trừ"], ["×", "*", "nhân (chèn dấu *)"], ["÷", "/", "chia (chèn dấu /). Phần trăm thì chia 100, vd giam_gia / 100"],
    ['" "', '""', "Giá trị chữ trong dấu nháy, vd \"Marketing Team\". Chữ phân biệt hoa/thường"],
  ]],
];
// Khối chèn nhanh: 3 hàng nút + chip tên cột + (khi bấm chip cột Nhóm) chip giá trị của cột đó.
function exprHelperHTML(cols) {
  const chips = cols.map((col) => `<button type="button" class="cf-chip" data-role="expr-col" data-col="${escapeAttr(col)}" title="Chèn cột ${escapeAttr(col)}">${escapeHtml(col)}</button>`).join("");
  // Lưới 6 cột đều nhau (CSS .cf-expr-toolbar): hàng 1 và 2 đủ 6 nút; hàng 3 có 5 nút, nút cặp nháy rộng gấp đôi (is-wide) để cả 3 hàng thẳng hai mép.
  // Hàng 2 và 3 toàn ký hiệu nên cỡ chữ to hơn cho dễ nhìn (is-symbols).
  const groups = EXPR_BUTTON_GROUPS.map(([name, buttons], gi) =>
    `<div class="cf-expr-words${gi > 0 ? " is-symbols" : ""}" role="group" aria-label="${escapeAttr(name)}">${buttons.map(([label, word, tip]) =>
      `<button type="button" class="btn btn-ghost btn-small${word === '""' ? " is-wide" : ""}" data-role="expr-word" data-word="${escapeAttr(word)}" title="${escapeAttr(tip)}">${escapeHtml(label)}</button>`).join("")}</div>`).join("");
  return `<div class="field">
      <label>Bấm để chèn vào biểu thức (tại chỗ con trỏ)</label>
      <div class="cf-expr-toolbar">${groups}</div>
      <div class="cf-chips" id="cf-col-chips">${chips || '<span class="cf-add-hint">(chọn file hoặc dán text trước để có danh sách cột)</span>'}</div>
      <div class="cf-values" id="cf-value-box" hidden>
        <p class="cf-values-title" id="cf-value-title"></p>
        <div class="cf-chips cf-value-chips" id="cf-value-chips"></div>
        <p class="cf-add-hint" id="cf-value-more" hidden></p>
      </div>
    </div>`;
}
// Hàng "Giá trị trong cột «X»" dưới các chip cột: hiện khi vừa bấm chip của cột Nhóm (backend trả column_values cho cột chữ ít giá trị khác nhau);
// cột số / ngày / tên người... không có giá trị để liệt kê thì ẩn (số gõ thẳng, không cần nháy).
function renderCfValueChips(col) {
  const box = $("cf-value-box");
  if (!box) return;
  const info = col ? state.cf.columnValues[col] : null;
  state.cf.valueCol = info ? col : "";
  if (!info) { box.hidden = true; return; }
  $("cf-value-title").innerHTML = `Giá trị trong cột <b>${escapeHtml(col)}</b> (bấm để chèn, phân biệt hoa/thường)`;
  $("cf-value-chips").innerHTML = info.values.map((v) =>
    `<button type="button" class="cf-chip cf-chip-value" data-role="expr-value" data-value="${escapeAttr(v.value)}" title="${v.count} dòng">${escapeHtml(v.value)}<span class="cf-chip-count">${v.count}</span></button>`).join("");
  const more = $("cf-value-more");
  more.hidden = !info.more;
  if (info.more) more.textContent = `Còn ${info.more} giá trị ít gặp, gõ tay trong dấu nháy.`;
  box.hidden = false;
}
// Khuôn ngày (trống = tự nhận) + sai số khi so bằng.
function exprOptionsHTML() {
  const e = state.cf.expr;
  return `<div class="cf-row">
      <div class="field"><label for="cf-rule-date-format">Khuôn ngày (để trống = tự nhận)</label><input class="input mono" id="cf-rule-date-format" placeholder="%d/%m/%Y" value="${escapeAttr(e.dateFormat)}" /></div>
      <div class="field"><label for="cf-tolerance">Sai số khi so bằng giữa hai số</label><input class="input" id="cf-tolerance" type="number" step="any" min="0" value="${escapeAttr(e.tolerance)}" /></div>
    </div>`;
}
function renderCfRuleFields() {
  const type = $("cf-rule-type").value;
  const box = $("cf-rule-fields");
  const cols = state.cf.columns;
  const c = (id, label, sel) => cfColumnSelect(id, label, sel || cols[0] || "");
  state.cf.ruleType = type;
  if (type === "expression") {
    box.innerHTML = `<div class="cf-expr-form">
      <div class="field">
        <label for="cf-expression">Biểu thức: điều kiện mà MỌI dòng phải thoả</label>
        <textarea class="input mono" id="cf-expression" rows="3" spellcheck="false" placeholder='vd: tuoi >= 18 và tuoi <= 65'>${escapeHtml(state.cf.expr.text)}</textarea>
        <p class="cf-live" id="cf-live-check" role="status" aria-live="polite" hidden></p>
      </div>
      ${exprHelperHTML(cols)}
      ${exprOptionsHTML()}
      <p class="hint-note">Dòng chắc chắn sai thì bị gắn cờ, ô trống hoặc sai kiểu bị bỏ qua và được báo lại. Tên cột có dấu cách viết trong [ ].</p></div>`;
    renderCfValueChips(state.cf.valueCol); // dựng lại form (đổi tab / đọc lại cột): hiện lại giá trị của cột đang chọn nếu còn
    scheduleLiveCheck(); // ... và kiểm tra lại biểu thức đang có (đầu vào có thể vừa đổi)
  } else {
    box.innerHTML = `<div class="cf-row cf-fd-row">${c("cf-det-col", "Cột xác định (A)")}<div class="field" id="cf-fd-deps"></div></div>
      <p class="hint-note">Mỗi giá trị A chỉ đi với đúng 1 giá trị của từng cột phụ thuộc (vd ma_nv → ten). Không dùng cho cột là kết quả giao dịch.</p>`;
    renderCfFdDeps();
  }
}
/* ----- Phụ thuộc hàm: 1 cột xác định (A) suy ra NHIỀU cột phụ thuộc (B1, B2...) -----
   cfFdDeps = các cột phụ thuộc đang chọn (mỗi cột 1 ô chọn + nút xoá; nút "＋ Thêm cột phụ thuộc" ở dưới). Mỗi ô chỉ liệt kê cột chưa dùng và
   khác cột xác định. Backend tách thành từng rule A → Bi và kiểm riêng từng cột (xem _cross_rules_from_config). */
let cfFdDeps = [];
function cfFdDetColumn() {
  const el = $("cf-det-col");
  return el ? el.value : "";
}
// Giữ các cột phụ thuộc còn hợp lệ (còn trong file, khác cột xác định, không trùng nhau); rỗng thì chọn sẵn cột đầu tiên khác cột xác định.
function cfFdReconcile() {
  const cols = state.cf.columns;
  const det = cfFdDetColumn();
  const kept = [];
  for (const c of cfFdDeps) if (cols.includes(c) && c !== det && !kept.includes(c)) kept.push(c);
  if (!kept.length) { const first = cols.find((c) => c !== det); if (first) kept.push(first); }
  cfFdDeps = kept;
}
function renderCfFdDeps() {
  const box = $("cf-fd-deps");
  if (!box) return;
  cfFdReconcile();
  const cols = state.cf.columns;
  const det = cfFdDetColumn();
  const rows = cfFdDeps.map((dep, i) => {
    const opts = cols.filter((c) => c === dep || (c !== det && !cfFdDeps.includes(c)))
      .map((c) => `<option value="${escapeAttr(c)}"${c === dep ? " selected" : ""}>${escapeHtml(c)}</option>`).join("");
    const remove = cfFdDeps.length > 1
      ? `<button type="button" class="btn btn-ghost btn-small cf-fd-remove" data-role="fd-remove" data-index="${i}" aria-label="Xoá cột phụ thuộc ${i + 1}">✕</button>` : "";
    return `<div class="cf-fd-dep"><select class="select" data-role="fd-dep" data-index="${i}" aria-label="Cột phụ thuộc ${i + 1}">${opts || '<option value="">(chọn file trước)</option>'}</select>${remove}</div>`;
  }).join("");
  const free = cols.filter((c) => c !== det && !cfFdDeps.includes(c)).length;
  box.innerHTML = `<label>Cột phụ thuộc (B)</label>${rows}` +
    `<div class="cf-add-row"><button type="button" class="btn btn-ghost btn-small" data-role="fd-add"${free && cols.length ? "" : " disabled"}>＋ Thêm cột phụ thuộc</button>` +
    `<span class="cf-add-hint">${free ? `Còn ${free} cột chưa chọn` : "Đã chọn hết các cột"}</span></div>`;
}
// Sự kiện gắn 1 lần lên #cf-options (nội dung bên trong bị dựng lại liên tục); chỉ phản ứng khi tool đang mở là Rule liên cột.
$("cf-options").addEventListener("change", (e) => {
  if (state.cf.tool !== "cross-rule") return;
  if (e.target.id === "cf-det-col") { renderCfFdDeps(); return; } // đổi cột xác định -> cột phụ thuộc không được trùng nó
  if (e.target.dataset.role === "fd-dep") {
    cfFdDeps[Number(e.target.dataset.index)] = e.target.value;
    renderCfFdDeps(); // các ô khác phải loại cột vừa chọn
  }
});
/* ----- Rule "Biểu thức": chèn cột / giá trị / nút vào ô biểu thức, tại chỗ con trỏ ----- */
const EXPR_RESERVED = new Set(["và", "va", "and", "hoặc", "hoac", "or", "không", "khong", "not", "so", "số", "ngay", "ngày", "chu", "chữ", "co", "có"]);
const EXPR_BOX = "cf-expression"; // ô nhập biểu thức duy nhất của tab Biểu thức
// Tên cột viết trần được nếu chỉ gồm chữ/số/_/. (không bắt đầu bằng số) và không trùng từ khoá; còn lại để trong [ ].
function exprRef(name) {
  const plain = /^[\p{L}_][\p{L}\p{N}_.]*$/u.test(name) && !EXPR_RESERVED.has(name.toLowerCase());
  return plain ? name : `[${name}]`;
}
// Giá trị chữ viết trong dấu nháy kép. Bộ đọc coi \ là ký tự thoát và coi cả " “ ” là dấu nháy kép (xem _tokenize), nên các ký tự đó trong giá trị
// phải thêm \ phía trước, không thì chuỗi bị cắt giữa chừng.
function exprString(value) {
  return `"${String(value).replace(/[\\"“”]/g, "\\$&")}"`;
}
function saveExprState() {
  if ($(EXPR_BOX)) state.cf.expr.text = $(EXPR_BOX).value;
}
function insertIntoExpression(text) {
  const box = $(EXPR_BOX);
  if (!box) return;
  const start = box.selectionStart == null ? box.value.length : box.selectionStart;
  const end = box.selectionEnd == null ? start : box.selectionEnd;
  const before = box.value.slice(0, start);
  const pad = before && !/[\s(\[]$/.test(before) ? " " : ""; // tách khỏi chữ đứng trước cho khỏi dính vào nhau
  box.value = before + pad + text + box.value.slice(end);
  const caret = (before + pad + text).length;
  box.focus();
  // Chèn "( )", "có()" hoặc cặp nháy "" thì đặt con trỏ vào giữa hai dấu để gõ tiếp.
  const inside = text === "( )" || text === '""' || text.endsWith("()");
  box.setSelectionRange(inside ? caret - 1 : caret, inside ? caret - 1 : caret);
  saveExprState();
  scheduleLiveCheck(); // chèn bằng nút / chip không bắn sự kiện input nên phải tự hẹn kiểm tra
}
$("cf-options").addEventListener("input", (e) => {
  if (state.cf.tool !== "cross-rule") return;
  if (e.target.id === EXPR_BOX) { saveExprState(); scheduleLiveCheck(); }
  else if (e.target.id === "cf-rule-date-format" && $("cf-rule-type").value === "expression") { state.cf.expr.dateFormat = e.target.value; scheduleLiveCheck(); }
  else if (e.target.id === "cf-tolerance") { state.cf.expr.tolerance = e.target.value; scheduleLiveCheck(); }
});
/* ----- Kiểm tra biểu thức khi đang gõ ------------------------------------------------------------------------------------------------------
   Ngừng gõ LIVE_CHECK_DELAY_MS thì gửi biểu thức + đầu vào lên /api/noise-tools/check-expression (cùng bộ tính với Phát hiện, không gắn cờ dòng nào) và hiện
   dòng "✓ hợp lệ" hoặc lỗi dưới ô nhập. Mỗi lần gõ/chèn tăng liveSeq nên kết quả của lần kiểm tra cũ về muộn bị bỏ. Không chặn nút Phát hiện. */
function setLiveCheck(kind, html) {
  const el = $("cf-live-check");
  if (!el) return;
  el.hidden = !kind;
  el.className = "cf-live" + (kind ? ` is-${kind}` : "");
  el.innerHTML = html || "";
}
function scheduleLiveCheck() {
  clearTimeout(state.cf.liveTimer);
  state.cf.liveSeq++; // mọi kết quả đang chờ về trở thành cũ
  const box = $(EXPR_BOX);
  if (!box || state.cf.tool !== "cross-rule") return;
  const line = $("cf-live-check");
  if (!box.value.trim()) { setLiveCheck(null); return; }
  if (line && !line.hidden) line.classList.add("is-stale"); // đang gõ: mờ kết quả cũ cho khỏi tưởng còn đúng
  state.cf.liveTimer = setTimeout(runLiveCheck, LIVE_CHECK_DELAY_MS);
}
async function runLiveCheck() {
  const box = $(EXPR_BOX);
  if (!box || state.cf.tool !== "cross-rule" || $("cf-rule-type").value !== "expression") return;
  const expression = box.value.trim();
  const src = cfInputSource();
  if (!expression || !src) { setLiveCheck(null); return; }
  const size = src.file ? src.file.size : (src.text || "").length;
  if (size > LIVE_CHECK_MAX_BYTES) { setLiveCheck("idle", "Dữ liệu lớn nên không tự kiểm tra khi gõ: bấm «Phát hiện» để kiểm tra."); return; }
  const fd = new FormData();
  const inp = collectInput("cf", fd);
  if (inp.error) { setLiveCheck(null); return; }
  fd.append("expression", expression);
  fd.append("date_format", $("cf-rule-date-format") ? $("cf-rule-date-format").value.trim() : "");
  fd.append("tolerance", $("cf-tolerance") ? $("cf-tolerance").value.trim() : "");
  const seq = ++state.cf.liveSeq;
  setLiveCheck("wait", "Đang kiểm tra…");
  let response, data;
  try {
    response = await fetch("/api/noise-tools/check-expression", { method: "POST", body: fd });
    data = await response.json();
  } catch (err) {
    if (seq === state.cf.liveSeq) setLiveCheck(null); // mất kết nối: im lặng, nút Phát hiện sẽ báo
    return;
  }
  if (seq !== state.cf.liveSeq) return; // trong lúc chờ đã gõ tiếp / đổi đầu vào: kết quả này đã cũ
  if (!response.ok) { setLiveCheck(null); return; } // lỗi đọc dữ liệu: để Phát hiện báo
  if (data.ok) {
    const reads = (data.columns || []).map((c) => `<b>${escapeHtml(c.name)}</b> ${EXPR_KIND_VI[c.type] || ""}${c.date_format ? " " + escapeHtml(humanDateFormat(c.date_format)) : ""}`).join(" · ");
    setLiveCheck("ok", `✓ Biểu thức hợp lệ${reads ? ` · cách đọc cột: ${reads}` : ""}`);
  } else {
    setLiveCheck("bad", `✗ ${escapeHtml(data.error || "Biểu thức chưa hợp lệ")}`);
  }
}
$("cf-options").addEventListener("click", (e) => {
  if (state.cf.tool !== "cross-rule") return;
  const colBtn = e.target.closest('[data-role="expr-col"]');
  if (colBtn) {
    insertIntoExpression(exprRef(colBtn.dataset.col));
    renderCfValueChips(colBtn.dataset.col); // cột Nhóm thì hiện thêm các giá trị của nó để bấm chèn
    return;
  }
  const valueBtn = e.target.closest('[data-role="expr-value"]');
  if (valueBtn) { insertIntoExpression(exprString(valueBtn.dataset.value)); return; }
  const wordBtn = e.target.closest('[data-role="expr-word"]');
  if (wordBtn) { insertIntoExpression(wordBtn.dataset.word); return; }
  if (e.target.closest('[data-role="fd-add"]')) {
    const det = cfFdDetColumn();
    const next = state.cf.columns.find((c) => c !== det && !cfFdDeps.includes(c));
    if (!next) return;
    cfFdDeps.push(next);
    renderCfFdDeps();
    return;
  }
  const remove = e.target.closest('[data-role="fd-remove"]');
  if (remove) {
    cfFdDeps.splice(Number(remove.dataset.index), 1);
    renderCfFdDeps();
  }
});
// Gom tuỳ chọn trên màn hình thành JSON gửi backend. Trả { error } hoặc { config }.
function buildCfConfig() {
  const tool = state.cf.tool;
  if (!state.cf.columns.length) return { error: "Chưa đọc được cột nào. Chọn file hoặc dán text trước." };
  const num = (id) => { const v = $(id) ? $(id).value.trim() : ""; return v === "" ? null : Number(v); };
  if (tool === "cross-rule") {
    const rule = { rule_type: $("cf-rule-type").value };
    if (rule.rule_type === "expression") {
      rule.expression = $("cf-expression").value.trim();
      if (!rule.expression) return { error: "Chưa nhập biểu thức." };
      rule.date_format = $("cf-rule-date-format").value.trim() || null;
      rule.tolerance = num("cf-tolerance"); // để trống -> null, backend dùng mặc định 0.01
    } else {
      Object.assign(rule, { determinant_column: $("cf-det-col").value, dependent_columns: cfFdDeps.slice() });
      if (!rule.dependent_columns.length) return { error: "Chọn ít nhất 1 cột phụ thuộc." };
      if (rule.dependent_columns.includes(rule.determinant_column)) return { error: "Cột phụ thuộc phải khác cột xác định." };
    }
    return { config: { tool, rule } };
  }
  if (CF_MULTI[tool]) {
    // Mỗi form = 1 cột. Gửi cả danh sách `items` để backend kiểm tất cả trong 1 lần.
    const forms = cfForms(tool);
    if (!forms.length) return { error: CF_MULTI[tool].noColumnsError };
    const items = [];
    for (const f of forms) {
      const r = CF_MULTI[tool].toItem(f);
      if (r.error) return { error: r.error };
      items.push(r.item);
    }
    return { config: { tool, items } };
  }
  return { error: "Tool này chưa được hỗ trợ." };
}
// Bảng các dòng bị gắn cờ: cột đầu = số dòng thật trong file, ô lỗi tô màu.
function renderFlaggedTable(table, columns, flaggedRows) {
  // Phụ thuộc hàm (backend đoán ô sai): thêm cột "Gợi ý" ngay sau "Dòng" (đứng gần nên khỏi cuộn ngang; lý do đầy đủ ở tooltip) và ô "mốc
  // so sánh" (r.ref) tô nhạt. Các tool khác không có r.hint / r.ref nên bảng vẫn như cũ.
  const hasHint = flaggedRows.some((r) => r.hint);
  const head = `<thead><tr><th>Dòng</th>${hasHint ? "<th>Gợi ý</th>" : ""}${columns.map((c) => `<th>${escapeHtml(c)}</th>`).join("")}</tr></thead>`;
  const body = flaggedRows.map((r) => {
    const flagged = new Set(r.flagged);
    const ref = new Set(r.ref || []);
    const cells = r.cells.map((v, i) => {
      const cls = flagged.has(columns[i]) ? ' class="cf-flag"' : ref.has(columns[i]) ? ' class="cf-ref"' : "";
      return `<td${cls}>${escapeHtml(v)}</td>`;
    }).join("");
    const hint = hasHint ? `<td class="cf-hint" title="${escapeAttr((r.notes || []).join("\n"))}">${escapeHtml(r.hint || "")}</td>` : "";
    return `<tr><td>${r.row_number}</td>${hint}${cells}</tr>`;
  }).join("");
  table.innerHTML = head + `<tbody>${body}</tbody>`;
}
/* ----- Rule "Biểu thức": khung báo cách ĐỌC dữ liệu (cột nào thành kiểu gì) và số dòng bị BỎ QUA ----- */
const EXPR_KIND_VI = { num: "Số", date: "Ngày", text: "Chữ" };
// "%d/%m/%Y" -> "dd/mm/yyyy" cho người không quen ký hiệu strptime.
function humanDateFormat(fmt) {
  const map = { "%Y": "yyyy", "%y": "yy", "%m": "mm", "%d": "dd", "%H": "hh", "%M": "mi", "%S": "ss" };
  return String(fmt).replace(/%[A-Za-z]/g, (t) => map[t] || t);
}
function renderExprInfo(info) {
  const box = $("cf-expr-info");
  if (!info) { box.hidden = true; box.innerHTML = ""; return; }
  const total = info.total_rows;
  const skipped = info.skipped_rows;
  const bad = info.violating_rows;
  const q = (s) => `«${escapeHtml(s)}»`;
  const kind = (c) => EXPR_KIND_VI[c.type] + (c.date_format ? ` ${humanDateFormat(c.date_format)}` : "");
  const warns = [];
  if (total > 0 && skipped >= total) warns.push(["bad", "Mọi dòng đều chưa kiểm được, nên kết quả «0 lỗi» không có nghĩa là dữ liệu sạch."]);
  info.columns.forEach((c) => {
    if (c.readable === 0 && c.blank < total) { // có ô không trống mà không đọc được ô nào
      const how = c.type === "date"
        ? ` ${c.date_format ? `Đang đọc theo khuôn ${escapeHtml(humanDateFormat(c.date_format))}. ` : "Không khuôn ngày phổ biến nào khớp. "}Kiểm tra ô «Khuôn ngày» hoặc dùng ngay(cột, "%d/%m/%Y").`
        : "";
      warns.push(["bad", `Không đọc được ô nào của cột ${q(c.name)} thành ${EXPR_KIND_VI[c.type]}.${how}`]);
    }
  });
  if (skipped > 0) {
    const parts = info.columns.filter((c) => c.blank > 0 || c.unreadable > 0).map((c) => {
      const bits = [];
      if (c.blank) bits.push(`${c.blank} ô trống`);
      if (c.unreadable) bits.push(`${c.unreadable} ô không đọc được thành ${EXPR_KIND_VI[c.type]}${c.date_format ? ` (khuôn ${escapeHtml(humanDateFormat(c.date_format))})` : ""}`);
      return `${q(c.name)}: ${bits.join(", ")}`;
    });
    if (info.zero_division_rows) parts.push(`${info.zero_division_rows} dòng có phép chia cho 0`);
    warns.push(["warn", `Bỏ qua ${skipped}/${total} dòng vì chưa tính được${parts.length ? ": " + parts.join(" · ") : ""}. Xử lý ô trống / sai định dạng trước (nhóm Tự động) rồi nối tiếp.`]);
  }
  if (info.text_order_columns && info.text_order_columns.length) {
    warns.push(["warn", `Cột ${info.text_order_columns.map(q).join(", ")} đang được đọc là Chữ nên so thứ tự theo bảng chữ cái. Nếu đó là ngày hoặc số, hãy dùng ngay(cột, "%d/%m/%Y") hoặc so(cột).`]);
  }
  box.innerHTML =
    `<div class="cf-expr-summary"><span><b>${total}</b> dòng</span><span class="is-bad"><b>${bad}</b> vi phạm</span>` +
    `<span><b>${total - bad - skipped}</b> đạt</span><span class="${skipped ? "is-skip" : ""}"><b>${skipped}</b> bỏ qua</span></div>` +
    `<div class="cf-expr-cols"><span class="cf-expr-lbl">Cách đọc cột</span>${info.columns.map((c) => `<span class="cf-expr-col"><b>${escapeHtml(c.name)}</b> · ${escapeHtml(kind(c))}</span>`).join("")}</div>` +
    warns.map(([k, t]) => `<p class="cf-expr-warn is-${k}">${t}</p>`).join("");
  box.hidden = false;
}
// Câu tóm tắt phân tích Phụ thuộc hàm: mỗi cột phụ thuộc có bao nhiêu nhóm mâu thuẫn, nghi sai ở cột xác định (A) hay cột phụ thuộc (B).
function fdAnalysisText(fa) {
  if (!fa || !fa.rules) return "";
  const parts = fa.rules.filter((r) => r.groups > 0).map((r) => {
    const bits = [];
    if (r.determinant) bits.push(`${r.determinant} nhóm có vẻ là đối tượng khác nhau dùng chung «${fa.determinant}» (nghi sai «${fa.determinant}»)`);
    if (r.dependent) bits.push(`${r.dependent} nhóm nghi sai «${r.column}»`);
    if (r.unknown) bits.push(`${r.unknown} nhóm chưa xác định được`);
    return `${fa.rules.length > 1 ? `«${r.column}»: ` : ""}${bits.join(", ")}`;
  });
  return parts.length ? `Phân tích: ${parts.join(" · ")}.` : "";
}
$("cf-detect-btn").addEventListener("click", async () => {
  const T = TOOLSEC.cf;
  setError($(T.error), "");
  $("cf-handling").hidden = true;
  hideCfConfirm();
  $("cf-expr-info").hidden = true; // không để lại khung báo của lần phát hiện trước (kể cả khi lần này báo lỗi)
  const formData = new FormData();
  const fresh = !pipeUsable("cf");
  const inp = collectInput("cf", formData);
  if (inp.error) return setError($(T.error), inp.error);
  const built = buildCfConfig();
  if (built.error) return setError($(T.error), built.error);
  formData.append("mode", "detect");
  formData.append("config", JSON.stringify(built.config));
  // "Chữ ký" cấu hình + đầu vào LÚC GỬI (trước khi chờ server): người dùng sửa form trong lúc chờ thì lần sửa đó phải bị coi là "đã đổi".
  const sigAtSend = cfSignature();
  const data = await callBackend($("cf-detect-btn"), "Phát hiện", "/api/noise-tools/configured", formData, $(T.error));
  if (!data) return;
  const multi = Array.isArray(built.config.items) && Array.isArray(data.per_column);
  state.cf.detect = { data, config: built.config, inputLabel: inp.label, fresh, multi, sig: sigAtSend };
  state.cf.stale = false;
  const label = CF_TAB_LABEL[state.cf.tool];
  prepareCfHandling(multi, data, state.cf.tool);
  $(T.resultEmpty).hidden = true;
  $(T.resultCard).hidden = false;
  $(T.resultTag).textContent = multi ? `Phát hiện · ${label} · ${data.per_column.length} cột` : `Phát hiện · ${label}`;
  $(T.resultDims).textContent = `${data.flagged_rows_count} dòng lỗi / ${data.total_rows} dòng`;
  $(T.download).disabled = true;
  $(T.cont).hidden = true;
  const note = $("cf-result-note");
  renderExprInfo(data.expression_info);
  if (data.findings_count === 0) {
    $("cf-result-table-wrap").hidden = true;
    note.hidden = false;
    // Biểu thức mà còn dòng bị bỏ qua thì "0 lỗi" chưa chắc là sạch: nói rõ thay vì báo ✅ (lỗi cũ: sai khuôn ngày ra "0 lỗi" im lặng).
    const ei = data.expression_info;
    const unchecked = !!(ei && ei.skipped_rows > 0);
    note.textContent = unchecked
      ? `Không có dòng nào chắc chắn vi phạm, nhưng ${ei.skipped_rows}/${ei.total_rows} dòng chưa kiểm được (xem khung phía trên). Kết quả này chưa chắc là dữ liệu sạch.`
      : "Không phát hiện ô nào vi phạm với cấu hình này.";
    note.classList.add("is-only");
    note.classList.toggle("is-long", unchecked);
    setStatus($(T.status), unchecked ? `⚠ Không thấy dòng sai, nhưng ${ei.skipped_rows}/${ei.total_rows} dòng chưa kiểm được` : "✅ Không phát hiện lỗi nào · dữ liệu giữ nguyên", unchecked ? "is-warn" : "is-ok");
    if (multi) $("cf-handling").hidden = false; // vẫn cho xem bảng "cột nào 0 lỗi"
    if (data.result_text) {
      recordPipeStep(`${label} (không đổi)`, data.result_text, "csv", inp.label, fresh, inp.source);
      $(T.download).disabled = false;
      renderContinuePanel("cf");
      state.cf.detect.sig = cfSignature(); // recordPipeStep đổi đầu vào sang kết quả này: không tính là "đã đổi"
    }
    cfCheckStale();
    return;
  }
  $("cf-result-table-wrap").hidden = false;
  renderFlaggedTable($(T.resultTable), data.columns, data.flagged_rows);
  note.classList.remove("is-only");
  const noteParts = [];
  if (data.truncated) noteParts.push(`Chỉ hiện ${data.flagged_rows.length} dòng lỗi đầu tiên.`);
  if (data.flagged_rows.some((r) => r.hint)) {
    noteParts.push("Ô tô đậm = nghi sai · ô tô nhạt = mốc so sánh · rê chuột vào cột «Gợi ý» để xem lý do.");
    const analysis = fdAnalysisText(data.fd_analysis);
    if (analysis) noteParts.push(analysis);
  }
  note.hidden = !noteParts.length;
  note.classList.toggle("is-long", data.flagged_rows.some((r) => r.hint));
  note.textContent = noteParts.join(" ");
  if (multi) {
    const colsWithErrors = data.per_column.filter((p) => p.findings_count > 0).length;
    setStatus($(T.status), `${data.findings_count} ô lỗi ở ${colsWithErrors} cột · ${data.flagged_rows_count} dòng (tổng ${data.total_rows}). Chọn cách xử lý từng cột bên dưới.`, "is-ok");
  } else {
    // Phụ thuộc hàm nhiều cột phụ thuộc: kèm số dòng vi phạm của từng cột (cột nào 0 dòng thì không nhắc).
    const parts = (data.rule_breakdown || []).filter((b) => b.flagged_rows_count > 0).map((b) => `${b.column}: ${b.flagged_rows_count} dòng`);
    const byDep = parts.length ? ` Theo cột phụ thuộc — ${parts.join(" · ")}.` : "";
    setStatus($(T.status), `${data.findings_count} ô lỗi ở ${data.flagged_rows_count} dòng (tổng ${data.total_rows}).${byDep} Chọn cách xử lý bên dưới.`, "is-ok");
  }
  // Nhịp 2: danh sách cách xử lý do backend quyết theo kiểu cột × loại lỗi.
  const sel = $("cf-action");
  // Phụ thuộc hàm (có fd_plan): mặc định "— Chọn cách xử lý —" (không chọn sẵn cách nào đổi dữ liệu, cùng bài học Bước 5 cũ) + hiện xem trước tác động.
  // Rule thường (không phải Phụ thuộc hàm) tự dựng "kế hoạch" từ số dòng vi phạm để cũng có dòng xem trước "Sẽ xoá N dòng (a → b)".
  state.cf.fdPlan = data.fd_plan || { generic: true, remove_row: { rows: data.flagged_rows_count }, unresolved_groups: 0 };
  state.cf.fdTotalRows = data.total_rows;
  state.cf.fdDeterminant = data.fd_analysis ? data.fd_analysis.determinant : "";
  sel.innerHTML = '<option value="">— Chọn cách xử lý —</option>' +
    data.available_actions.map((a) => `<option value="${a}">${ACTION_LABELS[a] || a}</option>`).join("");
  renderCfActionPreview();
  $("cf-fixed-value-wrap").hidden = sel.value !== "fixed_value";
  setError($("cf-apply-error"), "");
  setStatus($("cf-apply-status"), "", "");
  $("cf-handling").hidden = false;
  cfCheckStale();
});
// ----- Báo "cấu hình đã đổi, bấm Phát hiện lại" -----
// Nút Áp dụng LUÔN dùng cấu hình lúc bấm Phát hiện (state.cf.detect.config), dù người dùng đã sửa form sau đó; bảng kết quả bên dưới
// cũng là của lần phát hiện đó. Nên khi form / đầu vào lệch khỏi lần Phát hiện cuối thì báo rõ và khoá Áp dụng cho tới khi Phát hiện lại.
// Chữ ký = cấu hình đang khai (hoặc lỗi nếu đang khai dở) + chữ ký đầu vào; sửa rồi sửa lại y như cũ thì không còn bị coi là "đã đổi".
function cfSignature() {
  const built = buildCfConfig();
  const src = cfInputSource();
  return JSON.stringify([built.error ? `lỗi:${built.error}` : built.config, src ? src.sig : null]);
}
function cfCheckStale() {
  const det = state.cf.detect;
  const note = $("cf-stale-note");
  const btn = $("cf-apply-btn");
  const stale = !!det && !$("cf-handling").hidden && det.sig !== cfSignature();
  note.hidden = !stale;
  if (stale) {
    hideCfConfirm(); // số liệu trong hộp xác nhận là của cấu hình cũ
    note.textContent = "⚠ Cấu hình hoặc dữ liệu đã đổi so với lần Phát hiện cuối. Bấm «Phát hiện» lại trước khi Áp dụng.";
    btn.disabled = true;
  } else if (state.cf.stale) {
    btn.disabled = false; // chỉ mở lại khi chính mình đã khoá (không đụng nút lúc đang chờ server trả lời)
  }
  state.cf.stale = stale;
}
// Sau khi các xử lý riêng của form (đổi cột, thêm/xoá form, nút trong form...) chạy xong mới so sánh.
["input", "change", "click"].forEach((evt) => $("section-config").addEventListener(evt, () => setTimeout(cfCheckStale, 0)));
// Xem trước tác động của cách xử lý đang chọn (chỉ Phụ thuộc hàm): số liệu lấy từ fd_plan backend trả lúc Phát hiện.
function renderCfActionPreview() {
  const box = $("cf-action-preview");
  const plan = state.cf.fdPlan;
  const action = $("cf-action").value;
  box.classList.remove("is-risk");
  if (!plan || !action) { box.hidden = true; box.textContent = ""; return; }
  const total = state.cf.fdTotalRows;
  const left = plan.unresolved_groups
    ? ` ${plan.unresolved_groups} nhóm chưa xác định được ô sai (hoà số lượng, hoặc nghi sai cột «${state.cf.fdDeterminant}») sẽ giữ nguyên để bạn tự xử lý.` : "";
  let text;
  if (action === "fix_to_majority") {
    text = plan.fix_to_majority.cells
      ? `Sẽ sửa ${plan.fix_to_majority.cells} ô về giá trị phổ biến nhất của nhóm; không xoá dòng nào.${left}`
      : `Không có ô nào sửa được tự động.${left}`;
  } else if (action === "remove_suspect_rows") {
    const n = plan.remove_suspect_rows.rows;
    text = n ? `Sẽ xoá ${n} dòng nghi sai (${total} → ${total - n} dòng).${left}` : `Không có dòng nào xoá được tự động.${left}`;
  } else if (action === "remove_row") {
    const n = plan.remove_row.rows;
    if (plan.generic) {
      text = `Sẽ xoá ${n} dòng vi phạm (${total} → ${total - n} dòng).`;
    } else {
      text = `Sẽ xoá ${n} dòng (${total} → ${total - n} dòng), gồm cả các dòng có thể là đúng.`;
      box.classList.add("is-risk");
    }
  } else {
    text = "Không đổi gì, chỉ để xem hoặc tải file.";
  }
  box.textContent = text;
  box.hidden = false;
}
$("cf-action").addEventListener("change", () => {
  $("cf-fixed-value-wrap").hidden = $("cf-action").value !== "fixed_value";
  renderCfActionPreview();
});
$("cf-apply-btn").addEventListener("click", async () => {
  const T = TOOLSEC.cf;
  const det = state.cf.detect;
  if (!det) return setError($("cf-apply-error"), 'Bấm "Phát hiện" trước.');
  setError($("cf-apply-error"), "");
  let applyExtra;
  let action = "";
  if (det.multi) {
    // Nhiều cột: mỗi cột có cách xử lý riêng trong bảng tổng hợp; cột để "Bỏ qua" / chưa chọn thì không gửi (không bị đụng tới).
    // Cột chọn "điền giá trị cố định" phải có giá trị (backend còn kiểm hợp kiểu cột: số nguyên / số).
    const actions = {};
    let invalid = "";
    document.querySelectorAll('#cf-multi [data-role="sum-action"]').forEach((sel) => {
      if (sel.value === "skip" || invalid) return;
      const column = sel.dataset.column;
      const spec = { action: sel.value };
      if (sel.value === "fixed_value") {
        const box = sel.closest(".cf-sum-row").querySelector('[data-role="sum-fixed"]');
        const value = box ? box.value.trim() : "";
        if (!value) { invalid = `Cột "${column}": chưa nhập giá trị cố định.`; return; }
        spec.fixed_value = value;
      }
      actions[column] = spec;
    });
    if (invalid) return setError($("cf-apply-error"), invalid);
    if (!Object.keys(actions).length) {
      // Tool "preselect" (không xoá dữ liệu) để mặc định cách xử lý nên "hết cột" nghĩa là người dùng chủ động chọn "Bỏ qua" cả loạt;
      // tool còn lại mặc định "— Chọn cách xử lý —" nên "hết cột" nghĩa là chưa chọn gì -- 2 trường hợp cần 2 câu nói khác nhau.
      const preselect = CF_MULTI[state.cf.tool] && CF_MULTI[state.cf.tool].preselect;
      return setError($("cf-apply-error"), preselect
        ? 'Chưa chọn cách xử lý cho cột nào (đang để "Bỏ qua" hết).'
        : "Chưa chọn cách xử lý cho cột nào. Chọn cách xử lý ở ít nhất 1 cột rồi bấm Áp dụng.");
    }
    applyExtra = { actions };
  } else {
    action = $("cf-action").value;
    if (!action) return setError($("cf-apply-error"), "Chọn cách xử lý trước khi bấm Áp dụng.");
    const fixedValue = $("cf-fixed-value").value;
    if (action === "fixed_value" && !fixedValue) return setError($("cf-apply-error"), "Chưa nhập giá trị cố định.");
    applyExtra = { action, fixed_value: fixedValue };
  }
  hideCfConfirm();
  // Có XOÁ DÒNG thì chạy thử trước (backend tính đúng như Áp dụng thật nhưng không trả file) rồi hỏi xác nhận bằng SỐ THẬT.
  // Các cách chỉ sửa giá trị (điền, kéo về biên...) không mất dòng nên áp dụng luôn, giống Bước 5 cũ.
  const removesRows = det.multi
    ? Object.values(applyExtra.actions).some((a) => a.action === "remove_row")
    : (action === "remove_row" || action === "remove_suspect_rows");
  if (removesRows) {
    const trial = await cfSendApply(applyExtra, true, $("cf-apply-btn"), "Áp dụng");
    if (!trial) return;
    if (trial.rows_removed > 0) {
      const before = trial.rows_before, after = trial.rows_after, n = trial.rows_removed;
      const risky = before > 0 && n / before >= 0.2;
      const maybeCorrect = !det.multi && action === "remove_row" && state.cf.fdPlan && !state.cf.fdPlan.generic;
      $("cf-confirm-text").textContent = `Sẽ xoá ${n} dòng (${before} → ${after} dòng).` +
        (maybeCorrect ? " Gồm cả các dòng có thể là đúng." : "") +
        (trial.cells_changed ? ` Đồng thời sửa ${trial.cells_changed} ô ở các cột khác.` : "") +
        (risky ? ` Đây là ${Math.round((n / before) * 100)}% số dòng, hãy xem lại cho chắc.` : "") +
        " Bấm «Xác nhận» thì mới xoá thật.";
      state.cf.pendingApply = { applyExtra, action };
      $("cf-confirm").hidden = false;
      return;
    }
    // Chạy thử báo không có dòng nào bị xoá (vd cách xử lý không đụng tới dòng nào): không cần hỏi, áp dụng luôn.
  }
  await cfFinishApply(applyExtra, action, $("cf-apply-btn"), "Áp dụng");
});
// Gửi lệnh Áp dụng lên backend. dryRun = true thì chỉ lấy số liệu (rows_before/after/removed, cells_changed), không có file.
// applyBusy báo cho nút Hoàn tác / Bắt đầu lại từ gốc biết đang có lệnh chạy dở (tránh đổi chuỗi nối tiếp giữa chừng).
async function cfSendApply(applyExtra, dryRun, btn, idleText) {
  const det = state.cf.detect;
  const formData = new FormData();
  const inp = collectInput("cf", formData);
  if (inp.error) { setError($("cf-apply-error"), inp.error); return null; }
  formData.append("mode", "apply");
  if (dryRun) formData.append("dry_run", "true");
  formData.append("config", JSON.stringify(Object.assign({}, det.config, applyExtra)));
  state.cf.applyBusy = true;
  try {
    const data = await callBackend(btn, idleText, "/api/noise-tools/configured", formData, $("cf-apply-error"));
    return data ? Object.assign(data, { _inp: inp }) : null;
  } finally {
    state.cf.applyBusy = false;
  }
}
// Áp dụng THẬT rồi hiện kết quả + ghi vào chuỗi nối tiếp (phần này trước đây nằm thẳng trong handler của nút Áp dụng).
async function cfFinishApply(applyExtra, action, btn, idleText) {
  const T = TOOLSEC.cf;
  const det = state.cf.detect;
  hideCfConfirm();
  const data = await cfSendApply(applyExtra, false, btn, idleText);
  if (!data) return;
  const inp = data._inp;
  const label = CF_TAB_LABEL[state.cf.tool];
  const colCount = data.preview_rows && data.preview_rows.length ? data.preview_rows[0].length : 0;
  $("cf-result-table-wrap").hidden = false;
  $("cf-result-note").hidden = true;
  $("cf-expr-info").hidden = true; // dữ liệu đã đổi, khung báo của lần phát hiện không còn đúng
  showResultTable("cf", label, data.preview_rows, tableDims(data.stats.final_row_count, colCount));
  $(T.download).disabled = false;
  $("cf-handling").hidden = true;
  setStatus($(T.status), det.multi
    ? `${statusFromStats(data.stats)} · đã xử lý ${(data.per_column || []).length} cột`
    : `${statusFromStats(data.stats)} · ${ACTION_LABELS[action] || action}`, "is-ok");
  recordPipeStep(label, data.result_text, "csv", inp.label, det.fresh, inp.source);
  renderContinuePanel("cf");
}
// ----- Hộp xác nhận xoá dòng -----
function hideCfConfirm() {
  $("cf-confirm").hidden = true;
  state.cf.pendingApply = null;
}
$("cf-confirm-yes").addEventListener("click", async () => {
  const pending = state.cf.pendingApply;
  if (!pending || !state.cf.detect) return hideCfConfirm();
  await cfFinishApply(pending.applyExtra, pending.action, $("cf-confirm-yes"), "Xác nhận xoá và áp dụng");
});
$("cf-confirm-no").addEventListener("click", hideCfConfirm);
// Đổi lựa chọn cách xử lý (hoặc giá trị cố định) sau khi hộp đã hiện thì số liệu trong hộp không còn đúng: ẩn hộp, bắt bấm Áp dụng lại.
["change", "input"].forEach((evt) => $("cf-handling").addEventListener(evt, hideCfConfirm));

// ====== Khởi động ======
// Hỗ trợ ?section=<tên khối> (home / guide / security / privacy / free-tools /
// convert) để mở thẳng đúng khối. Không có hoặc sai tên -> trang chủ.
(function initSectionFromQuery() {
  const requested = new URLSearchParams(window.location.search).get("section");
  if (SECTIONS.includes(requested)) state.section = requested;
})();

checkAuth();
checkBackendHealth();
activateTool("ft", state.ft.tool);
activateTool("cv", state.cv.tool);
activateTool("cf", state.cf.tool);
renderPipeStrips();
switchSection(state.section);
