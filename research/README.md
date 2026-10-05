# Code nghiên cứu

Thư mục này chứa pipeline dữ liệu và công cụ thí nghiệm theo [kế hoạch tổng](../docs/planning/project-plan.md). Source code được version trong Git; dataset và kết quả chứa bản ghi học sinh lưu trong `data/` đã ignore.

Đã có audit, pipeline action → observation và BKT baseline train/dev. Chạy từ gốc repo:

```powershell
python research/data/audit_assistments_2017.py
python -m research.data.preprocess_assistments_2017
python -m research.bkt.benchmark
```

Audit và preprocess dùng thư viện chuẩn Python. Benchmark cần [requirements riêng](requirements.txt) gồm NumPy/SciPy; đọc [hướng dẫn chạy](../docs/research/data/RUNBOOK.md), [protocol](../docs/research/data/observation-protocol.md) và [kết quả dev v1](../docs/research/data/bkt-dev-v1.md). Test được giữ lại, không đọc trong lệnh benchmark. Không thay tham số bootstrap sản phẩm bằng kết quả trên dữ liệu công khai.
