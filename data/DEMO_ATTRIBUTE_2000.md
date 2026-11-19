# Bộ dữ liệu DEMO cho phần Attribute Noise (Product) — nhân viên, 1997 dòng

Dùng để **chạy trực tiếp lúc bảo vệ** và **trích số liệu vào báo cáo**. Một file duy nhất chứa đủ mọi loại lỗi mà các tool Attribute của Denoise dò được
(Free Tools + Cần cấu hình), kèm đáp án từng ô lỗi. Class Noise không dùng file này (dùng Credit Card, xem `CLAUDE.md` mục 35, 38).

| File | Nội dung |
|---|---|
| `data/demo_attribute_noise_2000.csv` | **1997 dòng × 20 cột**, dữ liệu để upload (UTF-8; nếu mở bằng Excel bị lỗi font tiếng Việt thì dùng bản `.xlsx` hoặc upload thẳng vào Denoise) |
| `data/demo_attribute_noise_2000.xlsx` | bản Excel y hệt (đã kiểm: ra đúng cùng số liệu) |
| `data/demo_attribute_noise_2000_ground_truth.csv` | **đáp án**: 1087 dòng, mỗi dòng là một ô/dòng bị cấy lỗi (dòng, cột, loại lỗi, giá trị gốc, giá trị đã cấy, tool nên bắt) |

Cột `row` trong file đáp án = số thứ tự dòng dữ liệu (1 = dòng đầu tiên sau tiêu đề), **khớp cột "Dòng" trên giao diện**. Mở bằng Excel thì cộng thêm 1 vì có dòng tiêu đề.

**Sinh lại** (hạt giống cố định nên ra đúng cùng file): `SCALE=3.62 OUT_NAME=demo_attribute_noise_2000 python3 data/generate_test_attribute_noise.py`
(PowerShell: `$env:SCALE="3.62"; $env:OUT_NAME="demo_attribute_noise_2000"; python data/generate_test_attribute_noise.py`). Cùng script đó với `SCALE=1` ra bộ test nhỏ 552 dòng cũ (`test_attribute_noise.*`, giữ nguyên từng ô).

## 1. Các cột

| Cột | Ý nghĩa | Ghi chú |
|---|---|---|
| `id` | số thứ tự dòng | |
| `ma_nv` | mã nhân viên | 1442 mã khác nhau; nhiều nhân viên có 2–3 hợp đồng (để thử **Phụ thuộc hàm** `ma_nv → ho_ten, ngay_sinh`) |
| `ho_ten`, `gioi_tinh`, `tuoi`, `ngay_sinh`, `email`, `so_dien_thoai` | thông tin cá nhân | |
| `phong_ban` | Sales / HR / IT / Marketing / Finance | |
| `loai_hd` | Chính thức / Thử việc / Cộng tác viên | |
| `ngay_vao`, `ngay_ra` | ngày vào / ra của hợp đồng (yyyy-mm-dd) | |
| `luong`, `thuong`, `tong_thu_nhap` | lương, thưởng (85% bằng 0), tổng = lương + thưởng | |
| `hoa_hong` | % hoa hồng (chỉ phòng Sales có) | |
| `diem_dg` | điểm đánh giá (1–10) | |
| `Hệ số lương` | tên cột **có dấu cách + tiếng Việt** (để thử cách viết `[Hệ số lương]` trong Biểu thức) | |
| `ghi_chu` | ghi chú chữ | |
| `cot_trong` | cột **trống hoàn toàn** | |

## 2. Lỗi đã cấy sẵn (từ file đáp án)

| Loại lỗi | Cấy ở cột | Số lượng |
|---|---|---|
| Ô trống (`""`, NA, N/A, null, -, ?, none, --) | ghi_chu 109 · email 25 · luong 22 · gioi_tinh 22 · so_dien_thoai 22 · ho_ten 18 · phong_ban 18 · tuoi 14 · diem_dg 14 · ngay_sinh 14 · Hệ số lương 11 · ngay_ra 11 · ngay_vao 11 | 311 ô, thêm 14 dòng trống hoàn toàn và cột `cot_trong` trống 100% |
| Sai định dạng | ngay_sinh 36 · email 22 · so_dien_thoai 22 · luong 18 · diem_dg 11 · tuoi 11 · ngay_vao 11 · Hệ số lương 7 | 138 ô |
| Khoảng trắng thừa (đầu / cuối / lặp giữa / ký tự vô hình / non-breaking) | ghi_chu 87 · ho_ten 54 | 141 ô |
| Dòng trùng | trùng hệt 65 + gần trùng 22 (email viết HOA, ghi_chu thừa dấu cách) | 87 dòng |
| Ngoài khoảng | tuoi 33 · diem_dg 22 · luong 14 · Hệ số lương 7 | 76 ô |
| Giá trị bất thường | luong: 29 ô lệch hẳn (45–70 triệu) · thuong: cột 85% bằng 0 | 29 ô |
| Không nhất quán (khác hoa/thường, vài ô gõ sai chính tả) | phong_ban 67 · gioi_tinh 50 · loai_hd 18 | 135 ô |
| Rule liên cột — Biểu thức | ngay_ra < ngay_vao 36 · tong_thu_nhap ≠ luong + thuong 29 · Thử việc mà lương > 12 triệu 18 · Sales thiếu hoa_hong 25 · [Hệ số lương] ≤ 0 7 | 115 |
| Rule liên cột — Phụ thuộc hàm `ma_nv → …` | ho_ten 25 · ngay_sinh 15 · ma_nv 7 | 47 ô |

