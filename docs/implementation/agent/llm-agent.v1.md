# Agent LLM, bản v1

**Trạng thái:** code và test xong; với model thật mới có 1 lần gọi kiểm tra key (§6.1) và một lần chạy đủ 16 tình huống dev × 6 cấu hình ([ablation-runner §5.1](../evaluation/ablation-runner.v1.md)), chưa lặp. Model: `gpt-4o-mini` (OpenAI). Mọi test dùng LLM giả, không gọi mạng.
**Liên quan:** [pedagogical-decision.v1.md](pedagogical-decision.v1.md) (hợp đồng, luật gate), [langgraph-skeleton.v1.md](langgraph-skeleton.v1.md) (luồng một lượt), plan §13 (fallback), §18 (RQ5, latency/cost).

## 1. Vai trò

Agent LLM thay Rule-policy ở **bước đề xuất** của node `decide`. Nó đọc state và kết quả tool của lượt, rồi trả về đúng một `DecisionProposal`. Các bước còn lại giữ nguyên:

```text
state + context ──→ LLMProposer ──→ policy gate ──(chấp nhận)──→ quyết định cuối
                        │                 └──(từ chối)──→ Rule-policy (fallback)
                        └──(lỗi, timeout, sai schema)───→ Rule-policy (fallback)
```

LLM không viết câu trả lời cho học sinh (đó là bước `generate`, xem [response-generation.v1.md](../generation/response-generation.v1.md)) và không ghi mastery. Đề xuất của LLM phải qua cùng policy gate với Rule-policy, nên một quyết định sai luật không bao giờ tới học sinh.

## 2. Thành phần

| File | Nội dung |
|---|---|
| `backend/app/llm/client.py` | `LLMSettings` (đọc env), `OpenAIResponsesClient` (Responses API, structured output strict), bảng giá `PRICES` và `cost_usd` |
| `backend/app/agent/llm_proposer.py` | Lời dặn `INSTRUCTIONS`, schema đầu ra `OUTPUT_SCHEMA`, `build_input`, `LLMProposer`, `build_proposer`, `decision_config` |
| `backend/app/llm/types.py` | `LLMUsage` dùng chung cho Agent và extraction |
| `backend/app/agent/decision.py` | Các trường `PedagogicalDecision.agent_usage` và `decision_latency_ms` |
| `backend/app/agent/decide.py` | `run_decision`: proposer → gate → fallback và đo thời gian cả chuỗi, dùng chung cho LangGraph và script; `RulePolicyProposer` |
| `backend/app/llm/fakes.py` | `FakeLLMClient` cho test và lần chạy thử |
| `backend/app/agent/fakes.py` | `ScriptedProposer` cho test Agent |
| `research/agent/scenarios.py` | Đọc bộ tình huống dev (dùng chung cho test và script; không thuộc luồng dạy thật) |
| `research/agent/compare_proposers.py` | So sánh Agent LLM với Rule-policy trên bộ tình huống dev |
| `research/llm_support.py` | Đọc `.env`, xin xác nhận trước khi gọi API thật, thống kê token/latency/chi phí (dùng chung với LLM extraction) |
| `tests/test_agent_llm.py` | 104 test, không gọi mạng |

Phiên bản ghi vào decision log: `prompt_version = agent-prompt-0.5.0`, `policy_version = llm-agent-0.1.0`, `model_id` theo cấu hình. Sửa lời dặn, định dạng input hay schema đầu ra thì phải tăng `PROMPT_VERSION`.

## 3. Dữ liệu gửi cho model

Mỗi lượt gửi một lần, gồm hai phần:

