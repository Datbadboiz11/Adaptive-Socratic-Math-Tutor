# Script chạy ablation, bản v1

**Trạng thái:** bản nháp của Member 3, code và test xong cho đủ 7 cấu hình của plan §18.1, gồm Socratic LLM baseline (§3.1). Với model thật **đã chạy một lần đủ 16 tình huống dev × 6 cấu hình** (§5.1), khi chưa có baseline; chưa lặp và chưa có ai chấm câu. Baseline chưa chạy với model thật. Số liệu của LLM giả không nói gì về chất lượng của model.
**Căn cứ:** plan §17 (RQ1b, RQ2, RQ5), §18.1, §18.2, §19.1 (vận hành); PRD NFR-04. **Bước sau:** [quy trình chấm ẩn cấu hình](rating-workflow.v1.md).

## 1. Vai trò

[`research/evaluation/run_ablation.py`](../../../research/evaluation/run_ablation.py) cho cùng một bộ tình huống chạy qua từng cấu hình của plan §18.1, rồi ghi:

- câu mỗi cấu hình gửi học sinh, ở dạng `SystemOutput` mà `build_rating_packet.py` đọc được;
- quyết định, các lần sinh câu, latency, token và chi phí của từng lượt, để đo vận hành (RQ5).

Nó không chấm chất lượng câu. Việc đó do người chấm làm theo rubric.

## 2. Một lượt chạy thế nào

Mỗi cặp (tình huống, cấu hình) chạy **một lượt qua đúng các node LangGraph của hệ thống**, không dựng lại chuỗi xử lý riêng cho thí nghiệm:

```text
state của tình huống (đã chấm bài, đã ghi observation)
   │  nạp vào checkpoint như thể node observe vừa chạy xong
   ▼
readiness → context → decide → generate → verify → commit
```

- State của tình huống là state sau khi bài làm đã được chấm, nên graph chạy tiếp từ sau node `observe`. Các node trước đó (extract, analyze, observe) không chạy: mọi cấu hình dùng cùng kết quả chấm (plan §18.2: giữ cùng analyzer).
- Rule-policy cũng chạy trong graph này, như plan §18.1 yêu cầu.
- Mọi cấu hình dùng cùng generator, verifier, policy gate, template dự phòng và cùng số lần sinh lại.
- Socratic LLM baseline là ngoại lệ duy nhất: không có policy nên không đi qua graph (§3.1).
- Các cấu hình chạy xen kẽ trong từng tình huống, để thay đổi của API theo thời gian không dồn vào một cấu hình.

## 3. Mỗi cấu hình khác Full ở đâu

| Cấu hình | Phần bị thay | Làm ở đâu |
|---|---|---|
| `full` | Không | Context của tình huống giữ nguyên |
| `no_bkt` | Policy không thấy `p_mastery`; `mastery_view = none`; readiness bỏ điều kiện ngưỡng, chỉ dùng evidence log | `graph.project_state`, `rule_policy.compute_readiness` (code hệ thống) |
| `heuristic` | Policy không thấy `p_mastery`; ước lượng là tỷ lệ đúng của tối đa 5 observation độc lập gần nhất | Như trên |
| `no_kg` | Context không có cạnh prerequisite, không có concept kế tiếp, `kg_enabled = false`. Nội dung của skill mà RAG chỉ biết tới nhờ cạnh prerequisite cũng bị bỏ | `run_ablation.project_context`, cùng quy tắc với `stubs.StubTools` (`stubs.retrieval_skills`) |
| `no_rag` | Context không có nội dung truy xuất, `rag_enabled = false` | `run_ablation.project_context` |
| `rule_policy` | Luật thay Agent LLM; không gọi model để quyết định | `decide.RulePolicyProposer` |

| `socratic_llm` | Không có analyzer, student model, KG, RAG, policy, gate hay problem bank: một LLM được prompt Socratic, chỉ nhận đề và cửa sổ hội thoại | [`socratic_baseline.py`](../../../research/evaluation/socratic_baseline.py), không qua graph |

### 3.1. Socratic LLM baseline

Plan §18.1: "LLM được prompt Socratic, nhận đề và cùng cửa sổ hội thoại; không có student model dài hạn/KG/RAG", và chỉ là tham chiếu cấp hệ thống, không dùng riêng để kết luận thành phần nào gây cải thiện.

