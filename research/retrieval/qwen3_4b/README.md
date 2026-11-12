# Qwen3-Embedding-4B trên Kaggle — bản thử nghiệm riêng

Thư mục này là thí nghiệm đối chiếu với BGE-M3, không thay model sản phẩm. Notebook, dependencies, gói input, ZIP kết quả và thư mục import đều có tên riêng. Không sửa notebook BGE đã chạy, backend, `.env`, index hoặc kết quả BGE.

## Hai file cần đưa lên Kaggle

1. Import **[qwen3_4b_kaggle.ipynb](qwen3_4b_kaggle.ipynb)** vào một notebook Kaggle mới.
2. Upload **`data/exports/pilot-retrieval-qwen3-4b-input.zip`** thành Dataset **Private**, rồi **Add Input** vào notebook. Gói đã tạo sẵn từ source hiện tại. Notebook nhận cả ZIP nguyên lẫn thư mục Kaggle đã giải nén.

Không dùng ZIP input của BGE cho notebook này. Không cần upload dữ liệu ASSISTments/FoundationalASSIST, `.env`, API key hoặc toàn bộ repo. Gói riêng có 15 file: corpus, query set, baseline BGE, manifest, 11 file code/dependencies tối thiểu. SHA-256 kiểm tra tính nhất quán của gói do nhóm tạo, không phải chữ ký xác thực bên ngoài.

Trong Settings, bật **Internet**, chọn **GPU T4 ×2** nếu có, rồi **Save Version → Save & Run All**. Chờ phiên nền bắt đầu trước khi đóng trình duyệt/tắt máy. Bản sửa OOM v2 chia trọng số model qua hai GPU bằng Transformers/Accelerate; đây là model parallel, không phải ghép VRAM thành một card hay chạy hai bản sao. Một GPU cũng được hỗ trợ khi còn đủ bộ nhớ. Giới hạn/quota Kaggle vẫn áp dụng.

Chạy xong, tải **`pilot-retrieval-qwen3-4b.zip`** trong Output của phiên đã hoàn thành, file nằm ở `/kaggle/working/pilot-retrieval-qwen3-4b.zip`. Đặt vào `data/exports/` tại máy, giữ nguyên ZIP.

## Chạy lại sau lỗi CUDA out of memory

1. Dừng session Kaggle cũ và mở session GPU mới (Stop session/Restart session tùy giao diện). Chỉ chạy lại ô lỗi không bảo đảm giải phóng model cũ hoặc tensor traceback.
2. Import lại notebook mới trong thư mục này. Upload **lại cả ZIP input mới** thành Dataset version mới và kiểm tra notebook đang gắn đúng version. Không chỉnh tay code trong ZIP vì sẽ làm sai hashes.
3. Không gắn đồng thời nhiều bản input Qwen; bộ kiểm tra yêu cầu `runtime_loader=transformers-fp16-balanced-v2` nên input cũ sẽ bị từ chối trước khi tải model.
4. Bật Internet và T4 ×2, Run All trên session sạch. Trước tải, xem `VRAM trước khi tải`; sau tải, xem `precision_verified: float16` và `device_map` trong log. Model chỉ có một bản với các lớp được phân bổ giữa GPU.
5. Nếu vẫn lỗi, giữ log VRAM, device map (nếu có) và traceback. Không kết luận model đã chạy qua chỉ từ các unit tests; bản sửa đã chạy thành công trên T4 ×2, xem kết quả kiểm tra ngày 19/10/2026 bên dưới.

Bản cũ đã yêu cầu FP16, nhưng log OOM xảy ra ở `SentenceTransformer.to(device)`. Traceback không đủ chứng minh chắc chắn là FP32 hay model cũ còn trong session. Bản sửa loại bỏ bước chuyển toàn bộ model vào GPU 0, kiểm soát bộ nhớ/kiểu dữ liệu và ghi chẩn đoán để lần chạy tiếp có bằng chứng rõ hơn. Giữ nguyên model/revision, corpus/query, prefix, 2560 chiều, last-token pooling, chuẩn hóa và nhãn đánh giá; không đổi sang 4-bit hoặc model khác.

