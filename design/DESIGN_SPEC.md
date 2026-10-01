# Mở — Quy tắc thiết kế và bàn giao

## 1. Ý tưởng

**Mở — học từ cách nghĩ.** Một không gian học yên tĩnh, khuyến khích thử và tự sửa. Biểu tượng lá tạo liên tưởng đến tiến bộ từng chút; minh họa toán dùng đường cong và các dấu nhỏ. Đây là tên/nhận diện đề xuất cho prototype, có thể đổi khi nhóm chốt tên sản phẩm.

Giao diện ưu tiên **bài tập + hành động tiếp theo**, sau đó mới đến thống kê. Không dùng bảng xếp hạng, điểm thưởng hay phần trăm hiểu biết lớn để tạo áp lực. Màu chỉ hỗ trợ ý nghĩa; trạng thái luôn có chữ và/hoặc icon.

## 2. Màu và bề mặt

| Token | Giá trị cơ sở | Dùng cho |
|---|---|---|
| Ink | `#203A35` | Chữ chính |
| Muted | `#6F7E79` | Chú thích và nội dung phụ |
| Green | `#19594D` | Hành động chính, nhận diện |
| Green dark | `#123F36` | Hover, nền nhận diện đậm |
| Mint | `#E9F1EA` | Nền nhẹ, trạng thái tích cực |
| Paper | `#F7F8F4` | Nền ứng dụng |
| White | `#FFFFFF` | Bề mặt bài tập và panel |
| Border | `#E3E8E1` | Phân tách cấu trúc |
| Lime | `#DCEA9A` | Điểm nhấn trên nền xanh đậm |
| Peach | `#FCF0E4` | Gợi ý, kết quả có hỗ trợ |
| Blue background | `#EDF3F8` | Thông tin/chưa xác minh |

Không dùng đỏ làm phản ứng mặc định với một bài sai. Màu đất/đào đi cùng lời mời kiểm tra lại, tránh tạo cảm giác bị phán xét. Màu lỗi đậm dành cho vấn đề thao tác hoặc kết nối.

## 3. Chữ và nhịp bố cục

- Chữ UI ưu tiên sans serif có đủ dấu tiếng Việt; công thức dùng Cambria Math/Cambria/Georgia.
- Tiêu đề trang khoảng 25–32px; hero khoảng 29–39px tùy viewport. Nội dung chính cần ưu tiên khả năng đọc; chữ nhỏ dành cho nhãn phụ của bản mẫu.
- Sidebar rộng 226px ở desktop, thu về rail ở tablet và menu mở trên mobile.
- Nội dung có gutter 40px ở desktop, 18px trên mobile.
- Card bo góc 20px; nhóm lớn 22–24px; nút/input 10–12px.
- Khoảng cách theo nhịp 4/8/12/16/24/32px. Dùng border nhẹ, bóng đổ chủ yếu khi hover hoặc modal.
- Mỗi nhóm có một CTA chính; hành động tạm dừng/đổi lựa chọn có cấp độ nhẹ hơn.

## 4. Sáu màn hình

| Mã | Màn hình | Quyết định thiết kế |
|---|---|---|
| S01 | Đăng nhập | Nửa màn hình kể câu chuyện thương hiệu; form gọn. Bản mẫu chỉ chọn tên gọi, không giả vờ có xác thực thật |
| S02 | Tổng quan | Thẻ tiếp tục là ưu tiên. Người mới nhận CTA chọn chủ đề, không xuất hiện tiến trình bịa |
| S03 | Chủ đề | Bộ lọc ba miền + tìm tên. Mỗi thẻ có nội dung ngắn, thời lượng định hướng và CTA |
| S04 | Phiên học | Bên trái là đề và bài làm; bên phải là hội thoại gợi mở. Học sinh không phải đổi trang để xem hint |
| S05 | Report | Phân biệt tự làm đúng / đúng sau hỗ trợ / lần quan sát; timeline và gợi ý bước tiếp |
| S06 | Tiến trình | Tách tab kỹ năng và lịch sử. Dữ liệu ít luôn được ghi rõ; report cũ mở từ lịch sử |

