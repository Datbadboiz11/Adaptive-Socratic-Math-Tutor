# Chặng 6 — Phép đo dev cho 13 concept Member 2

Runner dùng code retrieval và graph sản phẩm hiện hành, PostgreSQL/pgvector thử nghiệm trong schema riêng, model embedding CPU ghim file hash và runtime version. Không gọi API model, không tạo quan sát BKT hoặc ghi session học sinh.

## Dữ liệu và phép so

| Dữ liệu | Dùng để đo | Giới hạn |
|---|---|---|
| 104 query / 169 judgment của Chặng 3 | Recall/Hit/nDCG tại K=1/3/5; phân tích theo concept/purpose | Nhãn dev tất định, chưa phải human gold |
| 156 query của Chặng 5 | Scope, candidate count, fallback, cache và latency | 195 judgment chưa chấm; không tính điểm chất lượng |
| 104 cặp Full/No-RAG | Đầu ra từ cùng graph, cùng đề, bài làm và policy; chuẩn bị chấm ẩn tên cấu hình | 39 ca bài nộp sai và 65 yêu cầu hỗ trợ, đều từ authoring/dev; không phải held-out test |

Cả hai retriever dùng cùng bộ lọc production trước xếp hạng. Một lượt query-cache cold chạy sau khi model/corpus đã làm nóng; tiếp theo có hai lượt query-cache warm. Đảo thứ tự query và comparator bằng seed cố định. Wall time bao gồm ghi trace; thời gian core được lưu riêng. Các lượt warm chỉ thêm mẫu timing, không nhân số nhãn hoặc số query độc lập khi tổng hợp chất lượng.

Các query hỏi mơ hồ/ngoài scope của bộ 156 được giữ trong output với `executed: false`: route đã được soạn trước, runner không giả vờ đã đo độ chính xác classifier. Ca loại hết ví dụ vẫn gọi retriever và đo trả rỗng riêng. Query không có grade 2 có Recall/Hit N/A; nDCG dùng gain 0/1/3 và N/A nếu mọi grade đều 0. Không thay nhãn chưa biết bằng 0.

Khoảng tin cậy của chênh lệch semantic–metadata lấy mẫu bootstrap **theo toàn bộ concept**, giữ các paraphrase cùng nhóm; chỉ phân tích cold pass có nhãn. Đây là độ nhạy trên 13 concept dev, không suy rộng thành bằng chứng hiệu quả học tập.

## Chạy

```powershell
python scripts/retrieval/run_member2_stage6.py --audit-only
python scripts/dev/validation_runtime.py database
python scripts/retrieval/run_member2_stage6.py --workspace-local
```

Lệnh cuối cần dependencies RAG và weights đã chuẩn bị theo [runbook KB](../../../content/kb/README.md). Có thể chỉ định `--output` tới một thư mục mới. Runner từ chối đích có sẵn, đối chiếu hash đầu vào trước/sau, xóa schema thử nghiệm do chính nó tạo và kiểm tra trạng thái KB phục vụ trước/sau. Không xóa file hoặc thư mục.

Kết quả nằm trong `artifacts/stage6-validation/<run-id>/`: config/nguồn đã ghim, rankings thô, report JSON/Markdown, lỗi ranking, EXPLAIN ANALYZE/BUFFERS, trace retrieval, đầu ra cặp thô, packet ẩn tên cấu hình, key và hai mẫu chấm. Key và raw output dành cho người phân tích; không gửi kèm người chấm packet.

`retrieval-checkpoint.json` giữ dữ liệu retrieval ngay trước khi chạy cặp đầu ra. Nếu bước sau bị lỗi, checkpoint chỉ là dữ liệu trung gian, không phải một run đã hoàn tất. Run đầy đủ có `manifest.json` với hash của toàn bộ artifact. Khi đối chiếu kết quả chấm, chỉ bỏ qua `assessment_id` được tạo mới cho từng lần gọi; mọi facts chấm toán và policy vẫn phải khớp.

Sau khi hai người hoàn tất review ở hai bản làm việc riêng, chạy:

```powershell
python scripts/retrieval/review_member2_stage6.py --run THU_MUC_KET_QUA --first REVIEW_A.json --second REVIEW_B.json --output artifacts/stage6-rating-comparison.json
```

Công cụ kiểm hash packet, rubric, danh tính/thời điểm, đủ cặp/tiêu chí và N/A. Khi còn bất đồng, không xuất điểm chất lượng hợp nhất. Khi đồng thuận, báo agreement/kappa và khoảng tin cậy theo concept; chỉ số tiết lộ được đảo chiều vì điểm thấp hơn tốt hơn. Không gán review giả hoặc tự biến bộ dev thành test chính thức.

## Cách dùng kết quả

- Giữ direct lookup cho hint/explanation có ID đã biết; các probe ID được báo riêng và không làm tăng điểm semantic.
- Production hiện dùng direct cho hint/explanation và metadata cho ví dụ. Đo semantic trên query không chứng minh hint thực tế đã tốt hơn; cần chấm các cặp đầu ra riêng.
- No-RAG vẫn dùng thang hint đã duyệt trong baseline. Hint giống nhau là kết quả hợp lệ; không sửa baseline để làm nổi bật Full.
- Nhãn review cặp để trống. Ẩn tên cấu hình/đảo A–B không ngăn người chấm suy đoán cấu hình từ nội dung. Chưa có human ratings thì không báo thắng/thua về toán, bám lỗi hay tiết lộ.
- Chỉ thêm hybrid/ANN/reranker nếu phân tích lỗi, candidate count và query plan chứng minh cần. K=5 thường phủ hết KB nhỏ; xem K=1/3 để đánh giá ranking.
- p95 retrieval tuần tự không thay thế p95 toàn lượt gia sư, browser hoặc thử tải đồng thời. Chưa có test độc lập và nhãn được xác nhận thì kết quả vẫn là dev.

Tham số được ghim trong [config v1](member2-13.config.v1.json). [Bàn giao Chặng 6](../../../docs/implementation/member2/part6/README.md) giữ kết quả local và các phần còn mở.
