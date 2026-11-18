# Kịch bản test Denoise — mô phỏng người dùng thật

File dùng chung cho **Attribute Noise**: **`data/test_attribute_noise.csv`** (552 dòng × 20 cột, chủ đề nhân viên, có đủ mọi loại lỗi của Attribute). Bản Excel y hệt: `test_attribute_noise.xlsx`.
**Class Noise KHÔNG dùng file này** mà dùng bộ Credit Card (`data/kaggle_creditcard_fraud.csv`, xem mục 7 và CLAUDE.md mục 35-36).
Đáp án từng ô bị cấy lỗi: `test_attribute_noise_ground_truth.csv` (cột `row` = số thứ tự dòng dữ liệu, khớp cột "Dòng" trên giao diện; trong Excel/CSV mở bằng bảng tính thì cộng thêm 1 vì có dòng tiêu đề).
Sinh lại bất cứ lúc nào: `python3 data/generate_test_attribute_noise.py` (hạt giống cố định nên ra đúng cùng file).

File phụ: `test_semicolon.csv`, `test_tab.txt` (đổi delimiter), `test_convert_nested.json`, `test_convert_lines.jsonl` (JSON → CSV), `test_empty.csv`, `test_header_only.csv`, `test_bad.json` (file xấu).

**Cách dùng:** chạy `python3 app.py`, mở `http://localhost:5000`, làm lần lượt từng mục, đánh dấu ô vuông. Số liệu "kỳ vọng" dưới đây đã được đối chiếu với tính độc lập bằng pandas (0 lệch). Nếu giao diện ra số khác thì ghi lại: đó là lỗi.

> Cột "Dòng" trong bảng kết quả bắt đầu từ 1 (dòng dữ liệu đầu tiên). Chữ trên giao diện nhiều chỗ viết HOA bằng CSS, không phải lỗi.

---

## 0. Bảng lỗi cấy sẵn trong file

| Loại lỗi | Cột | Số lượng |
|---|---|---|
| Ô trống (`""`, NA, N/A, null, -, ?, none, --) | ho_ten 9 · gioi_tinh 10 · tuoi 8 · ngay_sinh 8 · email 11 · so_dien_thoai 10 · phong_ban 9 · ngay_vao 7 · ngay_ra 7 · luong 10 · hoa_hong 11 · diem_dg 8 · Hệ số lương 7 · ghi_chu 34 | 4 dòng trống hoàn toàn (mọi cột còn lại có thêm 4 ô trống), cột `cot_trong` trống 100% |
| Sai định dạng | tuoi 3 · luong 5 · email 6 · so_dien_thoai 6 · ngay_sinh 10 · ngay_vao 3 · diem_dg 3 · Hệ số lương 2 | **38 ô** |
| Khoảng trắng thừa | ho_ten, ghi_chu (đầu / cuối / lặp giữa / zero-width / non-breaking) | **35 ô** bị đổi khi cắt (45 nếu tick "gộp khoảng trắng lặp") |
| Dòng trùng | 18 trùng hệt + 6 gần trùng (email viết HOA, ghi_chu thừa dấu cách) | xoá **21** (18 + 3 dòng trống giống nhau); **27** nếu bỏ qua hoa/thường + khoảng trắng |
| Ngoài khoảng | tuoi (18–65) 9 · luong (3tr–100tr) 4 · diem_dg (1–10) 6 · Hệ số lương (>0) 2 | |
| Giá trị bất thường | luong: 9 ô (IQR 1.5), 1 ô (Z-score 3) · thuong: cột 85% bằng 0 → IQR = 0 | thuong: **80 ô** + cảnh báo vàng |
| Không nhất quán | gioi_tinh 14 · loai_hd 5 · phong_ban 15 (ngưỡng 1) / 19 (ngưỡng 0.85, bắt cả "Sale", "Marketting") | |
| Rule liên cột | `ngay_ra >= ngay_vao` 10 · `luong + thuong == tong_thu_nhap` 8 · Thử việc mà luong > 12tr 5 · Sales thiếu hoa_hong 7 | |
| Phụ thuộc hàm `ma_nv → ho_ten, ngay_sinh` | 32 dòng thuộc 9 nhóm mâu thuẫn (ho_ten) + 6 nhóm (ngay_sinh) | xem mục 5.5 |

