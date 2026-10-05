# Adaptive Socratic Math Tutor — Mở

Trợ lý học Toán bằng câu hỏi gợi mở, thuộc đề tài **VIN-02: Nghiên cứu và xây dựng trợ lý AI dạy học Toán theo phương pháp Socratic thích ứng sử dụng AI Agent**.

Xem [cấu trúc thư mục](docs/development/project-structure.md) và [mục lục tài liệu](docs/README.md). PRD nằm tại `docs/product/prd.md`; kế hoạch tổng nằm tại `docs/planning/project-plan.md`.

## Trạng thái hiện tại

Repository đã có **nền tảng Phần 1–3 và frontend tích hợp Phần 4**: kiểm tra phương trình bằng SymPy, observation/BKT, LangGraph/checkpoint PostgreSQL, OpenAI và web dùng API thật. Phần 5 đã có 7 ca API/DB thực tế; nghiệm thu thủ công trên build frontend mới còn mở. Nhánh nghiên cứu đã preprocess ASSISTments 2017 và fit BKT baseline train/dev. Chỉ phục vụ thử nội bộ: nội dung/gợi ý chưa duyệt chuyên môn, BKT trong sản phẩm vẫn dùng bootstrap chưa hiệu chỉnh cho người học Việt Nam, chưa có đăng nhập sản phẩm. Các phản hồi trong `design/` vẫn là mô phỏng độc lập.

Mục tiêu đồ án là 30–50 concept, hướng tới 40 concept. Lát cắt MVP G2 đề xuất tập trung vào một chủ đề chạy end-to-end; xem [kế hoạch MVP](docs/planning/mvp/README.md).

## Xem prototype

Clone repo:

```powershell
git clone https://github.com/Datbadboiz11/Adaptive-Socratic-Math-Tutor.git
cd Adaptive-Socratic-Math-Tutor
```

Mở `design/index.html` bằng Chrome hoặc Edge. Không cần npm, API key hay backend để xem giao diện.

Hoặc dùng Python 3 phục vụ các file:

```powershell
python -m http.server 8765 --bind 127.0.0.1 --directory design
```

Truy cập <http://127.0.0.1:8765>. Thanh dưới có Wireframe, Luồng và Kịch bản. Chi tiết ở [hướng dẫn thiết kế](design/README.md).

Prototype lưu phiên trong localStorage của trình duyệt. Font web là tùy chọn, có font dự phòng khi offline. Riêng prototype không cần biến môi trường; khung ứng dụng mới dùng `.env.example` theo hướng dẫn bên dưới.

## Chạy ứng dụng Phần 3

Đọc [bộ bàn giao Phần 3](docs/implementation/mvp/phase3/README.md) để xem cách chạy, thứ tự đọc code và giới hạn. `.env` cần `DEMO_MODE=true`, `TUTOR_ENABLED=true`. `LLM_ENABLED=true` dùng key/model server để gọi OpenAI; khi tắt hoặc API lỗi, ứng dụng dùng mẫu gợi mở có nhãn thử nghiệm. Không tự coi mẫu này là nội dung đã được người duyệt.