## Cấu hình model và so sánh

- Model `Qwen/Qwen3-Embedding-4B`, revision cố định `5cf2132abc99cad020ac570b19d031efec650f2b`.
- Vector **2560 chiều**, last-token pooling của model, chuẩn hóa L2, tokenizer/padding trái và EOS theo revision đã pin.
- Query có instruction bằng tiếng Anh về truy xuất nội dung Toán tiếng Việt; passage chỉ gồm title + text như BGE, không thêm instruction. Prefix được ghi trong encoder và hashes để tái lập; không chứa nhãn relevance, đáp án hoặc kết quả đánh giá.
- Load bằng **AutoModel/AutoTokenizer của Transformers**, truyền `dtype=torch.float16`, dùng Accelerate và kiểm tra dtype thật sau tải. Hai GPU dùng `device_map="balanced"`, một GPU dùng placement trực tiếp. Không gọi `.to(cuda:0)` lên model đã chia; chừa 2 GiB VRAM/GPU, in memory/device map, không tự offload CPU/disk. **FP16**, SDPA, tắt KV cache; không dùng BF16, quantization hay FlashAttention 2. Model weights khoảng 8 GB, tải ban đầu có thể chiếm phần lớn thời gian; cache ở `/kaggle/temp/qwen3-4b-model-cache`, không xuất weights vào Output.
- Batch mặc định **2**, max_length **512**. Kiểm tra cả instruction/EOS trước encode; không cắt âm thầm. Encode hết VRAM sẽ thử giảm batch đến 1 rồi dừng nếu vẫn lỗi, không fallback thành vector giả hay BM25.
- Cùng **40 chunks, 90 query nháp, K=3**, bộ lọc concept/purpose/hint level, nhãn relevance, BM25 và tie break như BGE. Không thay nhãn hoặc loại query trượt.
- Notebook in Metadata/BM25/**BGE-M3 đã chạy**/**Qwen mới chạy** trên cùng dữ liệu. Có Recall@3, Hit@3, nDCG@3, từng concept và từng query. Các instruction là cấu hình riêng của model nên đây là so sánh hai pipeline theo cấu hình khuyến nghị, không phải chỉ thay số tham số trong một encoder giống hệt.

Bộ này là phát triển tự biên soạn: 80 query dương, 10 case scope rỗng, nhiều query cùng họ. Chưa là test có review độc lập; không kết luận model lớn hơn tốt hơn hoặc có lợi cho học sinh từ điểm dev.

