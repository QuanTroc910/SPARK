"""Logic nghiệp vụ tài khoản: đăng ký, xác thực đăng nhập, đổi mật khẩu.

QUAN TRỌNG -- KHÔNG tự viết công thức băm/mã hoá mật khẩu (khác triết lý
"tự viết tay" ở nhiều module khác của dự án, vd KNN impute tự viết trong
attribute_handling.py): bảo mật mật khẩu là lĩnh vực RỦI RO CAO nếu tự chế
sai mà không nhận ra. Dùng `werkzeug.security` (đã có sẵn trong Flask,
không cần cài thêm) -- `generate_password_hash`/`check_password_hash` dùng
thuật toán băm hiện đại, đã kiểm chứng rộng rãi, cùng tinh thần `bcrypt`.
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_connection

MIN_USERNAME_LENGTH = 3
MIN_PASSWORD_LENGTH = 6


class AccountError(Exception):
    """Lỗi nghiệp vụ tài khoản (trùng tên đăng nhập, sai mật khẩu, mật khẩu
    quá ngắn...) -- app.py bắt lỗi này để trả HTTP 400 kèm message rõ ràng,
    cùng cách các module khác trong dự án đã làm (vd FormulaError)."""


@dataclass
class User:
    id: int
    username: str
    created_at: str


def register(username: str, password: str) -> User:
    """Tạo tài khoản mới. Mật khẩu KHÔNG BAO GIỜ được lưu dạng gốc -- chỉ
    lưu `password_hash` (chuỗi băm 1 chiều, không thể giải ngược lại thành
    mật khẩu thật)."""
    username = (username or "").strip()
    password = password or ""
    if len(username) < MIN_USERNAME_LENGTH:
        raise AccountError(f"Tên đăng nhập phải có ít nhất {MIN_USERNAME_LENGTH} ký tự")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AccountError(f"Mật khẩu phải có ít nhất {MIN_PASSWORD_LENGTH} ký tự")

    password_hash = generate_password_hash(password)
    created_at = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        try:
            cursor = conn.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                (username, password_hash, created_at),
            )
        except sqlite3.IntegrityError as exc:
            # Cột username có ràng buộc UNIQUE -- INSERT trùng tên sẽ raise lỗi này.
            raise AccountError("Tên đăng nhập đã tồn tại") from exc
        return User(id=cursor.lastrowid, username=username, created_at=created_at)


def authenticate(username: str, password: str) -> User:
    """Kiểm tra đăng nhập. Cố tình dùng CHUNG 1 thông báo lỗi cho cả 2
    trường hợp "không có tài khoản này" và "có tài khoản nhưng sai mật
    khẩu" -- không tiết lộ username nào đã tồn tại hay chưa qua nội dung
    lỗi (tránh kẻ xấu dò danh sách username hợp lệ)."""
    username = (username or "").strip()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, created_at FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    if row is None or not check_password_hash(row["password_hash"], password or ""):
        raise AccountError("Tên đăng nhập hoặc mật khẩu không đúng")
    return User(id=row["id"], username=row["username"], created_at=row["created_at"])


def get_user(user_id: int) -> "User | None":
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, username, created_at FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    return User(id=row["id"], username=row["username"], created_at=row["created_at"]) if row else None


def change_password(user_id: int, old_password: str, new_password: str) -> None:
    """Đổi mật khẩu -- bắt buộc đúng mật khẩu CŨ trước (giống mọi trang hồ
    sơ tài khoản thật), tránh ai đó chiếm được phiên đăng nhập (session) là
    đổi luôn được mật khẩu mà không cần biết mật khẩu gốc."""
    if len(new_password or "") < MIN_PASSWORD_LENGTH:
        raise AccountError(f"Mật khẩu mới phải có ít nhất {MIN_PASSWORD_LENGTH} ký tự")
    with get_connection() as conn:
        row = conn.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None or not check_password_hash(row["password_hash"], old_password or ""):
            raise AccountError("Mật khẩu hiện tại không đúng")
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (generate_password_hash(new_password), user_id),
        )
