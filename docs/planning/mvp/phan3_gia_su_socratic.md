# Phần 3 — Xử lý Toán và gia sư Socratic

**Trạng thái:** Đã triển khai luồng kỹ thuật và kiểm chứng OpenAI thật; còn chờ duyệt chuyên môn nội dung/gợi ý. Xem [bàn giao Phần 3](../../implementation/mvp/phase3/README.md).
**Đầu vào:** Nội dung và grammar phần 1, lưu trữ phần 2.  
**Mục tiêu:** Phản hồi dựa trên xác minh toán và bằng chứng phiên, không dựa trên kịch bản UI.

## 1. Validator trước, phản hồi sau

- [x] Parser chỉ nhận grammar đã công bố; có giới hạn độ dài/độ phức tạp và timeout. Không dùng `eval` hoặc đưa input thô vào parser không kiểm soát.
- [x] Dùng SymPy kết hợp luật theo dạng để kiểm tra nghiệm và tương đương giữa hai bước trong miền hỗ trợ.
- [x] Tìm bước sai đầu tiên; không cộng các bước sai kéo theo thành nhiều lỗi mới.
- [x] Chấp nhận cách biến đổi hợp lệ khác lời giải mẫu; không so khớp chuỗi với đáp án duy nhất.
- [x] Phân biệt `correct`, `incorrect`, `unclear`, `unverified`, `out_of_scope`; trường hợp chưa kiểm chứng không mặc định là sai.
- [x] Diagnosis chỉ đề xuất giả thuyết như lỗi phân phối ở trạng thái `suspected`, có tham chiếu bước giải.

## 2. Observation và BKT tối thiểu

- [x] Xác định một opportunity bằng bài/nhiệm vụ và skill đích, không bằng mỗi lượt chat.
- [x] Chỉ kết quả đầu tiên xác minh được, đủ điều kiện theo protocol, chưa nhận hỗ trợ làm lộ bước cần đánh giá mới tạo observation chuẩn.
- [x] Sửa sau hint được ghi `assisted_correct`, không tăng observation chuẩn; sửa trước hint cũng không ghi observation thứ hai cho cùng opportunity/skill.
- [x] Input mơ hồ, ngoài phạm vi hoặc chưa xác minh không cập nhật BKT.
- [x] Bài luyện gần sau ví dụ được ghi rõ nguồn/quan hệ; không tự coi là observation độc lập chỉ vì có ID mới.
- [x] Lưu dự đoán trước cập nhật, trạng thái sau cập nhật, evidence count và parameter version. Agent/LLM không được trực tiếp sửa mastery.
- [x] Dùng tham số khởi tạo có nguồn và version, ghi rõ chưa hiệu chỉnh cho người học Việt Nam; không tuyên bố đã fit chỉ vì có dataset.
- [x] Kiểm thử công thức bằng ví dụ tính tay và replay từ log; kiểm tra tính duy nhất cùng phần 2.

Việc fit/benchmark ASSISTments và so sánh baseline nằm ở giai đoạn tiếp sau, không chặn luồng G2. BKT tối thiểu chỉ chứng minh cơ chế cập nhật có thể tái lập, chưa chứng minh chất lượng dự đoán.

## 3. Luồng điều phối đã triển khai

```text
Nạp session + kiểm tra request + claim turn job
→ LangGraph: parse/xác minh → xem trước eligibility → policy
→ Chọn hint/mẫu draft theo skill và mức hỗ trợ
→ OpenAI chọn cách diễn đạt trong danh sách hữu hạn
→ Guard kiểm tra câu trả lời; dùng mẫu draft nếu không đạt
→ Lưu checkpoint và kết quả đã chuẩn bị
→ Transaction: kiểm tra lại version/eligibility → observation/BKT nếu đủ điều kiện
→ Lưu turn/decision, commit job và response cache
```

Các node LangGraph và checkpoint PostgreSQL đã nối với kết quả lượt. Bước gọi model nằm ngoài transaction cập nhật BKT để không giữ khóa cơ sở dữ liệu khi chờ HTTP. Đây là luồng policy tối thiểu; không tuyên bố đã hoàn thiện Agent sử dụng KG/RAG của PRD.

## 4. Hành vi gia sư

| Tình huống | Cách xử lý |
|---|---|
| Sai bước phân phối | Hỏi tập trung vào số hạng chưa được nhân; tránh đưa nghiệm |
| Đúng độc lập | Xác nhận bài học sinh đã đưa ra; đề nghị bài tiếp theo |
| Đúng sau hỗ trợ | Xác nhận và lưu riêng kết quả có hỗ trợ |
| Chưa rõ/chưa xác minh | Hỏi học sinh viết lại hoặc bổ sung bước; không chấm sai |
| Xin đáp án/bỏ qua policy | Giữ cách hỗ trợ gợi mở, không đưa lời giải bài hiện tại |
| Liên tiếp chưa tiến triển | Theo giới hạn đã chốt: ví dụ khác, luyện nền hoặc cho dừng; có đường quay lại |
| Timeout/phản hồi không đạt | Dùng mẫu thử nghiệm phù hợp state; log rõ nguồn fallback `draft_template` |

Giới hạn ban đầu đề xuất tối đa 3 lượt gợi ý không có tiến triển trước khi mời đổi cách hỗ trợ hoặc nghỉ. Đây là cấu hình cần nhóm chốt, không phải ngưỡng nghiên cứu đã được chứng minh.

## 5. Kiểm tra phản hồi

Không chỉ dùng prompt để bảo đảm đúng. Guard kiểm tra schema, hành động và câu trả lời khớp chính xác một trong các mẫu cho phép. Model không được tự sinh phép biến đổi hoặc lời giải; chất lượng toán và sư phạm của các mẫu vẫn cần người có chuyên môn duyệt. Khi model lỗi hoặc trả ngoài danh sách, dùng mẫu thử nghiệm và ghi nguồn fallback.

Nội dung học sinh là dữ liệu, không được ghi đè system policy hay cấp quyền cập nhật state. API key ở server. Chỉ gửi nội dung cần thiết cho model.

## 6. Điều kiện xong

- [x] Ca chuẩn phát hiện đúng bước 1; không tự xuất nghiệm `x = 8` trước khi học sinh đưa đáp án.
- [x] Cách giải hợp lệ khác được chấp nhận trong phạm vi công bố.
- [x] Không có observation thêm sau hint, retry hoặc resume.
- [x] Có ít nhất một lượt chạy bằng LLM thật và bằng chứng; lượt fallback ghi rõ nguồn.
- [x] Log truy vết được validation → evidence → action → response.
- [x] Tham số, prompt, nội dung và validator có version; giới hạn còn lại được ghi rõ.

## 7. Giới hạn triển khai và việc còn mở

- [ ] Người có chuyên môn duyệt bài, hint và mẫu phản hồi; hiện giữ nhãn `draft`/`draft_template`, không giả nhận `reviewed_fallback`.
- Model hiện chọn cách diễn đạt trong catalog hữu hạn; chưa cho sinh lời giải hoặc ngôn ngữ toán tự do.
- BKT dùng tham số giả định kỹ thuật có nguồn/version, chưa fit hoặc benchmark dataset.
- Inference chạy trước transaction cập nhật BKT để tránh giữ khóa DB khi đợi model; eligibility được kiểm tra lại lúc commit.
- Phiên cũ của Phần 2 vẫn chỉ lưu trữ. Xem [kiến trúc](../../implementation/mvp/phase3/ARCHITECTURE.md) và [kiểm tra](../../implementation/mvp/phase3/TESTING.md) cho chi tiết và bằng chứng.
