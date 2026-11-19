# Nguồn KB, model và quản trị snapshot

Code Chặng 3 xem [bàn giao và evidence](../../docs/implementation/member2/part3/README.md). Thư mục này chỉ chứa cấu hình model đã ghim; registry/bank có version vẫn là nguồn chuẩn. PostgreSQL/pgvector là bản phục vụ; source files không bị CLI sync sửa.

## Model và chi phí

[embedding-profile.v1.json](embedding-profile.v1.json) ghim model đa ngôn ngữ `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, ONNX 384 chiều, cosine, L2 normalization, không thêm prefix; FastEmbed 0.9.1/ONNX Runtime 1.32.0 và hash năm file. Weights lấy từ [bản ONNX Qdrant](https://huggingface.co/Qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q/tree/faf4aa4225822f3bc6376869cb1164e8e3feedd0). Profile fingerprint phân biệt model/revision/dimension/config; không dùng tên model đơn lẻ làm khóa cache.

Trên máy mới:

```powershell
python -m pip install -r backend/requirements-rag.txt
python scripts/kb/prepare_embedding_model.py
```

Script tải riêng các file public tại commit đã ghim, xác minh checksum và từ chối ghi đè file khác hash. Có thể dùng `--output-dir` để chọn thư mục mới. Đặt `KB_MODEL_DIR` trong environment nếu dùng đường dẫn riêng; `--workspace-local` cũng đọc giá trị từ `.env` hiện có.

Sau khi chuẩn bị, inference dùng file cục bộ và `local_files_only`; không cần OpenAI/Gemini key. Core backend vẫn chạy được khi chưa cài `requirements-rag.txt`: direct/metadata không cần model, semantic có ứng viên sẽ trả `retrieval_unavailable` nếu thiếu dependency/weights đúng profile. Không tự chuyển sang API trả phí hoặc hạ review filter.

## Đồng bộ

Mặc định `--source oatutor-v2` đọc registry snapshot và hai `draft.json` trong lô `M2-OAT02`. `--source curriculum` đọc registry/pilot canonical. Vì hai bản registry hiện cùng `0.1.0` nhưng khác hash, không trộn chúng trong cùng namespace/version; khi hợp nhất nguồn phải bump version và dùng bank tương ứng.

```powershell
python scripts/kb/sync_kb.py --workspace-local sync --dry-run
python scripts/kb/sync_kb.py --workspace-local sync --activate
python scripts/kb/sync_kb.py --workspace-local status
```

Không dùng `--workspace-local` trong container/Linux/CI: cấu hình `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD` hoặc `DATABASE_URL`. Chạy migration trước bằng `python -m app.manage migrate` từ environment có `backend` trong Python path. Script wrapper đã thêm path khi chạy từ workspace.

`--registry PATH --bank PATH` nhận cặp source đã thống nhất version. `--profile PATH` dùng profile khác; `--model-dir PATH` chọn weights tương ứng. CLI không tự gán human approval. Hiện source thật vẫn draft và sync tạo snapshot có 0 teaching chunk; các ca có nội dung trong evidence dùng namespace fixture riêng.

Muốn chỉ chuẩn bị snapshot, bỏ `--activate`. Kích hoạt riêng bằng `activate --snapshot ID_TU_STATUS`. Sync phát hiện đổi cùng registry/chunk version và dừng; nội dung mới cần version mới. Lỗi chuẩn bị/publish không chuyển con trỏ active. Dry-run chỉ đọc DB và tính diff, không ghi sync run hoặc tạo embedding.

## Ví dụ và rút duyệt

Explanation/hint yêu cầu concept, alignment và pack đủ duyệt; difficulty `null` có nghĩa nội dung chung, không phải độ khó được suy đoán. Teaching chunk giữ nguồn pack và nguồn alignment riêng.

`MathCase.examples` chưa có family/lineage và teaching text được duyệt độc lập nên không được tự xuất bản. `sync --examples PATH` nhận danh sách theo [ExamplePublication schema](../../contracts/kb/v1/ExamplePublication.schema.json), gồm case ID thuộc pack, pack hash, family/source/lineage, difficulty, teaching text và review provenance. Không lấy `reference_answer/reference_steps` của pack làm chunk. Runtime loại bài hiện tại, source group, family và lineage gần bài đang đo.

`withdraw --concept CONCEPT_ID --version CONTENT_VERSION --reason LY_DO --actor NGUOI_THUC_HIEN` rút một pack version trong namespace đang quản trị. Ledger có hiệu lực với snapshot cũ lẫn mới; đồng bộ lại sẽ loại pack đó khỏi snapshot mới. Không sửa văn bản hay xóa snapshot cũ để thực hiện rút duyệt. Phạm vi fixture được chọn bằng global option `--namespace fixture-TEN`; production tool chỉ bind `runtime`.

`export --snapshot ID_TU_STATUS --output artifacts/TEN_MOI.json` xuất registry, manifest và teaching projections, kèm active/withdrawal metadata. Export là bản archival để đối soát/bàn giao Neo4j; consumer vẫn phải kiểm quyền/duyệt trước khi phục vụ. File đích phải chưa tồn tại.

## Docker và CI

DB dùng `pgvector/pgvector:pg17`; migration tạo extension trong schema `public`. Muốn có CPU embedding trong image backend, đặt `INSTALL_RAG=true` trước khi build. Model được bind chỉ đọc tại `/models/kb`; dùng `KB_MODEL_HOST_DIR` nếu đường dẫn host khác `./artifacts/kb-model`. Chuẩn bị bản triển khai gồm các file thường trước khi dùng Docker:

```powershell
python scripts/kb/prepare_embedding_model.py --export-dir artifacts/kb-model
```

Cache Hugging Face có symlink sang blob ngoài thư mục snapshot; chỉ mount riêng thư mục snapshot có thể làm link hỏng. Export copy các file đã xác minh thành file thường và kiểm lại hash, không overwrite file khác hash. Bản triển khai local đã được tạo/kiểm tra. Artifacts/DB/model cache bị loại khỏi Docker build context, không COPY vào image.

Workflow chạy test vector với synthetic embeddings để ổn định, không cần key/model download. Lượt nghiệm thu cục bộ có weights thật nằm trong [acceptance](../../docs/implementation/member2/part3/acceptance.json). Docker/CI từ xa chưa được chạy trong máy hiện tại.

Theo [pgvector](https://github.com/pgvector/pgvector#filtering), exact search cung cấp mốc kiểm chứng trước khi thử ANN có filter. KB hiện nhỏ nên giữ exact cosine; chỉ cân nhắc HNSW/hybrid/reranker sau khi có bottleneck hoặc lỗi dev đủ rõ. Tham khảo [FastEmbed supported models](https://qdrant.github.io/fastembed/examples/Supported_Models/) khi tạo profile phiên bản mới.
