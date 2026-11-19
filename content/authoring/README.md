# Biên soạn nháp nội dung — pipeline v1

Pipeline Chặng 2 dùng lại `ConceptPack` và checker toán đang có. Mỗi run xử lý một concept, tạo nháp và hồ sơ review riêng trong `artifacts/authoring/` đã Git ignore. Không ghi vào registry/pilot hoặc DB sản phẩm.

Đọc [bản bàn giao và review Chặng 2](../../docs/implementation/member2/part2/README.md) để xem trạng thái, giới hạn và kết quả kiểm tra.

Ngày 17/11/2026: đã chuẩn bị [lô nguồn OATutor + AI bổ sung A02/E02 và 24 query dev](../../docs/implementation/member2/source-pilot/README.md). Lô được lưu riêng, còn chờ người thật review; không thay registry/pilot canonical hoặc tự duyệt nhãn.

Bản hiện hành: [hoàn thiện Chặng 2, revision M2-OAT02](../../docs/implementation/member2/part2-completion/README.md). Dùng `prepare_oatutor_batch.py build --edition stage2-v2` để tái tạo và truyền `--batch content/authoring/batches/a02-e02-oatutor.v2` khi check/review. Có thêm `curriculum-review` và `labels-review`; v1 được giữ nguyên cho đối chiếu. Các config `.v1.json` và ví dụ CLI authoring ban đầu bên dưới là workflow cũ, chưa thay bằng scope của snapshot v2.

## 1. Cấu hình

- [a02.v1.json](configs/a02.v1.json): phân phối, ba họ dương/âm/đặt nhân tử chung.
- [e02.v1.json](configs/e02.v1.json): ba dạng phương trình bậc nhất hiện có.
- [draft.v1.txt](prompts/draft.v1.txt): prompt có version, scope, ngữ pháp, ID, provenance và quy tắc hint.
- [DraftRequest schema](../../contracts/authoring/v1/DraftRequest.schema.json), [GeneratedContent schema](../../contracts/authoring/v1/GeneratedContent.schema.json), [ContentReview schema](../../contracts/authoring/v1/ContentReview.schema.json).

Config có tác giả, revision, content version, nguồn, ba family/source group, model, token budget và timeout. Model mặc định trong hai config kế thừa lựa chọn đang có của dự án, chưa phải kết quả benchmark model cho authoring. Đổi model trong config khi nhóm chốt thí nghiệm.

Scope/lớp trong registry hiện còn nháp. Pipeline cho phép tạo nội dung authoring theo scope khai báo để chuẩn bị review, không coi đây là nội dung đã đối chiếu chương trình hoặc được phép dạy học.

## 2. Xem kế hoạch mà không gọi model

Từ repo root, với Python có Pydantic 2:

```powershell
python scripts/authoring/draft_content.py plan --config content/authoring/configs/a02.v1.json
```

Lệnh chỉ in prompt/context. Context gồm source metadata của registry, không tự tải hoặc xác minh nội dung nguồn.

## 3. Chạy offline để kiểm tra luồng

```powershell
python scripts/authoring/draft_content.py draft --config content/authoring/configs/a02.v1.json --run-id a02-local-01 --provider pilot_replay
python scripts/authoring/draft_content.py check --run-id a02-local-01
```

`pilot_replay` lấy pack nháp hiện có, đổi ID bản ghi sang namespace của revision và giữ nguyên family/source group. Đây là replay, không phải nội dung mới hoặc lần gọi LLM. Nó kiểm tra được request → draft → checker → hồ sơ review.

Nếu đã có payload từ một lần sinh model, dùng `--provider replay --input <generated.json>`. Chỉ chấp nhận cấu trúc `GeneratedContent`, không nhận các trường review/tự duyệt.

Không ghi đè run cũ. Dùng run ID mới để thử lại; nếu sửa nội dung/config/prompt thì đổi revision và giữ run cũ để đối chiếu. Các bản cùng revision chỉ nên dùng để replay/đối chiếu, không tự coi là các phiên bản nội dung được publish khác nhau. Quy tắc bất biến ID/version khi publish tiếp tục được kiểm soát ở Chặng 3.

## 4. Gọi OpenAI thật

