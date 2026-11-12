# RAG pilot — Qwen trên Kaggle và PostgreSQL/pgvector

Triển khai ngày **19/10/2026**, tiếp nối [kết quả embedding Qwen](../../research/retrieval/qwen3-4b-v1.md). Bám [plan tổng mục 8.5 và 14–15](../../planning/project-plan.md) cùng [PRD FR-09](../../product/prd.md). Đây là lớp truy xuất backend cho pilot, chưa là Agent/phiên học tích hợp hoàn chỉnh.

## Luồng và ranh giới

```text
API pilot có xác thực
  → Analyzer xác minh bài làm
  → KG lấy prerequisite ứng viên
  → mục tiêu kiến thức + câu hỏi chẩn đoán biên soạn
  → lọc concept / loại nội dung / mức hint / trạng thái review
  → lấy vector khớp chính xác từ catalog Qwen đã chạy Kaggle (hoặc HTTP service tùy chọn)
  → pgvector xếp hạng cosine trên nội dung đã lọc
  → trả content IDs, nguồn, version, collection và thời gian encode
```

Đầu vào cần làm rõ hoặc bài đã hoàn thành không gọi encoder. Nội dung chưa duyệt không bao giờ xuất qua chế độ `approved_only`; pilot có cờ và demo auth được xem nháp với nhãn rõ ràng. Kho truy xuất chỉ chứa explanations/hints, không chứa reference answers, worked solutions hoặc error fixtures. Raw bước giải không được đưa vào câu hỏi embedding của luồng grounding.

Không tự phê duyệt nội dung, cập nhật BKT, tạo câu trả lời LLM, hoặc thêm chủ đề lên web. KG chỉ cung cấp ứng viên, không chứng minh học sinh yếu prerequisite. BKT, tham số nghiên cứu, dữ liệu train/dev/test và checkpoint phiên MVP giữ nguyên.

## Các file chính

| File | Vai trò |
|---|---|
| [qwen_query.py](../../../backend/app/qwen_query.py) | Encoder metadata/prefix/revision chuẩn, HTTP client có token, timeout, không redirect, kiểm tra vector/model/query hash |
| [qwen_service.py](../../../backend/app/qwen_service.py) | Một tiến trình model riêng, nạp cache tại startup, CPU FP16 hoặc CUDA đủ VRAM, last-token pooling và L2 |
| [rag_store.py](../../../backend/app/rag_store.py) | Kiểm tra artifact, migration riêng, đồng bộ immutable và truy vấn pgvector |
| [001_qwen_pgvector.sql](../../../backend/rag_migrations/001_qwen_pgvector.sql) | Bảng registry snapshot, collection, chunks và vector 2560 chiều |
| [pilot_retrieval.py](../../../backend/app/pilot_retrieval.py) | Chọn Qwen/pgvector, fallback BM25 minh bạch; BGE JSON vẫn dùng làm baseline |
| [qwen_catalog.py](../../../backend/app/qwen_catalog.py) | Catalog truy vấn Kaggle, kiểm tra encoder/snapshot/corpus/policy, lookup đúng query hash |
| [qwen3_runtime_queries_kaggle.ipynb](../../../research/retrieval/qwen3_4b/qwen3_runtime_queries_kaggle.ipynb) | Notebook mới cho 30 truy vấn runtime, không sửa notebook thí nghiệm đã chạy |
| [compose.rag.yaml](../../../compose.rag.yaml) | Overlay pilot opt-in; không thay Compose cơ sở hoặc xóa volume PG17 |
| [check_qwen_pgvector.py](../../../scripts/checks/check_qwen_pgvector.py) | Replay query vectors đã lưu qua pgvector để phát hiện sai khác ranking; không giả làm inference mới |

Migrations RAG có bảng checksum riêng, không gắn vào migration MVP. Chỉ chạy khi bật đợt RAG. `rag_registry_snapshots` giữ toàn bộ registry có version; graph runtime vẫn đi qua Neo4j/registry adapter hiện có. `rag_collections` gắn model/revision/prefix, corpus hash, graph snapshot và manifest hash. Reimport đúng artifact không thêm dòng; artifact/payload/vector khác bị từ chối, không tự repair/overwrite.

