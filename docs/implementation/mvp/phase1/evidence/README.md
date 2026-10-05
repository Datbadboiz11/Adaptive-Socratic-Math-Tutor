# Evidence Phần 1

Thư mục này lưu kiểm tra nền tảng và nội dung, không phải kết quả đánh giá LLM/BKT hay ≥5 ca manual end-to-end của gate.

- [content-check.json](content-check.json): 6/6 bài qua kiểm tra nghiệm, các cách giải, bước lỗi và ví dụ khác.
- [tests.xml](tests.xml): 20 tests đạt, không fail/skip. Có cảnh báo deprecation của thư viện TestClient dùng httpx; không ảnh hưởng kết quả, cần theo dõi khi nâng dependency.
- [smoke-ready.json](smoke-ready.json): 4 kiểm tra live/readiness/frontend/OpenAPI đạt; đã chạy lại sau khi khởi động Docker sau lần gián đoạn.
- [smoke-db-down.json](smoke-db-down.json): DB bị dừng thì readiness trả 503, liveness vẫn 200 và frontend hiển thị mất kết nối. DB đã được khởi động lại sau thử nghiệm.
- [browser-check.json](browser-check.json): 3 kích thước 390/768/1440 px không tràn ngang, nút kiểm tra lại hoạt động, không có browser runtime errors.
- [verification.json](verification.json): chỉ mục kết quả và giới hạn kiểm chứng.
- [Ảnh desktop](foundation-1440.png), [tablet](foundation-768.png), [điện thoại](foundation-390.png): trang chuẩn bị môi trường, không phải phiên tutoring.

Kiểm tra tự động không thay review chuyên môn. `human_review=draft` có nghĩa bài chưa được người review duyệt, kể cả `math_check=pass`.

13 schema đã được kiểm tra đồng bộ với Pydantic; TypeScript check và Docker production build đã đạt trong quá trình triển khai. Kết quả này là kiểm tra local; workflow GitHub Actions mới được sửa trong working tree, chưa có kết quả remote cho thay đổi Phần 1 này.
