# Bàn giao review độc lập Chặng 4 — 26/11/2026

Trạng thái: **chờ Member 1/3 review**. Tệp này chuẩn bị phạm vi, bước tái hiện và chỗ ghi kết quả; không phải chữ ký hoặc bằng chứng review đã diễn ra. Không gửi thông báo tới thành viên hay đẩy mã lên remote trong lượt triển khai này.

## Căn cứ và tái hiện

Đối soát [verification](verification-stage4-2026-11-26.json), [JUnit](tests-stage4-2026-11-26.xml), [Chromium](browser-stage4-2026-11-26.json) và hash mã nguồn trong verification. Kiểm thử dùng schema riêng; không kích hoạt snapshot rỗng lên namespace phục vụ.

```powershell
.\.venv\Scripts\python.exe scripts/dev/validation_runtime.py database
.\.venv\Scripts\python.exe scripts/dev/validation_runtime.py tests --suite stage4
npm --prefix frontend test
npm --prefix frontend run typecheck
npm --prefix frontend run build
.\.venv\Scripts\python.exe scripts/checks/check_stage4_browser.py
```

Full suite lịch sử cần các batch A02/E02 đã không còn trong workspace. Suite hiện hành nêu rõ phạm vi, không thay thế nghiệm thu archive. Workflow `stage4-current-checks.yml` đã được chuẩn bị cho phạm vi này; chưa có URL/job remote hoặc bằng chứng Docker mới.

## Member 1 — phiên, observation và báo cáo

- Kiểm `test_stage4_teaching.py`: sai → hỗ trợ → sửa đúng → bài độc lập; replay giữ nguyên turn/receipt; commit lỗi không tạo assistance/observation một phần.
- Kiểm `test_stage4_reports.py` và `report_diagnoses.py`: `supported` chỉ nói về dấu vết lỗi lặp ở ít nhất hai họ bài độc lập. Không nâng số lần retry, bài gần hoặc bài đã được hỗ trợ thành bằng chứng độc lập. `rejected` chỉ bác bỏ nhận định về bài làm mới nhất đã sửa đúng, giữ nguyên nhận định lịch sử.
- Không có lỗi được gán mẫu hoặc thiếu evidence thì UI ghi thiếu bằng chứng. Dữ liệu canonical vẫn chỉ chấm dòng cuối và không tự tạo BKT.
- Report 2.1 đóng băng khi kết thúc; report 2.0 vẫn đọc được, không viết lại payload cũ. Parameter source chỉ lấy từ phiên bản đã biết; phiên bản lạ phải ghi thiếu provenance.
- Kiểm liên kết evidence về đúng bài đã nộp, nguồn/version/time BKT và quyền sở hữu report giữa hai hồ sơ.

Người review: ______ · Thời điểm: ______ · Revision/hash: ______

Kết quả (đạt/cần sửa), vấn đề và bằng chứng: ______

## Member 3 — nội dung, policy, guard và giao diện

- Kiểm Full/No-RAG ghim theo session; No-RAG không nhận context/citation KB, kể cả qua cache. Retrieval lỗi không đổi correctness/BKT.
- Đối chiếu retrieved/generator/delivered refs; phản hồi dùng nguyên văn nội dung duyệt và kiểm guard tại commit, gồm withdrawal. Kiểm mức tiết lộ trong cả 13 concept, đặc biệt ví dụ phải khác family/source/lineage bài đo.
- Dùng ảnh và flow Chromium để kiểm phân thức A10, hệ E09, tiếng Việt, 390/1440 px, HTML không tin cậy, bàn phím/focus và retry sau timeout thực của AbortController (đồng hồ ảo 45 giây).
- Nội dung ôn tập hiện dựa trên bài làm có evidence; không tự kết luận prerequisite yếu. Sinh lời tự do, graph recommendation và thực nghiệm RQ3 là phạm vi riêng, chưa được nghiệm thu bởi hồ sơ này.

Người review: ______ · Thời điểm: ______ · Revision/hash: ______

Kết quả (đạt/cần sửa), vấn đề và bằng chứng: ______

## Remote CI/Docker

CI run URL/revision: ______ · Kết quả: ______

Docker image digest/lệnh và kết quả: ______

Không đánh dấu hoàn tất các mục này bằng kết quả kiểm thử cục bộ.
