# Kiểm tra Phần 2

## Bộ kiểm tra tự động

Cài backend dev dependencies theo Phần 1 và bật DB bằng Compose. Chạy từ thư mục gốc:

```powershell
.\.venv\Scripts\python.exe scripts/check_phase1.py
.\.venv\Scripts\python.exe scripts/export_contracts.py --check
.\.venv\Scripts\python.exe scripts/export_phase2_openapi.py --check
.\.venv\Scripts\python.exe scripts/test_phase2_local.py
.\.venv\Scripts\python.exe scripts/smoke_foundation.py
```

Runner local đọc cấu hình DB từ `.env`, kết nối cổng local đã cấu hình, không in password. Integration tests tạo schema `test_phase2_<UUID>`, migration/seed trong đó, rồi dọn đúng schema vừa tạo. Không chạy test trên DB production. Hiện gồm 20 tests Phần 1 và 12 tests Phần 2. Một cảnh báo deprecation của Starlette/httpx không làm test thất bại.

Các test Phần 2: migration/seed lặp; nội dung đổi cùng version; response không lộ lời giải; create retry; draft giữ khoảng trắng; pause/resume giữ opportunity; submit/hint/report không tạo kết quả học tập giả; đồng thời cùng request; đồng thời khác request cùng version; quyền theo profile; hết bài/phiên đóng; rollback rồi retry; unique observation + rollback cả history; input sai và demo disabled.

CI đã bổ sung service PostgreSQL 17 và chạy toàn bộ suite; kết quả CI trên GitHub chỉ có sau khi push, không suy ra từ lần chạy local.

## Kiểm tra restart và DB tạm ngừng

```powershell
.\.venv\Scripts\python.exe scripts/check_phase2_persistence.py --exercise-recovery
```

Script tạo một phiên demo mới, restart backend, xác nhận state và response cache còn nguyên; tạm dừng DB, kiểm tra lỗi 503, bật lại DB trong `finally`, retry cùng request và đối chiếu report. Chỉ chạy lúc không có người khác thao tác trên ứng dụng local. Volume DB được giữ lại. Nếu không muốn gián đoạn container, bỏ `--exercise-recovery`; khi đó không kiểm tra restart/outage.

## Kiểm tra trình duyệt

Cần Python có Playwright và Chromium (cài trong môi trường riêng hoặc `.venv` theo README). Với Compose đang chạy:

```powershell
python scripts/check_phase2_browser.py
```

Script tạo một phiên demo mới qua web, kiểm tra lưu trước pause, reload/resume, mô phỏng mất response **sau khi backend commit**, retry không nhân đôi turn, xung đột do tab khác sửa và giữ nháp của tab hiện tại, đổi bài, report sau reload, cookie HttpOnly, từ chối POST khác origin và ba kích thước 1440/768/390. Bản nháp test không phải kết quả học sinh thật. Các phiên kiểm tra được giữ lại trong lịch sử để đối chiếu.

## Evidence

Lượt kiểm tra local ngày 01/10/2026: **32/32 pytest đạt**, frontend typecheck và production build đạt; **3 kiểm tra persistence/recovery** và **6 nhóm kiểm tra trình duyệt** đạt. Có kiểm tra trực quan ảnh desktop và report mobile. DB/backend/frontend đã được đưa về trạng thái healthy sau bài kiểm tra DB outage. Xem [kết quả chi tiết](CHECK_RESULTS.md).

Kết quả được sinh khi chạy test, nằm tại `docs/phase2/evidence/`:

- `tests.xml`: kết quả pytest, số lượng pass/fail.
- `smoke-ready.json`: health, frontend và OpenAPI.
- `persistence-check.json`: restart/outage/retry và report thực tế; không chứa token.
- `browser-check.json`: các bước web đã đạt, session ID và lỗi JavaScript.
- `session-1440.png`, `session-768.png`, `session-390.png`, `report-mobile.png`: giao diện thực tế.

Các file này là bằng chứng lưu trữ. Chưa phải đánh giá chất lượng Toán, Socratic, OpenAI, BKT hay toàn bộ nghiệm thu G2. Phải chạy bổ sung sau tích hợp Phần 3.

## Năm kịch bản tự kiểm tra

| Ca | Thao tác | Kết quả mong đợi |
|---|---|---|
| 1 | Viết nháp → lưu → pause → F5 → mở phiên → resume | Nội dung/opportunity không đổi, observation vẫn 0 |
| 2 | Nộp `x=5` | Có turn đã lưu, trạng thái chưa xác minh, không báo đúng giả |
| 3 | Gửi lại cùng request ID/body qua API | Response giống lần đầu, không tăng lượt |
| 4 | Hai tab mở cùng version; tab A lưu rồi tab B lưu | Tab B nhận conflict; tải state mới giữ nháp để lưu chủ động |
| 5 | Next → finish → F5 → mở phiên đã đóng | Report đọc lại từ DB, không cộng observation khi xem lại |

Để xem DB bằng VS Code/pgAdmin: host `127.0.0.1`, port theo `POSTGRES_PORT` (mặc định 5433), database/user/password theo `.env`. Không cần công cụ này để sử dụng hoặc seed ứng dụng. Có thể đọc `sessions`, `opportunities`, `turns`, `requests`; không chỉnh tay record khi ứng dụng đang chạy.
