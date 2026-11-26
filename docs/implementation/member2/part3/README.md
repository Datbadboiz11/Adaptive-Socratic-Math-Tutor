# Chặng 3 — KB và retrieval runtime

**Đã hoàn thiện triển khai local cho 13 concept ngày 26/11/2026; chờ nghiệm thu Docker/CI và review độc lập.** Nguồn runtime mặc định là lô M2-ORIG02 `0.4.0-member2-review`: 13 pack, 52 explanation/hint và 39 example publication, tổng 91 chunk. Ví dụ dùng version publication `0.4.1-member2-kb-examples`, giữ provenance của pack đã duyệt. Snapshot `KB-228707710ea975db30f14555327b414c73437725afe965f1f5ab8c233340cb0c` đã được kích hoạt trong PostgreSQL local; sync lặp thêm 0 chunk và tính lại 0 embedding.

Nghiệm thu mới chạy trong schema tạm hoàn toàn mới, có fingerprint chứng minh channel runtime đang phục vụ giữ nguyên. Bộ benchmark phủ đủ 13 concept có 104 query, 169 judgment và 13 fallback: semantic Recall/Hit@1 `0,8242`, nDCG@1 `0,8828`, Recall/Hit@3 `1,0000`, nDCG@3 `0,9634`; đây là dev labels tất định, chưa phải human gold/RQ3 cuối. Các chỉ số được chạy lại theo corpus lời giải chi tiết mới.

Nền tảng kỹ thuật ngày 18/11/2026 vẫn gồm migration, projector, atomic snapshot/withdrawal, embedding CPU có cache, direct/metadata/semantic retrieval và tool bind quyền từ state server. Các artifact không có hậu tố ngày là hồ sơ lịch sử của lượt A02/E02, không phải trạng thái runtime hiện hành.

Xem hồ sơ hiện hành [acceptance DB + embedding thật](acceptance-2026-11-26.json), [kết quả retrieval](retrieval-evaluation-2026-11-26.json), [210 trace có distance](retrieval-traces-2026-11-26.json) và [bàn giao tổng hợp](completion-2026-11-26.json). Hồ sơ lịch sử vẫn được giữ để đối chiếu. Không có API key trong các file này.

[Review kỹ thuật để Member 1/3 đối chiếu](technical-review-2026-11-26.md) ghi sáu thiếu sót, kết quả local, giới hạn benchmark và phần chờ xác nhận bên ngoài. Hồ sơ AI-review bị mất được tái dựng từ query rationale/qrels còn lại, có nhãn ngày tái dựng; không được coi là bản gốc đã tìm lại.

## Kết quả review nền tảng kỹ thuật

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

Lượt hiện hành đạt **375 passed, 0 skipped, 0 failed** với PostgreSQL/pgvector thật, cùng **13 checker/schema checks**. Frontend typecheck và production build đều đạt; kết quả được ghi trong [completion](completion-2026-11-26.json) và [JUnit](tests-2026-11-26.xml). Hồ sơ lịch sử ngày 18/11 ghi 303 test, gồm 48 test Chặng 3; không cộng gộp hai lượt nghiệm thu.

Local dùng Python 3.11, PostgreSQL 16.15 và pgvector 0.8.6. Docker/CI từ xa vẫn chưa chạy vì workspace không có `.git`/repository kết nối; không coi kết quả local là remote CI pass.

## Nội dung runtime hiện hành và nghiệm thu

