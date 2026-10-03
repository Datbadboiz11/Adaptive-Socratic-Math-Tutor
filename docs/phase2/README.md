# Phần 2 — Backend và lưu phiên

> Đây là tài liệu mốc Phần 2. Ứng dụng hiện đã có [Phần 3](../phase3/README.md); các phiên cũ vẫn chỉ lưu trữ, phiên mới có thể bật tutor. Evidence dưới đây giữ nguyên để đối chiếu lịch sử.

Phần này triển khai PostgreSQL, migration/seed, API phiên học và một màn hình thử nối API thật. Chưa nối validator, BKT hoặc OpenAI; nhánh tích hợp đó được làm ở Phần 3. Sáu bài mẫu giữ trạng thái **draft**, chỉ dùng thử nội bộ. Dataset trong `data/` không bị sửa hoặc import.

## Chạy và thử ngay

Mở PowerShell tại thư mục gốc dự án. Bật Docker Desktop, bảo đảm `.env` có `DEMO_MODE=true`, rồi chạy:

```powershell
docker compose up --build -d --wait --wait-timeout 180
```

Nếu chưa có `.env`: `Copy-Item .env.example .env`. Không ghi đè file cấu hình đã có. Không cần mở pgAdmin/extension để nạp bài: service `init` tự migration và seed trước khi backend chạy. `init` kết thúc với mã 0 là bình thường.

Máy Windows dùng đường dẫn có dấu có thể gặp lỗi BuildKit `x-docker-expose-session-sharedkey ... non-printable ASCII`. Trong cùng terminal, dùng:

```powershell
$env:COMPOSE_BAKE='false'
$env:DOCKER_BUILDKIT='0'
docker compose up --build -d --wait --wait-timeout 180
```

Đây là cách tương thích đã dùng khi kiểm tra trên máy này. Các biến chỉ tác động terminal hiện tại.

1. Mở <http://localhost:3000>, chọn **Minh Anh** hoặc **Gia Huy**.
2. Chọn **Bắt đầu phiên thử**. Đề đầu tiên: `3x + 5 = 20`.
3. Viết `3x = 15` và `x = 5` trên hai dòng; chọn **Lưu nháp**.
4. **Tạm dừng**, tải lại trang, mở phiên trong danh sách **Các phiên đã lưu**, rồi **Tiếp tục phiên**.
5. Chọn **Gửi bài để lưu**: nhật ký ghi bài đã lưu, chưa xác minh đúng/sai.
6. **Thử bài tiếp**, sau đó **Kết thúc & xem báo cáo**. Lượt gửi là số thật từ DB; số đúng/observation vẫn 0 vì chưa có bộ chấm. Không diễn giải 0 là học sinh sai.

Bản nháp lưu khi nhấn **Lưu nháp**, hoặc trước thao tác tạm dừng/đổi bài/kết thúc. Chưa có autosave. Giao diện cảnh báo trước khi rời bản nháp chưa lưu. Khi mất mạng, giữ nguyên trang và dùng **Thử lại yêu cầu**; cùng request ID được gửi lại để tránh ghi trùng. Không lưu bản nháp vào localStorage.

## Đã có và giới hạn

| Hạng mục | Hiện trạng |
|---|---|
| DB | Profile demo, token demo, topic, problem, session, opportunity, turn, observation, mastery history, decision, request cache và migration ledger |
| Seed | 2 profile, 1 topic, 6 bài mẫu; chạy lại không nhân đôi; sửa cùng content version bị từ chối |
| API | Tạo/đọc/liệt kê phiên, lưu nháp, nộp bài, ghi yêu cầu gợi ý, pause/resume/next/finish/report |
| Nhất quán | Transaction, request replay, payload hash, session version, khóa đồng thời và ràng buộc observation duy nhất |
| Web | UI dùng API thật, lịch sử DB, xử lý retry/conflict và báo cáo; responsive |
| Xác thực | Chọn profile demo và token 24 giờ. **Không phải đăng nhập người dùng thật**: ai dùng demo cũng có thể chọn một profile được công bố |
| Nội dung | Đáp án/lời giải/hint lưu riêng; API public không trả chúng. Nội dung chưa được người có chuyên môn duyệt |
| AI / BKT | Chưa gọi model, chưa chấm, chưa tạo observation/mastery từ bài làm. Schema và transaction boundary sẵn cho tích hợp |

Tất cả cổng Compose chỉ bind `127.0.0.1`. Không dùng chế độ demo để triển khai công khai. Khi `DEMO_MODE=false`, toàn bộ API phiên/demo bị đóng (403); health vẫn hoạt động.

## Đọc tài liệu/code theo thứ tự

1. [Kiến trúc và dữ liệu](ARCHITECTURE.md): đường đi của một request và bảng DB.
2. [Migration](../../backend/migrations/001_sessions.sql): khóa, constraint, quan hệ.
3. [Migration/seed runner](../../backend/app/manage.py): kiểm tra checksum và nạp nội dung.
4. [Schema API](../../backend/app/session_contracts.py) và [OpenAPI đã xuất](../../contracts/phase2/openapi.json): dữ liệu thực tế của Phần 2.
5. [Session service](../../backend/app/sessions.py): đọc `mutation`, `locked`, `view`, rồi từng endpoint.
6. [FastAPI app](../../backend/app/main.py): health, exception, trace ID.
7. [Proxy frontend](../../frontend/app/api/%5B...path%5D/route.ts), [workspace](../../frontend/app/workspace.tsx): cookie demo, thao tác UI, retry/conflict.
8. [Hướng dẫn kiểm tra](TESTING.md), [test tích hợp](../../tests/test_phase2.py).

Swagger chạy tại <http://localhost:8000/docs>. Để thử API bằng Swagger: gọi `/api/v1/demo/login`, lấy `access_token`, truyền `Bearer <token>` vào header `authorization` của endpoint cần thử. Token demo khác OpenAI API key; không commit cả hai.

[Bàn giao Phần 1](../phase1/README.md) mô tả mốc trước khi có lưu phiên. Evidence Phần 1 là lịch sử; trạng thái ứng dụng mới nhất nằm tại đây. Không tự coi Phần 2 là hoàn thành MVP hoặc hoàn thành toàn bộ P0 của PRD.

**Bước kế tiếp:** [Phần 3](../../plan/phan3_gia_su_socratic.md): validator → xác định evidence hợp lệ → BKT → policy/gia sư → ghi kết quả trong transaction, rồi nghiệm thu lại submit/report.