---

## 1. Tài khoản
- [ ] Chưa đăng nhập: trang chủ, Guide, Bảo mật, Quyền riêng tư xem được; góc phải có "Đăng nhập" và "Bắt đầu".
- [ ] Chưa đăng nhập, bấm một tool trong menu Product → hiện màn đăng nhập (không vào được tool).
- [ ] Đăng ký: tên đăng nhập `ab` (quá ngắn) → báo lỗi. Mật khẩu `123` → báo lỗi. Tên ≥ 3 ký tự + mật khẩu ≥ 6 ký tự → vào luôn, thấy tên tài khoản trên header.
- [ ] Đăng ký trùng tên đã có → báo lỗi.
- [ ] Đăng xuất → về trạng thái khách. Đăng nhập sai mật khẩu → báo lỗi (không nói rõ tên có tồn tại hay không). Đăng nhập đúng → vào được.
- [ ] Tải lại trang (F5) khi đang đăng nhập → vẫn đăng nhập.
- [ ] Hồ sơ: hiện tên + ngày tạo. Đổi mật khẩu với mật khẩu cũ sai → lỗi. Mật khẩu mới < 6 ký tự → lỗi. Đúng → báo thành công; đăng xuất rồi đăng nhập bằng mật khẩu mới.
- [ ] Mở 2 trình duyệt / 2 tài khoản khác nhau: file của người này không hiện ở người kia.

## 2. Điều hướng chung
- [ ] Menu **Product**: 12 mục (4 Cần cấu hình, 3 Convert, 4 Free Tools, 1 Class Noise) mở đúng trang/tab.
- [ ] Header: Home, Class Noise, Guide. Logo → trang chủ.
- [ ] Trang chủ: nút "Làm sạch 1 file, miễn phí" → Xoá dòng trùng; "Xem hướng dẫn" → Guide; 8 ô "Bắt đầu từ một tool nhỏ" mở đúng tool.
- [ ] Guide: bấm từng mục trong mục lục → cuộn đúng mục; mục đang đọc được tô đậm.
- [ ] Chân trang: mọi link mở đúng; "Lên đầu trang" hoạt động.
- [ ] Thu nhỏ cửa sổ về ~390px (điện thoại): trang không bị kéo ngang.

## 3. Free Tools (nhóm "Tự động") — mỗi tool: chọn file → Chạy → xem kết quả → tải về

Làm chung cho cả 4 tool:
- [ ] Bấm **Chạy** khi chưa có file → báo lỗi, không treo.
- [ ] Kéo thả file vào ô; chọn bằng nút "Chọn file"; xem trước 20 dòng + "552 dòng × 20 cột".
- [ ] Tab **Dán text**: dán `a,b⏎1,x⏎1,x⏎2,y` rồi Chạy; dán rỗng rồi Chạy → báo lỗi.
- [ ] "Đổi file" trong khung xem trước; sau khi chạy, "Tải file khác" ở dải đen.
- [ ] Nút **Tải xuống CSV** mở sau khi chạy; mở file tải về kiểm tra đúng nội dung.
- [ ] File Excel `test_attribute_noise.xlsx`: ra cùng số liệu như CSV.
- [ ] `test_empty.csv` → báo "File rỗng"; `test_header_only.csv` → chạy được, 0 dòng, không báo lỗi lạ.
- [ ] Panel "Xong · xử lý tiếp bằng" hiện sau khi chạy; dải đen ghi các bước đã qua.

### 3.1 Xoá dòng trùng
- [ ] Chạy mặc định → **đã xoá 21 dòng (552 → 531)**.
- [ ] "Xem các dòng trùng" → khung 01 đổi sang danh sách (Giữ / Xoá), nút đổi thành "Xem dữ liệu"; bấm lại → về như cũ.
- [ ] Tick "Bỏ qua hoa/thường" + "Bỏ qua khoảng trắng thừa" → **xoá 27 dòng**.
- [ ] Chỉ so theo cột: gõ `email` hoặc `ma_nv, ngay_vao`, giữ **Cuối cùng** → số dòng xoá thay đổi, không lỗi. Gõ tên cột không tồn tại → báo lỗi rõ.

