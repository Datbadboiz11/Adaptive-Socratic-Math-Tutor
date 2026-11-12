# Code nghiên cứu

Thư mục này chứa pipeline dữ liệu và công cụ thí nghiệm theo [kế hoạch tổng](../docs/planning/project-plan.md). Source code được version trong Git; dataset và kết quả chứa bản ghi học sinh lưu trong `data/` đã ignore.

Đã có audit, pipeline action → observation và BKT baseline train/dev. Chạy từ gốc repo:

```powershell
python research/data/audit_assistments_2017.py
python -m research.data.preprocess_assistments_2017
python -m research.bkt.benchmark
```

Audit và preprocess dùng thư viện chuẩn Python. Benchmark cần [requirements riêng](requirements.txt) gồm NumPy/SciPy; đọc [hướng dẫn chạy](../docs/research/data/RUNBOOK.md), [protocol](../docs/research/data/observation-protocol.md) và [kết quả dev v1](../docs/research/data/bkt-dev-v1.md). Test được giữ lại, không đọc trong lệnh benchmark. Không thay tham số bootstrap sản phẩm bằng kết quả trên dữ liệu công khai.

[analyzer/evaluate.py](analyzer/evaluate.py) chạy 180 ca phát triển tự biên soạn và thử từng bài pilot offline. Đọc [hướng dẫn Analyzer](../docs/implementation/curriculum/analyzer.v1.md) trước khi diễn giải kết quả: nhãn nháp, có trùng mẫu phát triển; không phải benchmark test độc lập. Công cụ dùng dependencies backend, không cần NumPy/SciPy hoặc OpenAI.

[retrieval/bge_m3_colab.ipynb](retrieval/bge_m3_colab.ipynb) tạo vector dense BGE-M3 trên Kaggle hoặc Colab GPU, đo thời gian/VRAM và so sánh metadata/BM25/semantic trên 90 query nháp. Giữ tên notebook cũ; Kaggle tự đọc Dataset gắn vào notebook và xuất ZIP vào Output, chạy nền bằng Save Version → Save & Run All. Đã chạy thực tế trên Kaggle T4 ngày 10/10/2026, nhập vector vào `data/retrieval/bge-m3-v1/` và tái lập rankings/metrics offline: BGE-M3 Recall@3 = 0,875, Hit@3 = 0,938, nDCG@3 = 0,854; chưa vượt BM25 trên mọi tiêu chí. Đọc [hướng dẫn và phân tích kết quả](../docs/implementation/curriculum/grounding.v1.md). `retrieval/evaluate.py` dùng chung giữa máy và notebook; đánh giá lại vector đã xuất không cần tải model. Nhãn phát triển chưa review; backend local chưa có model cache để encode câu hỏi mới.

[Qwen3-Embedding-4B riêng](retrieval/qwen3_4b/README.md) đã chạy FP16 trên Kaggle T4 ×2 và kiểm tra Output ngày 19/10/2026. Kết quả lưu tại `data/retrieval/qwen3-4b-v1/`, ZIP tại `data/exports/pilot-retrieval-qwen3-4b.zip`; notebook đã chạy giữ trong thư mục experiment. Tính lại từ vector tái lập toàn bộ metrics/270 rankings, Recall@3 = 0,958333, Hit@3 = 1,0, nDCG@3 = 0,954360 trên 80 query dương nháp. Xem [báo cáo Qwen v1 và giới hạn](../docs/research/retrieval/qwen3-4b-v1.md). BGE và cấu hình backend giữ nguyên; chưa chọn model sản phẩm từ bộ dev nhỏ này.
