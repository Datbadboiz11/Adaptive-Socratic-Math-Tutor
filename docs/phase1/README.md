# Phần 1 — Bộ bàn giao chuẩn bị MVP

**Nhánh làm việc:** `tiendatv1` → PR về `main`.  
**Phạm vi thực hiện:** chuẩn bị nội dung, contract và nền tảng phát triển. Chưa triển khai phiên học, chấm bài, gia sư AI hoặc BKT online.  
**Dataset nghiên cứu:** không đọc, sửa hay tiền xử lý thư mục `data/`; không cần chờ bộ chưa được cấp quyền.

## 1. Đọc theo thứ tự

| Tài liệu | Dùng để quyết định/làm việc gì |
|---|---|
| [Phạm vi và quyết định](SCOPE.md) | G2 làm đến đâu, những gì chưa nằm trong phần này |
| [Bộ nội dung và phiếu review](CONTENT_REVIEW.md) | Rà 6 bài, đáp án, lỗi và gợi ý trước khi sử dụng với học sinh |
| [Hợp đồng dữ liệu/API](CONTRACTS.md) | Frontend và backend thống nhất payload, version và mã lỗi |
| [Grammar đầu vào](INPUT_GRAMMAR.md) | Các cách nhập được nhận, giới hạn và phân loại chưa xác minh |
| [Protocol observation](OBSERVATION_PROTOCOL.md) | Khi nào ghi bằng chứng BKT, khi nào chỉ ghi sự kiện |
| [Môi trường phát triển](DEVELOPMENT.md) | Chạy Next.js/FastAPI/PostgreSQL; các lệnh kiểm tra |
| [Bằng chứng kiểm tra](evidence/README.md) | Phân biệt kiểm tra đã chạy với checklist chưa duyệt |

## 2. Artifact có thể dùng ngay

- [Bộ 6 bài JSON](../../content/linear_equations.v1.json): nguồn nội dung phục vụ seed ở Phần 2, chưa nạp vào DB và chưa xuất cho học sinh.
- [Pydantic contracts](../../backend/app/contracts.py): nguồn chuẩn schema, có kiểm tra cấu trúc và một số ràng buộc giữa field.
- [JSON Schemas v1](../../contracts/v1/ProblemPublic.schema.json): được sinh lại từ Pydantic; không sửa tay.
- [Compose](../../compose.yaml), [mẫu môi trường](../../.env.example), backend health check và frontend Next.js: nền tảng chạy local.
- [Kiểm tra nội dung](../../scripts/check_phase1.py) và [tests](../../tests/test_phase1.py): xác minh nghiệm, bước biến đổi, ranh giới dữ liệu public/private và hành vi khi DB lỗi.

## 3. Trạng thái và điểm còn chờ

| Hạng mục | Trạng thái |
|---|---|
| Repository, nhánh làm việc, quy trình PR | Đã xác định; không tự merge `main` |
| PostgreSQL thay vì MySQL | Đã được người dùng chốt |
| OpenAI là nhà cung cấp API | Người dùng xác nhận đã có API; chưa kiểm tra key/quota |
| Scope, grammar, protocol và contract v1 | Đã chuẩn bị để nhóm dùng và review |
| Bộ 6 bài mẫu | Có mã kiểm tra toán; giữ trạng thái `draft` đến khi có người rà sư phạm |
| Môi trường local | Đã chạy Next.js/FastAPI/PostgreSQL; kiểm tra kết nối, DB lỗi và khởi động lại đạt; xem evidence |
| Model ID, ngân sách tiền và quyền model thực tế | Chờ nhóm chọn sau benchmark; không tự đoán hoặc gọi API tính phí |
| Rubric G2 ngoài ảnh thông báo | Chưa được cung cấp; chưa xác minh yêu cầu bổ sung về số concept/module |
| Tên/username và phân công cuối cùng của 3 người | Chờ nhóm; chỉ có phân công theo vai trò |
| Review chuyên môn độc lập | Chưa có chữ ký người review; kiểm tra bằng chương trình không thay thế mục này |

**Không đánh dấu “Phần 1 hoàn tất mọi điều kiện” khi các mục xác nhận trên còn chờ.** Các đầu ra kỹ thuật hiện có đủ để bắt đầu phần schema/API ở Phần 2; mở bài cho người học cần cổng review nội dung và validator thật.

Mở bản đang chạy tại <http://localhost:3000>. Các thay đổi Phần 1 được lưu trong working tree trên `tiendatv1`, chưa commit/push/merge. Bản prototype đầy đủ vẫn ở `design/index.html`; trang localhost hiện là khung sản phẩm đang xây dựng.

## 4. Bước tiếp nối cụ thể

1. Thành viên phụ trách nội dung rà [phiếu review](CONTENT_REVIEW.md), sửa hoặc xác nhận từng bài; lưu người duyệt và version thực tế.
2. Ở Phần 2, tạo migration cho registry/profile/session/opportunity và seed có version. Chưa tạo bảng session trong phần chuẩn bị này.
3. Tạo `POST /sessions` và `GET /sessions/{id}` theo contract; kiểm tra DB persistence và idempotency.
4. Nối frontend để hiển thị bài từ DB; chỉ mở họ bài đã qua validator và review.
5. Ở Phần 3, triển khai validator, observation, BKT và LangGraph/OpenAI; dùng bộ chuẩn bị này làm fixtures phát triển, không gọi là bộ test nghiên cứu độc lập.
