# Member 2 — Phần 1: hợp đồng và ma trận độ phủ

Ngày thực hiện: 16/11/2026. Theo [Chặng 1 của kế hoạch Member 2](../../../planning/member-2-plan.md).

**Trạng thái:** bộ chuẩn bị kỹ thuật đã triển khai và kiểm tra; năm quyết định giao diện và phân công nội dung vẫn chờ nhóm review. Chưa đạt điều kiện “được cả ba thành viên review” của Chặng 1. Dừng tại mốc này để người dùng review trước khi thực hiện Chặng 2.

## 1. Đầu ra và thứ tự review

1. [coverage.md](coverage.md): ma trận 40 concept, owner/reviewer đề xuất, nội dung hiện có, skill và dạng authoring.
2. [Workboard](../../../../content/curriculum/member2-workboard.v1.json): nguồn đề xuất phân công 13/13/14 concept và năm cổng review.
3. [Hợp đồng Python](../../../../backend/app/member2_contracts.py): kiểu dữ liệu và quy tắc nhất quán cho public problem, readiness, retrieval, tutor presentation và report.
4. [Fixtures 0.2.0](../../../../contracts/member2/v0.2.0/examples.json) và [JSON Schema 0.2.0](../../../../contracts/member2/v0.2.0/FoundationExamples.schema.json): ví dụ hiện hành để Member 1/3 thảo luận và viết tích hợp.
5. [Tests](../../../../tests/test_member2_foundation.py): kiểm tra ranh giới dữ liệu, disclosure, snapshot, readiness và độ khớp artifact.
6. [coverage.json](coverage.json): bản đầy đủ có nguồn, scope, trạng thái review, blockers và SHA-256 đầu vào.

Đây là module đề xuất `member2-proposal-0.2.0`. FastAPI, DB, tutor và frontend đang chạy chưa nhập hoặc sử dụng module hợp đồng này. Helper eligibility của BKT đã được bổ sung nhận diện cờ trợ giúp tường minh, giữ cách xử lý cũ khi cờ chưa có. Chưa có endpoint mới, migration hoặc lời gọi LLM/embedding.

Đã sửa ba vấn đề phát hiện khi review C03/C04/C05; xem [bản review và hướng dẫn tích hợp 0.2.0](review-fixes.md). Bản 0.1.0 được giữ để đối chiếu lịch sử, không phải contract dùng cho tích hợp mới.

JSON Schema mô tả hình dạng dữ liệu. Những quy tắc đối soát giữa các trường được thực thi bằng Pydantic và tests; validator chỉ đọc JSON Schema không tự có toàn bộ quy tắc nghiệp vụ đó.

## 2. Kết quả kiểm kê

| Chỉ số | Thực tế |
|---|---:|
| Concept trong registry | 40 |
| Pack hiện có, đều nháp | 10 |
| Bài / ví dụ / mẫu lỗi / mức hint | 60 / 30 / 20 / 30 |
| Pack được duyệt / chunk được công bố | 0 / 0 |
| Concept đủ điều kiện end-to-end theo ID mới | 0 |
| Phân công đề xuất Member 1 / 2 / 3 | 13 / 13 / 14 |
| Quyết định được nhóm ký review | 0 / 5 |

Validator online hiện hỗ trợ phương trình trên `CON-LINEAR-01` / `SK-LIN-SOLVE` trong demo nội bộ. Điều này không xác nhận khả năng chấm trên `E02` / `SK-E02-SOLVE`. Bộ kiểm tra authoring năm loại task cũng không thay thế bộ chấm input của học sinh.

## 3. Năm quyết định cần nhóm review

