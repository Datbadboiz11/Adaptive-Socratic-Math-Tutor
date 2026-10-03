# Phần 4 — Frontend và tích hợp

**Trạng thái:** Đã triển khai frontend tích hợp và build đạt; nghiệm thu browser trên bản frontend mới còn chờ quyền truy cập. Xem [bàn giao Phần 4](../docs/phase4/README.md).
**Đầu vào:** Prototype `design/`, contract phần 1 và API phần 2–3.  
**Mục tiêu:** Người dùng đi hết một phiên học bằng UI và backend thật.

## 1. Tái sử dụng thiết kế

Giữ hướng xanh ngọc–kem, bố cục và nội dung phù hợp từ prototype. Chuyển thành component trong frontend sản phẩm theo stack PRD; giữ `design/` làm bản tham chiếu.

- [x] App shell, danh sách chủ đề từ API, bài làm, tutor panel và report từ server.
- [x] Hiển thị phương trình trong phạm vi hỗ trợ, trạng thái nút, Ctrl+Enter, focus phản hồi và bố cục điện thoại; còn cần nghiệm thu browser trên bản build mới.
- [x] Luồng sản phẩm không có thanh Wireframe/Luồng/Kịch bản; prototype `design/` giữ riêng.
- [x] Bài, phản hồi và số liệu lịch sử dùng API; không đưa `classify()` từ `design/app.js` vào sản phẩm.

## 2. Ưu tiên màn hình

| Màn hình | Phạm vi G2 |
|---|---|
| Hồ sơ/tổng quan | Chọn hồ sơ demo được cấp, bắt đầu hoặc tiếp tục phiên; dữ liệu thật của phiên thử |
| Chủ đề | Một chủ đề mở được, không tạo cảm giác các chủ đề chưa hỗ trợ đã hoạt động |
| Phiên học | Đề, nhập bước, gửi, nhận câu hỏi, gợi ý, bài mới, tạm dừng/kết thúc |
| Report | Tự làm đúng/có hỗ trợ, observation và lịch sử từ backend |
| Tiến trình nâng cao | Hoãn nếu chưa có đủ evidence và API |

## 3. Hợp đồng tương tác

- Gửi bài: giữ draft, tạo `request_id` cho hành động, khóa gửi trùng trong lúc chờ.
- Mạng lỗi: giữ input; thử lại cùng hành động dùng lại ID. Nội dung sửa thành hành động mới có ID mới.
- Server báo xung đột state: tải trạng thái mới và hướng dẫn người dùng; không tự ghi đè bài nháp.
- Loading phải có trạng thái kết thúc/fallback; không treo vô hạn.
- Phân biệt lỗi mạng với `unverified`: một bên là request không hoàn tất, một bên là kết quả xác minh chưa đủ bằng chứng.
- Lưu draft có version, flush trước pause/navigation và hiển thị đang lưu/đã lưu/lưu lỗi. Draft không gọi luồng chấm bài.
- Báo “đã lưu” khi backend xác nhận; localStorage chỉ là bản dự phòng nháp nếu cần.
- Tải lại trang lấy session thật từ server; không tự tạo opportunity mới.
- Khi finish, report lấy dữ liệu server, không tự tăng số liệu cho đẹp.

## 4. Buổi kiểm tra tích hợp

1. Khởi động frontend, backend và DB từ hướng dẫn.
2. Tạo phiên mới → nhập bước sai → nhận câu hỏi gợi mở thật.
3. Sửa đúng → xác nhận kết quả có hỗ trợ.
4. Chọn bài mới → tự làm; kiểm tra tính đủ điều kiện observation theo protocol.
5. Kết thúc → report khớp evidence; mở lại history đúng phiên.
6. Thử tạm dừng, reload, timeout và retry; kiểm tra UI lẫn DB.

## 5. Điều kiện xong

- [x] Không có bước nào trong hành trình chính phải thao tác DB thủ công để tiếp tục.
- [x] Bài, phản hồi và report đều từ API; dữ liệu demo được gắn nhãn trung thực.
- [ ] Chạy lại hành trình draft, retry, hỗ trợ và resume trên bản frontend Phần 4 sau build.
- [ ] Chụp lại và kiểm tra bản frontend Phần 4 tại 390px và 1440px; ảnh Phần 3 là bản trước thay đổi.
- [ ] Kiểm tra UI bản mới không lộ đáp án từ payload, API key hoặc lỗi nội bộ thô trong browser.

**Bàn giao:** Bản chạy end-to-end cho [phần 5](phan5_kiem_thu_va_bang_chung.md).
