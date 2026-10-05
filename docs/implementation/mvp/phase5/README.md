# Bằng chứng Phần 5

Ngày 02/10/2026 (giờ Việt Nam), nhánh `tiendatv1`, working tree chưa commit theo `AGENTS.md`.

| Loại | Kết quả | Bằng chứng |
|---|---|---|
| Frontend Phần 4 | `npm run typecheck` và `npm run build` đạt | [Bàn giao](../phase4/README.md) |
| API/DB | 7 ca đạt trong schema PostgreSQL riêng, không gọi OpenAI | [api-checks.json](api-checks.json), [script](../../../../scripts/checks/check_phase5_api.py) |
| Browser cũ Phần 3 | 6 nhóm kiểm tra, không lỗi JS; trước thay đổi UI Phần 4 | [browser-check.json](../phase3/evidence/browser-check.json) |
| Manual UI trên build Phần 4 | **NOT RUN** | [Phiếu ca](manual-tests.md) |

API/DB test là phép kiểm tra kỹ thuật với học sinh tổng hợp; mỗi lượt tạo schema riêng và chỉ ghi số liệu đã lược bỏ token. Không coi đây là 7 ca manual qua UI. Lượt browser Phần 3 cũng không được nhận là ảnh mới của Phần 4.

Công cụ browser của Codex báo từ chối quyền mở `http://127.0.0.1:3001`, vì vậy không thử qua trình duyệt khác để lách. Khi quyền được cấp lại, chạy `manual-tests.md` trên build Phần 4, lưu ảnh/response và cập nhật actual/pass/fail. Trước khi nộp, bằng chứng phải khớp commit được nhóm tạo và review theo quy trình; lần này không có commit.
