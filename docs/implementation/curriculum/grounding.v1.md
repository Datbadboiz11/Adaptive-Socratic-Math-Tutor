# KG/RAG pilot và embedding trên Kaggle / Colab

Đợt này tiếp nối [Analyzer pilot](analyzer.v1.md): tra prerequisite từ registry/Neo4j, lọc nội dung dạy rồi xếp hạng metadata, BM25 hoặc BGE-M3 dense. Có API thử nội bộ và log nối assessment, edge IDs, content IDs, version và phương pháp truy xuất thực tế. Chưa có Agent ra quyết định hay phiên học pilot nhiều lượt trên web.

## Chạy Kaggle nền: có thể tắt máy sau khi phiên bắt đầu

Dùng cùng notebook [bge_m3_colab.ipynb](../../../research/retrieval/bge_m3_colab.ipynb); giữ tên file để tương thích các đường dẫn cũ. Notebook tự nhận diện Kaggle, không gọi upload/download của Colab khi chạy trên Kaggle.

1. Tạo lại gói từ gốc dự án sau khi sửa nội dung hoặc code:

   ```powershell
   .\.venv\Scripts\python.exe scripts/exports/prepare_retrieval_colab.py
   ```

2. Trên Kaggle, tạo Dataset **Private** từ `data/exports/pilot-retrieval-input.zip`. Đây là bộ nội dung nháp nội bộ. Không upload cả thư mục `data/`, `.env` hay ASSISTments/FoundationalASSIST.
3. Tạo notebook, import `bge_m3_colab.ipynb`, dùng **Add Input** gắn Dataset vừa tạo. Nếu Kaggle giải nén ZIP thành thư mục, notebook vẫn đọc được và kiểm tra đúng 12 file cùng SHA-256 trước khi dùng code.
4. Trong Settings, chọn **GPU** (T4 nếu có) và bật **Internet** để cài thư viện/tải BGE-M3. Notebook hiện dùng một GPU, không tự chia model qua hai GPU.
5. Chọn **Save Version → Save & Run All**, không chỉ Quick Save hoặc Run All tương tác. Chờ xác nhận phiên nền bắt đầu; sau đó có thể đóng trình duyệt/tắt máy. Giới hạn thời gian/quota của Kaggle vẫn áp dụng. Xem [tài liệu Kaggle](https://www.kaggle.com/docs/notebooks).
6. Khi phiên hoàn thành, vào **Output** của phiên đó và tải **`pilot-retrieval-bge-m3.zip`**, được ghi trực tiếp tại `/kaggle/working/pilot-retrieval-bge-m3.zip`. Đặt ZIP vào `data/exports/` rồi dùng cùng lệnh import bên dưới.

Notebook tự tìm một ZIP `pilot-retrieval-input.zip` hoặc thư mục có `manifest.json`/`corpus.json`/`queries.json` dưới `/kaggle/input/`. Nếu không có hoặc có nhiều gói, nó dừng với hướng dẫn; có thể đặt `INPUT_PATH` trong ô đầu thành đường dẫn ZIP/thư mục cụ thể. Dataset input chỉ được đọc; code đã kiểm tra được sao chép sang thư mục làm việc. Cache model nằm trong `/kaggle/temp/bge-m3-model-cache`, không xuất model weights vào Output.

## Chạy Colab: chỉ cần hai file

1. Mở [bge_m3_colab.ipynb](../../../research/retrieval/bge_m3_colab.ipynb) bằng **Google Colab → File → Upload notebook**.
2. Chọn **Runtime → Change runtime type → T4 GPU**.
3. Chạy ô upload trong notebook, chọn **`data/exports/pilot-retrieval-input.zip`** tại máy. Gói đã được tạo từ nội dung hiện tại; trước mỗi lần chạy lại sau khi sửa source/nội dung, tạo lại bằng lệnh dưới.
4. Chạy các ô còn lại lần lượt. Model tải từ Hugging Face; không cần OpenAI API key. Nếu hết VRAM, giảm `BATCH_SIZE` từ 8 xuống 4 hoặc 2 trong ô tạo vector.
5. Ô cuối tải về **`pilot-retrieval-bge-m3.zip`**. Đặt vào `data/exports/`, nhập lại bằng lệnh bên dưới.

Từ gốc dự án:

```powershell
.\.venv\Scripts\python.exe scripts/exports/prepare_retrieval_colab.py
```

ZIP đầu vào có đúng 12 file: `corpus.json`, `queries.json`, `manifest.json` và 9 file code/dependencies tối thiểu. Có kiểm tra SHA-256 và danh sách file trước khi chạy code. Không tải cả repo, `.env`, API key, dataset ASSISTments, PostgreSQL hay `pilot.v1.json` có lời giải chuẩn. Manifest là kiểm tra tính nhất quán của gói do dự án tạo, không phải chữ ký xác thực từ bên ngoài.

Notebook **không huấn luyện BGE-M3**. Nó dùng model có sẵn để tạo embedding, đo thời gian/VRAM và đánh giá truy xuất. Colab T4 dùng FP16, batch 8, max_length 512; đoạn quá dài bị từ chối thay vì âm thầm cắt. Encoder là `BAAI/bge-m3`, revision `5617a9f61b028005a4858fdac845db406aefb181`, vector dense 1024 chiều, chuẩn hóa L2; pooling theo cấu hình Sentence Transformers của model, không thêm prefix. Không bật sparse hoặc ColBERT ở đợt này.

Nguồn cấu hình: [model card BGE-M3](https://huggingface.co/BAAI/bge-m3), [Sentence Transformers](https://sbert.net/docs/package_reference/sentence_transformer/model.html). GPU thực tế và phiên bản thư viện được ghi vào kết quả. [Colab](https://research.google.com/colaboratory/faq.html) có giới hạn tài nguyên và thời gian phiên; dùng để tạo index/đánh giá, không coi là server sản phẩm lâu dài.

## Nhập kết quả về dự án

```powershell
.\.venv\Scripts\python.exe scripts/exports/import_retrieval_artifact.py data/exports/pilot-retrieval-bge-m3.zip
```

Importer kiểm tra model/revision, toàn bộ content IDs, text hashes, corpus hiện tại, query set và vector; tính lại rankings/metrics trước khi ghi. Chỉ nhận 6 file JSON: index, query vectors, evaluation, corpus, queries và run manifest; không nạp pickle hoặc thực thi code tải về. Nếu thư mục đích có kết quả khác, công cụ dừng để giữ nguyên file. Dùng `--output data/retrieval/bge-m3-v2` để lưu một phiên bản mới rồi cấu hình đường dẫn index phù hợp.

Sau khi import, chạy lại đánh giá offline từ vector đã có, không cần GPU/model:

```powershell
.\.venv\Scripts\python.exe research/retrieval/evaluate.py --inputs data/retrieval/bge-m3-v1 --semantic --output data/retrieval/bge-m3-v1/evaluation-rerun.json
```

Vector nội dung **chưa đủ** cho câu hỏi mới: backend phải dùng đúng BGE-M3 để tạo query vector. Máy chạy backend có thể dùng CPU, sẽ chậm hơn cấu hình GPU; FP32 CPU và FP16 Colab có thể tạo chênh lệch nhỏ ở điểm/tie, cần đo latency và ổn định ranking trước triển khai. Cài dependencies và tải model một lần ở máy backend:

```powershell
.\.venv\Scripts\python.exe -m pip install -r research/retrieval/requirements.txt
.\.venv\Scripts\python.exe scripts/dev/cache_embedding_model.py
```

Model cache nằm trong `data/models/`; API chỉ đọc model đã có, không tải model trong lượt học. Tải model này độc lập với ZIP kết quả Colab. Nếu dùng Docker, đặt `INSTALL_LOCAL_EMBEDDING=true` trong `.env`, tạo cache từ lệnh host trên và rebuild backend; mounts cache/index chỉ đọc. Image mặc định không cài dependencies embedding nặng.

## Thử graph và grounding

Graph dùng snapshot SHA-256 theo registry. Import idempotent: thêm snapshot và merge các ID thuộc snapshot đó, không xóa dữ liệu graph. Lưu 40 concept và 68 cạnh đề xuất cùng nguồn/review/version. Tra ngược `PREREQUISITE_OF` tối đa 2 tầng; kiểm tra parity với registry trước khi sử dụng. `RELATED_TO`/`PART_OF` không được coi là prerequisite.

Khi Docker Desktop Engine đang chạy:

```powershell
docker compose --profile knowledge up -d --wait neo4j
docker compose --profile knowledge run graph-init
```

Mật khẩu graph local mẫu trong `.env.example`; cấu hình thật đặt ở `.env`. Neo4j Browser ở `http://localhost:7474`. Adapter dùng [Neo4j Query API](https://neo4j.com/docs/query-api/current/query/), kiểm tra cả lỗi trong body khi HTTP trả 202. Snapshot không có, lệch hoặc server unavailable sẽ báo `registry_fallback` và dùng DAG local, không ghi nhận là truy vấn Neo4j thành công.

Thử ngay offline bằng baseline, không cần Docker/model/Colab:

```powershell
.\.venv\Scripts\python.exe scripts/dev/pilot_grounding.py --problem P-A02-01 --step "3x+2" --method lexical --graph registry --output data/retrieval/grounding-demo.json
```

Đầu ra: lỗi bước được xác minh, giả thuyết lỗi ở trạng thái `suspected`, prerequisite paths và gợi ý ứng viên tối đa mức 1. Query embedding chỉ lấy mục tiêu kiến thức và câu hỏi chẩn đoán biên soạn, không lấy raw bài làm hoặc ID học sinh. Bài hoàn thành/đầu vào cần làm rõ sẽ không lấy thêm hints; kết quả retrieval không tự trở thành quyết định dạy học.

API bổ sung dưới `/api/v1/pilot/`:

| Route | Chức năng |
|---|---|
| `POST /retrieve` | Query + concept IDs + purpose + hint level + method; trả nội dung ứng viên |
| `POST /problems/{problem_id}/ground` | Analyzer → prerequisite → retrieval; trả kết quả và trace log |

Để mở API nội bộ, bật cả `PILOT_ANALYZER_ENABLED=true` và `PILOT_GROUNDING_ENABLED=true`. Cần đăng nhập demo và Bearer token như API MVP hiện có; bật cờ không bỏ qua auth. `LOCAL_EMBEDDING_ENABLED=true` chỉ bật sau khi đã có dependencies, model cache và index. Thiếu một trong các phần này thì semantic trả lexical fallback kèm lý do; benchmark semantic không cho fallback. Cờ mặc định tắt và `.env` hiện tại không được tự sửa. Sau đổi `.env`, recreate backend bằng `docker compose up -d --build backend`.

Log được trả trong response; lệnh offline có `--output` để lưu. Chưa persist log vào phiên sản phẩm và chưa dùng hint này để sinh reply. Không có writes vào PostgreSQL, cập nhật BKT hoặc thay topics trên web trong endpoint này.

## Bộ phát triển và kết quả đã kiểm tra

Kho truy xuất có **40 chunks**: 10 giải thích + 30 hints cho 10 concept pilot. Chỉ chiếu các trường được phép, không lấy worked examples, lời giải chuẩn hoặc error fixtures. Một câu ghi chú triển khai “MVP” trong giải thích E02 bị loại khi tạo projection; nội dung nguồn giữ nguyên. Public filter đòi concept/alignment/pack được duyệt; hiện 0 chunk công bố, nội dung nháp chỉ được dùng qua preview có cờ và auth. Metadata disclosure là ranh giới kỹ thuật, chưa tự chứng minh hint tốt về sư phạm.

[retrieval.dev.v1.json](../../../content/curriculum/retrieval.dev.v1.json) có **90 query nháp**: 80 query có relevance (8/concept, scope local/global, explanation/hints mức 1–3) và 10 case scope chưa có nội dung. Các paraphrase cùng họ có tương quan; chưa đủ bộ 120–200 query có review theo [plan tổng](../../planning/project-plan.md), chưa là test độc lập. Negative cases chỉ kiểm tra pool rỗng, chưa kiểm tra abstention tổng quát ngoài miền.

Đánh giá trên cùng bộ lọc, K=3 tạm dùng cho dev, chưa chốt K nghiệm thu:

| Phương pháp | Recall@3 | Hit@3 | nDCG@3 |
|---|---:|---:|---:|
| Metadata, xếp theo ID | 0,606 | 0,613 | 0,488 |
| Lexical BM25 | 0,840 | 0,963 | 0,852 |
| BGE-M3, Kaggle T4 ngày 10/10/2026 | 0,875 | 0,938 | 0,854 |

### Kết quả Kaggle thực tế, ngày 10/10/2026

Đã kiểm tra notebook có output chạy hoàn thành và `data/exports/pilot-retrieval-bge-m3.zip`. Gói qua kiểm tra SHA-256, input manifest, corpus/query set hiện tại, model/revision, coverage và vector 1024 chiều hữu hạn/chuẩn hóa. Đã nhập vào `data/retrieval/bge-m3-v1/`; chạy lại đánh giá offline từ vector trong `evaluation-rerun.json` tái lập chính xác cả metrics và 270 rankings (không so thời gian ranking phụ thuộc máy). Notebook đã chạy thực tế trên Tesla T4, FP16, batch 8; đây không phải vector giả trong tests.

Theo `run-manifest.json`, tải/khởi tạo model mất **76,867 giây**; encode 40 chunks mất **1,537 giây**, encode 90 query mất **0,272 giây**; peak bộ nhớ GPU do PyTorch ghi nhận **1105,1 MiB**. Đây là đo trên batch nhỏ của phiên Kaggle, không phải thời gian cài thư viện, tổng thời gian notebook hay latency mỗi câu hỏi trên backend CPU. Log pip có xung đột `huggingface-hub` với Gradio/Diffusers được cài sẵn; pipeline này không dùng hai thư viện đó, các ô embedding/evaluation/export hoàn thành và không có output loại `error`.

Kết quả có ích cho pilot nhưng **BGE-M3 chưa vượt BM25 trên mọi tiêu chí**:

- Recall@3 tăng từ 0,8396 lên 0,8750, khoảng **3,54 điểm phần trăm**; nDCG@3 chỉ tăng từ 0,8517 lên 0,8544.
- Hit@3 giảm: BM25 trúng ít nhất một nhãn ở **77/80** query dương; BGE-M3 **75/80**. So theo từng query, semantic cải thiện recall ở 12, giảm ở 4, bằng ở 64; nDCG tăng ở 18, giảm ở 11, bằng ở 51.
- Cả 40 query giới hạn đúng concept đều Hit@3 = 1,0; pool chỉ có 1–3 nội dung nên đây là điều kiện dễ, không chứng minh năng lực tìm kiếm rộng. Trên 40 query dương mở scope 10 concept, BM25 Hit@3 = 0,925, BGE-M3 = 0,875.
- Với 60 query lấy hints, BGE-M3 recall tốt hơn nhưng Hit@3 và nDCG thấp hơn BM25; phần lấy giải thích tăng nDCG. Vì vậy không dùng trung bình toàn bộ để khẳng định chất lượng gợi ý sư phạm đã cải thiện.
- BGE-M3 cải thiện rõ ở A02 (tính phân phối) và F05 (đỉnh/trục đối xứng); giảm ở A03, E02 và N04 theo một số tiêu chí. Hai phương pháp đều trả rỗng đúng 10 scope không có nội dung; đây là kiểm tra bộ lọc metadata, không phải nhận biết câu hỏi ngoài miền.

Năm query BGE-M3 không lấy được nhãn phù hợp trong top 3 đều ở scope rộng:

| Query | Nhóm kiến thức | Nhận xét trên nhãn dev hiện tại |
|---|---|---|
| `Q-A03-04` | Thu gọn hạng tử đồng dạng | Lấy gợi ý phân phối/dấu thay cho xác định hạng tử cùng phần biến; BM25 trúng |
| `Q-E02-08` | Phương trình bậc nhất | Lấy gợi ý thu gọn biểu thức thay cho cô lập ẩn; BM25 trúng |
| `Q-F01-08` | Giá trị hàm số | Câu hỏi về thế đầu vào/tính phép toán lấy gợi ý đại số khác; cả hai phương pháp trượt |
| `Q-N04-04` | Phân số tương đương | Câu hỏi chia tử số lấy gợi ý concept khác; cả hai phương pháp trượt |
| `Q-N04-06` | Rút gọn phân số | Chọn ước chung của tử/mẫu lấy gợi ý dấu/đại số; BM25 trúng |

Không đổi nhãn để tăng điểm hoặc bỏ các query trượt. Hướng tiếp theo là review nhãn/nội dung, phân tích query/scope, và thử kết hợp lexical + dense trên dev với baseline giữ nguyên; chưa cần đổi model hoặc fine-tune từ kết quả nhỏ này. Mọi thay đổi corpus/query text phải tạo lại gói/vector/hash tương ứng.

Notebook vẫn hỗ trợ cả Kaggle và Colab. Môi trường local chưa có model cache để encode câu hỏi mới, nên nhập index không tự bật semantic trong ứng dụng. Docker Engine local không sẵn sàng ở đợt ban đầu nên Neo4j/PostgreSQL thật chưa được kiểm tra tại máy. Có integration tests và dịch vụ Neo4j/PostgreSQL trong CI, chưa có kết quả chạy remote trong phiên này. [Báo cáo kiểm chứng](grounding-checks.v1.json) giữ nguyên phần chạy/skip và hashes của đợt triển khai ban đầu; kết quả Kaggle mới nằm trong các artifact nêu trên.

## Theo plan tổng, còn gì

Đợt này hiện thực phần tra prerequisite và “lọc metadata → xếp hạng ngữ nghĩa” ở mục 8.4–8.5 của kế hoạch, nối API nội bộ theo mốc tuần 3. Đây chưa phải prototype tuần 4 đủ module. Index JSON là artifact portable cho 40 chunks; **chưa đồng bộ vào pgvector** như kiến trúc sản phẩm dự kiến, chưa dùng index này trong phiên web.

Tiếp theo: review nhãn/nội dung và xử lý các trường hợp retrieval trượt, thử lexical + dense trên dev; đo runtime encode câu hỏi mới; đồng bộ registry/chunks/vector vào PostgreSQL + pgvector có version; đưa grounding vào Agent chọn can thiệp cùng Student Model, lưu decision logs và backtrack/return trong phiên học. Sau đó đánh giá nhiều lượt và Full/No-KG/No-RAG/Rule-policy, mở rộng nội dung đã duyệt. Pipeline ASSISTments/BKT v1 và tập test giữ nguyên.
