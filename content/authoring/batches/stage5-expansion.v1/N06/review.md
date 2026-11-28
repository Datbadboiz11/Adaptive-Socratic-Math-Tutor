# N06 — Bản nháp Chặng 5

Trạng thái: chờ review độc lập; chưa xuất bản KB.

Muốn cộng hoặc trừ hai phân số, đưa chúng về cùng một mẫu khác không bằng cách nhân cả tử và mẫu với cùng một số khác không. Khi đã cùng mẫu, cộng hoặc trừ các tử và giữ nguyên mẫu chung; sau đó rút gọn nếu có thể. Với phân số âm, giữ dấu của từng tử khi quy đồng và khi thực hiện phép trừ.

## Bài tập và bước chuẩn

- `D-N06-S5-R001-P-01`: `2/7 + 3/7` → `(2 + 3)/7` → `5/7`; đáp án `5/7`.
- `D-N06-S5-R001-P-02`: `6/11 - 2/11` → `(6 - 2)/11` → `4/11`; đáp án `4/11`.
- `D-N06-S5-R001-P-03`: `1/3 + 1/6` → `2/6 + 1/6` → `3/6` → `1/2`; đáp án `1/2`.
- `D-N06-S5-R001-P-04`: `5/8 - 1/4` → `5/8 - 2/8` → `3/8`; đáp án `3/8`.
- `D-N06-S5-R001-P-05`: `2/3 + 1/5` → `10/15 + 3/15` → `13/15`; đáp án `13/15`.
- `D-N06-S5-R001-P-06`: `-1/4 - 1/6` → `-3/12 - 2/12` → `-5/12`; đáp án `-5/12`.
- `D-N06-S5-R001-X-01`: `1/9 + 5/9` → `6/9` → `2/3`; đáp án `2/3`.
- `D-N06-S5-R001-X-02`: `3/10 - 1/5` → `3/10 - 2/10` → `1/10`; đáp án `1/10`.
- `D-N06-S5-R001-X-03`: `1/2 + 2/7` → `7/14 + 4/14` → `11/14`; đáp án `11/14`.

## Mẫu lỗi cần review

- `D-N06-S5-R001-ERR-01` trên `D-N06-S5-R001-P-01`: `(2 + 3)/(7 + 7)` → `5/14`. Bước sai đầu: 1. Có thể đã cộng cả hai mẫu khi cộng hai phân số. Khi hai phân số đã cùng mẫu, mẫu số biểu thị đơn vị phần nào?
- `D-N06-S5-R001-ERR-02` trên `D-N06-S5-R001-P-04`: `5/8 - 1/8` → `4/8`. Bước sai đầu: 1. Có thể đã đổi mẫu nhưng không nhân tử với cùng hệ số. Để đổi một phần tư sang mẫu tám mà giữ nguyên giá trị, tử số cần thay đổi thế nào?

## Thang gợi ý

1. Hai phân số đang có cùng mẫu chưa? Mẫu số của chúng có khác không?
2. Chọn một mẫu chung, rồi nhân cả tử lẫn mẫu của mỗi phân số với cùng hệ số phù hợp.
3. Viết lại hai phân số cùng mẫu trên một dòng. Cộng hoặc trừ các tử theo đúng dấu, giữ mẫu chung rồi kiểm tra rút gọn.

Checker chỉ xác minh tính tương đương số học. Người review kiểm thêm mục tiêu đo, thứ tự thao tác, tiếng Việt, nguồn và tiết lộ; đúng đáp án cuối chưa đủ xác minh quá trình làm bài.
