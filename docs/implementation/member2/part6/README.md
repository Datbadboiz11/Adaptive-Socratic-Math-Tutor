# Chặng 6 — Đánh giá dev và bàn giao 13 concept Member 2

Ngày **27/11/2026**, đã hoàn tất phần triển khai và nghiệm thu kỹ thuật Chặng 6 trong phạm vi 13 concept của Member 2: runner tái lập, phép so retrieval, phân tích lỗi/latency/cache, đầu ra Full/No-RAG và công cụ xử lý review độc lập. Kết quả hiện là **dev**, chưa phải nghiệm thu RQ3 chính thức vì thiếu nhãn được xác nhận và test độc lập.

Không chờ 27 concept của hai thành viên khác để chạy gói này. Không gọi API model trả phí; dùng PostgreSQL 16.15, pgvector 0.8.6 và model CPU 384 chiều đã ghim checksum. Không sửa runtime/frontend hoặc dữ liệu nội dung đã duyệt.

## Kết quả retrieval

Trên bộ **104 query / 169 judgment dev tất định**, 91 query có nhãn phù hợp trực tiếp và 13 ca trả rỗng được báo riêng. Cả hai cách lấy dùng cùng bộ lọc production và cùng snapshot 91 chunk.

| Cách lấy | Recall/Hit@1 | nDCG@1 | nDCG@3 | Recall@5 | p95 cold query (ms) | p95 warm query (ms) |
|---|---:|---:|---:|---:|---:|---:|
| Metadata | 0,4286 | 0,6190 | 0,8783 | 1,0000 | 81,12 | 83,53 |
| Semantic exact | 0,8242 | 0,8828 | 0,9634 | 1,0000 | 149,57 | 126,33 |

Nguồn: [report.json](dev-2026-11-27/report.json), có đủ Recall/Hit/nDCG tại K=1/3/5 và phân tích theo concept/purpose. Chênh lệch nDCG@1 semantic–metadata là **+0,2637**, khoảng bootstrap 95% **[0,2271; 0,3004]** khi lấy mẫu theo 13 concept. Đây chỉ là độ nhạy trên dev labels, không phải suy luận về học sinh hoặc human gold.

Recall@5 chạm 1 vì mọi tập ứng viên đều có tối đa ba chunk. Không dùng chỉ số này một mình để kết luận ranking tốt. Metadata có 52 ca trượt target grade 2 ở vị trí đầu; semantic còn 16 ca, gồm 12 hint và 4 ví dụ. Xem [lỗi ranking](dev-2026-11-27/ranking-errors.json).

Trên bộ **156 query Chặng 5**, mọi điểm chất lượng giữ **N/A** vì 195 judgment chưa chấm. Có 130 query được gọi retriever; 26 ca mơ hồ/ngoài scope chỉ là route đã soạn trước, không được trình bày như kiểm thử classifier thành công. p95 của metadata/semantic tương ứng **83,69/154,58 ms** ở query-cache cold và **88,73/139,45 ms** ở warm.

## Cache, scope và dữ liệu thực nghiệm

- Đã lưu 1.560 row thực nghiệm, trong đó 1.404 lần gọi retriever và 156 row route control không thực thi; warm repeat không làm tăng số nhãn độc lập.
- **0 vi phạm scope/exclusion** trong các lần gọi đã chạy; các ca loại hết ví dụ trả rỗng đúng. Không biến query rỗng hoặc nhãn chưa biết thành Recall/nDCG đạt.
- Hai lượt query-cache warm giữ nguyên ranking và tính lại **0 embedding**. Sync corpus lặp cũng tính lại 0 embedding.
- **26 probe direct lookup** đúng ID/version trên đủ 13 concept, gọi embedding 0 lần; được tách khỏi điểm semantic.
- Lượt chạy tính 300 embedding text cục bộ: 91 corpus, 208 query có ứng viên và một query phục vụ EXPLAIN. Không có model API call.
- Cold query đo sau khi model/corpus đã nóng; tải/kiểm model ban đầu mất khoảng 3 giây, được ghi riêng. Wall time gồm ghi trace, không phải p95 toàn lượt gia sư hoặc phép thử tải đồng thời.
- [Query plan](dev-2026-11-27/query-plans.json) của mẫu ba ứng viên có SQL execution khoảng 0,34–0,38 ms. Chưa có bằng chứng cần ANN. Nếu tối ưu latency tiếp, cần đo riêng kết nối/ghi trace trước khi thêm thuật toán ranking.
- Mọi dữ liệu DB thử nghiệm nằm trong schema mới, đã dọn sau lượt chạy. [Receipt isolation](dev-2026-11-27/report.json) xác nhận trạng thái KB phục vụ trước/sau khớp nhau.

## Full / No-RAG

Đã chạy **104 cặp** qua graph sản phẩm: 65 yêu cầu hỗ trợ và 39 bài nộp sai được biên soạn sẵn, phủ đủ 13 concept. Mỗi cặp dùng cùng đề, bài làm, mức hỗ trợ và policy; chỉ thay cấu hình RAG/snapshot theo semantics sản phẩm. Mọi facts chấm toán khớp nhau; `assessment_id` riêng của từng lần gọi được giữ trong raw output và không dùng để kết luận hai lần chấm khác nhau. Không ghi session học sinh hoặc quan sát BKT.

