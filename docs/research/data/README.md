# Dữ liệu nghiên cứu — bước kiểm kê đầu tiên

Đây là nhánh công việc theo [kế hoạch đồ án 12 tuần](../../planning/project-plan.md) và [PRD](../../product/prd.md), **không phải pipeline BKT đã huấn luyện**. Dữ liệu thô nằm trong `data/` và được Git bỏ qua. Chỉ báo cáo tổng hợp không chứa ID học sinh ở [assistments_2017_audit.json](assistments_2017_audit.json).

## Nguồn và phạm vi lần kiểm kê

Script [audit_assistments_2017.py](../../../research/data/audit_assistments_2017.py) đọc mười file `student_log_1.csv` đến `student_log_10.csv` trong bản **ASSISTments Data Mining Competition 2017 — Competition Training Set**. Bản `anonymized_full_release_competition_dataset.csv` trong cùng gói là release thay thế và **không được nối** vào mười log, vì có thể trùng dữ liệu. Junyi trong `data/archive/` chưa được đưa vào báo cáo này.

Chạy từ thư mục gốc repo:

```powershell
python research/data/audit_assistments_2017.py
python -m unittest discover -s tests -p test_assistments_audit.py -v
```

Có thể dùng `--data-root` nếu đặt dữ liệu ở nơi khác và `--max-rows-per-file 1000 --output data/audit-sample.json` để thử nhanh. **Không commit** file mẫu hoặc các bản ghi đã biến đổi trong `data/`.

## Phát hiện trên bản hiện có

| Chỉ số | Kết quả | Ý nghĩa |
|---|---:|---|
| Dòng hành động | 942.816 | Có `correct` theo từng dòng, nhưng dòng hành động chưa đồng nghĩa một opportunity BKT |
| Học sinh ẩn danh | 1.709 | Có thể chia theo học sinh sau khi chốt protocol |
| Nhãn skill gốc | 102 | Chưa ánh xạ vào 40 concept/skill tiếng Việt |
| Problem ID | 4.117 | Chưa kiểm tra trùng biến thể/họ bài |
| Thời gian giảm trong thứ tự file của cùng học sinh | 2.554 | Phải sắp xếp/kiểm tra theo student, thời gian và action ID trước khi tạo chuỗi |
| ID xuất hiện ở cả hai file nhãn cuộc thi | 48 | Không dùng hai file này như split KT mặc định; cần tìm hiểu bản ghi lặp và giao thức gốc |
| ID lặp trong `training_label.csv` | 47 dòng | Không giả định một dòng nhãn tương ứng một học sinh |

`student_log_3.csv` đến `student_log_10.csv` ghi `Prev5count`, còn log 1–2 ghi `prev5count`; audit chấp nhận **duy nhất** khác biệt chữ hoa/thường này và báo cáo rõ. Cột bắt buộc thiếu hoặc thay đổi cấu trúc vẫn gây lỗi.

Theo [mô tả cuộc thi của ASSISTments](https://sites.google.com/view/assistmentsdatamining/data-mining-competition-2017), mục tiêu của `training_label.csv` là dự đoán kết quả dài hạn về tham gia STEM, **không phải nhãn đúng/sai cho từng bước học**. [Bảng giải thích cột của ASSISTments](https://docs.google.com/spreadsheets/d/1QVUStXiRerWbH1X0P11rJ5IsuU2Xutu60D1SjpmTMlk/edit) định nghĩa `original` là bài gốc thay vì bài scaffold; `hint` là hành động xin gợi ý; `attemptCount` là số bài đã làm trong tutor, không phải số lần thử trên bài hiện tại. Vì thế audit chỉ đếm giá trị trường, chưa suy ra “đúng độc lập” hoặc cập nhật BKT. `AveKnow`, `Ln`, `AveCorrect` và các thống kê tương lai/toàn lịch sử cũng không được dùng làm ground truth hay đặc trưng trước dự đoán khi chưa chứng minh không rò rỉ.

## Bước kế tiếp trên đường găng

1. Chốt đơn vị opportunity/observation và chính sách loại hint/scaffold/lượt lặp từ **tài liệu cột và kiểm tra mẫu**, không suy ra từ tên cột. Giữ `unverified` khi thiếu thông tin.
2. Thiết kế split **theo học sinh và họ bài**, khóa test trước khi fit/chọn ngưỡng. Ghi manifest và version, không dùng split `training_label`/`validation_test_label` của mục tiêu STEM làm split KT.
3. Xây pipeline streaming chuẩn hóa action → observation ở `data/processed/`, lưu lý do giữ/loại và kiểm tra không trùng opportunity. Không xuất ID/bản ghi thô vào Git.
4. Chạy BKT baseline với đánh giá dự đoán lượt tiếp theo (log loss, AUC, Brier/calibration) và đối chiếu online BKT hiện có. Báo riêng kết quả trên dữ liệu này; không coi tham số là đã hiệu chuẩn cho học sinh Việt Nam.
5. Song song, rà taxonomy 40 concept, quan hệ prerequisite và nội dung tiếng Việt theo quy trình duyệt; chỉ map raw skill khi có căn cứ. Junyi là benchmark bổ sung và FoundationalASSIST không chặn pipeline chính.

Audit đọc ID học sinh ẩn danh trong bộ dữ liệu cục bộ nhưng không ghi các ID đó ra báo cáo. Nó không xác nhận quyền phát hành lại bộ dữ liệu và không chứng minh chất lượng sư phạm. Khi chia sẻ repo, giữ dữ liệu gốc và file biến đổi trong `data/`.
