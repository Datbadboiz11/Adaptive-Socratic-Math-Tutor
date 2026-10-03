# Phần 1 — Chốt phạm vi và chuẩn bị

**Trạng thái:** Đã chuẩn bị bộ nội dung, contracts và khung môi trường; còn chờ review chuyên môn, xác nhận phân công/rubric bổ sung và model/ngân sách. Xem [bộ bàn giao chi tiết](../docs/phase1/README.md) và evidence để biết những kiểm tra đã chạy.
**Mục tiêu:** Cả nhóm thống nhất một bản MVP có thể làm và chứng minh được trước gate.  
**Thời điểm:** 01/10; hoàn tất trước các thay đổi tích hợp lớn.

## 1. Luồng bắt buộc đề xuất

Hồ sơ demo → chọn chủ đề phương trình bậc nhất → nhận bài → nhập từng bước → hệ thống xác minh → hỏi gợi mở khi cần → sửa bài → thử bài mới → kết thúc → xem báo cáo. Có tạm dừng/tiếp tục và thử lại khi request lỗi.

MVP dùng hồ sơ tổng hợp phục vụ demo nội bộ, không giả lập chúng thành tài khoản học sinh thật. Nếu mở ra Internet, phải giải quyết xác thực và phân quyền trước; không coi một `student_id` gửi từ client là kiểm soát truy cập.

## 2. Việc cần làm

- [x] Xác định repo hiện có, nhánh `tiendatv1` → PR về `main`, quy trình review và yêu cầu từ ảnh gate.
- [ ] Đối chiếu rubric bổ sung nếu có và gán tên người phụ trách thực tế; chưa tự suy đoán thông tin nhóm.
- [x] Chọn môi trường local bằng Docker Compose; remote chỉ làm nếu gate yêu cầu hoặc còn thời gian.
- [x] Giữ stack trong PRD: Next.js/React, FastAPI/Pydantic, PostgreSQL; SymPy/LangGraph ở giai đoạn xử lý thật; HTTP trước.
- [x] Người dùng xác nhận có OpenAI API; chuẩn bị biến môi trường phía server, mặc định chưa bật gọi model.
- [ ] Chốt model ID, kiểm tra quyền/quota và ngân sách qua benchmark; chưa gọi API tính phí trong Phần 1.
- [x] Giữ `design/`; tạo riêng `frontend/`, `backend/`, `content/`, `contracts/`, `tests/`, `docs/phase1/`.
- [x] Ghi rõ KG/Neo4j và vector RAG chưa thuộc lát cắt G2 đề xuất; xem tài liệu scope.
- [x] Định nghĩa grammar, skill đích và protocol observation g2-v1, tách bài luyện gần và bằng chứng độc lập.

## 3. Nội dung toán tối thiểu

Chuẩn bị ít nhất 6 bài đã review trong 3 họ: `ax+b=c`, `a(x+b)=c`, `ax+b=cx+d`; giới hạn nghiệm duy nhất, một ẩn, hệ số đơn giản và không có biến ở mẫu. Mỗi họ chỉ mở trên UI khi validator thực sự hỗ trợ.

**Đầu ra hiện có:** [6 bài JSON](../content/linear_equations.v1.json) đã có script kiểm tra toán và [phiếu review](../docs/phase1/CONTENT_REVIEW.md). Trạng thái người duyệt vẫn là `draft`; không đồng nhất kiểm tra máy với review chuyên môn. Chưa xử lý dataset trong `data/` và chưa seed DB trong phần này.

Mỗi bài cần: ID, concept/skill, họ mẫu, đề, đáp án tham chiếu, cách giải hợp lệ, lỗi thường gặp, hint ladder, ví dụ khác, nguồn/người review/version. Đáp án tham chiếu nằm phía server; API nhận bài không gửi kèm nghiệm.

Ví dụ xuyên suốt: `2(x - 3) = 10`; bước `2x - 3 = 10` là bước sai đầu tiên. Các bước biến đổi đúng từ phương trình sai đó không bị tính thành nhiều lỗi mới.

Bài tiếp theo phải có metadata quan hệ với bài/ví dụ trước: bài mới khác họ hay luyện tập gần. Chỉ đổi số không tự động trở thành bằng chứng chuyển giao độc lập. Chốt trường hợp đủ điều kiện observation trước khi thu kết quả.

## 4. Contract cần thống nhất

| Đối tượng | Trường tối thiểu đề xuất |
|---|---|
| Problem | `problem_id`, `concept_id`, `skill_ids`, `family_id`, `prompt`, `content_version` |
| Session | `session_id`, `student_id`, `status`, `state_version`, `current_opportunity_id` |
| Submission | `request_id`, `session_id`, `opportunity_id`, `expected_state_version`, `steps` |
| Verification | `assessment_status`, `first_error_step`, `reason_code`, `verification_method`, `validator_version`; bám tên PRD |
| Diagnosis | `hypothesis`, `status: suspected`, `evidence_refs` |
| Observation | `opportunity_id`, `skill_id`, `eligible`, `eligibility_reason`, `correct`, `assistance_level` |
| Tutor response | `action`, `message`, `hint_level`, `next_actions`, `response_source` |
| Report | Kết quả độc lập/có hỗ trợ, số observation hợp lệ, lịch sử phiên và giới hạn dữ liệu |

Không suy đoán mọi skill trong một bài đều đã được quan sát. Với lát cắt đầu tiên có thể quy định một skill đích cho một opportunity; chỉ cập nhật skill có đủ bằng chứng.

Contract thực thi và JSON Schema nằm trong [bộ bàn giao](../docs/phase1/CONTRACTS.md). Skill đích G2 là `SK-LIN-SOLVE`; các skill tiền đề không tự nhận observation từ đáp án cuối.

## 5. Điều kiện xong

- [x] Có tài liệu phân định G2/Phần 1 và những phần còn thiếu so với PRD.
- [x] Repo và nhánh làm việc xác định; phân công theo vai trò đã chuẩn bị.
- [ ] Nhóm xác nhận người phụ trách thực tế và rubric bổ sung.
- [x] Có contract, bộ nội dung seed và kiểm tra kỹ thuật tái chạy được.
- [ ] Có người rà nội dung/sư phạm và ghi thông tin review thực tế.
- [ ] Model cụ thể, quyền/quota, ngân sách đã kiểm chứng; hiện chỉ xác nhận nhà cung cấp OpenAI.

Môi trường local và kết quả health/build/test được ghi riêng trong [evidence](../docs/phase1/evidence/README.md); không dùng trạng thái chuẩn bị để tuyên bố MVP chạy end-to-end.

**Bàn giao:** quyết định scope, contract và nội dung seed cho [phần 2](phan2_backend_va_du_lieu.md) và [phần 3](phan3_gia_su_socratic.md).
