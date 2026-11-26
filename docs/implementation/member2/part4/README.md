# Chặng 4 — Tích hợp nội dung KB vào lượt gia sư

## Bản triển khai đầu tiên — 26/11/2026

Đã nối KB Chặng 3 vào LangGraph cho 13 concept Member 2. Đây là lát cắt xuyên suốt đầu tiên của Chặng 4: giải thích/hint/ví dụ đã duyệt, receipt giao nội dung, UI hiển thị nguồn và report theo skill. Bộ lắp phản hồi dùng nguyên văn teaching text đã duyệt; chưa bật sinh câu trả lời tự do bằng LLM.

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

| Hạng mục trong plan 4 | Kết quả bản đầu |
|---|---|
| Node/tool retrieval và dùng nội dung | Node `retrieve` chạy ngoài transaction session. Hint/explanation có ID đã biết dùng direct lookup, example dùng metadata lọc scope; không gọi embedding mỗi lượt. |
| Ref được lấy, ref vào generator, ref được giao | Ba danh sách riêng trong `turns.pipeline.retrieval`. Assembler nhận đúng một teaching projection; UI chỉ nhận `content_refs` thực sự có trong phản hồi đã guard. |
| Replay/resume | `requests`, `turn_jobs.prepared` và checkpoint giữ kết quả đã tính. Retry turn đã commit không chạy lại graph/retrieval khi active KB đổi. |
| Full/No-RAG | Server ghim mode/snapshot khi tạo session. No-RAG thoát trước khi đọc registry/chunk/cache. Baseline vẫn dùng các gợi ý xác định từ pack theo policy cũ; không có retrieved context hay citation KB. |
| Delivery và assistance | Cờ `assistance_received` đơn điệu, độc lập với `hint_level`. Giải thích mức 0 vẫn là hỗ trợ khi đã giao. Retrieval đơn thuần không bật cờ; ledger và response commit nguyên tử. |
| Withdrawal và outage | Commit kiểm lại membership/hash và withdrawal dưới namespace lock. KB bị lỗi không đổi kết quả bộ chấm, không tạo citation/assistance giả, không dùng lại nội dung từ snapshot đã bị chặn. |
| Ví dụ khác bài đang đo | Lọc family/source/lineage trước top-K. Family của ví dụ đã giao còn được xét khi phân loại bài luyện gần ở những lượt sau. |
| Student UI | Có nút giải thích/ví dụ, phân biệt ví dụ với bài hiện tại, source title dễ đọc và version trong phần mở rộng. Tách API/types, feedback, report và MathText khỏi `workspace.tsx`. |
| Types/formula | Types public sinh từ schema backend, có drift check CI. Spike MathML hỗ trợ phân số đơn, lũy thừa và căn trong inline code; biểu thức khác giữ nguyên escaped text/Unicode. |
| Learning report | Tổng hợp theo skill: kết quả độc lập/hỗ trợ/lặp, lượt sai/chưa xác minh, observation IDs, mốc mastery/count và parameter provenance khi có. Report hoàn thành lưu trong `session_reports`, không lấy mastery mới từ phiên sau. |

13 concept canonical tiếp tục dùng bộ chấm dòng cuối và **không tạo BKT observation**. Report hiển thị thiếu observation thay vì suy diễn mastery. Legacy giữ ID/skill/BKT cũ và `no_rag`; mapping canonical còn `proposed` nên không tự nhập KB E02 vào phiên legacy.

Receipt delivery có nghĩa phản hồi hỗ trợ đã commit để trả cho client; hệ thống chưa có cơ chế xác nhận học sinh đã đọc. Khi mất phản hồi mạng, retry đối soát đúng receipt đã commit. Report đưa gợi ý luyện thêm dựa trên turn chưa đúng có evidence ID, không tự chẩn đoán học sinh yếu hay gán prerequisite thành điểm yếu.

### Chạy và đối soát

```powershell
.\.venv\Scripts\python.exe scripts/dev/validation_runtime.py database
.\.venv\Scripts\python.exe scripts/kb/sync_kb.py --workspace-local sync --activate
.\.venv\Scripts\python.exe scripts/exports/export_frontend_types.py --check
.\.venv\Scripts\python.exe scripts/dev/validation_runtime.py tests
npm --prefix frontend run typecheck
npm --prefix frontend run build
.\.venv\Scripts\python.exe scripts/checks/check_stage4_browser.py
```

Đặt `TUTOR_RAG_MODE=full` hoặc `no_rag` ở environment của backend rồi tạo session mới. Session cũ giữ mode/snapshot đã ghim; client không gửi mode, scope hoặc quyền hint. Chạy `scripts/dev/validation_runtime.py serve` để mở bản build hiện hành khi các cổng cấu hình còn trống; backend/frontend đang chạy từ bản cũ cần khởi động lại bằng quy trình vận hành của chúng.

Browser checker tự tạo schema PostgreSQL và hai web process trên cổng riêng, dùng weights embedding cục bộ thật, chạy xong dừng process và dọn schema. Nó kiểm luồng sai → KB hint → đúng có hỗ trợ → bài độc lập → report trên N02/A10/F05, retry mất phản hồi, example citation, pause/reload/resume, hai tab xung đột, đổi hồ sơ và khung 390/1440 px. Kiểm MathML/XSS dùng public GET được thay thế bằng payload synthetic ngay trong trình duyệt; không coi payload đó là output của gia sư.

Hồ sơ hiện hành: [verification](verification-stage4-2026-11-26.json), [browser](browser-stage4-2026-11-26.json), [JUnit](tests-stage4-2026-11-26.xml). Thu lại bằng `scripts/checks/collect_stage4_validation.py --browser-run ID_TU_BROWSER_CHECKER`.

### Phần tiếp theo của Chặng 4

- Generator LLM có grounded context và review độc lập về toán/disclosure nếu cần diễn đạt tự do; bản này chọn nguyên văn để có guard chặt và 0 API call.
- Tích hợp graph điều hướng/prerequisite với Member 3; recommendation có nguồn và evidence thay vì suy diễn điểm yếu.
- UI chẩn đoán phong phú hơn, session nhiều skill, tách hook quản lý session và render hệ/phân thức tổng quát.
- Nghiệm thu Docker/remote CI và ký review riêng của Member 1/3. Full/No-RAG hiện là cấu hình có kiểm thử, chưa phải thực nghiệm RQ3.

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
