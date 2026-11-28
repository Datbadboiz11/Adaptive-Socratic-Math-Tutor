# Chặng 5 — Mở rộng nội dung và relevance dataset

> Hồ sơ tại mốc triển khai ban đầu, trước khi người dùng chốt phạm vi 13 concept Member 2. Các lệnh và trạng thái bên dưới ghi theo mốc đó; dùng [README hiện hành](README.md) cho công việc tiếp theo.

Lượt triển khai đầu ngày **26/11/2026** đã bổ sung hai pack nháp, ma trận công việc 40 concept và bộ query ứng viên có công cụ review chạy được. Đây là phần khởi đầu Chặng 5; nghiệm thu đủ 40 concept và nhãn test độc lập vẫn còn mở.

Nghiệm thu local đạt **108 test nội dung/dataset và 151 test hồi quy phiên học với PostgreSQL/pgvector thật**, 0 lỗi, 0 bỏ qua ở cả hai bộ. Hai suite có phần kiểm publication chung nên không cộng thành số test độc lập. Xem [bằng chứng và hash](verification-2026-11-26.json).

## Đầu ra đã có

| Hạng mục | Kết quả |
|---|---|
| Nội dung mới | N03 — thứ tự phép tính; N06 — cộng/trừ phân số. Tổng 12 bài, 6 ví dụ, 4 mẫu lỗi, 6 hint; 3 họ bài mỗi concept |
| Kiểm tra nội dung | Checker hiện hữu và SymPy độc lập kiểm đáp án/bước chuẩn, vị trí sai đầu. Hai pack giữ `draft`; binding task `numeric` của hai concept cũng chờ review trong snapshot riêng |
| Độ phủ pack | 22/40 concept, 132 bài và 66 ví dụ khi chọn một pack hiện hành mỗi concept. Trong đó chỉ 13 concept/78 bài có trong release phục vụ đã duyệt |
| Ma trận | Owner/reviewer, skill, scope, nguồn, version/hash pack, phụ thuộc, thiếu hụt, batch và query cho cả 40 concept |
| Query | 160 query ứng viên, 4/concept: giải thích theo hiểu nhầm, hint, ví dụ với lỗi gõ và ca điều hướng/không có tài liệu |
| Corpus và qrels | Ghim 91 teaching chunk hiện hành; 64 cặp query–document đủ điều kiện đang **chưa chấm**, `relevance: null` |
| Pilot review | 26 query trên 13 concept có nội dung; 38 judgment cần chấm. Hai mẫu A/B riêng, trống danh tính và thời điểm |
| Split | 88 query dev trên 22 concept đã dùng cho authoring; 72 query `test_candidate` trên 18 concept khác. Giữ chung concept/intent/source/family/lineage trong một split |
| Công cụ | Dựng/đối soát artifact, tạo file review mới, so sánh hai người chấm và giữ bất đồng; không ghi đè file có sẵn |
| CI | Workflow offline riêng, không cần DB hoặc lời gọi API model. Chưa có kết quả CI từ xa |

Hai pack mới nằm trong [stage5-expansion.v1](../../../../content/authoring/batches/stage5-expansion.v1/manifest.json). Đọc bản review [N03](../../../../content/authoring/batches/stage5-expansion.v1/N03/review.md) và [N06](../../../../content/authoring/batches/stage5-expansion.v1/N06/review.md). Phân công trong workboard được giữ nguyên: cả hai thuộc Member 3, reviewer Member 1; tác giả bản nháp ghi Codex.

Ma trận có thể đọc tại [coverage.md](../../../../research/retrieval/stage5/coverage40.v1/coverage.md); [coverage.json](../../../../research/retrieval/stage5/coverage40.v1/coverage.json) giữ dữ liệu chi tiết. Các batch đề xuất là phục vụ 13 → hoàn thiện 22 → mở rộng 30 → 40. Phần chưa có pack được xếp theo quan hệ tiên quyết; vẫn phải đóng từng cổng scope, checker, review và UI/policy trước khi mở chủ đề.

## Chạy lại và review

Từ thư mục gốc, với dependencies backend đã cài:

