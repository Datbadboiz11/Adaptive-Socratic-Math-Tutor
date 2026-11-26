# Chặng 4 — Tích hợp nội dung KB vào lượt gia sư

## Bản hoàn thiện các thiếu sót — 26/11/2026

Đã nối KB Chặng 3 vào LangGraph cho 13 concept Member 2 và hoàn thiện các thiếu sót được rà soát ở UI/báo cáo: hook quản lý phiên, chẩn đoán có bằng chứng, provenance BKT, phân thức/hệ phương trình và nghiệm thu bàn phím/timeout. Bộ lắp phản hồi dùng nguyên văn teaching text đã duyệt; chưa bật sinh câu trả lời tự do bằng LLM.

Nghiệm thu trạng thái workspace hiện hành: **149 test backend/runtime và 4 test cấu trúc công thức đạt, 0 lỗi, 0 skip**; **10 nhóm Chromium đạt** với DB/weights embedding thật; frontend production build và TypeScript đạt. Hồ sơ ghi rõ suite được chạy và giới hạn archive lịch sử, không coi đây là chạy lại toàn bộ 400 test trên workspace hiện tại. Kết quả và hash cuối nằm trong [verification](verification-stage4-2026-11-26.json).

Luồng thực tế:

```text
Session pin Full/No-RAG + snapshot KB
  → validate → eligibility → policy
  → retrieve (direct hint/explanation, metadata example)
  → assemble approved text → exact-output guard
  → transaction commit: turn + delivery + assistance + observation nếu đủ điều kiện
  → UI nguồn đã dùng → report đóng băng cuối phiên
```

### Đã triển khai và ranh giới

| Hạng mục trong plan 4 | Kết quả hiện hành |
|---|---|
| Node/tool retrieval và dùng nội dung | Node `retrieve` chạy ngoài transaction session. Hint/explanation có ID đã biết dùng direct lookup, example dùng metadata lọc scope; không gọi embedding mỗi lượt. |
| Ref được lấy, ref vào generator, ref được giao | Ba danh sách riêng trong `turns.pipeline.retrieval`. Assembler nhận đúng một teaching projection; UI chỉ nhận `content_refs` thực sự có trong phản hồi đã guard. |
| Replay/resume | `requests`, `turn_jobs.prepared` và checkpoint giữ kết quả đã tính. Retry turn đã commit không chạy lại graph/retrieval khi active KB đổi. |
| Full/No-RAG | Server ghim mode/snapshot khi tạo session. No-RAG thoát trước khi đọc registry/chunk/cache. Baseline vẫn dùng các gợi ý xác định từ pack theo policy cũ; không có retrieved context hay citation KB. |
| Delivery và assistance | Cờ `assistance_received` đơn điệu, độc lập với `hint_level`. Giải thích mức 0 vẫn là hỗ trợ khi đã giao. Retrieval đơn thuần không bật cờ; ledger và response commit nguyên tử. |
| Withdrawal và outage | Commit kiểm lại membership/hash và withdrawal dưới namespace lock. KB bị lỗi không đổi kết quả bộ chấm, không tạo citation/assistance giả, không dùng lại nội dung từ snapshot đã bị chặn. |
| Ví dụ khác bài đang đo | Lọc family/source/lineage trước top-K. Family của ví dụ đã giao còn được xét khi phân loại bài luyện gần ở những lượt sau. |
| Student UI | Tách API/types, `useTutorSession`, feedback, report, MathText và ProblemFormula. Hook quản lý draft/retry/xung đột/hồ sơ; giữ nguyên request khi retry. Chuyển focus sau khi React dựng phản hồi, gồm lượt gửi đầu tiên. |
| Types/formula | Types public sinh từ schema backend, có drift check. Native MathML hỗ trợ biểu thức số/biến, phân thức lồng, số mũ, căn, so sánh và hệ nhiều phương trình; parser giới hạn độ dài/token/độ sâu, không thực thi HTML/TeX. Đề A10/E09 có layout theo task; không suy ra đáp án bài lời văn. Ký hiệu ngoài grammar giữ escaped text. |
| Learning report | Report 2.1 có chẩn đoán kèm facts/turn IDs và trạng thái `suspected`/`supported`/`rejected`, liên kết về bài nộp, nguồn/version/time BKT trong phần mở rộng. Giữ số liệu theo skill và snapshot `session_reports`; đọc được report 2.0 mà không viết lại payload cũ. |

