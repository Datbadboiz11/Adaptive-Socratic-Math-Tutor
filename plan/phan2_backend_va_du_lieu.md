# Phần 2 — Backend và lưu dữ liệu

**Trạng thái:** Chưa thực hiện.  
**Đầu vào:** Scope và contract phần 1.  
**Mục tiêu:** Mỗi hành động học có dữ liệu lưu được, đọc lại được và không ghi trùng khi thử lại.

## 1. Công việc theo thứ tự

- [ ] Dựng FastAPI, cấu hình môi trường, health check và kết nối PostgreSQL.
- [ ] Tạo migration cho profile demo, problem registry, session, opportunity, submission/turn, observation, mastery history và decision log.
- [ ] Tách đáp án/nội dung nội bộ khỏi schema trả cho frontend.
- [ ] Viết seed có thể chạy lại mà không nhân đôi ID/bản ghi.
- [ ] Tạo API dưới đây; đối chiếu tên cuối cùng với contract và OpenAPI.
- [ ] Gắn pipeline ở phần 3 vào submit, rồi hoàn thiện report/resume.

## 2. API đề xuất

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

- [ ] Tạo phiên, lấy bài và nộp bài được qua API.
- [ ] Khởi động lại backend vẫn đọc lại được phiên đã lưu.
- [ ] Gửi lại cùng request không tăng lượt/observation/mastery history.
- [ ] Thử hai request đồng thời: không nhân đôi observation hoặc ghi đè state âm thầm.
- [ ] Draft/resume và report khớp dữ liệu DB.
- [ ] Lỗi đầu vào/model/DB có mã lỗi và thông điệp phù hợp; log có request/session/opportunity ID.

**Bàn giao:** API chạy được, migration/seed, OpenAPI và kết quả kiểm tra cho phần 4.
