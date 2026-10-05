# Protocol observation — g2-v1

## 1. Kỹ năng mục tiêu

Lát cắt này chỉ cập nhật một skill thô **`SK-LIN-SOLVE`: giải phương trình bậc nhất một ẩn trong phạm vi đã công bố**. Đây là mapping G2, không phải danh mục skill hoàn chỉnh của 40 concept.

Các skill tiền đề `SK-EQUALITY`, `SK-SIGNED-OPS`, `SK-DISTRIBUTE`, `SK-COMBINE-TERMS`, `SK-FRACTIONS` dùng để mô tả nội dung và giả thuyết lỗi. Chưa cập nhật BKT riêng cho chúng từ một nghiệm cuối. Muốn theo dõi phân phối riêng cần thiết kế task/step quan sát được ở phiên bản sau.

Ví dụ `2(x-3)=10 → x-3=5 → x=8` đủ chứng cứ cho task giải phương trình nhưng không chứng minh người học đã thực hiện phép phân phối.

## 2. Thuật ngữ

- **Turn:** một lần gửi hoặc yêu cầu trợ giúp, có `request_id`.
- **Opportunity:** một nhiệm vụ của một người học với bài/version và skill đích. Resume, retry, sửa bài không làm thành opportunity mới.
- **Assessment:** kết quả xác minh một lần gửi; có thể chưa xác minh/chưa rõ.
- **Observation chuẩn:** assessment đầu tiên đủ điều kiện của một opportunity/skill. Có thể đúng hoặc sai.
- **Sự kiện hỗ trợ:** hint/ví dụ/sửa sau hỗ trợ vẫn được lưu nhưng không phải observation BKT chuẩn.

## 3. Quy tắc quyết định, theo thứ tự

| Điều kiện | Eligible | Lý do |
|---|---|---|
| Đã có observation cho student/opportunity/skill | Không | `already_observed` |
| Học sinh đã nhận trợ giúp nội dung ở opportunity này | Không | `assisted` |
| Bài lặp đã từng làm, dù tạo lại ID opportunity | Không | `repeat` |
| Cùng họ với bài/ví dụ vừa được hỗ trợ trong phiên này | Không | `near_practice` |
| Chưa có kết quả xác minh đúng/sai | Không | `not_verified` |
| Chưa quy được bằng chứng về skill/task đích | Không | `not_target_evidence` |
| Kết quả đầu tiên độc lập, đã xác minh, phù hợp skill | Có | `first_independent_verified` |

Chính sách G2 bảo thủ: các bài cùng họ vừa nhận hỗ trợ trong cùng phiên đều là luyện tập gần; chưa dùng thời gian chờ để tự đổi nhãn. Một bài khác họ có thể đủ điều kiện nếu chưa hỗ trợ ở bài đó và chưa làm trước, nhưng chỉ là bằng chứng tiếp theo theo protocol, không chứng minh chuyển giao mạnh/nhân quả học tập.

## 4. Ma trận nguồn bài

| Bài | Họ/source group | Quan hệ cần lưu |
|---|---|---|
| LIN-001, LIN-002 | `F-AX-B-C` / `G-LIN-ISOLATE` | Cùng họ; sau hỗ trợ một bài, bài còn lại là `near_practice` trong phiên |
| LIN-003, LIN-004 | `F-A-XB-C` / `G-LIN-DISTRIBUTE` | Áp dụng cùng quy tắc với ví dụ có ngoặc |
| LIN-005, LIN-006 | `F-AXB-CXD` / `G-LIN-BOTH-SIDES` | Áp dụng cùng quy tắc với x ở hai vế |

Bài đầu: `initial`. Bài khác họ: `cross_family`, có `related_problem_id`. Bài đã làm: `repeat`. Metadata `source_group` giữ ổn định khi thay số/version nội dung để chống tạo ID mới nhằm tăng evidence.

## 5. Ví dụ nhiều lượt

1. LIN-003, chưa trợ giúp, gửi `2x-3=10`: observation sai thứ nhất nếu xác minh và mapping hợp lệ.
2. Tutor hỏi gợi mở: tăng mức hỗ trợ, observation vẫn là 1.
3. Sửa thành `x=8`: lưu `assisted_correct`, không thêm observation.
4. Chuyển LIN-004 sau hỗ trợ cùng họ: luyện tập gần, dù tự trả lời đúng cũng không tự thêm observation chuẩn.
5. Chọn LIN-005 chưa từng làm, khác họ, không có hint: có thể tạo observation thứ hai theo g2-v1.

Nếu lượt đầu mơ hồ thì chưa tiêu thụ observation; khi người học viết lại rõ mà chưa nhận gợi ý nội dung, assessment đủ điều kiện đầu tiên vẫn có thể được ghi. Hướng dẫn định dạng đơn thuần không phải hint; câu nhắc có nội dung giải toán phải ghi hỗ trợ.

## 6. Lưu trữ và kiểm soát ở Phần 2–3

- Unique constraint `(student_id, opportunity_id, skill_id)` trên observation chuẩn.
- Request idempotency theo chủ thể + endpoint + request ID; payload hash khác cho cùng key → 409.
- Lock/version guard session để quyết định eligibility không bị race condition.
- Transaction lưu observation, mastery history và dấu hoàn tất xử lý; BKT không ghi nếu transaction thất bại.
- Resume đối soát với kết quả lượt đã commit, kể cả lỗi sau DB commit nhưng trước checkpoint.
- Ghi `prediction_before`, `mastery_before/after`, parameter version và protocol version.
- Agent/LLM chỉ đề xuất hành động, không được gán mastery hoặc đổi eligibility.

Đây là đặc tả đã chốt cho triển khai, **chưa có runtime BKT hoặc DB constraint observation trong Phần 1**. Tham số BKT khởi tạo cần ghi nguồn và giới hạn; không tự gán prior/learning rate rồi gọi là đã fit từ dataset.
