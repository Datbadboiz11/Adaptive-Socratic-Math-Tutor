# Code nghiên cứu

Thư mục này chứa pipeline dữ liệu và công cụ thí nghiệm theo [kế hoạch tổng](../docs/planning/project-plan.md). Source code được version trong Git; dataset và kết quả chứa bản ghi học sinh lưu trong `data/` đã ignore.

Hiện có [audit ASSISTments 2017](data/audit_assistments_2017.py), chạy từ gốc repo:

```powershell
python research/data/audit_assistments_2017.py
```

Đọc [báo cáo và giới hạn](../docs/research/data/README.md) trước khi tạo observation, chia tập hoặc fit BKT. Script này mới kiểm kê schema/chất lượng, chưa huấn luyện mô hình.