Nguồn mặc định là [lô 13 pack đã duyệt](../../../../content/authoring/batches/member2-original.v2/manifest.json); CLI tự nạp [39 ExamplePublication](../../../../content/kb/member2-v2/example-publications.json) đã ghim hash. Các nguồn A02/E02 và curriculum draft vẫn có thể chọn tường minh nhưng tiếp tục tạo 0 chunk. [Runbook đồng bộ](../../../../content/kb/README.md#đồng-bộ)

**Snapshot `runtime` hiện hành chứa 40 concept/40 skill trong registry và 91 teaching chunk thuộc 13 concept Member 2.** Direct lookup tạo 0 embedding; lần đồng bộ đầu tạo 91 embedding, lần lặp dùng 91 cache hit và tính mới 0.

Nghiệm thu dương dùng chính 91 chunk đã duyệt với profile embedding thật, weights ONNX thật và PostgreSQL/pgvector thật. Chỉ phép thử withdrawal dùng namespace fixture; namespace đó nằm trong schema nghiệm thu cô lập và không được tool runtime chọn.

Nghiệm thu ghi nhận:

- Schema `stage3_check_*` được tạo mới, migrate riêng và dọn sau lượt chạy; checker không thể đạt nhờ snapshot runtime cũ.
- 91 chunk có provenance/hash và không chứa trường private reference; 39 example giữ family/source/lineage để loại ví dụ gần bài đang đo.
- 104 query chạy bằng metadata và semantic, tổng 210 retrieval trace kể cả direct/withdrawal; 13/13 fallback đúng ở mỗi mode.
- Rút pack A01 trong namespace fixture cô lập chặn cả snapshot cũ; snapshot kế tiếp còn 84 chunk, không ảnh hưởng runtime.

| Dev metric (91 query có target; 13 fallback N/A) | Metadata theo ID | Semantic cosine |
|---|---:|---:|
| Recall/Hit@1 | 0,4286 | 0,8242 |
| nDCG@1 | 0,6190 | 0,8828 |
| Recall/Hit@3 | 1,0000 | 1,0000 |
| nDCG@3 | 0,8783 | 0,9634 |
| Fallback đúng | 13/13 | 13/13 |

K=1/3/5 đều có raw output và tổng hợp theo từng concept. Nhãn mới được sinh tất định từ teaching intent/scope đã duyệt, không phải gán nhãn độc lập của con người; vì vậy chỉ dùng làm dev benchmark, chưa phải final RQ3 hay bằng chứng hiệu quả học tập. Khoảng cách cosine không phải xác suất đúng.

## Chạy lại

Từ thư mục gốc, dùng `.venv` hiện có. Model đã có trong workspace; lệnh chuẩn bị sẽ chỉ kiểm hash nếu đủ file:

```powershell
.\.venv\Scripts\python.exe scripts/dev/validation_runtime.py database
.\.venv\Scripts\python.exe scripts/kb/prepare_embedding_model.py
.\.venv\Scripts\python.exe scripts/kb/build_member2_stage3_assets.py --check
.\.venv\Scripts\python.exe scripts/kb/sync_kb.py --workspace-local sync --dry-run
.\.venv\Scripts\python.exe scripts/kb/sync_kb.py --workspace-local sync --activate
.\.venv\Scripts\python.exe scripts/kb/sync_kb.py --workspace-local status
.\.venv\Scripts\python.exe scripts/checks/check_stage3_kb.py --workspace-local --real-db
```

`database` dùng tooling PostgreSQL cục bộ và chạy migration có checksum. `check_stage3_kb.py --real-db` luôn dùng schema mới rồi dọn schema; nó không kích hoạt snapshot runtime thật. Hai lệnh `sync` phía trên mới là thao tác triển khai. Workspace/checkout mới cần PostgreSQL có pgvector hoặc Compose; không có các binary cục bộ trong Git. Xem [runbook nguồn/model](../../../../content/kb/README.md).

Lệnh audit không cần DB/model tải về:

```powershell
.\.venv\Scripts\python.exe scripts/exports/export_kb_contracts.py --check
.\.venv\Scripts\python.exe scripts/checks/check_stage3_kb.py
```

Để chạy lại full test DB bằng helper: `scripts/dev/validation_runtime.py tests`. Helper bỏ key thật khỏi environment và dùng stub/synthetic credentials trong tests. `tests.xml` không hậu tố ngày là hồ sơ lịch sử; kết quả hiện hành dùng tên có ngày để tránh ghi đè bằng chứng cũ.

Admin CLI có thêm `activate --snapshot`, `withdraw --concept --version --reason --actor`, `export --snapshot --output`. Đây là thao tác quản trị, không mở HTTP endpoint cho browser/LLM. Export dùng chế độ tạo file mới, kèm trạng thái active/withdrawal và nhãn archival; không phải quyền tự động công bố lại nội dung cũ.

## Tự review về tính hợp lý và tối ưu

1. **Phù hợp đề tài:** scope concept–skill, grade, difficulty, hint/disclosure và exclusions được áp trên DB trước xếp hạng. Truy xuất không ghi observation/mastery/assistance; các test xác nhận không phát sinh dữ liệu học tập.
2. **Chi phí:** dùng CPU/model đa ngôn ngữ hiện có; 0 lượt API model trong Chặng 3. Cache theo text hash + profile; direct/metadata và query không có ứng viên tránh inference. Với KB nhỏ, exact scan rõ ràng và đủ dùng; chưa thêm ANN/hybrid/reranker.
3. **Độ tin cậy:** snapshot nguyên tử, khóa/version/hash và withdrawal được kiểm bằng test DB thật, gồm lỗi giữa publish và các race. API fallback không hạ bộ lọc duyệt để lấy dữ liệu.
4. **Bảo toàn phép đo:** các ví dụ thiếu metadata độc lập bị loại; mapping legacy vẫn `proposed`; tool chưa tự đổi session/BKT hoặc coi truy xuất là học sinh nhận hỗ trợ.
5. **Điểm đã sửa sau review:** cache Hugging Face dùng link sang blob ngoài thư mục snapshot, nên loader chấp nhận link hợp lệ và kiểm hash file đã ghim; test runtime xác nhận weights thật chạy được. Docker mount bản export file thường để tránh link cache hỏng khi đổi môi trường; bản copy được kiểm lại hash. Bổ sung chặn nội dung khi lưu trace thất bại và kiểm integrity trước kích hoạt/trả kết quả. Loại key thật khỏi environment test và loại artifacts/DB/model cache khỏi Docker build context.

Chưa thêm service hoặc dependency cho lexical/reranker vì dev chưa chỉ ra nhu cầu đủ rõ. Chưa tối ưu chỉ số để thay việc tăng chất lượng/độ phủ dữ liệu. Dữ liệu đã rút duyệt vẫn giữ lịch sử phục vụ audit, nhưng bị loại khỏi retrieval; không có lệnh xóa dữ liệu/file trong quy trình này.

## Bàn giao Chặng 4

Cập nhật sau bàn giao ngày 26/11/2026: [bản tích hợp đầu tiên Chặng 4](../part4/README.md) đã nối retrieval vào gia sư, ghi receipt giao nội dung, thêm UI nguồn/ví dụ và report theo skill. Các giới hạn bên dưới ghi phạm vi tại thời điểm khép Chặng 3.

Đầu vào cho Member 3 là [tool](../../../../backend/app/kb_tool.py), [retriever](../../../../backend/app/retrieval.py), [contract runtime](../../../../backend/app/kb_contracts.py) và [schema](../../../../contracts/kb/v1/KBResult.schema.json). `BoundTeachingContentTool.invoke()` chỉ nhận query; `bind_runtime_tool()` nhận `TrustedKBState` do server tạo. Các schema scope/request là nội bộ.

Chặng 4 cần adapter canonical/legacy có version, snapshot gắn với session/turn, node retrieval + context thực sự đưa vào generator, guard output, commit assistance_received theo delivery, replay không truy xuất lại và UI hiển thị nguồn đã dùng. Model wording hiện chỉ chọn câu trong enum; không tự coi nó đã dùng RAG. Concept/validator/UI readiness vẫn phải được kiểm trước khi mở bài mới cho học sinh.

Phạm vi hồ sơ này dừng ở Chặng 3. Tiến độ Chặng 4 và các phần còn lại của Member 2 được theo dõi trong hồ sơ riêng ở trên.
