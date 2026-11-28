# Chặng 5 — Phạm vi 13 concept của Member 2

Theo phạm vi người dùng chốt ngày **26/11/2026**, công việc hiện hành chỉ triển khai trên 13 concept Member 2. 27 concept của Member 1/3 chờ các chủ sở hữu hoàn thành rồi tiếp nhận sau; chúng không chặn việc phát triển, review hoặc kiểm thử gói này.

Danh sách: **N02, N05, N08, A01, A04, A07, A10, E03, E06, E09, F02, F05, F08**. Nguồn tiếp tục là [lô M2-ORIG02 đã duyệt](../../../../content/authoring/batches/member2-original.v2/manifest.json).

## Đầu ra hiện hành

| Hạng mục | Kết quả trong phạm vi Member 2 |
|---|---|
| Nội dung | 13 pack đã duyệt, 78 bài, 39 họ bài và 39 ví dụ; không tạo thêm pack ngoài phân công |
| Corpus | 91 teaching chunk khớp projection/snapshot đang dùng; ghim cả profile embedding và nguồn/version/hash |
| Query | 156 query dev, 12/concept: giải thích, hiểu nhầm, thuật ngữ/lỗi gõ, hint 1–3, ba cách hỏi ví dụ và ba ca control |
| Candidate | 195 cặp query–document đủ điều kiện; relevance giữ `null` cho tới khi chấm |
| Pilot | 26 query, 39 judgment; có tài liệu đọc chứa nguyên văn candidate và hai mẫu review riêng |
| Review toàn bộ | Hai mẫu A/B cho 156 query và 195 judgment; CLI mặc định chọn đúng gói 13 concept |
| Taxonomy | Ánh xạ đủ 39 mẫu lỗi có sẵn vào 32 nhóm lỗi đề xuất; nhiều mẫu dùng chung nhóm, mapping mới còn chờ review |
| Phụ thuộc bên ngoài | Member 1: 13 concept; Member 3: 14 concept, ghi `awaiting_owner_delivery`; không đếm vào thiếu hụt của Member 2 |
| Kiểm thử | 136 test liên quan đạt, 0 lỗi/0 bỏ qua, gồm 28 test mới cho phạm vi 13 concept và kiểm hồi quy hồ sơ cũ |

Đọc [ma trận 13 concept](../../../../research/retrieval/stage5/member2-13.v1/coverage.md), [pilot để review](../../../../research/retrieval/stage5/member2-13.v1/pilot-review.md), [taxonomy](../../../../research/retrieval/stage5/member2-13.v1/misconception-taxonomy.json), [trạng thái chờ tiếp nhận](../../../../research/retrieval/stage5/member2-13.v1/integration-status.json) và [bằng chứng kiểm tra](verification-member2-13-2026-11-26.json).

## Chạy lại

Từ thư mục gốc, trong môi trường đã cài dependencies backend:

```powershell
python scripts/retrieval/prepare_member2_stage5.py --check
python scripts/retrieval/curate_stage5.py check
python -m pytest tests/test_member2_stage5.py tests/test_stage5_dataset.py tests/test_curriculum.py tests/test_kb_unit.py tests/test_stage3_completion.py tests/test_member2_authoring_pipeline.py -q
```

Builder chỉ xuất file dưới `research/retrieval/stage5/member2-13.v1`; không viết vào pack đã duyệt, dữ liệu hai thành viên khác hoặc database. Bỏ `--check` chỉ dùng để tạo ở đích mới với `--output-root`. File hiện hữu được bảo vệ khỏi ghi đè.

Kiểm `curate_stage5.py check` phải báo `concept_count: 13`, `concepts_awaiting_reviewed_content: []` và `other_members_block_current_scope: false`.

## Gán nhãn và review

Tạo bản làm việc mới cho pilot:

```powershell
python scripts/retrieval/curate_stage5.py template --selection pilot --slot A --output artifacts/member2-stage5-pilot-A.json
python scripts/retrieval/curate_stage5.py template --selection pilot --slot B --output artifacts/member2-stage5-pilot-B.json
```

Dùng `--selection full` để tạo mẫu cho toàn bộ 156 query. Hai người đánh giá điền danh tính/thời điểm thật, kiểm wording/route và chấm 0/1/2 cho mọi candidate được giao theo [guideline](../../../../research/retrieval/stage5/ANNOTATION_GUIDE.md). Những mẫu A/B trống không được coi là review đã diễn ra.

```powershell
python scripts/retrieval/curate_stage5.py compare --first artifacts/member2-stage5-pilot-A.json --second artifacts/member2-stage5-pilot-B.json --output artifacts/member2-stage5-pilot-comparison.json
```

Công cụ từ chối nhãn thiếu, sai hash/version, tài liệu ngoài scope và hai review cùng danh tính. Khi có bất đồng, giữ hai bản gốc và xuất danh sách cần hòa giải; không tự lấy trung bình. Taxonomy 32 nhóm là đề xuất từ AI hỗ trợ, còn cần review ngữ nghĩa và ánh xạ trước khi xuất bản.

## Phần còn lại trong phạm vi này

- Chấm/review pilot, sửa query hoặc guideline bằng revision mới, rồi hoàn tất relevance labels và mapping taxonomy cho lô 13 concept.
- Thiết kế bộ test độc lập theo scenario/họ nguồn chưa dùng để điều chỉnh hệ thống. Cả 13 concept đã xuất hiện trong authoring/dev, nên 156 query hiện đều là dev; không chia paraphrase thành test để tạo bằng chứng độc lập giả.
- Sau review và hòa giải, khóa test/query/qrels/KB/embedding/config trước thực nghiệm Chặng 6. `formal_test_ready` hiện vẫn là `false`.
- Khi Member 1/3 bàn giao, kiểm version, provenance review/nguồn, task/checker, family/source/lineage và bằng chứng hồi quy, rồi tạo revision tích hợp mới. Việc này được để sau theo yêu cầu của người dùng.

Không gọi API model trả phí trong lượt triển khai. [Workflow Stage 5](../../../../.github/workflows/stage5-content-checks.yml) đã chuyển sang gói 13 concept; chưa chạy remote CI. Mã runtime/frontend không thay đổi, không thu thêm bằng chứng browser/DB trong lượt này.

## Hồ sơ trước khi chốt phạm vi

[Bàn giao lượt đầu](README-initial-40.md), [bằng chứng lượt đầu](verification-2026-11-26.json), bộ `coverage40.v1` và hai bản nháp N03/N06 được giữ nguyên để tra cứu. Các file đó không còn là gói mặc định hoặc danh sách việc cần làm hiện hành. `prepare_stage5.py` chỉ phục vụ đối soát hồ sơ cũ; entry point hiện hành là `prepare_member2_stage5.py`.
