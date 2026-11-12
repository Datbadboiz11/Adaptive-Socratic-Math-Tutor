# Bộ chấm người học và Analyzer pilot v1

Đợt triển khai ngày 06/10/2026 tiếp nối [registry/pilot](../../../content/curriculum/README.md). Đây là bộ chấm và Analyzer baseline chạy được, cùng API thử nội bộ và dữ liệu phát triển; chưa phải luồng gia sư đủ module trên 10 concept.

## Vị trí trong kế hoạch tổng

[Kế hoạch tổng](../../planning/project-plan.md) mô tả Analyzer ở mục 8.2, bộ evaluation ở mục 11.5/12 và các mốc ở mục 24: tuần 2 checker các dạng đầu; tuần 3 Analyzer v1; tuần 4 validator/Analyzer cho 8–10 concept và tích hợp end-to-end. Đợt này thực hiện phần checker/Analyzer và chuẩn bị dữ liệu phát triển của các mốc đó. Các tuần là các luồng song song, không thể suy ra hoàn thành tuần 4 chỉ từ việc có 10 concept.

Hướng triển khai tiếp theo có thứ tự phụ thuộc:

1. **Đợt hiện tại:** chấm bài làm người học, xác định bước sai đầu tiên trong phạm vi kiểm chứng được; chuẩn bị ca đúng/sai, ca mơ hồ và kiểm tra hồi quy. Giữ tách biệt kết quả toán và giả thuyết nguyên nhân.
2. **KG/RAG:** dùng concept/skill và bằng chứng lỗi để tìm kiến thức liên quan; lọc nguồn, trạng thái duyệt và mức gợi ý; ghi content/edge IDs. Chuẩn bị query và nhãn relevance, so sánh retrieval metadata với retrieval ngữ nghĩa.
3. **Agent:** đọc lịch sử, Student Model và bằng chứng Analyzer để chọn hỏi chẩn đoán, gợi ý, ôn prerequisite hoặc bài mới. Dùng policy luật làm baseline; validate action/tool, có fallback và decision log.
4. **Tích hợp pilot:** nối chấm → phân tích → truy xuất → can thiệp → phản hồi tiếp theo vào phiên học có persistence, backtrack/return và UI. Nội dung nháp chỉ xuất hiện trong chế độ thử nội bộ; review chạy song song.
5. **Thực nghiệm và mở rộng:** tạo bộ đánh giá riêng theo họ bài/source group, khóa test trước thực nghiệm cuối; mở rộng concept theo checklist, đánh giá Analyzer/retrieval và full system/ablation. Không dùng kết quả hồi quy của đợt này làm kết quả nghiên cứu cuối.

Khi chọn mô hình/chi phí gọi AI, nguồn giáo trình hoặc công bố nội dung, cần chốt với nhóm. Đợt này không cần quyết định mới: dùng nội dung pilot sẵn có, không gọi AI trả phí và không tự ghi duyệt chuyên môn.

## Phần đã triển khai

Hỗ trợ 10 concept N01/N02/N04/A01/A02/A03/E01/E02/F01/F05 với 60 bài, thuộc 5 loại nhiệm vụ:

| Loại | Chấm được | Điều kiện hoàn thành |
|---|---|---|
| `numeric` | Biểu thức số, phép tính hữu tỉ chính xác | Giá trị số cuối; N04 cần phân số tối giản, mẫu dương |
| `evaluate` | Thay giá trị vào biểu thức/hàm | Kết quả số đã tính xong |
| `polynomial` | So sánh hệ số đa thức một biến bậc ≤ 2 | Thu gọn/khai triển; hai bài phân phối ngược A02 cần dạng nhân tử |
| `linear_equation` | Phương trình tương đương, nghiệm duy nhất/rỗng/vô số | Nghiệm đã cô lập; E01 cần bước biến đổi có dấu `=` |
| `quadratic_vertex` | Cặp tọa độ đỉnh chính xác | Đủ `(hoành độ, tung độ)`; chưa chấm trục đối xứng riêng |

Chấp nhận `3x`, `3(x+2)`, phép nhân `×`, dấu trừ Unicode và `x^2`. Các bước là snapshot biểu thức/phương trình đầy đủ. Không hỗ trợ lời giải tự do bằng lời, biến ngoài `x`, phân thức có ẩn ở mẫu, căn, bất đẳng thức hoặc bậc cao. Dạng `1/2x` cần làm rõ; viết `(1/2)*x`. Đầu vào mỗi bước tối đa 160 ký tự, tối đa 12 bước; parser giới hạn độ sâu/số phép tính và worker có deadline tối đa 3 giây.

