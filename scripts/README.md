# Công cụ repo

Chạy các lệnh từ thư mục gốc dự án; các script tự xác định repository root bằng vị trí file.

- `checks/`: kiểm tra repo, nội dung, browser, API/DB và health. Script `check_phase3_live.py` gọi OpenAI thật theo cấu hình local; dùng riêng khi cần kiểm tra AI.
- `exports/`: tạo hoặc kiểm tra JSON Schema/OpenAPI từ backend.
- `dev/`: runner hồi quy dùng PostgreSQL Compose và schema test riêng.
- `authoring/`: pipeline soạn nháp một concept, kiểm tra và ghi nhận review độc lập; xem [hướng dẫn](../content/authoring/README.md).

Lô nguồn OATutor A02/E02 dùng `authoring/prepare_oatutor_batch.py` (`fetch`, `build`, `check`, `review`), kiểm tra offline bằng `checks/check_oatutor_pilot.py`. Xem [hồ sơ lô và review](../docs/implementation/member2/source-pilot/README.md); dữ liệu và nhãn vẫn đang chờ người thật duyệt.

Bản hiện hành Chặng 2 dùng `build --edition stage2-v2`, `curriculum-review`, `labels-review` và batch `content/authoring/batches/a02-e02-oatutor.v2`. Kiểm tra bằng `checks/check_stage2_completion.py` và `checks/check_stage2_math.py` (SymPy độc lập). Xem [bàn giao và tự review](../docs/implementation/member2/part2-completion/README.md).

Ví dụ:

```powershell
python scripts/checks/check_repository.py --include-untracked
.\.venv\Scripts\python.exe scripts/checks/check_phase1.py
.\.venv\Scripts\python.exe scripts/exports/export_contracts.py --check
.\.venv\Scripts\python.exe scripts/dev/test_phase3_local.py
```

Code xử lý dataset và benchmark nằm trong [research/](../research/README.md). Xem [cấu trúc repo](../docs/development/project-structure.md) để tra vị trí cũ/mới.
