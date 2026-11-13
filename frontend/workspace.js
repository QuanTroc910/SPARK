"use strict";

/* ============================================================
   workspace.js -- logic cho trang workspace.html.

   ĐÃ GỘP (xem comment đầu workspace.html): phần thân trang giờ có 6 KHỐI
   cùng tồn tại trên 1 trang -- trang chủ, Guide, Bảo mật, Quyền riêng tư
   (bước 5, công khai), #section-free-tools (trước ở tools.js) và
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
// Bảng dữ liệu kiểu CYD: cột ĐẦU TIÊN là số thứ tự dòng (1-based, chữ mờ,
// có kẻ dọc ngăn -- xem .cyd-table trong workspace.css), các cột sau là dữ
// liệu thật. Dùng chung cho bảng xem trước, bảng kết quả Free Tools và
// bảng kết quả Convert.
function renderPreviewTable(table, rows) {
  if (!rows || !rows.length) {
    table.innerHTML = "";
    return;
  }
  const [header, ...body] = rows;
  table.innerHTML =
    "<thead><tr><th>Dòng</th>" + header.map((h) => `<th>${escapeHtml(h)}</th>`).join("") + "</tr></thead>" +
    "<tbody>" +
    body.map((row, i) => `<tr><td>${i + 1}</td>` + row.map((cell) => `<td>${escapeHtml(cell)}</td>`).join("") + "</tr>").join("") +
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
// CÔNG KHAI (bước 5): chưa đăng nhập vẫn xem được. 2 khối sau cần đăng nhập.
const SECTIONS = ["home", "guide", "security", "privacy", "free-tools", "convert"];
const PUBLIC_SECTIONS = new Set(["home", "guide", "security", "privacy"]);

const state = {
  section: "home", // 1 trong SECTIONS -- khối đang hiện (mặc định: trang chủ)
  ft: {
    tool: "remove-duplicates", // khớp ĐÚNG hậu tố route /api/noise-tools/<tool>
    inputMode: "file",
    selectedFile: null,
    // true khi đang hiện bảng xem trước dữ liệu GỐC (thay cho ô kéo-thả) --
    // xem showFtRawPreview()/hideFtRawPreview()/renderFtInputArea().
    rawPreviewActive: false,
    filePreview: null, // {label, dims, rows, note} của file đã chọn, xem showFtRawPreview()
    activeContinueCategory: null,
    // "Nối tiếp" trong CHÍNH khối Free Tools (chạy nhiều tool liên tiếp mà
    // không cần tải file về/tải lên lại) -- xem showFtResult() bên dưới.
    pipeline: { active: false, originalText: null, originalLabel: "", currentText: null, steps: [], forceNewUpload: false },
  },
  cv: {
    tool: "delimiter", // "delimiter" | "csv-to-json" | "json-to-csv"
    inputMode: "file",
    selectedFile: null,
    rawPreviewActive: false,
    filePreview: null, // {label, dims, rows, note} -- giống state.ft.filePreview
    lastResult: null,
  },
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
  // Đăng xuất xong về trang chủ ở trạng thái khách (giống CYD), không hiện
  // thẳng form đăng nhập nữa -- muốn đăng nhập lại thì bấm nút ở header.
  setAuthMode("login");
  authState.user = null;
  switchSection("home");
  onLoggedOut();
  window.scrollTo(0, 0);
});
$("open-profile-btn").addEventListener("click", () => {
  window.location.href = "index.html?open=profile";
});
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
  // Viền màu nhấn (.is-current) cho pill của "vùng" đang mở: Product chứa
  // Free Tools + Convert, Guide là pill riêng. Trang chủ/Bảo mật/Riêng tư:
  // không pill nào sáng.
  $("ws-product-btn").classList.toggle("is-current", section === "free-tools" || section === "convert");
  $("ws-nav-guide").classList.toggle("is-current", section === "guide");
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

// Mọi link TĨNH có data-tool (cột "Tự động" trong mega menu + chân trang) --
// chuyển sang khối Free Tools + đúng tab. data-convert-tool -- chuyển sang
// khối Convert + đúng tab. Cả 2 đều CHUYỂN TẠI CHỖ (không điều hướng đi
// đâu), xem activateFtTool()/activateCvTool() định nghĩa bên dưới. Các link
// trong panel "Xử lý tiếp" được tạo SAU lúc này nên gắn listener riêng ở
// renderContinuePanel().
document.querySelectorAll("a[data-tool]").forEach((a) => {
  a.addEventListener("click", (e) => {
    e.preventDefault();
    switchSection("free-tools");
    activateFtTool(a.dataset.tool);
    setProductMenuOpen(false);
  });
});
document.querySelectorAll("a[data-convert-tool]").forEach((a) => {
  a.addEventListener("click", (e) => {
    e.preventDefault();
    switchSection("convert");
    activateCvTool(a.dataset.convertTool);
    setProductMenuOpen(false);
  });
});

// Chân trang: nút "Lên đầu trang" + link "Đăng xuất" (dùng chung hành vi với
// nút Đăng xuất ở header).
$("ws-backtop").addEventListener("click", () => window.scrollTo({ top: 0, behavior: "smooth" }));
$("footer-logout-link").addEventListener("click", (e) => {
  e.preventDefault();
  $("logout-btn").click();
});

/* ============================================================
   KHỐI: FREE TOOLS -- gộp từ tools.js, giữ nguyên toàn bộ logic, chỉ đổi
   tên phần tử trùng ID sang tiền tố "ft-" (xem quy ước đầu file) + đổi tên
   hàm thêm "Ft" để phân biệt với khối Convert bên dưới.
   ============================================================ */