## 3. Số kỳ vọng khi chạy từng tool trên FILE GỐC

Mỗi dòng dưới đây đã chạy qua **đúng API của web** và đối chiếu với **phép tính độc lập bằng pandas** (không dùng code của web): **35 phép đo, khớp 100%**.
Khi demo, trước mỗi tool nhớ bấm **"Bắt đầu lại từ gốc"** (hoặc tải lại file) vì các tool **nối tiếp** nhau; số khi nối tiếp ở mục 4.

### Free Tools (nhóm "Tự động")

| Tool | Cách chạy | Kỳ vọng |
|---|---|---|
| **Xoá dòng trùng** | mặc định | xoá **78** dòng (1997 → 1919) = 65 trùng hệt + 13 dòng trống giống nhau |
| | tick bỏ qua hoa/thường + khoảng trắng | xoá **100** dòng (thêm 22 dòng gần trùng) |
| **Cắt khoảng trắng thừa** | mặc định | **127** ô đổi (đầu 40 · cuối 40 · ký tự vô hình 14 · non-breaking 11 · ghi_chu thừa dấu cách ở 22 dòng gần trùng) |
| | tick gộp khoảng trắng lặp | **163** ô (thêm 36 ô lặp giữa chữ) |
| **Sai định dạng** | báo cáo | **138** ô sai ở **132** dòng (ngay_sinh 36 · email 22 · so_dien_thoai 22 · luong 18 · diem_dg 11 · tuoi 11 · ngay_vao 11 · Hệ số lương 7) |
| **Ô trống** | xem số ô trống từng cột | tổng **602** ô trống + cột `cot_trong` trống 100%; **14** dòng trống hoàn toàn |
| | | từng cột: Hệ số lương 25 · diem_dg 28 · email 39 · ghi_chu 123 · gioi_tinh 36 · ho_ten 32 · hoa_hong 39 · luong 36 · ngay_ra 25 · ngay_sinh 28 · ngay_vao 25 · phong_ban 32 · so_dien_thoai 36 · tuoi 28 (đã gồm 14 ô từ 14 dòng trống hoàn toàn; các cột id, ma_nv, loai_hd, thuong, tong_thu_nhap chỉ có đúng 14 ô đó) |

### Cần cấu hình

| Tool | Cấu hình nhập | Kỳ vọng |
|---|---|---|
| **Ngoài khoảng** | tuoi (số nguyên) 18–65 · luong (số nguyên) 3.000.000–100.000.000 · diem_dg (số thực) 1–10 · Hệ số lương (số thực) 0,1–100 | tuoi **33** · luong **14** · diem_dg **22** · Hệ số lương **7** ô lỗi (đúng bằng số đã cấy); chọn "Xoá dòng" cho tuoi + luong → xoá hợp **47** dòng |
| **Giá trị bất thường** | luong, IQR 1,5 | **32** ô = 29 ô cấy + 3 ô 900.000.000 (biên IQR: −3,7tr … 32,9tr) |
| | luong, Z-score 3 | chỉ **3** ô: các giá trị cực đoan làm độ lệch chuẩn phình to (35,6tr) nên Z-score bỏ sót — **cho thấy vì sao nên có cả hai phương pháp** |
| | thuong, IQR 1,5 | **306** ô + **khung cảnh báo vàng "IQR = 0"** (Q1 = Q3 = 0 nên mọi ô khác 0 đều bị gắn cờ; không nên chọn "Kéo về biên") |
| **Không nhất quán** | giá trị chuẩn gioi_tinh: `Nam, Nữ` · loai_hd: `Chính thức, Thử việc, Cộng tác viên` · phong_ban: `Sales, HR, IT, Marketing, Finance`; ngưỡng giống nhau = 1 | gioi_tinh **50** · loai_hd **18** · phong_ban **53** ô |
| | hạ ngưỡng xuống 0,85 | phong_ban lên **67** ô (bắt thêm "Sale", "Marketting"); cả 3 cột cùng lúc: **132** dòng |
| **Rule liên cột · Biểu thức** | `ngay_ra >= ngay_vao` | **36** dòng vi phạm |
| | `luong + thuong = tong_thu_nhap` (sai số 0,01) | **29** dòng |
| | `loai_hd = "Thử việc" => luong <= 12000000` | **18** dòng |
| | `phong_ban = "Sales" => có(hoa_hong)` | **25** dòng |
| | `[Hệ số lương] > 0` | **7** dòng |
| **Rule liên cột · Phụ thuộc hàm** | `ma_nv` xác định `ho_ten` + `ngay_sinh` | ho_ten **78** dòng (32 nhóm) · ngay_sinh **52** dòng (22 nhóm) · hợp **116** dòng |
| | cách xử lý | "Sửa về giá trị phổ biến nhất" **22** ô · "Chỉ xoá dòng nghi sai" **22** dòng · "Xoá cả dòng" **116** dòng · **32** nhóm giữ nguyên vì chưa xác định được (hoà, hoặc nghi sai chính cột `ma_nv`) |

