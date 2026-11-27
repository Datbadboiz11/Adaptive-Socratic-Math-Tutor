# Công cụ repo

Chạy các lệnh từ thư mục gốc dự án; các script tự xác định repository root bằng vị trí file.

- `checks/`: kiểm tra repo, nội dung, browser, API/DB và health. Script `check_phase3_live.py` gọi OpenAI thật theo cấu hình local; dùng riêng khi cần kiểm tra AI.
- `exports/`: tạo hoặc kiểm tra JSON Schema/OpenAPI từ backend.
- `dev/`: runner hồi quy dùng PostgreSQL Compose và schema test riêng.
- `authoring/`: pipeline soạn nháp một concept, kiểm tra và ghi nhận review độc lập; xem [hướng dẫn](../content/authoring/README.md).
- `kb/`: kiểm bộ publication/benchmark 13 concept, chuẩn bị model và đồng bộ snapshot đã duyệt; xem [runbook KB](../content/kb/README.md).
- `retrieval/`: `prepare_member2_stage5.py --check` kiểm gói Chặng 5 cho đúng 13 concept Member 2; `curate_stage5.py` mặc định dùng gói này để tạo workset và đối chiếu hai review. `prepare_stage5.py` giữ để đối soát hồ sơ 40 concept trước khi chốt phạm vi. Xem [bàn giao](../docs/implementation/member2/part5/README.md).

Chặng 6 dùng `retrieval/run_member2_stage6.py --audit-only` để kiểm đầu vào, hoặc `--workspace-local` để chạy phép đo với PostgreSQL/pgvector và model CPU local. `retrieval/review_member2_stage6.py` đối chiếu hai bộ chấm packet Full/No-RAG có kiểm hash và giữ bất đồng. Xem [phương pháp](../research/retrieval/stage6/README.md).



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
