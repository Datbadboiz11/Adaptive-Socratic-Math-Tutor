# Chặng 3 — KB và retrieval runtime

**Đã hoàn thiện kỹ thuật ngày 18/11/2026, dừng tại mốc review này.** Có migration, projector, sync và snapshot activation/withdrawal, embedding CPU có cache, direct lookup, metadata/semantic retrieval và tool được bind quyền từ state server. Chặng 4 nối nội dung vào Agent/response/delivery/UI chưa thực hiện.

Xem [verification.json](verification.json), [303 test](tests.xml), [nghiệm thu DB + embedding thật](acceptance.json), [trace có khoảng cách xếp hạng](retrieval-traces.json) và [12 checker](checks.json). Không có API key trong các file này.

## Kết quả review

| Yêu cầu Chặng 3 | Kết quả |
|---|---|
| Registry/concept/skill/mapping có version | Migration `003_curriculum_kb.sql` tạo bảng phục vụ KB; lưu cả nguồn registry, concept, skill và mapping legacy ở trạng thái `proposed` |
| Chunk/version/hash | Khóa content ID + version; checksum toàn payload và text riêng. Đổi text, review hoặc provenance cùng version bị từ chối |
| Sync dry-run và chạy lặp | Dry-run không ghi DB/khởi tạo model; sync lần hai thêm 0 chunk và tính lại 0 embedding |
| Tạo embedding ngoài transaction | Hash weights/tokenizer và runtime được ghim; batch tối đa 32 trong model; model loading/inference diễn ra khi không có kết nối DB mở |
| Snapshot đầy đủ và kích hoạt nguyên tử | Membership liên kết đúng chunk/text/model; kiểm count, manifest, registry, payload và vector hash. Publish + chuyển con trỏ trong cùng transaction; lỗi giữ snapshot trước |
| Đồng thời | Khóa theo namespace và kiểm snapshot hiện hành trước khi chuyển con trỏ. Không để lượt chuẩn bị cũ ghi đè publisher mới; sync cùng snapshot vẫn idempotent |
| Rút duyệt | Ledger theo concept/pack version. Chặn cả snapshot lịch sử; sync kế tiếp loại nội dung đã rút. Kiểm tra lại nếu bị rút trong lúc tính embedding |
| Không trộn model/dimension | Profile fingerprint chứa model/revision/weights/runtime/dimension/config. FK ràng buộc profile + dimension + text hash; query model khác snapshot trả fallback |
| Chunk an toàn | Chỉ project explanation/hint đã duyệt concept + alignment + pack. Ví dụ cần bản duyệt teaching text và family/source/lineage riêng; không lấy thẳng solution của `MathCase` |
| Retrieval | Direct ID/version không gọi embedding; metadata không cần model; semantic exact cosine trên pgvector. Áp bộ lọc trước top-K; lỗi trả rỗng có reason |
| Quyền và trace | Tool chỉ nhận `RetrievalQuery`; scope/snapshot/grade/hint/exclusion được server bind. Trace lưu ref/version/hash và distance; không ghi raw query, đáp án riêng hoặc learner state |
| CI và đóng gói | CI thêm KB schema/audit, DB service dùng pgvector. Docker có dependency RAG tùy chọn và model mount chỉ đọc; cache/DB trong `artifacts` bị loại khỏi build context |

**303 passed, 0 skipped, 0 failed**, gồm **48 test Chặng 3** (14 unit +34 PostgreSQL/pgvector). 12 checker/schema checks đạt. Checksum xác nhận 59 tệp canonical/nguồn/lô v1 giữ nguyên; AI-review manifest của Chặng 1–2 vẫn đạt kiểm tra integrity.

Local dùng Python 3.11.6, PostgreSQL 16.15 và pgvector 0.8.6. YAML Compose/workflow đã parse và kiểm cấu hình; Docker và CI từ xa chưa chạy vì máy không có Docker và thư mục không có `.git`/repository kết nối. Không coi kết quả local là remote CI pass.

## Nội dung thật và fixture nghiệm thu