Nguồn cấu hình: [model card Qwen](https://huggingface.co/Qwen/Qwen3-Embedding-4B), [pooling của revision](https://huggingface.co/Qwen/Qwen3-Embedding-4B/blob/5cf2132abc99cad020ac570b19d031efec650f2b/1_Pooling/config.json), [Accelerate: tải model lớn](https://huggingface.co/docs/accelerate/en/concept_guides/big_model_inference), [Kaggle notebooks](https://www.kaggle.com/docs/notebooks).

## Tạo lại gói và nhập kết quả riêng

Từ gốc dự án, tạo lại input sau khi sửa source hoặc nội dung. Lệnh chỉ ghi ZIP input Qwen, đọc baseline BGE và giữ nguyên các file cũ:

```powershell
.\.venv\Scripts\python.exe research/retrieval/qwen3_4b/experiment.py prepare
```

Sau khi tải Output Kaggle:

```powershell
.\.venv\Scripts\python.exe research/retrieval/qwen3_4b/experiment.py import data/exports/pilot-retrieval-qwen3-4b.zip
```

Kết quả nhập vào `data/retrieval/qwen3-4b-v1/`. Importer kiểm tra allowlist/hash/model/corpus/query/vector, tính lại toàn bộ metrics và rankings trước khi ghi; chỉ chấp nhận đích `qwen3-4b-*` trực tiếp trong `data/retrieval/`. Nếu kết quả đích đã có và khác, dùng `--output data/retrieval/qwen3-4b-v2` để giữ cả hai lần chạy. Không dùng `scripts/exports/import_retrieval_artifact.py` của BGE.

Đánh giá lại từ vector đã có không cần GPU/model:

```powershell
.\.venv\Scripts\python.exe research/retrieval/qwen3_4b/experiment.py evaluate --inputs data/retrieval/qwen3-4b-v1 --output data/retrieval/qwen3-4b-v1/evaluation-rerun.json
```

ZIP chỉ có 7 JSON, gồm index, query vectors, evaluation, corpus, queries, baseline BGE và run manifest. Không nạp pickle hoặc chạy code tải về. Backend vẫn dùng BGE và không nhận vector Qwen 2560 chiều vào index 1024 chiều.

## Kiểm tra trước khi gửi

Kiểm tra source/notebook compile; BM25/metadata parity với evaluator BGE; loader Transformers/Accelerate FP16 một/hai GPU, từ chối VRAM thiếu/FP32/offload, last-token pooling/prompt; input ZIP và Dataset đã giải nén; export/import với vector giả; từ chối artifact sai hoặc ghi vào thư mục BGE. Các kiểm thử cấu trúc không phải kết quả chất lượng Qwen thực tế. Đã bổ sung kết quả Kaggle thật ngày 19/10/2026 bên dưới, không thay thế bằng điểm trong tests.

## Kết quả đã tải về — 19/10/2026

Notebook trong thư mục này là bản đã chạy, giữ nguyên output. ZIP đã chuyển vào `data/exports/pilot-retrieval-qwen3-4b.zip`; bảy JSON đã nhập riêng vào `data/retrieval/qwen3-4b-v1/`. `evaluation-rerun.json` tái lập metrics và 270 rankings; `verification.json` lưu kiểm tra hash/input/model/vector cùng phân tích từng query.

Qwen chạy FP16 trên hai T4, Recall@3 = **0,958333**, Hit@3 = **1,0**, nDCG@3 = **0,954360** trên 80 query dương nháp. Không đổi BGE hoặc backend; đây chưa phải test độc lập. Đọc [báo cáo kết quả và tài nguyên](../../../docs/research/retrieval/qwen3-4b-v1.md).
## Batch truy vấn cho backend trên Kaggle

Ngoài notebook thí nghiệm ở trên, [qwen3_runtime_queries_kaggle.ipynb](qwen3_runtime_queries_kaggle.ipynb) là **notebook riêng mới** cho 30 câu truy xuất do luồng pilot hiện tạo. Upload `data/exports/pilot-query-vectors-qwen3-4b-input.zip`, chọn T4 ×2 + Internet, session mới, Save & Run All; tải `pilot-query-vectors-qwen3-4b.zip`. Không cần tải dataset học sinh hoặc embed lại 40 chunks.

```powershell
.\.venv\Scripts\python.exe research/retrieval/qwen3_4b/runtime_catalog.py import --input data/exports/pilot-query-vectors-qwen3-4b.zip
```

Catalog chỉ phục vụ query khớp chính xác, gắn snapshot/policy/corpus; query khác có fallback rõ ràng. Không phải service Kaggle luôn bật, không làm thay đổi kết quả đánh giá Qwen/BGE cũ. Xem [hướng dẫn RAG runtime](../../../docs/implementation/curriculum/rag-runtime.v1.md). Cặp notebook/input có thể tái tạo bằng `scripts/exports/prepare_qwen_runtime_kaggle.py`.

Lượt runtime ngày **19/10/2026 đã nhập thành công**: ZIP ở `data/exports/pilot-query-vectors-qwen3-4b.zip`; catalog, run manifest và verification ở `data/retrieval/qwen3-4b-runtime/`. Notebook runtime hiện là bản đã chạy, giữ outputs. Log cho thấy 30 vector × 2560 chiều, FP16 trên T4 ×2, model load 52,299 giây và encode 3,025 giây. Không tái tạo đè notebook đã chạy; nếu cần lần thử mới, lưu riêng bản có outputs trước. Đây là kiểm tra artifact/runtime catalog, không phải thí nghiệm chất lượng retrieval mới.

