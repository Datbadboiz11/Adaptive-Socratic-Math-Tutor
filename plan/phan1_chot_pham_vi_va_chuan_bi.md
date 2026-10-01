# Phần 1 — Chốt phạm vi và chuẩn bị

**Trạng thái:** Chưa thực hiện.  
**Mục tiêu:** Cả nhóm thống nhất một bản MVP có thể làm và chứng minh được trước gate.  
**Thời điểm:** 01/10; hoàn tất trước các thay đổi tích hợp lớn.

## 1. Luồng bắt buộc đề xuất

Hồ sơ demo → chọn chủ đề phương trình bậc nhất → nhận bài → nhập từng bước → hệ thống xác minh → hỏi gợi mở khi cần → sửa bài → thử bài mới → kết thúc → xem báo cáo. Có tạm dừng/tiếp tục và thử lại khi request lỗi.

MVP dùng hồ sơ tổng hợp phục vụ demo nội bộ, không giả lập chúng thành tài khoản học sinh thật. Nếu mở ra Internet, phải giải quyết xác thực và phân quyền trước; không coi một `student_id` gửi từ client là kiểm soát truy cập.

## 2. Việc cần làm

- [ ] Kiểm tra rubric G2 và repository nhóm đang dùng; chốt nhánh nộp, quy tắc review và đầu mối.
- [ ] Chọn môi trường local bằng Docker Compose; remote chỉ làm nếu gate yêu cầu hoặc còn thời gian.
- [ ] Bám stack trong PRD: Next.js/React, FastAPI/Pydantic, PostgreSQL, SymPy, LangGraph; HTTP trước.
- [ ] Chốt model API, quyền truy cập, giới hạn chi phí và cấu hình qua biến môi trường. Không ghi API key vào repo.
- [ ] Giữ `design/` làm tài liệu tham chiếu; dựng mã sản phẩm riêng, chẳng hạn `frontend/`, `backend/`, `content/`, `tests/`, `docs/`.
- [ ] Ghi rõ KG/Neo4j và vector RAG chưa thuộc lát cắt G2 đề xuất. Truy xuất nội dung theo skill ID không được quảng cáo là đã hoàn thành RAG.
- [ ] Chốt grammar nhập Toán, cách gán skill và protocol observation trước khi code.

## 3. Nội dung toán tối thiểu

Chuẩn bị ít nhất 6 bài đã review trong 3 họ: `ax+b=c`, `a(x+b)=c`, `ax+b=cx+d`; giới hạn nghiệm duy nhất, một ẩn, hệ số đơn giản và không có biến ở mẫu. Mỗi họ chỉ mở trên UI khi validator thực sự hỗ trợ.

Mỗi bài cần: ID, concept/skill, họ mẫu, đề, đáp án tham chiếu, cách giải hợp lệ, lỗi thường gặp, hint ladder, ví dụ khác, nguồn/người review/version. Đáp án tham chiếu nằm phía server; API nhận bài không gửi kèm nghiệm.

Ví dụ xuyên suốt: `2(x - 3) = 10`; bước `2x - 3 = 10` là bước sai đầu tiên. Các bước biến đổi đúng từ phương trình sai đó không bị tính thành nhiều lỗi mới.

Bài tiếp theo phải có metadata quan hệ với bài/ví dụ trước: bài mới khác họ hay luyện tập gần. Chỉ đổi số không tự động trở thành bằng chứng chuyển giao độc lập. Chốt trường hợp đủ điều kiện observation trước khi thu kết quả.

## 4. Contract cần thống nhất

| Đối tượng | Trường tối thiểu đề xuất |
|---|---|
| Problem | `problem_id`, `concept_id`, `skill_ids`, `family_id`, `prompt`, `content_version` |
| Session | `session_id`, `student_id`, `status`, `state_version`, `current_opportunity_id` |
| Submission | `request_id`, `session_id`, `opportunity_id`, `expected_state_version`, `steps` |
| Verification | `status`, `first_wrong_step`, `reason_code`, `supported_scope`, `validator_version` |
| Diagnosis | `hypothesis`, `status: suspected`, `evidence_refs` |
| Observation | `opportunity_id`, `skill_id`, `eligible`, `eligibility_reason`, `correct`, `assistance_level` |
| Tutor response | `action`, `message`, `hint_level`, `next_actions`, `response_source` |
| Report | Kết quả độc lập/có hỗ trợ, số observation hợp lệ, lịch sử phiên và giới hạn dữ liệu |

Không suy đoán mọi skill trong một bài đều đã được quan sát. Với lát cắt đầu tiên có thể quy định một skill đích cho một opportunity; chỉ cập nhật skill có đủ bằng chứng.

## 5. Điều kiện xong

- [ ] Nhóm biết rõ mục nào làm trong G2, mục nào còn thiếu so với PRD.
- [ ] Repo và người phụ trách đã xác định, không tạo repo trùng.
- [ ] Có contract và bộ nội dung seed đã review để backend/frontend cùng dùng.
- [ ] Môi trường API model và DB sẵn sàng; rủi ro thiếu quyền truy cập đã được ghi nhận.

**Bàn giao:** quyết định scope, contract và nội dung seed cho [phần 2](phan2_backend_va_du_lieu.md) và [phần 3](phan3_gia_su_socratic.md).