## 5. Phiên học: thứ tự đọc

1. Tên chủ đề, vị trí trong phiên và tùy chọn nghỉ/kết thúc.
2. Đề bài và biểu thức ở vị trí nổi bật.
3. Vùng nhập nhiều dòng; số dòng chỉ hỗ trợ định hướng, không phải step ID chính thức từ backend.
4. Hai hành động: xin gợi ý hoặc gửi bài. Khi xử lý, khóa gửi để tránh thao tác lặp.
5. Phản hồi ngắn gần bài làm; câu hỏi dài hơn nằm trong hội thoại.
6. Khi hoàn tất, CTA chính đổi thành bài mới hoặc report.

Trên mobile, hai vùng xếp dọc; nội dung đề/bài làm giữ ưu tiên. Bản sản phẩm nên tiếp tục thử nghiệm việc chuyển focus/scroll đến câu hỏi mới khi có phản hồi, nhất là khi bàn phím đang mở.

## 6. Component và trạng thái

| Component | Trạng thái cần giữ khi chuyển sang frontend |
|---|---|
| App shell | Desktop, tablet rail, mobile menu; điều hướng đang chọn |
| Topic card | Mới, đang luyện, kết quả tìm kiếm trống |
| Answer editor | Rỗng, có nội dung, đang xử lý, hoàn tất, lỗi nhập |
| Feedback | Cần kiểm tra, hợp lệ một phần, đúng tự làm, đúng có hỗ trợ, chưa rõ, chưa xác minh, kết nối lỗi |
| Tutor bubble | Câu hỏi, phản hồi học sinh, ví dụ khác có nhãn, đang xử lý |
| Hint meter | Không hỗ trợ → mức 1–4; không phải điểm số |
| Resume card | Bài hiện tại, lưu nháp, tiếp tục đúng phiên |
| Modal | Nghỉ, kết thúc, chuyển chủ đề; focus/keyboard và Escape |
| Report metrics | Số liệu từ log; giữ giá trị 0 khi thiếu bằng chứng |
| Prototype controls | Tách khỏi giao diện học sinh và loại khỏi bản triển khai |

## 7. Ngôn ngữ giao diện

- Dùng “Em thử kiểm tra bước này” thay vì khẳng định “Em không hiểu kiến thức”.
- Dùng “Chưa xác minh được” thay vì chấm sai khi thiếu căn cứ.
- Ghi “Đúng sau hỗ trợ” nhất quán với report.
- Không hiển thị BKT, RAG, LangGraph, observation ID hoặc kết luận từ confidence LLM trong màn hình học sinh.
- Có thể xác nhận đáp án học sinh đã tự đưa ra; không tự đưa lời giải hoàn chỉnh.
- Ví dụ hỗ trợ có nhãn “Ví dụ khác” và không bị trộn với đề đang làm.

## 8. Truy cập và responsive

Có semantic buttons/links/forms, label cho input, focus ring, skip link, aria-live cho phản hồi, focus trap trong modal/drawer, đóng bằng Escape và tôn trọng reduced motion. Đã kiểm tra overflow ở 390/768/1024/1440px.

Các kiểm tra này không thay thế audit WCAG hoặc thử nghiệm thực tế với học sinh. Trước triển khai cần đánh giá tương phản chi tiết, cỡ chữ thực tế trên thiết bị học sinh, trình đọc màn hình, bàn phím ảo và cách nhập toán.

## 9. Ranh giới bản thiết kế

UI đăng nhập không có credential thật; lịch học Minh Anh là dữ liệu mẫu; các bộ đếm minh họa quy tắc chứ không chạy mô hình. Sáu topic và 12 đề demo không phải độ phủ 40 concept. Ghi nhận/tham số kỹ năng của hệ thống thật phải lấy từ API đã kiểm chứng, không sao chép trực tiếp các số mẫu.
