# Bàn giao nhánh update-hoang2611 — 26/11/2026

Nhánh được tạo trực tiếp từ `main` tại `dd59e314e15131a5a8e567f0c893ecb0b9c4b358`, rồi tích hợp bản Member 2 trong workspace. Thư mục tải về không có `.git`; bản checkout xuất bản được chuẩn bị riêng để giữ nguyên mã, `.env` và dữ liệu cục bộ của người dùng.

## Phạm vi xuất bản

Đưa lên mã backend/frontend, migration, contract, 13 pack đã duyệt, cấu hình authoring, prompt, benchmark dev và hồ sơ bàn giao cần để đọc/tái lập dự án. Không đưa `.env`, API key, thư viện đã cài, môi trường ảo, build, cache, log, database, weights embedding hoặc thư mục artifacts lên Git. `.env.example` là cấu hình mẫu với key trống.

Các module Agent/KG/extraction/generation/evaluation đã có trên `main` được giữ lại. Các phần dùng chung được gộp có chủ đích:

- Giữ bộ chấm mở rộng `symbolic-bounded-2.2.0` và chẩn đoán của `main`; thêm nhánh chấm dòng cuối cho 13 concept Member 2 và adapter khai triển.
- Giữ request ID qua header, kiểm retry và checkpoint pause/resume của `main`; bổ sung receipt/hỗ trợ từ KB.
- Giữ kiểm tham số BKT và điều kiện lượt đầu; bổ sung cờ hỗ trợ mức 0.
- Giữ `SkillMastery.status`; số liệu report lấy từ observation của chính phiên và đóng băng khi kết thúc.
- Giữ dependency/Compose Neo4j và tài liệu nghiên cứu của `main`, đồng thời thêm pgvector/KB và UI Chặng 4.

Prompt `draft-pack-2.2.0` được khôi phục nguyên văn từ system message trong run authoring đã lưu của chính workspace. Không dùng nội dung sinh lại để thay thế một prompt đã ghi nhận.

## Kiểm tra và bằng chứng

Kết quả bản tích hợp nằm trong `publication-update-hoang2611.json` cùng thư mục. Hồ sơ Chặng 3/4 trong `docs/implementation/member2/` là snapshot nghiệm thu trước khi gộp `main`; hash của chúng mô tả đúng bản source tại lần nghiệm thu đó. Không coi các snapshot cũ là bằng chứng đã chạy lại trên bản tích hợp.

```powershell
python scripts/checks/check_repository.py
python scripts/checks/check_current_release.py
python scripts/checks/check_stage3_kb.py
python scripts/exports/export_contracts.py --check
python scripts/exports/export_phase3_openapi.py --check
python scripts/exports/export_frontend_types.py --check
npm --prefix frontend test
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

Sau sửa PR #8, `check_current_release.py` chạy toàn bộ test còn giữ trong repo. Những bộ file riêng đã ngừng dùng và test chỉ phục vụ chúng đã bị loại bỏ theo yêu cầu người dùng; các kiểm tra gate/retrieval/authoring còn cần thiết dùng fixture trong bộ nhớ. Không còn danh sách loại trừ test vì archive thiếu.

Workflow repository hiện chạy phạm vi trên; workflow Stage 4 tiếp tục chạy suite riêng. Không có kết quả Docker hoặc remote CI được suy ra từ kiểm thử cục bộ. Việc push nhánh không tự merge vào `main`.