**Model nhận:** đề bài, việc học sinh làm ở lượt này (`submit`, `request_hint`, `message`, `pause`, `resume`), bài làm, lời nhắn và các câu gia sư vừa gửi (tối đa 3 câu, cùng cửa sổ với generator của hệ thống). Lô ablation chạy một lượt từ state của tình huống, nên không cấu hình nào có câu gia sư trước đó.

**Model không nhận:** kết quả chấm bài, bước sai, họ lỗi, giả thuyết lỗi, mức gợi ý, mastery, lịch sử hỗ trợ, cạnh KG, nội dung truy xuất, mã bài hay đáp án. Baseline không giao bài mới. Test kiểm tra phần này trên chính chuỗi gửi cho model.

**Giữ giống các cấu hình khác (plan §18.2):**

- Cùng client: cùng model, temperature, giới hạn token đầu ra và timeout.
- Cùng policy về tiết lộ. Câu phải qua các kiểm tra chống lộ đáp án và lời giải của verifier: `answer_leak`, `math_unverified`, `unsourced_equation`, `unsourced_expression`, và `hint_level_exceeded` khi câu kể ra quá một thao tác giải mới (chuỗi "nhân vào ngoặc, cộng hai vế rồi chia" là dàn bài lời giải ở mọi mức hint). Đây là `ResponseVerifier.solution_checks`, phần mà `check_generated` của hệ thống cũng gọi. Không đạt thì sinh lại một lần kèm lý do, với cùng lời nhắc như generator, trừ lời nhắc cho `hint_level_exceeded` được viết lại vì baseline không có mức hint. Vẫn không đạt thì gửi câu hệ thống cố định, vì baseline không có template theo intent. Không có đáp án để kiểm tra thì không gọi model.
- Verifier đọc kết quả chấm chỉ để biết học sinh đã tự giải đúng chưa: xác nhận đáp án học sinh tự tìm ra không bị tính là tiết lộ. Kết quả chấm không được gửi cho model.
- Verifier lỗi sau khi model đã trả lời thì dòng lỗi vẫn giữ câu model viết (chưa được chấp nhận) và usage của nó, như lượt lỗi qua graph.

**Kiểm tra không áp dụng:** phần theo mức hint (ở mức 0–1 chỉ được hỏi, không bảo làm thao tác mới), action là câu hỏi và nội dung được trích, vì cả ba cần quyết định của policy. Bốn kiểm tra lời văn không cần quyết định (khẳng định bài đúng khi chưa xác minh, hỏi dồn, quá dài, lặp nguyên văn) không chặn câu của baseline, vì chúng thuộc cách hệ thống viết câu chứ không thuộc policy về tiết lộ. Chúng được đếm ở `unenforced_checks`, để thấy câu baseline đã gửi mắc những lỗi mà hệ thống chặn. Người chấm vẫn chấm mọi chiều của rubric, kể cả "Đúng toán" khi baseline khen một bài làm sai.

Phiên bản prompt: `socratic-baseline-prompt-0.5.0`, ghi ở `summary.json` (`versions.socratic_baseline_prompt`).

Test kiểm tra phần dữ liệu Agent thật sự nhận: ở No-KG không còn mã cạnh nào trong prompt; ở No-BKT và Heuristic mọi `p_mastery` là rỗng nhưng số observation vẫn còn.

## 4. Đầu ra

Ghi vào thư mục `--out` (đặt trong `data/`, đã ignore). Script không ghi đè thư mục đã có file.

| File | Nội dung |
|---|---|
| `outputs.jsonl` | Một `SystemOutput` cho mỗi (tình huống, cấu hình), lấy từ **lần chạy thứ nhất**. Đưa thẳng vào `build_rating_packet.py --outputs` |
| `runs.jsonl` | Mọi lượt chạy, kể cả các lần lặp và lượt lỗi: `PedagogicalDecision`, các lần sinh câu, latency, usage. Ghi ngay sau từng lượt, nên lô dừng giữa chừng vẫn giữ phần đã chạy |
| `summary.json` | Tổng hợp theo cấu hình, kèm phiên bản của workflow, policy, prompt, verifier, template và tên model |

Tổng hợp theo cấu hình:

