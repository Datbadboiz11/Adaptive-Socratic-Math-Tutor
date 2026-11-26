# Chọn ngưỡng mastery trên dev v1

Trạng thái: đã có công cụ sàng lọc, kết quả trên bộ 16 ca, bộ replay và bộ dev pilot đã duyệt nhãn. **Ngưỡng giữ ở giá trị khởi đầu (§4.2); chưa chốt ngưỡng chính thức**, vì bộ dev hiện có chưa đủ (§5).

Plan §18.2: "ngưỡng quyết định được chọn trên dev theo cùng ngân sách, không mặc định ngưỡng xác suất BKT áp nguyên cho heuristic". Trước đây Heuristic dùng y hệt ngưỡng BKT (`backend/app/agent/mastery.py`, `THRESHOLDS`). Công cụ `research/evaluation/select_thresholds.py` chọn ngưỡng cho từng loại ước lượng theo cùng một quy trình, và đo độ nhạy của quyết định theo ngưỡng. Công cụ không gọi API.

## 1. Ngưỡng được thử

Policy so ba ngưỡng: ước lượng là thấp khi `< low`, tốt khi `>= good`, đủ để chuyển concept khi `>= ready`. Mỗi phép so có điều kiện bằng chứng đi kèm:

| Ngưỡng | Dùng ở | Điều kiện bằng chứng (giữ cố định) |
|---|---|---|
| `low` | `standing` → bằng chứng `low_estimate` của skill nền (gate G18, Rule-policy, `facts` của Agent LLM) | `MIN_OBSERVATIONS_FOR_ESTIMATE = 2` |
| `good` | `standing`; luật lỗi thao tác khi lịch sử tốt (Rule-policy) | `MIN_OBSERVATIONS_FOR_ESTIMATE = 2` (luật lỗi thao tác trước đây viết riêng `n >= 2`, nay dùng cùng hằng số) |
| `ready` | `compute_readiness` → gate G07 | `READY_MIN_OBSERVATIONS = 3`, hai lần độc lập gần nhất đúng, không còn giả thuyết lỗi mở |

Đợt này chỉ thử ba ngưỡng. Các điều kiện bằng chứng giữ cố định, vì đổi chúng cùng lúc sẽ làm số ứng viên tăng nhanh và khó biết thay đổi nào gây ra khác biệt.

## 2. Ứng viên và ngân sách

**Heuristic (`recent_ratio`).** Tỷ lệ đúng của cửa sổ 2–5 observation chỉ nhận 11 giá trị k/n: 0, 1/5, 1/4, 1/3, 2/5, 1/2, 3/5, 2/3, 3/4, 4/5, 1. Ứng viên là mọi bộ `low ≤ good ≤ ready` lấy từ các giá trị này (286 bộ). Hai bộ cho cùng cách phân loại trên **mọi** cửa sổ observation có thể có (độ dài 1–5, theo đúng cách so và điều kiện bằng chứng ở §1) chỉ giữ một bộ. Còn lại 266 bộ. Bộ khởi đầu (2/5, 3/5, 4/5) được giữ làm đại diện của nhóm của nó. Test đối chiếu cách khử trùng này với `standing` và `compute_readiness` thật trên mọi cửa sổ.

**BKT.** P(L) là số liên tục nên không khử trùng được như trên. Để cùng ngân sách, BKT có đúng số ứng viên như Heuristic (266 bộ), lấy từ lưới 0,05–0,95 bước 0,05 (các bộ `low ≤ good ≤ ready`) theo thứ tự khai báo trước: gần bộ khởi đầu (0,4; 0,6; 0,8) nhất theo khoảng cách L1, rồi giá trị nhỏ hơn.

Hai bên dùng danh sách giá trị khác nhau nhưng cùng số ứng viên và cùng tiêu chí chọn.

## 3. Đánh giá và tiêu chí chọn

Mỗi bộ ngưỡng được tính lại từ đầu như node `readiness` → `decide` của graph:

1. Chiếu state theo cấu hình: Full cho BKT, Heuristic cho tỷ lệ đúng (`project_state`).
2. Tính lại readiness bằng bộ ngưỡng đang thử. Readiness đã lưu trong tình huống không được dùng.
3. Rule-policy đề xuất, gate kiểm tra, fallback như `run_decision`.

Ngưỡng chỉ có hiệu lực trong lúc đánh giá (`mastery.thresholds_override`, giới hạn trong khối `with`). Ngưỡng của luồng dạy thật không đổi.

Chỉ số mỗi bộ: số quyết định cuối nằm trong `acceptable_actions`, số nằm trong `forbidden_actions`, số đề xuất bị gate từ chối, số lỗi, số tình huống đủ readiness, và số tình huống đổi quyết định so với bộ khởi đầu.

Độ nhạy được so ở hai mức, giống script ablation (`COMPARISONS` trong `run_ablation.py`):

- **action/intent:** chỉ so action và intent.
- **quyết định đầy đủ:** so thêm skill mục tiêu, mức hint, bài được giao, nội dung và cạnh KG được chọn. Ví dụ trong test: SC-15 được thêm một skill nền yếu (`SK-A03-COLLECT`, P(L) = 0,1). Với `low = 0,2` policy kiểm tra skill thu gọn biểu thức; với `low = 0,4` policy kiểm tra skill tính phân phối. Cả hai đều là `diagnose` / `probe_prerequisite` / mức 0: mức action/intent không thấy thay đổi này, còn mức đầy đủ có thấy.

Khi skill mục tiêu thay đổi theo ngưỡng, báo cáo của từng tình huống liệt kê các skill đó.

**Tiêu chí chọn, khai báo trước, giống nhau cho hai bên** (`SELECTION`): ít lỗi nhất → nhiều quyết định chấp nhận được nhất → nhiều quyết định khớp nhãn chi tiết (intent/skill) nhất → ít quyết định bị cấm nhất → ít lần gate từ chối nhất. Tiêu chí nhãn chi tiết được thêm ở bản `select-thresholds-0.3.0`, trước khi có lần chọn chính thức nào; nó chỉ tính trên các ca có nhãn intent hoặc skill ([adaptive-scenarios](adaptive-scenarios.v1.md)). Hòa ở mọi chỉ số thì chọn bộ gần bộ khởi đầu nhất (L1), rồi bộ có giá trị nhỏ hơn. Số bộ hòa điểm và khoảng giá trị của chúng luôn được báo cáo: nhiều bộ hòa nghĩa là bộ dev chưa phân biệt được các ngưỡng, không phải ngưỡng được chọn là tốt nhất.

Công cụ từ chối bộ tình huống không phải split dev (plan §11.5: test không được dùng để điều chỉnh ngưỡng).

**Dấu vân tay của dữ liệu đầu vào** (`summary.json`, `inputs`) có hai phần, áp dụng như nhau cho bộ mặc định và file replay:

- `loaded_sha256`: hash của mọi state, context và nhãn đã nạp, tức đúng dữ liệu công cụ đánh giá.
- `source_files`: hash từng file nguồn. Bộ mặc định ghép state từ `fixtures.v1.json` và `scenarios.dev.v1.json`, nên hash cả hai file.

Sửa fixture vẫn đổi hash, kể cả khi danh sách ID và phiên bản policy giữ nguyên.

## 4. Kết quả chạy thử đầu tiên

Rule-policy `rule-policy-0.4.0`, readiness `stop-0.1.0`, gate `gate-0.5.0`. Kết quả nằm ở thư mục tạm, chưa ghi vào `data/`.