```powershell
python scripts/retrieval/prepare_stage5.py --check
python scripts/retrieval/curate_stage5.py check
python -m pytest tests/test_stage5_dataset.py tests/test_curriculum.py tests/test_kb_unit.py tests/test_stage3_completion.py tests/test_member2_authoring_pipeline.py -q
```

Không truyền `--check` chỉ dùng để tạo artifact ở một đích mới. Đích hiện hữu được bảo vệ khỏi ghi đè, kể cả file review. Khi cần thay nội dung/schema, tạo revision tiếp theo và cập nhật bàn giao; không sửa nhãn trong snapshot này.

Tạo hai bản review làm việc mới:

```powershell
python scripts/retrieval/curate_stage5.py template --selection pilot --slot A --output artifacts/stage5-review-A.json
python scripts/retrieval/curate_stage5.py template --selection pilot --slot B --output artifacts/stage5-review-B.json
```

Mỗi người chấm riêng, đọc query và teaching text từ [corpus](../../../../research/retrieval/stage5/coverage40.v1/corpus.json), ghi danh tính/thời điểm thực tế, kiểm wording/route/scope rồi điền relevance 0/1/2 cho toàn bộ candidate được giao. Điểm retriever không phải nhãn chuẩn. Hướng dẫn chi tiết ở [guideline](../../../../research/retrieval/stage5/ANNOTATION_GUIDE.md).

Sau khi hai người hoàn tất:

```powershell
python scripts/retrieval/curate_stage5.py compare --first artifacts/stage5-review-A.json --second artifacts/stage5-review-B.json --output artifacts/stage5-pilot-comparison.json
```

Công cụ kiểm hash corpus/query/content version, coverage đầy đủ và hai danh tính khác nhau; báo exact agreement, Cohen's kappa khi xác định được và danh sách bất đồng. Bất đồng không tự lấy trung bình hoặc chọn một người; cần hòa giải có bằng chứng ở revision sau. Nhãn đồng thuận chỉ xuất cho phần đã review và vẫn ghi `formal_test_ready: false`.

## Giới hạn và bước tiếp theo

- 108 query của 27 concept đang thiếu nội dung trong corpus đã duyệt. Chúng mang `awaiting_reviewed_content`; không được tính như các ca fallback đúng hoặc không có tài liệu liên quan.
- Toàn bộ 72 query test ứng viên đang chờ nội dung. Split hiện tại là đề xuất holdout theo concept, còn cần review phương pháp và độ phủ trước khi khóa; chưa phải bộ test RQ3 chính thức hoặc phép đo trên cùng phân phối concept.
- 26 query pilot dùng để sửa guideline/wording trên dev. Các ca control còn lại trên 13 concept phục vụ gồm 5 ca loại hết ví dụ, 4 ca hỏi mơ hồ và 4 ca ngoài scope; chúng cần chấm route riêng trước khi đánh giá ranking.
- Corpus chỉ sao chép teaching projection đã duyệt. Hai pack nháp mới không được đưa vào corpus, sync KB, topic runtime hoặc BKT. Passing checker không tự phê duyệt nội dung hay nguồn.
- Bộ chấm số học xác minh giá trị; chưa xác nhận học sinh thực hiện đúng thứ tự thao tác hoặc trình bày đủ bước. N04 được gắn blocker riêng vì tương đương phân số chưa đo được yêu cầu tối giản.
- Còn thiếu ít nhất 162 bài và 81 ví dụ **được duyệt** để đủ 40 concept theo mức tối thiểu. Số mẫu lỗi chưa được coi là số nhãn taxonomy độc lập.
- Cần review hai pack mới và bảy pack cũ, hoàn thiện scope/checker cho 18 concept chưa có pack, bổ sung nội dung theo batch, cập nhật snapshot và chấm nhãn độc lập. Sau đó mới ghim test/query/qrels/corpus/embedding/config và chạy Chặng 6.

Không có lời gọi model trả phí trong lượt triển khai này. [Hồ sơ kiểm tra](verification-2026-11-26.json) ghi rõ bộ test và hash đã chạy. Workflow [Stage 5](../../../../.github/workflows/stage5-content-checks.yml) đã được chuẩn bị; chưa thực hiện commit/push hay remote CI.
