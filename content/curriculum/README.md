# Bộ nội dung Toán tiếng Việt — registry và pilot v1

Đợt triển khai ngày 04/10/2026 theo [plan tổng, mục 5/12/24](../../docs/planning/project-plan.md) và [PRD](../../docs/product/prd.md). Nhóm chưa có tài liệu bắt buộc hoặc người duyệt. **Toàn bộ nội dung và cạnh graph hiện là nháp**, chưa công bố cho học sinh.

Đã có danh mục 40 concept và pilot 10 concept: N01, N02, N04, A01, A02, A03, E01, E02, F01, F05. Pilot gồm 60 bài thuộc 30 họ mẫu, 30 ví dụ giải, 20 mẫu lỗi và 30 mức gợi ý. E02 dùng lại 6 bài MVP trong bản authoring mới; không đổi dữ liệu gốc. Tất cả bản ghi pilot là `authoring_dev`, không phải bộ test kín hoặc bộ evaluation đã đủ quy mô.

## Thứ tự đọc

1. [registry.v1.json](registry.v1.json): mục tiêu, skill, dạng hỗ trợ, lớp đề xuất, nguồn và cạnh prerequisite.
2. [pilot.v1.json](pilot.v1.json): giải thích, bài, đáp án riêng, ví dụ, mẫu lỗi và hint ladder cho từng concept.
3. [curriculum.py](../../backend/app/curriculum.py): schema, loader, kiểm tra graph và ranh giới công bố.
4. [authoring_math.py](../../backend/app/authoring_math.py): kiểm tra toán chính xác cho nội dung do nhóm biên soạn.
5. [check_curriculum.py](../../scripts/checks/check_curriculum.py) và [tests](../../tests/test_curriculum.py): kiểm tra độ phủ, tham chiếu, an toàn parser và nội dung nháp.

Schema JSON có thể xem ở [CurriculumRegistry](../../contracts/v1/CurriculumRegistry.schema.json) và [PilotBank](../../contracts/v1/PilotBank.schema.json).

## Ma trận độ phủ

Tên và phạm vi 40 concept lấy từ plan. Lớp bên dưới là đề xuất để review, không phải kết quả nghiệm thu chương trình. Dấu `—` nghĩa là chưa biên soạn pack; có tên trong registry chưa được tính là concept hoàn chỉnh.

