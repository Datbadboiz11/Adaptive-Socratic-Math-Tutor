# Nhãn dev sau AI review ngày 18/11/2026

[Manifest](manifest.json) ghim corpus `DEV-A02-E02-M2-OAT02`, bản nhãn đề xuất gốc, reviewer kind AI và hash của [queries](queries.json)/[qrels](qrels.json). Đã rà 24 query × 8 ứng viên, sửa 2/192 judgments từ 2 xuống 1; không sửa bộ v2 gốc hoặc cấp quyền publish nội dung.

Đây là review đa góc nhìn của cùng Codex, không phải nhãn gold hoặc hai người gán độc lập. Dùng cho phát triển; không đưa lesson/variant/paraphrase liên quan vào final test độc lập. Xem [báo cáo và lý do sửa nhãn](../../../../docs/implementation/member2/ai-review-2026-11-18/README.md).

Recall/Hit dùng relevant≥2 có 6 query không có positive; nDCG dùng gain 0/1/3 chỉ có 4 query không có positive gain. Manifest tách các danh sách này khỏi 4 ca metadata fallback. Chưa chạy metric retrieval.