Nguồn mặc định là lô `content/authoring/batches/a02-e02-oatutor.v2`: registry snapshot 40 concept/40 skill, hai pack A02/E02. Nguồn `curriculum` cũng được hỗ trợ nhưng là baseline khác; hai registry có cùng version mà hash khác không được nhập lẫn trong cùng namespace. Khi hợp nhất/duyệt nguồn mới phải tạo version thống nhất mới.

**Snapshot `runtime` hiện chứa 40 concept, 40 skill và 0 teaching chunk.** Concept, alignment và pack thật vẫn chưa có human review. Đây là hành vi chặn đúng; không chuyển AI review thành `human_approved` và không mở nội dung nháp cho học sinh.

Ca retrieval dương dùng bản sao teaching text A02/E02 với **review provenance synthetic** trong namespace `fixture-stage3-b68c108859c5`. Các nhãn synthetic chỉ nằm trong dữ liệu kiểm thử/bảng fixture; không ghi vào nguồn. Profile embedding thực, weights ONNX thực và PostgreSQL thực. Namespace fixture không được tool runtime chọn.

Nghiệm thu ghi nhận:

- 8 teaching chunk, sync lặp không nhân bản; direct lookup tạo **0 embedding**.
- Tổng 28 text được embed trong lượt cold của provider: 8 chunk +20 query có ứng viên. Bốn query bị chặn không chạy query embedding.
- 24 query ×8 judgments dùng nhãn **AI-reviewed dev**, giữ hai grade sửa ở lượt review trước. Có mapping ID và kiểm text khớp corpus gốc trong acceptance.
- 50 retrieval trace riêng: 48 lượt metadata/semantic, 1 direct lookup và 1 kiểm tra sau rút duyệt. Đây là trace truy xuất, chưa phải trace đưa context vào generator hay giao nội dung cho học sinh.
- Rút pack A02 của **fixture** chặn truy xuất qua snapshot cũ; snapshot fixture kế tiếp còn 4 chunk E02, không tính lại embedding. Namespace runtime không bị rút nội dung trong phép thử này.

| Dev metric | Metadata theo ID | Semantic cosine |
|---|---:|---:|
| Recall/Hit@1, 18 query được định nghĩa | 0,6111 | 0,8333 |
| nDCG@1, 20 query được định nghĩa | 0,7167 | 0,9000 |
| Recall/Hit@3, 18 query được định nghĩa | 1,0000 | 1,0000 |
| nDCG@3, 20 query được định nghĩa | 0,8980 | 0,9720 |
| Fallback đúng theo metadata | 4/4 | 4/4 |

N/A được giữ riêng: sáu query không có relevance ≥2 cho Recall/Hit; bốn query không có gain dương cho graded nDCG. K=1/3/5 đều có raw output. Corpus nhỏ, nhiều query chỉ có 1–3 ứng viên, nhãn AI và baseline ID đơn giản nên kết quả chỉ phục vụ phát triển; chưa phải human gold, final RQ3 hay bằng chứng hiệu quả học tập. Khoảng cách cosine không phải xác suất đúng.

## Chạy lại

Từ thư mục gốc, dùng `.venv` hiện có. Model đã có trong workspace; lệnh chuẩn bị sẽ chỉ kiểm hash nếu đủ file:

```powershell
.\.venv\Scripts\python.exe scripts/dev/validation_runtime.py database
.\.venv\Scripts\python.exe scripts/kb/prepare_embedding_model.py
.\.venv\Scripts\python.exe scripts/kb/sync_kb.py --workspace-local sync --dry-run
.\.venv\Scripts\python.exe scripts/kb/sync_kb.py --workspace-local sync --activate
.\.venv\Scripts\python.exe scripts/kb/sync_kb.py --workspace-local status
.\.venv\Scripts\python.exe scripts/checks/check_stage3_kb.py --workspace-local --real-db
```

`database` dùng tooling PostgreSQL cục bộ và chạy migration có checksum. Workspace/checkout mới cần PostgreSQL có pgvector hoặc Compose; không có các binary cục bộ trong Git. Xem [runbook nguồn/model](../../../../content/kb/README.md).

Lệnh audit không cần DB/model tải về:

```powershell
.\.venv\Scripts\python.exe scripts/exports/export_kb_contracts.py --check
.\.venv\Scripts\python.exe scripts/checks/check_stage3_kb.py
```

Để chạy lại full test DB bằng helper: `scripts/dev/validation_runtime.py tests`. Helper bỏ key thật khỏi environment và dùng stub/synthetic credentials trong tests. File `tests.xml` tại đây là kết quả 303 test của lần nghiệm thu, không bị ghi đè bởi lần chạy sau.

Admin CLI có thêm `activate --snapshot`, `withdraw --concept --version --reason --actor`, `export --snapshot --output`. Đây là thao tác quản trị, không mở HTTP endpoint cho browser/LLM. Export dùng chế độ tạo file mới, kèm trạng thái active/withdrawal và nhãn archival; không phải quyền tự động công bố lại nội dung cũ.

## Tự review về tính hợp lý và tối ưu

1. **Phù hợp đề tài:** scope concept–skill, grade, difficulty, hint/disclosure và exclusions được áp trên DB trước xếp hạng. Truy xuất không ghi observation/mastery/assistance; các test xác nhận không phát sinh dữ liệu học tập.
2. **Chi phí:** dùng CPU/model đa ngôn ngữ hiện có; 0 lượt API model trong Chặng 3. Cache theo text hash + profile; direct/metadata và query không có ứng viên tránh inference. Với KB nhỏ, exact scan rõ ràng và đủ dùng; chưa thêm ANN/hybrid/reranker.
3. **Độ tin cậy:** snapshot nguyên tử, khóa/version/hash và withdrawal được kiểm bằng test DB thật, gồm lỗi giữa publish và các race. API fallback không hạ bộ lọc duyệt để lấy dữ liệu.
4. **Bảo toàn phép đo:** các ví dụ thiếu metadata độc lập bị loại; mapping legacy vẫn `proposed`; tool chưa tự đổi session/BKT hoặc coi truy xuất là học sinh nhận hỗ trợ.
5. **Điểm đã sửa sau review:** cache Hugging Face dùng link sang blob ngoài thư mục snapshot, nên loader chấp nhận link hợp lệ và kiểm hash file đã ghim; test runtime xác nhận weights thật chạy được. Docker mount bản export file thường để tránh link cache hỏng khi đổi môi trường; bản copy được kiểm lại hash. Bổ sung chặn nội dung khi lưu trace thất bại và kiểm integrity trước kích hoạt/trả kết quả. Loại key thật khỏi environment test và loại artifacts/DB/model cache khỏi Docker build context.

Chưa thêm service hoặc dependency cho lexical/reranker vì dev chưa chỉ ra nhu cầu đủ rõ. Chưa tối ưu chỉ số để thay việc tăng chất lượng/độ phủ dữ liệu. Dữ liệu đã rút duyệt vẫn giữ lịch sử phục vụ audit, nhưng bị loại khỏi retrieval; không có lệnh xóa dữ liệu/file trong quy trình này.

## Bàn giao Chặng 4 — chưa triển khai

Đầu vào cho Member 3 là [tool](../../../../backend/app/kb_tool.py), [retriever](../../../../backend/app/retrieval.py), [contract runtime](../../../../backend/app/kb_contracts.py) và [schema](../../../../contracts/kb/v1/KBResult.schema.json). `BoundTeachingContentTool.invoke()` chỉ nhận query; `bind_runtime_tool()` nhận `TrustedKBState` do server tạo. Các schema scope/request là nội bộ.

Chặng 4 cần adapter canonical/legacy có version, snapshot gắn với session/turn, node retrieval + context thực sự đưa vào generator, guard output, commit assistance_received theo delivery, replay không truy xuất lại và UI hiển thị nguồn đã dùng. Model wording hiện chỉ chọn câu trong enum; không tự coi nó đã dùng RAG. Concept/validator/UI readiness vẫn phải được kiểm trước khi mở bài mới cho học sinh.

**Dừng tại đây theo yêu cầu: không bắt đầu Chặng 4, không mở rộng 240 bài và không đánh dấu toàn bộ Member 2 hoàn tất.**
