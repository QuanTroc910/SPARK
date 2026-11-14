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
// 5 tool cần cấu hình, class-noise = 4 bước ở workspace-flow.js, profile = hồ
// sơ, free-tools, convert).
const SECTIONS = ["home", "guide", "security", "privacy", "config", "class-noise", "profile", "free-tools", "convert"];
const PUBLIC_SECTIONS = new Set(["home", "guide", "security", "privacy"]);

const state = {
  section: "home", // 1 trong SECTIONS -- khối đang hiện (mặc định: trang chủ)
  // Bộ nhớ NỐI TIẾP dùng chung cho cả 3 nhóm tool (xem phần "BA NHÓM TOOL").
  // originalText/Kind = kết quả ĐẦU TIÊN của chuỗi ("Bắt đầu lại từ gốc" quay
  // về đây), currentText/Kind = kết quả mới nhất = đầu vào của tool kế tiếp
  // (kind "csv" hoặc "json" -- JSON chỉ nối tiếp được sang JSON → CSV).
  pipe: { active: false, originalLabel: "", originalText: null, originalKind: "csv", currentText: null, currentKind: "csv", steps: [], forceNewUpload: false },
  // Trạng thái riêng từng nhóm: tool đang chọn, kiểu nhập, file đã chọn, bảng xem trước.
  // listView = danh sách của nút "Xem ..." sau lần chạy gần nhất: { kind: tên tool, data: dữ liệu backend trả, showing }
  // (kind "remove-duplicates" = các dòng trùng, "trim-whitespace" = các ô đã sửa; null = chưa có / đã bị xoá);
  // showing = khung 01 đang hiện danh sách đó thay cho đầu vào.
  ft: { tool: "remove-duplicates", inputMode: "file", selectedFile: null, rawPreviewActive: false, filePreview: null, listView: null,
        // Tool Sai định dạng: bảng kiểu dữ liệu từng cột. colTypes = [{name, guessed, guessedFmt, dtype, dateFormat}] (null = chưa có);
        // colState = idle|loading|ready|error; colSig = "chữ ký" đầu vào đã đọc cột (tránh đọc lại khi đầu vào không đổi);
        // colSeq/colPromise = chống chạy chồng; colCounts = {cột: số ô sai} của lần Chạy gần nhất (countsSig = chữ ký đầu vào lúc đó).
        colTypes: null, colState: "idle", colError: "", colSig: "", colSeq: 0, colPromise: null, colCounts: null, countsSig: "" },
  cv: { tool: "delimiter", inputMode: "file", selectedFile: null, rawPreviewActive: false, filePreview: null, lastResult: null },
  // cf thêm: columns/guessed đọc từ /api/noise-tools/inspect, detect = kết quả nhịp "Phát hiện".
  cf: { tool: "out-of-range", inputMode: "file", selectedFile: null, rawPreviewActive: false, filePreview: null, columns: [], guessed: {}, detect: null },
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
// 1 form dùng cho cả 2 chế độ -- chỉ đổi chữ (tiêu đề, nút, dòng chuyển chế
// độ, gợi ý độ dài) để không phải nhân đôi HTML.
function setAuthMode(mode) {
  authState.mode = mode;
  const isLogin = mode === "login";
  $("ws-auth-eyebrow").textContent = isLogin ? "[ Chào mừng trở lại ]" : "[ Bắt đầu ]";
  $("ws-auth-title").textContent = isLogin ? "Đăng nhập" : "Tạo tài khoản";
  $("ws-auth-desc").textContent = isLogin
    ? "Tiếp tục việc đang dở. Dữ liệu gắn với tài khoản của bạn, người khác không thấy được."
    : "Tải lên, làm sạch và xuất file. Mỗi tài khoản là 1 không gian riêng, không qua bên thứ ba.";
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
function PRIVACY_COLUMN() {
  return {
    t: "Riêng tư theo thiết kế",
    b: "File được backend Flask thật đọc để xử lý rồi xoá file tạm NGAY sau khi đọc xong, không giữ lại bản nào. Vẫn cần đăng nhập như mọi chỗ khác trong Denoise.",
  };
}

/* ----- Nhãn dùng chung ----- */
const TOOL_TAB_LABEL = {
  "remove-duplicates": "Xoá dòng trùng",
  "trim-whitespace": "Cắt khoảng trắng",
  "fill-blanks": "Điền/xoá ô trống",
  "remove-empty-rows": "Xoá dòng trống",
  "format-noise": "Sai định dạng",
};
const CV_TAB_LABEL = { delimiter: "Đổi delimiter CSV", "csv-to-json": "CSV → JSON", "json-to-csv": "JSON → CSV" };
const CF_TAB_LABEL = {
  "out-of-range": "Ngoài khoảng",
  outlier: "Giá trị bất thường",
  "inconsistent-category": "Không nhất quán",
  "missing-advanced": "Thiếu giá trị (nâng cao)",
  "cross-rule": "Rule liên cột",
};
const DTYPE_LABELS = {
  integer: "Số nguyên", float: "Số thực", text: "Văn bản", email: "Email",
  phone: "Số điện thoại", date: "Ngày tháng", category: "Nhóm (category)",
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
};
const DELIMITER_LABELS = { ",": "dấu phẩy (,)", ";": "dấu chấm phẩy (;)", "\t": "tab", "|": "dấu gạch đứng (|)" };
function delimiterLabel(d) {
  return DELIMITER_LABELS[d] || d;
}

/* ----- Nội dung trang (tiêu đề, mô tả, hình, 3 bước, 3 cột) từng tool ----- */
const TOOL_INFO = {
  "remove-duplicates": {
    headline: "XOÁ DÒNG TRÙNG<br>TRONG FILE CSV",
    desc: "Tìm và xoá các dòng lặp lại chỉ trong vài giây. So khớp trên mọi cột, hoặc chỉ những cột xác định 1 bản ghi (vd email) -- bản đầu tiên (hoặc cuối cùng) luôn được giữ lại.",
    mock: mockPair([[[]], [[]], [["is-hit", "is-hit", "is-hit"], { tag: "TRÙNG" }], [[]]], [[[]], [[]], [[]]], "-1 dòng"),
    steps: ["Thả file CSV/Excel vào, hoặc dán text.", "Chọn cột xác định trùng lặp (để trống = so toàn bộ cột).", "Xem số dòng đã xoá, rồi tải file đã làm sạch."],
    explainer: [
      { t: "Thế nào là trùng", b: "Mặc định, 1 dòng bị coi là trùng khi MỌI cột khớp y hệt dòng trước đó. Chọn cột cụ thể để coi 2 dòng là cùng 1 bản ghi dù các cột khác khác nhau." },
      { t: "Vì sao gần-trùng lọt lưới", b: `"an@x.com" và "AN@X.com" giống nhau với người nhưng khác nhau với máy. Bật "Bỏ qua hoa/thường" và "Bỏ qua khoảng trắng thừa" để bắt được cả 2 trường hợp đó.` },
      PRIVACY_COLUMN(),
    ],
  },
  "trim-whitespace": {
    headline: "CẮT KHOẢNG TRẮNG THỪA<br>TRONG FILE CSV",
    desc: "Cắt khoảng trắng vô hình làm 2 giá trị tưởng giống nhau mà máy tính lại coi là khác nhau: khoảng trắng đầu/cuối, non-breaking space, và ký tự zero-width.",
    mock: mockPair([[["is-hit"]], [["", "is-hit"]], [[]], [["", "", "is-hit"]]], [[["is-fixed"]], [["", "is-fixed"]], [[]], [["", "", "is-fixed"]]], "3 ô"),
    steps: ["Thả file CSV/Excel vào, hoặc dán text.", "Chọn có gộp khoảng trắng lặp lại/xoá ký tự vô hình hay không.", "Xem số ô đã đổi, rồi tải file đã làm sạch."],
    explainer: [
      { t: "Những gì bị xoá", b: `Khoảng trắng đầu/cuối MỌI ô (kể cả non-breaking space) luôn bị cắt. "Gộp khoảng trắng lặp lại" biến "a␣␣b" thành "a␣b"; "Xoá ký tự vô hình" bỏ các ký tự zero-width không nhìn thấy nhưng vẫn tính là ký tự.` },
      { t: "Vì sao quan trọng", b: `1 khoảng trắng thừa biến "Hà Nội " thành giá trị KHÁC "Hà Nội" -- lookup/so khớp sẽ thất bại, kiểm tra trùng lặp sẽ bỏ sót. Cắt khoảng trắng trước giúp mọi bước xử lý sau đáng tin hơn.` },
      PRIVACY_COLUMN(),
    ],
  },
  "fill-blanks": {
    headline: "ĐIỀN / XOÁ Ô TRỐNG<br>TRONG FILE CSV",
    desc: "Thay ô trống bằng giá trị bạn chọn, điền theo giá trị ở dòng gần nhất phía trên, hoặc xoá hẳn cả dòng thiếu -- áp dụng cho ĐÚNG 1 cột bạn chỉ định.",
    mock: mockPair([[[]], [["is-hit"]], [[]], [["is-hit"]]], [[[]], [["is-fixed"]], [[]], [["is-fixed"]]], "Điền ↓"),
    steps: ["Thả file CSV/Excel vào, hoặc dán text.", "Gõ tên cột cần xử lý, chọn cách điền/xoá.", "Xem số ô đã đổi (hoặc số dòng đã xoá), rồi tải file."],
    explainer: [
      { t: "3 cách điền/xoá", b: `"Điền theo giá trị phía trên" copy giá trị KHÔNG trống GẦN NHẤT phía trên xuống (hợp với báo cáo theo nhóm, mỗi nhóm chỉ ghi tên 1 lần). "Điền giá trị cố định" dùng ĐÚNG 1 giá trị bạn gõ (vd "Không rõ"). "Xoá cả dòng" bỏ hẳn dòng thiếu.` },
      { t: "Cần điền thông minh hơn?", b: `Tool "Thiếu giá trị (nâng cao)" ở nhóm Cần cấu hình điền theo trung bình / trung vị / KNN / giá trị phổ biến nhất tuỳ kiểu cột -- bấm "Xử lý tiếp" sau khi chạy là sang được ngay.` },
      PRIVACY_COLUMN(),
    ],
  },
  "remove-empty-rows": {
    headline: "XOÁ DÒNG TRỐNG<br>TRONG FILE CSV",
    desc: "Xoá các dòng không có giá trị nào cả, kể cả dòng chỉ toàn khoảng trắng/dấu phẩy rỗng -- tuỳ chọn thêm: xoá luôn cột nào trống hoàn toàn từ trên xuống dưới.",
    mock: mockPair([[[]], [[], { removed: true, tag: "TRỐNG" }], [[]], [[], { removed: true, tag: "TRỐNG" }], [[]]], [[[]], [[]], [[]]], "-2 dòng"),
    steps: ["Thả file CSV/Excel vào, hoặc dán text.", "Chọn có xoá luôn cột trống hoàn toàn hay không.", "Tải file không còn dòng/cột trống."],
    explainer: [
      { t: "Thế nào là trống", b: "1 dòng bị coi là trống khi MỌI cột đều trống hoặc chỉ chứa khoảng trắng -- dòng còn ít nhất 1 giá trị thì vẫn được giữ lại, dù phần lớn ô khác trống." },
      { t: "Cột trống hoàn toàn", b: "File xuất ra đôi khi có cột chưa từng được điền gì (lỗi mẫu/thiếu dữ liệu nguồn). Bật tuỳ chọn này để xoá luôn cột đó, không chỉ dòng." },
      PRIVACY_COLUMN(),
    ],
  },
  "format-noise": {
    headline: "BẮT Ô SAI ĐỊNH DẠNG<br>TRONG FILE CSV",
    desc: "Email thiếu @, số điện thoại lẫn chữ, ngày ghi sai khuôn, số nguyên có chữ cái. Denoise tự đoán kiểu của từng cột rồi quét mọi cột một lượt, gắn cờ ô không khớp. Đoán sai kiểu cột nào thì bạn chọn lại ngay dưới bảng dữ liệu.",
    mock: mockPair([[[]], [["", "is-hit"]], [[]], [["", "is-hit"]]], [[[]], [["", "is-fixed"]], [[]], [["", "is-fixed"]]], "2 ô"),
    steps: ["Thả file CSV/Excel vào, hoặc dán text.", "Xem kiểu Denoise đoán cho từng cột, sửa nếu đoán sai.", "Chọn chỉ báo, để trống ô sai hoặc xoá dòng, rồi bấm Chạy."],
    explainer: [
      { t: "Kiểu nào kiểm tra gì", b: "Email cần dạng ten@mien; số điện thoại chỉ chữ số và vài ký tự +, -, khoảng trắng; ngày phải đúng khuôn (vd %Y-%m-%d); số nguyên/số thực phải ép được thành số. Cột kiểu Nhóm hoặc Văn bản không có khuôn nên không bị kiểm tra." },
      { t: "Kiểu cột được đoán thế nào", b: "Denoise nhìn giá trị thật của cột chứ không nhìn tên cột: từ 90% giá trị khớp khuôn nào thì đoán cột là kiểu đó, nên vài ô sai không làm hỏng việc đoán và vẫn bị bắt. Đoán sai kiểu cột nào thì sửa ở bảng ngay dưới dữ liệu đầu vào." },
      PRIVACY_COLUMN(),
    ],
  },
};

const CV_INFO = {
  delimiter: {
    headline: "ĐỔI DELIMITER<br>CỦA FILE CSV",
    desc: "Đổi dấu phẩy thành chấm phẩy, tab, gạch đứng hoặc ngược lại mà không làm hỏng các giá trị có dấu ngoặc kép.",
    mock: mockTextPair("export_eu.csv", ["ma;ten;gia", ["A01;But bi;12,50", true], "A02;Kep giay;3,00"], "export.csv", ["ma,ten,gia", ['A01,But bi,"12,50"', true], 'A02,Kep giay,"3,00"'], "; → ,"),
    dropTitle: "Thả file CSV vào đây", accept: ".csv,.txt",
    steps: ["Thêm file; delimiter hiện tại được tự nhận diện.", "Chọn delimiter mới bạn cần.", "Tải file đã đổi về."],
    explainer: [
      { t: "Vì sao delimiter khác nhau", b: "Ở nơi dùng dấu phẩy làm dấu thập phân, Excel lưu CSV bằng chấm phẩy. Hệ thống khác lại xuất tab hoặc gạch đứng. Công cụ nhập thường chỉ nhận đúng 1 loại, nên phải đổi file chứ không sửa tay." },
      { t: "Dấu ngoặc kép được lo sẵn", b: "Giá trị có chứa delimiter mới, dấu ngoặc kép hoặc xuống dòng sẽ tự được bọc trong ngoặc kép; giá trị chỉ bọc vì delimiter cũ thì được ghi lại bình thường." },
      PRIVACY_COLUMN(),
    ],
  },
  "csv-to-json": {
    headline: "CHUYỂN CSV<br>SANG JSON",
    desc: "Biến CSV thành JSON sạch, khoá theo tên cột, tuỳ chọn tự nhận diện số và true/false.",
    mock: mockTextPair("products.csv", ["sku,name,price", ["A-100,But bi,3.2", true], "A-101,Kep giay,0.5"], "products.json", ["[", "  {", ['    "sku": "A-100",', true], ['    "name": "But bi",', true], ['    "price": 3.2', true], "  },", "  …", "]"], "→ JSON"),
    dropTitle: "Thả file CSV vào đây", accept: ".csv,.txt",
    steps: ["Thêm file CSV.", "Chọn Objects hay Arrays, có ép kiểu số / true-false không.", "Sao chép JSON hoặc tải về dạng .json."],
    explainer: [
      { t: "Khoá lấy từ dòng tiêu đề", b: 'Mỗi dòng thành 1 object, khoá là tên cột. Tên cột trống thành "column_1", tên trùng được thêm hậu tố như "name_2" nên không mất giá trị nào.' },
      { t: "Kiểu dữ liệu không bất ngờ", b: "Bật ép kiểu thì số và true/false thành số và boolean JSON, ô trống thành null. Giá trị có số 0 ở đầu như mã bưu điện, số điện thoại vẫn giữ nguyên dạng chuỗi." },
      PRIVACY_COLUMN(),
    ],
  },
  "json-to-csv": {
    headline: "CHUYỂN JSON<br>SANG CSV",
    desc: "Làm phẳng mảng JSON hoặc JSON Lines thành CSV mở được bằng bảng tính, object lồng nhau thành cột.",
    mock: mockTextPair("users.json", ["[", "  {", '    "id": 1,', ['    "address": {', true], ['      "city": "Ha Noi"', true], "    }", "  }", "]"], "users.csv", [["id,address.city", true], "1,Ha Noi"], "→ CSV"),
    dropTitle: "Thả file JSON vào đây", accept: ".json,.jsonl,.txt",
    steps: ["Dán JSON hoặc thả file .json / .jsonl.", 'Xem lại cột: trường lồng nhau thành tên như "address.city".', "Tải CSV về."],
    explainer: [
      { t: "Nhận những gì", b: "1 mảng object, 1 object đơn, mảng của mảng, hoặc JSON Lines (mỗi dòng 1 object). Cột xuất theo thứ tự khoá xuất hiện lần đầu; khoá thiếu thành ô trống." },
      { t: "Dữ liệu lồng nhau", b: 'Object lồng nhau được làm phẳng thành tên cột nối bằng dấu chấm, vd "address.city". Mảng bên trong được ghi nguyên dạng JSON trong 1 ô nên không mất dữ liệu.' },
      PRIVACY_COLUMN(),
    ],
  },
};

const CF_INFO = {
  "out-of-range": {
    headline: "BẮT GIÁ TRỊ<br>NGOÀI KHOẢNG",
    desc: "Tuổi 210, lương âm, điểm 11/10. Bạn khai min và max hợp lý cho một cột số, Denoise gắn cờ mọi giá trị nằm ngoài rồi kéo về biên, điền lại hoặc xoá dòng theo ý bạn.",
    mock: mockPair([[[]], [["is-hit"]], [[]], [[]], [["is-hit"]]], [[[]], [["is-fixed"]], [[]], [[]], [["is-fixed"]]], "Kéo về biên"),
    steps: ["Chọn file và cột số cần kiểm tra.", "Gõ giá trị nhỏ nhất và lớn nhất hợp lệ, bấm Phát hiện.", "Chọn kéo về biên / điền lại / xoá dòng, bấm Áp dụng."],
    explainer: [
      { t: "Khoảng là do bạn quyết", b: "Không có khoảng đúng cho mọi file: tuổi nhân viên khác tuổi bệnh nhân. Denoise không tự đoán, bạn khai theo hiểu biết về dữ liệu của mình." },
      { t: "Kéo về biên nghĩa là gì", b: "Giá trị nhỏ hơn min thành min, lớn hơn max thành max. Giữ được dòng, chỉ sửa đúng ô lỗi. Khác với Giá trị bất thường (outlier) dựa trên thống kê, ở đây biên là con số cứng bạn chọn." },
      PRIVACY_COLUMN(),
    ],
  },
  outlier: {
    headline: "BẮT GIÁ TRỊ<br>BẤT THƯỜNG",
    desc: "Không cần biết trước khoảng hợp lý. Denoise tính biên từ chính dữ liệu bằng IQR hoặc Z-score, gắn cờ các giá trị lệch hẳn so với phần còn lại của cột.",
    mock: mockPair([[[]], [[]], [["", "", "is-hit"]], [[]], [[]]], [[[]], [[]], [["", "", "is-fixed"]], [[]], [[]]], "1 ô"),
    steps: ["Chọn file và cột số.", "Chọn IQR (mặc định, hệ số 1.5) hoặc Z-score (3 độ lệch chuẩn), bấm Phát hiện.", "Xem giá trị bị gắn cờ; kéo về biên, điền lại, xoá dòng hoặc giữ nguyên nếu đó là dữ liệu thật."],
    explainer: [
      { t: "IQR và Z-score", b: "IQR lấy khoảng giữa tứ phân vị 1 và 3, nhân hệ số 1.5 làm biên; bền với dữ liệu lệch. Z-score đo số độ lệch chuẩn so với trung bình; hợp với dữ liệu phân phối chuông." },
      { t: "Bất thường không chắc là sai", b: "Một đơn hàng rất lớn có thể là thật. Vì vậy luôn xem bảng ô bị gắn cờ trước, và có lựa chọn Giữ nguyên để chỉ ghi nhận mà không sửa." },
      PRIVACY_COLUMN(),
    ],
  },
  "inconsistent-category": {
    headline: "CHUẨN HOÁ GIÁ TRỊ<br>KHÔNG NHẤT QUÁN",
    desc: '"Nam", "nam", "NAM", " Nam " cùng một nghĩa nhưng là bốn giá trị khác nhau với máy. Bạn khai danh sách giá trị chuẩn, Denoise tìm biến thể gần giống và tự đưa về đúng giá trị chuẩn.',
    mock: mockPair([[["is-hit"]], [[]], [["is-hit"]], [[]]], [[["is-fixed"]], [[]], [["is-fixed"]], [[]]], "Chuẩn hoá"),
    steps: ["Chọn file và cột nhóm (category).", "Gõ danh sách giá trị chuẩn, cách nhau bởi dấu phẩy, bấm Phát hiện.", "Xem các biến thể bị gắn cờ rồi bấm Áp dụng để chuẩn hoá."],
    explainer: [
      { t: "Thế nào là gần giống", b: "Denoise so độ giống chuỗi (sau khi bỏ hoa/thường và khoảng trắng) với từng giá trị chuẩn. Ngưỡng mặc định 0.85: đủ bắt lỗi gõ nhẹ, đủ chặt để không gộp nhầm hai nhóm khác nhau." },
      { t: "Giá trị không khớp gì cả", b: "Một giá trị không giống bất kỳ giá trị chuẩn nào vẫn bị gắn cờ nhưng không tự sửa, vì không biết đưa về đâu. Hãy xem lại danh sách chuẩn hoặc xử lý tay." },
      PRIVACY_COLUMN(),
    ],
  },
  "missing-advanced": {
    headline: "ĐIỀN GIÁ TRỊ THIẾU<br>THEO KIỂU CỘT",
    desc: 'Ô trống, "NA", "null", "-", "?" đều là thiếu. Khác tool Điền ô trống đơn giản, ở đây cách điền phụ thuộc kiểu cột: trung bình, trung vị, KNN cho cột số; giá trị phổ biến nhất cho cột nhóm.',
    mock: mockPair([[[]], [["", "is-hit"]], [[]], [["", "is-hit"]]], [[[]], [["", "is-fixed"]], [[]], [["", "is-fixed"]]], "Impute"),
    steps: ["Chọn file và cột cần điền; kiểu cột đã đoán sẵn.", "Bấm Phát hiện để xem các ô thiếu.", "Chọn cách điền hợp với kiểu cột, bấm Áp dụng."],
    explainer: [
      { t: "KNN điền thế nào", b: "Với mỗi ô thiếu, Denoise tìm 5 dòng giống nhất theo các cột số khác (khoảng cách Euclid sau chuẩn hoá) rồi lấy trung bình của chúng. Viết tay, không phụ thuộc thư viện ngoài." },
      { t: "Vì sao cột email không có impute", b: "Bảng quyết định kiểu cột × loại lỗi chỉ cho phép đoán giá trị với cột số và cột nhóm. Email, số điện thoại, ngày tháng chỉ có xoá dòng hoặc điền cố định." },
      PRIVACY_COLUMN(),
    ],
  },
  "cross-rule": {
    headline: "BẮT MÂU THUẪN<br>GIỮA HAI CỘT",
    desc: "Ngày nghỉ việc trước ngày vào làm, tổng tiền không bằng số lượng nhân đơn giá, một mã nhân viên gắn với hai tên. Bạn khai quan hệ, Denoise kiểm tra từng dòng.",
    mock: mockPair([[[]], [["is-hit", "", "is-hit"]], [[]], [[]]], [[[]], [[]], [[]]], "-1 dòng"),
    steps: ["Chọn file; chọn một trong bốn kiểu rule.", "Khai cột và quan hệ (so sánh, nếu-thì, công thức, phụ thuộc hàm), bấm Phát hiện.", "Xem dòng vi phạm; xoá dòng vi phạm hoặc giữ nguyên để rà tay."],
    explainer: [
      { t: "Bốn kiểu rule", b: "So sánh: cột A < cột B. Nếu-thì: nếu cột X = giá trị thì cột Y phải thoả điều kiện. Công thức: tong == gia * so_luong. Phụ thuộc hàm: mỗi giá trị cột A chỉ được đi với đúng một giá trị cột B." },
      { t: "Công thức an toàn", b: "Công thức được phân tích thành cây cú pháp và chỉ cho phép bốn phép tính, số và tên cột. Không có eval(), không gọi được hàm nào. Ô thiếu hoặc không ép được kiểu được bỏ qua, không tính là vi phạm." },
      PRIVACY_COLUMN(),
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
  if (g === "ft") refreshFtColumnTypes();
}
async function handleFileSelected(g, file) {
  if (g === "ft") clearListView(); // đầu vào đổi -> danh sách của lần chạy trước không còn đúng
  const st = state[g];
  st.selectedFile = file;
  if (g === "ft") refreshFtColumnTypes(); // tool Sai định dạng: đọc cột + đoán kiểu của file vừa chọn
  const sizeText = `${(file.size / 1024).toFixed(1)} KB`;
  if (g === "cf") {
    // Tool cần cấu hình: nhờ backend đọc (có tên cột + kiểu đoán sẵn + 20 dòng
    // xem trước) -- hoạt động cả với Excel, và là nguồn cho dropdown chọn cột.
    await cfInspect({ file }, file.name);
    return;
  }
  if (g === "cv" && (!/\.(csv|txt)$/i.test(file.name) || st.tool === "json-to-csv")) {
    showRawPreview(g, file.name, sizeText, null, 'File JSON -- bấm "Convert" để xem kết quả dạng bảng.');
    return;
  }
  if (!/\.csv$/i.test(file.name) && g === "ft") {
    showRawPreview(g, file.name, sizeText, null, 'Không xem trước được file Excel trong trình duyệt -- bấm "Chạy" để xem kết quả.');
    return;
  }
  let text;
  try {
    text = await readFileAsText(file);
  } catch (err) {
    showRawPreview(g, file.name, sizeText, null, "Không đọc được file để xem trước -- vẫn chạy được bình thường.");
    return;
  }
  const { rows, totalDataRows } = naiveParseCsvPreview(text, PREVIEW_ROWS);
  showRawPreview(g, file.name, tableDims(totalDataRows, rows.length ? rows[0].length : 0), rows, totalDataRows > PREVIEW_ROWS ? `Xem trước ${PREVIEW_ROWS}/${totalDataRows} dòng đầu.` : "");
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
  if (st.inputMode === "file") {
    if (!st.selectedFile) return { error: "Chưa chọn file nào." };
    formData.append("file", st.selectedFile);
    return { label: st.selectedFile.name };
  }
  const text = $(T.paste).value;
  if (!text.trim()) return { error: "Chưa dán nội dung nào." };
  formData.append("text", text);
  return { label: "văn bản dán tay" };
}

/* ----- Dải "đang nối tiếp" + 2 nút trên dải (dùng chung 3 nhóm) ----- */
function renderPipeStrips() {
  const p = state.pipe;
  const stepsText = p.steps.length ? ` · đã qua: ${p.steps.map((s) => s.label).join(" → ")}` : " · chưa xử lý bước nào";
  Object.keys(TOOLSEC).forEach((g) => {
    const strip = $(TOOLSEC[g].strip);
    strip.hidden = !p.active;
    if (p.active) strip.querySelector(".pipe-strip-text").innerHTML = `📄 Đang dùng: <strong>${escapeHtml(p.originalLabel)}</strong>${escapeHtml(stepsText)}`;
    renderInputArea(g);
  });
  refreshFtColumnTypes(); // đầu vào nối tiếp đổi -> bảng kiểu cột của tool Sai định dạng cập nhật theo
}
document.querySelectorAll(".pipe-new-file-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    state.pipe.forceNewUpload = true;
    Object.keys(TOOLSEC).forEach((g) => { state[g].rawPreviewActive = false; });
    renderPipeStrips();
  });
});
document.querySelectorAll(".pipe-reset-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    const p = state.pipe;
    p.currentText = p.originalText;
    p.currentKind = p.originalKind;
    p.steps = [];
    p.forceNewUpload = false;
    renderPipeStrips();
    Object.keys(TOOLSEC).forEach(resetResult);
    if (state.section === "config") cfInspect({ text: p.currentText }, p.originalLabel);
  });
});
// Ghi nhận 1 bước vừa xong: kết quả thành đầu vào kế tiếp của cả 3 nhóm.
// fresh = lần chạy này dùng file/text MỚI (không phải kết quả bước trước) ->
// bắt đầu 1 chuỗi mới, bỏ chuỗi cũ.
function recordPipeStep(label, text, kind, inputLabel, fresh) {
  const p = state.pipe;
  if (!p.active || fresh) {
    p.active = false;
    p.active = true;
    p.originalText = text;
    p.originalKind = kind;
    p.originalLabel = inputLabel;
    p.steps = [];
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
  if (stats.cells_changed > 0) parts.push(`đã sửa ${stats.cells_changed} ô`);
  // Tool Sai định dạng ở chế độ "chỉ báo" (không đổi gì): nói rõ đã tìm thấy bao nhiêu ô sai.
  if (stats.flagged_cell_count !== undefined && !stats.removed_row_count && !stats.cells_changed) {
    parts.push(stats.flagged_cell_count > 0 ? `tìm thấy ${stats.flagged_cell_count} ô sai định dạng` : "không thấy ô nào sai định dạng");
  }
  if (stats.columns_removed) parts.push(`đã xoá ${stats.columns_removed} cột`);
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
    { icon: "∅", tool: "missing-advanced", sub: "Mean · median · KNN · mode" },
    { icon: "⋈", tool: "cross-rule", sub: "Mâu thuẫn giữa 2 cột" },
  ] },
  { key: "convert", label: "Convert", g: "cv", attr: "data-convert-tool", items: [
    { icon: "⇄", tool: "delimiter" }, { icon: "{ }", tool: "csv-to-json" }, { icon: "{ }", tool: "json-to-csv" },
  ] },
  { key: "auto", label: "Tự động", g: "ft", attr: "data-tool", items: [
    { icon: "⧉", tool: "remove-duplicates" }, { icon: "⇥", tool: "trim-whitespace" },
    { icon: "▦", tool: "fill-blanks" }, { icon: "☰", tool: "remove-empty-rows" },
    { icon: "@", tool: "format-noise" },
  ] },
];
function renderContinuePanel(g) {
  const panel = $(TOOLSEC[g].cont);
  const pills = panel.querySelector(".continue-pills");
  const list = panel.querySelector(".continue-list");
  const isJson = state.pipe.currentKind === "json"; // sau CSV → JSON chỉ còn JSON → CSV nhận được
  panel.hidden = false;
  list.innerHTML = "";
  pills.innerHTML = CONTINUE_GROUPS.map((gr) =>
    `<button type="button" class="continue-pill" data-category="${gr.key}"${isJson && gr.key !== "convert" ? " disabled" : ""}>${gr.label}</button>`
  ).join("");
  pills.querySelectorAll(".continue-pill").forEach((pill) => {
    pill.addEventListener("click", () => {
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
// Mang kết quả hiện tại sang tool đích (có thể ở nhóm khác).
function startChain(g, tool) {
  switchSection(TOOLSEC[g].section);
  activateTool(g, tool);
  state.pipe.forceNewUpload = false;
  renderPipeStrips();
  const fromText = `📥 Đang dùng kết quả của bước trước (${state.pipe.steps.map((s) => s.label).join(" → ")}).`;
  setStatus($(TOOLSEC[g].status), fromText, "is-ok");
  if (g === "cf") cfInspect({ text: state.pipe.currentText }, state.pipe.originalLabel, { keepPreview: true });
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
  if (g === "ft") refreshFtColumnTypes();
}
Object.keys(TOOLSEC).forEach((g) => {
  const T = TOOLSEC[g];
  document.querySelectorAll(`#${T.tabs} .convert-tab`).forEach((btn) => btn.addEventListener("click", () => activateTool(g, btn.dataset.tool)));
  wireInputToggle($(T.toggle), $(T.dropzone), $(T.paste), (mode) => { state[g].inputMode = mode; if (g === "ft") refreshFtColumnTypes(); });
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
$("opt-action").addEventListener("change", () => {
  $("opt-fixed-value-wrap").hidden = $("opt-action").value !== "fixed_value";
});
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
  } else if (tool === "fill-blanks") {
    const column = $("opt-column").value.trim();
    if (!column) return setError($(T.error), "Chưa gõ tên cột cần xử lý.");
    const action = $("opt-action").value;
    if (action === "fixed_value" && !$("opt-fixed-value").value) return setError($(T.error), "Chưa nhập giá trị để điền vào ô trống.");
    formData.append("column", column);
    formData.append("action", action);
    formData.append("fixed_value", $("opt-fixed-value").value);
  } else if (tool === "remove-empty-rows") {
    formData.append("also_remove_empty_columns", $("opt-remove-empty-columns").checked ? "true" : "false");
  } else if (tool === "format-noise") {
    // Đang đọc cột (vd vừa nối tiếp từ bước trước) thì chờ xong để gửi đúng bảng kiểu cột mới nhất.
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
  recordPipeStep(TOOL_TAB_LABEL[tool], data.result_text, "csv", inp.label, fresh);
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
    note: 'Cột "Dòng" là số thứ tự dòng trong đầu vào · các dòng cùng nhóm trùng nằm cạnh nhau · "Giữ" = bản được giữ lại, "Xoá" = bản đã bị xoá.',
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
    note: 'Cột "Dòng" là số thứ tự dòng trong đầu vào · ô tô nền là ô đã bị sửa, hiện giá trị TRƯỚC khi sửa · ␣ dấu cách · ⇥ tab · ⏎ xuống dòng · ⍽ non-breaking space · ⟨ZW⟩ ký tự vô hình.',
    // Ô đã sửa tô nền (class is-changed).
    tableOpts: (d) => ({ rowNumbers: d.row_numbers, cellClasses: d.cell_changed.map((row) => row.map((c) => (c ? "is-changed" : ""))) }),
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
    note: 'Cột "Dòng" là số thứ tự dòng trong đầu vào · ô tô nền là ô sai định dạng so với kiểu cột đang chọn, giữ nguyên giá trị gốc. Kiểu cột sai thì sửa ở bảng bên dưới rồi bấm Chạy lại.',
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
  fillPreviewCard("ft", cfg.tag, cfg.dims(d), d.rows, (shownAll ? "" : cfg.truncated(d)) + cfg.note, cfg.tableOpts(d));
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
  if (!st.colTypes) { box.innerHTML = '<p class="ft-coltypes-msg">Chọn file hoặc dán dữ liệu ở trên: Denoise sẽ đọc tên cột và đoán kiểu của từng cột ở đây, bạn sửa được.</p>'; return; }
  const counts = st.colCounts || {};
  box.innerHTML =
    `<div class="ft-coltypes-bar"><span class="ft-coltypes-title">Kiểu dữ liệu từng cột</span><span class="ft-coltypes-meta">${st.colTypes.length} cột</span>` +
    '<button type="button" class="btn btn-ghost btn-small" data-role="reset">↺ Về kiểu tự đoán</button></div>' +
    '<p class="ft-coltypes-hint">Denoise đoán kiểu mỗi cột từ giá trị thật. Chỉ cột kiểu Số nguyên, Số thực, Email, Số điện thoại, Ngày tháng mới bị kiểm tra khuôn. Đoán sai thì chọn lại.</p>' +
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
// Dán text: đọc cột sau khi người dùng ngừng gõ ~600ms.
let ftPasteTimer = null;
$("ft-paste-input").addEventListener("input", () => {
  clearTimeout(ftPasteTimer);
  ftPasteTimer = setTimeout(refreshFtColumnTypes, 600);
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
  const data = await callBackend($("convert-run-btn"), "Convert", url, formData, $(T.error));
  if (!data) return;
  state.cv.lastResult = data;
  $(T.resultEmpty).hidden = true;
  $(T.download).disabled = false;
  if (tool === "csv-to-json") {
    $(T.resultCard).hidden = true;
    $("convert-json-card").hidden = false;
    $("convert-json-dims").textContent = `${data.record_count} record`;
    $("convert-result-text").textContent = data.result_text;
    setStatus($(T.status), `✅ ${data.record_count} record (delimiter: ${delimiterLabel(data.used_delimiter)})`, "is-ok");
    recordPipeStep(CV_TAB_LABEL[tool], data.result_text, "json", inp.label, fresh);
  } else {
    $("convert-json-card").hidden = true;
    const colCount = data.preview_rows && data.preview_rows.length ? data.preview_rows[0].length : 0;
    // row_count của backend đếm CẢ dòng tiêu đề -> số dòng dữ liệu = row_count - 1.
    const dataRows = Math.max(0, data.row_count - 1);
    showResultTable("cv", CV_TAB_LABEL[tool], data.preview_rows, tableDims(dataRows, colCount));
    setStatus($(T.status), tool === "delimiter"
      ? `✅ ${dataRows} dòng dữ liệu · đã nhận diện delimiter gốc: ${delimiterLabel(data.used_from_delimiter)}`
      : `✅ ${dataRows} dòng dữ liệu · ${data.columns.length} cột`, "is-ok");
    recordPipeStep(CV_TAB_LABEL[tool], data.result_text, "csv", inp.label, fresh);
  }
  renderContinuePanel("cv");
});

/* ============================================================
   CẦN CẤU HÌNH -- đọc cột từ backend, dựng tuỳ chọn theo tool, 2 nhịp
   Phát hiện -> Áp dụng (POST /api/noise-tools/configured, mode=detect|apply)
   ============================================================ */
const CF_DTYPES = {
  "out-of-range": ["integer", "float"],
  outlier: ["integer", "float"],
  "inconsistent-category": ["category"],
  "missing-advanced": ["integer", "float", "category", "text", "email", "phone", "date"],
};
const OPERATORS = ["<", "<=", ">", ">=", "==", "!="];

// Đọc tên cột + kiểu đoán sẵn (+ xem trước) từ backend cho file/text hiện tại.
async function cfInspect(source, label, opts) {
  opts = opts || {};
  const fd = new FormData();
  if (source.file) fd.append("file", source.file);
  else fd.append("text", source.text || "");
  let response, data;
  try {
    response = await fetch("/api/noise-tools/inspect", { method: "POST", body: fd });
    data = await response.json();
  } catch (err) {
    setError($("cf-error"), "Không gọi được backend để đọc cột.");
    return;
  }
  if (!response.ok) {
    state.cf.columns = [];
    state.cf.guessed = {};
    renderCfOptions();
    if (source.file) showRawPreview("cf", label, `${(source.file.size / 1024).toFixed(1)} KB`, null, data.error || "Không đọc được file.");
    else setError($("cf-error"), data.error || "Không đọc được nội dung.");
    return;
  }
  state.cf.columns = data.columns;
  state.cf.guessed = data.guessed_dtypes || {};
  renderCfOptions();
  if (source.file && !opts.keepPreview) {
    const note = data.row_count > PREVIEW_ROWS ? `Xem trước ${PREVIEW_ROWS}/${data.row_count} dòng đầu · ${data.columns.length} cột đã đọc được.` : `${data.columns.length} cột đã đọc được.`;
    showRawPreview("cf", label, tableDims(data.row_count, data.columns.length), data.preview_rows, note);
  }
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
function cfDtypeSelect(allowed, selected) {
  const opts = allowed.map((d) => `<option value="${d}"${d === selected ? " selected" : ""}>${DTYPE_LABELS[d]}</option>`).join("");
  return `<div class="field"><label for="cf-dtype">Kiểu dữ liệu kỳ vọng</label><select class="select" id="cf-dtype">${opts}</select></div>`;
}
function cfOperatorSelect(id) {
  return `<select class="select" id="${id}">${OPERATORS.map((o) => `<option value="${o}">${o}</option>`).join("")}</select>`;
}
function cfValueTypeSelect(id, selected) {
  return `<select class="select" id="${id}">${[["number", "Số"], ["date", "Ngày"], ["text", "Chữ"]].map(([v, l]) => `<option value="${v}"${v === selected ? " selected" : ""}>${l}</option>`).join("")}</select>`;
}
// Kiểu mặc định cho 1 cột = kiểu backend đoán nếu tool cho phép, không thì kiểu đầu danh sách.
function cfDefaultDtype(column, allowed) {
  const guessed = state.cf.guessed[column];
  return allowed.includes(guessed) ? guessed : allowed[0];
}
function renderCfOptions() {
  const tool = state.cf.tool;
  const wrap = $("cf-options");
  const cols = state.cf.columns;
  const firstCol = cols[0] || "";
  if (tool === "cross-rule") {
    wrap.innerHTML = `
      <div class="field">
        <label>Kiểu rule</label>
        <div class="ft-seg" data-seg-for="cf-rule-type">
          <button type="button" class="is-active" data-value="compare">So sánh</button>
          <button type="button" data-value="conditional">Nếu – thì</button>
          <button type="button" data-value="formula">Công thức</button>
          <button type="button" data-value="functional_dependency">Phụ thuộc hàm</button>
        </div>
        <select class="select" id="cf-rule-type" hidden>
          <option value="compare">So sánh</option><option value="conditional">Nếu – thì</option>
          <option value="formula">Công thức</option><option value="functional_dependency">Phụ thuộc hàm</option>
        </select>
      </div>
      <div id="cf-rule-fields"></div>`;
    wireSegmented(wrap.querySelector(".ft-seg"));
    $("cf-rule-type").addEventListener("change", renderCfRuleFields);
    renderCfRuleFields();
    return;
  }
  const allowed = CF_DTYPES[tool];
  const dtype = cfDefaultDtype(firstCol, allowed);
  let extra = "";
  if (tool === "out-of-range") {
    extra = `<div class="cf-row"><div class="field"><label for="cf-min">Nhỏ nhất hợp lệ</label><input class="input" id="cf-min" type="number" step="any" placeholder="vd: 18" /></div><div class="field"><label for="cf-max">Lớn nhất hợp lệ</label><input class="input" id="cf-max" type="number" step="any" placeholder="vd: 65" /></div></div><p class="hint-note">Để trống 1 bên = không chặn bên đó</p>`;
  } else if (tool === "outlier") {
    extra = `<div class="cf-row"><div class="field"><label>Phương pháp</label><div class="ft-seg" data-seg-for="cf-outlier-method"><button type="button" class="is-active" data-value="iqr">IQR</button><button type="button" data-value="zscore">Z-score</button></div><select class="select" id="cf-outlier-method" hidden><option value="iqr">IQR</option><option value="zscore">Z-score</option></select></div><div class="field"><label for="cf-outlier-threshold">Ngưỡng</label><input class="input" id="cf-outlier-threshold" type="number" step="any" value="1.5" /></div></div><p class="hint-note">IQR thường dùng 1.5 · Z-score thường dùng 3</p>`;
  } else if (tool === "inconsistent-category") {
    extra = `<div class="field"><label for="cf-categories">Danh sách giá trị chuẩn (cách nhau bởi dấu phẩy)</label><textarea class="input" id="cf-categories" rows="2" placeholder="vd: Nam, Nữ"></textarea></div><div class="field"><label for="cf-similarity">Ngưỡng giống nhau (0.5 – 1)</label><input class="input" id="cf-similarity" type="number" step="0.01" min="0.5" max="1" value="0.85" /></div>`;
  } else if (tool === "missing-advanced") {
    extra = `<p class="hint-note">Thiếu = ô trống, "NA", "null", "none", "?", "-". Cách điền hợp lệ phụ thuộc kiểu cột bạn chọn.</p>`;
  }
  wrap.innerHTML = cfColumnSelect("cf-column", "Cột cần kiểm tra", firstCol) + cfDtypeSelect(allowed, dtype) + extra;
  wrap.querySelectorAll(".ft-seg[data-seg-for]").forEach(wireSegmented);
  // Đổi cột -> kiểu tự theo kiểu đoán sẵn của cột đó (vẫn sửa tay được).
  $("cf-column").addEventListener("change", () => {
    $("cf-dtype").value = cfDefaultDtype($("cf-column").value, allowed);
    $("cf-dtype").dispatchEvent(new Event("change"));
  });
  $("cf-dtype").addEventListener("change", () => {
    const w = $("cf-date-format-wrap");
    if (w) w.hidden = $("cf-dtype").value !== "date";
  });
  const method = $("cf-outlier-method");
  if (method) method.addEventListener("change", () => { $("cf-outlier-threshold").value = method.value === "zscore" ? "3" : "1.5"; });
}
function renderCfRuleFields() {
  const type = $("cf-rule-type").value;
  const box = $("cf-rule-fields");
  const cols = state.cf.columns;
  const c = (id, label, sel) => cfColumnSelect(id, label, sel || cols[0] || "");
  if (type === "compare") {
    box.innerHTML = `<div class="cf-row-3">${c("cf-col-a", "Cột A")}<div class="field"><label>&nbsp;</label>${cfOperatorSelect("cf-operator")}</div>${c("cf-col-b", "Cột B", cols[1])}</div>
      <div class="cf-row"><div class="field"><label for="cf-value-type">So sánh theo kiểu</label>${cfValueTypeSelect("cf-value-type", "number")}</div><div class="field"><label for="cf-rule-date-format">Khuôn ngày (nếu kiểu Ngày)</label><input class="input mono" id="cf-rule-date-format" value="%Y-%m-%d" /></div></div>
      <p class="hint-note">Vi phạm = dòng mà A <i>không</i> thoả quan hệ với B. Ô thiếu/không ép được kiểu bị bỏ qua.</p>`;
  } else if (type === "conditional") {
    box.innerHTML = `<p class="hint-note">NẾU</p><div class="cf-row-3">${c("cf-if-col", "Cột điều kiện")}<div class="field"><label>&nbsp;</label>${cfOperatorSelect("cf-if-op")}</div><div class="field"><label for="cf-if-value">Giá trị</label><input class="input" id="cf-if-value" placeholder="vd: Nam" /></div></div>
      <div class="field"><label for="cf-if-type">Kiểu giá trị điều kiện</label>${cfValueTypeSelect("cf-if-type", "text")}</div>
      <p class="hint-note">THÌ</p><div class="cf-row-3">${c("cf-then-col", "Cột kết quả", cols[1])}<div class="field"><label>&nbsp;</label>${cfOperatorSelect("cf-then-op")}</div><div class="field"><label for="cf-then-value">Giá trị</label><input class="input" id="cf-then-value" placeholder="vd: 0" /></div></div>
      <div class="cf-row"><div class="field"><label for="cf-then-type">Kiểu giá trị kết quả</label>${cfValueTypeSelect("cf-then-type", "number")}</div><div class="field"><label for="cf-rule-date-format">Khuôn ngày (nếu kiểu Ngày)</label><input class="input mono" id="cf-rule-date-format" value="%Y-%m-%d" /></div></div>`;
  } else if (type === "formula") {
    box.innerHTML = `<div class="field"><label for="cf-formula">Công thức (tên cột, số, + - * /, một phép so sánh)</label><input class="input mono" id="cf-formula" placeholder="vd: tong == so_luong * don_gia" /></div>
      <div class="field"><label for="cf-tolerance">Sai số cho phép khi so bằng</label><input class="input" id="cf-tolerance" type="number" step="any" value="0.01" /></div>
      <p class="hint-note">Cột có sẵn: ${cols.length ? cols.map(escapeHtml).join(", ") : "(chọn file trước)"}</p>`;
  } else {
    box.innerHTML = `<div class="cf-row">${c("cf-det-col", "Cột xác định (A)")}${c("cf-dep-col", "Cột phụ thuộc (B)", cols[1])}</div>
      <p class="hint-note">Mỗi giá trị A chỉ được đi với đúng 1 giá trị B (vd ma_nv → ten). Không dùng cho B là kết quả giao dịch lặp lại.</p>`;
  }
}
// Gom tuỳ chọn trên màn hình thành JSON gửi backend. Trả { error } hoặc { config }.
function buildCfConfig() {
  const tool = state.cf.tool;
  if (!state.cf.columns.length) return { error: "Chưa đọc được cột nào. Chọn file hoặc dán text trước." };
  const num = (id) => { const v = $(id) ? $(id).value.trim() : ""; return v === "" ? null : Number(v); };
  if (tool === "cross-rule") {
    const rule = { rule_type: $("cf-rule-type").value };
    if (rule.rule_type === "compare") {
      Object.assign(rule, { column_a: $("cf-col-a").value, operator: $("cf-operator").value, column_b: $("cf-col-b").value, value_type: $("cf-value-type").value, date_format: $("cf-rule-date-format").value || null });
      if (rule.column_a === rule.column_b) return { error: "Cột A và cột B phải khác nhau." };
    } else if (rule.rule_type === "conditional") {
      Object.assign(rule, { if_column: $("cf-if-col").value, if_operator: $("cf-if-op").value, if_value: $("cf-if-value").value, if_value_type: $("cf-if-type").value, then_column: $("cf-then-col").value, then_operator: $("cf-then-op").value, then_value: $("cf-then-value").value, then_value_type: $("cf-then-type").value, date_format: $("cf-rule-date-format").value || null });
      if (!rule.if_value || !rule.then_value) return { error: "Nhập đủ giá trị ở cả vế NẾU và THÌ." };
    } else if (rule.rule_type === "formula") {
      rule.formula = $("cf-formula").value.trim();
      rule.tolerance = num("cf-tolerance") === null ? 0.01 : num("cf-tolerance");
      if (!rule.formula) return { error: "Chưa nhập công thức." };
    } else {
      Object.assign(rule, { determinant_column: $("cf-det-col").value, dependent_column: $("cf-dep-col").value });
      if (rule.determinant_column === rule.dependent_column) return { error: "Hai cột phải khác nhau." };
    }
    return { config: { tool, rule } };
  }
  const column = $("cf-column").value;
  const dtype = $("cf-dtype").value;
  const params = {};
  if (tool === "out-of-range") {
    params.min_value = num("cf-min");
    params.max_value = num("cf-max");
    if (params.min_value === null && params.max_value === null) return { error: "Nhập ít nhất 1 trong 2 giá trị nhỏ nhất / lớn nhất." };
    if (params.min_value !== null && params.max_value !== null && params.min_value > params.max_value) return { error: "Giá trị nhỏ nhất đang lớn hơn giá trị lớn nhất." };
  }
  if (tool === "outlier") {
    params.outlier_method = $("cf-outlier-method").value;
    params.outlier_threshold = num("cf-outlier-threshold") === null ? 1.5 : num("cf-outlier-threshold");
  }
  if (tool === "inconsistent-category") {
    const cats = $("cf-categories").value.split(",").map((s) => s.trim()).filter(Boolean);
    if (!cats.length) return { error: "Nhập ít nhất 1 giá trị chuẩn." };
    params.valid_categories = cats;
    params.category_similarity_threshold = num("cf-similarity") === null ? 0.85 : num("cf-similarity");
  }
  return { config: { tool, column, dtype, params } };
}
// Bảng các dòng bị gắn cờ: cột đầu = số dòng thật trong file, ô lỗi tô màu.
function renderFlaggedTable(table, columns, flaggedRows) {
  const head = `<thead><tr><th>Dòng</th>${columns.map((c) => `<th>${escapeHtml(c)}</th>`).join("")}</tr></thead>`;
  const body = flaggedRows.map((r) => {
    const flagged = new Set(r.flagged);
    const cells = r.cells.map((v, i) => `<td${flagged.has(columns[i]) ? ' class="cf-flag"' : ""}>${escapeHtml(v)}</td>`).join("");
    return `<tr><td>${r.row_number}</td>${cells}</tr>`;
  }).join("");
  table.innerHTML = head + `<tbody>${body}</tbody>`;
}
$("cf-detect-btn").addEventListener("click", async () => {
  const T = TOOLSEC.cf;
  setError($(T.error), "");
  $("cf-handling").hidden = true;
  const formData = new FormData();
  const fresh = !pipeUsable("cf");
  const inp = collectInput("cf", formData);
  if (inp.error) return setError($(T.error), inp.error);
  const built = buildCfConfig();
  if (built.error) return setError($(T.error), built.error);
  formData.append("mode", "detect");
  formData.append("config", JSON.stringify(built.config));
  const data = await callBackend($("cf-detect-btn"), "Phát hiện", "/api/noise-tools/configured", formData, $(T.error));
  if (!data) return;
  state.cf.detect = { data, config: built.config, inputLabel: inp.label, fresh };
  const label = CF_TAB_LABEL[state.cf.tool];
  $(T.resultEmpty).hidden = true;
  $(T.resultCard).hidden = false;
  $(T.resultTag).textContent = `Phát hiện · ${label}`;
  $(T.resultDims).textContent = `${data.flagged_rows_count} dòng lỗi / ${data.total_rows} dòng`;
  $(T.download).disabled = true;
  $(T.cont).hidden = true;
  const note = $("cf-result-note");
  if (data.findings_count === 0) {
    $("cf-result-table-wrap").hidden = true;
    note.hidden = false;
    note.textContent = "Không phát hiện ô nào vi phạm với cấu hình này.";
    note.classList.add("is-only");
    setStatus($(T.status), "✅ Không phát hiện lỗi nào · dữ liệu giữ nguyên", "is-ok");
    if (data.result_text) {
      recordPipeStep(`${label} (không đổi)`, data.result_text, "csv", inp.label, fresh);
      $(T.download).disabled = false;
      renderContinuePanel("cf");
    }
    return;
  }
  $("cf-result-table-wrap").hidden = false;
  renderFlaggedTable($(T.resultTable), data.columns, data.flagged_rows);
  note.classList.remove("is-only");
  note.hidden = !data.truncated;
  note.textContent = data.truncated ? `Chỉ hiện ${data.flagged_rows.length} dòng lỗi đầu tiên.` : "";
  setStatus($(T.status), `⚑ ${data.findings_count} ô lỗi ở ${data.flagged_rows_count} dòng (tổng ${data.total_rows}). Chọn cách xử lý bên dưới.`, "is-ok");
  // Nhịp 2: danh sách cách xử lý do backend quyết theo kiểu cột × loại lỗi.
  const sel = $("cf-action");
  sel.innerHTML = data.available_actions.map((a) => `<option value="${a}">${ACTION_LABELS[a] || a}</option>`).join("");
  $("cf-fixed-value-wrap").hidden = sel.value !== "fixed_value";
  setError($("cf-apply-error"), "");
  setStatus($("cf-apply-status"), "", "");
  $("cf-handling").hidden = false;
});
$("cf-action").addEventListener("change", () => {
  $("cf-fixed-value-wrap").hidden = $("cf-action").value !== "fixed_value";
});
$("cf-apply-btn").addEventListener("click", async () => {
  const T = TOOLSEC.cf;
  const det = state.cf.detect;
  if (!det) return setError($("cf-apply-error"), 'Bấm "Phát hiện" trước.');
  setError($("cf-apply-error"), "");
  const action = $("cf-action").value;
  const fixedValue = $("cf-fixed-value").value;
  if (action === "fixed_value" && !fixedValue) return setError($("cf-apply-error"), "Chưa nhập giá trị cố định.");
  const formData = new FormData();
  const inp = collectInput("cf", formData);
  if (inp.error) return setError($("cf-apply-error"), inp.error);
  formData.append("mode", "apply");
  formData.append("config", JSON.stringify(Object.assign({}, det.config, { action, fixed_value: fixedValue })));
  const data = await callBackend($("cf-apply-btn"), "Áp dụng", "/api/noise-tools/configured", formData, $("cf-apply-error"));
  if (!data) return;
  const label = CF_TAB_LABEL[state.cf.tool];
  const colCount = data.preview_rows && data.preview_rows.length ? data.preview_rows[0].length : 0;
  $("cf-result-table-wrap").hidden = false;
  $("cf-result-note").hidden = true;
  showResultTable("cf", label, data.preview_rows, tableDims(data.stats.final_row_count, colCount));
  $(T.download).disabled = false;
  $("cf-handling").hidden = true;
  setStatus($(T.status), `${statusFromStats(data.stats)} · ${ACTION_LABELS[action] || action}`, "is-ok");
  recordPipeStep(label, data.result_text, "csv", inp.label, det.fresh);
  renderContinuePanel("cf");
});

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
