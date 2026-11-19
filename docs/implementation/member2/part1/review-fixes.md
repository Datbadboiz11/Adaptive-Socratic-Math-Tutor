# Review và sửa C03/C04/C05 — contract 0.2.0

Ngày thực hiện: 16/11/2026. Theo yêu cầu sửa ba vấn đề phát hiện trong review Chặng 1.

## 1. Phạm vi và phiên bản

Contract hiện hành: `member2-proposal-0.2.0`, với [fixtures](../../../../contracts/member2/v0.2.0/examples.json) và [schema](../../../../contracts/member2/v0.2.0/FoundationExamples.schema.json). Thay đổi cấu trúc dữ liệu có chủ đích; bản mới từ chối payload mang version 0.1.0 thay vì tự suy diễn/migrate. Artifact 0.1.0 giữ nguyên để đối chiếu.

Chưa triển khai RAG, DB migration hoặc UI/report API mới. Các cổng xác nhận của Member 1/3 trong workboard vẫn là `pending_review`. Bộ sửa này hoàn thiện phần kỹ thuật của hợp đồng đề xuất và helper eligibility liên quan.

## 2. C03 — Ghi nhận trợ giúp độc lập với mức hint

Vấn đề cũ: explanation hợp lệ ở mức 0 nhưng eligibility chỉ nhìn mức hỗ trợ lớn hơn 0. Nếu adapter chỉ sao chép số đó, lượt sửa sau giải thích có thể bị coi là độc lập.

Thay đổi:

- Teaching chunk được phân loại `counts_as_assistance=true`, kể cả explanation ở mức 0. Nhãn này phân loại nội dung; truy xuất chưa cập nhật state.
- `TutorPresentation` có `assistance_provided` kiểu boolean chặt và `opportunity_id`. Hint, ví dụ khác hoặc phản hồi sử dụng teaching content không được khai báo là chưa hỗ trợ.
- `OpportunityAssistance` lưu `assistance_received` riêng với `assistance_level`. `record_delivery()` kiểm tra đúng opportunity/bài, chỉ tăng mức tối đa, giữ cờ trợ giúp qua các lượt và cho kết quả như nhau khi áp dụng lại cùng phản hồi.
- Helper `knowledge.eligibility()` xem `assistance_received` hoặc mức hỗ trợ cũ. Opportunity legacy chưa có cờ vẫn dùng điều kiện trước đây; trạng thái “đã có observation” vẫn được ưu tiên.

Thứ tự tích hợp bắt buộc:

1. Nạp trạng thái trợ giúp đã lưu trước khi học sinh nộp bài.
2. Chấm và xét eligibility cho câu trả lời đó bằng trạng thái trước lượt.
3. Chốt phản hồi đã kiểm tra và cập nhật `OpportunityAssistance` trong transaction cùng turn/response.
4. Dùng trạng thái đã cập nhật cho lần trả lời tiếp theo.

Điều này giữ observation độc lập đầu tiên dù phản hồi ngay sau đó có gợi ý. Lượt sửa sau gợi ý không tạo observation độc lập mới. Hướng dẫn thuần định dạng, không có nội dung dạy, có thể mang `assistance_provided=false`.

Khi nối runtime, Member 1 cần lưu cờ vào DB và đọc lại khi resume/retry; truy vấn nhận diện bài luyện gần/outcome cũng phải dùng lịch sử trợ giúp, bao gồm explanation mức 0. Không dựng lại cờ false từ một request mới. Helper đã được kiểm tra nhưng runtime hiện chưa có luồng explanation/RAG hoặc cột DB mới.

`assistance_provided` do server/policy quyết định từ nội dung thực sự được chốt cho người học; browser hoặc LLM không được tự cấp quyền “độc lập”. Nội dung sinh tự do vẫn cần guard sư phạm của Member 3.

## 3. C04 — Quyền truy xuất theo cặp concept–skill

Vấn đề cũ: hai danh sách riêng cho concept và skill vô tình cấp quyền cho mọi tổ hợp giữa chúng.

Thay bằng `allowed_targets`:

```json
[
  {"concept_id": "A02", "skill_id": "SK-A02-DISTRIBUTE"},
  {"concept_id": "N01", "skill_id": "SK-N01-SIGNED-ADD"}
]
```

Query `A02` + `SK-N01-SIGNED-ADD` bị từ chối, dù từng ID riêng lẻ xuất hiện trong danh sách. Các cặp trùng hoặc hai danh sách legacy đều bị từ chối.

Server phải dựng scope bằng `ServerRetrievalScope.from_registry(registry, **data)`: factory kiểm tra **mọi** cặp được cấp, kể cả cặp không dùng ở query hiện tại. Policy/graph xác định tập cặp được phép; registry xác nhận quan hệ concept–skill. Cả hai bước đều cần thiết.

Schema thuần không có bản registry để tự đối chiếu; gọi constructor trực tiếp chỉ kiểm tra hình dạng và tính duy nhất. Adapter phải dùng factory trên state server đáng tin cậy. Manifest snapshot và duyệt nội dung thật vẫn thuộc chặng đồng bộ/retrieval sau này.

## 4. C05 — Báo cáo đúng khi phiên học xen kẽ

`SkillReport` thêm:

- `session_observation_ids`: ID observation của đúng session/skill, không trùng.
- `other_session_observations`: số observation của phiên khác xen giữa hai mốc snapshot.

Các điều kiện:

```text
session_observations = số ID observation riêng của phiên/skill
evidence_count_after - evidence_count_before
    = session_observations + other_session_observations
valid_observations = tổng session_observations của các skill
```

Một observation không được tính cho hai skill trong cùng report. Count âm, count lùi, thiếu ID, ID trùng hoặc tổng sai đều bị từ chối.

Ví dụ: count toàn hồ sơ bắt đầu 5; phiên A tạo observation → 6; phiên B tạo observation → 7; phiên A tạo observation → 8. Report A lưu hai ID của A, `session_observations=2`, `other_session_observations=1`, count trước/sau 5/8. Không tính observation của B vào số bài/observation của A.

Server lấy các ID bằng join observations → opportunities theo session/skill, đối soát với DB và snapshot đúng parameter version. Việc ID đúng kiểu UUID chưa xác thực nó thuộc session; hợp đồng không thay thế truy vấn/kiểm soát quyền.

Mastery trước/sau phản ánh state quanh observations của phiên, có thể chịu tác động của phiên xen kẽ. Khi `other_session_observations>0`, UI phải nói rõ điều này, không gán toàn bộ delta cho phiên A hoặc coi là learning gain. Nếu phiên không có observation riêng, giữ cùng snapshot đã lưu cho cả trước/sau và không lấy state mới từ phiên khác để tạo tiến bộ.

## 5. Kiểm tra và điểm dừng

Các regression mới kiểm tra ba lỗi gốc, retry trợ giúp, lời nhắc định dạng, sai opportunity, không hồi tố hỗ trợ vào bài vừa nộp, cặp registry không hợp lệ, ID observation trùng và report không có bằng chứng mới.

Lệnh kiểm tra và kết quả thực tế: [verification-fixes.json](verification-fixes.json). Nội dung/pilot, dữ liệu và ID legacy, migration cũ cùng artifact contract 0.1.0 được đối chiếu hash để bảo đảm giữ nguyên.

Dừng tại bản sửa/review Chặng 1. Chặng 2 chưa bắt đầu.
