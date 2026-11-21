# Chạy pipeline ASSISTments 2017 và BKT

Chạy từ gốc repository. Không cần bật Docker, PostgreSQL hoặc OpenAI; không có API trả phí. Pipeline đọc file CSV đã có, không nhập log công khai vào database sản phẩm.

## Môi trường

Audit và preprocess chỉ cần Python 3.12. Benchmark cần NumPy/SciPy tại [research/requirements.txt](../../../research/requirements.txt). Khi có kết nối pip, có thể tạo môi trường riêng:

```powershell
python -m venv .venv-research
.\.venv-research\Scripts\python.exe -m pip install -r research/requirements.txt
```

`.venv-research/` và `data/` được Git ignore. Lần chạy trong Codex dùng Python runtime truy cập NumPy 2.2.6/SciPy 1.14.1 đã có trên máy; `.venv` của backend chưa được cài hai thư viện này. Runtime Codex không phải phụ thuộc bắt buộc của repository.

## Các lệnh

```powershell
python research/data/audit_assistments_2017.py
python -m research.data.preprocess_assistments_2017
.\.venv-research\Scripts\python.exe -m research.bkt.benchmark
.\.venv-research\Scripts\python.exe -m unittest discover -s tests -p test_research_pipeline.py -v
```

Preprocess từ chối ghi đè một run đã tồn tại. Benchmark mặc định fit trên train, đánh giá dev và không mở `test.csv`; báo cáo RQ1a được ghi vào file JSON và Markdown. Chỉ mở test sau khi dev analysis đã hoàn tất và bật cờ tường minh:

```powershell
python -m research.data.preprocess_assistments_2017 --output data/processed/assistments2017-replay-01
.\.venv-research\Scripts\python.exe -m research.bkt.benchmark --processed data/processed/assistments2017-replay-01 --output data/experiments/assistments2017-replay-01
.\.venv-research\Scripts\python.exe -m research.bkt.benchmark --processed data/processed/assistments2017-v1
.\.venv-research\Scripts\python.exe -m research.bkt.benchmark --processed data/processed/assistments2017-v1 --evaluate-test
```

Đầu ra chứa bản ghi phải nằm trong `data/` của repository. Source logs bất biến. Với `--output` là file JSON, artifact được lưu trong thư mục sibling `<tên-file>_artifacts`. Không gọi benchmark nếu chưa có `preprocessing_report.json` hoàn chỉnh.

## Đầu ra và thứ tự đọc

| Vị trí local | Nội dung |
|---|---|
| `data/processed/assistments2017-v1/protocol.json` | Cấu hình đóng băng của run |
| `.../preprocessing_report.json` | Số dòng giữ/loại, support, nguồn và SHA-256 |
| `.../decisions.csv` | Lý do quyết định cho từng vị trí dòng nguồn |
| `.../train.csv`, `dev.csv`, `test.csv` | Observations theo thứ tự trong từng học sinh |
| `.../split_manifest.json` | ID hash–split, seed và tỷ lệ |
| `.../skill_manifest.json` | Raw skill–skill hash; chưa map skill Việt Nam |
| `.../staging.sqlite3` | Bản ghi cần thiết để truy vết, không dùng làm DB web |
| `data/experiments/rq1a_kt_benchmark_report.json` | Metric BKT pooled/per-skill, ba baseline, calibration và giới hạn; test result chỉ khi bật cờ |
| `data/experiments/rq1a_kt_benchmark_report.md` | Bảng Markdown so sánh và calibration expected/observed |
| `data/experiments/rq1a_kt_benchmark_report_artifacts/parameters.json` | Pooled/skill parameters, fit diagnostics và support |
| `.../dev_predictions.csv`, `.../test_predictions.csv` | Prediction trước câu trả lời; test chỉ khi bật cờ |

Những file trên đều local, không push lên Git. Báo cáo tổng hợp được chia sẻ trong docs; đọc [kết quả dev](bkt-dev-v1.md). Một hash học sinh vẫn có thể liên kết với nguồn; không gọi các CSV đã hash là dữ liệu hoàn toàn ẩn danh.

Đọc source theo thứ tự: [config](../../../research/config/assistments2017.v1.json) → [preprocess](../../../research/data/preprocess_assistments_2017.py) → [BKT model](../../../research/bkt/model.py) → [benchmark](../../../research/bkt/benchmark.py) → [metrics](../../../research/bkt/metrics.py) → [tests](../../../tests/test_research_pipeline.py).

## pyBKT và bước kế tiếp

Khi cài được pyBKT vào môi trường nghiên cứu, chạy:

```powershell
.\.venv-research\Scripts\python.exe -m pip install pyBKT
.\.venv-research\Scripts\python.exe -m research.bkt.check_pybkt
```

Lệnh đối chiếu chỉ dùng chuỗi synthetic và tham số cố định, không fit/test dữ liệu học sinh. Hiện chưa chạy do thư viện chưa có và network của lệnh pip trong Codex bị chặn. Không sửa trạng thái `NOT RUN` thành `PASS` trước khi có kết quả thực tế.

Tiếp theo: đối chiếu pyBKT khi cài được, phân tích skill chạm biên và sensitivity bằng run/version mới, hoàn thiện registry/KB tiếng Việt và KG/RAG. Giữ test đến khi khóa model/protocol của thực nghiệm cuối. Không dùng kết quả dev này làm bằng chứng đã hoàn thành toàn đồ án.