- Số lượt có action thuộc tập chấp nhận được / bị cấm của tình huống; số đề xuất bị gate từ chối; số lượt phải fallback, theo lý do.
- Nguồn của câu gửi đi (LLM, template dự phòng, câu hệ thống), số lượt phải sinh lại, lỗi verifier tìm thấy ở câu của LLM.
- So sánh quyết định ở **hai mức**, vì hai lượt cùng action vẫn có thể giao hai bài khác nhau:
  - `action`: chỉ so action và intent (chiến lược).
  - `decision`: so thêm `target_skill_id`, `hint_level`, `problem_id`, `content_ids`, `edge_ids` (toàn bộ phần học sinh nhận được). Không so `reason` và `evidence`, vì đó là lời giải thích.
  - Mỗi mức có `differs_from_full` (các tình huống chọn khác Full ở lần chạy thứ nhất) và `unstable` (các tình huống mà những lần lặp `--repeat` không chọn giống nhau, plan §18.2). `differs_from_full` là kiểm tra đầu tiên cho rủi ro "có KG/RAG nhưng không ảnh hưởng quyết định" (plan §21).
- Latency cả lượt và riêng bước quyết định (trung vị, p95); token và chi phí của Agent và của generator, tách riêng.
- `socratic_llm` không có quyết định: các chỉ số về action, gate, fallback, `differs_from_full` và `unstable` để trống (`null`, bảng in `-`), không ghi 0. Các chỉ số về câu, latency, token và chi phí vẫn có; usage của baseline nằm ở phần `generation`.
- `model_calls`: số lần gọi model đếm ngay tại client. `model_calls_without_usage`: số lần gọi không ghi được usage. `cost_usd_per_turn` để trống khi có lần gọi không biết giá hoặc không ghi được usage, để không báo số thấp hơn chi phí thật.

### 4.1. Lượt lỗi

Một node lỗi không dừng cả lô. Lượt đó vẫn có dòng trong `runs.jsonl`, lấy từ checkpoint những gì các node trước node lỗi đã ghi: quyết định, các lần sinh câu (kể cả câu model đã viết) và usage của chúng. Usage của lượt lỗi được cộng vào tổng hợp; các chỉ số về quyết định và câu chỉ tính trên lượt hoàn tất. Lượt lỗi không có dòng trong `outputs.jsonl`, và script trả mã lỗi 1.

Nếu chính node gọi model bị lỗi sau khi model đã trả lời, usage của lần gọi đó không kịp vào checkpoint. Lần gọi vẫn được đếm ở `model_calls` và hiện ở `model_calls_without_usage`.

## 5. Chế độ chạy

| Chế độ | Agent | Generator | Dùng để |
|---|---|---|---|
| `--llm fake` (mặc định) | LLM giả trả đúng đề xuất của Rule-policy | LLM giả trả câu template; baseline nhận một câu hỏi chung cố định | Kiểm tra đường chạy, định dạng file, cách chiếu cấu hình. Không gọi API |
| `--llm openai --yes` | Model thật | Model thật | Lấy câu thật để chấm. **Tốn phí** |

Số lần gọi model tối đa = số tình huống × số lần lặp × (số cấu hình có Agent + số cấu hình × 2). Rule-policy và baseline không gọi Agent. Với 16 tình huống, 7 cấu hình, một lần chạy: 16 × (5 + 7 × 2) = **304 lần**. Script in con số này và dừng nếu vượt `--max-calls` (mặc định 50) hoặc thiếu `--yes`.

### 5.1. Lượt chạy với model thật trên bộ dev

Một lần chạy đủ 16 tình huống dev × 6 cấu hình, không lặp: `gpt-4o-mini`, `agent-prompt-0.4.0`, `response-prompt-0.2.0`, `gate-0.4.0`, `response-verifier-0.3.0`. 96 lượt, 201 lần gọi model, tổng chi phí tính từ usage trong log là **0,06545565 USD (≈ 0,06546 USD)**, không có lượt lỗi, mọi lần gọi đều ghi được usage. Chi phí này chỉ thuộc lô `dev-02`, chưa gồm lô chạy thử và lô bị ngắt. Lô được chạy thành bốn phần liên tiếp theo tình huống rồi gộp lại; file ở `data/ablation/dev-02` (không commit). Trước đó có một lượt chạy thử 2 tình huống × 3 cấu hình (`data/ablation/dev-thu`). Lô `data/ablation/dev-01` bị ngắt sau 13 lượt đã ghi log, chỉ có `runs.jsonl`; không dùng lô này để tạo phiếu chấm.

