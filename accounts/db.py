"""Kết nối SQLite cho tài khoản người dùng -- LƯU VÀO 1 FILE DUY NHẤT
(`spark_accounts.db`, tự tạo ở gốc repo), KHÔNG cần cài đặt/chạy 1 server
database riêng (khác PostgreSQL/MySQL). Đây là module DUY NHẤT trong dự án
có dữ liệu LƯU LÂU DÀI (khác hẳn UPLOADED_FILES/WORKING_FILES trong app.py
chỉ sống trong RAM, mất sạch khi server restart) -- tài khoản BẮT BUỘC phải
còn nguyên sau khi tắt/mở lại server.

Quy mô phù hợp: SQLite xử lý tốt tới hàng trăm nghìn lượt truy cập/ngày
(tài liệu chính thức sqlite.org/whentouse.html), thừa sức cho quy mô demo
khoá luận (vài người dùng cùng lúc) -- không cần PostgreSQL/MySQL.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "spark_accounts.db"


def get_connection() -> sqlite3.Connection:
    """Mở 1 kết nối MỚI tới file database cho mỗi lần gọi -- SQLite cho phép
    nhiều kết nối cùng lúc an toàn hơn giữ chung 1 kết nối sống suốt đời
    server (tránh lỗi khi nhiều request chạy đồng thời, threaded=True).

    row_factory = sqlite3.Row: cho phép đọc kết quả truy vấn kiểu
    `row["username"]` thay vì phải nhớ thứ tự cột `row[0]`, `row[1]`...
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Tạo bảng `users` nếu CHƯA có -- gọi 1 lần lúc server khởi động.
    An toàn gọi lại nhiều lần (IF NOT EXISTS không báo lỗi nếu bảng đã tồn tại).
    """
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