### 3.2 Cắt khoảng trắng
- [ ] Mặc định → **đã sửa 35 ô**. Tick "Gộp khoảng trắng lặp lại" → **45 ô**.
- [ ] "Xem các ô đã sửa": ô tô nền, hiện giá trị trước khi sửa với ký hiệu ␣ ⇥ ⏎ ⍽ ⟨ZW⟩.
- [ ] Bỏ tick "Xoá ký tự vô hình" → số ô đổi giảm (ký tự zero-width giữ lại).

### 3.3 Ô trống
- [ ] Bảng "Ô trống từng cột" liệt kê **20 cột** (mọi cột đều có ô trống vì có 4 dòng trống hoàn toàn), mỗi cột có số ô trống đúng như bảng mục 0.
- [ ] Chạy mặc định (không chọn gì) → chỉ **xoá 4 dòng trống hoàn toàn** (552 → 548).
- [ ] Tick "Xoá luôn cột trống hoàn toàn" → mất cột `cot_trong`.
- [ ] Thử từng cách xử lý: `ghi_chu` → Điền tay từng ô; `luong` → trung vị; `tuoi` → trung bình; `gioi_tinh` → giá trị phổ biến nhất; `phong_ban` → Xoá cả dòng; `ho_ten` → Điền từ ô phía trên. Kiểm tra bảng kết quả.
- [ ] Cột `email`, `so_dien_thoai`, `ngay_*` **không** có "điền trung bình / trung vị / KNN".
- [ ] "Điền tay từng ô": mở bảng các dòng có ô trống, gõ giá trị riêng từng ô; ô để trống lấy "Giá trị chung"; bỏ trống cả hai → ô giữ trống.
- [ ] "Xem các ô trống đã xử lý": dòng bị xoá gạch ngang, ô đã điền tô nền.
- [ ] Mẫu số: 5 cột (ghi_chu cố định, luong trung vị, tuoi trung bình, gioi_tinh phổ biến, email cố định) → **53 ô** được điền.

### 3.4 Sai định dạng
- [ ] Bảng "Kiểu dữ liệu từng cột" đoán đúng: id/tuoi/luong/… số nguyên; email; so_dien_thoai; ngay_sinh/ngay_vao/ngay_ra = Ngày tháng; gioi_tinh/phong_ban/loai_hd/ghi_chu = Nhóm.
- [ ] "Chỉ báo" → **tìm thấy 38 ô sai**; bảng kiểu cột hiện số ô sai ở 8 cột (tuoi 3, luong 5, email 6, so_dien_thoai 6, ngay_sinh 10, ngay_vao 3, diem_dg 3, Hệ số lương 2).
- [ ] "Để trống ô sai" → 38 ô; "Xoá cả dòng" → 37 dòng.
- [ ] Đổi kiểu `ngay_sinh` sang **Văn bản** rồi chạy lại → còn **28 ô** sai (38 − 10).
- [ ] Đổi khuôn ngày `ngay_sinh` thành `%d/%m/%Y` → gần như mọi dòng bị coi sai (vì dữ liệu là yyyy-mm-dd) — đúng như mong đợi.
- [ ] 6 ô `ngay_sinh` dạng `15/03/1990` bị gắn cờ là sai khuôn dù là ngày thật.

## 4. Convert
- [ ] **Đổi delimiter**: `test_semicolon.csv`, từ "Tự nhận diện" sang dấu phẩy → bảng 3 dòng; file tải về vẫn giữ `"Loại tốt, mới"` và `"Sổ ""A5"""` trong ngoặc kép.
- [ ] `test_tab.txt` (tab) → sang `;` ra `ma;ten;gia`.
- [ ] Delimiter gốc chọn sai (vd chọn tab cho file `;`) → không crash.
- [ ] **CSV → JSON**: dán `ma;ten⏎007;An` với delimiter `;` → `"ma": "007"` giữ chuỗi. Tick/bỏ "Tự ép kiểu". Chọn Arrays → mảng của mảng. Bỏ "Dòng đầu là header". Bỏ "Thụt lề".
- [ ] CSV → JSON với `test_attribute_noise.csv` → 552 object, không treo.
- [ ] **JSON → CSV**: `test_convert_nested.json` → cột `dia_chi.thanh_pho`, `dia_chi.quan`; ô có dấu phẩy / xuống dòng được bọc ngoặc kép. `test_convert_lines.jsonl` (mỗi dòng 1 object) cũng chạy; thử delimiter đầu ra `;`.
- [ ] `test_bad.json` → báo lỗi cú pháp rõ ràng (kèm số dòng).
- [ ] Đổi giữa 3 tab Convert: khung xem trước/kết quả được dọn, không lẫn dữ liệu tool trước.

