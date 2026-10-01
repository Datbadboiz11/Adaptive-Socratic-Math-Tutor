# Phần 3 — Xử lý Toán và gia sư Socratic

**Trạng thái:** Chưa thực hiện.  
**Đầu vào:** Nội dung và grammar phần 1, lưu trữ phần 2.  
**Mục tiêu:** Phản hồi dựa trên xác minh toán và bằng chứng phiên, không dựa trên kịch bản UI.

## 1. Validator trước, phản hồi sau

- [ ] Parser chỉ nhận grammar đã công bố; có giới hạn độ dài/độ phức tạp và timeout. Không dùng `eval` hoặc đưa input thô vào parser không kiểm soát.
- [ ] Dùng SymPy kết hợp luật theo dạng để kiểm tra nghiệm và tương đương giữa hai bước trong miền hỗ trợ.
- [ ] Tìm bước sai đầu tiên; không cộng các bước sai kéo theo thành nhiều lỗi mới.
- [ ] Chấp nhận cách biến đổi hợp lệ khác lời giải mẫu; không so khớp chuỗi với đáp án duy nhất.
- [ ] Phân biệt `correct`, `incorrect`, `unclear`, `unverified`, `out_of_scope`; trường hợp chưa kiểm chứng không mặc định là sai.
- [ ] Diagnosis chỉ đề xuất giả thuyết như lỗi phân phối ở trạng thái `suspected`, có tham chiếu bước giải.

## 2. Observation và BKT tối thiểu

- [ ] Xác định một opportunity bằng bài/nhiệm vụ và skill đích, không bằng mỗi lượt chat.
- [ ] Chỉ kết quả đầu tiên xác minh được, đủ điều kiện theo protocol, chưa nhận hỗ trợ làm lộ bước cần đánh giá mới tạo observation chuẩn.
- [ ] Sửa sau hint được ghi `assisted_correct`, không tăng observation chuẩn; sửa trước hint cũng không ghi observation thứ hai cho cùng opportunity/skill.
- [ ] Input mơ hồ, ngoài phạm vi hoặc chưa xác minh không cập nhật BKT.
- [ ] Bài luyện gần sau ví dụ được ghi rõ nguồn/quan hệ; không tự coi là observation độc lập chỉ vì có ID mới.
- [ ] Lưu dự đoán trước cập nhật, trạng thái sau cập nhật, evidence count và parameter version. Agent/LLM không được trực tiếp sửa mastery.
- [ ] Dùng tham số khởi tạo có nguồn và version, ghi rõ chưa hiệu chỉnh cho người học Việt Nam; không tuyên bố đã fit chỉ vì có dataset.
- [ ] Kiểm thử công thức bằng ví dụ tính tay và replay từ log; kiểm tra tính duy nhất cùng phần 2.

Việc fit/benchmark ASSISTments và so sánh baseline nằm ở giai đoạn tiếp sau, không chặn luồng G2. BKT tối thiểu chỉ chứng minh cơ chế cập nhật có thể tái lập, chưa chứng minh chất lượng dự đoán.

## 3. Luồng điều phối đề xuất

```text
Nạp session + kiểm tra request
→ Parse / xác minh bài
→ Xây observation đủ điều kiện
→ Cập nhật state/BKT một lần theo transaction
→ Policy chọn hành động trong danh sách cho phép
→ Lấy hint/ví dụ đã duyệt theo skill và mức hỗ trợ
→ LLM diễn đạt câu hỏi gợi mở
→ Kiểm tra phản hồi; fallback nếu không đạt
→ Lưu turn/decision, checkpoint và chờ học sinh
```

Dựng các node này trong LangGraph, nối cơ chế checkpoint với kết quả lượt đã lưu. Đây là luồng policy tối thiểu; không tuyên bố đã hoàn thiện Agent sử dụng KG/RAG của PRD.

## 4. Hành vi gia sư

| Tình huống | Cách xử lý |
|---|---|
| Sai bước phân phối | Hỏi tập trung vào số hạng chưa được nhân; tránh đưa nghiệm |
| Đúng độc lập | Xác nhận bài học sinh đã đưa ra; đề nghị bài tiếp theo |
| Đúng sau hỗ trợ | Xác nhận và lưu riêng kết quả có hỗ trợ |
| Chưa rõ/chưa xác minh | Hỏi học sinh viết lại hoặc bổ sung bước; không chấm sai |
| Xin đáp án/bỏ qua policy | Giữ cách hỗ trợ gợi mở, không đưa lời giải bài hiện tại |
| Liên tiếp chưa tiến triển | Theo giới hạn đã chốt: ví dụ khác, luyện nền hoặc cho dừng; có đường quay lại |
| Timeout/phản hồi không đạt | Dùng câu hỏi đã duyệt phù hợp state; log rõ nguồn fallback |

Giới hạn ban đầu đề xuất tối đa 3 lượt gợi ý không có tiến triển trước khi mời đổi cách hỗ trợ hoặc nghỉ. Đây là cấu hình cần nhóm chốt, không phải ngưỡng nghiên cứu đã được chứng minh.

## 5. Kiểm tra phản hồi

Không chỉ dùng prompt để bảo đảm đúng. Kiểm tra schema, phạm vi hành động, nội dung toán và tiết lộ nghiệm/lời giải. Một bộ lọc từ khóa không thể bảo đảm phát hiện mọi cách tiết lộ; khi không xác minh được, dùng hint đã duyệt. Ghi trường hợp lọt lỗi trong eval.

Nội dung học sinh là dữ liệu, không được ghi đè system policy hay cấp quyền cập nhật state. API key ở server. Chỉ gửi nội dung cần thiết cho model.

## 6. Điều kiện xong

- [ ] Ca chuẩn phát hiện đúng bước 1; không tự xuất nghiệm `x = 8` trước khi học sinh đưa đáp án.
- [ ] Cách giải hợp lệ khác được chấp nhận trong phạm vi công bố.
- [ ] Không có observation thêm sau hint, retry hoặc resume.
- [ ] Có ít nhất một lượt chạy bằng LLM thật và bằng chứng; lượt fallback ghi rõ nguồn.
- [ ] Log truy vết được validation → evidence → action → response.
- [ ] Tham số, prompt, nội dung và validator có version; giới hạn còn lại được ghi rõ.