| ID | Đề xuất trong phần này | Người review / phần triển khai tiếp |
|---|---|---|
| M2-C01: ID legacy | Giữ ID và BKT của phiên cũ. Dùng ID canonical cho nội dung mới; adapter có version và kế hoạch replay riêng trước khi đổi runtime. Chưa áp dụng mapping đề xuất vào lịch sử. | Member 1 quyết định adapter/migration; Member 2 rà taxonomy |
| M2-C02: public task/readiness | Bài mới dùng `task.kind`, `expression`, `variable_value` thay giả định mọi bài đều có `equation`. Public projector bỏ đáp án/bước chuẩn/nguồn nhóm riêng. Chủ đề chỉ mở khi tất cả readiness gates có bằng chứng. | Member 1 review API/capability; Member 2 triển khai UI khi tích hợp |
| M2-C03: hint | Tích hợp đầu tiên dùng 0–3; trạng thái đã nhận trợ giúp được lưu riêng, kể cả explanation mức 0. Chỉ cập nhật sau khi chốt phản hồi hỗ trợ. Mức 4 của FR-13 vẫn cần Member 3 đặc tả và Member 1 mở contract/DB. | Member 3 review ý nghĩa sư phạm; Member 1 review contract/DB |
| M2-C04: retrieval/response | Scope server cấp từng cặp concept–skill và đối chiếu registry. Result có request/retrieval ID, snapshot, config/embedding version và fallback reason. Ví dụ khác là public task riêng; giữ nhãn `draft_template` trung thực. | Member 2 làm retrieval; Member 3 review và tích hợp Agent/guard |
| M2-C05: report | Snapshot cuối phiên đếm observation của phiên bằng ID riêng, tách khỏi số observation phiên khác xen vào count tích lũy. Không có observation của phiên thì giữ snapshot ban đầu. Giữ parameter provenance và không gán toàn bộ mastery delta cho riêng phiên khi có xen kẽ. | Member 2 chốt trình bày; Member 1 review phép tính/API |

Workboard ghi tất cả quyết định là `pending_review`. Chỉ chuyển `accepted` khi người review thực sự xác nhận và ghi `reviewed_by`, `reviewed_at`. Schema kiểm tra định dạng/nhất quán của chữ ký này, không xác thực danh tính con người; quy trình nhóm chịu trách nhiệm về tính thật của bản ghi.

Phân công biên soạn chia đều concept giữa bốn nhóm nội dung và review chéo. Member 2 được đề xuất: **N02, N05, N08, A01, A04, A07, A10, E03, E06, E09, F02, F05, F08**. Danh sách có thể điều chỉnh sau khi nhóm cân đối độ khó và giờ công; chưa sửa tác giả hoặc trạng thái duyệt của bất kỳ nội dung gốc nào.

## 4. Ý nghĩa và giới hạn của contract

### Public problem và readiness

`project_problem()` là phép chiếu dữ liệu có chọn trường, dùng để thảo luận schema. Hàm không cấp phép xuất bản nội dung nháp. Khi làm endpoint thực tế, server còn phải kiểm tra review, readiness và quyền người dùng.

`ConceptReadiness.ready` được tính từ các gates, không nhận trường `ready=true` từ payload. Các gates gồm có pack, concept/alignment/pack được duyệt, prerequisite hợp lệ, validator được tích hợp, UI/policy được nghiệm thu và contract được review.

Ở baseline hiện tại, hai gates validator/UI của canonical IDs luôn là false vì chưa có bằng chứng tích hợp. Việc các gate review nội dung chuyển true không tự mở chủ đề. Khi triển khai tích hợp sau này cần bổ sung nguồn capability/evidence đã được kiểm chứng thay cho baseline này.

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

`--render schema`, `--render coverage-json`, `--render coverage-md` in bản sinh tương ứng ra stdout để review. Lệnh mặc định chỉ đọc/đối chiếu, không ghi đè artifact. Khi source thay đổi, cập nhật artifact bằng quy trình chỉnh sửa/review; không sửa số liệu tổng trong ma trận bằng tay.

Tự review các rủi ro chính:

- ID và dữ liệu legacy còn nguyên; schema v1 cũ vẫn khớp; đề xuất mới nằm trong namespace riêng.
- Owner và review status được ghi là đề xuất/chờ review; không tạo bằng chứng nhóm đã xác nhận.
- Matrix lấy dữ liệu từ registry/pilot thay vì điền tay; việc thiếu concept, trùng phân công hoặc lệch artifact được phát hiện.
- Có negative tests cho private payload, vượt hint, draft, thiếu review provenance, sai scope, trùng chunk, query sửa server scope, report sai count/delta/thời điểm.
- Kiểm tra trên dữ liệu synthetic/authoring không chứng minh chất lượng sư phạm, performance retrieval hoặc tích hợp API/browser.

Kết quả bản sửa hiện hành nằm tại [verification-fixes.json](verification-fixes.json). [verification.json](verification.json) là snapshot kiểm tra của bản 0.1.0 trước khi sửa; hash trong bản cũ mô tả source lúc đó, không phải source hiện tại.

## 6. Điểm dừng và bước tiếp theo

Phần chuẩn bị kỹ thuật của Chặng 1 đã có artifact để review. Cần nhóm xác nhận năm quyết định và cân đối phân công để hoàn tất gate review của Chặng 1.

Sau khi người dùng review mốc này, phần tiếp theo là **Chặng 2: pipeline LLM soạn nháp + checker + quy trình review**, bắt đầu từ E02/A02. Phần đó chưa được thực hiện trong lần này.