| Bộ tình huống | Loại ước lượng | Số bộ thử | Hòa điểm với bộ được chọn | Cách quyết định khác nhau (action/intent; đầy đủ) | Tình huống đổi quyết định (ở cả hai mức) |
|---|---|---|---|---|---|
| 16 tình huống soạn tay (`contracts/agent/scenarios.dev.v1.json`) | BKT | 266 | 266 (16/16 chấp nhận được) | 2; 2 | `SC-15` |
| | Heuristic | 266 | 255 (16/16) | 4; 4 | `SC-04`, `SC-15` |
| 6 tình huống replay nhãn nháp (`contracts/scenarios/examples.dev.v1.json`) | BKT | 266 | 266 (5/6) | 1; 1 | không có |
| | Heuristic | 266 | 266 (5/6) | 1; 1 | không có |

Trên hai bộ này, không tình huống nào chỉ đổi ở mức đầy đủ: những ca đổi skill hay nội dung cũng đổi luôn intent.

Đọc kết quả:

- **Bộ dev chưa chọn được ngưỡng.** Ở cả hai loại ước lượng, bộ được chọn là bộ khởi đầu chỉ vì luật hòa điểm.
- **`ready` chưa được đánh giá.** Không tình huống nào đủ readiness với bất kỳ bộ ngưỡng nào: các điều kiện bằng chứng (đủ observation, hai lần gần nhất đúng, không còn giả thuyết lỗi) luôn có ít nhất một điều kiện chưa đạt. Ngưỡng `ready` hiện không ảnh hưởng tới quyết định nào trên dev.
- **`SC-15`** (skill nền có ước lượng thấp: BKT 0,3; Heuristic 1/3) đổi quyết định theo `low`. Khi ước lượng dưới `low`, policy kiểm tra skill nền: `probe_prerequisite` trên `SK-A02-DISTRIBUTE`. Khi không, policy hỏi cách làm: `elicit_reasoning` trên `SK-E02-SOLVE`. Action vẫn là `diagnose`, nên nhãn theo action không phân biệt được hai trường hợp này.
- **`SC-04`** (lỗi tính toán, lịch sử 4/5 đúng) chỉ mất quyết định chấp nhận được với Heuristic khi `good = 1`. Lúc đó lịch sử 4/5 không còn là "tốt", và policy hỏi chẩn đoán thay vì nhắc tự kiểm tra.

### 4.1. Chạy thử trên bộ dev pilot

Bộ dev pilot (`contracts/scenarios/pilot.dev.v1.json`, 33 ca, lúc này nhãn còn là nháp; Rule-policy `rule-policy-0.4.0`) có các ca sát ranh giới ngưỡng, ca đạt readiness và nhãn intent hoặc skill cho 22 ca. Công cụ bản `select-thresholds-0.3.0`.

| Loại ước lượng | Số bộ thử | Bộ khởi đầu | Bộ được chọn | Hòa điểm với bộ được chọn | Tình huống đổi quyết định |
|---|---|---|---|---|---|
| BKT | 266 | 33/33 action, 21/22 chi tiết | 0,10 / 0,60 / 0,80: 33/33, 22/22 | 1 | DP-19, DP-24, DP-33 |
| Heuristic | 266 | 33/33 action, 21/22 chi tiết | 0 / 3/5 / 4/5: 33/33, 22/22 | 19 (low = 0; good 1/2–4/5; ready 3/5–1) | DP-18 – DP-21, DP-23, DP-24, DP-29, DP-33 |

Đọc kết quả:

- **`ready` bắt đầu được đánh giá.** Với BKT, 101 bộ có `ready` dưới 0,80 cho DP-24 (hai bài đầu sai, hai bài sau đúng) chuyển concept, trái nhãn nháp. Với Heuristic, các bộ hòa điểm cao nhất đều có `ready` từ 3/5 trở lên.
- **`good` có cận dưới với Heuristic** (1/2): thấp hơn thì các ca lịch sử yếu (DP-20, DP-21) bị xử lý như sơ suất đơn lẻ.
- **`low` bị quyết định bởi đúng một ca, và không nên tin.** Ở DP-33, học sinh vừa phân phối đúng và chỉ tính sai, nhưng ước lượng kiến thức nền còn thấp (BKT 0,12; Heuristic 0/2). Với mọi `low` cao hơn ước lượng đó, Rule-policy hỏi kiểm tra tính phân phối, trái nhãn nháp. Vì vậy công cụ chọn `low` thấp nhất (0,10 và 0), tức gần như tắt bằng chứng "ước lượng thấp". Đây là dấu hiệu về **logic của policy** (dùng ước lượng cũ dù bài làm hiện tại cho thấy điều ngược lại), không phải căn cứ để hạ ngưỡng. Các ca còn lại không phân biệt được `low`.
- **Kiểm tra bỏ riêng DP-33:** bộ được chọn quay về bộ khởi đầu ở cả hai loại ước lượng (BKT 165 bộ hòa điểm, Heuristic 190). Vậy việc hạ `low` hoàn toàn do một ca. Ngoài ra `low = 0` với Heuristic nghĩa là không tỷ lệ nào còn bị xếp là thấp (điều kiện `< low` không bao giờ đúng).
- **Không dùng kết quả này để chốt.** Một ca đổi được bộ được chọn cho thấy bộ dev còn quá nhỏ. Nhãn nháp lại do cùng công cụ đã viết Rule-policy soạn. Cần người khác duyệt nhãn (nhất là DP-33), quyết định có sửa policy không, rồi chạy lại.

### 4.2. Sau khi duyệt nhãn và sửa Rule-policy: quyết định hiện tại

Member 3 đã duyệt 33 nhãn của bộ pilot, kể cả nhãn DP-33. Vì nhãn DP-33 đúng, chỗ cần sửa là policy chứ không phải `low`. Rule-policy lên `rule-policy-0.5.0`: khi lỗi vừa chấm là lỗi thao tác (`arithmetic_error`, `sign_error`, `copy_error`) quy cho chính skill đích của bài đang làm, policy chỉ hỏi kiểm tra hay quay lại một skill nền khi có **bằng chứng trực tiếp** về skill nền đó: lỗi quy cho nó, hoặc câu kiểm tra đã được xác minh là chưa đạt. Bằng chứng suy từ các lần làm trước (ước lượng thấp, giả thuyết lỗi còn mở) không đủ, vì lỗi hiện tại là bằng chứng mới nhất và không nói gì về skill nền. Bộ 16 tình huống cũ không đổi quyết định nào.

Giới hạn: policy không biết các bước làm đúng đã dùng những skill nào (assessment chỉ có bước sai đầu tiên và skill của lỗi), nên họ lỗi thao tác là cách gần đúng. Với lỗi khác loại, ví dụ lỗi biến đổi ở bước 2 sau khi đã phân phối đúng ở bước 1, policy vẫn hỏi kiểm tra skill nền có ước lượng thấp. Muốn xử lý đúng cần analyzer gắn skill cho từng bước (hợp đồng với Member 1).

Chạy lại trên bộ pilot (33 ca, nhãn đã duyệt):

| Loại ước lượng | Bộ khởi đầu | Bộ được chọn | Hòa điểm | Tình huống đổi quyết định |
|---|---|---|---|---|
| BKT | 33/33 action, 22/22 chi tiết | 0,40 / 0,60 / 0,80 | 165 (low 0,10–0,60; good 0,35–0,80; ready 0,80–0,95) | DP-19, DP-24 |
| Heuristic | 33/33 action, 22/22 chi tiết | 2/5 / 3/5 / 4/5 | 144 (low 0–4/5; good 1/2–4/5; ready 3/5–1) | DP-18 – DP-21, DP-23, DP-24, DP-29 |

**Quyết định (tạm, chưa phải ngưỡng chốt):** giữ nguyên `THRESHOLDS` ở giá trị khởi đầu cho cả hai loại ước lượng.