## 5. Cần cấu hình (chạy 2 nhịp: Phát hiện → Áp dụng)

Chung cho cả 4 tool:
- [ ] Chưa chọn file: ô cột báo "Chọn file hoặc dán dữ liệu…".
- [ ] "＋ Thêm cột kiểm tra": mỗi cột chỉ khai 1 lần; danh sách cột trong ô chọn loại các cột đã dùng; nút "✕" xoá form.
- [ ] Sau **Phát hiện**: bảng "Lỗi theo từng cột" (cột nào bao nhiêu ô lỗi), bảng bên phải tô ô lỗi của mọi cột.
- [ ] Ô cách xử lý mặc định **"— Chọn cách xử lý —"**; bấm **Áp dụng** khi chưa chọn gì → không đổi dữ liệu / báo nhắc.
- [ ] Chọn **Xoá dòng** → dòng chữ "Sẽ xoá N dòng (a → b dòng)" hiện ngay; bấm Áp dụng → **hộp xác nhận** hiện số dòng thật; "Huỷ" thì không xoá gì; "Xác nhận xoá và áp dụng" mới xoá.
- [ ] Sau Phát hiện, **sửa bất kỳ ô nào** của form (hoặc thêm/xoá cột) → hiện "Cấu hình hoặc dữ liệu đã đổi… Bấm «Phát hiện» lại" và nút Áp dụng bị khoá; sửa lại y như cũ → hết cảnh báo.
- [ ] Sau Áp dụng: "Tải xuống CSV", "Xử lý tiếp bằng", dải đen; **Hoàn tác bước cuối** và **Bắt đầu lại từ gốc** hoạt động.

### 5.1 Ngoài khoảng
- [ ] Danh sách cột chỉ có cột số (không có ho_ten, email…). Thử `tuoi` 18–65, `luong` 3.000.000–100.000.000, `diem_dg` 1–10, `Hệ số lương` nhỏ nhất 0.1 → **9 / 4 / 6 / 2 ô lỗi**.
- [ ] Bỏ trống một bên (chỉ nhỏ nhất hoặc chỉ lớn nhất) chạy được; bỏ trống cả hai → báo lỗi; nhỏ nhất > lớn nhất → báo lỗi; gõ chữ → báo lỗi.
- [ ] Cách xử lý: "Kéo về biên" (không xoá dòng, giá trị về min/max); "Xoá cả dòng" ở 2 cột cùng lúc (tuoi + luong) → **xoá 13 dòng** (HỢP, không cộng trùng): 552 → 539; "Điền giá trị cố định" với `abc` cho cột số → bị chặn.
- [ ] Ô lỗi dạng chữ ("hai mươi") **không** bị tính là "ngoài khoảng" (đó là lỗi định dạng).

### 5.2 Giá trị bất thường
- [ ] `luong` IQR 1.5 → **9 ô**; chỉ Z-score 3 → **1 ô**; thêm phương pháp thứ 2 → dòng "IQR 1.5 bắt 9 ô · Z-score 3 bắt 1 ô · cả hai cùng bắt 1 ô".
- [ ] `thuong` IQR → **80 ô lỗi + khung vàng "IQR của cột này bằng 0"**; chọn "Kéo về biên" → hiện dòng đỏ cảnh báo mất dữ liệu thật; chọn "Giữ nguyên" → dòng đỏ ẩn.
- [ ] Ngưỡng 0 hoặc âm, để trống ngưỡng → báo lỗi / dùng mặc định.

### 5.3 Không nhất quán
- [ ] Danh sách cột chỉ có cột Nhóm (gioi_tinh, phong_ban, loai_hd, ghi_chu).
- [ ] `gioi_tinh` chuẩn `Nam, Nữ` ngưỡng 1 → **14 ô**; `loai_hd` `Chính thức, Thử việc, Cộng tác viên` → **5 ô**; `phong_ban` `Sales, HR, IT, Marketing, Finance` ngưỡng 1 → **15 ô**, hạ ngưỡng 0.85 → **19 ô** (thêm "Sale", "Marketting").
- [ ] Bỏ trống danh sách chuẩn → báo lỗi; ngưỡng 0.2 → báo lỗi (phải 0.5–1).
- [ ] Áp dụng "Tự chuẩn hoá" → các biến thể về đúng giá trị chuẩn.