Kết quả có **78 cặp cùng lời nhắn, 26 cặp khác lời nhắn**. Baseline No-RAG vốn đã có thang hint được duyệt, nên hint giống nhau là kết quả hợp lệ. Khác lời nhắn chưa chứng minh Full đúng toán hơn, bám lỗi hơn hoặc giúp học tốt hơn.

Người chấm đọc [packet ẩn tên cấu hình](dev-2026-11-27/paired-blind.json) và điền ở hai bản làm việc mới từ `paired-review-A.template.json` / `paired-review-B.template.json`. Giữ raw output và key giải mã cấu hình ở phía người phân tích, tách khỏi packet gửi người chấm. Việc ẩn tên/đảo A–B không bảo đảm không suy đoán được cấu hình từ nội dung.

```powershell
python scripts/retrieval/review_member2_stage6.py --run docs/implementation/member2/part6/dev-2026-11-27 --first REVIEW_A.json --second REVIEW_B.json --output artifacts/stage6-rating-comparison.json
```

Công cụ kiểm toàn bộ manifest/packet hash, rubric, danh tính/thời điểm thật, đủ cặp/tiêu chí và N/A. Khi có bất đồng, giữ cả hai nhãn và không xuất điểm hợp nhất. Khi đồng thuận, báo agreement/kappa và bootstrap theo concept. Điểm tiết lộ càng thấp càng tốt nên hướng chênh lệch được xử lý riêng. Hiện toàn bộ ô chấm vẫn trống; không có chữ ký hoặc đánh giá con người được tạo thay.

## Quyết định tối ưu hiện tại

[Khuyến nghị dev](recommendation-2026-11-27.json) giữ direct lookup cho ID hint/explanation đã biết. Với query cần xếp hạng ngữ nghĩa, phép đo ủng hộ exact search trên tập đã lọc, tối đa ba ứng viên và chỉ một chunk vào assembler. Giữ cache vector nhưng kiểm quyền/scope mỗi lượt. Chưa thêm ANN/hybrid/reranker khi chưa có lỗi được review chứng minh cần.

Production hiện dùng direct cho hint/explanation và metadata cho ví dụ. Khuyến nghị nghiên cứu chưa tự thay đổi policy sản phẩm; kết quả semantic không được diễn giải thành cải thiện chất lượng hint thực tế. 12 ca semantic trượt hint ở K=1 củng cố việc dùng ID chính xác khi server đã biết mức hint. Bốn ca ví dụ còn lại cần review nhãn/wording trước khi cân nhắc hybrid.

## Chạy lại và bằng chứng

Sau khi cài dependencies backend/RAG và chuẩn bị weights theo [runbook KB](../../../../content/kb/README.md):

```powershell
python scripts/retrieval/prepare_member2_stage5.py --check
python scripts/retrieval/run_member2_stage6.py --audit-only
python scripts/dev/validation_runtime.py database
python scripts/retrieval/run_member2_stage6.py --workspace-local
```

Lượt mới tự có run ID/thư mục riêng; có thể truyền `--output` tới một đích chưa tồn tại. Runner không ghi đè artifact, ghim config/source/model và kiểm hash nguồn trước/sau. Checkpoint retrieval được giữ nếu bước tạo cặp gặp lỗi; chỉ run có manifest hoàn tất mới được dùng cho review. Ranking/protocol có thể tái lập; timestamp, UUID và timing không được kỳ vọng giống từng byte giữa các lượt chạy.

Nghiệm thu local: **92 test offline/hồi quy liên quan và 1 test tích hợp DB bao phủ đủ 104 cặp**, 0 lỗi/0 bỏ qua. [Verification](verification-2026-11-27.json) ghi hash, lệnh và giới hạn. [Manifest kết quả](dev-2026-11-27/manifest.json) giữ checksum 14 artifact, gồm config, input hashes, ranking/trace thô, checkpoint, query plan, report và packet review. [Workflow CI](../../../../.github/workflows/stage6-member2-checks.yml) có PostgreSQL/pgvector và kiểm graph với fixture vectors; chưa chạy remote CI hoặc semantic inference trên CI.

## Điều kiện còn mở để nghiệm thu RQ3 chính thức

[Trạng thái bàn giao](completion-status-2026-11-27.json) đánh dấu kỹ thuật/dev đã hoàn tất, `formal_rq3_complete: false`. Phần còn thiếu là nhãn relevance và chấm cặp độc lập, hòa giải bất đồng, bộ scenario test độc lập chưa dùng tuning cùng cấu hình/snapshot đã khóa trước chạy test. Bằng chứng remote CI, browser/toàn lượt và tải đồng thời cũng chưa được thu trong lượt nghiên cứu này.

Các điều kiện trên không được thay bằng điểm dev hoặc chữ ký AI. 27 concept của Member 1/3 vẫn chờ chủ sở hữu bàn giao theo phạm vi đã chốt; chúng không chặn gói kỹ thuật 13 concept này.
