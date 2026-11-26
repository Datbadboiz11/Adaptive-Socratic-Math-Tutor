# Review kỹ thuật Chặng 3 — phạm vi 13 concept

Ngày rà soát: 26/11/2026. Người thực hiện: Codex, cùng tác nhân triển khai. Đây là hồ sơ tự review có bằng chứng để Member 1 và Member 3 đối chiếu. Chưa có chữ ký review độc lập của hai thành viên cho thay đổi Chặng 3 này.

## Đối chiếu sáu thiếu sót

| Thiếu sót | Kết quả hiện hành | Bằng chứng |
|---|---|---|
| 13 pack chưa vào KB | CLI mặc định `member2-v2`; runtime active có registry 40 concept/40 skill và 91 chunk thuộc 13 pack | [completion](completion-2026-11-26.json), [publication manifest](../../../../content/kb/member2-v2/manifest.json) |
| 39 example thiếu metadata | Có 39 publication với pack hash, family/source/lineage, teaching text và review provenance; teaching text được trích nguyên văn từ đề và lời giải trong tài liệu đã được người dùng duyệt | [publications](../../../../content/kb/member2-v2/example-publications.json), [builder](../../../../scripts/kb/build_member2_stage3_assets.py) |
| Checker phụ thuộc review đã mất | Review được tái dựng có ghi rõ nguồn và ngày tái dựng; hash queries/qrels cũ giữ nguyên, hash tệp lịch sử bị thiếu vẫn được lưu để đối chiếu | AI review manifest (`../../../../research/retrieval/dev/a02-e02.ai-review.v1/manifest.json`; retired source) |
| `--real-db` thay runtime | Tạo schema mới, kiểm `current_schema`, giữ fingerprint serving trước/sau, dọn schema; test cả thành công, lỗi trong acceptance và trùng schema | [checker](../../../../scripts/checks/check_stage3_kb.py), [DB tests](../../../../tests/test_kb_db.py), [acceptance](acceptance-2026-11-26.json) |
| Chưa đo retrieval đủ 13 concept | 104 query, 169 judgment, 13 fallback; raw rankings K=1/3/5 và metric theo từng concept | [benchmark](../../../../research/retrieval/dev/member2-13.v1/README.md), [metric](retrieval-evaluation-2026-11-26.json) |
| Bàn giao cũ, thiếu Docker/CI/review | Runbook, test XML, source hashes, acceptance và hồ sơ này đã cập nhật; workflow có build image RAG và kiểm 91 chunk trong image | [workflow](../../../../.github/workflows/repository-checks.yml), [completion](completion-2026-11-26.json) |

## Góc kiểm tra DB/CI để Member 1 review

- Không sửa migration đã áp dụng. Source registry/bank được kiểm hash file và hash từng pack theo hồ sơ duyệt; dữ liệu duyệt gốc giữ nguyên.
- 39 example có `content_version=0.4.1-member2-kb-examples`; provenance vẫn gắn pack `0.4.0-member2-review`. Snapshot và chunk cũ được giữ, nội dung mới không ghi đè version cũ.
- Sync mới tái sử dụng embedding của 52 explanation/hint. Sync lặp thêm 0 chunk và tính mới 0 embedding. Activation giữ transaction/namespace lock và kiểm integrity đầy đủ.
- Checker không dựa vào dữ liệu serving để đạt acceptance. Fingerprint serving trước/sau, dọn schema và phục hồi `PGOPTIONS` đều có kiểm thử; schema trùng tên không bị xóa.
- Workflow dùng PostgreSQL/pgvector, kiểm asset byte-for-byte, chạy full test có JUnit, build backend với `INSTALL_RAG=true`, kiểm 13 pack/91 chunk trong image và upload test evidence.

## Góc kiểm tra retrieval để Member 3 review

- Tool chỉ nhận `RetrievalQuery`; scope/snapshot/hint permission/exclusions do server bind. Các gate concept/alignment/pack vẫn bắt buộc.
- Example text được lấy từ đúng phần **Ví dụ** của review material có SHA-256 đã được duyệt. Không ghép trường private answer thành teaching text, không phát sinh quyết định human review mới.
- Filter concept/skill/purpose/grade/difficulty/disclosure và family/source/lineage chạy trước top-K. Direct lookup không cần embedding; fallback không có ứng viên bỏ qua query embedding.
- Withdrawal gắn pack version nên vẫn chặn example có version publication riêng. Acceptance rút A01 trong fixture và xác nhận snapshot sau rút còn 84 chunk.
- Nhãn benchmark được sinh tất định cho phát triển. Mỗi query chỉ có tối đa ba ứng viên sau filter; Recall@3 vì thế là kiểm độ phủ trong scope hẹp, chưa đủ để khẳng định chất lượng trên truy vấn thực tế hoặc RQ3 cuối.

## Phần cần nghiệm thu ở môi trường khác

Docker không có trên máy hiện tại; workspace không có `.git` hay repository từ xa kết nối. Workflow đã được chuẩn bị và YAML đã được kiểm, nhưng chưa có bằng chứng Docker execution hay remote CI pass. Member 1 cần chạy workflow từ checkout có Git và đối chiếu artifact upload; Member 3 cần review các ranh giới tool, publication và phương pháp đánh giá. Trạng thái được ghi là **hoàn thành local, chờ nghiệm thu bên ngoài**.

Việc đưa retrieved context vào generator, ghi nhận delivery/assistance, replay và hiển thị citation ở UI thuộc Chặng 4.