- **`low`: giữ 0,4 (BKT) và 2/5 (Heuristic), chưa có bằng chứng để chọn.** Các bộ `low = 0,10` (BKT) và `low = 0` (Heuristic) ở §4.1 chỉ là kết quả công cụ khớp ngưỡng vào DP-33. `low = 0` còn làm Heuristic mất hẳn khả năng nhận ra skill yếu, vì không tỷ lệ nào nhỏ hơn 0. Sau khi sửa policy, không ca nào phân biệt được `low`.
- **`good` = 0,6 / 3/5 và `ready` = 0,8 / 4/5: tiếp tục dùng làm giá trị khởi đầu**, có bằng chứng sàng lọc ban đầu: `ready` của BKT không nên dưới 0,8 (DP-24), `ready` của Heuristic không nên dưới 3/5, `good` của Heuristic không nên dưới 1/2 (DP-20, DP-21).
- Ngưỡng chính thức vẫn chọn lại trên bộ dev đã mở rộng, có nhãn độc lập của người thứ hai, rồi khóa trước khi chạy test (plan §10, §24).

## 5. Giới hạn và việc tiếp theo

| Giới hạn | Ảnh hưởng | Cách xử lý |
|---|---|---|
| Bộ 16 tình huống có mastery soạn tay; bộ replay chỉ có 6 ca nhãn nháp | Ngưỡng chọn trên đó không đáng tin; không được khóa | Chọn ngưỡng chính thức trên bộ dev đã mở rộng (plan §12: 160–200 tình huống), có lịch sử replay và nhãn đã review |
| Hầu như không tình huống nào nằm gần ranh giới ngưỡng; không ca nào đạt readiness | Hầu hết ứng viên hòa điểm; `ready` không được đánh giá | Khi mở rộng bộ tình huống, thêm các ca ở sát ranh giới `low`/`good` và các ca đủ điều kiện readiness |
| Nhãn chỉ theo action | Không phân biệt `probe_prerequisite` với `elicit_reasoning` (`SC-15`) | Nếu cần, thêm nhãn intent chấp nhận được cho các ca nhạy theo ngưỡng |
| Sàng lọc bằng Rule-policy | Agent LLM còn nhận giá trị mastery và tự đề xuất action, nên có thể phản ứng khác với ngưỡng | Sau khi chọn, chạy lại `run_ablation.py` (Full, Heuristic) với bộ ngưỡng đã chọn; lần này gọi model thật nên cần xác nhận trước |
| Chưa thử điều kiện bằng chứng | `MIN_OBSERVATIONS_FOR_ESTIMATE`, `READY_MIN_OBSERVATIONS` vẫn là giá trị khởi đầu | Đợt sau, nếu cần, thử thêm với cùng ngân sách cho hai bên |
| Ngưỡng BKT phụ thuộc bộ tham số BKT (Member 1) | Đổi tham số thì P(L) đổi, ngưỡng đã chọn có thể phải chọn lại (plan §16) | Ghi version tham số BKT cùng ngưỡng khi chốt |
| Backend sản phẩm chưa điền `recent_independent` khi tạo state cho Agent | Heuristic chỉ chạy được trong replay và fixtures | Thống nhất với Member 1 (plan §23.1: state Agent đọc vào), theo định nghĩa "độc lập" của plan §8.3 |

Khi chốt ngưỡng: lưu toàn bộ `candidates.jsonl` và `summary.json` (phiên bản công cụ, policy, readiness, gate; dấu vân tay dữ liệu đầu vào) vào `data/thresholds/`, ghi bộ được chọn và lý do vào tài liệu này, cập nhật `THRESHOLDS`, rồi khóa trước khi chạy test (plan §10, §24).

## 6. Lệnh

```powershell
python research/evaluation/select_thresholds.py --out data/thresholds/dev-01
python -m research.scenarios.build --input contracts/scenarios/examples.dev.v1.json --out data/scenarios/<bản>
python research/evaluation/select_thresholds.py --scenario-set data/scenarios/<bản>/dev.json --out data/thresholds/<tên>
.\.venv\Scripts\python.exe -m pytest -q tests/test_select_thresholds.py
```

Thư mục `--out` phải mới; công cụ không ghi đè kết quả cũ.
