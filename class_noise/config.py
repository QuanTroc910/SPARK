from dataclasses import dataclass


@dataclass
class ClassNoiseConfig:
    """Cấu hình 1 lượt phát hiện class noise (nhãn bị gán sai).

    Khác hẳn attribute noise (chạy được ngay từ dtype của 1 cột), class noise
    là 1 bài toán supervised learning: phải biết cột nào là NHÃN (label/target)
    và cột nào là ĐẶC TRƯNG (feature) dùng để dự đoán nhãn đó. Hệ thống KHÔNG
    thể tự suy ra quan hệ này từ dữ liệu -- đây là domain knowledge người dùng
    phải tự khai, giống hệt tinh thần CrossFieldRuleConfig ở attribute_noise/
    (xem CLAUDE.md mục 7 để hiểu lý do tương tự).

    label_column: tên cột chứa nhãn (chuỗi, dạng phân loại -- vd "Yes"/"No",
        "Sales"/"It"/"Hr"...).
    feature_columns: các cột ĐẶC TRƯNG dùng để dự đoán nhãn. Bản đầu này CHỈ
        hỗ trợ cột SỐ (numeric) -- Random Forest cần input dạng số; cột chữ
        (category/text) muốn dùng làm đặc trưng sẽ cần thêm bước mã hoá,
        chưa làm ở đây.
    n_estimators: số cây trong Random Forest (rừng càng nhiều cây thì kết quả
        càng ổn định nhưng chạy càng chậm).
    cv_folds: số fold cho Stratified K-Fold cross-validation -- dùng để lấy
        "pred_probs" trung thực cho MỌI dòng (xem docstring
        get_out_of_fold_probs() trong confident_learning.py).
    random_state: seed cố định để kết quả tái lập y hệt giữa các lần chạy.
    min_samples_leaf: số dòng tối thiểu ở MỖI lá của cây (chỉ Confident Learning dùng).
        Mặc định 5 thay vì 1: nhãn có nhiễu mà để cây mọc tới từng dòng lẻ thì cây
        "học thuộc" luôn cả nhãn sai, xác suất dự đoán bị đẩy về 0/1 quá cực đoan --
        trong khi Confident Learning cần xác suất mượt, phản ánh đúng độ tự tin.
    balanced: True = Random Forest dùng class_weight="balanced" (bù cho lớp hiếm); False =
        không bù (MẶC ĐỊNH). Bù thì xác suất bị đẩy lên cho lớp hiếm, làm Confident Learning
        gắn cờ quá tay và ước lượng tỷ lệ nhãn sai bị cao. Đã đo (cấy nhiễu có kiểm soát, 3 seed):
        với min_samples_leaf=5 (mặc định) tắt bù tốt hơn hoặc ngang bù ở cả 7 kịch bản trên Car,
        Adult, Credit Card; chênh lớn nhất ở nhiễu đồng đều trên Credit Card 5% (F1 0,715 so với
        0,449). Với min_samples_leaf=1 thì KHÔNG đúng ở mọi nơi: Credit Card nhiễu lớp hiếm 10%
        bật bù lại tốt hơn (0,786 so với 0,740). Chỉ Confident Learning dùng. Số liệu đầy đủ:
        CLAUDE.md, kế hoạch mục 3.
    """

    label_column: str
    feature_columns: list[str]
    n_estimators: int = 300
    cv_folds: int = 5
    random_state: int = 42
    min_samples_leaf: int = 5
    balanced: bool = False
