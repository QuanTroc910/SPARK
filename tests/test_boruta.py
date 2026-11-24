"""Test cho BORUTA ở bước giảm số cột của Class Noise (CLAUDE.md "Quyết định 24/11/2026").

Chạy:  python3 tests/test_boruta.py      (không cần pytest; in "KẾT QUẢ: N đạt, M lỗi", thoát mã 1 nếu có lỗi)

Gồm 3 nhóm:
  1. Unit test `boruta_select`: 5 cột thật (make_classification) + 10 cột rác -> mọi cột rác bị bỏ, 5 cột thật được giữ.
  2. Test `prepare_for_class_noise`: chạy Boruta thật; dự phòng khi Boruta lỗi / không giữ cột nào; chỉ 1 cột thì không chạy.
  3. Smoke test route /api/class-noise/detect bằng Flask test client trên 1 CSV số tổng hợp
     (tham số `reduce_columns` cũ bị bỏ qua; route `/api/class-noise/reduce-features` đã gỡ -> 404).
"""
import io
import os
import sys

import numpy as np
import pandas as pd
from sklearn.datasets import make_classification

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import class_noise.preprocess as preprocess_module  # noqa: E402
from class_noise.boruta import BorutaResult, boruta_select  # noqa: E402
from class_noise.preprocess import PreprocessConfig, prepare_for_class_noise  # noqa: E402

ok = fail = 0


def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
    else:
        fail += 1
        print("  FAIL:", name, extra)


def synthetic_frame(n=2000, n_junk=10, seed=0):
    """5 cột thật (đều mang thông tin về nhãn) + n_junk cột rác ngẫu nhiên; nhãn là cột `y` (chuỗi)."""
    X, y = make_classification(n_samples=n, n_features=5, n_informative=5, n_redundant=0, random_state=seed)
    rng = np.random.default_rng(seed + 1)
    df = pd.DataFrame(X, columns=[f"real{i}" for i in range(5)])
    for j in range(n_junk):
        df[f"junk{j}"] = rng.normal(size=n)
    df["y"] = np.where(y == 1, "pos", "neg")
    return df


# ---------------------------------------------------------------------------------------------
# 1) Unit test boruta_select
# ---------------------------------------------------------------------------------------------
df = synthetic_frame()
feats = [c for c in df.columns if c != "y"]
res = boruta_select(df[feats], df["y"].to_numpy())
real = {f"real{i}" for i in range(5)}
junk = {f"junk{j}" for j in range(10)}
check("5 cột thật đều được giữ", real <= set(res.kept), res.kept)
check("mọi cột rác bị bỏ", junk <= set(res.rejected), res.rejected)
check("không cột rác nào còn trong kept", not (junk & set(res.kept)), res.kept)
check("không cột thật nào bị bỏ", not (real & set(res.rejected)), res.rejected)
check("kept + rejected + tentative = tất cả cột, không trùng",
      sorted(res.kept + res.rejected) == sorted(feats) or sorted(res.kept + res.rejected + res.tentative) == sorted(feats))
check("tentative nằm trong kept (chưa chứng minh vô ích thì không bỏ)", set(res.tentative) <= set(res.kept))
check("n_iter hợp lệ", 1 <= res.n_iter <= 100, res.n_iter)

res2 = boruta_select(df[feats], df["y"].to_numpy())
check("cùng random_state -> cùng kết quả", (res.kept, res.rejected, res.n_iter) == (res2.kept, res2.rejected, res2.n_iter))

res3 = boruta_select(df[feats], df["y"].to_numpy(), max_iter=2)
check("max_iter nhỏ: dừng đúng số vòng, chưa kết luận thì giữ", res3.n_iter == 2 and len(res3.kept) == len(feats), (res3.n_iter, len(res3.kept)))

# nhãn hoàn toàn ngẫu nhiên: không cột nào được kết luận "quan trọng" thì cũng không được bỏ nhầm cột thật -- chỉ cần chạy không lỗi
rng = np.random.default_rng(5)
noise_only = pd.DataFrame(rng.normal(size=(600, 4)), columns=list("abcd"))
res_noise = boruta_select(noise_only, rng.integers(0, 2, 600).astype(str), max_iter=30)
check("nhãn ngẫu nhiên: chạy được, kết quả hợp lệ", set(res_noise.kept) | set(res_noise.rejected) == set("abcd"))

# ---------------------------------------------------------------------------------------------
# 2) prepare_for_class_noise
# ---------------------------------------------------------------------------------------------
cfg = PreprocessConfig(label_column="y", feature_columns=feats)
prepared = prepare_for_class_noise(df, cfg)
rep = prepared.report
red = rep.label_reduction
check("Boruta luôn chạy: label_reduction có thông tin", red is not None and red["applied"] and red["method"] == "boruta", red)
check("info có kept / rejected / tentative / n_iter / seconds",
      all(k in red for k in ("kept", "rejected", "tentative", "n_iter", "seconds")), list(red or {}))
