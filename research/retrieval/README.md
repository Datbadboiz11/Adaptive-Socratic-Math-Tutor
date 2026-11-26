# Đánh giá retrieval cho 13 concept

Bộ [member2-13.v1](dev/member2-13.v1/README.md) hiện có 91 document, 104 query và 169 judgment, phủ đủ 13 concept Member 2 được duyệt. Nhãn dev dùng để kiểm tra kỹ thuật; chưa phải human gold hoặc kết quả RQ3 cuối.

Các bộ file riêng trước đây đã bị loại bỏ theo yêu cầu của người dùng. Runner và fixture hiện hành không đọc lại các snapshot đó.

Kiểm source, publication, schema và benchmark:

```powershell
python scripts/checks/check_stage3_kb.py
python scripts/kb/build_member2_stage3_assets.py --check
```

Nghiệm thu với PostgreSQL/pgvector và model embedding cục bộ:

```powershell
python scripts/checks/check_stage3_kb.py --workspace-local --real-db
```

Checker tạo schema riêng, đối soát serving trước/sau và lưu kết quả mới trong `artifacts/stage3-validation/<run-id>/acceptance.json`. Không kích hoạt snapshot thử nghiệm trên namespace đang phục vụ. Chuẩn bị weights theo [runbook KB](../../content/kb/README.md); không cần API key để chạy embedding cục bộ.

`metrics.py` tính Recall/Hit/nDCG và xử lý query không có tài liệu liên quan. `pgvector_dev.py` giữ store nghiên cứu draft để kiểm transaction, checksum và metadata; test dùng fixture synthetic dựng trong bộ nhớ từ canonical data. Không coi những fixture này là nội dung được người duyệt.
