# Phần 3 — Bộ chấm Toán, BKT và gia sư Socratic

Đã nối bộ chấm phương trình bậc nhất, protocol observation, cập nhật BKT, LangGraph/checkpoint PostgreSQL, OpenAI và giao diện. Đây là **bản thử nội bộ**: bài/gợi ý vẫn `draft`, chưa có người duyệt chuyên môn; BKT dùng giả định khởi tạo của dự án, chưa fit hoặc hiệu chỉnh cho học sinh Việt Nam. Không xử lý các dataset trong `data/`.

## Chạy

Bật Docker Desktop. Từ thư mục gốc:

```powershell
docker compose up --build -d --wait --wait-timeout 180
```

Nếu BuildKit trên Windows báo lỗi đường dẫn có dấu, đặt `$env:COMPOSE_BAKE='false'` và `$env:DOCKER_BUILDKIT='0'` trong terminal rồi chạy lại. Service `init` tự chạy migration `002_tutor.sql`. Không xóa volume hay sửa migration `001` đã áp dụng.

Mở <http://localhost:3000>, chọn hồ sơ và **Bắt đầu phiên thử**. Các phiên Phần 2 giữ nguyên chế độ chỉ lưu trữ; cần phiên mới để dùng bộ chấm. Swagger: <http://localhost:8000/docs>.

| Biến server trong `.env` | Ý nghĩa |
|---|---|
| `DEMO_MODE=true` | Chỉ dùng chọn hồ sơ demo nội bộ, chưa phải đăng nhập sản phẩm |
| `TUTOR_ENABLED=true` | Phiên mới sử dụng pipeline Phần 3 |
| `LLM_ENABLED=true/false` | Bật/tắt gọi OpenAI; bộ chấm và BKT vẫn hoạt động khi tắt |
| `OPENAI_API_KEY` | Key giữ ở backend; không commit hoặc gửi frontend |
| `OPENAI_MODEL=gpt-4o-mini` | Giữ model đã cấu hình trong dự án; lượt live trả model snapshot trong evidence |
| `LLM_MAX_CALLS_PER_SESSION=8` | Chỉ 8 turn job đầu của phiên được phép đi vào bước gọi model; những lượt sau dùng template |
| `VALIDATOR_TIMEOUT_SECONDS=3` | Timeout subprocess gồm khởi động/import; code giới hạn cấu hình trong 0,05–3 giây |

Local đã bật tutor và OpenAI sau khi kiểm tra live thành công. `.env.example` vẫn để `LLM_ENABLED=false` để người clone chủ động bật. Mỗi yêu cầu model tối đa 320 output token, timeout HTTP 8 giây, không tự retry SDK. Đây là giới hạn từng phiên/request, không thay thế ngân sách tài khoản OpenAI; tạo phiên mới mở một hạn mức phiên mới.

## Thử một hành trình

1. Với bài đầu `3x + 5 = 20`, gửi `3x=15` rồi `x=5` trên hai dòng: được xác minh đúng.
2. Chuyển đến `LIN-003`, đề `2(x-3)=10`. Gửi `2x-3=10`, `2x=13`, `x=6.5`: sai đầu tiên ở bước 1, không tính các bước kéo theo thành ba lỗi.
3. Gia sư đưa câu hỏi gợi mở; mức hỗ trợ tăng. Nguồn phản hồi ghi rõ **OpenAI** hoặc **mẫu thử nghiệm**.
4. Sửa thành `x-3=5`, `x=8`: chấp nhận cách chia trước; lưu đúng sau hỗ trợ, không cộng observation thứ hai.
5. **Xin gợi ý** giữ nháp đang viết. Sau ba mức gợi ý, lượt cần giúp tiếp sẽ mời tạm dừng/đổi bài.
6. Kết thúc để xem kết quả độc lập/có hỗ trợ và số bằng chứng kỹ năng. Xác suất BKT chỉ lưu trong dữ liệu kỹ thuật, không hiển thị ở màn hình học sinh. Số bài đúng khác số observation; bài lặp có thể đúng nhưng không thêm bằng chứng BKT.

Mỗi lần gửi là toàn bộ bài giải hiện tại; khi sửa, thay bước sai trong ô nhập. Viết một phương trình mỗi dòng, dùng dấu chấm thập phân và ghi rõ phép nhân như `(1/2)*x`. Chỉ gửi `8` hoặc input mơ hồ sẽ được yêu cầu viết rõ, không chấm sai. Bài ngoài phạm vi có `reason_code=unsupported_scope`.

Nếu profile đã gặp các bài trong lần thử trước, số observation của phiên mới có thể bằng 0. Đây là bảo vệ protocol, không phải lỗi chấm. Tests và lượt live dùng schema/profile tổng hợp riêng để kiểm tra trường hợp độc lập mà không xóa lịch sử của bạn.

## Đọc code theo thứ tự

1. [Grammar](../phase1/INPUT_GRAMMAR.md) và [protocol](../phase1/OBSERVATION_PROTOCOL.md).
2. [math_validator.py](../../../../backend/app/math_validator.py): parser, tương đương phương trình, bước sai, worker timeout.
3. [knowledge.py](../../../../backend/app/knowledge.py), [tham số](../../../../content/bkt.bootstrap.v1.json): eligibility và công thức BKT.
4. [tutor.py](../../../../backend/app/tutor.py): graph, policy, gọi OpenAI và kiểm tra câu trả lời.
5. [checkpoints.py](../../../../backend/app/checkpoints.py): LangGraph checkpoint và pending writes trong PostgreSQL.
6. [tutor_service.py](../../../../backend/app/tutor_service.py): claim request, khôi phục graph, commit turn/observation/mastery nguyên tử.
7. [Migration 002](../../../../backend/migrations/002_tutor.sql), [sessions.py](../../../../backend/app/sessions.py): tích hợp với Phần 2 và báo cáo.
8. [workspace.tsx](../../../../frontend/app/workspace.tsx): nhận kết quả, gợi ý, lưu nháp và report.
9. [Kiến trúc](ARCHITECTURE.md), [kiểm tra](TESTING.md), [OpenAPI](../../../../contracts/phase3/openapi.json).

## Phạm vi chưa hoàn tất

- **Review chuyên môn:** chưa có người review thực tế. Không gán giả `human_approved` hay `reviewed_fallback`; dùng nguồn `draft_template`. Bước duyệt nội dung trong kế hoạch vẫn còn mở.
- **Ngôn ngữ tự do:** model chọn giữa các cách diễn đạt hữu hạn đã được code cho phép; không cho model tự viết phép biến đổi/lời giải. Đây là triển khai bảo thủ của bước diễn đạt, chưa phải đối thoại Socratic mở.
- Chưa có KG/Neo4j, vector RAG, nhiều concept, OCR, fit/benchmark dataset hay bằng chứng hiệu quả học tập.
- Chưa commit/push hoặc có CI remote cho thay đổi này. Code và evidence hiện ở workspace local.

Phiên bản này đủ để thử luồng kỹ thuật. Không coi việc có một lượt LLM thật hay BKT tăng là nghiệm thu chất lượng sư phạm hoặc hoàn thành toàn bộ PRD.