### 5.4 Rule liên cột — tab Biểu thức
- [ ] Gõ `ngay_ra >= ngay_vao` → dưới ô hiện dòng xanh "✓ Biểu thức hợp lệ · cách đọc cột…" sau ~1 giây; Phát hiện → **10 dòng vi phạm**, khung thông tin "bỏ qua 13 dòng" (ô trống/sai ngày).
- [ ] `loai_hd = "Thử việc" => luong <= 12000000` → **5**.
- [ ] `phong_ban = Sales => có(hoa_hong)` (chữ trần, không nháy) → **7**.
- [ ] `[Hệ số lương] > 0` (tên cột có dấu cách) → **2**.
- [ ] `luong + thuong == tong_thu_nhap` → **8**.
- [ ] `tuoi >= 18 và tuoi <= 65` → **9**.
- [ ] Ghép bằng nút: bấm chip `tuoi`, nút `>=`, gõ 18, nút `và`, … ra đúng như gõ tay. Bấm chip `phong_ban` → hiện hàng chip giá trị (Sales, IT…) bấm chèn kèm dấu nháy.
- [ ] Gõ dở `tuoi >=` → dòng đỏ báo thiếu vế; `phong_ban = Salse` → báo lỗi gợi ý «Sales»; `khong_co_cot > 1` → báo không có cột; bấm Phát hiện khi biểu thức sai → báo lỗi, không treo.
- [ ] Đổi "Khuôn ngày" thành khuôn sai (`%Y/%m/%d`) → khung đỏ "không đọc được ô nào…", **không** báo "0 lỗi" im lặng.
- [ ] Xoá dòng vi phạm: xem trước "Sẽ xoá 10 dòng vi phạm (552 → 542 dòng)", hộp xác nhận.

### 5.5 Rule liên cột — tab Phụ thuộc hàm
- [ ] Cột xác định `ma_nv`; cột phụ thuộc `ho_ten` + "＋ Thêm cột phụ thuộc" `ngay_sinh` → **32 dòng** bị gắn cờ, có cột "Gợi ý", ô nghi sai tô đậm, ô mốc tô nhạt.
- [ ] Khung phân tích: ho_ten 9 nhóm (7 nghi sai `ho_ten`, 2 nghi sai `ma_nv` — mã bị dùng chung cho 2 người), ngay_sinh 6 nhóm (4 + 2).
- [ ] 4 cách xử lý; "Sửa về giá trị phổ biến nhất" → xem trước **"Sẽ sửa 6 ô"**; nhóm hoà (2 dòng) và nhóm nghi sai `ma_nv` **không bị đụng** ("9 nhóm chưa xác định").
- [ ] "Chỉ xoá dòng nghi sai", "Xoá cả dòng" (hiện đỏ "gồm cả các dòng có thể là đúng").

## 6. Nối tiếp nhiều tool + hoàn tác (xuyên 3 nhóm)
- [ ] Cắt khoảng trắng → "Xử lý tiếp bằng" → Ô trống → Sai định dạng → Xoá dòng trùng → Ngoài khoảng → Đổi delimiter: mỗi bước dùng kết quả bước trước (đầu vào hiện "Đầu vào hiện tại = kết quả sau: …"), số dòng khớp.
- [ ] Dải đen ghi chuỗi các bước; **Hoàn tác bước cuối** lùi từng bước (tối đa 5); **Bắt đầu lại từ gốc** về file ban đầu; **Tải file khác** quên hẳn file cũ ở cả 3 nhóm.
- [ ] Sau CSV → JSON, "Xử lý tiếp bằng" chỉ cho JSON → CSV (các tool khác mờ).
- [ ] Chuyển tab / chuyển nhóm giữa chừng (khi đang có kết quả) rồi quay lại: không lẫn kết quả.
- [ ] Tải lại trang (F5) giữa chừng: chuỗi bước mất (bình thường), không lỗi.

