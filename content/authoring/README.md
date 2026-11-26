# Pipeline biên soạn nội dung Member 2

Phạm vi Chặng 2 hiện gồm **N02, N05, N08, A01, A04, A07, A10, E03, E06, E09, F02, F05 và F08**. Nguồn dùng cho các run mới là [registry snapshot và bank đã duyệt M2-ORIG02](batches/member2-original.v2/manifest.json), phiên bản `0.4.0-member2-review`.

Bộ [13 cấu hình](configs/member2-v2/N02.json) cấp concept, skill, ba family/source group, model, ngân sách token và thời gian chờ. [Prompt 2.2.0](prompts/draft.v2.txt) mô tả các định dạng đang được checker hỗ trợ, gồm phân thức, dữ kiện lời văn, căn chính xác, khử hệ, trục đối xứng và điều kiện cơ số. Ngữ cảnh cấp rõ sáu ô bài tương ứng với ba họ mẫu.

## Chạy pipeline

Chạy từ thư mục gốc với dependencies backend đã cài. Thêm `--source member2-v2` cho các run hiện hành.

```powershell
python scripts/authoring/draft_content.py plan --source member2-v2 --config content/authoring/configs/member2-v2/F05.json
python scripts/authoring/draft_content.py draft --source member2-v2 --config content/authoring/configs/member2-v2/F05.json --provider pilot_replay --run-id m2-f05-replay-01
python scripts/authoring/draft_content.py check --run-id m2-f05-replay-01
```

`pilot_replay` dùng nội dung đã có để kiểm đường xử lý. Metadata của run ghi rõ nguồn replay và số lượt gọi model bằng 0. Run ID phải mới. Lệnh tạo run dùng chế độ tạo file mới và ghi trạng thái lỗi khi provider hoặc checker gặp vấn đề.

## Sinh nháp bằng API

Đặt `OPENAI_API_KEY` và `AUTHORING_LLM_ENABLED=true` trong môi trường process chạy CLI. Có thể dùng `--model` để chọn model khác cấu hình. Request được lưu sẽ ghi đúng model đã chọn.

```powershell
$env:AUTHORING_LLM_ENABLED = "true"
python scripts/authoring/draft_content.py draft --source member2-v2 --config content/authoring/configs/member2-v2/N02.json --provider openai --model gpt-4o-mini --run-id m2-n02-openai-01
python scripts/authoring/draft_content.py check --run-id m2-n02-openai-01
```

CLI lấy key từ biến môi trường process. Khi lưu key trong `.env`, nạp biến đó vào process trước khi chạy. Các artifact chỉ chứa nội dung, cấu hình và metadata cần cho đối soát. Adapter đặt timeout và giới hạn token theo request, mỗi run gửi một request tới provider.

Nhánh Gemini dùng `GEMINI_API_KEY`, `--provider gemini` và model phù hợp, ví dụ `--model gemini-3.1-flash-lite`.

## Artifact và kiểm tra

Run mới nằm trong `artifacts/authoring/<run-id>/`. Các tệp cần cho kiểm tra gồm

- `request.json` và `prompt.json` lưu cấu hình thực tế và prompt có version.
- `registry-snapshot.json` và `bank-snapshot.json` ghim ngữ cảnh của run.
- `generated.json`, `draft.json` và `checks.json` lưu output, bản nháp do server gắn metadata và lỗi có vị trí.
- `review-template.json` cấp checklist trống cho reviewer.
- `manifest.json` lưu trạng thái, model, usage, version và SHA-256 từng artifact.
- `failure.json` xuất hiện khi provider hoặc schema thất bại.

`draft_ready` là nháp qua checker và sẵn sàng review. `check_failed` ghi nháp còn lỗi máy. `failed` ghi run chưa có nháp hợp lệ. Lệnh `check` và `review` đọc snapshot đã ghim cho các run Member 2 mới. Snapshot bị sửa sẽ bị phát hiện trước khi ghi review.

## Review và tái tạo nội dung đã duyệt

Reviewer sao chép template sang file riêng rồi điền người duyệt, thời điểm, hash, nhận xét và kết quả năm mục. Chấp thuận cần đủ toán, phạm vi chương trình, ngôn ngữ/sư phạm, disclosure và nguồn. Nội dung được sửa cần revision và run mới.

```powershell
python scripts/authoring/draft_content.py review --run-id m2-f05-replay-01 --review-file artifacts/review-f05.json
```

Kết quả nằm trong `reviews/<review-id>/`, có `approved-pack.json` khi duyệt đạt. Mọi nháp mới từ API cần review cho đúng hash trước khi xuất bản.

Để tái tạo 13 pack M2-ORIG02 và hồ sơ lời giải đang dùng, chạy

```powershell
python scripts/authoring/prepare_member2_pilot.py --edition v2
python scripts/authoring/prepare_member2_pilot.py --edition v2 --output artifacts/member2-review-new
```

Thư mục xuất phải mới. Lựa chọn v2 xử lý đúng 13 concept và kiểm trùng trong baseline curriculum cùng lô đang tạo.

## Nghiệm thu

```powershell
python scripts/checks/check_authoring.py
python scripts/checks/check_authoring.py --live-run TEN_RUN_API_DA_LUU
python -m pytest tests/test_member2_authoring_pipeline.py tests/test_content_authoring.py tests/test_member2_stage2_pilot.py -q
```

Bộ check mặc định kiểm đủ 13 cấu hình, prompt, schema, replay và ranh giới công bố draft. `--live-run` xác minh metadata cùng nội dung của một lượt gọi provider đã lưu. Các ca review synthetic trong test được gắn nhãn rõ.

Hồ sơ A02/E02 và prompt v1 phục vụ tái lập các lượt trước. Chọn `--source legacy` khi kiểm một run lịch sử theo nguồn cũ. [Bàn giao Chặng 2 hiện hành](../../docs/implementation/member2/part2/README.md)
