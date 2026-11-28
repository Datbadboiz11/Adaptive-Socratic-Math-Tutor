# N03 — Bản nháp Chặng 5

Trạng thái: chờ review độc lập; chưa xuất bản KB.

Tính biểu thức trong ngoặc trước. Ngoài ngoặc, thực hiện nhân và chia trước cộng và trừ. Các phép nhân/chia cùng mức, hoặc cộng/trừ cùng mức, thực hiện từ trái sang phải. Không đổi vị trí các phép trừ hay chia nếu chưa có phép biến đổi hợp lệ.

## Bài tập và bước chuẩn

- `D-N03-S5-R001-P-01`: `8 + 3*4` → `8 + 12` → `20`; đáp án `20`.
- `D-N03-S5-R001-P-02`: `25 - 2*7` → `25 - 14` → `11`; đáp án `11`.
- `D-N03-S5-R001-P-03`: `(8 + 3)*4` → `11*4` → `44`; đáp án `44`.
- `D-N03-S5-R001-P-04`: `30/(7 - 2)` → `30/5` → `6`; đáp án `6`.
- `D-N03-S5-R001-P-05`: `24/3*2` → `8*2` → `16`; đáp án `16`.
- `D-N03-S5-R001-P-06`: `18 - 7 + 2` → `11 + 2` → `13`; đáp án `13`.
- `D-N03-S5-R001-X-01`: `6 + 2*5` → `6 + 10` → `16`; đáp án `16`.
- `D-N03-S5-R001-X-02`: `(6 + 2)*5` → `8*5` → `40`; đáp án `40`.
- `D-N03-S5-R001-X-03`: `36/6*3` → `6*3` → `18`; đáp án `18`.

## Mẫu lỗi cần review

- `D-N03-S5-R001-ERR-01` trên `D-N03-S5-R001-P-01`: `11*4` → `44`. Bước sai đầu: 1. Có thể đã cộng trước khi nhân. Trong biểu thức không có ngoặc, phép nhân và phép cộng được ưu tiên thế nào?
- `D-N03-S5-R001-ERR-02` trên `D-N03-S5-R001-P-05`: `24/(3*2)` → `4`. Bước sai đầu: 1. Có thể đã tự thêm ngoặc vào chuỗi chia rồi nhân. Hai phép chia và nhân cùng mức được thực hiện từ phía nào?

## Thang gợi ý

1. Em thấy dấu ngoặc hoặc những nhóm phép toán nào trong biểu thức?
2. Xác định phần trong ngoặc trước; sau đó phân biệt nhóm nhân/chia với nhóm cộng/trừ.
3. Mỗi dòng chỉ tính một phép được ưu tiên, chép nguyên phần còn lại. Với các phép cùng mức, bắt đầu từ bên trái.

Checker chỉ xác minh tính tương đương số học. Người review kiểm thêm mục tiêu đo, thứ tự thao tác, tiếng Việt, nguồn và tiết lộ; đúng đáp án cuối chưa đủ xác minh quá trình làm bài.
