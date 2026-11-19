# Query dev A02/E02 — revision M2-OAT02

Cập nhật 18/11/2026: [bộ sau AI review](../a02-e02.ai-review.v1/README.md) đã rà đủ 24 query và sửa hai grade. Bản v2 ở đây được giữ nguyên để truy vết; AI review không được ghi thành nhãn gold của người thật.

[24 query và nhãn đề xuất](queries.proposed.json) đã được điều chỉnh theo A02 chỉ khai triển và explanation E02 mới. Tất cả vẫn là dữ liệu AI soạn để phát triển, không phải utterance quan sát từ học sinh hoặc nhãn gold do người thật duyệt.

[Snapshot dev](../../../../content/authoring/batches/a02-e02-oatutor.v2/retrieval-dev/manifest.json) ghim corpus 8 ứng viên nháp và 192 judgments; 20 query có positive trực tiếp, 4 ca metadata fallback. `DEV-E02-03` được đề xuất grade 2 sau khi đọc explanation mới; grade 1 ở v1 vẫn nguyên vẹn. Không dùng lại lesson, biến thể hoặc paraphrase của dev trong final test độc lập.

Đã có [mẫu review](../../../../content/authoring/batches/a02-e02-oatutor.v2/retrieval-dev/labels-review-template.json) và lệnh `labels-review` để tiếp nhận xác nhận/chỉnh nhãn, lưu candidate mới mà không sửa snapshot. Đọc [bản bàn giao Chặng 2](../../../../docs/implementation/member2/part2-completion/README.md) để biết cách điền và ghi nhận. Chưa chạy retriever hoặc báo cáo metric trên bộ này; nội dung còn draft nên chưa đủ điều kiện runtime.
