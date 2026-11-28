# Hướng dẫn gán nhãn Chặng 5 — bản pilot

Phạm vi hiện hành là [13 concept Member 2](member2-13.v1/manifest.json), gồm 156 query dev có nội dung đã duyệt và 195 candidate cần chấm. Pilot có 26 query/39 judgment, kèm [tài liệu đọc nguyên văn](member2-13.v1/pilot-review.md). 27 concept khác chờ chủ sở hữu bàn giao và không chặn lượt review này. Nhãn không được suy ra từ điểm cosine hoặc thứ tự ID.

## Đơn vị chấm và nhãn

Đơn vị là **query + phạm vi server + content ID/version/hash**. Đọc đầy đủ ý định, concept/skill, purpose, mức hint, lớp, bài đang học và exclusions trước khi đọc teaching text.

| Nhãn | Ý nghĩa |
|---|---|
| `null` | Chưa chấm; không được thay bằng 0 để chạy metric |
| 0 | Không giúp giải quyết ý định được hỏi, dù cùng concept |
| 1 | Giúp một phần; còn thiếu phần cốt lõi hoặc điều kiện mà query yêu cầu |
| 2 | Trực tiếp giải quyết ý định, đúng toán và phù hợp mức hỗ trợ/scope |

Review/disclosure/scope là điều kiện bắt buộc. Candidate bị cấm không được cho điểm dương hoặc thêm vào danh sách chỉ vì giống nghĩa. Nếu corpus chứa draft/private hoặc văn bản sai toán, dừng chấm query đó, đặt `query_accepted: false`, ghi lý do và yêu cầu revision; không dùng nhãn relevance để che lỗi publication.

Hint ở mức thấp có thể chỉ giúp một phần query yêu cầu chiến lược. Không mặc định hint cùng concept là grade 2. Ví dụ đúng toán nhưng không làm rõ hiểu nhầm được hỏi có thể là grade 1 hoặc 0. Chấm theo văn bản thực tế, không theo tên chunk.

## Quy trình hai người độc lập

1. Mỗi người tạo file mới với slot A hoặc B bằng CLI. Điền `reviewer`, `reviewed_at` ISO 8601 có múi giờ và giữ `method: independent_human` chỉ khi người thật đã chấm độc lập. File template không phải chữ ký hoặc review đã diễn ra.
2. Với từng query, kiểm wording có rõ và có đo đúng ý định không; đối chiếu route và scope. Điền `checked`, `query_accepted`, `notes`. Câu mơ hồ có thể cần sửa; chưa nhận query thì công cụ không xuất nhãn đồng thuận.
3. Đọc mọi teaching chunk nằm trong `judgments`, qua đúng ID trong corpus. Điền số nguyên 0/1/2 vào `relevance`; giữ nguyên ID, version và hash. Không thêm tài liệu ngoài candidate set. Toàn bộ candidate đủ điều kiện được chấm, không chỉ top-K của một retriever.
4. Không xem file hoặc điểm của người kia trước khi hoàn tất bản nhãn độc lập. Lưu nguyên hai file đầu; chạy `compare` để nhận agreement/bất đồng. Danh tính trong JSON là ghi nhận của người nộp, phần mềm không xác minh con người ở ngoài hệ thống.
5. Nếu bất đồng, giữ cả hai nhãn gốc và ghi quyết định hòa giải/lý do ở artifact mới. CLI hiện giữ xung đột và không tự xuất qrels hợp nhất khi còn bất đồng. Việc có cùng danh tính sau chuẩn hóa chữ hoa/khoảng trắng bị từ chối.

## Các trường hợp đặc biệt

- `content_status: awaiting_reviewed_content`: chưa có corpus hợp lệ cho concept; không chấm thành query không có tài liệu liên quan. Công cụ từ chối coi review này là hoàn tất.
- `expected_route: empty`: server exclusions đã loại hết ví dụ. Khi nội dung sẵn sàng, đây là ca đo filter/fallback riêng; không gán Recall/nDCG bằng 1 vì trả rỗng.
- `clarify` hoặc `out_of_scope`: kiểm quyết định trước retrieval; không đưa vào trung bình ranking như query thông thường. `eligible_candidate_ids` trống ở đây thể hiện route dự kiến, không chứng minh retriever tự hiểu câu hỏi.
- Query có candidate nhưng tất cả được chấm 0: đây mới là ca không có tài liệu liên quan sau review. Recall/Hit/nDCG không xác định báo N/A; đánh giá fallback riêng.
- Chỉ có grade 1: nDCG có thể xác định, nhưng Recall/Hit với threshold 2 không xác định. Gain nDCG cố định 0, 1, 3 tương ứng grade 0, 1, 2.

## Split và đóng băng

Toàn bộ 156 query của gói hiện hành là dev vì cả 13 concept đã dùng cho authoring/phát triển. Không tự tách một phần paraphrase thành test. Các query cùng concept/intent hoặc có chung source/family/lineage phải cùng split, kể cả khi quan hệ nguồn xuất hiện ở hai trường metadata khác nhau.

Hiện chưa khóa test. Bộ test độc lập cần scenario/nhóm nguồn mới chưa dùng để chọn cấu hình, cùng review phương pháp và relevance độc lập. Sau khi rà đủ ứng viên, có hai bản nhãn và hòa giải, khóa query/qrels/split/KB snapshot/embedding/config **trước** lần chạy RQ3 chính thức. Các query và đáp án nghiên cứu không được xuất bản vào KB generator. Hồ sơ [coverage40.v1](coverage40.v1/manifest.json) được giữ làm lịch sử trước khi người dùng chốt phạm vi 13 concept.

Giới hạn chất lượng hiện tại: query do AI hỗ trợ soạn, chưa có truy vấn học sinh thật; mẫu dùng chung cấu trúc câu và `vi du` là lỗi gõ nhẹ. Cần người review bổ sung ngôn ngữ tự nhiên, sai thuật ngữ và điều kiện toán cụ thể trước khi coi đây là gold dataset.