**Đây là số của bộ dev, chạy một lần, dùng để tìm lỗi của hệ thống; không phải kết quả RQ.** Tập action chấp nhận được do chính người viết Rule-policy soạn và chưa có người gán nhãn thứ hai, nên 16/16 của Rule-policy là hệ quả của cách soạn nhãn, không phải bằng chứng luật tốt hơn Agent.

| Cấu hình | Action cuối chấp nhận được | Trong đó do Agent tự đề xuất | Đề xuất bị gate từ chối | Đầu ra Agent sai schema | Lượt gửi câu template | Latency cả lượt (trung vị; p95) | Chi phí mỗi lượt |
|---|---:|---:|---:|---:|---:|---|---:|
| `full` | 10/16 | 4 | 5 | 1 | 1 | 4,2 s; 6,9 s | 0,00082 USD |
| `no_bkt` | 9/16 | 4 | 4 | 1 | 4 | 4,4 s; 6,5 s | 0,00085 USD |
| `heuristic` | 13/16 | 7 | 5 | 1 | 2 | 4,8 s; 6,3 s | 0,00079 USD |
| `no_kg` | 14/16 | 6 | 3 | 5 | 1 | 3,8 s; 6,4 s | 0,00066 USD |
| `no_rag` | 9/16 | 4 | 5 | 1 | 6 | 4,8 s; 7,6 s | 0,00077 USD |
| `rule_policy` | 16/16 | không gọi Agent | 0 | không gọi Agent | 1 | 1,9 s; 2,8 s | 0,00020 USD |

Không cấu hình nào chọn action thuộc tập bị cấm.

Quan sát:

1. **Phần lớn action chấp nhận được của các cấu hình có Agent đến từ luật fallback, không phải từ Agent.** Ở Full, Agent tự đề xuất được 4 action chấp nhận được; 6 lượt còn lại là fallback sau khi gate từ chối hoặc đầu ra sai schema. Cột "action chấp nhận được" vì thế đo cả hệ thống (Agent + gate + fallback), không đo riêng Agent.
2. **Agent chọn `diagnose` / `probe_prerequisite` quá thường xuyên.** Trong 16 lượt, Full đề xuất nó 5 lần, No-BKT 7, No-RAG 6. Gate cho qua cả khi không hợp tình huống: học sinh vừa làm đúng sau hỗ trợ (`SC-10`), lỗi tính toán với lịch sử tốt (`SC-04`), đã có giả thuyết lỗi được hỗ trợ trên chính skill đó (`SC-08`). Đã sửa ở `agent-prompt-0.5.0` và `gate-0.5.0` (luật G21, [llm-agent §6.4](../agent/llm-agent.v1.md)); chưa chạy lại với model thật.
3. **Gate chặn được các đề xuất sai dữ liệu:** mã cạnh không có trong context ở No-KG (`E02-A02`, `E02-P001`, `E02`), cạnh không nối tới skill đích (G05, 5 lần), nội dung vượt mức hint (G04, 16 lần), backtrack khi vừa làm đúng (G08, 4 lần).
4. **Đầu ra Agent sai schema ở 9/80 lần gọi**, dồn vào No-KG (5) và `SC-09` (4 cấu hình). Decision log không giữ đầu ra thô của Agent nên chưa biết sai ở đâu.
5. **Generator hỏi hai câu trong một lượt.** `too_many_questions` chiếm 35/41 lỗi verifier tìm thấy. Lượt phải gửi câu template chỉ có ở `diagnose`: 15/29 lượt `probe_prerequisite` và `elicit_reasoning`; các action khác không lượt nào phải dùng template. Sinh lại sửa được 10/25 lượt có lỗi ở lần sinh đầu. Đã sửa lời dặn và lý do sinh lại ở `response-prompt-0.3.0` ([response-generation §7.1](../generation/response-generation.v1.md)); chưa chạy lại với model thật.
6. **Câu template của `probe_prerequisite` không nêu tên skill** ("em nhắc lại quy tắc nền của dạng bài này giúp mình nhé"), nên các lượt ở mục 5 gửi một câu hỏi chung chung. Đã sửa ở `templates-0.2.0`: câu template và model nhận tên chủ đề của skill từ registry.
7. **`differs_from_full` chưa đọc được như ảnh hưởng của KG/RAG/BKT.** No-KG khác Full ở 10/16 tình huống, nhưng 8 lượt No-KG là fallback, và chưa có lần lặp nào để tách khỏi dao động của chính model. Cần `--repeat` trước khi dùng số này.
8. **Latency:** lượt chậm nhất 9,0 s; lần gọi Agent chậm nhất 6,8 s với timeout 8 s. Prompt của Agent khoảng 4.300 token đầu vào ở Full, 3.400 ở No-KG; generator khoảng 1.000.