- **Lời dặn (cố định):** vai trò, bảng action sinh tự động từ `ACTION_SPECS` (kèm cách điền từng trường cho mỗi action, `field_rules`), 14 luật cứng tương ứng với luật gate, và phần sư phạm ghi lại bảng policy của plan §9 theo từng loại bằng chứng (vừa làm đúng, xin gợi ý hoặc không tiến triển, lỗi thao tác với lịch sử tốt, có giả thuyết lỗi, chưa rõ nguyên nhân, khi nào hỏi kiểm tra prerequisite, kẹt ở mức hint cao). Lời dặn viết bằng tiếng Anh; `reason` yêu cầu viết bằng tiếng Việt. Vì phần này cố định và dài hơn 1.024 token, provider tự cache, nên các lượt sau tính giá token đã cache.
- **Input (thay đổi theo lượt):** JSON gồm `state` (đã chiếu theo cấu hình ablation), `context` (đề bài đang làm, nội dung truy xuất, cạnh KG, concept kế tiếp, bài ứng viên) và `facts`.

`facts` là giá trị hệ thống tính sẵn **từ chính state đó**: danh sách bằng chứng được phép trích, mức hint tối đa, cờ kẹt, các concept trong nhánh, giả thuyết lỗi đang mở, bằng chứng thiếu skill nền, các skill nền đáng hỏi kiểm tra ở lượt này (`probe_candidates`), xếp loại mastery. Agent và Rule-policy vì vậy dùng **cùng thông tin**, đúng điều kiện so sánh của RQ5. Model chỉ không phải tự tính lại các giá trị này.

**Đề bài:** `context.current_problem_prompt` là đề bài công khai, đúng như học sinh thấy, do problem bank trả về. Không có đề bài thì model không hiểu được tin nhắn kiểu "em chưa hiểu" hay bài làm đang giải gì (bản đầu thiếu phần này, review 14/11 phát hiện).

**Không gửi:** `student_id`, `session_id`, `request_id`, ngân sách tool, đáp án và lời giải tham chiếu. Test `test_input_sends_problem_statement_but_no_identity_or_answer` kiểm tra: đề bài có mặt, còn đáp án của bài đang làm không xuất hiện ở phần do hệ thống gửi (bài làm của học sinh có thể chứa đáp án em tự viết). Tin nhắn của học sinh nằm trong `state` như dữ liệu; lời dặn nói rõ không làm theo yêu cầu nào trong đó.

## 4. Gọi model và xử lý lỗi

| Thiết lập | Giá trị | Lý do |
|---|---|---|
| API | Responses API, `text.format` = JSON Schema `strict` | Đầu ra luôn đúng cấu trúc; Pydantic kiểm tra tiếp các ràng buộc chi tiết (S01–S09) |
| `temperature` | 0 | Giảm dao động giữa các lần chạy |
| `max_output_tokens` | 400 | Một đề xuất chỉ cần khoảng 100 token |
| Timeout | `AGENT_LLM_TIMEOUT_SECONDS`, mặc định 8 giây | Lượt dạy không chờ lâu |
| Thử lại | Không (`max_retries = 0`) | Lỗi thì fallback ngay (plan §13) |
| `store` | `false` | Không lưu hội thoại phía provider |

| Kết quả gọi | `fallback_reason` | `agent_usage.error` |
|---|---|---|
| Đề xuất hợp lệ, gate chấp nhận | (không có) | (không có) |
| Đề xuất hợp lệ, gate từ chối | `gate_rejected` | (không có) |
| Quá thời gian | `agent_timeout` | `timeout` |
| Lỗi provider (mạng, xác thực, rate limit) | `agent_error` | tên lỗi, ví dụ `RateLimitError` |
| Model từ chối trả lời | `agent_error` | `refusal` |
| Đầu ra bị cắt (hết token) | `agent_schema_error` | `incomplete:max_output_tokens` |
| JSON hỏng hoặc sai hình dạng | `agent_schema_error` | `invalid_output` |

Mọi trường hợp đều có quyết định cuối hợp lệ từ Rule-policy, và decision log giữ lại lần gọi lỗi.

## 5. Đo token, latency và chi phí