| Mã | Concept | Lớp đề xuất | Bài / ví dụ / mẫu lỗi | Trạng thái |
|---|---|---|---|---|
| N01 | Cộng trừ số có dấu | 6 | 6 / 3 / 2 | Nháp có kiểm tra toán |
| N02 | Nhân chia số có dấu | 6 | 6 / 3 / 2 | Nháp có kiểm tra toán |
| N03 | Thứ tự phép tính | 6 | — | Danh mục đề xuất |
| N04 | Phân số tương đương và rút gọn | 6 | 6 / 3 / 2 | Nháp có kiểm tra toán |
| N05 | Quy đồng và so sánh phân số | 6 | — | Danh mục đề xuất |
| N06 | Cộng trừ phân số | 6 | — | Danh mục đề xuất |
| N07 | Nhân chia phân số | 6 | — | Danh mục đề xuất |
| N08 | Chuyển đổi phân số–thập phân–phần trăm | 6 | — | Danh mục đề xuất |
| N09 | Lũy thừa với số mũ nguyên | 7, 11 | — | Danh mục đề xuất |
| N10 | Căn bậc hai số học | 7, 9 | — | Danh mục đề xuất |
| A01 | Thay giá trị vào biểu thức | 7 | 6 / 3 / 2 | Nháp có kiểm tra toán |
| A02 | Tính phân phối | 7, 8 | 6 / 3 / 2 | Nháp có kiểm tra toán |
| A03 | Thu gọn hạng tử đồng dạng | 7, 8 | 6 / 3 / 2 | Nháp có kiểm tra toán |
| A04 | Nhân đơn thức và đa thức | 7, 8 | — | Danh mục đề xuất |
| A05 | Bình phương một tổng/hiệu | 8 | — | Danh mục đề xuất |
| A06 | Hiệu hai bình phương | 8 | — | Danh mục đề xuất |
| A07 | Phân tích nhân tử bằng đặt nhân tử chung | 8 | — | Danh mục đề xuất |
| A08 | Phân tích nhân tử bằng hằng đẳng thức/nhóm | 8 | — | Danh mục đề xuất |
| A09 | Rút gọn phân thức và điều kiện xác định | 8 | — | Danh mục đề xuất |
| A10 | Cộng trừ nhân chia phân thức | 8 | — | Danh mục đề xuất |
| E01 | Phép biến đổi tương đương và điều kiện | 8 | 6 / 3 / 2 | Nháp có kiểm tra toán |
| E02 | Phương trình bậc nhất một ẩn | 8 | 6 / 3 / 2 | Nháp có kiểm tra toán |
| E03 | Lập phương trình từ bài toán bằng lời | 8 | — | Danh mục đề xuất |
| E04 | Phương trình tích | 9 | — | Danh mục đề xuất |
| E05 | Phương trình chứa ẩn ở mẫu | 9 | — | Danh mục đề xuất |
| E06 | Phương trình bậc hai và biệt thức | 9 | — | Danh mục đề xuất |
| E07 | Hệ thức Viète cơ bản | 9 | — | Danh mục đề xuất |
| E08 | Giải hệ bậc nhất bằng thế | 9 | — | Danh mục đề xuất |
| E09 | Giải hệ bậc nhất bằng cộng đại số | 9 | — | Danh mục đề xuất |
| E10 | Bất phương trình bậc nhất và quy tắc đổi chiều | 9 | — | Danh mục đề xuất |
| F01 | Khái niệm hàm số và giá trị hàm | 8, 10 | 6 / 3 / 2 | Nháp có kiểm tra toán |
| F02 | Tập xác định | 10 | — | Danh mục đề xuất |
| F03 | Hệ số góc và giá trị ban đầu của hàm bậc nhất | 8 | — | Danh mục đề xuất |
| F04 | Nghiệm và dấu hàm bậc nhất | 10 | — | Danh mục đề xuất |
| F05 | Đỉnh và trục đối xứng của hàm bậc hai | 10 | 6 / 3 / 2 | Nháp có kiểm tra toán |
| F06 | Khoảng đồng biến/nghịch biến của hàm bậc hai | 10 | — | Danh mục đề xuất |
| F07 | Dấu tam thức bậc hai và bất phương trình bậc hai | 10 | — | Danh mục đề xuất |
| F08 | Hàm số mũ và quy tắc lũy thừa với điều kiện áp dụng | 11 | — | Danh mục đề xuất |
| F09 | Logarit và quy tắc logarit | 11 | — | Danh mục đề xuất |
| F10 | Phương trình mũ/logarit cơ bản | 11 | — | Danh mục đề xuất |

Registry có 68 cạnh prerequisite đề xuất. `PREREQUISITE_OF` từ A → B nghĩa là A cần trước B. Đây không phải bằng chứng học sinh yếu A khi làm sai B; Agent vẫn cần bằng chứng hoặc câu hỏi chẩn đoán. Những cạnh có tính chất thiết kế theo scope phải được người duyệt xác nhận, sửa hoặc bỏ.

## Mẫu biên soạn

Để thêm pack, lấy cấu trúc hoàn chỉnh của N01 trong `pilot.v1.json` làm mẫu rồi đổi toàn bộ ID, mục tiêu và nội dung. Không tạo thêm một thư mục/file riêng cho mỗi bài.

Một pack cần:

- `concept_id`, `content_version`: khớp registry và bank.
- `explanation`: giải thích khái niệm bằng tiếng Việt, không chứa lời giải bài hiện tại.
- `problems`: ít nhất 6 bài, ít nhất 3 họ mẫu có cách làm/cấu trúc khác nhau. Đổi số trong cùng mẫu vẫn giữ `family_id` và `source_group` của họ đó.
- `examples`: ít nhất 3 ví dụ riêng; generator không được tự lấy chúng làm lời giải cho bài đang đo.
- `errors`: bước sai đầu tiên, họ lỗi, giả thuyết `suspected` và câu hỏi chẩn đoán. Không gán nhãn chắc chắn từ một lần sai.
- `hints`: đủ 3 mức theo thứ tự conceptual → strategy → scaffold. Câu hỏi gợi mở phải để học sinh tự thực hiện bước tiếp theo.
- `review`: tác giả, nguồn, trạng thái và người/thời điểm duyệt thật khi có.

