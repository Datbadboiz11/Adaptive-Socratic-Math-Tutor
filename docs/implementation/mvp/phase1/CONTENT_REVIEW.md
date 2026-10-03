# Bộ 6 bài và quy trình duyệt

Nguồn chuẩn: [linear_equations.v1.json](../../../../content/linear_equations.v1.json), version `0.1.0`, split `authoring_dev`.

## 1. Nội dung đã chuẩn bị

| ID | Đề | Đáp án tham chiếu (nội bộ) | Trọng tâm lỗi minh họa |
|---|---|---|---|
| LIN-001 | `3x + 5 = 20` | `5` | Phép toán ngược khi loại hằng số |
| LIN-002 | `-2x + 7 = 15` | `-4` | Dấu khi chia cho hệ số âm |
| LIN-003 | `2(x - 3) = 10` | `8` | Chỉ nhân hệ số vào số hạng đầu |
| LIN-004 | `-3(x + 2) = 12` | `-6` | Dấu của tích khi bỏ ngoặc |
| LIN-005 | `5x - 4 = 2x + 11` | `5` | Gom số hạng chứa x mà không giữ tương đương |
| LIN-006 | `2x + 3 = 4x - 8` | `11/2` | Dấu khi loại hằng số ở bước tiếp theo |

Mỗi bài có hai cách giải, một chuỗi lỗi được định vị bước sai đầu tiên, ba gợi ý không đưa nghiệm, một ví dụ khác có lời giải, metadata nguồn/họ/skill và review. Ví dụ khác có nghiệm khác bài đang làm để tránh vô tình lộ nghiệm; cùng họ vẫn được đánh dấu luyện tập gần theo protocol.

Toàn bộ là bài tự biên soạn có AI hỗ trợ. Không lấy từ log ASSISTments/Junyi, không dùng dữ liệu người học và không tự ghi người review là giảng viên.

## 2. Kiểm tra tự động làm được gì?

`scripts/checks/check_phase1.py` dùng số hữu tỉ chính xác và bộ đánh giá AST giới hạn để kiểm tra nghiệm, tương đương của tất cả bước trong 12 cách giải, vị trí lỗi của 6 chuỗi sai, lời giải 6 ví dụ khác, độ phủ ba họ và public projection không chứa đáp án/hint.

Nó không kiểm chứng mức độ phù hợp với chương trình, cách diễn đạt sư phạm, mọi biến thể lỗi thực tế hoặc khả năng tiết lộ lời giải gián tiếp của LLM. File nội dung vẫn giữ `review.status=draft` sau khi chạy, không tự đổi thành `human_approved`.

## 3. Phiếu review từng bài

Người review thực hiện cho từng ID, có thể ghi vào issue/PR rồi cập nhật metadata sau khi thực sự duyệt.

| Mục | Câu hỏi rà soát |
|---|---|
| Tính đúng | Đề có nghiệm duy nhất? Cả hai cách giải và ví dụ khác có đúng? |
| Skill | Bằng chứng phù hợp `SK-LIN-SOLVE`? Có suy rộng sang skill tiền đề không? |
| Lỗi | Bước sai đầu tiên đúng? Các bước kéo theo có bị tính thành lỗi độc lập? |
| Diagnosis | Chỉ là giả thuyết `suspected`, có thể có nguyên nhân khác? |
| Hint | Hỏi vừa đủ? Có vô tình cung cấp nghiệm hoặc toàn bộ lời giải hiện tại? |
| Phạm vi | Biểu thức có nằm trong grammar/validator dự kiến? |
| Ngôn ngữ | Học sinh hiểu được câu hỏi, không có thuật ngữ kỹ thuật dư thừa? |
| Ví dụ hỗ trợ | Khác bài hiện tại, rõ nhãn, lưu quan hệ luyện tập gần? |

```text
Problem ID / content version:
Người review / ngày giờ:
Kết quả: yêu cầu sửa / đồng ý
Phép kiểm tra hoặc nhận xét:
Chỉnh sửa cần làm:
PR / commit / evidence:
```

## 4. Điều kiện phát hành nội dung

Chỉ xuất bài cho tutoring thật khi `human_approved`, reviewer/timestamp đầy đủ và họ bài được validator hỗ trợ. Phần 2 phải enforce điều kiện này phía server; frontend không phải lớp bảo vệ duy nhất. Thay đổi nội dung tạo version mới; không thay âm thầm bài mà phiên cũ đã dùng.

Sáu bài này là dữ liệu phát triển đã được xem trước. Khi đánh giá nghiên cứu cần tập test riêng theo source group/họ mẫu và quy trình trong PRD; không chia ngẫu nhiên các biến thể thay số sang train/test rồi báo khái quát hóa.