check("cột giữ lại = 5 cột thật", set(prepared.feature_columns) == real, prepared.feature_columns)
dropped = {d.column: d for d in rep.dropped_columns}
check("10 cột rác ghi vào dropped_columns với reason label_reduction",
      set(dropped) == junk and all(d.reason == "label_reduction" for d in dropped.values()), sorted(dropped))
check("detail đúng câu yêu cầu", all(d.detail == "Boruta: không quan trọng hơn cột ngẫu nhiên" for d in dropped.values()))
check("bảng đưa vào thuật toán chỉ còn cột thật + nhãn", set(prepared.df.columns) == real | {"y"}, list(prepared.df.columns))
check("PreprocessConfig không còn tuỳ chọn reduce_by_label", not hasattr(cfg, "reduce_by_label"))

# 1 cột đặc trưng duy nhất: không chạy Boruta
one = prepare_for_class_noise(df, PreprocessConfig(label_column="y", feature_columns=["real0"]))
check("chỉ 1 cột: không chạy Boruta, giữ nguyên", one.feature_columns == ["real0"] and one.report.label_reduction is None)

# Boruta ném lỗi -> dự phòng giữ tất cả cột + cảnh báo
original = preprocess_module.boruta_select


def broken(*args, **kwargs):
    raise RuntimeError("giả lập lỗi")


preprocess_module.boruta_select = broken
try:
    fb = prepare_for_class_noise(df, cfg)
finally:
    preprocess_module.boruta_select = original
check("Boruta lỗi: giữ tất cả cột", set(fb.feature_columns) == set(feats), fb.feature_columns)
check("Boruta lỗi: có cảnh báo nói rõ", any("Boruta không chạy được" in w for w in fb.report.warnings), fb.report.warnings)
check("Boruta lỗi: không cột nào bị ghi label_reduction", not any(d.reason == "label_reduction" for d in fb.report.dropped_columns))
check("Boruta lỗi: info ghi applied = False", fb.report.label_reduction and fb.report.label_reduction["applied"] is False)

# Boruta không giữ cột nào -> dự phòng giữ tất cả
preprocess_module.boruta_select = lambda X, y, **kw: BorutaResult(kept=[], rejected=list(X.columns), tentative=[], n_iter=7)
try:
    z = prepare_for_class_noise(df, cfg)
finally:
    preprocess_module.boruta_select = original
check("Boruta giữ 0 cột: giữ tất cả cột", set(z.feature_columns) == set(feats), z.feature_columns)
check("Boruta giữ 0 cột: có cảnh báo", any("không giữ cột nào" in w for w in z.report.warnings), z.report.warnings)
check("Boruta giữ 0 cột: không cột nào bị ghi bỏ vì label_reduction", not any(d.reason == "label_reduction" for d in z.report.dropped_columns))

# cảnh báo lớp hiếm vẫn còn
rare = df.copy()
rare["y"] = np.where(np.arange(len(rare)) < 20, "hiem", "dong")
rp = prepare_for_class_noise(rare, cfg)
check("cảnh báo lớp hiếm vẫn còn", any("Lớp hiếm" in w for w in rp.report.warnings), rp.report.warnings)
check("info có margin + minority_rows", rp.report.label_reduction and "margin" in rp.report.label_reduction and rp.report.label_reduction["minority_rows"] == 20)

# Boruta dùng TOÀN BỘ dòng đủ giá trị (không lấy mẫu): dòng có ô trống ở cột còn lại bị bỏ khỏi bước Boruta nhưng không lỗi
holes = df.copy()
holes.loc[holes.index[:30], "real0"] = np.nan
hp = prepare_for_class_noise(holes, cfg)
check("có ô trống: Boruta dùng đủ dòng không trống", hp.report.label_reduction["n_rows_used"] == len(df) - 30, hp.report.label_reduction["n_rows_used"])

# mọi dòng đều có ô trống ở 1 cột nào đó: không có dòng để chạy Boruta -> giữ tất cả cột, có cảnh báo, không lỗi
allblank = df[feats + ["y"]].copy()
for i, c in enumerate(feats):
    allblank.loc[allblank.index[i::len(feats)], c] = np.nan      # mỗi dòng bị khuyết đúng 1 cột
try:
    ab = prepare_for_class_noise(allblank, cfg)
    check("mọi dòng có ô trống: không văng lỗi ở bước Boruta", True)
    check("mọi dòng có ô trống: Boruta không áp dụng + có cảnh báo",
          ab.report.label_reduction and ab.report.label_reduction["applied"] is False
          and any("đủ giá trị" in w for w in ab.report.warnings), ab.report.warnings)