### 5.2. Chạy lại bản đã sửa, lặp hai lần

[`run_dev_repeat.py`](../../../research/evaluation/run_dev_repeat.py) điều phối cùng `run_ablation.py`
trong các tiến trình riêng, mỗi phần bốn tình huống và hai lần lặp. Với bộ dev hiện tại và 7 cấu hình,
tổng cộng 224 lượt, tối đa 608 lần gọi (trước khi có baseline: 192 lượt, 544 lần gọi). Script lưu dấu SHA-256 của mã nguồn và dữ liệu,
cấu hình model cùng phiên bản các thành phần trong `manifest.json`. Cấu hình môi trường được
giữ cố định cho các tiến trình con. Script kiểm tra DNS trước khi tạo lô gọi model thật.

Sau mỗi phần, script dừng nếu phần đó không chạy hết hoặc ghi nhận lỗi kết nối/xác thực/quyền API.
Một lượt lỗi ở một node không làm dừng lô: lượt đó vẫn nằm trong kết quả, được báo trong bản gộp và
làm script trả mã 1. Log và dữ liệu phần đã chạy được giữ lại.

Lô bị ngắt thì chạy lại cùng lệnh với `--resume`. Phần đã xong được dùng lại, không gọi model lần
hai; phần dở được chạy lại vào thư mục mới (`part-3-retry1`), thư mục dở vẫn giữ nguyên. `--resume`
từ chối khi mã nguồn, bộ tình huống hoặc cấu hình model đã khác lúc lô bắt đầu, vì hai nửa khi đó
không so được với nhau. Khi gộp, script kiểm tra đủ mọi cặp
`scenario/configuration/attempt`, phiên bản khớp và mã nguồn không đổi. Các file gộp gồm
`runs.jsonl`, `outputs.jsonl`, `summary.json` và `diagnostics.json`. Phiếu chấm lấy câu ở lần
lặp thứ nhất, còn độ ổn định dùng cả hai lần như script gốc.

`diagnostics.json` đếm riêng đề xuất `probe_prerequisite` trước gate, đề xuất probe bị từ chối,
probe cuối cùng, lỗi hai câu ở lần sinh đầu, lỗi được sửa thành công ở lần sinh lại và lỗi
dẫn tới template. Tổng số đề xuất parse được và số câu sinh đầu đọc được là mẫu số đi kèm.
Lỗi API được đếm riêng. Độ ổn định ở hai mức action/decision nằm trong `summary.json`.

**Trạng thái chạy thật của bản mới**. Môi trường thực thi lỗi DNS tới `api.openai.com`.
Lô `data/ablation/dev-03/part-1` đã ghi 48 lượt nhưng cả 88 lần gọi đều lỗi
`APIConnectionError`, không có usage do provider trả về. Các lượt đều gửi template dự phòng.
Lô đã dừng, được đánh dấu không hợp lệ trong `data/ablation/dev-03/status.json`.
Không dùng lô này để đánh giá model hoặc tạo phiếu chấm. Chưa xác định được token/chi phí
của các lần gọi lỗi. Lệnh điều phối mới đã kiểm tra lỗi DNS trước khi gọi model.

Kiểm tra offline qua đủ 192 lượt (6 cấu hình, trước khi có baseline) đã chạy ở `data/ablation/dev-repeat-offline-check`.
Số liệu từ client giả chỉ dùng kiểm tra điều phối, ghép dữ liệu và định dạng báo cáo. Lô chạy thật của bản mới là `dev-04` (§5.3).

### 5.3. Lô `dev-04`: bản đã sửa, 7 cấu hình, lặp hai lần

