# Phần 2 — Backend và lưu dữ liệu

**Trạng thái:** Đã triển khai lớp lưu trữ và nối pipeline Phần 3 cho phiên mới. Xem [bàn giao Phần 2](../../implementation/mvp/phase2/README.md) và [cập nhật Phần 3](../../implementation/mvp/phase3/README.md).

**Đầu vào:** Scope và contract phần 1.  
**Mục tiêu:** Mỗi hành động học có dữ liệu lưu được, đọc lại được và không ghi trùng khi thử lại.

## 1. Công việc theo thứ tự

- [x] Dựng FastAPI, cấu hình môi trường, health check và kết nối PostgreSQL.
- [x] Tạo migration cho profile demo, problem registry, session, opportunity, submission/turn, observation, mastery history và decision log.
- [x] Tách đáp án/nội dung nội bộ khỏi schema trả cho frontend.
- [x] Viết seed có thể chạy lại mà không nhân đôi ID/bản ghi.
- [x] Tạo API dưới đây; đối chiếu tên cuối cùng với contract và OpenAPI.
- [x] Gắn pipeline ở phần 3 vào submit, rồi hoàn thiện report/resume cho chế độ thử nội bộ.

## 2. API đề xuất

API đã triển khai dùng prefix `/api/v1` (trừ health). Có thêm login/profile demo và lịch sử phiên. [`contracts/phase2/openapi.json`](../../../contracts/phase2/openapi.json) mô tả API thực tế. `/topics` hiện trả `tutoring_ready=false`, chỉ cho phép thử lưu nội bộ; submit chưa xác minh và không tạo observation. Quy định sư phạm của bảng dưới vẫn là đích sau Phần 3.

| Endpoint | Trách nhiệm |
|---|---|
| `GET /health` | Kiểm tra dịch vụ; DB readiness được biểu diễn rõ |
| `GET /topics` | Chủ đề thực sự có bài và validator hỗ trợ |
| `POST /sessions` | Tạo phiên với hồ sơ demo và chủ đề |
| `GET /sessions/{id}` | Đọc trạng thái phiên, bài hiện tại và phần hội thoại được phép hiển thị |
| `PUT /sessions/{id}/draft` | Lưu bản nháp có version; chưa chấm, chưa tạo observation |
| `POST /sessions/{id}/turns` | Nộp bài hoặc yêu cầu gợi ý với schema hành động rõ |
| `POST /sessions/{id}/pause` | Lưu trạng thái và đánh dấu tạm dừng |
| `POST /sessions/{id}/resume` | Tiếp tục opportunity hiện có |
| `POST /sessions/{id}/next` | Chọn bài tiếp, ghi quan hệ với bài trước, tạo opportunity phù hợp |
| `POST /sessions/{id}/finish` | Đóng phiên; gọi lại không tạo báo cáo trùng |
| `GET /sessions/{id}/report` | Tổng hợp bằng chứng từ DB |

## 3. Tính nhất quán bắt buộc

- `request_id` chống việc cùng request được xử lý thành nhiều lượt. Gửi lại cùng ID và cùng payload trả kết quả đã lưu; cùng ID khác payload báo xung đột.
- Unique constraint theo student/opportunity/skill bảo vệ observation chuẩn; application check đơn thuần chưa đủ.
- Transaction gắn observation, thay đổi mastery và dấu đã xử lý. Không ghi mastery trước rồi mất evidence log.
- State version ngăn hai request cùng sửa một phiên bằng dữ liệu cũ; request còn lại nhận trạng thái xung đột có thể phục hồi.
- Resume/reload không tạo opportunity mới, không tăng observation và không làm mất mức hỗ trợ.
- DB commit thành công nhưng response/checkpoint lỗi: replay phải nhận biết lượt đã commit. Lưu kết quả lượt làm nguồn đối soát; việc tính lại không được ghi thêm side effect.
- Lỗi model có thể dùng phản hồi fallback đã duyệt. Lỗi lưu trữ không được hiển thị như đã lưu thành công.

## 4. Report cần có

Đếm riêng số bài tự làm đúng, số bài đúng sau hỗ trợ và số observation đủ điều kiện. Số bài và số observation là hai đại lượng khác nhau. Ghi bài đã thử, hỗ trợ đã dùng, trạng thái tạm dừng/kết thúc và kỹ năng cần luyện tiếp dựa trên evidence.

Không lấy dữ liệu Minh Anh dựng sẵn trong `design/app.js` làm kết quả thật. Nếu hiển thị mastery, ghi rõ đây là ước lượng, evidence count và parameter version; trường hợp chưa có dữ liệu phải thể hiện đúng.

## 5. Điều kiện xong và cách kiểm tra

- [x] Tạo phiên, lấy bài và nộp bài được qua API (lưu bài, chưa chấm).
- [x] Khởi động lại backend vẫn đọc lại được phiên đã lưu (đã chạy restart container thực tế).
- [x] Gửi lại cùng request không tăng lượt/observation/mastery history.
- [x] Thử hai request đồng thời: không ghi đè state âm thầm; unique observation và rollback history được kiểm tra bằng fixture constraint riêng. BKT thực tế còn chờ Phần 3.
- [x] Draft/resume và report khớp dữ liệu DB; đã thử trên web và sau reload.
- [x] Lỗi đầu vào/DB có mã lỗi và thông điệp phù hợp; log turn có request/session/opportunity ID. Đã thử DB ngừng hoạt động và phục hồi.
- [x] Đã nối model/checkpoint; có test lỗi model, phục hồi sau node model và lượt OpenAI thật ở Phần 3.

**Bàn giao:** API chạy được, migration/seed, OpenAPI và kết quả kiểm tra cho phần 4.

**Cập nhật Phần 3:** runtime đã ghi observation/mastery trong cùng transaction; có test rollback, checkpoint và BKT giữa hai phiên. Các mô tả API “chỉ lưu/chưa chấm” bên trên là mốc Phần 2; API hiện hành xem OpenAPI Phần 3. Sáu bài vẫn draft; chưa nghiệm thu sư phạm.
