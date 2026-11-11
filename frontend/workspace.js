"use strict";

/* ============================================================
   workspace.js -- logic cho trang workspace.html (giao diện MỚI, đang xây
   dần để thay thế index.html/luồng 5 bước cũ). Bản này MỚI CHỈ có phần
   header (dropdown Product, trạng thái đăng nhập/backend) -- phần thân
   trang (sidebar cấu hình + khu vực kết quả) sẽ viết thêm ở bước sau.
   ============================================================ */

const $ = (id) => document.getElementById(id);

// ====== Cổng xác thực: giống hệt convert.js/tools.js -- bắt buộc đăng
// nhập, dùng chung session với trang chính, chưa đăng nhập thì chuyển
// thẳng về index.html (nơi có form đăng nhập thật). ======
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
  // Khác index.html/convert.js/tools.js (còn chữ "Backend: đã/chưa kết nối") --
  // ở đây CHỈ còn 1 chấm tròn màu, không có chữ đi kèm (yêu cầu gọn bớt header).
  // Vẫn giữ y nguyên THÔNG TIN đó dưới dạng `title` (tooltip khi rê chuột vào
  // chấm tròn) để không mất hẳn, chỉ ẩn khỏi tầm nhìn mặc định.
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

// ====== Khởi động ======
checkAuth();
checkBackendHealth();