Sử dụng `vector(2560)` và exact search cho 40 chunks. pgvector hỗ trợ lưu vector tới 16000 chiều, nhưng HNSW/IVFFlat với kiểu vector giới hạn 2000 chiều; không tạo HNSW vector 2560 sai cấu hình. Mở rộng ANN/halfvec là thí nghiệm riêng sau này, không tự giảm chiều/quantize model để tăng tốc. [Tài liệu pgvector](https://github.com/pgvector/pgvector).

## Phương án đã chọn: Kaggle tạo vector truy vấn theo đợt

Người dùng chọn Kaggle ngày 19/10/2026. Backend mặc định `QWEN_QUERY_PROVIDER=catalog`; không cần tải trọng số về máy cá nhân hoặc chạy model liên tục. Bộ pilot hiện có **30 query duy nhất**: 10 mục tiêu concept và 20 mục tiêu kèm câu hỏi chẩn đoán đã biên soạn. Đây là vector **truy vấn**, khác 40 vector **nội dung** đã có. Không embed lại corpus hay dữ liệu tương tác học sinh.

`grounding_queries.py` dùng chung phép tạo query cho Analyzer→KG→retrieval và trình xuất catalog. Khi Analyzer không khớp mẫu lỗi, query chỉ gồm mục tiêu concept. Khi bài đã hoàn thành/cần làm rõ, grounding không gọi retrieval. Catalog bao phủ các query có thể phát sinh theo policy hiện tại, **không bao phủ mọi câu hỏi tự do** ở endpoint `/retrieve` và không chứng minh chất lượng hỗ trợ cuối cùng.

Chạy Kaggle:

1. Import [notebook runtime mới](../../../research/retrieval/qwen3_4b/qwen3_runtime_queries_kaggle.ipynb), chọn **T4 ×2**, bật Internet, session mới.
2. Upload riêng **`data/exports/pilot-query-vectors-qwen3-4b-input.zip`** qua Add Input. Notebook hỗ trợ cả ZIP và thư mục Kaggle tự giải nén; kiểm tra allowlist/hash được pin trước khi nạp code đóng gói.
3. Save Version → Save & Run All. Tải **`pilot-query-vectors-qwen3-4b.zip`**, đặt vào `data/exports/`.
4. Import bằng lệnh dưới. Lượt Kaggle ngày **19/10/2026 đã chạy thành công** và catalog thực đã được nhập; xem kết quả kiểm tra bên dưới.

```powershell
.\.venv\Scripts\python.exe research/retrieval/qwen3_4b/runtime_catalog.py import --input data/exports/pilot-query-vectors-qwen3-4b.zip
```

Importer chỉ đọc hai JSON theo allowlist, kiểm tra model/revision/dimensions, checksum, danh mục đầy đủ, input manifest, snapshot registry và corpus hiện tại; lưu `data/retrieval/qwen3-4b-runtime/catalog.json`. Đã có catalog khác thì từ chối ghi đè. Sau khi nội dung/policy thay đổi, xuất lại cặp notebook/input bằng `scripts/exports/prepare_qwen_runtime_kaggle.py`, chạy Kaggle lại và chọn đường dẫn catalog phiên bản mới nếu cần.

Lookup chỉ dùng **query hash khớp chính xác** cùng encoder. Không lấy vector query gần giống để giả encode câu mới. Query ngoài danh mục trả `actual_method=lexical`, `fallback_reason=qwen_query_not_in_catalog`; thiếu catalog trả `qwen_catalog_missing`. Khi thành công: `query_encoding_source=kaggle_catalog`; thời gian lookup không phải latency inference GPU. Không dùng 90 query vectors của bộ dev cũ thay cho các query runtime mới, không tạo relevance labels/điểm đánh giá mới từ catalog này.

Kaggle dùng model FP16 cùng loader đã kiểm chứng ở thí nghiệm, `device_map=balanced` trên T4 ×2, batch 2. Phần encode 30 câu nhỏ; tải và nạp trọng số thường chiếm phần lớn thời gian, tùy session/mạng. Không mở tunnel hoặc coi notebook là dịch vụ web thường trực. Khi muốn semantic cho mọi query tự do, cần cập nhật batch hoặc chuyển sang HTTP model service có tài nguyên phù hợp.

## Kết quả catalog Kaggle đã nhập — 19/10/2026

- ZIP output đã chuyển về `data/exports/pilot-query-vectors-qwen3-4b.zip` (686.263 byte); giải nén theo allowlist thành `catalog.json` và `run-manifest.json` trong `data/retrieval/qwen3-4b-runtime/`. `verification.json` cùng thư mục ghi kiểm tra chi tiết.
- Đủ 30 query hash, mỗi vector 2560 chiều, giá trị hữu hạn, L2 norm 1; 30 vector khác nhau. Model/revision/input manifest, policy, registry và corpus khớp hiện tại. Catalog đã vượt kiểm tra `QueryCatalog.ready()`.
- Notebook tại `research/retrieval/qwen3_4b/qwen3_runtime_queries_kaggle.ipynb` là bản đã chạy, giữ nguyên outputs; bốn code cell có execution counts 1–4, không có error output. Không tái tạo notebook này để tránh mất log chạy thực.
- Theo log Kaggle: FP16 trên hai Tesla T4, model load **52,299 giây**, encode 30 query **3,025 giây**, peak PyTorch memory GPU 0/1 **3840,9 / 3869,6 MiB**. Đây không phải latency API đầu cuối.
- Có cảnh báo pip về Gradio/Diffusers cần huggingface-hub mới hơn; notebook không dùng hai thư viện này và đã xuất artifact hợp lệ. Không coi cảnh báo đó là lỗi embedding hoặc thay đổi dependencies của lượt đã chạy.
- Đã thử offline 30 query × 3 mức hint với 40 corpus vectors thật: tiền lọc KG/concept/hint/review, cosine ranking hữu hạn, draft không xuất qua `approved_only`, query lạ bị từ chối catalog. Không có relevance labels mới nên không công bố Recall/AUC cho lượt này.
- Kiểm thử liên quan: **73 passed, 9 skipped** (7 pgvector DB, 2 ASGI). Readiness PostgreSQL vẫn báo `pgvector_unavailable`; chưa xác nhận SQL ranking hoặc toàn luồng API/DB. Kết quả và index BGE/Qwen thí nghiệm cũ giữ nguyên.

## HTTP service tùy chọn cho câu hỏi mới

Chỉ chọn `QWEN_QUERY_PROVIDER=http` khi có model service. File index/ZIP chỉ chứa vector, không chứa trọng số Qwen. Để encode câu hỏi mới online vẫn cần model khoảng 8 GB và runtime có đủ bộ nhớ. Máy hiện tại có GTX 1650 4 GB, chưa đủ cho Qwen FP16 như lần chạy T4 ×2.

Dịch vụ model tách khỏi FastAPI gia sư, một worker, một lượt inference tại một thời điểm. Chưa có trọng số trong cache thì readiness 503; **không tải model trong API request**. CPU FP16 là lựa chọn thử chậm, cần đủ RAM cho trọng số và phần phụ; latency CPU chưa được đo trong đợt này. Có GPU riêng thì chạy cùng service với `QWEN_SERVICE_DEVICE=cuda` và PyTorch CUDA, hoặc trỏ backend tới endpoint HTTPS có token. Chưa fine-tune, không đổi model/revision/prefix so với artifact.

## Chạy với Docker Desktop

Cần Docker Engine running và terminal có quyền truy cập Engine. Import catalog trước khi kiểm tra semantic runtime. Từ gốc dự án:

```powershell
docker compose -f compose.yaml -f compose.rag.yaml up -d db
docker compose -f compose.yaml -f compose.rag.yaml --profile rag up --build rag-init
docker compose -f compose.yaml -f compose.rag.yaml up -d --build backend frontend
```

Overlay dùng `pgvector/pgvector:0.8.7-pg17-bookworm`, cùng PostgreSQL major 17 và volume hiện có; không dùng `down -v`. Đổi image có thể cần khởi động lại DB. `rag-init` đọc artifact `data/retrieval/qwen3-4b-v1/`, kiểm tra model/corpus/hashes trước khi mở transaction, nhập 40 vectors và registry snapshot. Không ghi vào tables học sinh/MVP hoặc sửa file artifact.

Catalog không cần token hoặc tải trọng số trên máy cá nhân. Để dùng **CPU/HTTP profile tùy chọn**, trước tiên chuẩn bị token/cache (lệnh này tải khoảng 8 GB, chỉ chạy khi đã chọn phương án CPU và đủ tài nguyên):

```powershell
New-Item -ItemType Directory -Path 'data/models/qwen3-4b' -Force
$env:QWEN_QUERY_PROVIDER = 'http'
$env:QWEN_SERVICE_TOKEN = (& .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))")
docker compose -f compose.yaml -f compose.rag.yaml --profile qwen-tools run qwen-cache
docker compose -f compose.yaml -f compose.rag.yaml --profile qwen-cpu up -d qwen-embedding
```

`qwen-cache` chỉ tải tokenizer/safetensors của revision đã pin; service runtime mount cache read-only. Model service CPU bind localhost:8011, backend gọi qua hostname nội bộ `qwen-embedding:8011`. `QWEN_SERVICE_URL` dành cho backend chạy native; `QWEN_CONTAINER_SERVICE_URL` dành cho backend trong Docker (mặc định hostname nội bộ). Khi dùng GPU server riêng, cấu hình URL tương ứng ở phía server và giữ token ngoài Git. Recreate backend với cùng biến provider/token khi chuyển sang HTTP. Phương án Kaggle catalog không cần chạy các lệnh CPU này.

## API và cách kiểm tra

Đăng nhập demo lấy Bearer token như MVP. Overlay bật `PILOT_ANALYZER_ENABLED` và `PILOT_GROUNDING_ENABLED`; Compose cơ sở và `.env` cá nhân không bị tự sửa. Các endpoint:

- `GET /api/v1/pilot/retrieval/status`: model/schema, collection, query provider, catalog ready/query count hoặc lý do chưa sẵn sàng. `query_service_configured=true` chỉ nói URL/token HTTP hợp lệ, không khẳng định model service ready; trường này không cần true khi dùng catalog.
- `POST /api/v1/pilot/retrieve`: query mới, concept IDs, purpose, hint level, top K và method. Trả vector store/collection/encoder/revision và thời gian encode khi semantic thành công.
- `POST /api/v1/pilot/problems/P-A02-01/ground`: `{"submission_kind":"steps","steps":["3x+2"],"method":"semantic","hint_level":1}`. Analyzer → KG → retrieval, không sinh reply hoặc cập nhật Student Model.

Payload retrieval ví dụ: `{"query":"Vì sao cần nhân hệ số với mọi phần trong ngoặc?","concept_ids":["A02"],"purpose":"hint","hint_level":1,"top_k":3,"method":"semantic"}`. Đây là query tự do nên catalog có thể fallback; dùng endpoint `/ground` để kiểm tra query theo policy hiện tại. Không truyền query vectors từ trình duyệt; vector đến từ catalog đã import hoặc model service có token.

Nếu thành công: `actual_method=semantic`, `embedding_model=Qwen/Qwen3-Embedding-4B`, `embedding_dimensions=2560`, `vector_store=pgvector`, có collection ID. Nếu collection/model không sẵn sàng: `actual_method=lexical`, `vector_store=lexical_fallback`, có `fallback_reason`, không gắn nhãn Qwen semantic giả.

`query_encoding_ms` đo lookup/đọc/kiểm tra catalog hoặc HTTP client tùy `query_encoding_source`, không phải thời gian GPU thuần. Cosine chỉ xếp hạng nội dung ứng viên; chưa chốt ngưỡng từ chối câu hỏi ngoài miền trên dữ liệu độc lập. Không diễn giải score thành xác suất đúng hoặc bằng chứng học sinh yếu kỹ năng.

Đánh giá lại DB mà không cần model (cần PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD đúng DB):

```powershell
$env:PYTHONPATH = (Resolve-Path backend).Path
.\.venv\Scripts\python.exe scripts/checks/check_qwen_pgvector.py --output data/retrieval/qwen3-pgvector-replay.json
```

Lệnh trên dùng 90 query vectors đã có, so top K với run Kaggle, ghi rõ đây là replay. Để chứng minh inference mới cần gọi service bằng câu chưa có trong bộ 90 query và kiểm tra kết quả API/log/tài nguyên; chưa được dùng vector cũ để giả chứng minh phần này.

## Kiểm chứng và giới hạn tại đợt triển khai

Xem [báo cáo kiểm tra](rag-runtime-checks.v1.json). Tests có ca vector 1024/2560 sai model, stale hash, service timeout/sai query, review/hint filter, không đưa raw bài làm vào query, fallback có nhãn và guard token/concurrency. Có kiểm thử DB thật riêng trong CI (image pgvector PG17) và kiểm thử HTTP; nếu local không có Docker/ASGI loopback thì báo skip thay vì coi đã pass.

Đợt này chưa tích hợp generator/Agent/phiên học web mở rộng, không chốt test nghiên cứu. Việc kế tiếp sau khi runtime hoạt động: kiểm tra trên câu hỏi mới, review content/relevance, nối nội dung thực sự vào Agent/Student Model và lưu decision log nhiều lượt theo plan tuần 3–4. Không mở rộng concept hoặc đổi nội dung chỉ để tăng điểm retrieval.