13 concept canonical tiếp tục dùng bộ chấm dòng cuối và **không tạo BKT observation**. Report hiển thị thiếu observation thay vì suy diễn mastery. Legacy giữ ID/skill/BKT cũ và `no_rag`; mapping canonical còn `proposed` nên không tự nhập KB E02 vào phiên legacy.

Receipt delivery có nghĩa phản hồi hỗ trợ đã commit để trả cho client; hệ thống chưa có cơ chế xác nhận học sinh đã đọc. Khi mất phản hồi mạng, retry đối soát đúng receipt đã commit. Report đưa gợi ý luyện thêm dựa trên turn chưa đúng có evidence ID, không tự chẩn đoán học sinh yếu hay gán prerequisite thành điểm yếu.

`suspected` cần một dấu vết sai đã xác minh khớp mẫu biên soạn. `supported` chỉ xác nhận dấu vết lặp lại ở lượt đầu chưa nhận hỗ trợ trên ít nhất hai họ bài độc lập; không nâng thành kết luận về hiểu biết tiềm ẩn. `rejected` là một nhận định riêng về bài làm mới nhất đã được xác minh đúng trên chính opportunity đó; nhận định nghi vấn lịch sử vẫn giữ nguyên. Lượt chưa xác minh, thiếu mẫu hoặc thiếu facts không sinh chẩn đoán. Các nhánh được kiểm bằng dữ liệu synthetic có ghi rõ; browser dùng report legacy thật để kiểm nghi vấn, sửa đúng và provenance.

Nguồn BKT chỉ gắn với phiên bản tham số biết được; phiên bản cũ không có archive nguồn hiển thị thiếu provenance thay vì mượn nguồn hiện hành. Canonical không có observation tiếp tục hiển thị thiếu dữ liệu BKT.

### Chạy và đối soát

```powershell
.\.venv\Scripts\python.exe scripts/dev/validation_runtime.py database
.\.venv\Scripts\python.exe scripts/kb/sync_kb.py --workspace-local sync --activate
.\.venv\Scripts\python.exe scripts/exports/export_frontend_types.py --check
.\.venv\Scripts\python.exe scripts/dev/validation_runtime.py tests --suite stage4
npm --prefix frontend run typecheck
npm --prefix frontend test
npm --prefix frontend run build
.\.venv\Scripts\python.exe scripts/checks/check_stage4_browser.py
```

Đặt `TUTOR_RAG_MODE=full` hoặc `no_rag` ở environment của backend rồi tạo session mới. Session cũ giữ mode/snapshot đã ghim; client không gửi mode, scope hoặc quyền hint. Chạy `scripts/dev/validation_runtime.py serve` để mở bản build hiện hành khi các cổng cấu hình còn trống; backend/frontend đang chạy từ bản cũ cần khởi động lại bằng quy trình vận hành của chúng.

Browser checker tự tạo schema PostgreSQL và hai web process trên cổng riêng, dùng weights embedding cục bộ thật, chạy xong dừng process và dọn schema. Nó kiểm luồng sai → KB hint → đúng có hỗ trợ → bài độc lập → report trên N02/A10/F05, hệ E09, report legacy thật, retry mất phản hồi, example citation, pause/reload/resume, hai tab xung đột, đổi hồ sơ và khung 390/1440 px. Kiểm Tab/Shift+Tab, skip link, Ctrl+Enter, focus phản hồi, mở provenance và theo liên kết evidence bằng bàn phím. Ca timeout dùng đồng hồ ảo Playwright đi qua đúng AbortController 45 giây của production: server đã commit, response bị giữ, UI giữ nháp/khóa lúc tải rồi retry cùng payload, cuối cùng chỉ có một turn và state version 2. Không hạ timeout trong mã sản phẩm. Kiểm MathML/XSS bổ sung dùng public GET synthetic; không coi payload đó là output của gia sư.

Bộ `--suite stage4` gồm integration Chặng 4 trên đủ 13 concept, bộ chấm canonical/legacy, phiên/API và kiểm publication hiện hành. Full suite 400 test đã đạt trước khi các lô A02/E02 lịch sử không còn trong workspace; lượt nghiệm thu hiện tại không coi kết quả đó là full-suite pass của trạng thái mới. Lệnh `tests` không chọn suite vẫn giữ kiểm toàn bộ lịch sử và cần những source archive tương ứng. Checker KB hiện hành ghi rõ `historical_sources_unavailable` nếu thiếu archive, không suy ra archive đã được kiểm.

