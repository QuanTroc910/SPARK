"""Test cho việc tự xoá dữ liệu cũ khỏi RAM (CLAUDE.md mục 59) và việc tắt debug mặc định.

Chạy:  python3 tests/test_purge.py      (không cần pytest; in "KẾT QUẢ: N đạt, M lỗi", thoát mã 1 nếu có lỗi)
"""
import io
import os
import sys
import time
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pandas as pd
import app as appmod

ok = fail = 0


def check(name, cond):
    global ok, fail
    if cond:
        ok += 1
    else:
        fail += 1
        print("LỖI:", name)


def seed(file_id, owner=1, working=True, history=True):
    appmod.UPLOADED_FILES[file_id] = pd.DataFrame({"a": ["1"]})
    appmod.FILE_OWNERS[file_id] = owner
    if working:
        appmod.WORKING_FILES[file_id] = pd.DataFrame({"a": ["1"]})
    if history:
        appmod.HANDLING_HISTORY[file_id] = [{"snapshot": None}]


def present(file_id):
    return any(file_id in d for d in (appmod.UPLOADED_FILES, appmod.WORKING_FILES, appmod.HANDLING_HISTORY,
                                      appmod.FILE_OWNERS, appmod.FILE_LAST_USED))


ttl = appmod.FILE_TTL_SECONDS
now = time.monotonic()

# 1. Xoá đúng file quá hạn, giữ file còn mới, xoá sạch MỌI dict của file bị xoá
old, fresh = "old-" + uuid.uuid4().hex, "fresh-" + uuid.uuid4().hex
seed(old); seed(fresh)
appmod.FILE_LAST_USED[old] = now - ttl - 5
appmod.FILE_LAST_USED[fresh] = now - 10
res = appmod._purge_expired(now)
check("xoá 1 file quá hạn", res["files"] >= 1)
check("file quá hạn biến khỏi mọi dict", not present(old))
check("file còn mới được giữ nguyên", present(fresh) and fresh in appmod.UPLOADED_FILES and fresh in appmod.WORKING_FILES)

# 2. Đúng ranh giới: đúng bằng TTL chưa bị xoá, hơn TTL 1 giây thì bị xoá
edge = "edge-" + uuid.uuid4().hex
seed(edge)
appmod.FILE_LAST_USED[edge] = now - ttl
appmod._purge_expired(now)
check("đúng bằng TTL thì chưa xoá", edge in appmod.UPLOADED_FILES)
appmod._purge_expired(now + 1)
check("quá TTL 1 giây thì xoá", edge not in appmod.UPLOADED_FILES)

# 3. id chưa có mốc thời gian: bắt đầu tính từ bây giờ (không bị xoá ngay)
nots = "nots-" + uuid.uuid4().hex
seed(nots)
appmod.FILE_LAST_USED.pop(nots, None)
appmod._purge_expired(now)
check("id chưa có mốc không bị xoá ngay", nots in appmod.UPLOADED_FILES and nots in appmod.FILE_LAST_USED)
appmod._purge_expired(now + ttl + 1)
check("id chưa có mốc bị xoá sau TTL", nots not in appmod.UPLOADED_FILES)

# 4. Chỉ còn mầm trong 1 dict (vd chỉ HANDLING_HISTORY) vẫn được dọn
lone = "lone-" + uuid.uuid4().hex
appmod.HANDLING_HISTORY[lone] = []
appmod.FILE_LAST_USED[lone] = now - ttl - 1
appmod._purge_expired(now)
check("mầm lẻ trong HANDLING_HISTORY được dọn", lone not in appmod.HANDLING_HISTORY)

# 5. Download
d_old, d_new = "d-old-" + uuid.uuid4().hex, "d-new-" + uuid.uuid4().hex
for d in (d_old, d_new):
    appmod.CLEANED_FILES[d] = pd.DataFrame({"a": ["1"]})
    appmod.DOWNLOAD_OWNERS[d] = 1
appmod.DOWNLOAD_LAST_USED[d_old] = now - ttl - 5
appmod.DOWNLOAD_LAST_USED[d_new] = now - 5
res = appmod._purge_expired(now)
check("download quá hạn bị xoá", d_old not in appmod.CLEANED_FILES and d_old not in appmod.DOWNLOAD_OWNERS)
check("download còn mới được giữ", d_new in appmod.CLEANED_FILES)

# 6. Qua route thật: tải lên -> dùng liên tục không bị xoá; để quá hạn thì 404; dùng lại thì hoãn hạn
client = appmod.app.test_client()
user = "purge" + uuid.uuid4().hex[:8]
r = client.post("/api/auth/register", json={"username": user, "password": "abcdef123"})
check("đăng ký", r.status_code == 200)
csv = "x,y,label\n" + "\n".join(f"{i},{i * 2},{i % 2}" for i in range(40))
r = client.post("/api/upload", data={"file": (io.BytesIO(csv.encode()), "t.csv")}, content_type="multipart/form-data")
check("upload 200", r.status_code == 200)
fid = r.get_json()["file_id"]
check("upload ghi mốc thời gian", fid in appmod.FILE_LAST_USED)

appmod.FILE_LAST_USED[fid] = time.monotonic() - ttl + 30       # sắp hết hạn
r = client.post("/api/export-working", json={"file_id": fid})   # dùng file -> hoãn hạn
check("export dùng file được", r.status_code == 200)
check("dùng file làm mới mốc thời gian", time.monotonic() - appmod.FILE_LAST_USED[fid] < 5)
appmod._purge_expired()
check("file vừa dùng không bị dọn", fid in appmod.UPLOADED_FILES)

appmod.FILE_LAST_USED[fid] = time.monotonic() - ttl - 5
appmod._purge_expired()
r = client.post("/api/export-working", json={"file_id": fid})
check("file quá hạn: route trả 404 + lời nhắc tải lại", r.status_code == 404 and "upload lại" in r.get_json()["error"])

# 7. Dọn kèm request (before_request) chạy mà không làm hỏng request, và bị chặn đến 1 lần / PURGE_INTERVAL
old2 = "old2-" + uuid.uuid4().hex
seed(old2)
appmod.FILE_LAST_USED[old2] = time.monotonic() - ttl - 5
appmod._last_purge_at = time.monotonic()                        # vừa dọn xong -> chưa tới lượt
client.get("/api/auth/me")
check("trong khoảng chờ thì chưa dọn", old2 in appmod.UPLOADED_FILES)
appmod._last_purge_at = time.monotonic() - appmod.PURGE_INTERVAL_SECONDS - 1
r = client.get("/api/auth/me")
check("hết khoảng chờ thì request kèm dọn, vẫn trả 200", r.status_code == 200 and old2 not in appmod.UPLOADED_FILES)

# 8. Debug tắt mặc định
src = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
check("app.run dùng debug=debug_mode (không cứng True)", "app.run(port=5000, debug=debug_mode" in src)
check("debug đọc từ SPARK_DEBUG", 'SPARK_DEBUG' in src)

print(f"KẾT QUẢ: {ok} đạt, {fail} lỗi")
sys.exit(1 if fail else 0)
