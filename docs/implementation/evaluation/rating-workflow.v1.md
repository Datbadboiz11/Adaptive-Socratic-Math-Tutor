# Quy trình chấm ẩn cấu hình, bản v1

**Trạng thái:** bản nháp của Member 3, code và test xong, **chưa có lượt chấm thật nào**. Đã tạo bộ bài pilot từ câu model thật của lô `dev-04` (§6.1), chờ hai người chấm.
**Căn cứ:** plan §18.2, §19.1–§19.3; PRD §9.2, §9.4. **Hướng dẫn cho người chấm:** [socratic-rubric.v1.md](socratic-rubric.v1.md).

## 1. Vai trò

Rubric Socratic là thước đo chính của RQ1b (Full/No-BKT/Heuristic), RQ2 (Full/No-KG) và RQ5 (Full/Rule-policy), và là phần chấm đầu ra của RQ3 (Full/No-RAG, plan §17). Phần này gồm:

- định nghĩa rubric trong code để phiếu chấm được kiểm tra;
- tạo bộ bài **ẩn cấu hình, thứ tự ngẫu nhiên riêng cho từng người chấm**, có cả so sánh ghép cặp trên cùng state;
- đọc phiếu, tính **độ đồng thuận trên điểm trước hòa giải**, tổng hợp điểm cuối theo từng chiều.

Nó không sinh câu và không gọi model. Câu cần chấm do [`run_ablation.py`](ablation-runner.v1.md) ghi ra ở dạng `SystemOutput`.

## 2. Thành phần

| File | Việc |
|---|---|
| [`research/evaluation/rubric.py`](../../../research/evaluation/rubric.py) | Sáu chiều, mức điểm, cờ nghiêm trọng; hợp đồng `SystemOutput`, `RatingItem`, `PairItem`, `Rating`, `PairJudgment`, `PacketKey` |
| [`research/evaluation/build_rating_packet.py`](../../../research/evaluation/build_rating_packet.py) | Tạo bộ bài: ngữ cảnh từ bộ tình huống, ẩn hệ thống, xáo thứ tự, phiếu CSV |
| [`research/evaluation/score_ratings.py`](../../../research/evaluation/score_ratings.py) | Đọc và kiểm tra phiếu, độ đồng thuận, điểm cuối, tổng hợp, phiếu hòa giải |
| [`research/evaluation/agreement.py`](../../../research/evaluation/agreement.py) | Cohen's kappa, weighted kappa, bootstrap theo nhóm; không dùng thư viện ngoài |
| [`contracts/evaluation/`](../../../contracts/evaluation/) | JSON Schema xuất từ các hợp đồng trên |
| [`tests/test_evaluation.py`](../../../tests/test_evaluation.py) | 26 test, không gọi API |

## 3. Luồng dữ liệu

```text
SystemOutput (JSONL: tình huống × hệ thống → câu, action, hint_level)
   │
   ▼ build_rating_packet.py
<packet>/key.json               mã → hệ thống, action; KHÔNG đưa người chấm
<packet>/items.jsonl            các câu đã ẩn hệ thống
<packet>/raters/<id>/items.md   ngữ cảnh + câu, thứ tự riêng của người đó
<packet>/raters/<id>/ratings.csv
<packet>/raters/<id>/pairs.md|csv   khi có --compare
   │  người chấm điền CSV, độc lập
   ▼ score_ratings.py
<packet>/report.json            đồng thuận, điểm theo hệ thống, ghép cặp
<packet>/reconciled/ratings.todo.csv   câu hai người chấm khác nhau
   │  hòa giải: điền reconciled/ratings.csv (cùng cột)
   ▼ score_ratings.py (chạy lại)
```

Bộ bài chứa câu của hệ thống và điểm của người chấm, nên để trong `data/` (đã ignore). Script không ghi đè thư mục đã có file, để không mất phiếu đã chấm.

Trước khi đọc điểm, `score_ratings.py` kiểm tra dòng tiêu đề của từng phiếu. Phiếu lưu lại bằng dấu chấm phẩy hoặc tab (Excel dùng dấu phân cách của máy) vẫn đọc được. Phiếu thiếu cột, dùng dấu phân cách khác hoặc không phải UTF-8 làm script dừng và báo tên file, để phiếu hỏng không bị tính là "chưa chấm".

### 3.1. Đầu vào `SystemOutput`

Một dòng JSON cho mỗi cặp (tình huống, hệ thống): `scenario_id`, `system` (ví dụ `full`, `no_kg`, `rule_policy`), `message`, và nếu có `action`, `intent`, `hint_level`, `problem_id` (bài mới mà câu giao), `response_source`. Mỗi cặp (tình huống, hệ thống) chỉ có một câu.

