# Code nghiên cứu

Thư mục này chứa pipeline dữ liệu và công cụ thí nghiệm theo [kế hoạch tổng](../docs/planning/project-plan.md). Source code được version trong Git; dataset và kết quả chứa bản ghi học sinh lưu trong `data/` đã ignore.

Đã có audit, pipeline action → observation và BKT baseline train/dev. Chạy từ gốc repo:

```powershell
python research/data/audit_assistments_2017.py
python -m research.data.preprocess_assistments_2017
python -m research.bkt.benchmark
```

Đánh giá phần của Member 3 trên bộ dev tự soạn (không phải kết quả báo cáo). Mặc định không gọi API; gọi model thật phải thêm `--yes` và có key trong `.env`:

```powershell
python research/agent/compare_proposers.py --agent fake        # Agent LLM so với Rule-policy
python research/extraction/evaluate_extraction.py --llm fake   # LLM extraction
```

Phần dùng chung của các script có gọi LLM (đọc `.env`, xác nhận trước khi gọi, thống kê token/chi phí) nằm ở `llm_support.py`. Client, kiểu usage và client giả dùng chung nằm ở `backend/app/llm/`. Thiết kế và giới hạn: [Agent LLM](../docs/implementation/agent/llm-agent.v1.md), [LLM extraction](../docs/implementation/extraction/llm-extraction.v1.md).

Audit và preprocess dùng thư viện chuẩn Python. Benchmark cần [requirements riêng](requirements.txt) gồm NumPy/SciPy; đọc [hướng dẫn chạy](../docs/research/data/RUNBOOK.md), [protocol](../docs/research/data/observation-protocol.md) và [kết quả dev v1](../docs/research/data/bkt-dev-v1.md). Test được giữ lại, không đọc trong lệnh benchmark. Không thay tham số bootstrap sản phẩm bằng kết quả trên dữ liệu công khai.
