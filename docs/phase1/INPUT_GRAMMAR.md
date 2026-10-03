# Grammar nhập bài — phiên bản g2-v1

## 1. Phạm vi được chuẩn bị

Phương trình một ẩn `x`, miền số thực, bậc nhất, nghiệm duy nhất. Ba họ đề: `ax+b=c`, `a(x+b)=c`, `ax+b=cx+d`; hệ số có thể âm, nghiệm có thể nguyên hoặc hữu tỉ. Không có biến ở mẫu, lũy thừa, căn, trị tuyệt đối, bất phương trình, nhiều ẩn hoặc hệ phương trình.

Đây là đặc tả cho validator ở Phần 3. `scripts/check_phase1.py` chỉ kiểm tra file nội dung do nhóm biên soạn, không được dùng thay production validator cho input học sinh.

## 2. Cú pháp v1

```text
submission := equation (NEWLINE equation)*
equation   := expression "=" expression
expression := term (("+" | "-") term)*
term       := factor (("*" | "/") factor)*
factor     := ("+" | "-")? atom
atom       := NUMBER | "x" | "(" expression ")"
NUMBER     := 1..5 chữ số, tùy chọn dấu chấm + 1..4 chữ số
```

Giới hạn ngữ nghĩa: chỉ chia cho hằng số khác 0, chỉ nhân khi kết quả vẫn tuyến tính. Hệ thống không dùng `eval`, không gọi hàm/tên tùy ý từ input.

Chuẩn hóa có ghi log `raw`/`normalized`: bỏ khoảng trắng thừa, Unicode `−` thành `-`, `×`/`·` thành `*`, `÷` thành `/`; hỗ trợ nhân ngầm dạng `2x`, `2(x-3)` và `-3x`. Biểu thức dùng ngoặc để chỉ rõ thứ tự, chẳng hạn `(x+1)/2`. Không tự đoán `1/2x` nghĩa là `(1/2)*x` hay `1/(2x)`; yêu cầu viết rõ.

- Dùng dấu chấm cho số thập phân. `6,5` cần hỏi lại, không tự biến thành 65.
- Một phương trình trên mỗi dòng; UI tách dòng thành mảng `steps`.
- V1 chưa nhận dấu mũi tên hoặc nhiều dấu `=` trên một dòng; hướng dẫn người dùng xuống dòng.
- Dòng đề lặp lại đầu bài được lưu nhưng loại khỏi việc đánh số bước đánh giá.
- Câu trả lời chỉ có `x=8` có thể chấm kết quả task, không suy ra bước lỗi hay thành thạo phân phối.
- Chỉ `8` hoặc câu văn “em nghĩ là tám”: hỏi xác nhận định dạng; chưa dùng LLM extraction trong bản đầu.

## 3. Ngân sách đầu vào

Tối đa 12 bước, 160 ký tự/bước, bản nháp 2.000 ký tự. Parser dự kiến tối đa 80 AST node và độ sâu 12 trên một vế; giới hạn thời gian xác minh riêng (mục tiêu 1 giây ở worker). Kiểm tra kích thước trước parse; process timeout phải bảo đảm dừng công việc, không chỉ ngừng chờ coroutine. Thiết lập timeout runtime thuộc Phần 3, chưa được tuyên bố có trong skeleton hiện tại.

## 4. Quyết định theo loại input

| Ví dụ | Kết quả dự kiến | Observation |
|---|---|---|
| `2x-6=10` rồi `x=8` | `verified_correct` khi là lời giải hoàn tất hợp lệ | Có nếu thỏa protocol |
| `x-3=5` rồi `x=8` | Chấp nhận cách chia hai vế trước | Có nếu thỏa protocol |
| `2x-3=10` | `verified_incorrect`, bước 1 | Có nếu là kết quả đầu tiên đủ điều kiện |
| Chỉ `x-3=5` | Biến đổi đúng nhưng task chưa xong: `unverified`, reason `valid_partial` | Không; khuyến khích viết tiếp không lộ bước |
| `x=6.5` | Có thể xác minh nghiệm sai, `first_error_step=null` vì chưa có bước giải | Có nếu thỏa protocol; không bịa lỗi phân phối |
| Input rỗng, `x=`, `6,5` | `needs_clarification` | Không |
| `x^2=4`, `1/x=2`, `y=3` | `unverified`, reason `unsupported_scope` | Không |
| Yêu cầu bỏ policy/đưa lời giải | Xử lý như yêu cầu hội thoại, không như phương trình | Không |

Các enum bám PRD: `verified_correct`, `verified_incorrect`, `unverified`, `needs_clarification`. Không thêm `out_of_scope` làm assessment status riêng; dùng `reason_code=unsupported_scope`.

## 5. Tiêu chí nghiệm thu validator ở bước sau

Phải chấp nhận cách giải khác, tìm đúng bước sai đầu tiên, xử lý lỗi kéo theo, không chấm sai input chưa hiểu, không suy đoán misconception từ nghiệm cuối và không cho phép parser thực thi code. Bộ bài ở Phần 1 là fixtures phát triển đã biết, không dùng để tuyên bố accuracy trên test độc lập.
