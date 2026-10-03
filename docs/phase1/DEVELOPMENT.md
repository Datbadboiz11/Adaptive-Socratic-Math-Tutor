# Môi trường phát triển Phần 1

## 1. Cấu trúc và phiên bản

| Thành phần | Cấu hình |
|---|---|
| Frontend | Next.js 16.3.8, React 19.3.0, TypeScript; dependency chính xác và `package-lock.json` |
| Backend | Python 3.12, FastAPI/Pydantic/Psycopg/Uvicorn; xem requirements |
| DB | PostgreSQL 17, image `postgres:17-bookworm`, volume `mo-tutor_postgres_data` |
| Vận hành local | Docker Compose project `mo-tutor`, các cổng chỉ bind `127.0.0.1` |
| OpenAI | Đã xác định nhà cung cấp; chưa cài SDK/gọi API, chưa chọn model |

Image pin major/tag, chưa pin digest; bản dựng khác ngày có thể nhận cập nhật patch của base image. Backend khóa dependency trực tiếp; các dependency bắc cầu chưa có lock đầy đủ. Khi chốt bản nộp cần ghi commit, image/version thực tế và hoàn thiện khóa dependency nếu cần tái lập tuyệt đối.

## 2. Chạy toàn bộ bằng Docker

Chạy từ thư mục gốc repo. Cần Docker Desktop đang chạy và kết nối Internet ở lần build đầu để tải image/thư viện.

```powershell
# Chỉ copy khi chưa có .env; tránh ghi đè key hoặc thiết lập đã có.
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up --build -d --wait
docker compose ps
```

Mở <http://localhost:3000>. Trang phải hiển thị **Đã kết nối cơ sở dữ liệu** khi frontend gọi được backend và backend thực hiện được `SELECT 1` trên PostgreSQL.

- API live: <http://localhost:8000/health/live>.
- API readiness: <http://localhost:8000/health/ready>.
- Swagger endpoint đã có: <http://localhost:8000/docs>.
- DB cho công cụ SQL trên máy: host `127.0.0.1`, port `5433`, database/user/password theo `.env`.
- Trong mạng Compose: DB là `db:5432`, backend là `backend:8000`; không dùng localhost để gọi container khác.

Hiện mới có health check, chưa có migration/bài mẫu/phiên trong DB. Trang frontend không tự nạp đáp án hay giả lập gia sư. Nếu cổng đã có dịch vụ khác, đổi `FRONTEND_PORT`, `BACKEND_PORT`, `POSTGRES_PORT` trong `.env` rồi tạo lại container; không dừng dịch vụ ngoài dự án.

```powershell
# Xem log của riêng dự án
docker compose logs --tail 80 backend frontend
# Dừng ứng dụng và giữ nguyên dữ liệu volume
docker compose stop
# Chạy lại
docker compose start
```

Không dùng `down -v` như bước chạy thường lệ: nó xóa volume DB. Đổi password trong `.env` không tự đổi password của PostgreSQL đã khởi tạo trong volume; phải thực hiện đổi role password đúng cách ở bước quản trị.

## 3. Phát triển trên máy, DB trong Docker

```powershell
docker compose up -d db
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
```

Chọn chạy backend trên máy hoặc trong container, không chạy hai bản cùng cổng. Với bản trên máy, đặt `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD` tương ứng cấu hình local trong terminal riêng; không commit password hoặc chụp terminal chứa secret. FastAPI không tự đọc `.env` trong chế độ chạy trực tiếp này.

```powershell
# Sau khi đặt các biến PG* trong terminal backend:
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Terminal frontend:

```powershell
cd frontend
npm ci
npm run dev
```

Backend URL mặc định là `http://127.0.0.1:8000`, được gọi từ Next.js server. Nếu đổi port, đặt `BACKEND_URL` ở môi trường chạy frontend; không cần CORS cho luồng health server-to-server này.

## 4. Kiểm tra nội dung và contracts

```powershell
.\.venv\Scripts\python.exe scripts/check_phase1.py --write-report
.\.venv\Scripts\python.exe scripts/export_contracts.py --check
.\.venv\Scripts\python.exe -m pytest tests/test_phase1.py -q
```

Sau khi sửa Pydantic schema, chạy `scripts/export_contracts.py` không có `--check` để sinh lại JSON Schemas, xem diff và commit cùng thay đổi contract. Không sửa JSON Schema bằng tay.

Kiểm tra kết nối khi Compose đang chạy và rà file mới trước commit:

```powershell
.\.venv\Scripts\python.exe scripts/smoke_foundation.py
.\.venv\Scripts\python.exe scripts/check_repository.py --include-untracked
```

Kiểm tra browser là tùy chọn, cần môi trường Python có Playwright và Chromium. Chạy `python scripts/check_foundation_browser.py` từ môi trường đó; script chỉ mở localhost và ghi ảnh/kết quả vào thư mục evidence. Không cần cài Playwright để chạy ứng dụng.

Frontend:

```powershell
cd frontend
npm run typecheck
npm run build
```

## 5. Cấu hình OpenAI và ngân sách

Người dùng đã xác nhận nhóm có OpenAI API. `.env.example` chuẩn bị `LLM_PROVIDER=openai`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `LLM_ENABLED=false`. Không tự lấy key từ dự án khác, không đặt biến `NEXT_PUBLIC_OPENAI_API_KEY`, không gửi key qua chat. Khi tích hợp, key chỉ được cấp cho backend.

Phần 1 không sử dụng SDK hoặc request OpenAI; `.env` không được đưa nguyên vào container frontend/backend hiện tại. Chỉ các biến DB cần thiết được cấp cho backend. Chưa kiểm tra quyền model, quota, thanh toán hoặc latency thực tế.

Trước Phần 3, nhóm cần chốt:

1. Model ID/version dựa trên benchmark phản hồi tiếng Việt, đúng Toán, không lộ lời giải, latency và chi phí.
2. Ngân sách tiền theo ngày/đợt thử, người theo dõi và cách chặn khi hết ngân sách.
3. Giới hạn kỹ thuật đề xuất ban đầu: tối đa một model call/lượt, đầu ra tối đa 500 token, timeout 15 giây, không tự retry tính phí khi chưa rõ request trước đã hoàn tất. Đây là cấu hình dự kiến, chưa phải runtime enforce.
4. Fallback nội dung đã duyệt khi timeout/không đạt kiểm tra; ghi rõ nguồn và lỗi, không báo kết quả LLM giả.

## 6. Nguồn kỹ thuật dùng khi chuẩn bị

- [Docker Compose startup order](https://docs.docker.com/compose/how-tos/startup-order/): dùng health check và `service_healthy` để chờ DB sẵn sàng.
- [Next.js installation](https://nextjs.org/docs/app/getting-started/installation): cấu trúc App Router và công cụ chạy/build.
- [Psycopg installation](https://www.psycopg.org/psycopg3/docs/basic/install.html): adapter PostgreSQL cho Python.
- [OpenAI API authentication](https://developers.openai.com/api/reference/overview): API key chỉ ở server qua môi trường/secret management.
