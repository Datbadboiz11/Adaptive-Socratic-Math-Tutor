# Retrieval dev cho 13 concept M2-ORIG02

Bộ dữ liệu này khớp byte-for-byte với snapshot KB `0.4.0-member2-review`:

- 13 concept, 91 teaching document (52 explanation/hint và 39 example);
- 104 truy vấn: mỗi concept có 1 explanation, 3 mức hint, 3 example và 1 fallback;
- 169 judgment trên đúng tập ứng viên còn lại sau scope/filter;
- relevance `2` cho teaching unit đích, `1` cho unit liên quan cùng purpose; Recall/Hit dùng ngưỡng `2`, nDCG dùng gain `0/1/3`;
- 13 fallback không có ứng viên, được đánh giá riêng và không đưa vào mẫu số metric có relevance.

Nhãn được sinh tất định từ teaching intent và scope đã duyệt để kiểm phát triển, không phải human gold độc lập hay test set RQ3 cuối. Query example luôn chọn bài hiện tại ở family khác để kiểm exclusion; query fallback loại toàn bộ source/family/lineage của example trong concept.

Tái tạo/kiểm tra:

```powershell
python scripts/kb/build_member2_stage3_assets.py --check
python scripts/checks/check_stage3_kb.py --workspace-local --real-db
```

Lệnh `--real-db` tạo schema `stage3_check_*` mới, migrate và chạy acceptance ở đó, sau đó dọn schema. Nó không thay đổi channel `runtime` đang phục vụ. Việc triển khai runtime là lệnh quản trị riêng `scripts/kb/sync_kb.py ... sync --activate`.
