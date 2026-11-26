# Retrieval dev chạy trên pgvector thật

Runner này đo retrieval bằng corpus **8 explanation/hint nháp**, 24 query và 192 judgments sau AI review. Dữ liệu giữ nguyên version/hash và trạng thái draft; không xuất bản vào KB cho học sinh, không sửa production review gate và chưa nối vào Agent.

Hai cấu hình dùng cùng filter và cùng tập ứng viên:

- `metadata`: sắp theo content ID làm baseline đơn giản, không dùng text similarity.
- `semantic`: cosine distance trong PostgreSQL/pgvector, embedding CPU miễn phí bằng `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, 384 chiều, không thêm prefix.

Giữ cả Recall/Hit với relevance ≥2 và graded nDCG với gains 0/1/3. Sáu query không có relevance 2 có Recall/Hit là N/A; bốn query không có gain dương có nDCG là N/A. Macro average chỉ tính query được định nghĩa, báo cả mẫu số. Bốn query bị chặn metadata phải trả rỗng. Không hạ filter để tăng metric.

## Chạy lại trên máy Windows hiện tại

Môi trường `.venv` và PostgreSQL cục bộ đã được chuẩn bị. Từ gốc dự án:

```powershell
.\.venv\Scripts\python.exe research/retrieval/run_dev.py --workspace-local
```

Runner đọc thông tin DB từ `.env` qua helper nội bộ; không gọi model API. Mỗi lần chạy tạo `artifacts/retrieval-validation/<run-id>/benchmark.json` riêng, chứa raw rankings, khoảng cách, metric từng query, latency, hash weights/config/corpus/query/qrels và sync receipts.

Nếu DB đã dừng, khởi động lại bằng `scripts/dev/validation_runtime.py database`. Helper dùng bộ PostgreSQL trong `artifacts/tooling/pg16`, không phải bộ cài toàn hệ thống.

## Chuẩn bị trên môi trường mới

```powershell
python -m pip install -r research/requirements-retrieval.txt -r research/requirements.txt
python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2', cache_dir='artifacts/tooling/embedding-models', threads=2)"
```

Sau lần tải đầu, runner chọn đúng một snapshot weights có sẵn, ghi hash cả năm file và dùng `specific_model_path`. Nếu có nhiều snapshot thì dừng để chọn/cache đúng phiên bản. Cache embedding khóa theo text + fingerprint model/dimension/prefix/weights/runtime. Muốn tái lập **đúng số liệu đã lưu**, dùng commit weights và các hash trong [benchmark đã lưu](../../docs/implementation/member2/runtime-validation-2026-11-18/benchmark.json); tải bản mới không mặc nhiên tái lập bản cũ.

Trên Linux/CI hoặc PostgreSQL riêng: cấu hình `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`, cài extension pgvector trên server; chạy lệnh không có `--workspace-local`. User DB cần quyền tạo extension/schema cho môi trường nghiên cứu. Compose/CI đã đổi sang image `pgvector/pgvector:pg17`; chưa có lần CI từ xa của thay đổi hiện tại.

## Thiết kế và giới hạn

Store nằm trong schema riêng `member2_retrieval_dev`. Sync khóa transaction, kiểm checksum corpus/tài liệu, từ chối đổi nội dung cùng snapshot/model và commit nguyên lô. Sync lần hai không thêm hàng. Bảng chấp nhận riêng explanation/hint draft phi runtime. Truy vấn áp concept–skill, purpose, mức hint, grade, disclosure và exclusions trước khi xếp hạng; không nhận scope từ web/LLM.

Chỉ có 8 chunk nên quét exact cosine là đủ. Chưa cần HNSW, reranker, dịch vụ embedding hay phí API. Đây là phép thử plumbing và xếp hạng dev; bộ dữ liệu còn nhỏ, cùng nguồn authoring/AI review, không phải human gold, final test hay đo hiệu quả học tập. Metadata baseline đơn giản cũng không đại diện cho BM25 hoặc một baseline từ khóa mạnh. Độ trễ chỉ mô tả một lượt chạy cục bộ, chưa có tải đồng thời; tốc độ cache khác với inference đầu tiên.

Chặng 3 đã có migration/projector/sync runtime, snapshot activation/withdrawal và tool bind quyền server; xem [bàn giao mới](../../docs/implementation/member2/part3/README.md). Runner nghiên cứu trong thư mục này vẫn tách riêng để đối chiếu. Tích hợp context/delivery/replay vào Agent thuộc Chặng 4 và chưa triển khai.