Một bài có dạng:

```json
{
  "case_id": "P-A02-01",
  "concept_id": "A02",
  "primary_skill_id": "SK-A02-DISTRIBUTE",
  "family_id": "FAM-A02-positive",
  "source_group": "GROUP-A02-positive",
  "difficulty": "introductory",
  "prompt": "Khai triển 3*(x+2); trình bày các bước.",
  "task": {"kind": "polynomial", "expression": "3*(x+2)", "variable_value": null},
  "reference_answer": "3*x+6",
  "reference_steps": ["3*x+3*2", "3*x+6"],
  "split": "authoring_dev",
  "origin": "Bài tự biên soạn cho pilot."
}
```

`reference_steps` là các biểu thức/phương trình tương đương đầy đủ dành cho **kiểm tra authoring**, không phải mọi câu văn/bước giải tự do mà học sinh có thể nhập. Ngữ pháp hỗ trợ phép +, -, *, / với hằng số, ngoặc và biến `x`; đa thức không quá bậc hai. Viết phép nhân tường minh (`3*x`, `x*x`), không dùng `x^2` hoặc lời gọi hàm. Mỗi snapshot không quá 160 ký tự. Dạng ngoài phạm vi không được đưa vào bank bằng cách bỏ qua lỗi checker.

| `task.kind` | Đầu vào | Đáp án riêng / bước snapshot |
|---|---|---|
| `numeric` | Biểu thức số hữu tỉ | Biểu thức số cùng giá trị; N04 cần phân số tối giản, mẫu dương |
| `evaluate` | Đa thức và `variable_value` | Biểu thức số sau thay biến |
| `polynomial` | Đa thức một biến bậc ≤ 2 | Đa thức tương đương |
| `linear_equation` | Phương trình bậc nhất nghiệm duy nhất | Phương trình cùng nghiệm hoặc giá trị nghiệm |
| `quadratic_vertex` | Đa thức bậc hai | Cặp `(hoành độ, tung độ)`; chưa chấm trục đối xứng riêng |

F05 giới hạn bài đo ở tọa độ đỉnh. Trục đối xứng được giải thích và suy ra nhưng chưa có skill/validator đo riêng. Khi mở rộng phải cập nhật hành vi đo và tests, không tính ngầm là đã đủ toàn bộ concept.

## Review và công bố

1. Người biên soạn đối chiếu mục tiêu/lớp và sửa scope cho phù hợp.
2. Một người khác kiểm tra đáp án, cách giải khác, mẫu lỗi và gợi ý. Nhờ giáo viên/giảng viên rà prerequisite và các trường hợp khó.
3. Ghi người/thời điểm duyệt thật; duyệt curriculum alignment, concept, pack và cạnh riêng. Không tự đặt `human_approved` vì checker PASS.
4. Rà lại nội dung sinh cho học sinh: đúng scope, đúng mức gợi ý, không tiết lộ đáp án. Trước khi công bố cần bổ sung kiểm thử mức tiết lộ bằng nội dung thực tế.
5. Khi tạo bộ evaluation, chia theo `source_group`/họ mẫu; không dùng các bài authoring này làm test độc lập. Bộ records có nhãn và tình huống thích ứng theo mục 12 của plan còn phải biên soạn.

`prerequisite_candidates()` mặc định chỉ đi qua cạnh và concept đã duyệt, tối đa hai tầng, trả edge IDs. Chế độ `authoring=True` chỉ để người biên soạn xem các cạnh nháp; không dùng để ra quyết định cho học sinh.

