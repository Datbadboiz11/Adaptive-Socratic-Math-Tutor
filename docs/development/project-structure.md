# Cấu trúc repository

Repo dùng cấu trúc monorepo: frontend, backend, nội dung học và nghiên cứu dữ liệu cùng được quản lý phiên bản. Mỗi thư mục có một vai trò; thư mục gốc chứa cấu hình dùng chung và tài liệu khởi động.

```text
Adaptive-Socratic-Math-Tutor/
├── backend/                  # FastAPI, tutoring engine, migrations, dependencies
│   ├── app/
│   └── migrations/
├── frontend/                 # Next.js: giao diện sản phẩm và API proxy
│   └── app/
├── content/                  # Bài, hint và tham số BKT có version
├── contracts/                # JSON Schema, OpenAPI và fixtures hợp đồng
├── research/                 # Code tiền xử lý/benchmark/nghiên cứu
│   └── data/                 # Công cụ kiểm kê ASSISTments hiện tại
├── scripts/                  # Công cụ vận hành repo
│   ├── checks/               # Kiểm tra nội dung, API, DB, browser và smoke
│   ├── exports/              # Xuất/check JSON Schema và OpenAPI
│   └── dev/                  # Runner kiểm thử local dùng DB trong Compose
├── tests/                    # Kiểm thử tự động backend và nghiên cứu
├── design/                   # Prototype HTML độc lập, spec, UI flow và ảnh mẫu
├── docs/
│   ├── product/              # brief.md, prd.md
│   ├── planning/             # project-plan.md và mvp/ (kế hoạch G2)
│   ├── design/               # Mục lục thiết kế
│   ├── development/          # Cấu trúc repo, thiết lập GitHub
│   ├── implementation/mvp/   # Bàn giao phase1–phase5 và evidence tương ứng
│   └── research/data/        # Tài liệu audit và báo cáo tổng hợp
├── data/                     # Dataset local, được Git ignore
├── .github/                  # CI, mẫu issue và PR
├── compose.yaml              # Chạy các dịch vụ
├── .env.example              # Cấu hình mẫu, được đưa lên Git
├── .env                      # Cấu hình thật, được Git ignore
├── README.md
├── CONTRIBUTING.md
└── AGENTS.md
```

`node_modules`, `.next`, `.venv`, cache Python, log và dataset là file sinh ra/local; không tính là source trong cây trên. `data/` giữ nguyên các thư mục dữ liệu đã tải. Không chuyển log ASSISTments/Junyi vào PostgreSQL sản phẩm chỉ để dùng chung chỗ lưu.

## File cần đọc để tiếp tục code

- [PRD](../product/prd.md): hành vi, mức ưu tiên và acceptance criteria.
- [Kế hoạch tổng](../planning/project-plan.md): module, dữ liệu, thực nghiệm và mốc 12 tuần.
- [Bàn giao MVP](../implementation/mvp/README.md): code đã có, contract và giới hạn theo từng giai đoạn.
- [Dữ liệu nghiên cứu](../research/data/README.md): kết quả audit và việc cần làm trước tiền xử lý/BKT baseline.

## Các vị trí cũ đã chuyển

| Trước | Hiện tại |
|---|---|
| `brief_de_tai_socratic_math_tutor.md` | `docs/product/brief.md` |
| `PRD_Adaptive_Socratic_Math_Tutor.md` | `docs/product/prd.md` |
| `plan_de_tai_socratic_math_tutor.md` | `docs/planning/project-plan.md` |
| `plan/` | `docs/planning/mvp/` |
| `docs/phase1/` … `docs/phase4/` | `docs/implementation/mvp/phase1/` … `phase4/` |
| `docs/evidence/` | `docs/implementation/mvp/phase5/` |
| `docs/data/` | `docs/research/data/` |
| `docs/REPOSITORY_SETUP.md` | `docs/development/repository-setup.md` |
| `scripts/audit_assistments_2017.py` | `research/data/audit_assistments_2017.py` |
| Các `scripts/check_*.py`, `smoke_foundation.py` | `scripts/checks/` |
| Các `scripts/export_*.py` | `scripts/exports/` |
| Các `scripts/test_*_local.py` | `scripts/dev/` |

Snapshot JSON/XML/ảnh cũ được giữ nguyên. Đường dẫn và hash bên trong snapshot mô tả lần chạy gốc; việc di chuyển không được coi là chạy lại nghiệm thu.

## Lệnh từ thư mục gốc repo

```powershell
docker compose up -d --build --wait
python scripts/checks/check_repository.py --include-untracked
.\.venv\Scripts\python.exe scripts/checks/check_phase1.py
.\.venv\Scripts\python.exe scripts/exports/export_contracts.py --check
.\.venv\Scripts\python.exe scripts/exports/export_phase3_openapi.py --check
python research/data/audit_assistments_2017.py
```

Lệnh Docker và thư mục làm việc frontend/backend giữ nguyên. `--include-untracked` kiểm tra working tree khi file chuyển chỗ còn chưa stage; CI kiểm tra các file trong Git index.
