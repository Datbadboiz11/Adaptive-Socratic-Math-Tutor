# Kiểm tra và evidence Phần 3

Kết quả đã lưu ngày 01/10/2026: [JUnit](evidence/tests.xml) ghi **72 test đạt, 0 lỗi, 0 bỏ qua**; [browser check](evidence/browser-check.json) ghi **6 kiểm tra đạt, 6 lượt tutor, 0 lỗi JavaScript**. Hành trình web tạo 5 lượt gửi bài, trong đó 1 lượt đúng độc lập, 2 bài đúng sau hỗ trợ, 1 lượt chưa xác minh và 1 observation hợp lệ. [Lượt OpenAI thật](evidence/live-openai.json) trả kết quả từ `gpt-4o-mini-2024-07-18`. Đây là các kết quả của lần chạy đã lưu, không thay thế kiểm thử lại sau thay đổi mã.

## Regression (không tốn API)

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pip install -r backend/requirements-dev.txt
docker compose up -d --wait db
.\.venv\Scripts\python.exe -X utf8 scripts/dev/test_phase3_local.py
.\.venv\Scripts\python.exe -X utf8 scripts/exports/export_contracts.py --check
.\.venv\Scripts\python.exe -X utf8 scripts/exports/export_phase3_openapi.py --check
.\.venv\Scripts\python.exe -X utf8 scripts/checks/check_repository.py --include-untracked
.\.venv\Scripts\python.exe -X utf8 scripts/checks/smoke_foundation.py
```

Runner ép `LLM_ENABLED=false`; test timeout dùng stub không thực hiện HTTP. DB tests dùng schema UUID riêng, xóa đúng schema test khi xong, giữ nguyên dữ liệu demo. CI dùng PostgreSQL 17 và kiểm tra OpenAPI Phần 3; OpenAPI Phần 2 giữ làm bản lịch sử.

| Nhóm | Các tình huống |
|---|---|
| Toán | Hai cách giải mỗi bài; bước sai đầu tiên; lỗi kéo theo; nghiệm sai đơn lẻ; phân số/thập phân; đảo hai vế; phương trình hằng; input mơ hồ/ngoài phạm vi; injection; giới hạn độ sâu/node; worker bị hủy; phương trình ngoài 6 fixture tác giả |
| BKT | Công thức tính tay; replay chuỗi; eligibility đúng thứ tự; không cập nhật từ partial/unclear/hint/repeat/near practice |
| Tích hợp | Atomic observation/history/state; rollback sau BKT; hai phiên cập nhật cùng skill; same-key retry; checkpoint phục hồi sau node model; budget/fallback; báo cáo đúng sau hỗ trợ |
| Kế thừa | Toàn bộ tests Phần 1 và storage-only của Phần 2 vẫn chạy |

## Một lượt OpenAI thật

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/checks/check_phase3_live.py --live-openai
```

Lệnh này **có thể tính phí API** và được tách khỏi CI/regression. Đọc key/model từ `.env`, tạo schema tổng hợp tạm, thực hiện một turn với tối đa 320 output token, rồi replay cùng request để đối chiếu. Không in key/token. Schema test được dọn trong `finally`; kết quả public được ghi trong [live-openai.json](evidence/live-openai.json).

Lượt đã kiểm chứng: `gpt-4o-mini-2024-07-18`, input 362 token, output 22 token (tổng 384). Bài `2(x-3)=10`, sai ở bước 1; phản hồi không đưa nghiệm và replay khớp kết quả đã lưu. Đây là bằng chứng kết nối và luồng, không phải benchmark lựa chọn model. Có một lượt thử trước đó không đạt assertion bước 1 khi chạy đồng thời nhiều kiểm tra; không có output đầy đủ để chẩn đoán chắc chắn và không dùng lượt đó làm bằng chứng đạt. Lượt chạy lại được lưu đầy đủ.

## Browser

Cần môi trường Python có Playwright/Chromium. Với Compose đã chạy:

```powershell
python scripts/checks/check_phase3_browser.py
```

Script dùng profile demo Gia Huy và giữ phiên test trong lịch sử. Nếu local bật OpenAI, tối đa 6 lượt của hành trình có thể gọi model. Kiểm tra draft/pause/reload; mất response sau commit; unclear; xin hint giữ nháp; sửa đúng sau hỗ trợ; bước sai phân phối; cách giải khác; report; 3 viewport. Không mở script Phase 2 với tutor mới rồi coi expectation “chưa chấm” là kết quả hiện tại.

## Evidence được sinh

- `docs/implementation/mvp/phase3/evidence/tests.xml`: pytest thật, số pass/fail/skipped.
- `docs/implementation/mvp/phase3/evidence/live-openai.json`: input, model/source/usage, assessment và response công khai của ca live; không chứa key.
- `docs/implementation/mvp/phase3/evidence/browser-check.json`: lượt API thật từ web, counters và lỗi JavaScript.
- `docs/implementation/mvp/phase3/evidence/tutor-1440.png`, `tutor-768.png`, `tutor-390.png`, `report-mobile.png`: ảnh thực tế sau chạy browser.

Các file chỉ được coi là đạt khi script tương ứng đã chạy thành công. Tests không thay thế review người có chuyên môn, dataset test độc lập, pilot học sinh hoặc manual evidence/commit cuối cùng ở Phần 5.

Đã xem ảnh [desktop](evidence/tutor-1440.png), [tablet](evidence/tutor-768.png), [mobile](evidence/tutor-390.png) và [báo cáo mobile](evidence/report-mobile.png). Các viewport không tràn ngang; nháp, nguồn phản hồi, mức gợi ý và báo cáo hiển thị. Đây là kiểm tra giao diện Phần 3, chưa thay thế nghiệm thu toàn bộ frontend Phần 4.

## Những vấn đề phát hiện trong lúc triển khai

- Docker Desktop ban đầu chưa chạy, nên lượt DB test đầu không kết nối được. Đã bật Docker và giữ nguyên volume.
- Giới hạn worker 1 giây khiến lượt browser đầu trả `cannot_verify`, không tạo observation. Đã nâng thời hạn tổng khởi động + xác minh lên 3 giây, vẫn hủy process nếu quá hạn; chưa cam kết SLA 1 giây.
- Khi chạy suite cùng lúc build Docker, một lượt worker hợp lệ vẫn không hoàn tất trong 3 giây. Giữ [JUnit của lượt đó](evidence/tests-during-build.xml) để đối chiếu, đã che token demo tạm. Vì vậy lần nghiệm thu cuối chạy sau build; bài chưa xác minh không bị coi là sai hoặc cập nhật BKT.