### 3.2. Người chấm thấy gì

Ngữ cảnh lấy từ state của tình huống, **giống nhau cho mọi hệ thống** (đánh giá một lượt từ cùng state, plan §18.2): đề, đáp án, lý do lượt (nộp bài, xin gợi ý...), bài làm, lời nhắn, kết quả chấm bài (bước sai đầu tiên, họ lỗi, giả thuyết hiểu nhầm), mức hỗ trợ đã dùng, bằng chứng từng skill, các lượt gần đây.

| Ẩn khỏi người chấm | Lý do |
|---|---|
| Tên hệ thống, action, intent, hint_level của câu | Ẩn cấu hình (plan §19.1). Người chấm đánh giá câu học sinh thấy. |
| Xác suất mastery của BKT | Không lấy giá trị BKT làm chuẩn (PRD §9.4); nếu không, RQ1b sẽ chấm BKT bằng chính BKT. Người chấm thấy bằng chứng quan sát được: số lần tự làm, đúng/sai gần nhất, số lần đúng sau gợi ý. |
| Tập action chấp nhận được của tình huống | Dùng để tính tự động tỷ lệ chọn đúng tập, không để định hướng người chấm. |

Đáp án được hiện cho người chấm (giống "gold solution" trong guideline MRBench) vì không có nó thì không chấm được "Không tiết lộ". Câu giao bài mới có kèm đề và đáp án bài mới ngay bên dưới (`TutorTurn`). Ở phiếu ghép cặp, mỗi phía A, B mang bài của riêng mình, vì hai hệ thống có thể giao hai bài khác nhau.

### 3.3. Ngẫu nhiên và tái lập

Một `--seed` quyết định mã câu, thứ tự của từng người chấm và bên A của từng cặp. Cùng đầu vào và seed thì ra cùng bộ bài. Seed được ghi trong `key.json` và cũng dùng cho bootstrap.

### 3.4. Phiên bản rubric

`key.json` ghi phiên bản rubric lúc tạo bộ bài. Pilot dùng để sửa guideline; mỗi lần đổi mức điểm hay luật cờ thì tăng `RUBRIC_VERSION`. Đánh giá chính thức chạy trên một phiên bản cố định: `score_ratings.py` dừng nếu phiên bản của bộ bài khác phiên bản trong code, nên điểm của hai phiên bản không bị gộp hay kiểm tra bằng luật của nhau.

## 4. Tính điểm

### 4.1. Đồng thuận (trước hòa giải)

Cho từng cặp người chấm, trên các câu cả hai cùng chấm:

| Chỉ số | Áp dụng cho |
|---|---|
| Weighted kappa, trọng số bậc hai (đổi bằng `--weights linear`), kèm tỷ lệ trùng khớp | Từng chiều 0–2; bỏ câu `na` hoặc không chấm được. Số câu một người ghi `na` còn người kia cho điểm được báo riêng (`na_mismatch`) |
| Cohen's kappa | Từng cờ nghiêm trọng; nhãn "không chấm được"; lựa chọn ghép cặp |

Lựa chọn ghép cặp được đổi về theo hệ thống (tham chiếu / so sánh / ngang nhau) trước khi so, vì A/B của hai người chấm có thể ngược nhau. Kappa là `None` khi không xác định, ví dụ cả hai người chấm cùng cho mọi câu 2 điểm.

### 4.2. Điểm cuối của một câu

1. Có bản hòa giải → dùng bản hòa giải (`reconciled`).
2. Mọi người chấm trùng nhau ở cả điểm, cờ và "không chấm được" → dùng điểm đó (`agreed`).
3. Chỉ một người chấm → dùng điểm đó, đánh dấu `single`. Chỉ hợp với pilot; chạy chính thức cần hai người chấm.
4. Còn lại → `unresolved`, không vào tổng hợp và được ghi vào `reconciled/ratings.todo.csv` kèm điểm từng người.

Ghép cặp theo cùng quy tắc. Ở phiếu hòa giải ghép cặp, A/B theo bản của **người chấm đầu tiên** trong `key.json`; buổi hòa giải đọc `pairs.md` của người đó.

### 4.3. Tổng hợp theo hệ thống

- Từng chiều: trung bình, phân bố 0/1/2, số câu `na`, khoảng tin cậy 95%. Báo từng chiều, không cộng tổng (plan §19.2).
- Tỷ lệ thất bại: câu có ít nhất một cờ nghiêm trọng, kèm số lần mỗi cờ.
- Tỷ lệ action thuộc tập chấp nhận được / bị cấm của tình huống, tính từ `key.json`, không qua người chấm.
- Ghép cặp: số lần hệ thống tham chiếu thắng, hệ thống so sánh thắng, ngang nhau, chưa hòa giải.
- Khoảng tin cậy: bootstrap percentile, **lấy mẫu lại theo tình huống** (plan §19.3), 2000 lần.