16 tình huống dev × 7 cấu hình × 2 lần lặp = 224 lượt: `gpt-4o-mini`, `agent-prompt-0.5.0`, `gate-0.5.0`, `rule-policy-0.5.0`, `response-prompt-0.3.0`, `response-verifier-0.4.0`, `templates-0.2.0`, `socratic-baseline-prompt-0.5.0`. 423 lần gọi model trong bản gộp, không lượt nào lỗi, không lỗi API, mọi lần gọi đều ghi được usage. Chi phí từ usage của bản gộp **0,152 USD**. Tiến trình đầu bị dừng khi máy thiếu bộ nhớ giữa phần 3: 63 lần gọi của phần dở (0,021 USD) nằm ở `part-3/`, không vào bản gộp; phần 3 được chạy lại ở `part-3-retry1/` bằng `--resume`. File ở `data/ablation/dev-04` (không commit).

**Vẫn là số của bộ dev, dùng để tìm lỗi; không phải kết quả RQ.** Tập action chấp nhận được của 16 tình huống được soạn cùng Rule-policy, nên 32/32 của Rule-policy không chứng minh luật tốt hơn Agent.

| Cấu hình | Action cuối chấp nhận được | Trong đó do Agent tự đề xuất | Đề xuất bị gate từ chối | Agent lỗi/sai schema | Lượt gửi câu template | Latency cả lượt (trung vị; p95) | Chi phí mỗi lượt |
|---|---:|---:|---:|---:|---:|---|---:|
| `full` | 26/32 | 14 | 12 | 0 | 5 | 4,9 s; 10,6 s | 0,00096 USD |
| `no_bkt` | 20/32 | 11 | 9 | 0 | 7 | 4,5 s; 6,8 s | 0,00090 USD |
| `heuristic` | 20/32 | 11 | 9 | 0 | 6 | 4,3 s; 6,9 s | 0,00091 USD |
| `no_kg` | 23/32 | 13 | 10 | 0 | 4 | 4,4 s; 6,5 s | 0,00076 USD |
| `no_rag` | 22/32 | 12 | 12 | 0 | 2 | 3,9 s; 5,7 s | 0,00084 USD |
| `rule_policy` | 32/32 | không gọi Agent | 0 | không gọi Agent | 1 | 1,8 s; 2,8 s | 0,00022 USD |
| `socratic_llm` | không có quyết định | – | – | – | 0 | 1,6 s; 3,0 s | 0,00017 USD |

Chỉ một lượt chọn action thuộc tập bị cấm (`no_kg`).

Quan sát:

1. **Đầu ra Agent không còn sai schema** (0/160 lần gọi, trước đó 9/80), và tỷ lệ action chấp nhận được do Agent tự đề xuất ở Full tăng từ 4/16 lên 14/32. Gate vẫn từ chối 9–12/32 đề xuất ở mỗi cấu hình có Agent, chủ yếu vì nội dung vượt mức hint (G04, 7–12 lần) và cạnh KG không nối tới skill đích hoặc không có trong context (G05).
2. **Agent hỏi chẩn đoán lặp lại khi đã đủ bằng chứng.** Ở `SC-02` (giả thuyết lỗi đã được hỗ trợ), `SC-03` (vừa hỏi chẩn đoán, vẫn sai cùng lỗi) và `SC-07` (xin thêm gợi ý ở mức 2), Full chọn `diagnose` / `distinguish_hypothesis` ở cả hai lần lặp, và các cấu hình có Agent khác cũng vậy. Gate cho qua vì không có luật cấm hỏi chẩn đoán lặp lại. Đây là lỗi lớn nhất còn lại của Agent trên bộ này; bộ dev pilot có các ca cùng loại (DP-06, DP-17) với `diagnose` nằm trong tập bị cấm.
3. **Probe prerequisite đã giảm:** Full đề xuất 2 lần trong 32 lượt (trước đó 5/16).
4. **Generator vẫn hỏi hai câu ở lần sinh đầu** 2–7/32 lượt mỗi cấu hình; ở Full, sinh lại sửa được 3 lượt, 5 lượt phải gửi template.
5. **Baseline Socratic LLM:** 32/32 câu do model viết được gửi, 2 lượt phải sinh lại vì vi phạm kiểm tra chống lộ lời giải, không lượt nào phải gửi câu hệ thống. Trong câu đã gửi, 6 lượt khen bài là đúng khi bài chưa được xác minh đúng và 1 lượt hỏi dồn (`unenforced_checks`). Baseline nhanh và rẻ nhất vì chỉ gọi model một lần mỗi lượt.
6. **Độ ổn định giữa hai lần lặp:** Full khác nhau ở `SC-05`, `SC-06` về quyết định đầy đủ; No-BKT và No-KG không ổn định ở 4–5 tình huống. Hai lần lặp chưa đủ để tách ảnh hưởng của BKT/KG/RAG khỏi dao động của model.
7. **Latency:** p95 của Full là 10,6 s, cao nhất trong các cấu hình; lần gọi Agent có p95 4,9 s với timeout 8 s.
8. Lô này chạy trên 16 tình huống cũ, nên **chưa cho biết Agent xử lý ca kiểu DP-33 thế nào**; muốn biết phải chạy trên bộ dev pilot (`--scenario-set`).
9. **Ngữ cảnh của `SC-04` và `SC-15` trong lô này bị mâu thuẫn.** Hai tình huống chỉ sửa kết quả chấm (lỗi tính ở bước 3; lỗi biến đổi ở bước 2) mà giữ bài làm mặc định của fixture (`2x - 3 = 10`, sai phân phối ở bước 1). Mọi cấu hình đều nhận cùng ngữ cảnh mâu thuẫn đó. Fixture đã được sửa sau lô này: `SC-04` thành `2x - 6 = 10 → 2x = 16 → x = 6` (chia sai ở bước 3); `SC-15` thành `x - 3 = 5 → x = 2` (chia hai vế cho 2 trước, sai ở bước 2), để học sinh chưa dùng tới tính phân phối và việc hỏi kiểm tra skill nền đó vẫn nhất quán với DP-33. Kết quả của hai tình huống này trong `dev-04` không so được với lần chạy sau và không đưa vào phiếu chấm.