Từ thư mục gốc repo, bật Docker Desktop rồi chạy:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up --build -d --wait
```

Mở <http://localhost:3000> → chọn hồ sơ → **Bắt đầu phiên thử**. Phiên mới dùng bộ chấm/gia sư; phiên Phần 2 vẫn giữ chế độ chỉ lưu trữ. Service `init` tự migration/seed. Nếu Docker báo lỗi BuildKit trên đường dẫn có dấu, xem [cách xử lý](docs/implementation/mvp/phase3/README.md). Pipeline dữ liệu nghiên cứu chạy riêng, không chặn bản thử này.

## Thử luồng prototype riêng trong design/

Chọn **Kịch bản → Bắt đầu bài**, với đề `2(x - 3) = 10`:

1. Gửi `2x - 3 = 10`, `2x = 13`, `x = 6.5` trên các dòng riêng để xem gợi mở cho lỗi phân phối.
2. Sửa thành `2x - 6 = 10`, `2x = 16`, `x = 8` để xem trạng thái đúng sau hỗ trợ.
3. Chọn bài mới, sau đó xem báo cáo phiên.

Đây là kịch bản kiểm thử UI, không phải bằng chứng chấm Toán/LLM chạy thật.

## Tài liệu

| Tài liệu | Nội dung |
|---|---|
| [Brief](docs/product/brief.md) | Bài toán, phạm vi và giá trị nghiên cứu |
| [PRD](docs/product/prd.md) | Yêu cầu chức năng, dữ liệu và nghiệm thu |
| [Kế hoạch đồ án](docs/planning/project-plan.md) | Lộ trình đầy đủ và thực nghiệm |
| [Kế hoạch phần tiếp theo](docs/planning/mvp/README.md) | 6 phần triển khai và bàn giao MVP G2 |
| [Bàn giao Phần 1](docs/implementation/mvp/phase1/README.md) | Nội dung, hợp đồng dữ liệu, protocol và khung môi trường |
| [Bàn giao Phần 2](docs/implementation/mvp/phase2/README.md) | API/DB, chạy web, thứ tự đọc code và giới hạn |
| [Kiến trúc Phần 2](docs/implementation/mvp/phase2/ARCHITECTURE.md) | Sơ đồ thực tế, bảng DB, transaction và API |
| [Kiểm tra Phần 2](docs/implementation/mvp/phase2/TESTING.md) | Test tích hợp, trình duyệt, restart/DB outage và evidence |
| [Bàn giao Phần 3](docs/implementation/mvp/phase3/README.md) | Bộ chấm, BKT, LangGraph/OpenAI, cách thử và đọc code |
| [Kiến trúc Phần 3](docs/implementation/mvp/phase3/ARCHITECTURE.md) | Grammar, transaction, checkpoint, tham số và giới hạn model |
| [Kiểm tra Phần 3](docs/implementation/mvp/phase3/TESTING.md) | Hồi quy Toán/BKT, phục hồi và evidence OpenAI thật |
| [Bàn giao Phần 4](docs/implementation/mvp/phase4/README.md) | Giao diện tích hợp, chủ đề, nháp, lỗi mạng và cách chạy build mới |
| [Bằng chứng Phần 5](docs/implementation/mvp/phase5/README.md) | Kết quả API/DB và trạng thái nghiệm thu manual |
| [Đặc tả thiết kế](design/DESIGN_SPEC.md) | Màu sắc, bố cục, component và trạng thái |
| [UI flow](design/USER_FLOWS.md) | Luồng sử dụng và ngoại lệ |
| [Quy trình đóng góp](CONTRIBUTING.md) | Nhánh, PR và review |
| [Thiết lập repository](docs/development/repository-setup.md) | Cấu hình và những việc cần quản lý trên GitHub |

## Kiểm tra

Kiểm tra cơ bản dùng Node.js và Python 3, không cần thư viện ngoài:

```powershell
node --check design/app.js
python -m py_compile design/audit_ui.py
python scripts/checks/check_repository.py
```

GitHub Actions được cấu hình chạy kiểm tra tài liệu, content/contract, validator/BKT, API với PostgreSQL thật và build frontend. CI không gọi OpenAI trả phí. Xem [hướng dẫn kiểm tra Phần 3](docs/implementation/mvp/phase3/TESTING.md); tests kỹ thuật chưa chứng minh chất lượng dự đoán BKT hoặc hiệu quả học tập.

Để chạy kiểm tra trình duyệt tùy chọn trong một môi trường Python riêng:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install playwright
.\.venv\Scripts\python.exe -m playwright install chromium
```

Giữ HTTP server ở trên đang chạy, rồi dùng terminal thứ hai:

```powershell
.\.venv\Scripts\python.exe design/audit_ui.py
```

Runner ghi lại ảnh và kết quả trong `design/previews/`; xem diff trước khi commit những thay đổi được tạo lại. [Kết quả prototype đã lưu](design/previews/qa-results.json) được phân biệt với evidence MVP sẽ thu sau.

## Dữ liệu và thông tin nhạy cảm

`data/` không được đưa lên Git vì chứa dataset tải riêng và bản ghi đã xử lý. Các bộ dữ liệu bên ngoài cần tuân thủ điều kiện truy cập/sử dụng. API keys, `.env`, môi trường ảo và file DB cục bộ cũng được bỏ qua.

Đã có [audit và pipeline ASSISTments 2017](docs/research/data/README.md), [protocol observation](docs/research/data/observation-protocol.md) và [BKT baseline dev](docs/research/data/bkt-dev-v1.md). Cách chạy tái lập ở [runbook](docs/research/data/RUNBOOK.md). Test chưa đánh giá; chưa kiểm chứng ánh xạ skill sang chương trình Việt Nam hoặc đưa tham số nghiên cứu vào ứng dụng.

Bước tiếp theo của dự án đã có [registry và pilot nội dung tiếng Việt](content/curriculum/README.md): 40 concept đề xuất, 10 pack nháp với 60 bài, 30 ví dụ, 20 mẫu lỗi và checker toán/graph. Chưa duyệt chuyên môn, chưa seed các pack vào web; bộ chấm online và các ID MVP giữ nguyên. Xem hướng dẫn để biên soạn, review và tiếp tục tích hợp KG/RAG.

Chưa chọn giấy phép phân phối mã nguồn; không tự áp một giấy phép cho dataset bên ngoài. Nhóm sẽ quyết định giấy phép phù hợp sau.
