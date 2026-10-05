# Phiếu nghiệm thu thủ công trên frontend Phần 4

**Trạng thái: NOT RUN.** Công cụ browser của Codex bị từ chối quyền vào bản frontend mới ở cổng 3001. Không điền `PASS` từ kết quả API hoặc ảnh browser Phần 3. Ghi giờ chạy, người chạy, Git commit/build, profile/session ID và ảnh sau khi thực hiện.

| Ca | Thao tác trên web | Expected | Actual | Kết quả |
|---|---|---|---|---|
| TC01 | Phiên mới, đi đến LIN-003; nhập `2x-6=10`, `2x=16`, `x=8` | Đúng độc lập; một observation nếu chưa gặp bài | Chưa chạy trên build Phần 4 | NOT RUN |
| TC02 | Nhập `2x-3=10`, `2x=13`, `x=6.5` ở LIN-003 | Chỉ bước 1 sai; hỏi gợi mở, không lộ nghiệm | Chưa chạy trên build Phần 4 | NOT RUN |
| TC03 | Tiếp TC02, xin gợi ý rồi sửa thành `x-3=5`, `x=8` | Đúng sau hỗ trợ; không thêm observation | Chưa chạy trên build Phần 4 | NOT RUN |
| TC04 | Nhập `x=` và một bài ngoài phạm vi | Yêu cầu viết rõ/ghi chưa xác minh; BKT không đổi | Chưa chạy trên build Phần 4 | NOT RUN |
| TC05 | Gửi bài rồi mô phỏng mất response sau commit; bấm thử lại | Cùng `request_id`, một turn/observation | Chưa chạy trên build Phần 4 | NOT RUN |
| TC06 | Nhập nháp, đổi phiên; reload, tạm dừng/tiếp tục | Nháp, bài và mức hỗ trợ giữ đúng | Chưa chạy trên build Phần 4 | NOT RUN |
| TC10 | Có bài độc lập, có hỗ trợ, chưa xác minh; kết thúc và mở lại report | Số liệu khớp API và DB | Chưa chạy trên build Phần 4 | NOT RUN |

Khi chạy, dùng tối thiểu 5 ca khác nhau, ghi **input chính xác, expected, actual, PASS/FAIL, thời gian, người chạy, commit, môi trường và đường dẫn ảnh/log** cho từng ca. Một ca fail phải lưu lần fail và lần chạy lại sau sửa. Không đưa API key, token hoặc file `.env` vào ảnh/log.

Các kiểm tra tương ứng ở tầng API đã có [actual output](api-checks.json), nhưng không chứng minh trạng thái màn hình, bàn phím, focus hoặc responsive của frontend mới.
