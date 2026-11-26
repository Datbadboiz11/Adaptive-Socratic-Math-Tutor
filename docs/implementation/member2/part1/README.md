# Member 2 — Phần 1: hợp đồng và ma trận độ phủ

Triển khai ngày 16/11/2026. Ghi nhận xác nhận ban đầu ngày 23/11/2026 và xác nhận cập nhật ngày 24/11/2026 theo [Chặng 1 của kế hoạch Member 2](../../../planning/member-2-plan.md).

**Trạng thái Chặng 1.** Theo xác nhận của người dùng, Member 1, Member 2 và Member 3 đã thông qua danh mục 40 concept và các quyết định C01–C05. Ma trận hiện hành ghi nhận phân công theo workboard 13/13/14 và đánh dấu đủ 5 cổng hợp đồng là `accepted`. [Hồ sơ xác nhận có chữ ký](../../../../content/curriculum/member2-workboard-confirmation.v1.json)

## Cập nhật ngày 24/11/2026

**Nhóm đã xác nhận bản cập nhật Chặng 1.** Codex ký ghi nhận theo ủy quyền của người dùng cho Member 1, Member 2 và Member 3. Hồ sơ gắn SHA-256 chuẩn hóa LF với đúng tài liệu, mã và dữ liệu trong phạm vi đã xem. Ngày ghi hồ sơ áp dụng cho xác nhận chung của nhóm. [Hồ sơ M2-STAGE1-TEAM-20261124](../../../../content/curriculum/member2-stage1-update-confirmation.v1.json)

**Luồng demo đã mở 13 concept Member 2 từ lô M2-ORIG02.** Ma trận ghi khả năng demo riêng với điều kiện mở luồng của pilot canonical. Kết quả nghiệm thu áp dụng cho API tích hợp hiện hành. [Nghiệm thu demo](../part4/README.md)

