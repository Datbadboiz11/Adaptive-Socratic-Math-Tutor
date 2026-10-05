# Công cụ repo

Chạy các lệnh từ thư mục gốc dự án; các script tự xác định repository root bằng vị trí file.

- `checks/`: kiểm tra repo, nội dung, browser, API/DB và health. Script `check_phase3_live.py` gọi OpenAI thật theo cấu hình local; dùng riêng khi cần kiểm tra AI.
- `exports/`: tạo hoặc kiểm tra JSON Schema/OpenAPI từ backend.
- `dev/`: runner hồi quy dùng PostgreSQL Compose và schema test riêng.

Ví dụ:

```powershell
python scripts/checks/check_repository.py --include-untracked
.\.venv\Scripts\python.exe scripts/checks/check_phase1.py
.\.venv\Scripts\python.exe scripts/exports/export_contracts.py --check
.\.venv\Scripts\python.exe scripts/dev/test_phase3_local.py
```

Code xử lý dataset và benchmark nằm trong [research/](../research/README.md). Xem [cấu trúc repo](../docs/development/project-structure.md) để tra vị trí cũ/mới.