## 6. Giới hạn

| Giới hạn | Ảnh hưởng | Hướng xử lý |
|---|---|---|
| Với model thật mới chạy một lần, không lặp (§5.1) | Chưa tách được ảnh hưởng của cấu hình khỏi dao động của model; latency/chi phí là của một lô 96 lượt | Chạy `--repeat` sau khi sửa các lỗi ở §5.1; cần người có key đồng ý |
| Decision log không giữ đầu ra thô của Agent khi sai schema | Không chẩn đoán được 9 lần sai schema ở §5.1 | Ghi lại đầu ra thô hoặc thông báo lỗi validate |
| Chỉ có bộ tình huống dev (16 tình huống, một bài toán chính) | Không dùng làm kết quả RQ | Bộ tình huống thích ứng dev/test theo plan §11.5, §12 |
| `SC-12` ghi tay `ready_to_advance = true`, nhưng bằng chứng của skill không đủ điều kiện | Graph tính lại readiness nên mọi cấu hình đều thấy "chưa sẵn sàng"; tình huống này chưa kiểm tra được nhánh chuyển concept. Script liệt kê các tình huống như vậy ở `readiness_differs_from_fixture` | Soạn lại bằng chứng của `SC-12` khi mở rộng bộ tình huống (plan §18.2: state lấy từ BKT phải tái lập từ lịch sử, không chỉnh tay) |
| Hồ sơ mastery của tình huống là giá trị soạn tay | Chỉ là test policy, chưa phải bằng chứng về hiệu quả của BKT (plan §18.2) | State tái lập từ lịch sử và bộ tham số của Member 1 |
| Ngưỡng của Heuristic chưa tune | Đang dùng cùng giá trị khởi đầu với BKT, trái plan §18.2 nếu giữ nguyên đến lúc chạy chính thức | Chọn ngưỡng trên dev theo cùng ngân sách |
| No-RAG bỏ toàn bộ nội dung, trong khi `scaffold` bắt buộc trích nội dung đã duyệt | Dưới No-RAG không còn chọn được `scaffold`: hợp đồng quyết định bắt buộc action này có nội dung trích, nên đề xuất đó bị loại và lượt rơi về fallback. Chênh lệch với Full vì thế gồm cả việc mất hẳn một action, không chỉ là câu kém bám nội dung | Ghi rõ khi phân tích RQ3; xem `differs_from_full` ở mức action để tách các tình huống bị ảnh hưởng |
| No-KG giữ nguyên state của tình huống | State có thể mang dấu vết của KG từ lượt trước (ví dụ `SC-11` đang ở bài ôn prerequisite) | Đúng với "cùng lịch sử trước lượt đánh giá" (plan §18.2); ghi rõ khi phân tích RQ2 |
| KG, RAG, problem bank trong context là dữ liệu soạn sẵn của tình huống | Chưa đo retrieval thật | Nối tool thật khi Member 2 có RAG và problem bank |
| Chỉ một lượt | Chưa có đánh giá nhiều lượt (plan §19.1) | Làm sau khi có quỹ đạo nhiều lượt |
| Baseline chưa chạy với model thật | Chưa biết baseline lộ đáp án bao nhiêu lần trước verifier, chất lượng câu và chi phí | Chạy cùng lô lặp hai lần ở §5.2; cần người có key đồng ý |
| Baseline chỉ thấy lượt hiện tại khi chạy một lượt | Ở tình huống đã có nhiều lượt hỗ trợ (`SC-07`, `SC-08`, `SC-14`), hệ thống biết qua state còn baseline thì không. Đúng định nghĩa "không có student model", nhưng bất lợi hơn một cuộc chat thật, nơi model đọc được câu mình đã viết | Đánh giá nhiều lượt (plan §19.1) cho baseline đọc đúng các câu nó đã gửi; ghi rõ khi phân tích |
| Lời dặn của baseline do Member 3 soạn và tự rà (bản 0.3.0–0.5.0 thêm: chỉ xác nhận ngắn khi mọi bước và đáp án đều đúng, bước sai thì chỉ bước sai đầu tiên kể cả khi đáp án đúng, chỉ có đáp án đúng thì xác nhận kết quả nhưng không khẳng định cách giải, hỏi lại khi bài mơ hồ hay chỉ có đáp án, chỉ dựa vào ngữ cảnh được đưa, luôn tiếp tục bài hiện tại); chưa có người ngoài review | Baseline yếu do prompt kém sẽ làm hệ thống trông tốt hơn thật | Một thành viên khác trong nhóm review prompt trước khi khóa test; giữ cùng các luật tiết lộ với prompt của generator |

