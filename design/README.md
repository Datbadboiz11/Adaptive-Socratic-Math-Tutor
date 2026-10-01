# Mở — Wireframe, UI & user flows

Bản thiết kế tương tác cho **Adaptive Socratic Math Tutor / VIN-02**, dựa trên PRD 0.2 và brief của dự án. Hướng thẩm mỹ đã chọn: **sáng, xanh ngọc, nền kem, nhẹ nhàng và hiện đại**.

## Mở bản thiết kế

**Cách nhanh nhất:** mở [index.html](index.html) bằng Chrome hoặc Edge. Không cần cài thư viện, đăng nhập dịch vụ hay chạy backend. Các file `index.html`, `styles.css`, `app.js` phải ở cùng thư mục.

Hoặc phục vụ bằng HTTP từ thư mục `design`:

```powershell
python -m http.server 8765 --bind 127.0.0.1
```

Mở `http://127.0.0.1:8765`. Dữ liệu ở file:// và localhost là hai vùng lưu riêng của trình duyệt.

## Có gì trong bản bàn giao?

| Thành phần | Cách xem |
|---|---|
| 6 màn hình chính | Tổng quan, Chủ đề, Phiên học, Report, Tiến trình/Lịch sử; Đăng nhập ở thanh dưới |
| Bản đồ user flow | Bấm **Luồng** ở thanh dưới; mỗi nút mở màn hình/trạng thái tương ứng |
| Wireframe | Bấm **Wireframe** để chuyển sang bản đơn sắc, giữ nguyên bố cục và tương tác |
| Kịch bản ngoại lệ | Bấm **Kịch bản** → chọn input chưa rõ, chưa xác minh, mất kết nối, mắc kẹt… |
| Người mới / người quay lại | **Kịch bản** → chọn hồ sơ mới hoặc Minh Anh |
| Ảnh màn hình | Thư mục [previews](previews/) |
| Quy tắc thiết kế | [DESIGN_SPEC.md](DESIGN_SPEC.md) |
| Đặc tả luồng | [USER_FLOWS.md](USER_FLOWS.md) |
| Kiểm tra đã chạy | [previews/qa-results.json](previews/qa-results.json) |

Thanh **MỞ / DESIGN 01** và bàn điều khiển kịch bản là lớp trình diễn dành cho nhóm review; không đưa vào sản phẩm học sinh khi triển khai.

## Demo luồng chính trong 2 phút

1. Chọn **Kịch bản → Bắt đầu bài** để bắt đầu sạch.
2. Nhập bài làm dưới đây rồi bấm **Gửi bài làm**:

```text
2x - 3 = 10
2x = 13
x = 6.5
```

3. Mở gợi ý kiểm tra bước phân phối. Thử **Em cần gợi ý** hoặc **Cùng xem một ví dụ khác**.
4. Sửa bài thành:

```text
2x - 6 = 10
2x = 16
x = 8
```

5. Kết quả hiển thị **Đúng sau hỗ trợ**. Số lần quan sát không tăng do lượt sửa này.
6. Bấm **Thử một bài mới**. Với `3(x + 2) = 21`, nhập:

```text
3x + 6 = 21
3x = 15
x = 5
```

7. Bấm **Nhìn lại phiên học**: report tách 1 bài tự làm đúng, 1 bài đúng sau hỗ trợ và 2 lần quan sát.
8. Thử luồng khác: đang viết bài → **Tạm dừng** → tải lại trang → **Tiếp tục phiên**. Bài làm vẫn còn.

Các đáp án trên dành cho người kiểm thử bản thiết kế; giao diện gia sư không tự đưa nghiệm cho học sinh.

## Phạm vi của prototype

- Đây là **UI prototype có kịch bản cố định**, không phải hệ thống chấm Toán, LLM hoặc BKT thực tế.
- Có 6 chủ đề minh họa được nối tương tác, mỗi chủ đề có bài đầu và một bài mới. Bản này không tuyên bố đã hoàn tất phạm vi 40 concept của sản phẩm.
- Cách viết nhận diện được giới hạn theo kịch bản. Cách giải khác sẽ có thể chuyển sang **Chưa xác minh**, không chứng minh cách giải đó sai.
- “Đăng nhập” là trải nghiệm chọn tên gọi/hồ sơ giả. Không có tài khoản, mật khẩu hoặc xác thực thật; không nhập dữ liệu nhạy cảm.
- Các bộ đếm trong phiên minh họa quy tắc observation. Không tính hay tuyên bố mastery BKT đã hiệu chỉnh. Dữ liệu lịch sử ban đầu của Minh Anh là minh họa.
- Bản mẫu lưu dữ liệu trong localStorage, chỉ trên trình duyệt/thiết bị hiện tại. Đổi trình duyệt, đổi origin hoặc xóa dữ liệu trình duyệt có thể mất phiên. Không phải persistence nhiều thiết bị.
- Kịch bản tình huống thay thế phiên hiện tại; nút **Đặt lại** chỉ đặt lại khóa dữ liệu của prototype này.
- Font web là tùy chọn; khi không tải được có font hệ thống dự phòng. Không có ảnh hoặc thư viện JavaScript bên ngoài bắt buộc để ứng dụng hoạt động.

## Bàn giao cho frontend

1. Giữ cấu trúc màn hình, component và trạng thái ở tài liệu thiết kế.
2. Thay bộ state local/scripted bằng contracts và API trong PRD; không tái sử dụng `classify()` như mathematical validator.
3. Tách lớp trình diễn (`prototype-bar`, drawer kịch bản, preset) khỏi sản phẩm.
4. Thay hồ sơ giả, các ghi nhận lịch sử và bộ đếm minh họa bằng dữ liệu thật đã kiểm chứng.
5. Chốt thiết kế xác thực thật, cold start, ngưỡng policy và giới hạn dữ liệu trước pilot người dùng.

## Kiểm tra giao diện

`audit_ui.py` chạy bằng Playwright + Chromium. Nó kiểm tra hành trình chính, topic filter/search, hỗ trợ không cộng observation, report, pause/resume, retry và overflow; xuất screenshots và kết quả JSON. Đây là acceptance check của prototype, không đánh giá mô hình dạy học.

```powershell
# Sau khi bật HTTP server ở trên, dùng môi trường Python có Playwright:
python audit_ui.py
```

Môi trường dựng bản mẫu đã có sẵn Playwright; không cần cài thêm gì để **xem** bản thiết kế.