Kết quả tách các trường:

- `assessment_status`: đúng đã kiểm chứng, sai đã kiểm chứng, cần làm rõ hoặc chưa kiểm chứng.
- `first_error_step`: chỉ ghi khi có các bước đủ rõ; dừng tại lỗi đầu tiên, các bước sau là `not_assessed` để tránh tính nhiều lỗi kéo theo.
- `completed`: tương đương về toán chưa chắc đã đạt dạng đáp án yêu cầu. Bài làm dở trả `valid_partial`, không phải observation đúng/sai hoàn chỉnh.
- `misconception_candidate`/`error_family`: chỉ khớp mẫu lỗi cùng bài, cùng vị trí; luôn `suspected`, kèm câu hỏi chẩn đoán. Lỗi chưa có mẫu giữ `unknown`. Cùng một nghiệm sai không đủ bằng chứng để suy ra cùng nguyên nhân.
- `updates_student_model=false`: không cập nhật BKT, không lưu phiên hay observation. API này không nối với eligibility pipeline của MVP.

Nếu `submission_kind=final_answer`, phải có đúng một phần tử; không tự suy ra bước sai đầu tiên hoặc misconception. Với E01, một đáp án riêng lẻ không đo được kỹ năng biến đổi, kể cả đáp án đúng.

Nếu dòng đầu là bản sao nguyên văn task và còn bước tiếp theo, nó chỉ là ngữ cảnh; số bước chấm bắt đầu từ dòng làm bài sau đó. Không coi việc nộp lại nguyên đề là đã hoàn thành.

Đây là **Analyzer baseline bằng kiểm chứng toán và mẫu lỗi**, chưa thêm LLM suy luận nguyên nhân. Baseline giúp tạo contract/bằng chứng và làm đối chứng khi thêm Analyzer AI. Chất lượng AI cuối cần bộ đánh giá độc lập và thực nghiệm, không chỉ tests kỹ thuật.

## Thử ngay, không cần Docker

Từ thư mục gốc dự án:

```powershell
.\.venv\Scripts\python.exe -X utf8 research/analyzer/evaluate.py --problem P-A02-01 --step '3x+6'
.\.venv\Scripts\python.exe -X utf8 research/analyzer/evaluate.py --problem P-A02-01 --step '3x+2'
.\.venv\Scripts\python.exe -X utf8 research/analyzer/evaluate.py --problem P-E02-03 --kind final_answer --step '6.5'
.\.venv\Scripts\python.exe -X utf8 research/analyzer/evaluate.py --problem P-A02-01 --step '3x+3*2'
```

Lần lượt: đúng và hoàn thành; sai bước 1 với giả thuyết thiếu phân phối; sai đáp án nhưng không đoán bước/nguyên nhân; biến đổi đúng nhưng chưa tính xong. Có thể lặp `--step` để nhập nhiều bước. Đây là thử authoring, không tạo phiên học.

## Thử API nội bộ

Trong `.env` cục bộ đặt `PILOT_ANALYZER_ENABLED=true`; giữ `DEMO_MODE=true`. Sau khi Docker Desktop hoạt động, chạy `docker compose up -d --build --wait`. Cờ mặc định tắt và nội dung không được seed thành topic mới trên web. Web gia sư hiện tại vẫn dùng luồng MVP cũ.

API dùng xác thực hồ sơ demo hiện có. Lấy hồ sơ/token rồi gọi API bằng PowerShell:

```powershell
$pilotBase = 'http://localhost:8000/api/v1'
$pilotProfiles = Invoke-RestMethod "$pilotBase/demo/profiles"
$pilotLoginBody = @{demo_profile_id = $pilotProfiles[0].student_id} | ConvertTo-Json
$pilotLogin = Invoke-RestMethod "$pilotBase/demo/login" -Method Post -ContentType 'application/json' -Body $pilotLoginBody
$pilotHeaders = @{Authorization = "Bearer $($pilotLogin.access_token)"}
Invoke-RestMethod "$pilotBase/pilot/concepts" -Headers $pilotHeaders
$pilotBody = @{submission_kind = 'steps'; steps = @('3x+2')} | ConvertTo-Json
Invoke-RestMethod "$pilotBase/pilot/problems/P-A02-01/assess" -Method Post -Headers $pilotHeaders -ContentType 'application/json' -Body $pilotBody
```

