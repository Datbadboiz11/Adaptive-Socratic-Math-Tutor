# Member 2 — Chặng 2: pipeline nháp nội dung và review

Cập nhật 17/11/2026: xem [bản hoàn thiện Chặng 2 và tự review M2-OAT02](../part2-completion/README.md) cho trạng thái hiện hành, lô OATutor đã chỉnh scope và các luồng review nhãn/curriculum. Phần bên dưới lưu kết quả triển khai pipeline ban đầu.

Ngày triển khai: 16/11/2026. Theo [kế hoạch Chặng 2](../../../planning/member-2-plan.md).

**Trạng thái:** pipeline kỹ thuật đã triển khai và chạy CLI offline cho A02/E02; dừng tại mốc review. Chưa có API key để chạy OpenAI thật; chưa có người review nội dung thực tế. Hai nháp chạy được là replay từ pilot hiện có, không tính là 12 bài mới.

## 1. Đầu ra

- [content_authoring.py](../../../../backend/app/content_authoring.py): request/content/review contracts, prompt context, kiểm tra nội dung, review ràng buộc hash.
- [authoring_runs.py](../../../../backend/app/authoring_runs.py): OpenAI/replay providers, artifact immutable, xác minh checksum và snapshot review riêng.
- [CLI](../../../../scripts/authoring/draft_content.py): `plan`, `draft`, `check`, `review`.
- [Config/prompt và hướng dẫn sử dụng](../../../../content/authoring/README.md), schema và tests.
- [test_content_authoring.py](../../../../tests/test_content_authoring.py): checker, chống tự duyệt, lỗi provider, SDK với HTTP giả lập và vòng đời review.
- [verification.json](verification.json): kết quả chạy, các giới hạn và hashes đối chiếu.

Không sửa registry/pilot, ID/tham số BKT, migration hoặc API runtime. Các cổng review của nhóm ở Chặng 1 không tự chuyển accepted khi pipeline máy chạy đạt.

## 2. Luồng đã triển khai

```text
Config + scope registry + prompt có version
    → OpenAI Structured Outputs hoặc replay được gắn nhãn
    → GeneratedContent: model không có trường tự duyệt
    → ConceptPack draft với metadata do server gắn
    → Schema + ID/reference/family/source-group + toán/hint checks
    → Hồ sơ review của một người khác, gắn đúng hash
    → Candidate được duyệt riêng hoặc yêu cầu sửa
```

Sau nhánh candidate vẫn chưa công bố runtime. Đồng bộ PostgreSQL/pgvector thuộc Chặng 3, cần concept/alignment/nội dung được duyệt và snapshot đủ điều kiện.

## 3. Review kỹ thuật theo yêu cầu Chặng 2

| Yêu cầu | Thực hiện | Giới hạn |
|---|---|---|
| Tái sử dụng schema/template | Dùng `ConceptPack`, `AuthoredProblem`, `MathCase`, `ErrorFixture`, `Hint` đang có | Schema không chứng minh nội dung đúng |
| LLM hỗ trợ soạn nháp | Adapter OpenAI có structured output, token budget, timeout, không retry tự động | Live NOT RUN vì chưa có key; đã kiểm thử SDK với MockTransport không ra mạng |
| Version/provenance | Lưu request/prompt, payload, model/usage nếu có, revision, source hashes, checksum và thời điểm | Replay offline tái lập được; live LLM không bảo đảm output xác định |
| Một concept/run | A02/E02 có hai config, mỗi config ba họ, sáu bài và ba ví dụ | Đa dạng thực chất của họ mẫu vẫn cần người review |
| Checker toán/tham chiếu | Đáp án/bước, skill, ID trùng, family/source-group, task scope, first-error, cả bước sau lỗi | Chỉ trong ngữ pháp hữu tỉ/đa thức/linear/evaluate/vertex đã khai báo |
| Kiểm tra sư phạm/disclosure | Chặn một số trường hợp chép đáp án vào hint, checklist độc lập đầy đủ | Chưa phải bộ đánh giá nghĩa tự nhiên, đúng toán của mọi câu văn hoặc chống lộ đáp án hoàn chỉnh |
| Review độc lập | Không chấp nhận tác giả tự duyệt, thiếu checklist, hash cũ, thời điểm không hợp lệ hoặc còn lỗi máy | Danh tính do nhóm tự quản, chưa có auth sản phẩm |
| Bảo toàn phiên bản | Tạo run/file bằng chế độ exclusive, checksum, không ghi đè hoặc xóa; review là snapshot riêng | Run bị ngắt giữ nguyên để kiểm tra; dùng run/revision mới |
| Không đưa draft lên web | Chỉ lưu trong `artifacts/`, không sửa bank/registry/seed; tests kiểm tra `safe_chunks()` | Đã duyệt pack vẫn cần các gate concept/alignment/runtime |

## 4. Kết quả CLI đã chạy

Hai run local ở `artifacts/authoring/m2-a02-stage2/` và `artifacts/authoring/m2-e02-stage2/`:

| Concept | Provider | Bài / họ / ví dụ / lỗi / hint | Checker | Review | Model calls |
|---|---|---|---|---|---:|
| A02 | pilot_replay | 6 / 3 / 3 / 2 / 3 | PASS, có cảnh báo cần review | pending, draft | 0 |
| E02 | pilot_replay | 6 / 3 / 3 / 2 / 3 | PASS, có cảnh báo cần review | pending, draft | 0 |

`check` đã xác minh lại checksums và toán trên từng run. Family/source group giữ nguyên nguồn pilot; bản sao không trở thành test độc lập hoặc bằng chứng chuyển giao. `review-template.json` chưa có reviewer/thời điểm; không chạy duyệt thật bằng danh tính giả.

Hai folder này đã Git ignore và chỉ có ở máy chạy. Để tái lập trên máy khác, dùng `pilot_replay` với config đã version và một run ID mới theo [hướng dẫn](../../../../content/authoring/README.md).

## 5. Kiểm tra chất lượng phép đo và rủi ro còn lại

- N04: checker yêu cầu reference answer là phân số tối giản, không chỉ bằng giá trị. Việc bài thực sự đo đúng hành vi rút gọn vẫn cần review scope.
- F05: báo cảnh báo rõ chỉ đo tọa độ đỉnh, chưa có bộ đo riêng cho trục đối xứng.
- Mẫu lỗi: kiểm tra bước sai đầu tiên, giữ suspected, không đếm lỗi kéo theo như lỗi mới; kiểm tra cú pháp cả phần trace sau bước sai.
- Hint: phát hiện một số dạng chép đáp án trực tiếp; người review vẫn phải rà explanation/hints/diagnostic questions và ví dụ gần bài đo.
- Source metadata không phải giấy phép hoặc xác nhận chương trình. Các mục nguồn/lớp/quyền sử dụng trong review không tự được đánh dấu pass.
- Việc merge candidate vào bank cần quyết định version/hash và review các gate trước publish; pipeline Chặng 2 không tự merge.

## 6. Điểm dừng

Hoàn thành phần kỹ thuật để tạo, kiểm tra và review nháp. Hai việc bên ngoài chưa hoàn thành là chạy OpenAI thật bằng key của nhóm và review nội dung bởi người khác/người có chuyên môn. Không suy ra chất lượng nháp LLM hoặc nội dung đã được duyệt từ các tests.

Dừng ở Chặng 2 để người dùng review. Chặng 3 chưa bắt đầu.
