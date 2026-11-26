# Nhãn dev sau AI review ngày 18/11/2026

[Manifest](manifest.json) ghim corpus `DEV-A02-E02-M2-OAT02`, bản nhãn đề xuất gốc, reviewer kind AI và hash của [queries](queries.json)/[qrels](qrels.json). Hồ sơ review hiện hành nằm cùng snapshot tại [review.json](review.json) và [query-review.json](query-review.json), thay cho đường dẫn tài liệu lịch sử không còn trong workspace. Đã rà 24 query × 8 ứng viên, sửa 2/192 judgments từ 2 xuống 1; không sửa bộ v2 gốc hoặc cấp quyền publish nội dung.

Hai tệp review được **tái dựng ngày 26/11/2026** từ query rationale, qrels và workboard còn lưu, không phải bản gốc của hồ sơ đã mất. Manifest giữ hash của hai tệp lịch sử trong `historical_unavailable_review_files_sha256` để đối chiếu; checker xác minh hash hiện hành và nhãn tái dựng rõ ràng. Các queries/qrels đã ghim giữ nguyên byte.

Đây là review đa góc nhìn của cùng Codex, không phải nhãn gold hoặc hai người gán độc lập. Dùng cho phát triển; không đưa lesson/variant/paraphrase liên quan vào final test độc lập. CI không còn phụ thuộc thư mục đã bị loại khỏi workspace.

Recall/Hit dùng relevant≥2 có 6 query không có positive; nDCG dùng gain 0/1/3 chỉ có 4 query không có positive gain. Manifest tách các danh sách này khỏi 4 ca metadata fallback. Chưa chạy metric retrieval.
