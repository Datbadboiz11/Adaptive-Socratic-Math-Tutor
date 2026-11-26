# Công cụ repo

Chạy các lệnh từ thư mục gốc dự án; các script tự xác định repository root bằng vị trí file.

- `checks/`: kiểm tra repo, nội dung, browser, API/DB và health. Script `check_phase3_live.py` gọi OpenAI thật theo cấu hình local; dùng riêng khi cần kiểm tra AI.
- `exports/`: tạo hoặc kiểm tra JSON Schema/OpenAPI từ backend.
- `dev/`: runner hồi quy dùng PostgreSQL Compose và schema test riêng.
- `authoring/`: pipeline soạn nháp một concept, kiểm tra và ghi nhận review độc lập; xem [hướng dẫn](../content/authoring/README.md).
- `kb/`: kiểm bộ publication/benchmark 13 concept, chuẩn bị model và đồng bộ snapshot đã duyệt; xem [runbook KB](../content/kb/README.md).



`authoring/prepare_member2_pilot.py` kiểm và dựng 13 concept đang được phân công; request kiểm thử canonical được tạo trong bộ nhớ, không cần config riêng đã loại bỏ.

Ví dụ:

```powershell
python scripts/checks/check_repository.py --include-untracked
.\.venv\Scripts\python.exe scripts/checks/check_phase1.py
.\.venv\Scripts\python.exe scripts/exports/export_contracts.py --check
.\.venv\Scripts\python.exe scripts/dev/test_phase3_local.py
```

Code xử lý dataset và benchmark nằm trong [research/](../research/README.md). Xem [cấu trúc repo](../docs/development/project-structure.md) để tra vị trí cũ/mới.

Nghiệm thu Chặng 3 hiện hành:

```powershell
python scripts/checks/check_stage3_kb.py --workspace-local --real-db
python scripts/dev/validation_runtime.py tests
python scripts/checks/collect_stage3_completion.py --acceptance-run ID_TU_CHECKER --tests-xml artifacts/validation-db-tests.xml --frontend
```

`--real-db` dùng schema mới và kiểm serving trước/sau; thao tác triển khai snapshot là lệnh `kb/sync_kb.py ... sync --activate` riêng. Entry point cũ `collect_stage3_validation.py` chuyển tiếp sang collector hiện hành, không còn đọc trace từ schema đã dọn.