Cài các dependencies backend có sẵn trong repo, cấu hình API key trong môi trường server và đặt `AUTHORING_LLM_ENABLED=true`. CLI không tự đọc `.env`; biến trong `.env.example` là mẫu cấu hình, cần export vào process chạy CLI.

```powershell
$env:AUTHORING_LLM_ENABLED = "true"
python scripts/authoring/draft_content.py draft --config content/authoring/configs/a02.v1.json --run-id a02-openai-01 --provider openai
```

Không đưa key vào command argument, config, prompt hoặc Git. Cần có `OPENAI_API_KEY` trong môi trường trước khi chạy. Cờ authoring độc lập với `LLM_ENABLED` của gia sư online.

Adapter sử dụng Responses `parse` với Pydantic, `store=false`, timeout từ config, token budget và không retry tự động; theo [hướng dẫn Structured Outputs của OpenAI](https://developers.openai.com/api/docs/guides/structured-outputs). Schema đúng cấu trúc chưa chứng minh toán/sư phạm đúng. Model refusal/incomplete hoặc lỗi provider tạo run thất bại có log đã lược thông tin nhạy cảm, không trở thành nháp được duyệt.

Một run có tối đa một lời gọi model ở tầng ứng dụng. Khi live call lỗi, metadata ghi số lần thử, không mặc định chi phí bằng 0. Không có bảo đảm output live giống hệt khi gọi lại; khả năng replay đến từ payload/prompt/config đã lưu.

## 5. Hồ sơ trong mỗi run

| Tệp | Ý nghĩa |
|---|---|
| `request.json`, `prompt.json` | Config và input thực tế, có version/hash |
| `generated.json` | Nội dung có cấu trúc để replay; không có quyền duyệt |
| `draft.json` | Pack gắn tác giả/nguồn từ request, trạng thái draft |
| `checks.json` | Lỗi/cảnh báo có code và vị trí; `passed` là kết quả máy |
| `review-template.json` | Reviewer/thời điểm trống, checklist chưa đánh giá |
| `failure.json` nếu có | Lỗi schema hoặc lỗi provider đã được lược dữ liệu nhạy cảm |
| `manifest.json` | Trạng thái run, provider/model/usage nếu có, source hashes và checksums artifacts |

`draft_ready` nghĩa là nháp sẵn sàng để người khác review. `check_failed` có nháp nhưng còn lỗi máy; `failed` không có nháp reviewable. Nếu process/IO bị ngắt và chưa có manifest hoàn chỉnh, giữ thư mục để điều tra và chạy run mới.

## 6. Review thủ công

Sao chép `review-template.json` ra một file mới ngoài run để điền, tránh sửa artifact gốc. Người review phải khác tác giả và tự điền danh tính, thời điểm, kết quả năm mục cùng nhận xét:

- Toán và đáp án/bước giải.
- Chương trình, lớp và độ phủ hành vi đo.
- Sư phạm, ngôn ngữ và đa dạng thực chất của họ bài.
- Mức tiết lộ trong hint/explanation/câu hỏi chẩn đoán.
- Nguồn và quyền sử dụng.

```powershell
python scripts/authoring/draft_content.py review --run-id a02-local-01 --review-file artifacts/authoring/review-a02-r001.json
```

Để `decision=approved`, tất cả mục phải pass, đúng hash bản nháp và ngày review hợp lệ; còn lỗi máy thì không duyệt được. `changes_requested` lưu yêu cầu sửa và không tạo candidate được duyệt. Sau sửa, tạo revision/run mới rồi review lại.

Kết quả lưu thêm vào `reviews/<review_id>/`, không sửa nháp gốc. `approved-pack.json` là candidate để tích hợp sau, chưa tự nạp vào bank, chưa duyệt concept/alignment/cạnh graph và chưa được công bố cho học sinh. CLI ghi nhận danh tính do nhóm cung cấp, chưa có xác thực tài khoản/chữ ký số.

## 7. Tự kiểm tra

```powershell
python scripts/checks/check_authoring.py
python -m unittest discover -s tests -p test_content_authoring.py -v
```

Tests có approval/review synthetic để thử nghiệp vụ. Chúng không phải review nội dung thật; artifacts test ở `artifacts/authoring-tests/` được giữ lại, không xóa tự động theo quy tắc workspace.
