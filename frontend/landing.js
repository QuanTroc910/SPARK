"use strict";

/* Trang giới thiệu (landing.html) công khai, không bắt đăng nhập -- JS ở
   đây CHỈ làm 2 việc: báo trạng thái backend + cuộn mượt khi bấm anchor
   link trong trang (vd "Tính năng"/"Quy trình"). Mọi logic đăng nhập/app
   thật nằm ở script.js (index.html), không lặp lại ở đây. */

async function checkBackendHealth() {
  const dot = document.getElementById("backend-dot");
  const text = document.getElementById("backend-status-text");
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

checkBackendHealth();
