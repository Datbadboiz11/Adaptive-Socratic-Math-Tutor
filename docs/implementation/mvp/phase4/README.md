# Bàn giao Phần 4 — frontend tích hợp

Frontend sản phẩm nằm trong `frontend/`, dùng Next.js và API phiên học từ Phần 2–3. `design/` vẫn là prototype riêng. Phần 4 đã build và typecheck đạt; nghiệm thu browser trên chính build này chưa hoàn tất.

## Luồng đã triển khai

- Chọn hồ sơ demo và một chủ đề **thực sự có bài** từ `/api/topics`; chủ đề chưa hỗ trợ không được chọn. `tutoring_ready=false` được trình bày thành nội dung thử nội bộ đang chờ duyệt.
- Bắt đầu/mở lại phiên, viết phương trình mỗi dòng, lưu nháp, gửi bằng nút hoặc Ctrl+Enter, xin gợi ý, tạm dừng/tiếp tục, đổi bài và xem report. Đề, phản hồi và số liệu lấy từ API.
- Phản hồi mới xuất hiện trong vùng gia sư có `aria-live` và nhận focus sau khi gửi. Bài chưa xác minh được phân biệt với lỗi mạng. Khi mạng gián đoạn, yêu cầu giữ `request_id` để thử lại; người dùng cũng có thể tải trạng thái server để sửa bài và gửi một yêu cầu mới.
- Nháp đang sửa được lưu trên server trước khi đổi hồ sơ, đổi phiên, tạo phiên mới, xin gợi ý, tạm dừng, đổi bài hoặc kết thúc. Nếu lưu thất bại, hành động tiếp theo dừng và hiện lỗi để thử lại. Báo “đã lưu” chỉ sau response server.
- Report hiển thị số bài tự làm, đúng sau hỗ trợ, chưa xác minh và observation. Chỉ báo số bằng chứng kỹ năng; không đưa xác suất BKT thô vào màn hình học sinh. Nội dung demo và giới hạn chuyên môn có nhãn rõ.

## Chạy và kiểm tra

Với backend/PostgreSQL đang ở cổng 8000/5433, từ `frontend/`:

```powershell
npm run typecheck
npm run build
npm run start -- --port 3001
```

Mở <http://localhost:3001>. Bản build cục bộ đã đạt; frontend Docker ở cổng 3000 cần được build lại trước khi so sánh giao diện mới. Trong phiên này, tài khoản công cụ bị từ chối truy cập Docker pipe, nên chưa thay image cổng 3000. Giữ DB volume và dữ liệu demo; không cần import dataset ngoài.

Các file chính: [workspace.tsx](../../../../frontend/app/workspace.tsx), [workspace.css](../../../../frontend/app/workspace.css), [BFF](../../../../frontend/app/api/[...path]/route.ts). Phần 5 lưu [bằng chứng kỹ thuật và trạng thái manual](../phase5/README.md).

## Giới hạn còn lại

Ảnh và kiểm tra browser của Phần 3 là bản frontend cũ. Browser của Codex đã từ chối quyền truy cập `localhost:3001`; vì thế chưa có ảnh mới ở 390/1440px hoặc kiểm tra thực hành bàn phím/focus trên build này. Chưa có đăng nhập sản phẩm, duyệt chuyên môn nội dung hoặc kiểm chứng sư phạm với học sinh.
