# Hợp đồng dữ liệu và API — v1

## 1. Nguồn chuẩn và version

[Pydantic contracts](../../../../backend/app/contracts.py) là nguồn chuẩn cho cấu trúc. [JSON Schema](../../../../contracts/v1/ProblemPublic.schema.json) được sinh bằng `scripts/exports/export_contracts.py`; `--check` phát hiện schema bị lệch. Pydantic kiểm tra cấu trúc và một số quan hệ field; không xác minh tính đúng Toán, phân quyền hoặc transaction.

`schema_version=1.0.0`, `content_version=0.1.0`, protocol `g2-v1`. Dùng UUID cho request/session/opportunity/assessment/observation; ID có nghĩa và ổn định cho concept/skill/problem. Timestamp phải có timezone UTC. `state_version` bắt đầu từ 1 và tăng khi ghi state thành công.

[Payload mẫu](../../../../contracts/examples.v1.json) cho frontend/backend đã có test schema; đây là fixtures thiết kế, không phải output thực tế của API nghiệp vụ.

## 2. Public và private

- `ProblemPublic`: đề, phương trình, ID/version, concept/skill đích, họ bài, miền và độ khó.
- `ProblemPrivate`: bổ sung đáp án, cách giải, lỗi, gợi ý, ví dụ và nguồn/review; chỉ server/công cụ authoring được đọc.
- Không đưa cả object private vào JSON response rồi chỉ ẩn bằng CSS. Dùng `to_public()`/response model có whitelist field.
- Repo chứa nội dung authoring cho nhóm; “private” ở đây là ranh giới payload runtime, không có nghĩa file đáp án trong repo public là bí mật. Không dùng bộ bài public này làm đề thi bảo mật.

## 3. Contracts được cung cấp

| Schema | Mục đích |
|---|---|
| ProblemPublic / ContentBank | Đề trả cho client / registry nội bộ |
| CreateSession / SessionPublic | Khởi tạo và đọc lại phiên |
| DraftRequest / TurnRequest | Tách lưu nháp khỏi nộp bài/xin hint |
| Assessment | Đúng/sai/chưa xác minh/chưa rõ, bằng chứng và phương pháp |
| Opportunity / Eligibility | Nhiệm vụ, nguồn bài, trợ giúp và lý do đủ/không đủ điều kiện |
| Observation | Evidence chuẩn và trạng thái BKT trước/sau |
| TutorResponse | Hành động được phép, nội dung, nguồn và mức hỗ trợ |
| SessionReport | Bộ đếm độc lập, có hỗ trợ, observation và giới hạn |
| ErrorResponse | Mã lỗi ổn định, message và khả năng retry |

Assessment dùng `first_error_step` (1-based), không dùng `first_wrong_step` từ phác thảo cũ. Chỉ có nghiệm cuối sai thì không bịa bước sai. `unsupported_scope` là reason code của `unverified`. API lỗi cấu trúc dùng 422; phản hồi chưa xác minh hợp lệ về nghiệp vụ dùng 200 với assessment phù hợp.

## 4. Endpoint ở skeleton hiện tại

| Endpoint | Có chạy trong Phần 1? | Kết quả |
|---|---|---|
| `GET /health/live` | Có | 200 khi process sống, không cần DB |
| `GET /health/ready` | Có | 200 khi thực hiện được `SELECT 1`; 503 khi chưa cấu hình/kết nối DB |
| `GET /docs` | Có | Swagger chỉ mô tả endpoint health thực sự tồn tại |

## 5. API nghiệp vụ chuẩn bị cho Phần 2–3

**Các endpoint dưới đây chưa được triển khai.** Tiền tố đề xuất `/api/v1`; dùng schema ở trên làm request/response và thêm envelope khi triển khai.

| Method/path | Input/output | HTTP và quy tắc |
|---|---|---|
| GET `/topics` | Danh sách chủ đề sẵn sàng | Chỉ ready khi có nội dung duyệt + validator |
| POST `/sessions` | CreateSession → SessionPublic | 201 lần đầu; retry cùng key trả kết quả đã lưu |
| GET `/sessions/{id}` | SessionPublic | 200; kiểm tra chủ sở hữu; 404 nếu không được phép thấy |
| PUT `/sessions/{id}/draft` | DraftRequest → state version | Không chấm bài/observation; 409 nếu version cũ |
| POST `/sessions/{id}/turns` | TurnRequest → assessment/eligibility/tutor/state | Request ID bất biến khi retry cùng hành động |
| POST `/sessions/{id}/pause` | request ID + expected version → state | Flush draft trước khi pause; không tạo opportunity |
| POST `/sessions/{id}/resume` | request ID + expected version → state | Giữ task và mức hỗ trợ |
| POST `/sessions/{id}/next` | request ID + expected version → state | Server chọn bài, lưu quan hệ nguồn, không tin eligibility do client gửi |
| POST `/sessions/{id}/finish` | request ID + expected version → report | Gọi lại không tạo thêm báo cáo |
| GET `/sessions/{id}/report` | SessionReport | Tổng hợp từ evidence DB; chưa đủ dữ liệu phải nói rõ |

`student_id` ở response không cấp quyền. `demo_profile_id` chỉ dùng trong local demo, server ánh xạ hồ sơ đã cấp; khi public phải có principal từ cơ chế auth và kiểm tra ownership trên mọi endpoint.

## 6. Idempotency và concurrency

Khóa request gồm principal/session scope, endpoint và UUID. Lưu hash của payload chuẩn hóa, response và trạng thái xử lý. Retry cùng key/payload không chấm hay gọi model lại nếu đã có kết quả; cùng key/payload khác → 409 `idempotency_conflict`. Request cũ chưa commit có thể tiếp tục theo cơ chế recovery; không sinh observation mới để “thử lại”.

Mọi mutation nhận expected state version; thay đổi được commit cùng version mới. Unique observation và transaction là lớp bảo vệ cuối, không chỉ khóa nút gửi ở frontend. Seed nội dung phải upsert theo `(problem_id, content_version)` và từ chối ghi đè khác nội dung ở cùng version.

## 7. Tiêu chí bàn giao

Schema sinh lại không lệch, tests từ chối field đáp án trong public payload, trạng thái chưa xác minh không có bước sai, xin hint không kèm bài nộp, ID/version thống nhất. BKT values phải ở [0,1]; không cho LLM trả các giá trị này như kết quả được tin cậy. Endpoint nghiệp vụ thực sự hoạt động và invariants DB được kiểm thử ở phần tiếp theo.