Login ghi token demo theo cơ chế cũ; endpoint chấm chỉ đọc nội dung và chạy worker. Projection bài không chứa đáp án/lời giải/mẫu lỗi riêng. Request không được tự gửi đáp án chuẩn hoặc task để thay nội dung server.

Ba endpoint: `GET /api/v1/pilot/concepts`, `GET /api/v1/pilot/problems/{id}`, `POST /api/v1/pilot/problems/{id}/assess`. OpenAPI đầy đủ ở [contracts/pilot](../../../contracts/pilot/openapi.json); snapshot MVP cũ được giữ nguyên.

## Bộ dữ liệu phát triển và cách đánh giá

[analyzer.dev.v1.json](../../../content/curriculum/analyzer.dev.v1.json) có 180 ca: 60 trace chuẩn, 60 đáp án cuối, 20 trace lỗi, 20 đáp án sai không có trace và 20 ca cần làm rõ. Có concept, family và source group để chuẩn bị cách chia sau này. Không chứa dữ liệu học sinh thật.

Nhãn có trạng thái `draft_machine_audited`, split `authoring_dev`. Chúng xuất phát từ nội dung/mẫu lỗi dùng trong phát triển; **180/180 khớp kỳ vọng chỉ là kết quả hồi quy**, không phải accuracy/F1 trên test độc lập và không chứng minh hiệu quả học tập.

```powershell
.\.venv\Scripts\python.exe -X utf8 research/analyzer/evaluate.py --output data/experiments/analyzer-dev-v1
.\.venv\Scripts\python.exe -X utf8 scripts/checks/check_curriculum.py
.\.venv\Scripts\python.exe -X utf8 scripts/exports/export_contracts.py --check
.\.venv\Scripts\python.exe -X utf8 scripts/exports/export_phase3_openapi.py --check
.\.venv\Scripts\python.exe -X utf8 scripts/exports/export_pilot_openapi.py --check
.\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_pilot_analyzer.py tests/test_curriculum.py -q
```

Chỉ dùng `--build-dev` khi chủ động tạo lại dataset phát triển. Report/predictions được lưu trong `data/` đã ignore. Trước thực nghiệm chính cần biên soạn ca mới, review nhãn, chia theo họ/source group và giữ test kín. ASSISTments/BKT v1 và tập test của BKT không được thay đổi trong đợt này.

## Thứ tự đọc code

1. [pilot_contracts.py](../../../backend/app/pilot_contracts.py): đầu vào/đầu ra và ý nghĩa các trường.
2. [learner_math.py](../../../backend/app/learner_math.py): parser độc lập cho người học, so sánh giá trị/dạng hoàn thành.
3. [pilot_analyzer.py](../../../backend/app/pilot_analyzer.py): lỗi đầu tiên, abstention, giả thuyết; [worker](../../../backend/app/pilot_worker.py) giới hạn thời gian.
4. [test_pilot_analyzer.py](../../../tests/test_pilot_analyzer.py): cách giải khác, bài dở, đầu vào mơ hồ, lỗi kéo theo và bảo vệ API.
5. [evaluate.py](../../../research/analyzer/evaluate.py): tạo/chạy bộ dev và báo cáo theo concept/loại bài.
6. [pilot_api.py](../../../backend/app/pilot_api.py): API preview có cờ và xác thực; không ghi Student Model.

Hai task `P-A02-05/06` bổ sung `answer_form=factored_polynomial` để phân biệt yêu cầu đặt nhân tử với khai triển. Review vẫn nháp; phiên bản draft giữ 0.1.0, hash revision được lưu trong báo cáo mới. [checks.v1.json](checks.v1.json) là bằng chứng ngày 04/10, không thay bằng kết quả ngày 06/10.

## Giới hạn kiểm chứng môi trường

Trong lần triển khai này, TestClient không khởi tạo được vòng lặp asyncio vì socketpair loopback bị môi trường Windows chặn; Docker Engine cũng chưa sẵn sàng. HTTP và PostgreSQL chưa được kiểm chứng lại tại máy này. Tests HTTP mới được giữ để chạy mặc định trong CI; cờ `SKIP_ASGI_TESTS=1` chỉ dành cho môi trường có lỗi đó. Các kiểm tra toán, worker, contract, handler trực tiếp và corpus dev vẫn chạy được.

Kết quả cụ thể và hash source ở [analyzer-checks.v1.json](analyzer-checks.v1.json). CI được cấu hình kiểm tra API/PostgreSQL đầy đủ nhưng chưa được chạy từ đây; không coi cấu hình CI là bằng chứng PASS.