## 5. Quyết định cần nhóm chốt trước khi chấm thật

| Quyết định | Đang làm | Vì sao cần chốt |
|---|---|---|
| Mô tả mức 1 và 0, ví dụ | Bản nháp trong guideline, dùng để chấm thử | Plan chỉ định nghĩa mức 2. Hai người chấm độc lập một tập nhỏ, đối chiếu câu bất đồng rồi sửa guideline; đánh giá chính thức dùng một phiên bản cố định (§3.4) |
| Kiểu trọng số kappa | Bậc hai | Plan chỉ ghi "weighted kappa". Bậc hai phạt lệch 0↔2 nặng hơn hẳn lệch 0↔1; chưa có căn cứ nói nó tốt hơn tuyến tính cho rubric này. Chốt một kiểu trước khi xem kết quả |
| `na` cho "Bám lỗi" và "Gợi mở" | Chỉ ở lượt tạm dừng hoặc kết thúc phiên; học sinh làm đúng vẫn là lượt học. Câu `na` không vào mẫu số của chiều đó và được đếm riêng | Plan ghi mỗi chiều 0–2; cách khác là bỏ các lượt đó khỏi tập chấm |
| Cờ nghiêm trọng kéo theo điểm 0 | Bắt buộc | Tránh phiếu "lộ đáp án" mà "Không tiết lộ" vẫn 2 |
| "Không tiết lộ" = 0 kéo theo cờ `solution_revealed` | Bắt buộc; "Đúng toán" = 0 thì không bắt buộc cờ | Mức 0 của chiều này trùng định nghĩa của cờ. Nếu không bắt buộc, câu lộ đáp án có thể không vào tỷ lệ thất bại. Cách khác là bỏ cột cờ và suy ra thất bại từ điểm 0 |
| Bước sửa đúng của một bước tính là lộ một phần (mức 1) | Có, khi học sinh còn ít nhất một bước biến đổi phải tự làm. Bước được đưa là đáp án cuối, hoặc chỉ còn một phép tính số, thì 0 điểm kèm cờ | Plan chỉ nói "đáp án/lời giải hoàn chỉnh" là không đạt. Mức 1 ở đây không có nghĩa là hỗ trợ tốt: câu đó vẫn bị chấm thấp ở "Gợi mở" hoặc "Phù hợp người học" |
| Người chấm và cách chia bài | Chưa phân công. Công cụ giao **mọi** câu và cặp cho từng người chấm, không chia đôi | Hai người chấm độc lập (plan §19.2), nên câu nào cũng phải có đủ hai phiếu mới tính được đồng thuận. "Không chấm bài của chính mình" nghĩa là không chấm câu mẫu hay nhãn chuẩn do mình soạn: câu oracle và câu lỗi của bộ pilot do Member 3 soạn, nên Member 3 không chấm pilot. PRD §9.5 lưu ý khối lượng chấm lớn khi nhân số tình huống × cấu hình × người chấm |

## 6. Pilot hiện có

`--pilot` tạo bộ bài từ 16 tình huống dev: câu template của Rule-policy, câu oracle và câu lỗi đã soạn của bộ ca sinh phản hồi (57 câu, bỏ các câu lỗi cần lịch sử tin nhắn mới chấm được). Bộ này để thử guideline và đo độ đồng thuận ban đầu, **không phải đánh giá hệ thống**: câu oracle và câu lỗi do chính người viết verifier soạn.

### 6.1. Pilot trên câu model thật: `data/rating/dev-04-pilot-v2`

Pilot rubric của plan §19.3 bước 1, dùng câu model thật của lô `dev-04` ([ablation-runner §5.3](ablation-runner.v1.md)), lần lặp thứ nhất:

- **Phạm vi:** 14 tình huống × 3 hệ thống (Full, Rule-policy, Socratic LLM baseline) = 42 câu, và 28 cặp ghép (Full với Rule-policy, Full với baseline), cho hai người chấm `r1`, `r2`. Ba hệ thống này phủ RQ5 và mốc tham chiếu baseline; cả lô (7 hệ thống, 112 câu, 96 cặp mỗi người) quá nặng cho bước thử guideline.
- **Bỏ `SC-04` và `SC-15`:** ngữ cảnh của hai tình huống này trong lô `dev-04` mâu thuẫn (bài làm không khớp kết quả chấm), và fixture đã được sửa sau lô đó. Phiếu dựng ngữ cảnh từ fixture hiện tại, nên giữ chúng thì người chấm thấy bài làm mới cạnh câu trả lời viết cho bài cũ.
- **Đầu vào đã lọc** ở `data/rating/dev-04-pilot-v2-input.jsonl`; seed mặc định 0.
- **Người chấm:** câu do model sinh, không do Member 3 soạn, nên Member 3 có thể là một trong hai người chấm pilot. Người thứ hai nên là Member 1 hoặc Member 2. Mỗi người chỉ nhận thư mục `raters/<mã>/` của mình, không nhận `key.json`, và chấm đủ cả bộ.
- **Đây là chấm nội bộ.** Member 3 phát triển prompt và policy nên có thể nhận ra kiểu câu của từng hệ thống dù đã ẩn tên. Báo cáo điểm pilot phải ghi rõ điều này.
- **Giữ điểm ban đầu:** phiếu của từng người giữ nguyên sau khi nộp; hòa giải ghi vào `reconciled/`, không sửa phiếu gốc. Độ đồng thuận tính trên điểm trước hòa giải (§4).
- Điểm pilot dùng để sửa guideline và đo đồng thuận ban đầu, không dùng để so sánh cấu hình.
- Bản phiếu đầu `data/rating/dev-04-pilot` (còn `SC-04`, `SC-15`) được thay bằng bản này và không dùng; nó chưa có điểm nào.

```powershell
# Sau khi hai người điền raters/r1/ratings.csv, pairs.csv và raters/r2/...
.\.venv\Scripts\python.exe research/evaluation/score_ratings.py --packet data/rating/dev-04-pilot-v2
```

## 7. Giới hạn và việc tiếp theo

| Giới hạn | Ảnh hưởng | Hướng xử lý |
|---|---|---|
| Câu thật mới có từ một lô dev chạy một lần (`dev-02`), và lô đó còn lỗi hệ thống đã biết ([ablation-runner §5.1](ablation-runner.v1.md)): 15/96 lượt gửi câu template, 15/80 cặp có hai câu giống hệt nhau | Chấm lô này tốn công cho các lỗi đã biết; kết quả không dùng để so sánh cấu hình | Dùng lô này để thử guideline trên câu thật; sửa lỗi ở §5.1 và chạy lại trước khi chấm để so sánh |
| Chỉ đọc bộ tình huống dev (16 tình huống, một bài toán chính) | Chưa phủ concept; không dùng làm kết quả | Bộ tình huống thích ứng dev/test theo plan §11.5, §12 |
| Ngữ cảnh lấy đề và đáp án từ problem bank mẫu (`stubs.py`) | Bài ngoài bank mẫu không có đáp án hiện cho người chấm | Đổi sang problem bank thật của Member 2 |
| Câu template có câu chữ cố định | Người chấm có thể nhận ra câu template, ẩn cấu hình không tuyệt đối | Ghi vào báo cáo; so sánh chính là giữa các cấu hình cùng dùng LLM viết câu |
| Người chấm trong nhóm đều tham gia xây hệ thống | Ẩn cấu hình không làm họ độc lập với dự án; họ có thể nhận ra kiểu câu của từng cấu hình | Ưu tiên có người chấm ngoài nhóm; nếu chỉ chấm nội bộ thì ghi rõ giới hạn này trong báo cáo |
| Chỉ chấm một lượt | Chưa có chỉ số nhiều lượt (plan §19.1: đạt mục tiêu scenario, số lượt, lặp) | Làm sau khi có quỹ đạo nhiều lượt |
| Chưa có LLM-as-judge | Chỉ có người chấm | LLM judge chỉ hỗ trợ, không là nguồn chấm duy nhất (plan §19.2) |

## 8. Lệnh

```powershell
# Tạo bộ bài pilot cho hai người chấm (không gọi API)
.\.venv\Scripts\python.exe research/evaluation/build_rating_packet.py --pilot --raters r1 r2 --out data/rating/pilot-01

# Bộ bài từ lô dev-02 đã hoàn tất, có so sánh ghép cặp; không gọi API.
.\.venv\Scripts\python.exe research/evaluation/build_rating_packet.py --outputs data/ablation/dev-02/outputs.jsonl --raters r1 r2 `
    --compare full:no_bkt full:heuristic full:no_kg full:no_rag full:rule_policy --out data/rating/dev-02

# Tính điểm (chạy lại sau khi hòa giải)
.\.venv\Scripts\python.exe research/evaluation/score_ratings.py --packet data/rating/pilot-01

.\.venv\Scripts\python.exe -m pytest -q tests/test_evaluation.py
.\.venv\Scripts\python.exe scripts/exports/export_agent_contracts.py --check
```