`safe_chunks()` hiện là **tra cứu trực tiếp theo metadata**, chỉ trả giải thích/gợi ý của concept và pack đã duyệt, kèm content IDs, version, skill/lớp, nguồn và mức tiết lộ. Không trả các trường đáp án, lời giải chuẩn, examples hoặc errors. Cơ chế này chưa phải semantic RAG và chưa nối vào Agent. Các texts vẫn cần người duyệt kiểm tra tiết lộ; lọc schema không tự bảo đảm gợi ý đúng về sư phạm.

Vì chưa có reviewer, hiện có 0 nội dung công bố qua hai hàm trên. Bank nháp không được seed vào PostgreSQL sản phẩm và không xuất thành topic mới trên web. Bộ chấm online cũ vẫn chỉ hỗ trợ phương trình bậc nhất; checker authoring mới không được mô tả là đã có 10 bộ chấm người học.

## Đối chiếu nguồn

Nguồn nội dung và lớp được lưu trong `sources`/`alignment`, ngày truy cập 04/10/2026. Đã đọc [Chương trình môn Toán 2018 do Bộ GDĐT ban hành, bản Trường THCS Trương Công Định đăng lại](https://filethcs.hcm.shieldix.app/data/hcmedu/thcstruongcongdinh/2019_10/3_cttoan_610201915.pdf): phần lớp 6 cho số nguyên/phân số; lớp 7–8 cho biểu thức; lớp 8 cho phương trình bậc nhất và giá trị hàm; lớp 10 cho đỉnh hàm bậc hai. Các grade và scope vẫn cần review, nhất là concept tổng hợp nhiều hành vi.

Đã rà [Thông tư 17/2025 và tài liệu đính kèm trên Cổng văn bản Chính phủ](https://vanban.chinhphu.vn/?docid=215347&orggroupid=4&pageid=27160); Điều 1 của bản đính kèm liệt kê thay đổi môn Lịch sử/Địa lí/GDCD. Không dùng văn bản đó để chứng minh grade môn Toán. Nguồn 2018 là căn cứ đối chiếu sơ bộ, cần rà phiên bản và hướng dẫn chương trình trước nghiệm thu; chưa chọn bộ SGK. Bài pilot tự biên soạn hoặc lấy lại nội dung MVP của dự án, không sao chép bài từ PDF/SGK và không biến raw skill ASSISTments thành skill tiếng Việt.

## Chạy kiểm tra

Từ gốc repo, dùng môi trường backend đã có:

```powershell
.\.venv\Scripts\python.exe scripts/checks/check_curriculum.py
.\.venv\Scripts\python.exe -m pytest tests/test_curriculum.py -q
.\.venv\Scripts\python.exe scripts/exports/export_contracts.py --check
```

Không cần Docker, PostgreSQL hoặc OpenAI cho các lệnh authoring. CI chạy cả checker và tests này. Checker không ghi trạng thái review, không seed DB và không sửa dữ liệu ASSISTments.

Kiểm chứng ngày 04/10: **33 tests mới qua; hồi quy cuối 97 qua, 23 PostgreSQL skipped**. Schema, OpenAPI cũ và Markdown links qua; hash source/tham số BKT nghiên cứu giữ nguyên. Lần hồi quy đầu có một test cũ chạm timeout worker 3 giây; chạy lại riêng (34 tests) và hồi quy cuối đều qua, không đổi bộ chấm cũ. Đây vẫn là giới hạn vận hành cần theo dõi. [Báo cáo kiểm tra và SHA-256](../../docs/implementation/curriculum/checks.v1.json) lưu cả kết quả lần đầu và lần cuối; XML chứa output local nằm trong `data/test-runs/`.

## Bước tiếp theo

Mốc này hoàn thành registry và pilot authoring có kiểm tra; chưa phải prototype đủ module. Tiếp theo mở rộng parser/validator người học theo từng dạng, có ca đầu vào mơ hồ và phương pháp giải khác; nối KG/RAG vào Agent với decision log, backtrack/return và kiểm soát nội dung. Khi duyệt được pilot và luồng học ổn mới mở rộng khoảng 20 → 30 → 40 concept. Không tự chốt benchmark test hoặc đưa tham số ASSISTments vào bộ tiếng Việt.
