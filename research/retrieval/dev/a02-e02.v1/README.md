# Đề xuất query dev A02/E02

Bản này được giữ nguyên để đối chiếu. Dùng [revision M2-OAT02](../a02-e02.v2/README.md) cho pilot hiện hành; cơ chế tiếp nhận review nhãn đã được bổ sung ở revision đó.

[queries.proposed.json](queries.proposed.json) có 24 query tiếng Việt và nhãn relevance 0/1/2 do AI đề xuất. Không phải lời hỏi học sinh quan sát được hoặc nhãn gold của người thật.

Bản đã gắn ID/version/hash ứng viên nằm trong [retrieval-dev của lô](../../../../content/authoring/batches/a02-e02-oatutor.v1/retrieval-dev/manifest.json): 8 ứng viên nháp, 192 judgments, 4 ca không có ứng viên đủ điều kiện metadata. Query `DEV-E02-03` chỉ có relevance=1; ngưỡng relevant≥2 không có positive cho query này. Chưa chạy hoặc báo cáo metric retrieval.

Đọc [review và hướng dẫn](../../../../docs/implementation/member2/source-pilot/README.md). Người review kiểm tra mọi ứng viên, ghi sửa nhãn vào bản sao của review template; không sửa snapshot hoặc tự đổi cờ thành approved. Dành riêng các lesson nguồn, biến thể và paraphrase cho dev; chuẩn bị final test độc lập sau.
