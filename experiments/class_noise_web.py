"""Thực nghiệm class noise của Chương 4: chạy đúng đường đi của ứng dụng qua Flask test client
(/api/upload -> /api/class-noise/detect với method "combined"), chấm bộ kết hợp và hai danh sách riêng
(Confident Learning, Mutual k-NN) trên cùng tập dòng bị đổi nhãn.

Chạy từ thư mục gốc của mã nguồn:
    python experiments/class_noise_web.py --out results/class_noise.jsonl
Mặc định: 3 bộ dữ liệu × mức 0, 1, 3, 5, 7, 10% × hạt giống 0..4 (khoảng 25–30 phút trên máy 2 nhân).
"""
import argparse, io, json, os, time, warnings
warnings.filterwarnings("ignore")
from _common import ROOT, CLASS_DATASETS, load_class_dataset, flip_labels, score_rows

ap = argparse.ArgumentParser()
ap.add_argument("--datasets", default=",".join(CLASS_DATASETS))
ap.add_argument("--levels", default="0,0.01,0.03,0.05,0.07,0.10")
ap.add_argument("--seeds", default="0,1,2,3,4")
ap.add_argument("--out", default="results/class_noise.jsonl")
a = ap.parse_args()

os.chdir(ROOT)
import app as A
client = A.app.test_client()
client.post("/api/auth/register", json={"username": f"thucnghiem{os.getpid()}", "password": "thucnghiem123"})
os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
out = open(a.out, "a", encoding="utf-8")

for name in a.datasets.split(","):
    base = load_class_dataset(name); y0 = base["target"].to_numpy()
    for seed in [int(v) for v in a.seeds.split(",")]:
        for level in [float(v) for v in a.levels.split(",")]:
            y, idx = flip_labels(y0, level, seed)
            d = base.drop(columns="target").copy(); d["nhan"] = y
            feats = [c for c in d.columns if c != "nhan"]
            r = client.post("/api/upload", data={"file": (io.BytesIO(d.to_csv(index=False).encode()), f"{name}.csv")},
                            content_type="multipart/form-data")
            fid = r.get_json()["file_id"]
            t = time.time()
            r = client.post("/api/class-noise/detect", json={"file_id": fid, "label_column": "nhan",
                                                             "feature_columns": feats, "method": "combined"})
            sec = time.time() - t; js = r.get_json()
            truth = set(int(i) + 1 for i in idx)              # số dòng trên giao diện đếm từ 1
            rec = dict(dataset=name, seed=seed, level=level, n_rows=len(d), n_true=len(truth), http=r.status_code, sec=round(sec, 1))
            if r.status_code == 200:
                rec["ket_hop"] = score_rows({f["row_number"] for f in js["findings"]}, truth)
                for m, fl in (js.get("method_findings") or {}).items():
                    rec[m] = score_rows({f["row_number"] for f in fl}, truth)
                pre = js["preprocess"]; lr = pre.get("label_reduction") or {}; dg = js.get("diagnostics") or {}
                rec["chuan_bi"] = dict(bo_tuong_quan=[c["column"] for c in pre.get("dropped_columns", []) if c.get("reason") == "correlated"],
                                       boruta_vao=lr.get("n_columns_in"), boruta_giu=len(lr.get("kept", [])), boruta_vong=lr.get("n_iter"),
                                       dong_gop_bot=pre.get("n_rows_merged_away"), nhom_gop=pre.get("n_duplicate_groups_merged"))
                rec["muc_vuot_moc"] = (dg.get("single") or {}).get("excess_over_baseline")
                rec["do_phu_knn"] = (dg.get("distance") or {}).get("coverage")
                rec["canh_bao"] = dg.get("warnings") or []
                rec["nhan_goi_y_dung"] = sum(1 for f in js["findings"] if f["row_number"] in truth
                                             and str(f.get("suggested_label")) == str(y0[f["row_number"] - 1]))
            else:
                rec["error"] = js
            out.write(json.dumps(rec, ensure_ascii=False) + "\n"); out.flush()
            print(name, seed, level, rec["http"], rec["sec"], (rec.get("ket_hop") or {}).get("F1"), flush=True)