## 7. Lệnh

```powershell
# LLM giả, không gọi API
.\.venv\Scripts\python.exe research/evaluation/run_ablation.py --out data/ablation/dev-fake

# Một phần cấu hình và tình huống, lặp 3 lần để xem độ ổn định
.\.venv\Scripts\python.exe research/evaluation/run_ablation.py --configs full no_kg rule_policy --scenarios SC-08 SC-11 --repeat 3

# GỌI API THẬT cho lô mới (tốn phí): cần LLM_ENABLED=true và OPENAI_API_KEY trong .env
# Dùng thư mục mới; nếu dev-03 đã có dữ liệu thì chọn tên khác.
.\.venv\Scripts\python.exe research/evaluation/run_ablation.py --llm openai --yes --max-calls 304 --out data/ablation/dev-03

# Chạy lại hai lần, chia phần trong tiến trình riêng, tối đa 608 lần gọi.
# Chạy từ terminal có kết nối API; thư mục dev-04 phải mới.
.\.venv\Scripts\python.exe research/evaluation/run_dev_repeat.py --llm openai --yes --out data/ablation/dev-04
# Lô bị ngắt: chạy tiếp, dùng lại các phần đã xong.
.\.venv\Scripts\python.exe research/evaluation/run_dev_repeat.py --llm openai --yes --out data/ablation/dev-04 --resume

# Tạo phiếu từ lô dev-02 đã hoàn tất; không gọi API, không cần chạy lô mới ở trên.
.\.venv\Scripts\python.exe research/evaluation/build_rating_packet.py --outputs data/ablation/dev-02/outputs.jsonl --raters r1 r2 `
    --compare full:no_bkt full:heuristic full:no_kg full:no_rag full:rule_policy --out data/rating/dev-02
# Lô có baseline: thêm cặp full:socratic_llm vào --compare.

# Lô chạy trên bộ tình huống đã replay (run_ablation.py --scenario-set): đưa đúng file đó. Script so dấu
# vân tay từng tình huống (run.scenario_fingerprints trong summary.json của lô) với tình huống hiện tại và
# dừng nếu khác: bài làm, ngữ cảnh hay đề đã đổi, sai --scenario-set, hoặc lô không có summary.json.
.\.venv\Scripts\python.exe research/evaluation/build_rating_packet.py --outputs data/ablation/ap-01/outputs.jsonl `
    --scenario-set data/scenarios/approved-v1/dev.json --raters r1 r2 --compare full:no_kg --out data/rating/ap-01

.\.venv\Scripts\python.exe -m pytest -q tests/test_ablation.py tests/test_socratic_baseline.py
```
