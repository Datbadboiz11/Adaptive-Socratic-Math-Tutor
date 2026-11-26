# Đặc tả nháp cho 30 concept chưa có pack

Bảng ghi dạng đề, đầu ra cần chấm và dấu hiệu đạt theo [phạm vi trong registry](../../../../content/curriculum/registry.v2.json). Mỗi dòng dùng owner và reviewer trong [ma trận](coverage.md). Đây là đầu vào cho biên soạn và thiết kế validator. Mọi dòng đang chờ kiểm tra với bài mẫu, checker và luồng học thật.

| Concept | Dạng đề và đầu ra | Điều kiện chấm dự kiến |
|---|---|---|
| N03 | Tính biểu thức số có ngoặc hoặc nhiều phép toán. Nộp kết quả và bước trung gian. | Làm trong ngoặc trước, thực hiện nhân/chia trước cộng/trừ, giữ thứ tự trái sang phải trong cùng mức ưu tiên. |
| N05 | Quy đồng và điền quan hệ `<`, `=` hoặc `>` cho hai phân số. | Hai phân số trung gian cùng mẫu dương, mỗi phân số giữ nguyên giá trị và dấu so sánh đúng. |
| N06 | Tính tổng hoặc hiệu hai phân số. Nộp kết quả và bước quy đồng. | Giữ giá trị các phân số khi đổi mẫu, thực hiện đúng phép cộng/trừ và đơn giản hóa kết quả nếu đề yêu cầu. |
| N07 | Tính tích hoặc thương hai phân số. | Dùng đúng phép toán, xác nhận số chia khác 0 và lấy nghịch đảo của số chia khi thực hiện phép chia. |
| N08 | Đổi giữa phân số, số thập phân hữu hạn và phần trăm theo định dạng được hỏi. | Giá trị giữ nguyên và kết quả đúng định dạng đích, ví dụ có ký hiệu `%` khi đề yêu cầu phần trăm. |
| N09 | Tính lũy thừa số với số mũ nguyên. | Giữ đúng dấu theo cơ số và ngoặc. Với số mũ âm, kiểm tra cơ số khác 0 và dùng nghịch đảo. |
| N10 | Tính căn bậc hai số học của số chính phương hoặc nêu điều kiện dưới dấu căn. | Giá trị căn không âm, bình phương bằng số đã cho. Điều kiện xác định trên số thực là biểu thức dưới căn không âm. |
| A04 | Khai triển tích đơn thức với đa thức hoặc tích hai nhị thức. | Phân phối đủ các tích, thu gọn hạng tử đồng dạng và trả đa thức đã khai triển tương đương. |
| A05 | Khai triển bình phương nhị thức hoặc nhận dạng đa thức thành bình phương nhị thức. | Có đủ hạng tử chéo với đúng hệ số và dấu. Giữ đúng dạng đầu ra theo hướng yêu cầu. |
| A06 | Khai triển hoặc phân tích hiệu hai bình phương. | Nhận diện đúng hai biểu thức bình phương. Với đề phân tích, trả tích tổng và hiệu phù hợp. |
| A07 | Phân tích đa thức bằng cách đặt nhân tử chung. | Chọn nhân tử chung theo yêu cầu đề, nộp dạng tích và khai triển lại được đa thức ban đầu. |
| A08 | Phân tích đa thức bằng hằng đẳng thức hoặc nhóm bốn hạng tử. | Chỉ ra hằng đẳng thức hoặc nhóm hợp lệ, sau đó đưa về tích có khai triển đúng. |
| A09 | Rút gọn phân thức một biến và nộp điều kiện xác định ban đầu. | Biểu thức kết quả tương đương trên miền gốc. Điểm làm mẫu gốc bằng 0 vẫn bị loại sau khi khử nhân tử. |
| A10 | Cộng, trừ, nhân hoặc chia hai phân thức một biến. Nộp biểu thức và điều kiện. | Phép toán và dạng rút gọn đúng. Điều kiện loại các điểm làm mẫu gốc bằng 0 và các điểm làm phân thức chia bằng 0 khi có phép chia. |
| E03 | Từ bài toán một đại lượng chưa biết, nộp cách đặt ẩn, đơn vị, điều kiện và phương trình. | Phương trình mô tả đúng quan hệ trong đề và các đại lượng có đơn vị nhất quán. |
| E04 | Giải phương trình là tích của hai nhân tử bậc nhất bằng 0. | Xét cả hai trường hợp nhân tử bằng 0 và trả tập nghiệm đầy đủ, gộp nghiệm trùng. |
| E05 | Giải phương trình chứa ẩn ở mẫu quy về bậc nhất. | Nêu điều kiện từ mẫu gốc trước khi khử mẫu, đối chiếu từng nghiệm với điều kiện đó. |
| E06 | Giải phương trình bậc hai hệ số hữu tỉ trên số thực. | Tính biệt thức, xác định đúng số nghiệm phân biệt và nộp tập nghiệm chính xác, kể cả dạng căn khi cần. |
| E07 | Cho phương trình bậc hai có nghiệm thực, tính tổng và tích hai nghiệm. | Dùng đúng `−b/a` và `c/a`, với `a` khác 0 và điều kiện có nghiệm thực được thiết lập. |
| E08 | Giải hệ bậc nhất hai ẩn có nghiệm duy nhất bằng thế. | Thế biểu thức của một ẩn vào phương trình còn lại, rồi nộp cặp nghiệm thỏa cả hai phương trình. |
| E09 | Giải hệ bậc nhất hai ẩn có nghiệm duy nhất bằng cộng đại số. | Nhân hệ số và cộng/trừ phương trình để khử một ẩn, rồi nộp cặp nghiệm thỏa hệ gốc. |
| E10 | Giải bất phương trình bậc nhất một ẩn và nộp tập nghiệm. | Đổi chiều khi nhân/chia với số âm. Biên và dấu lấy biên khớp với toán tử của bất phương trình. |
| F02 | Tìm tập xác định thực của hàm chứa mẫu hoặc căn bậc hai. | Áp điều kiện mẫu khác 0 và biểu thức dưới căn không âm ở những vị trí tương ứng. Trả đúng giao các điều kiện. |
| F03 | Xác định hệ số góc và giá trị tại `x = 0` của `y = ax + b`. | Nêu đúng `a`, `b`, giải thích `a` là mức thay đổi của `y` khi `x` tăng 1 và `b` là `f(0)`. |
| F04 | Tìm nghiệm của hàm bậc nhất với `a` khác 0 và điền dấu trên hai khoảng. | Trả nghiệm `−b/a`, dấu đúng theo dấu của `a` và giá trị 0 tại nghiệm. |
| F06 | Tìm các khoảng đồng biến và nghịch biến của hàm bậc hai. | Xác định hoành độ đỉnh, dùng dấu của hệ số bậc hai để gán đúng chiều biến thiên ở mỗi phía. |
| F07 | Lập bảng dấu của tam thức bậc hai hoặc giải bất phương trình bậc hai. | Xử lý đúng các trường hợp không có nghiệm thực, nghiệm kép và hai nghiệm. Chọn đúng biên theo toán tử. |
| F08 | Rút gọn biểu thức lũy thừa hoặc nhận diện miền xác định của hàm mũ. | Dùng quy tắc lũy thừa trong miền hợp lệ. Với hàm mũ cơ số cố định, nêu `a > 0`, `a ≠ 1` và miền số mũ là các số thực. |
| F09 | Đổi giữa dạng logarit và dạng mũ hoặc gộp/tách biểu thức logarit. | Giữ cơ số dương khác 1 và đối số dương. Biểu thức sau biến đổi tương đương trên miền ban đầu. |
| F10 | Giải phương trình mũ cùng cơ số hoặc phương trình logarit dùng định nghĩa. | Biến đổi với cơ số hợp lệ, giải phần còn lại và đối chiếu nghiệm với điều kiện của bài gốc. |