- [Contract bài công khai 0.3.0](../../../../backend/app/member2_problem_contract.py) và [fixtures](../../../../contracts/member2/v0.3.0/examples.json) biểu diễn đủ 15 dạng bài authoring, gồm đặt nhân tử chung A07 và trục đối xứng F05. Projector chỉ lấy dữ liệu công khai. Adapter đọc bài phiên cũ chuyển `equation` thành `task` và giữ ID, version và skill đã ghi. Hồ sơ C01–C05 ngày 23/11 gắn với bản 0.2.0.
- `/api/v1/topics` trả `validator_task_kinds` theo tập bài hiện hành. Chủ đề M2-ORIG02 có bộ chấm khả dụng và đủ sáu bài khớp nguồn đã duyệt sẽ trả `tutoring_ready=true` trong demo. `TOPIC-LINEAR-01` có bộ chấm bước giải bậc nhất trong phạm vi repo đã kiểm thử. [OpenAPI](../../../../contracts/phase3/openapi.json)
- [Ma trận](coverage.md#độ-phủ-theo-nguồn-pack) ghi **20/40 concept có pack** và **15/40 có pack đã duyệt** tính theo concept duy nhất. JSON ghi nguồn, version, task, hồ sơ review và 13 concept được hỗ trợ trong luồng demo.
- Nhóm đã xác nhận **68 cạnh đồ thị** và **một ánh xạ legacy–canonical** trong registry v2. Registry lưu cạnh ở `draft` và ánh xạ ở `proposed`. Việc đưa chúng vào luồng học cần phiên bản tích hợp có bằng chứng validator và UI/policy. Hint mức 4 vẫn cần đặc tả của Member 3 và thay đổi contract/DB do Member 1 phụ trách theo C03.

## 1. Đầu ra

1. [Ma trận độ phủ](coverage.md) ghi owner/reviewer, nội dung hiện có, skill, dạng authoring và trạng thái readiness cho 40 concept.
2. [Workboard v1](../../../../content/curriculum/member2-workboard.v1.json) lưu phân công và các cổng trước khi xác nhận. [Hồ sơ xác nhận](../../../../content/curriculum/member2-workboard-confirmation.v1.json) gắn chữ ký với SHA-256 của workboard, registry và contract đã được thông qua.
3. [Hợp đồng Python](../../../../backend/app/member2_contracts.py): kiểu dữ liệu và quy tắc nhất quán cho public problem, readiness, retrieval, tutor presentation và report.
4. [Fixtures 0.2.0](../../../../contracts/member2/v0.2.0/examples.json) và [JSON Schema 0.2.0](../../../../contracts/member2/v0.2.0/FoundationExamples.schema.json): ví dụ hiện hành để Member 1/3 thảo luận và viết tích hợp.
5. [Tests](../../../../tests/test_member2_foundation.py): kiểm tra ranh giới dữ liệu, disclosure, snapshot, readiness và độ khớp artifact.
6. [coverage.json](coverage.json): bản đầy đủ có nguồn, scope, trạng thái review, blockers và SHA-256 đầu vào.
7. [Đặc tả nháp](task-specifications.md) ghi dạng đề và điều kiện chấm dự kiến cho 30 concept chưa có pack.

Hồ sơ ban đầu gắn với `member2-proposal-0.2.0`. Hồ sơ cập nhật gắn với bản 0.3.0 mở rộng hợp đồng bài công khai và các đầu ra được liệt kê ở trên. API phiên hiện hành trả contract v1, dùng adapter và kiểm capability ở phía server. Helper eligibility của BKT nhận diện cờ trợ giúp tường minh và giữ cách xử lý lịch sử khi cờ chưa có.

Đã sửa ba vấn đề phát hiện khi review C03/C04/C05; xem [bản review và hướng dẫn tích hợp 0.2.0](review-fixes.md). Bản 0.1.0 được giữ để đối chiếu lịch sử, không phải contract dùng cho tích hợp mới.

JSON Schema mô tả hình dạng dữ liệu. Những quy tắc đối soát giữa các trường được thực thi bằng Pydantic và tests; validator chỉ đọc JSON Schema không tự có toàn bộ quy tắc nghiệp vụ đó.

## 2. Kết quả kiểm kê

| Chỉ số | Thực tế |
|---|---:|
| Concept trong danh mục đã xác nhận | 40 / 40 |
| Concept và alignment đã duyệt trong [registry v2](../../../../content/curriculum/registry.v2.json) | 40 / 40 |
| Pack trong pilot canonical, đều nháp | 10 |
| Bài / ví dụ / mẫu lỗi / mức hint trong pilot canonical | 60 / 30 / 20 / 30 |
| Concept có pack ở ít nhất một nguồn | 20 |
| Concept có pack đã duyệt ở các lô biên soạn | 15 |
| Concept chưa có pack trong các nguồn được kiểm kê | 20 |
| Concept mở luồng demo nội bộ theo ID mới | 13 |
| Concept đủ mọi cổng xuất bản của pilot canonical | 0 |
| Phân công Member 1 / 2 / 3 | 13 / 13 / 14 |
| Quyết định đã thông qua | 5 / 5 |

Validator bậc nhất theo bước áp dụng cho `CON-LINEAR-01` / `SK-LIN-SOLVE`. Validator của lô M2-ORIG02 kiểm tra dòng cuối theo loại bài. Chủ đề `E02` / `SK-E02-SOLVE` thuộc lô thay thế riêng và ngoài phạm vi nghiệm thu này.

## 3. Năm quyết định đã được thông qua

| ID | Baseline được thông qua | Phân công triển khai tiếp |
|---|---|---|
| M2-C01: ID legacy | Giữ ID và BKT của phiên cũ. Dùng ID canonical cho nội dung mới; adapter có version và kế hoạch replay riêng trước khi đổi runtime. Chưa áp dụng mapping đề xuất vào lịch sử. | Member 1 quyết định adapter/migration; Member 2 rà taxonomy |
| M2-C02: public task/readiness | Bài mới dùng `task.kind`, `expression`, `variable_value` thay giả định mọi bài đều có `equation`. Public projector bỏ đáp án/bước chuẩn/nguồn nhóm riêng. Chủ đề chỉ mở khi tất cả readiness gates có bằng chứng. | Member 1 review API/capability; Member 2 triển khai UI khi tích hợp |
| M2-C03: hint | Tích hợp đầu tiên dùng 0–3; trạng thái đã nhận trợ giúp được lưu riêng, kể cả explanation mức 0. Chỉ cập nhật sau khi chốt phản hồi hỗ trợ. Mức 4 của FR-13 vẫn cần Member 3 đặc tả và Member 1 mở contract/DB. | Member 3 review ý nghĩa sư phạm; Member 1 review contract/DB |
| M2-C04: retrieval/response | Scope server cấp từng cặp concept–skill và đối chiếu registry. Result có request/retrieval ID, snapshot, config/embedding version và fallback reason. Ví dụ khác là public task riêng; giữ nhãn `draft_template` trung thực. | Member 2 làm retrieval; Member 3 review và tích hợp Agent/guard |
| M2-C05: report | Snapshot cuối phiên đếm observation của phiên bằng ID riêng, tách khỏi số observation phiên khác xen vào count tích lũy. Không có observation của phiên thì giữ snapshot ban đầu. Giữ parameter provenance và không gán toàn bộ mastery delta cho riêng phiên khi có xen kẽ. | Member 2 chốt trình bày; Member 1 review phép tính/API |

**Chữ ký ghi nhận ngày 23/11/2026.**  Hồ sơ dựa trên lời xác nhận của người dùng về quyết định của cả nhóm. Ngày trên là ngày ghi hồ sơ. Các trường chữ ký cá nhân `reviewed_by` và `reviewed_at` để trống, với bằng chứng chấp thuận chung lưu tại `team_confirmation` trong ma trận JSON.

Member 2 chịu trách nhiệm biên soạn **N02, N05, N08, A01, A04, A07, A10, E03, E06, E09, F02, F05, F08**. Hồ sơ xuất bản từng phiên bản nội dung hoặc đồ thị ghi rõ phạm vi và bằng chứng tích hợp tương ứng.

## 4. Ý nghĩa và giới hạn của contract

### Public problem và readiness

`project_curriculum_problem()` biểu diễn bài authoring bằng contract 0.3.0. Việc xuất bản dùng kết quả từ các cổng review, readiness và quyền người dùng. `project_legacy_problem()` dùng dữ liệu public đã lưu của phiên cũ để nhận diện dạng bài. Phiên và báo cáo v1 giữ định dạng gốc, kể cả kết quả replay đã commit.

`ConceptReadiness.ready` được tính từ các gates, không nhận trường `ready=true` từ payload. Các gates gồm có pack, concept/alignment/pack được duyệt, prerequisite hợp lệ, validator được tích hợp, UI/policy được nghiệm thu và contract được review.

Hai cổng validator và UI/policy của canonical IDs vẫn là `false` cho đến khi có bằng chứng tích hợp theo đúng cặp concept–skill và dạng bài. Capability của demo được đánh giá riêng tại `/topics`, lúc mở phiên và khi chọn bài chấm.

### Retrieval

`RetrievalQuery` chỉ gồm query, concept, skill, purpose và top K. `ServerRetrievalScope.from_registry()` tạo scope từ state server và kiểm tra từng cặp trong `allowed_targets` với registry. Query phải khớp một cặp đầy đủ; không được lấy nguyên scope từ browser hoặc LLM. Pydantic không tạo ra quyền truy cập và việc dùng class có tên “Server” không tự chứng minh scope đáng tin.

Mọi teaching chunk có `counts_as_assistance=true`, độc lập với mức hint. `TutorPresentation.assistance_provided` và `OpportunityAssistance.record_delivery()` ghi nhận trợ giúp theo đúng opportunity, giữ cờ trợ giúp và mức cao nhất qua retry/lượt sau. Chỉ lấy nội dung từ KB chưa có nghĩa là học sinh đã nhận trợ giúp. Quy trình tích hợp chi tiết nằm trong bản review 0.2.0.

`RetrievalExchange` đối chiếu request/result về correlation ID, KB snapshot, số lượng, concept/skill/purpose, grade/difficulty, mức hỗ trợ và loại trừ bài/source group. Ví dụ khác bắt buộc có problem ID và source group để kiểm tra exclusion.

Chunk có provenance review, source, content version và metadata; chunk không cho phép các trường private reference. Tuy nhiên, một lời giải vẫn có thể nằm trong trường text hợp lệ. Khi triển khai retrieval/generator, vẫn cần review nội dung thật, publication filter theo concept/alignment/pack, manifest snapshot và guard đầu ra của Member 3. Các validators ở đây chưa phải bộ lọc runtime đã tích hợp.

`content_version` là phiên bản từng nội dung; `kb_snapshot_version` là phiên bản tập nội dung đã publish. Hai giá trị không bắt buộc bằng nhau. Chặng đồng bộ sau này phải kiểm tra chunk-version thực sự thuộc snapshot; phần này chưa có kho snapshot để xác minh membership.

### Fixtures và report

Năm public problem fixture là phép chiếu từ pilot nháp, mỗi loại task một bài. Session IDs, reviews của chunk, cấu hình embedding, phản hồi và report đều là **synthetic fixtures**. `human_approved` trong fixture chỉ thử nhánh schema; không chứng nhận bất kỳ pack/concept thật nào. “Semantic” trong fixture là ví dụ nhãn method, chưa có phép tìm kiếm embedding thật.

Report minh họa một observation sai độc lập rồi sửa đúng sau hỗ trợ: một kết quả đúng có hỗ trợ, một observation và mastery giảm theo bootstrap. Có thêm ca chưa có bằng chứng, ca giữ nguyên snapshot cũ và ca hai observation của phiên xen với một observation của phiên khác. Count tích lũy chênh 3 nhưng phiên chỉ được ghi 2 observation, với hai ID riêng; không diễn giải mastery delta thành tác động riêng của phiên.

Report proposal hiện chốt phần facts theo skill. Timeline, hypotheses và recommendations có evidence sẽ được bổ sung cùng API/report ở Chặng 4; chưa coi là hoàn tất FR-18.

## 5. Kiểm tra và tự review

Chạy từ repo root bằng Python có Pydantic 2:

```powershell
python scripts/checks/check_member2_foundation.py
python -m unittest discover -s tests -p test_member2_foundation.py -v
python scripts/checks/check_curriculum.py
python scripts/checks/check_phase1.py
python scripts/exports/export_contracts.py --check
```

Check mới đối chiếu schema, public fixtures, ma trận và bằng chứng legacy với source hiện tại. CI được bổ sung check này; `pytest tests` sẵn có cũng phát hiện các test `unittest` mới. Chưa có kết quả chạy CI từ xa trong lần làm này.

`--render schema`, `--render problem-schema`, `--render problem-examples`, `--render coverage-json` và `--render coverage-md` in bản sinh tương ứng ra stdout. Lệnh mặc định đọc và đối chiếu artifact. Khi nguồn thay đổi, sinh lại artifact từ dữ liệu đã version.

Tự review các rủi ro chính:

- ID và dữ liệu legacy còn nguyên; schema v1 cũ vẫn khớp; đề xuất mới nằm trong namespace riêng.
- Hồ sơ xác nhận phải khớp đủ ba thành viên, 40 concept, năm cổng và checksum của các artifact đã được thông qua.
- Matrix lấy dữ liệu từ registry/pilot thay vì điền tay; việc thiếu concept, trùng phân công hoặc lệch artifact được phát hiện.
- Có negative tests cho private payload, vượt hint, draft, thiếu review provenance, sai scope, trùng chunk, query sửa server scope, report sai count/delta/thời điểm.
- Kiểm tra trên dữ liệu synthetic/authoring không chứng minh chất lượng sư phạm, performance retrieval hoặc tích hợp API/browser.

Các lượt kiểm tra trước khi ghi nhận xác nhận nhóm được lưu tại [verification-fixes.json](verification-fixes.json) và [verification.json](verification.json).

## 6. Readiness sau khi xác nhận

Các gate hợp đồng, concept và alignment đã đạt cho toàn bộ 40 concept. Luồng demo nội bộ có **13 concept đã nghiệm thu** từ lô M2-ORIG02. Cột readiness của pilot canonical vẫn tính pack, điều kiện tiên quyết và bằng chứng tích hợp theo bản canonical. [Nghiệm thu demo](../part4/README.md)