## 7. Class Noise (4 bước) — dùng bộ Credit Card
Dữ liệu: `data/kaggle_creditcard_fraud.csv` (284.807 dòng × 31 cột; nhãn `Class`; 30 cột số, không có cột chữ). Bộ này không có đáp án nhiễu: chỉ số trên màn hình
(CV accuracy, Precision/Recall/F1 từng lớp, ma trận đếm) là chất lượng bộ PHÂN LOẠI, không phải độ chính xác của việc tìm nhiễu (xem CLAUDE.md mục 35).
Muốn thử nhanh có thể dùng mẫu nhỏ (vd 5.000 dòng gồm đủ 492 dòng gian lận).
- [ ] Bước 1: 3 thẻ thuật toán; chưa chọn file → nút "Tải lên & tiếp tục" mờ; chọn file → hiện bảng xem trước 100 dòng + "N dòng × 31 cột" + nút "↺ Đổi file"; chọn **Distance-based** → tải lên.
- [ ] Bước 2: chọn nhãn `Class`; bấm "Phát hiện" khi chưa tick đặc trưng → báo "chọn ít nhất 1 cột".
- [ ] "Tích tất cả" → tick đủ 30 cột số, không cột nào bị khoá; "Bỏ tích tất cả" bỏ hết. "Chạy giảm cột tự động" → ra biểu đồ và tự tick một số cột `V` (không kỳ vọng số cụ thể); bước lọc tương quan gần như không loại cột nào (các cột `V` là PCA).
- [ ] Tham số hiện đúng theo thuật toán: Ensemble (số fold), Distance (k), Single (số cây, số fold).
- [ ] Bước 3 (Kết quả): Ensemble → 4 thẻ + bảng accuracy từng classifier; Distance-based → 4 thẻ, ẩn bảng precision/ma trận; Single learning → 5 thẻ + bảng precision/recall + ma trận. Tham khảo (một lần chạy Single learning trên nguyên bộ): CV accuracy 99,94% vs baseline 99,83%; F1 lớp gian lận 0,825; 96 dòng bị gắn cờ.
- [ ] Tìm trong danh sách ("zzzz" → "Không có dòng nào khớp"); phân trang.
- [ ] Bước 4 (Xử lý): hiện ghi chú "chưa có xử lý"; nút "Quay lại kết quả".
- [ ] Bấm thanh bước 1 để quay lại, đổi thuật toán, tải lên lại, chạy lại → kết quả đúng thuật toán mới.
- [ ] Tải `test_attribute_noise.csv` lên (có cột chữ): cột chữ (`ho_ten`, `gioi_tinh`...) bị KHOÁ ô tick + ghi chú "cột chữ, chưa hỗ trợ"; "Tích tất cả" chỉ tick cột số. Gọi API với cột chữ → HTTP 400 "Cột đặc trưng phải là cột SỐ…".
- [ ] Nhãn chỉ có 1 giá trị / cột nhãn toàn ô trống → báo lỗi rõ ràng, không treo.
- [ ] Chạy Single learning-based trên nguyên bộ Credit Card: có chữ "có thể mất vài phút"; trang không bị đơ vĩnh viễn.

## 8. Trường hợp biên / "phá" thử
- [ ] File sai đuôi (vd `.png`, `.pdf`) kéo vào ô → từ chối hoặc báo lỗi rõ.
- [ ] File CSV một cột; file có tiêu đề trùng tên cột; tên cột có dấu cách / tiếng Việt / ký tự lạ (`Hệ số lương`).
- [ ] File CSV dùng dấu `;` mở trong Free Tools (không có ô chọn delimiter): kết quả có hợp lý không.
- [ ] Bấm nút liên tiếp thật nhanh (Chạy 3 lần liền; Phát hiện rồi Áp dụng ngay) → không chạy chồng, không ra kết quả sai.
- [ ] Mở 2 tab trình duyệt cùng tài khoản, làm 2 việc khác nhau → không lẫn.
- [ ] Thu nhỏ / phóng to cửa sổ: bố cục không vỡ; bảng rộng có thanh cuộn ngang.
- [ ] Dán nội dung rất lớn (vài MB) vào ô "Dán text".
- [ ] Tắt server giữa chừng rồi bấm Chạy → báo lỗi kết nối, trang không trắng.
- [ ] Khởi động lại server: phải đăng nhập lại (đã biết).