Mỗi quyết định có `decision_latency_ms`: thời gian cả chuỗi proposer → gate → fallback, đo cho **mọi cấu hình**, kể cả Rule-policy, để so sánh được. Quyết định do Agent đề xuất có thêm `agent_usage` cho riêng lần gọi model:

| Trường | Ý nghĩa |
|---|---|
| `model_id` | Tên model provider trả về, có ngày snapshot (ví dụ `gpt-4o-mini-2024-07-18`) |
| `input_tokens`, `cached_input_tokens`, `output_tokens` | Theo `usage` của provider; **null** khi provider không trả `usage` |
| `latency_ms` | Thời gian riêng lần gọi model, tính cả mạng |
| `cost_usd`, `price_version` | Tính từ bảng giá trong `app/llm/client.py` |
| `error` | Lý do lỗi, nếu có |

Bảng giá `openai-list-2026-11-14` cho `gpt-4o-mini` (USD / 1M token): vào **0,15**, vào đã cache **0,075**, ra **0,60**. Đã đối chiếu với [trang giá chính thức của OpenAI](https://developers.openai.com/api/docs/pricing.md), mức Standard, ngày 14/11/2026. Đổi giá thì đổi cả `PRICE_VERSION`.

Khi lỗi trước lúc provider trả `usage` (timeout, lỗi mạng), số token và `cost_usd` để **null** chứ không phải 0, vì không biết lượt đó bị tính bao nhiêu token. Bản đầu ghi 0 nên kéo trung bình token xuống (review 14/11).

**Ước lượng (chưa đo thật):** input khoảng 3.600 token mỗi lượt theo cách đếm 4 ký tự/token của LLM giả; tiếng Việt có thể tốn nhiều token hơn. Một lượt chạy 16 tình huống khoảng 0,01 USD.

## 6. Chạy so sánh trên bộ tình huống dev

```powershell
# Chỉ Rule-policy, không gọi API
.\.venv\Scripts\python.exe research/agent/compare_proposers.py
# Đường Agent với LLM giả trả đúng đề xuất của Rule-policy: kiểm tra prompt, schema, gate, log; không gọi API
.\.venv\Scripts\python.exe research/agent/compare_proposers.py --agent fake
# GỌI API THẬT (tốn phí): cần LLM_ENABLED=true và OPENAI_API_KEY trong .env
.\.venv\Scripts\python.exe research/agent/compare_proposers.py --agent openai --yes --out data/agent_runs/dev-001.jsonl
```

Script chạy mỗi tình huống qua đúng chuỗi proposer → gate → fallback của hệ thống, in bảng từng tình huống và bảng tổng hợp:

| Chỉ số | Ý nghĩa |
|---|---|
| `gate_accepted` | Số đề xuất qua gate ngay |
| `fallbacks` | Số lần fallback, theo lý do |
| `final_acceptable` | Quyết định cuối thuộc `acceptable_actions` của tình huống |
| `proposed_forbidden` | Đề xuất thuộc `forbidden_actions` (gate có chặn hay không thì vẫn đếm) |
| `same_as_rule` | Trùng action và intent với Rule-policy (để biết Agent khác ở đâu, không phải thước đo đúng/sai) |
| `decision_ms` (trung vị, p95) | Cả chuỗi proposer → gate → fallback; có cho cả Rule-policy và Agent |
| `api_ms` (trung vị, p95) | Riêng lần gọi model, chỉ trên các lần có gọi (`llm_calls`) |
| `usage_known`, `usage_missing` | Số lần gọi có và không có `usage`; token trung bình chỉ tính trên `usage_known` |
| `cost_usd_known` (từ `cost_known_calls` / `llm_calls` lần) | Tổng chi phí của các lần biết chi phí; hai số khác nhau nghĩa là chi phí thật có thể cao hơn |

Với `--agent openai`, script in số lần gọi dự kiến trước khi chạy, dừng nếu thiếu `--yes`, và dừng nếu số lần gọi vượt `--max-calls` (mặc định 50). Có thể chạy một phần bằng `--scenarios SC-01 SC-08` và lặp bằng `--repeat 3` để xem độ ổn định.

### 6.1. Lần gọi thật đầu tiên (14/11/2026, kiểm tra key)

Một lần gọi trên SC-01 với `agent-prompt-0.1.0`: key dùng được, model trả `gpt-4o-mini-2024-07-18`, 3.960 token vào, 100 token ra, $0.00065, **6,9 giây**.

Model chọn đúng `diagnose / distinguish_hypothesis` như Rule-policy nhưng bị gate từ chối (G13, G17): điền bài đang làm vào `problem_id`, và trích bài chấm thay vì giả thuyết `HYP-001`. Hệ thống fallback đúng về Rule-policy.

Sửa ở `agent-prompt-0.2.0` (chưa chạy lại với model thật):
- Bảng action nói rõ trường nào phải null hoặc rỗng cho từng action. Test `test_field_rules_in_prompt_match_rule_policy` kiểm tra bảng này khớp với mọi đề xuất của Rule-policy.
- `facts.active_hypotheses` liệt kê giả thuyết đang mở; luật 13 ghi rõ dạng bằng chứng cần trích.

Latency 6,9 giây sát timeout 8 giây; cần xem lại khi có đủ số liệu.

### 6.2. Sửa sau review (14/11/2026), `agent-prompt-0.3.0`

- Gửi đề bài đang làm (`context.current_problem_prompt`).
- Số token chưa biết để null; báo cáo tách số lần thiếu `usage` và ghi rõ chi phí tính trên bao nhiêu lần gọi.
- Đo thời gian cả chuỗi cho mọi cấu hình (`decision_latency_ms`), tách khỏi latency API.
- Sửa dữ liệu tình huống: bài làm của SC-05, SC-10, SC-11, SC-12 trước đây là bài làm sai của fixture gốc, không khớp với kết quả chấm (SC-11 còn là bài của bài khác); xin gợi ý (SC-06, SC-07) không kèm bài làm. Test `test_scenario_messages_match_assessment` giữ cho bài làm khớp với kết quả chấm.

Chưa chạy lại với model thật.

### 6.3. Sửa sau review trước commit, `agent-prompt-0.4.0`

- Input có `latest_submission` (đúng bài làm đã chấm) tách khỏi `latest_student_message`; lời dặn nói rõ tin kết quả chấm khi lời nhắn nói khác.
- Luật 10 và `facts.stuck`: vừa làm đúng thì không còn kẹt (khớp G10 mới).
- Luật 12b: bài mới của `check_transfer`, `continue_practice`, `switch_problem`, `advance_difficulty` giữ nguyên skill và concept (khớp G20).

Chưa chạy lại với model thật.

### 6.4. Sửa sau lượt chạy model thật trên bộ dev, `agent-prompt-0.5.0`

Lượt chạy 16 tình huống × 6 cấu hình ([ablation-runner §5.1](../evaluation/ablation-runner.v1.md)) cho thấy Agent đề xuất `diagnose` / `probe_prerequisite` ở 10/16 tình huống (tính gộp năm cấu hình có Agent), trong khi Rule-policy chỉ dùng nó ở 1. Agent hỏi kiểm tra cả khi lỗi vừa chấm đã được quy cho chính skill đó, khi học sinh xin gợi ý, khi lỗi chỉ là lỗi tính toán, và khi học sinh vừa làm đúng. Lời dặn cũ chỉ có bốn câu về sư phạm, trong đó có "chưa rõ nguyên nhân thì chẩn đoán trước khi gợi ý".

- **Luật gate G21:** không `probe_prerequisite` khi học sinh vừa làm đúng. Luật 8 của lời dặn ghi điều này.
- **`facts.probe_candidates`:** các skill nền đáng hỏi kiểm tra ở lượt này, tính từ cùng state, mỗi skill kèm chuỗi cạnh phải trích (`edge_ids`).
  - Phạm vi: prerequisite trong hai tầng của concept đang học, đúng phạm vi G05 cho phép. `facts.prerequisite_evidence` vẫn chỉ tính cho prerequisite trực tiếp, vì backtrack mỗi bước lùi một tầng.
  - Danh sách rỗng khi không có bài làm sai vừa chấm, khi học sinh xin tạm dừng, hoặc khi đã chạm giới hạn hỗ trợ.
  - Skill có ước lượng thấp là ứng viên (plan §9: kiểm tra rồi mới backtrack).
  - Skill chưa có bằng chứng theo hướng nào (không yếu, không tốt) chỉ là ứng viên khi đã lên mức hint 3 mà vẫn sai (plan §10), giống `_unchecked_prerequisite` của Rule-policy. Skill có bằng chứng tốt thì không.
  - Skill đã bị quy lỗi, đã có giả thuyết đang mở hoặc đã hỏi trên bài này thì không.
  - Test: mọi ứng viên, khi đề xuất với đúng `edge_ids` của nó, đều qua gate (`test_every_probe_candidate_passes_the_gate`); skill mà Rule-policy hỏi kiểm tra luôn nằm trong danh sách (`test_rule_policy_probes_only_candidates`).
- **Phần sư phạm của lời dặn** ghi lại bảng policy của plan §9 theo từng loại bằng chứng, thay cho bốn câu chung. Ngưỡng "không tiến triển" và danh sách họ lỗi thao tác lấy từ cùng hằng số với Rule-policy.

Việc ghi rõ bảng policy làm Agent và Rule-policy gần nhau hơn: RQ5 khi đó so "LLM áp dụng policy đã ghi" với "luật cài sẵn policy đó", không phải LLM tự nghĩ policy. Chỉ có thêm luật gate G21; `probe_candidates` và các dòng của phần sư phạm là hướng dẫn trong prompt, gate không ép Agent chọn trong danh sách đó. Có nên ép hay không thì quyết định sau khi chạy lại với model thật.

Chưa chạy lại với model thật, nên chưa biết các sửa đổi này có giảm được số lần hỏi kiểm tra không.

**Lưu ý:** bộ tình huống là dữ liệu dev tự soạn (plan §11.5, §19.3). Kết quả dùng để sửa prompt, **không dùng làm kết quả RQ5**. RQ5 chạy trên bộ test riêng đã khóa ở tuần 7.

## 7. Giới hạn

| Giới hạn | Ảnh hưởng | Khi nào xử lý |
|---|---|---|
| Mới chạy model thật một lần trên bộ dev, với `agent-prompt-0.4.0` | Số liệu ở [ablation-runner §5.1](../evaluation/ablation-runner.v1.md) là của prompt cũ; chưa có số liệu cho `agent-prompt-0.5.0` | Chạy lại bộ dev có lặp khi được phép dùng API |
| Latency lần đầu 6,9 giây | Lượt dạy chậm, dễ chạm timeout | Đo trên 16 tình huống rồi chọn: tăng timeout, rút gọn input hoặc đổi model |
| Agent chưa tự chọn tool; context vẫn gọi KG/RAG/problem bank cố định | Chưa có quyết định "cần tra gì" | Sau khi có kết quả Agent trên dev |
| Mỗi lượt một lần gọi, không sinh lại khi bị gate từ chối | Bị từ chối là dùng Rule-policy ngay | Cân nhắc sau khi đo tỷ lệ bị từ chối |
| `LLM_MAX_CALLS_PER_SESSION` (của code nháp cũ) chưa áp cho Agent | Phiên dài gọi model mỗi lượt | Chốt ngân sách gọi model với nhóm |
| `reason` do model viết, chưa kiểm tra có khớp bằng chứng không | Lý do trong log có thể không chính xác | Khi làm rubric |

## 8. Lệnh

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_agent_llm.py -q
.\.venv\Scripts\python.exe research/agent/compare_proposers.py --agent fake
.\.venv\Scripts\python.exe scripts/exports/export_agent_contracts.py --check
```
