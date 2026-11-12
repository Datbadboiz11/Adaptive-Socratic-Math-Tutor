# Qwen3-Embedding-4B — kết quả Kaggle pilot v1

Kiểm tra ngày **19/10/2026** từ notebook và Output người dùng tải về. Đây là đánh giá retrieval trên bộ phát triển nháp, không phải độ chính xác toàn bộ gia sư hoặc hiệu quả học tập. Không đổi backend/model đang dùng.

## Vị trí file

- [Notebook đã chạy, giữ nguyên output](../../../research/retrieval/qwen3_4b/qwen3_4b_kaggle.ipynb).
- ZIP gốc chuyển từ thư mục dự án vào `data/exports/pilot-retrieval-qwen3-4b.zip`, giữ nguyên bytes/SHA-256.
- Bảy JSON trong ZIP đã được kiểm tra và nhập vào `data/retrieval/qwen3-4b-v1/`.
- `index.json`: 40 vector nội dung; `query-vectors.json`: 90 vector query, đều 2560 chiều, hữu hạn và chuẩn hóa L2.
- `evaluation.json`, `corpus.json`, `queries.json`, `bge-baseline.json`, `run-manifest.json`: kết quả và dữ liệu tái lập gốc.
- `evaluation-rerun.json`: tính lại offline từ vector; `verification.json`: bằng chứng kiểm tra, hashes, so sánh từng query và subgroup.
- Kết quả BGE cũ ở `data/retrieval/bge-m3-v1/` và ZIP BGE giữ nguyên.

## Kiểm chứng

ZIP có đúng 7 JSON, CRC/SHA-256 hợp lệ; các file nhập giữ nguyên bytes trong ZIP. Model/revision, corpus, query set và encoder khớp cấu hình hiện tại. Input manifest hash khớp gói input trên máy; các Python source trong gói cũng khớp. Baseline BGE trong Output khớp chính xác báo cáo BGE được giữ lại.

Chạy importer riêng rồi chạy lại evaluator offline: toàn bộ báo cáo và **270 rankings** của ba phương pháp được tái lập chính xác, ngoại trừ `ranking_ms` phụ thuộc thời gian máy. Không cần tải model hoặc dùng GPU để kiểm chứng bước này.

Notebook lưu đủ output của 7 code cells, không có output loại `error`. Execution counts là 1, 2, 3, 4, 7, 8, 9: có khoảng trống nên không khẳng định đây là một lần Run All sạch từ kernel mới. Kết quả cuối trong notebook khớp manifest/ZIP. Log pip có cảnh báo xung đột huggingface-hub với Gradio/Diffusers cài sẵn; pipeline không dùng hai thư viện này và các ô inference/evaluation/export đã hoàn thành.

## Điểm retrieval

Cùng 40 chunks, 90 query, K=3, metadata filters và nhãn relevance. Trung bình các metric dưới đây tính trên **80 query có nhãn nội dung phù hợp**; 10 case còn lại là scope không có nội dung và trả rỗng đúng.

| Phương pháp | Recall@3 | Hit@3 | nDCG@3 |
|---|---:|---:|---:|
| BM25 | 0,839583 | 0,962500 | 0,851716 |
| BGE-M3 | 0,875000 | 0,937500 | 0,854356 |
| Qwen3-Embedding-4B | **0,958333** | **1,000000** | **0,954360** |

Qwen tìm được ít nhất một nội dung được gán nhãn phù hợp trong top 3 ở **80/80 query dương**, BGE là 75/80, BM25 là 77/80. Hit@3 = 1 không đồng nghĩa mọi nội dung trả về đều đúng hoặc lấy đủ tất cả nội dung phù hợp: vẫn có 7 query recall dưới 1.

So với BGE, Recall@3 tăng **8,33 điểm phần trăm**, Hit@3 tăng **6,25 điểm phần trăm**, nDCG@3 tăng khoảng **10,00 điểm phần trăm**. Theo từng query, recall tốt hơn ở 12, thấp hơn ở 1 và bằng ở 67; nDCG tốt hơn ở 21, thấp hơn ở 4 và bằng ở 55. Không phải mọi trường hợp đều cải thiện. Query recall giảm là `Q-A01-06`; nDCG giảm tại `Q-A02-06`, `Q-A02-07`, `Q-A03-06`, `Q-A03-08`.

Trong 40 query dương mở scope toàn pilot, Qwen Recall@3 = 0,916667 và Hit@3 = 1; BGE tương ứng 0,75 và 0,875. Với 60 query lấy hints, Qwen Recall@3 = 0,944444, nDCG@3 = 0,939147; BGE tương ứng 0,833333 và 0,811959. Đây vẫn là relevance nháp, không phải chấm chất lượng sư phạm của gợi ý.

## Chạy thực tế và tài nguyên

- Qwen/Qwen3-Embedding-4B, revision `5cf2132abc99cad020ac570b19d031efec650f2b`, max length 512, query instruction, last-token pooling, chuẩn hóa L2.
- Loader `transformers-fp16-balanced-v2`; dtype FP16 đã kiểm tra. Embeddings và layers 0–15 trên GPU 0; layers 16–35 và norm trên GPU 1. Hai Tesla T4, không CPU/disk offload.
- Python 3.13.15; PyTorch 2.11.0+cu128; Transformers 4.57.6; Accelerate 1.14.0; batch 2 cho cả corpus và query.
- Model load: **78,940 giây**; encode 40 chunks: **1,521 giây**; encode 90 query: **3,368 giây**.
- PyTorch peak allocated: GPU 0 **3841,2 MiB**, GPU 1 **3870,8 MiB**. Tổng hai giá trị peak là 7712 MiB, không khẳng định là tổng peak đồng thời hay toàn bộ VRAM driver ghi nhận.
- Đây là thời gian một phiên Kaggle trên batch nhỏ, không phải latency production. BGE chạy batch 8/một T4, Qwen batch 2/hai T4 nên không suy ra so sánh tốc độ cùng điều kiện.

## Diễn giải và bước tiếp theo

Bản sửa OOM đã tải và encode thành công trong lần chạy này. Qwen có kết quả aggregate tốt hơn BGE/BM25 trên dev hiện tại, đủ để giữ làm ứng viên cho retrieval pilot. Nhãn và nội dung vẫn `draft_ai_authored`, query cùng họ có tương quan, tập corpus rất nhỏ; chưa có test độc lập, khoảng tin cậy hoặc bằng chứng hiệu quả học tập. Scope rỗng không đánh giá khả năng từ chối câu hỏi ngoài miền nói chung.

Chưa tự chuyển ứng dụng sang Qwen: backend vẫn cấu hình BGE, index Qwen 2560 chiều không được nạp vào index BGE 1024 chiều. Tiếp theo cần review nội dung/nhãn, kiểm tra các query chưa lấy đủ relevance, chọn cấu hình inference khi triển khai và nối retrieval vào phiên gia sư. Chưa cần chạy lại embedding chỉ vì đã sắp xếp file.
