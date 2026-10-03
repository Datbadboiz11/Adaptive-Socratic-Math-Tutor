# Kết quả kiểm tra local — 01/10/2026

Thực hiện trên nhánh `tiendatv1`, với Docker Compose PostgreSQL 17, backend FastAPI và frontend production build. Đây là kết quả của bản code trong workspace; không phải CI trên GitHub hoặc nghiệm thu chất lượng gia sư.

| Kiểm tra | Kết quả | Bằng chứng |
|---|---|---|
| Python/DB regression | 32 passed, 0 failed, 0 skipped; 1 cảnh báo deprecation Starlette/httpx | [JUnit](evidence/tests.xml) |
| Nội dung Phần 1 | 6 bài qua kiểm tra toán tác giả; cả 6 vẫn draft | `scripts/checks/check_phase1.py` |
| Contract | 13 schema mục tiêu và OpenAPI Phần 2 khớp code | `export_contracts.py --check`, `export_phase2_openapi.py --check` |
| Frontend | TypeScript và Next production build đạt | `npm run typecheck`, Docker build log |
| Liveness/readiness/web/OpenAPI | 4 kiểm tra đạt | [Smoke](evidence/smoke-ready.json) |
| Restart và DB outage | 3 kiểm tra đạt; DB được bật lại, không xóa volume | [Persistence](evidence/persistence-check.json) |
| Hành trình web và lỗi mạng | 6 nhóm kiểm tra đạt, không lỗi JavaScript runtime | [Browser](evidence/browser-check.json) |
| Tài liệu/repository | Relative links và file policy đạt, gồm file chưa tracked | `scripts/checks/check_repository.py --include-untracked` |

## Những tình huống đã thực sự thử

1. Tạo phiên, lưu nháp có khoảng trắng, pause, F5, mở phiên và resume: vẫn đúng bài và nháp.
2. Backend commit một bài nộp, trình duyệt không nhận response: nút retry gửi lại **cùng request ID và payload**, chỉ có một turn.
3. Tab khác lưu trước: tab đang viết nhận conflict; tải version mới vẫn giữ nháp local để người dùng lưu chủ động.
4. Restart backend: token, session và kết quả cached request vẫn đọc lại được từ DB.
5. Dừng DB: health/API trả 503. Bật DB và retry: lưu thành công đúng một lần.
6. Đổi bài, kết thúc, tải lại báo cáo: bài đã xem và lượt gửi khớp dữ liệu; không sinh observation/kết quả đúng giả.
7. Token demo ở cookie HttpOnly/SameSite Strict; trình duyệt JS không đọc được cookie; POST từ origin khác bị chặn.

## Ảnh giao diện

- [Phiên thử desktop 1440](evidence/session-1440.png)
- [Phiên thử tablet 768](evidence/session-768.png)
- [Phiên thử mobile 390](evidence/session-390.png)
- [Báo cáo mobile](evidence/report-mobile.png)

Đã kiểm tra không tràn ngang ở cả ba kích thước. Những phiên do script tạo được giữ trong lịch sử của hồ sơ demo; chúng là dữ liệu test có chủ đích.

## Chưa được chứng minh ở mốc này

- Độ đúng của bộ chấm bài học sinh, chất lượng gợi mở, gọi OpenAI và xử lý lỗi model.
- Eligibility, BKT, ghi observation/mastery và checkpoint LangGraph trong một luồng thật. Test constraint dùng fixture tổng hợp, không phải evidence học tập.
- Đăng nhập production, kiểm thử tải, duyệt chuyên môn bộ bài và ≥10 PR merged.

Các thay đổi đang ở workspace local; chưa commit/push trong lần triển khai Phần 2. CI đã được cập nhật cấu hình nhưng chưa có kết quả chạy remote cho thay đổi này.
