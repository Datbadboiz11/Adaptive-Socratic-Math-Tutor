# Code nghiên cứu

Thư mục này chứa pipeline dữ liệu và công cụ thí nghiệm theo [kế hoạch tổng](../docs/planning/project-plan.md). Source code được version trong Git; dataset và kết quả chứa bản ghi học sinh lưu trong `data/` đã ignore.

Đã có audit, pipeline action → observation và BKT baseline train/dev. Chạy từ gốc repo:

```powershell
python research/data/audit_assistments_2017.py
python -m research.data.preprocess_assistments_2017
python -m research.bkt.benchmark
```

Benchmark mặc định chỉ fit `train.csv`, đánh giá `dev.csv` và ghi báo cáo RQ1a vào `data/experiments/rq1a_kt_benchmark_report.json` cùng bảng Markdown. Chỉ mở held-out `test.csv` khi gọi tường minh `python -m research.bkt.benchmark --evaluate-test`. Audit và preprocess dùng thư viện chuẩn Python; benchmark cần [requirements riêng](requirements.txt) gồm NumPy/SciPy. Đọc [hướng dẫn chạy](../docs/research/data/RUNBOOK.md), [protocol](../docs/research/data/observation-protocol.md) và [kết quả dev v1](../docs/research/data/bkt-dev-v1.md). Không thay tham số bootstrap sản phẩm bằng kết quả trên dữ liệu công khai.