except Exception as exc:  # noqa: BLE001
    # chấp nhận PreprocessError ở các bước SAU (không còn dòng nào) -- miễn không phải lỗi đột ngột ở Boruta
    check("mọi dòng có ô trống: không văng lỗi lạ", type(exc).__name__ == "PreprocessError", repr(exc))

# ---------------------------------------------------------------------------------------------
# 3) Smoke test route /api/class-noise/detect (Flask test client)
# ---------------------------------------------------------------------------------------------
import app as A  # noqa: E402

smoke = synthetic_frame(n=700, n_junk=4, seed=3)
buf = io.StringIO()
smoke.to_csv(buf, index=False)
client = A.app.test_client()
name = "bor" + str(os.getpid())
r = client.post("/api/auth/register", json={"username": name, "password": "abcd1234"})
check("đăng ký test", r.status_code == 200, r.get_json())
r = client.post("/api/upload", data={"file": (io.BytesIO(buf.getvalue().encode("utf-8")), "smoke.csv")},
                content_type="multipart/form-data")
check("upload CSV tổng hợp", r.status_code == 200, r.get_json())
file_id = r.get_json()["file_id"]
smoke_feats = [c for c in smoke.columns if c != "y"]

body = {"file_id": file_id, "label_column": "y", "feature_columns": smoke_feats, "method": "combined"}
r = client.post("/api/class-noise/detect", json=body)
data = r.get_json()
check("detect combined -> 200", r.status_code == 200, data if r.status_code != 200 else "")
if r.status_code == 200:
    pp = data["preprocess"]
    lr = pp["label_reduction"]
    check("response preprocess có thông tin Boruta", lr and lr["method"] == "boruta" and lr["applied"], lr)
    # Bảng nhỏ (700 dòng) nên 1 cột rác có thể còn "chưa quyết định" sau 100 vòng -> vẫn được giữ (đúng thiết kế);
    # vì vậy chỉ đòi: cột bị bỏ phải là cột rác, bỏ được ít nhất 3/4 cột rác, mọi cột thật còn nguyên.
    dropped_cols = {d["column"] for d in pp["dropped_columns"] if d["reason"] == "label_reduction"}
    junk4 = {f"junk{j}" for j in range(4)}
    real5 = {f"real{i}" for i in range(5)}
    check("response: cột bị bỏ vì label_reduction đều là cột rác, bỏ được >= 3/4",
          dropped_cols <= junk4 and len(dropped_cols) >= 3, sorted(dropped_cols))
    check("response: không còn khoá reduce_by_label", "reduce_by_label" not in pp)
    check("response: mọi cột thật còn trong cột đã dùng", real5 <= set(pp["kept_columns"]), pp["kept_columns"])
    check("response: rejected + tentative của Boruta khớp cột bị bỏ / chưa quyết định",
          set(lr["rejected"]) == dropped_cols and set(lr["tentative"]) <= set(pp["kept_columns"]), (lr["rejected"], lr["tentative"]))
    check("response có bảng kết quả + method", data["method"] == "combined" and "findings" in data)
    json_text = r.get_data(as_text=True)
    check("JSON không chứa NaN/Infinity", "NaN" not in json_text and "Infinity" not in json_text)

# client cũ vẫn gửi reduce_columns: bị bỏ qua, vẫn chạy Boruta
for old_value in (True, False):
    r = client.post("/api/class-noise/detect", json={**body, "reduce_columns": old_value})
    lr2 = (r.get_json() or {}).get("preprocess", {}).get("label_reduction")
    check(f"gửi reduce_columns={old_value}: bị bỏ qua, Boruta vẫn chạy", r.status_code == 200 and lr2 and lr2["applied"], r.status_code)

# route cũ đã gỡ
r = client.post("/api/class-noise/reduce-features", json={"file_id": file_id, "label_column": "y"})
check("route /reduce-features đã gỡ (404/405)", r.status_code in (404, 405), r.status_code)
r = client.post("/api/class-noise/boruta", json={"file_id": file_id, "label_column": "y"})
check("route /boruta riêng đã gỡ (404/405)", r.status_code in (404, 405), r.status_code)

# method khác cũng đi qua Boruta (bước chuẩn bị dùng chung)
for m in ("single_learning", "distance_based"):
    r = client.post("/api/class-noise/detect", json={**body, "method": m})
    lrm = (r.get_json() or {}).get("preprocess", {}).get("label_reduction")
    check(f"method={m}: 200 + có Boruta", r.status_code == 200 and lrm and lrm["method"] == "boruta", r.status_code)

print(f"\nKẾT QUẢ: {ok} đạt, {fail} lỗi")
sys.exit(1 if fail else 0)
