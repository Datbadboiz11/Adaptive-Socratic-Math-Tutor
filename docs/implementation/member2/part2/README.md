# Chặng 2 — Pipeline nội dung và review của Member 2

**Đã hoàn thành ba mục bổ sung và nghiệm thu ngày 25/11/2026** cho phạm vi 13 concept **N02, N05, N08, A01, A04, A07, A10, E03, E06, E09, F02, F05, F08**. [Bằng chứng nghiệm thu](verification-2026-11-25.json)

| Tiêu chí | Kết quả |
|---|---|
| Cấu hình hiện hành | Có cấu hình riêng cho cả 13 concept, dùng registry và bank M2-ORIG02 ở phiên bản 0.4.0-member2-review. |
| Luồng CLI | `plan → draft → check → review` dùng nguồn `member2-v2`. Run mới lưu request, prompt và snapshot registry/bank cùng SHA-256. |
| Phạm vi prompt | Prompt 2.2.0 mô tả các định dạng checker hỗ trợ, gồm phân thức, lời văn, nghiệm vô tỉ, khử hệ, trục đối xứng và điều kiện cơ số. Ngữ cảnh chỉ định sáu ô bài thuộc ba họ mẫu. |
| Kiểm thử tự động | 188 test đạt trong lượt kiểm không cần DB. Bộ check mặc định kiểm đủ 13 cấu hình, schema, replay và ranh giới công bố draft. |
| Gọi OpenAI thật | Pack N02 được sinh bằng gpt-4o-mini, model trả về gpt-4o-mini-2024-07-18. Run m2-n02-openai-2c86dfa109 đạt draft_ready và checker. Usage ghi 4.000 input token, 1.937 output token. |
| Phụ thuộc A02/E02 | Nguồn authoring hiện hành và bộ check Chặng 2 dùng đúng 13 concept. Bộ tái tạo v2 hoạt động khi các thư mục lô A02/E02 cũ không được truy cập. |
| Nội dung đã duyệt | 13/13 pack M2-ORIG02 giữ hồ sơ phê duyệt của người dùng, gồm 78 bài, 39 ví dụ có lời giải, 39 mẫu lỗi và 39 hint. |

Hai lượt OpenAI đầu được checker ghi `check_failed` vì phân bố họ bài, cú pháp snapshot hoặc nhãn lỗi. Prompt đã bổ sung ô bài bắt buộc và chỉ dẫn snapshot cuối để sửa các lỗi này. Run sau đạt. Cả ba run và kết quả checker được lưu trong workspace. Gemini cũng đã tạo thành công một pack N02 trước khi key OpenAI được cập nhật. Metadata và hash của các lượt có trong bằng chứng nghiệm thu.

Mẫu OpenAI mới là nội dung sinh thêm, ở trạng thái `draft` chờ reviewer xem đúng hash trước khi dùng cho học sinh. [Output OpenAI và checker](live-openai-N02-2026-11-25.json)

## Chạy lại

Các lệnh sau chạy từ thư mục gốc dự án.

```powershell
python scripts/authoring/draft_content.py plan --source member2-v2 --config content/authoring/configs/member2-v2/A07.json
python scripts/authoring/draft_content.py draft --source member2-v2 --config content/authoring/configs/member2-v2/F05.json --provider pilot_replay --run-id m2-f05-replay-new
python scripts/authoring/draft_content.py check --run-id m2-f05-replay-new
python scripts/checks/check_authoring.py
python scripts/checks/check_authoring.py --live-run m2-n02-openai-2c86dfa109
```

Lệnh `--live-run` kiểm run đã lưu trong workspace. Run nằm tại `artifacts/authoring/m2-n02-openai-2c86dfa109/`. Trên máy mới, sinh một run với ID mới rồi dùng ID đó để kiểm.

Để gọi OpenAI, nạp `OPENAI_API_KEY` vào môi trường process và đặt `AUTHORING_LLM_ENABLED=true`. Chọn `--provider openai` và model được cấu hình. [Hướng dẫn CLI và API](../../../../content/authoring/README.md)

## Hồ sơ nội dung đã duyệt

[Nguồn biên soạn 13 concept](../../../../content/authoring/member2-original-pilot.v2.json) · [Manifest phê duyệt](../../../../content/authoring/batches/member2-original.v2/manifest.json) · [Bank đã duyệt](../../../../content/authoring/batches/member2-original.v2/approved-bank.json)

Bộ nội dung 0.4.0 có A04 kiểm khai triển/thu gọn, A10 đủ bốn phép toán phân thức, E03 dựng phương trình từ dữ kiện, E06 kiểm căn chính xác, F05 kiểm riêng tọa độ đỉnh và trục đối xứng, F08 kiểm cả cơ số và tập xác định. [Nghiệm thu luồng demo của 13 concept](../part4/README.md)

Để tái tạo hồ sơ lời giải và review trong một thư mục mới

```powershell
python scripts/authoring/prepare_member2_pilot.py --edition v2 --output artifacts/member2-review-new
```

Reviewer ghi nhận xét vào bản sao của template rồi chạy lệnh review tương ứng. Trạng thái review, người và thời điểm được gắn với hash nội dung. Mỗi lần sửa nội dung cần review lại phiên bản tương ứng.

## Hồ sơ lịch sử

Các lượt trước được lưu trong [verification.json](verification.json), [verification-update.json](verification-update.json), [Gemini retest ngày 23/11](gemini-retest-2026-11-23.json) và [hồ sơ nguồn OATutor](source-rights.json). Phạm vi nghiệm thu hiện tại là bộ 13 concept tự biên soạn đã nêu ở đầu trang.