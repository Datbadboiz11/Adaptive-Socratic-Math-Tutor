# BKT baseline — kết quả dev v1

Lần chạy ngày **03/10/2026**, theo [protocol v1](observation-protocol.md) và [kế hoạch tổng](../../planning/project-plan.md), mục 11 và 16. Đây là mốc dữ liệu/nghiên cứu sau MVP, chưa phải hoàn thành KG/RAG hoặc nghiệm thu toàn đồ án.

## Dữ liệu sau tiền xử lý

| Chỉ số | Kết quả |
|---|---:|
| Actions nguồn, đủ 10 file | 942.816 |
| Observations giữ lại | 121.958 |
| Học sinh có observation hợp lệ | 1.708 |
| Train | 85.011 observations / 1.195 học sinh / 85 skill |
| Dev | 18.465 observations / 256 học sinh / 84 skill |
| Test đã tạo, chưa đánh giá | 18.482 observations / 257 học sinh / 84 skill |

Phân chia theo học sinh, tỷ lệ 70/15/15, seed `20261003`. Một học sinh trong audit không còn observation hợp lệ sau lọc. Raw skill chưa được map thành concept tiếng Việt.

| Quyết định theo thứ tự ưu tiên | Actions |
|---|---:|
| Thiếu/không rõ skill | 78.103 |
| Repeated problem exposure | 510.618 |
| Không phải bài gốc hoặc scaffold | 211.096 |
| Hint hoặc có hỗ trợ ghi nhận | 20.978 |
| Context hỗ trợ trước trong cùng assistment hoặc không rõ | 63 |
| Giữ observation đầu tiên hợp lệ | 121.958 |

Các lý do loại là **loại trừ nhau theo precedence**, không phải số lượng tất cả các thuộc tính cùng xuất hiện. Ví dụ hint ở lần trả lời lặp được đếm trong repeated exposure. Số dòng giữ/loại cộng đúng số actions nguồn. Không có action ID duplicate/conflict được phát hiện trong run này; ca đó có kiểm thử synthetic riêng.

Chi tiết source SHA-256, số dòng và split tại [báo cáo preprocessing](assistments2017_preprocessing_v1.json). Dataset gốc bất biến; mỗi lần chạy tạo thư mục mới.

## Fit và kết quả

Chỉ fit bằng train, likelihood dự đoán trước đáp án, không quên. Có 75 skill fit riêng và 10 skill dùng pooled vì không đủ support. Trên dev, 18.378 observations dùng tham số skill riêng, 87 dùng pooled. Không có fallback do không hội tụ trong lần chạy này.

| Mô hình | Log loss ↓ | AUC ↑ | Brier ↓ | ECE 10 bins ↓ |
|---|---:|---:|---:|---:|
| BKT MLE | 0,649722 | 0,664844 | 0,228987 | 0,019659 |
| Tỷ lệ đúng theo skill từ train | 0,667305 | 0,623688 | 0,237447 | 0,024296 |
| History-rate từ các đáp án trước | 0,667422 | 0,644734 | 0,236327 | 0,038962 |

Đây là metric micro trên cùng 18.465 observations dev. Metric macro theo skill và calibration bins được lưu trong [báo cáo BKT dev](assistments2017_bkt_dev_v1.json). AUC không có hai lớp được để `null` và không gộp vào macro-AUC; số skill có metric được báo rõ.

BKT có kết quả dev tốt hơn hai baseline trong cấu hình v1. Chưa có khoảng tin cậy hoặc đánh giá test để kết luận mức cải thiện đáng tin cậy trên nguồn này. Không suy ra hiệu quả Socratic, phát hiện misconception, learning gain hoặc độ chính xác mastery của người học Việt Nam từ bảng này.

**35/75 fit riêng có tham số chạm biên.** Cần kiểm tra support, chuỗi quá ngắn, tính nhận diện tham số và độ nhạy của giới hạn trên dev. Pooled fit có cả ba khởi tạo hội tụ và không chạm biên. Không tự nới biên hoặc chọn model theo test.

## Kiểm chứng và giới hạn

Hồi quy cuối ngày 03/10/2026: **87 tests passed**, gồm backend với PostgreSQL thật và 13 tests nghiên cứu, có NumPy/SciPy. Thời gian pytest 41,16 giây. XML của run ở `data/test-runs/` nên không thay evidence MVP cũ. Kiểm tra Markdown links, Python compile, diff whitespace và hash source của báo cáo cũng qua.

- Regression kiểm tra first response, hint trước/sau, scaffold, lặp xuyên assignment, action duplicate/conflict, context assistment, thứ tự mơ hồ và split disjoint.
- Công thức prediction/update đối chiếu backend và phép cộng xác suất các đường trạng thái ẩn; analytic gradient đối chiếu sai phân hữu hạn.
- Benchmark có kiểm thử ngăn mở `test.csv`, kiểm tra fit chỉ nhận chuỗi train, prediction không dùng đáp án hiện tại và state mới cho học sinh mới.
- Source code, cấu hình, support, môi trường và artifact hashes được ghi trong báo cáo local. CI cài dependency nghiên cứu để chạy cả optimizer tests.
- `pyBKT` parity: **NOT RUN**, thư viện chưa có và pip trong môi trường Codex bị chặn. Engine lần này là constrained MLE NumPy/SciPy; không mô tả là đã fit bằng pyBKT.
- Protocol chỉ bảo đảm không có trợ giúp được ghi nhận trước observation được giữ; không quan sát trợ giúp ngoài log, nội dung họ bài hoặc tri thức tiềm ẩn thật. Sự học trong hint/scaffold bị loại chưa được BKT chuẩn mô hình hóa.

## Đã hoàn thành và việc tiếp theo

Đợt này hoàn thành quy tắc observation có version, preprocessing đủ nguồn, student split/manifest, fit train-only, hai baseline, dev metrics, artifact local và hướng dẫn tái lập. Các tham số nghiên cứu chưa thay [bootstrap sản phẩm](../../../content/bkt.bootstrap.v1.json).

Tiếp theo theo kế hoạch tổng:

1. Đối chiếu pyBKT khi có môi trường cài thư viện; phân tích các skill chạm biên và sensitivity trên dev bằng run/version mới.
2. Hoàn thiện registry 40 concept và 8–10 concept đại diện, prerequisite, nội dung, hints, validator/test và quy trình review chuyên môn.
3. Tích hợp Knowledge Graph và RAG vào Agent; ghi edge/content IDs và lý do can thiệp, có fallback và backtrack/return.
4. Khóa model/protocol và scripts trước thực nghiệm cuối; khi đó mới đánh giá test, bootstrap theo học sinh và công bố giới hạn.

Junyi là benchmark bổ sung; FoundationalASSIST chưa được cấp không chặn phần chính. Cách chạy và vị trí tất cả đầu ra nằm trong [runbook](RUNBOOK.md).
