# ASSISTments 2017 — protocol v1

Protocol: `assistments2017-first-original-v1`. Cấu hình có version tại [assistments2017.v1.json](../../../research/config/assistments2017.v1.json). Đây là protocol cho benchmark log công khai, không thay thế eligibility của tutoring engine tiếng Việt.

## Nguồn và nhãn

Chỉ dùng mười `student_log_*.csv` của Competition Training Set. Không nối alternative full release; không dùng nhãn STEM trong hai file label cuộc thi. [Mô tả cuộc thi](https://sites.google.com/view/assistmentsdatamining/data-mining-competition-2017) xác định mục tiêu cấp học sinh của cuộc thi, khác bài toán dự đoán câu trả lời kế tiếp của đồ án.

Theo [mô tả cột chính thức](https://docs.google.com/spreadsheets/d/1QVUStXiRerWbH1X0P11rJ5IsuU2Xutu60D1SjpmTMlk/edit), `actionId` định danh hành động, `problemId` định danh bài, `assistmentId` định danh bài nhiều phần, `startTime` là UNIX seconds, `correct` là tính đúng của câu trả lời, `original` phân biệt bài gốc với scaffold, `hint` nhận diện hành động hint và `hintCount` đếm hint đã xin. `attemptCount` được mô tả là số bài đã làm trong tutor; không dùng nó để suy ra lần trả lời đầu tiên.

Target v1 là **tính đúng của câu trả lời đầu tiên được ghi nhận trên bài gốc, không có hỗ trợ được ghi nhận trước đó**. Không khẳng định đây là lần đầu học sinh từng thấy bài, biết mọi hỗ trợ ngoài log, hoặc có nhãn ground truth mastery/misconception. Việc chấm `correct` dựa trên nguồn dữ liệu, không được gọi là xác minh SymPy của backend.

## Tạo observation

1. Đọc streaming các cột cần thiết vào SQLite local, hash ID để liên kết. Hash không bảo đảm ẩn danh; toàn bộ bản ghi vẫn ở thư mục Git ignore.
2. Kiểm tra header, định danh/context, số nguyên thời gian/action, skill và cờ nhị phân. `noskill`, nhãn thiếu/không xác định hoặc skill ghép chưa tách được bị loại. Không suy skill từ nội dung hoặc mastery có sẵn.
3. Action ID lặp với dữ liệu cần dùng giống nhau: chỉ giữ bản đầu. Cùng action ID nhưng nội dung khác: loại mọi bản có ID đó. Không lấy bản cuối ghi đè bản đầu.
4. Nhóm theo student–problem xuyên suốt cả mười file, sắp theo `startTime`, `actionId`, vị trí nguồn. Chỉ action đầu có thể tạo observation. Thay assignment hoặc quay lại bài không tạo observation mới trong v1.
5. Nếu action đầu thiếu nhãn, xin hint, scaffold hay không hợp lệ thì **không đẩy câu trả lời sau lên làm observation đầu tiên**. Thứ tự action/time bất đồng tại lần đầu cũng bị loại; timestamp thiếu ở bản ghi đầu không được bỏ qua để lấy bản ghi sau.
6. Giữ `original=1`, `scaffold=0`, `hint=0`, `hintCount=0`, `bottomHint=0`, `correct` trong `{0,1}`. Hint/scaffold hoặc context không rõ trước đó trong cùng student–assistment loại ứng viên. Hint xuất hiện sau câu trả lời đầu không làm thay đổi nhãn đã quan sát.
7. Một student–problem tạo tối đa một opportunity và một observation đo raw skill được gắn trên action đó. Mỗi dòng có lý do giữ/loại trong `decisions.csv`.

V1 cố ý bảo thủ: bỏ repeated exposure, scaffold và nhiều tương tác học có hỗ trợ. Nó chưa mô hình hóa sự học xảy ra ở các lượt bị loại. BKT ở observation kế tiếp vẫn có thể chịu tác động của hướng dẫn xen giữa; phải báo giới hạn này, không coi các bản ghi giữ lại là mẫu ngẫu nhiên của toàn bộ hoạt động học.

## Split và giữ test

- Sau bước chuẩn hóa, xếp hash ID học sinh bằng seed `20261003`, phân 70% train, 15% dev, còn lại test; làm tròn xuống train/dev. Không chia theo dòng hoặc dùng correctness để phân tầng.
- Toàn bộ observations của một học sinh thuộc một tập. Trong tập giữ thứ tự thời gian/action; mỗi student–skill bắt đầu bằng prior mới.
- Manifest và SHA-256 được lưu cùng run. Benchmark kiểm tra hash của train/dev/config/manifest trước khi fit. Lệnh benchmark **không mở `test.csv`**; việc tạo test và thống kê chất lượng đầu ra không phải đánh giá model trên test.
- Đây là split theo học sinh mới, chưa phải tổng quát hóa sang họ bài mới. Dataset hiện không cung cấp ánh xạ họ mẫu đủ căn cứ. Chia theo `template_family_id` áp dụng riêng cho bộ bài/bước giải tiếng Việt tự biên soạn.
- Có thể giữ các skill Hình học trong benchmark công khai, nhưng không map chúng thành nội dung sản phẩm; phạm vi sản phẩm vẫn loại Hình học.

## BKT và baseline

Fit no-forgetting BKT với likelihood dự đoán **trước** câu trả lời, chỉ dùng train. NumPy/SciPy tối ưu L-BFGS-B với analytic gradient; chọn trong ba điểm khởi tạo theo likelihood train và chỉ chấp nhận run hội tụ. Các giới hạn `prior=[.001,.999]`, `learn=[0,.5]`, `guess/slip=[.001,.49]` là lựa chọn v1 đã khai báo, không phải định luật BKT. Báo tham số chạm biên để phân tích trên dev.

Skill đủ 100 observations, 20 student–skill sequences và ít nhất 10 mẫu mỗi lớp được fit riêng. Các skill khác hoặc không hội tụ dùng pooled BKT fit từ các chuỗi student–skill train; không nối mọi skill thành một chuỗi. Skill chưa xuất hiện trong train dùng pooled. Cả bộ tham số nguồn lẫn lý do fallback được lưu local.

So sánh với tỷ lệ đúng theo skill train (Laplace smoothing) và history-rate dùng các câu trả lời **trước lượt hiện tại**, shrink về tỷ lệ train với trọng số 2. Không refit trên dev. V1 báo log loss, AUC có xử lý ties/null khi thiếu lớp, Brier và calibration 10 bins, micro và macro theo skill. Kết quả dev không phải kết quả test chính thức; khoảng tin cậy theo học sinh sẽ làm ở đợt thực nghiệm.

Kế hoạch ưu tiên [pyBKT](https://github.com/CAHLR/pyBKT). Môi trường hiện chưa có thư viện và kết nối pip bị chặn, nên lần này dùng MLE thay EM của thư viện. Có [lệnh đối chiếu pyBKT](../../../research/bkt/check_pybkt.py) trên chuỗi synthetic khi cài được; hiện trạng phải ghi `NOT RUN`. Gradient được so với sai phân hữu hạn; prediction được so với tổng xác suất các đường trạng thái ẩn và với backend hiện có. Các kiểm tra đó không thay thế đối chiếu pyBKT.

Không tự đưa tham số ASSISTments vào [bootstrap sản phẩm](../../../content/bkt.bootstrap.v1.json). Mapping raw skill–skill Việt Nam và hiệu chỉnh trên người học Việt Nam là công việc riêng.