/* Hình minh hoạ TRƯỚC/SAU kiểu CYD: 2 bảng mini có nhãn đen đè mép trên-trái,
   mỗi dòng có số thứ tự (hoặc 1 thẻ đen nhỏ như "TRÙNG"/"TRỐNG" ở dòng bị
   xử lý), 3 thanh đen thay cho chữ; ô lỗi tô màu nhấn, dòng bị xoá gạch
   chéo mờ. Bao quanh là 4 dấu ngoặc góc (.tool-mock-frame). */
function mockRow(cellClasses, opts) {
  const o = opts || {};
  // Luôn vẽ đủ 3 cột để 2 bảng trước/sau thẳng hàng nhau.
  const classes = [cellClasses[0] || "", cellClasses[1] || "", cellClasses[2] || ""];
  const cells = classes.map((c) => `<span class="tool-mock-cell${c ? " " + c : ""}"></span>`).join("");
  const num = o.tag ? `<span class="tool-mock-tag">${o.tag}</span>` : `<span class="tool-mock-num">${o.n}</span>`;
  return `<div class="tool-mock-row${o.removed ? " is-removed" : ""}">${num}${cells}</div>`;
}
// rows: mảng các phần tử [cellClasses, opts] -- số thứ tự dòng tự đánh 1, 2, 3...
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