## 4. Số khi chạy NỐI TIẾP (làm theo thứ tự lúc demo)

Chuỗi gợi ý: **Xoá dòng trùng → Cắt khoảng trắng → Ô trống (xoá dòng trống hoàn toàn)**, rồi mới kiểm lỗi logic bằng các tool Cần cấu hình (đúng lời khuyên "làm sạch trước, kiểm logic sau").

| Bước | Kỳ vọng |
|---|---|
| 1. Xoá dòng trùng | 1997 → **1919** dòng (xoá 78) |
| 2. Cắt khoảng trắng | **127** ô đổi, vẫn 1919 dòng |
| 3. Ô trống → xoá dòng trống hoàn toàn | xoá **1** dòng (13 dòng trống đã bị bước 1 xoá vì giống nhau) → **1918** dòng |
| 4. Ngoài khoảng / Không nhất quán / Biểu thức / Phụ thuộc hàm | **giữ nguyên** các số ở mục 3 (33 · 14 · 22 · 7 · 50 · 18 · 53/67 · 36 · 29 · 18 · 25 · 7 · 116 dòng) |
| 5. Giá trị bất thường | luong IQR **32**, Z-score **3** (giữ nguyên); thuong IQR **295** ô (giảm từ 306 vì 11 dòng trùng bị xoá có thưởng khác 0) |

Mỗi bước đều có **hộp xác nhận khi xoá dòng** và nút **"↶ Hoàn tác bước cuối"** ở dải đen — nên thử cho hội đồng xem.

## 5. Kịch bản demo gợi ý (≈ 10–12 phút)

1. **Giới thiệu file** (30 giây): mở `demo_attribute_noise_2000.csv`, nói "2000 dòng nhân viên, em cấy sẵn 1087 lỗi thuộc 9 loại, có file đáp án để đối chiếu".
2. **Free Tools**: Xoá dòng trùng (78; tick bỏ qua hoa/thường → 100) → Cắt khoảng trắng (127; xem danh sách ô đã sửa; tick gộp → 163) → Sai định dạng (138 ô, bảng kiểu dữ liệu từng cột) → Ô trống (602 ô; thử "Điền tay từng ô" cho `luong`).
3. **Cần cấu hình**: Ngoài khoảng (nhập 4 cột, xem bảng "lỗi theo từng cột") → Giá trị bất thường (luong IQR 32 ô so với Z-score chỉ 3 ô, và cảnh báo vàng ở `thuong`) → Không nhất quán (đổi ngưỡng 1 → 0,85) → Biểu thức (gõ `ngay_ra >= ngay_vao`, xem dòng xanh/đỏ báo hợp lệ khi đang gõ; thử `phong_ban = Sales => có(hoa_hong)` gõ trần không cần nháy) → Phụ thuộc hàm (xem cột "Gợi ý", thử "Sửa về giá trị phổ biến nhất").
4. **Kết**: mở file đáp án, cho thấy số web tìm được **khớp đúng số lỗi đã cấy** ở mọi tool.

## 6. Ghi vào báo cáo

- **Cách kiểm chứng:** mỗi tool chạy qua API thật của web; kết quả đối chiếu với (a) phép tính độc lập bằng pandas và (b) đáp án cấy sẵn. Tất cả các phép đo ở mục 3 và 4 **khớp 100%**.
- **Độ bắt lỗi (so với đáp án cấy):** Sai định dạng 138/138 · Ngoài khoảng 76/76 · Không nhất quán 135/135 (ngưỡng 0,85) · Giá trị bất thường 29/29 ô cấy (IQR) · Biểu thức 115/115 · dòng trùng 65/65 (+22/22 gần trùng khi bật bỏ qua hoa/thường) · khoảng trắng 141/141 (khi bật gộp khoảng trắng lặp; 105/141 ở chế độ mặc định vì ô "lặp giữa chữ" chỉ đổi khi gộp).
- **Lưu ý khi diễn giải:** lỗi cấy nhân tạo và các tool đều theo luật xác định, nên độ bắt 100% chứng minh *tool làm đúng như thiết kế*, không chứng minh khả năng tổng quát hoá trên dữ liệu thật. Giá trị bất thường (IQR/Z-score) còn bắt thêm 3 ô 900.000.000 ngoài 29 ô cấy; Z-score ở cột `luong` chỉ bắt 3 ô vì độ lệch chuẩn bị chính giá trị cực đoan kéo lên.
- **Giới hạn:** bộ dữ liệu sinh bằng script với một hạt giống cố định (một bộ duy nhất); lỗi cấy theo mẫu có sẵn (ví dụ các ô sai định dạng lặp lại vài kiểu), chưa phải dữ liệu bẩn thật.
