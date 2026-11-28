# Chặng 6 — Kết quả dev trên 13 concept Member 2

Nhãn 104 query là nhãn phát triển tất định. Bộ 156 query chưa có nhãn xác nhận; không tính chất lượng trên bộ này. Chưa phải nghiệm thu RQ3 chính thức.

| Dataset | Cách lấy | Cache query | nDCG@1 | nDCG@3 | Recall@5 | p95 wall (ms) |
|---|---|---|---:|---:|---:|---:|
| labelled_dev_104 | metadata | query_cache_cold_model_warm | 0.6190 | 0.8783 | 1.0000 | 81.12 |
| labelled_dev_104 | metadata | query_cache_warm | 0.6190 | 0.8783 | 1.0000 | 83.53 |
| labelled_dev_104 | semantic | query_cache_cold_model_warm | 0.8828 | 0.9634 | 1.0000 | 149.57 |
| labelled_dev_104 | semantic | query_cache_warm | 0.8828 | 0.9634 | 1.0000 | 126.33 |
| unjudged_dev_156 | metadata | query_cache_cold_model_warm | N/A | N/A | N/A | 83.69 |
| unjudged_dev_156 | metadata | query_cache_warm | N/A | N/A | N/A | 88.73 |
| unjudged_dev_156 | semantic | query_cache_cold_model_warm | N/A | N/A | N/A | 154.58 |
| unjudged_dev_156 | semantic | query_cache_warm | N/A | N/A | N/A | 139.45 |

## Diễn giải

- Direct lookup được báo riêng, không trộn vào điểm semantic.
- K=5 bao phủ toàn bộ tập ứng viên nhỏ; xem thêm K=1/3 và nDCG để phân biệt ranking.
- Query-cache cold chạy sau khi model/corpus đã được làm nóng; không phải process cold start.
- Warm pass dùng cache vector hiện hữu; vẫn kiểm đầy đủ scope/review/exclusion trong mỗi request.
- p95 là retrieval tuần tự có ghi trace, không phải p95 toàn lượt gia sư hoặc thử tải đồng thời.
- Ca mơ hồ/ngoài scope của bộ 156 query chưa chạy classifier: chỉ là route được soạn trước.
- Khoảng tin cậy bootstrap lấy mẫu theo concept, chỉ mô tả độ nhạy của dev labels.
- Chưa thêm ANN/hybrid/reranker; phân tích lỗi dev được lưu để quyết định bước tiếp theo.

## Full / No-RAG

{
  "pair_count": 104,
  "concept_count": 13,
  "wrong_submission_pairs": 39,
  "identical_messages": 78,
  "different_messages": 26,
  "generator": "current_product_reviewed_text_assembler_no_free_form_llm",
  "same_assessment_and_policy": true,
  "assessment_comparison": "all_fields_except_assessment_id",
  "session_writes": 0,
  "model_api_calls": 0,
  "quality_ratings": null,
  "quality_status": "pending_independent_human_review",
  "interpretation": "Identical hints are expected: the no_rag baseline already contains the approved hint ladder. Message differences do not establish improved teaching quality or learning outcomes."
}

Đọc `paired-blind.json` để chấm; giữ `paired-key.json` tách khỏi người chấm. Ẩn tên cấu hình không bảo đảm người chấm không suy đoán được từ nội dung. Không coi số đầu ra khác nhau là bằng chứng Full có chất lượng dạy học tốt hơn.
