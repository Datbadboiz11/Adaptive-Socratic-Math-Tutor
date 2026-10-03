# Quyết định phạm vi G2 và ranh giới Phần 1

## 1. Các quyết định đã chốt trong phiên làm việc

| ID | Quyết định | Căn cứ / tác động |
|---|---|---|
| D01 | Giữ PostgreSQL | Người dùng đã chọn; bám PRD, thuận tiện pgvector/checkpoint khi đến giai đoạn đó |
| D02 | Next.js/React + FastAPI/Pydantic | Stack PRD, prototype `design/` được giữ nguyên để tham chiếu |
| D03 | OpenAI là nhà cung cấp | Người dùng xác nhận đã có API; model/version chưa chọn |
| D04 | Một chủ đề phương trình bậc nhất cho lát cắt G2 | Ưu tiên một luồng end-to-end; không thay mục tiêu 40 concept và P0 cuối kỳ |
| D05 | Sáu bài tự biên soạn, ba họ mẫu | Không phụ thuộc quyền truy cập dataset KT; đủ fixtures ban đầu |
| D06 | Local qua Docker Compose, bind localhost | Không triển khai public app hoặc xử lý học sinh thật khi chưa có auth |
| D07 | HTTP trước, chưa streaming | Đầu ra kiểm tra xong mới gửi về client ở bước tích hợp sau |
| D08 | Truy xuất theo skill ID trước | Không gọi thao tác này là RAG vector hoặc KG đã hoàn thiện |

Số concept/module tối thiểu riêng của gate cần đối chiếu rubric chính thức nếu có. Ảnh thông báo hiện chỉ xác nhận: video 3 phút, sơ đồ, ≥10 PR merged, README và ≥5 test manual có output thật.

## 2. Lát cắt MVP G2 dự kiến

Hồ sơ demo → chọn chủ đề → nhận bài → nhập bước hoặc nghiệm → xác minh → gợi mở nếu cần → sửa bài → chọn bài tiếp → xem report. Có tạm dừng, tiếp tục và retry an toàn.

| Thành phần | Phần 1 hiện tại | Khi triển khai G2 |
|---|---|---|
| Nội dung | JSON và phiếu rà soát | Nội dung đã duyệt trong DB, chỉ trả đề và metadata public |
| Phiên học | Schema/contract | Tạo, đọc, cập nhật, pause/resume, finish |
| Toán | Kiểm tra offline bộ bài do nhóm soạn | Validator giới hạn, chấp nhận cách giải khác và abstain |
| BKT | Quy tắc evidence | Cập nhật xác định một lần, tham số/version và replay |
| OpenAI | Cấu hình mẫu, chưa có lệnh gọi | Benchmark/chọn model, kiểm tra phản hồi và fallback |
| LangGraph | Định nghĩa điểm lưu state và contract | Các node chạy thật cùng persistence/recovery |
| Frontend | Trang kiểm tra kết nối | Phiên học/hiển thị report thật |
| DB | PostgreSQL chạy local, health/readiness | Migration, seed versioned, uniqueness, transaction |

## 3. Ngoài phạm vi Phần 1

Không fit dataset, không benchmark KT, không sửa `data/`, không mở rộng 40 concept, không OCR/voice, không dashboard giáo viên, không bật Neo4j/pgvector, không viết quy tắc chấm dựa vào chuỗi cố định của prototype. Auth thật và kiểm soát quyền phải làm trước pilot/public deployment.

## 4. Phân công theo vai trò

| Vai trò trong brief | Đầu ra tiếp theo | Người review đề xuất |
|---|---|---|
| TV1 — Toán/BKT | Validator, eligibility, schema observation, test tính nhất quán | TV2 review nội dung, TV3 review API |
| TV2 — Nội dung/dữ liệu | Review 6 bài, registry, seed, evidence, tài liệu | TV1 review Toán, TV3 review tích hợp |
| TV3 — API/UI/Agent | Compose, API/session, UI, policy/LLM và tích hợp | TV1 review state, TV2 thử UI |

Tên và username thực tế chưa có; không tự gán danh tính hoặc mời collaborator. Nhánh hiện tại `tiendatv1`; thay đổi này có thể là một PR chuẩn bị có ý nghĩa, không tách giả tạo để đạt số PR.

## 5. Điều kiện chuyển bước

Phần 2 có thể bắt đầu khi contract và content fixtures đã qua check kỹ thuật. Chưa được coi bài là `human_approved` hoặc mở tutoring thật cho học sinh khi chưa review nội dung và chưa có validator. Các mục model/quota không chặn API tạo phiên/lấy đề, nhưng chặn tuyên bố gia sư OpenAI đã hoạt động.