const TOOL_INFO = {
  "remove-duplicates": {
    headline: "XOÁ DÒNG TRÙNG<br>TRONG FILE CSV",
    desc: "Tìm và xoá các dòng lặp lại chỉ trong vài giây. So khớp trên mọi cột, hoặc chỉ những cột xác định 1 bản ghi (vd email) -- bản đầu tiên (hoặc cuối cùng) luôn được giữ lại.",
    mock: mockPair(
      [[[]], [[]], [["is-hit", "is-hit", "is-hit"], { tag: "TRÙNG" }], [[]]],
      [[[]], [[]], [[]]],
      "-1 dòng"
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
      [[["is-hit"]], [["", "is-hit"]], [[]], [["", "", "is-hit"]]],
      [[["is-fixed"]], [["", "is-fixed"]], [[]], [["", "", "is-fixed"]]],
      "3 ô"
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
      [[[]], [["is-hit"]], [[]], [["is-hit"]]],
      [[[]], [["is-fixed"]], [[]], [["is-fixed"]]],
      "Điền ↓"
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
      [[[]], [[], { removed: true, tag: "TRỐNG" }], [[]], [[], { removed: true, tag: "TRỐNG" }], [[]]],
      [[[]], [[]], [[]]],
      "-2 dòng"
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
  // Đường dẫn "Trang chủ / Free Tools / <tên tool>" ở đầu trang đổi theo tool.
  $("ft-crumb-tool").textContent = TOOL_TAB_LABEL[tool];
  $("tool-hero").innerHTML = `
    <div class="tool-hero-grid">
      <div>
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
  handleFtFileSelected(file);
});

/* ====== Bảng xem trước dữ liệu GỐC (chưa xử lý) -- MỚI: đọc nhanh nội dung
   file NGAY LÚC CHỌN để hiện bảng xem trước trong khung "01 ĐẦU VÀO", THAY
   cho ô kéo-thả (xem ảnh mẫu CYD người dùng gửi). Đọc bằng FileReader thuần
   JS -- CHỈ ĐỂ HIỂN THỊ, không tính toán/phát hiện noise gì ở đây cả, xử lý
   THẬT vẫn luôn gửi file/text lên backend Flask như từ trước giờ (đúng
   nguyên tắc "không có bộ máy JS riêng" của dự án, xem CLAUDE.md). Bộ tách
   CSV ở đây CỐ TÌNH đơn giản (chỉ split theo dấu phẩy, không xử lý dấu
   ngoặc kép bao quanh giá trị có dấu phẩy) vì chỉ phục vụ XEM TRƯỚC, không
   phải bộ phân tích CSV thật (đó là việc của backend). ====== */
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
async function handleFtFileSelected(file) {
  const isCsv = /\.csv$/i.test(file.name);
  if (!isCsv) {
    // File Excel (.xlsx/.xls) -- không đọc được dạng văn bản thuần trong
    // trình duyệt (cần thư viện riêng mới giải mã được định dạng nhị phân
    // này), nên chỉ hiện dòng xác nhận đã chọn, KHÔNG có bảng xem trước.
    showFtRawPreview(file.name, `${(file.size / 1024).toFixed(1)} KB`, null, "Không xem trước được file Excel trong trình duyệt -- bấm \"Chạy\" để xem kết quả.");
    return;
  }
  let text;
  try {
    text = await readFileAsText(file);
  } catch (err) {
    showFtRawPreview(file.name, `${(file.size / 1024).toFixed(1)} KB`, null, "Không đọc được file để xem trước -- vẫn bấm \"Chạy\" được bình thường.");
    return;
  }
  const { rows, totalDataRows } = naiveParseCsvPreview(text, 20);
  const colCount = rows.length ? rows[0].length : 0;
  showFtRawPreview(file.name, tableDims(totalDataRows, colCount), rows, totalDataRows > 20 ? `Xem trước 20/${totalDataRows} dòng đầu.` : "");
}
// label = thẻ đen bên trái thanh trên (tên file), dims = chữ mờ bên phải
// ("N dòng × M cột" hoặc dung lượng file nếu không đọc được).
function showFtRawPreview(label, dims, rows, note) {
  state.ft.rawPreviewActive = true;
  // Nhớ lại nội dung xem trước của FILE ĐÃ CHỌN -- vì bảng xem trước dùng
  // chung với chế độ pipeline (renderFtPipelinePreview() ghi đè), khi quay
  // lại chế độ chọn file thì đổ lại từ đây, không cần đọc lại file.
  state.ft.filePreview = { label, dims, rows, note };
  renderFtInputArea();
}
// Đổ nội dung vào bảng xem trước (dùng cho CẢ file vừa chọn LẪN đầu vào của
// pipeline, xem renderFtPipelinePreview()). Ghi chú (note) khi KHÔNG có bảng
// thì chiếm cả khung với nền gạch chéo (.is-only), có bảng thì chỉ là 1 dòng
// nhỏ dưới bảng.
function fillFtPreviewCard(label, dims, rows, note) {
  const hasTable = !!(rows && rows.length);
  $("ft-raw-preview-label").textContent = label;
  $("ft-raw-preview-dims").textContent = dims || "";
  $("ft-raw-preview-table-wrap").hidden = !hasTable;
  if (hasTable) renderPreviewTable($("ft-raw-preview-table"), rows);
  const noteEl = $("ft-raw-preview-note");
  noteEl.hidden = !note;
  noteEl.textContent = note || "";
  noteEl.classList.toggle("is-only", !hasTable);
}
// Chế độ nối tiếp (pipeline đang chạy): khung 01 KHÔNG để trống mà hiện
// ĐẦU VÀO của lần chạy kế tiếp = kết quả của bước trước (pipeline.currentText),
// thẻ đen = tên file gốc, nút "Đổi file" ẩn (đã có "Tải file khác" trên dải
// pipeline). Tách CSV chỉ để hiển thị, giống naiveParseCsvPreview().
function renderFtPipelinePreview() {
  const p = state.ft.pipeline;
  const { rows, totalDataRows } = naiveParseCsvPreview(p.currentText || "", 20);
  const colCount = rows.length ? rows[0].length : 0;
  const stepsText = p.steps.length ? `Đầu vào hiện tại = kết quả sau: ${p.steps.map((s) => s.label).join(" → ")}` : "";
  fillFtPreviewCard(p.originalLabel, tableDims(totalDataRows, colCount), rows, stepsText);
}
function hideFtRawPreview() {
  state.ft.rawPreviewActive = false;
  state.ft.filePreview = null;
  state.ft.selectedFile = null;
  $("ft-file-input").value = "";
  renderFtInputArea();
}
$("ft-change-file-btn").addEventListener("click", hideFtRawPreview);

// ====== Khu vực nhập liệu (toggle File/Dán text, ô kéo-thả, ô dán text,
// bảng xem trước) -- gom hiển thị/ẩn vào 1 hàm DUY NHẤT để không rải logic
// if/else lặp lại ở nhiều nơi (renderFtPipelineStrip() gọi hàm này mỗi khi
// trạng thái pipeline đổi, showFtRawPreview()/hideFtRawPreview() cũng gọi). ======
function renderFtInputArea() {
  const p = state.ft.pipeline;
  const showUpload = !p.active || p.forceNewUpload; // false = đang dùng pipeline nối tiếp
  if (!showUpload) {
    // Pipeline: khung 01 hiện đầu vào của lần chạy kế tiếp, ẩn mọi ô chọn file.
    renderFtPipelinePreview();
    $("ft-input-toggle").hidden = true;
    $("ft-dropzone").hidden = true;
    $("ft-paste-input").hidden = true;
    $("ft-raw-preview").hidden = false;
    $("ft-change-file-btn").hidden = true;
    return;
  }
  const showRawPreview = state.ft.rawPreviewActive && !!state.ft.filePreview;
  // Chế độ chọn file: đổ lại nội dung file đã chọn từ bộ nhớ (bảng xem trước
  // có thể vừa bị pipeline ghi đè).
  if (showRawPreview) {
    const f = state.ft.filePreview;
    fillFtPreviewCard(f.label, f.dims, f.rows, f.note);
  }
  $("ft-input-toggle").hidden = showRawPreview;
  $("ft-dropzone").hidden = showRawPreview || state.ft.inputMode !== "file";
  $("ft-paste-input").hidden = showRawPreview || state.ft.inputMode !== "paste";
  $("ft-raw-preview").hidden = !showRawPreview;
  $("ft-change-file-btn").hidden = false;
}

// ====== Tuỳ chọn riêng tool "Điền/xoá ô trống": ô "Giá trị điền vào" chỉ
// hiện khi chọn "Điền giá trị cố định" ======
$("opt-action").addEventListener("change", () => {
  $("opt-fixed-value-wrap").hidden = $("opt-action").value !== "fixed_value";
});
// Công tắc nối liền (opt-keep, opt-action) -- xem wireSegmented() đầu file.
document.querySelectorAll(".ft-seg[data-seg-for]").forEach(wireSegmented);

/* ====== Thanh "nối tiếp" (pipeline) ====== */
function renderFtPipelineStrip() {
  const p = state.ft.pipeline;
  const strip = $("pipeline-strip");
  renderFtInputArea();

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
  state.ft.rawPreviewActive = false; // bỏ bảng xem trước CŨ, bắt chọn file MỚI
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
  $("ft-result-card").hidden = true;
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
  $("ft-result-card").hidden = false;
  // Thanh trên của bảng kết quả: thẻ đen = tên tool vừa chạy, bên phải =
  // "N dòng × M cột" (N lấy từ stats của backend, M đếm theo header preview).
  $("ft-result-tag").textContent = TOOL_TAB_LABEL[state.ft.tool];
  const colCount = data.preview_rows && data.preview_rows.length ? data.preview_rows[0].length : 0;
  $("ft-result-dims").textContent = tableDims(data.stats.final_row_count, colCount);
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
          hideCvRawPreview(); // bỏ file đang chọn bên Convert (nếu có) để ô dán text hiện ra
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

const CV_TAB_LABEL = { delimiter: "Đổi delimiter CSV", "csv-to-json": "CSV → JSON", "json-to-csv": "JSON → CSV" };

/* Hình trước/sau dạng VĂN BẢN cho Convert (đổi định dạng thì phải thấy chữ
   thật thu nhỏ). lines: mảng chuỗi; dòng nào cần nhấn thì ghi dạng
   ["chuỗi", true]. */
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

const CV_INFO = {
  delimiter: {
    headline: "ĐỔI DELIMITER<br>CỦA FILE CSV",
    desc: "Đổi dấu phẩy thành chấm phẩy, tab, gạch đứng hoặc ngược lại mà không làm hỏng các giá trị có dấu ngoặc kép.",
    mock: mockTextPair(
      "export_eu.csv", ["ma;ten;gia", ["A01;But bi;12,50", true], "A02;Kep giay;3,00"],
      "export.csv", ["ma,ten,gia", ['A01,But bi,"12,50"', true], "A02,Kep giay,\"3,00\""],
      "; → ,"
    ),
    dropTitle: "Thả file CSV vào đây",
    accept: ".csv,.txt",
    steps: [
      "Thêm file; delimiter hiện tại được tự nhận diện.",
      "Chọn delimiter mới bạn cần.",
      "Tải file đã đổi về.",
    ],
    explainer: [
      { t: "Vì sao delimiter khác nhau", b: "Ở nơi dùng dấu phẩy làm dấu thập phân, Excel lưu CSV bằng chấm phẩy. Hệ thống khác lại xuất tab hoặc gạch đứng. Công cụ nhập thường chỉ nhận đúng 1 loại, nên phải đổi file chứ không sửa tay." },
      { t: "Dấu ngoặc kép được lo sẵn", b: "Giá trị có chứa delimiter mới, dấu ngoặc kép hoặc xuống dòng sẽ tự được bọc trong ngoặc kép; giá trị chỉ bọc vì delimiter cũ thì được ghi lại bình thường." },
      CV_PRIVACY(),
    ],
  },
  "csv-to-json": {
    headline: "CHUYỂN CSV<br>SANG JSON",
    desc: "Biến CSV thành JSON sạch, khoá theo tên cột, tuỳ chọn tự nhận diện số và true/false.",
    mock: mockTextPair(
      "products.csv", ["sku,name,price", ["A-100,But bi,3.2", true], "A-101,Kep giay,0.5"],
      "products.json", ["[", "  {", ['    "sku": "A-100",', true], ['    "name": "But bi",', true], ['    "price": 3.2', true], "  },", "  …", "]"],
      "→ JSON"
    ),
    dropTitle: "Thả file CSV vào đây",
    accept: ".csv,.txt",
    steps: [
      "Thêm file CSV.",
      "Chọn Objects hay Arrays, có ép kiểu số / true-false không.",
      "Sao chép JSON hoặc tải về dạng .json.",
    ],
    explainer: [
      { t: "Khoá lấy từ dòng tiêu đề", b: "Mỗi dòng thành 1 object, khoá là tên cột. Tên cột trống thành \"column_1\", tên trùng được thêm hậu tố như \"name_2\" nên không mất giá trị nào." },
      { t: "Kiểu dữ liệu không bất ngờ", b: "Bật ép kiểu thì số và true/false thành số và boolean JSON, ô trống thành null. Giá trị có số 0 ở đầu như mã bưu điện, số điện thoại vẫn giữ nguyên dạng chuỗi." },
      CV_PRIVACY(),
    ],
  },
  "json-to-csv": {
    headline: "CHUYỂN JSON<br>SANG CSV",
    desc: "Làm phẳng mảng JSON hoặc JSON Lines thành CSV mở được bằng bảng tính, object lồng nhau thành cột.",
    mock: mockTextPair(
      "users.json", ["[", "  {", '    "id": 1,', ['    "address": {', true], ['      "city": "Ha Noi"', true], "    }", "  }", "]"],
      "users.csv", [["id,address.city", true], "1,Ha Noi"],
      "→ CSV"
    ),
    dropTitle: "Thả file JSON vào đây",
    accept: ".json,.jsonl,.txt",
    steps: [
      "Dán JSON hoặc thả file .json / .jsonl.",
      "Xem lại cột: trường lồng nhau thành tên như \"address.city\".",
      "Tải CSV về.",
    ],
    explainer: [
      { t: "Nhận những gì", b: "1 mảng object, 1 object đơn, mảng của mảng, hoặc JSON Lines (mỗi dòng 1 object). Cột xuất theo thứ tự khoá xuất hiện lần đầu; khoá thiếu thành ô trống." },
      { t: "Dữ liệu lồng nhau", b: "Object lồng nhau được làm phẳng thành tên cột nối bằng dấu chấm, vd \"address.city\". Mảng bên trong được ghi nguyên dạng JSON trong 1 ô nên không mất dữ liệu." },
      CV_PRIVACY(),
    ],
  },
};
function CV_PRIVACY() {
  return {
    t: "Riêng tư theo thiết kế",
    b: "File được backend Flask đọc để đổi định dạng rồi trả kết quả ngay trong cùng 1 request, không lưu lại bản nào. Vẫn cần đăng nhập như mọi chỗ khác trong Denoise.",
  };
}

function renderCvTool(tool) {
  const info = CV_INFO[tool];
  $("cv-crumb-tool").textContent = CV_TAB_LABEL[tool];
  $("cv-hero").innerHTML = `
    <div class="tool-hero-grid">
      <div>
        <h1 class="tool-hero-headline">${info.headline}</h1>
        <p class="tool-hero-desc">${info.desc}</p>
      </div>
      ${info.mock}
    </div>`;
  $("cv-steps").innerHTML = info.steps
    .map((s, i) => `<div><p class="tool-step-num">0${i + 1}</p><p class="tool-step-text">${escapeHtml(s)}</p></div>`)
    .join("");
  $("cv-explainer").innerHTML = info.explainer
    .map((e) => `<div><p class="tool-explainer-title">${escapeHtml(e.t)}</p><p class="tool-explainer-body">${escapeHtml(e.b)}</p></div>`)
    .join("");
  $("cv-dropzone-title").textContent = info.dropTitle;
  $("convert-file-input").accept = info.accept;
}

function activateCvTool(tool) {
  document.querySelectorAll("#convert-tabs .convert-tab").forEach((b) => b.classList.toggle("is-active", b.dataset.tool === tool));
  state.cv.tool = tool;
  // SCOPE theo #section-convert -- ".convert-options" dùng CHUNG với khối
  // Free Tools, không scope sẽ ẩn/hiện nhầm cả options của Free Tools.
  document.querySelectorAll("#section-convert .convert-options").forEach((el) => (el.hidden = el.id !== "convert-options-" + tool));
  renderCvTool(tool);
  // Đổi tool là đổi loại file nhận vào (CSV ↔ JSON) -- bỏ file đang chọn.
  hideCvRawPreview();
  resetCvResult();
}
document.querySelectorAll("#convert-tabs .convert-tab").forEach((btn) => {
  btn.addEventListener("click", () => activateCvTool(btn.dataset.tool));
});

// ====== Chọn kiểu nhập (File / Dán text) ======
wireInputToggle($("convert-input-toggle"), $("convert-dropzone"), $("convert-paste-input"), (mode) => {
  state.cv.inputMode = mode;
});

// ====== Dropzone + bảng xem trước file vừa chọn (giống Free Tools, không
// có pipeline nên đơn giản hơn). CSV: bảng; JSON: chỉ ghi chú, vì xem trước
// JSON dạng bảng không có nghĩa -- bấm Convert là thấy kết quả. ======
wireDropzone($("convert-dropzone"), $("convert-file-input"), (file) => {
  state.cv.selectedFile = file;
  handleCvFileSelected(file);
});
async function handleCvFileSelected(file) {
  const sizeText = `${(file.size / 1024).toFixed(1)} KB`;
  if (!/\.(csv|txt)$/i.test(file.name) || state.cv.tool === "json-to-csv") {
    showCvRawPreview(file.name, sizeText, null, 'File JSON -- bấm "Convert" để xem kết quả dạng bảng.');
    return;
  }
  let text;
  try {
    text = await readFileAsText(file);
  } catch (err) {
    showCvRawPreview(file.name, sizeText, null, 'Không đọc được file để xem trước -- vẫn bấm "Convert" được bình thường.');
    return;
  }
  // Xem trước tách theo dấu phẩy -- file dùng chấm phẩy/tab sẽ hiện 1 cột,
  // đó là chuyện bình thường của bước xem trước, backend tự nhận diện khi Convert.
  const { rows, totalDataRows } = naiveParseCsvPreview(text, 20);
  showCvRawPreview(file.name, tableDims(totalDataRows, rows.length ? rows[0].length : 0), rows, totalDataRows > 20 ? `Xem trước 20/${totalDataRows} dòng đầu.` : "");
}
function showCvRawPreview(label, dims, rows, note) {
  state.cv.rawPreviewActive = true;
  state.cv.filePreview = { label, dims, rows, note };
  renderCvInputArea();
}
function hideCvRawPreview() {
  state.cv.rawPreviewActive = false;
  state.cv.filePreview = null;
  state.cv.selectedFile = null;
  $("convert-file-input").value = "";
  renderCvInputArea();
}
$("cv-change-file-btn").addEventListener("click", hideCvRawPreview);
function renderCvInputArea() {
  const show = state.cv.rawPreviewActive && !!state.cv.filePreview;
  if (show) {
    const f = state.cv.filePreview;
    const hasTable = !!(f.rows && f.rows.length);
    $("cv-raw-preview-label").textContent = f.label;
    $("cv-raw-preview-dims").textContent = f.dims || "";
    $("cv-raw-preview-table-wrap").hidden = !hasTable;
    if (hasTable) renderPreviewTable($("cv-raw-preview-table"), f.rows);
    const noteEl = $("cv-raw-preview-note");
    noteEl.hidden = !f.note;
    noteEl.textContent = f.note || "";
    noteEl.classList.toggle("is-only", !hasTable);
  }
  $("convert-input-toggle").hidden = show;
  $("convert-dropzone").hidden = show || state.cv.inputMode !== "file";
  $("convert-paste-input").hidden = show || state.cv.inputMode !== "paste";
  $("cv-raw-preview").hidden = !show;
}

/* ====== Kết quả ====== */
function resetCvResult() {
  state.cv.lastResult = null;
  $("convert-result-empty").hidden = false;
  $("convert-result-card").hidden = true;
  $("convert-json-card").hidden = true;
  $("convert-download-btn").disabled = true;
  setStatus($("convert-status"), "", "");
  setError($("convert-error"), "");
}

function showCvResult(data) {
  state.cv.lastResult = data;
  $("convert-result-empty").hidden = true;
  $("convert-download-btn").disabled = false;

  if (state.cv.tool === "csv-to-json") {
    $("convert-result-card").hidden = true;
    $("convert-json-card").hidden = false;
    $("convert-json-dims").textContent = `${data.record_count} record`;
    $("convert-result-text").textContent = data.result_text;
    setStatus($("convert-status"), `✅ ${data.record_count} record (delimiter: ${delimiterLabel(data.used_delimiter)})`, "is-ok");
    return;
  }

  $("convert-json-card").hidden = true;
  $("convert-result-card").hidden = false;
  const colCount = data.preview_rows && data.preview_rows.length ? data.preview_rows[0].length : 0;
  // row_count của backend đếm CẢ dòng tiêu đề (đếm số dòng văn bản CSV) --
  // bảng hiển thị coi dòng đầu là tiêu đề nên số "dòng dữ liệu" = row_count - 1,
  // cho khớp với cột số thứ tự trong bảng.
  const dataRows = Math.max(0, data.row_count - 1);
  $("convert-result-tag").textContent = CV_TAB_LABEL[state.cv.tool];
  $("convert-result-dims").textContent = tableDims(dataRows, colCount);
  renderPreviewTable($("convert-result-table"), data.preview_rows);
  if (state.cv.tool === "delimiter") {
    setStatus($("convert-status"), `✅ ${dataRows} dòng dữ liệu · đã nhận diện delimiter gốc: ${delimiterLabel(data.used_from_delimiter)}`, "is-ok");
  } else {
    setStatus($("convert-status"), `✅ ${dataRows} dòng dữ liệu · ${data.columns.length} cột`, "is-ok");
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
// Hỗ trợ ?section=<tên khối> (home / guide / security / privacy / free-tools /
// convert) để mở thẳng đúng khối. Không có hoặc sai tên -> trang chủ.
(function initSectionFromQuery() {
  const requested = new URLSearchParams(window.location.search).get("section");
  if (SECTIONS.includes(requested)) state.section = requested;
})();

checkAuth();
checkBackendHealth();
renderFtToolHero(state.ft.tool);
renderFtToolSteps(state.ft.tool);
renderFtToolExplainer(state.ft.tool);
renderFtPipelineStrip();
renderCvTool(state.cv.tool);
renderCvInputArea();
switchSection(state.section);