Hồ sơ hiện hành: [verification](verification-stage4-2026-11-26.json), [browser](browser-stage4-2026-11-26.json), [JUnit backend](tests-stage4-2026-11-26.xml), [JUnit frontend](tests-frontend-stage4-2026-11-26.xml). Thu lại bằng `scripts/checks/collect_stage4_validation.py --browser-run ID_TU_BROWSER_CHECKER`. Trong lượt này `.env.example` cũng không còn trong workspace; collector ghi `configuration_files_unavailable`, không tái tạo hoặc thay thế tệp đã bị loại khỏi workspace.

### Bàn giao và phạm vi riêng

- [Hồ sơ Member 1/3 review](independent-review.md) có bước tái hiện, phạm vi và chỗ ghi quyết định; đang chờ người review thực hiện.
- Đã chuẩn bị workflow [Stage 4 current release](../../../../.github/workflows/stage4-current-checks.yml), chạy đúng suite hiện hành và test/typecheck/build frontend. Chưa chạy remote CI hoặc Docker; Docker CLI không có trong môi trường này. Workflow repository đầy đủ vẫn yêu cầu archive lịch sử; workflow mới không biến phần thiếu archive thành pass.
- Sinh lời tự do bằng LLM, graph điều hướng, session trộn skill, ký hiệu toán ngoài grammar và thực nghiệm RQ3 là phạm vi riêng. Full/No-RAG hiện có kiểm thử kỹ thuật, chưa phải kết quả nghiên cứu RQ3.

## Hồ sơ demo trước tích hợp retrieval — 24/11/2026

Nghiệm thu ngày 24/11/2026 với lô [M2-ORIG02 đã duyệt](../../../../content/authoring/batches/member2-original.v2/manifest.json). Demo nội bộ mở **13 chủ đề, 78 bài**, mỗi chủ đề có sáu bài. `app.manage bootstrap` seed lô đã xác minh hash vào PostgreSQL cùng dữ liệu demo cũ và có thể chạy lặp. `/api/v1/topics` báo khả năng mở phiên theo nội dung thực tế trong DB và cấu hình bộ chấm.

| Luồng | Kết quả nghiệm thu |
|---|---|
| Chọn chủ đề và làm bài | UI mở được cả 13 chủ đề. Đề và hướng dẫn nhập thay đổi theo dạng bài, gồm tọa độ đỉnh, trục đối xứng và điều kiện cơ số. |
| Chấm bài | Kiểm đúng 78 đáp án chuẩn và 39 mẫu lỗi. Bộ chấm xác minh dòng cuối, ghi `needs_clarification` cho đầu vào ngoài định dạng, lưu các dòng trước trong nhật ký. |
| Policy | Câu sai có thể nhận gợi ý từ đúng pack đã duyệt. Tối đa ba mức, sau đó UI cho xem phản hồi mời dừng hoặc chuyển bài. |
| Phiên học | Lưu nháp, tạm dừng, tải lại, tiếp tục và gửi lại cùng request giữ đúng trạng thái. |
| Báo cáo | Bài tự làm đúng, bài đúng sau hỗ trợ và bài lặp hoặc gần được đếm riêng. Chứng cứ BKT chỉ phát sinh ở luồng cũ theo điều kiện hiện hành của nó. |
| Tương thích và hiển thị | 332 test đạt với PostgreSQL, gồm phiên legacy và 13 phiên mới. Build và TypeScript đạt. Chromium chạy cả 13 chủ đề và kiểm khung 1440 px, 390 px. |

Bằng chứng nghiệm thu Chromium lưu tại `artifacts/browser-validation/member2-a48cf61233ee/verification.json` trong workspace.

Đây là luồng luyện tập nội bộ theo các pack đã duyệt. Mỗi phản hồi dùng bộ chấm hoặc gợi ý xác định từ pack. Đánh giá RQ3, khai thác đồ thị để điều hướng và tích hợp retrieval vào lời gia sư vẫn là các hạng mục riêng của kế hoạch.

## Chạy tại workspace

```powershell
.\.venv\Scripts\python.exe scripts/dev/validation_runtime.py database
```

Lệnh `database` chạy migration và seed theo version. Với bản frontend đã build, lệnh `scripts/dev/validation_runtime.py serve` mở backend và frontend nội bộ theo các cổng cấu hình. Kiểm thử trình duyệt dùng một demo PostgreSQL riêng để có hồ sơ mới.

```powershell
python -m pytest tests/test_member2_runtime.py -q
python scripts/checks/check_member2_browser.py --url http://127.0.0.1:3314
```

Đặt `RUN_DB_TESTS=1` và trỏ biến kết nối vào PostgreSQL thử nghiệm để chạy các ca API. Lệnh browser dùng URL của bản demo đã seed và lưu bằng chứng mới dưới `artifacts/browser-validation/`.
