# Hợp đồng quyết định sư phạm của Agent, bản nháp v1

**Trạng thái:** nháp của Member 3, cần chốt với Member 1 (state, assessment) và Member 2 (RAG, UI).
**Căn cứ:** [plan](../../planning/project-plan.md) §8.6, §9, §10, §18; [PRD](../../product/prd.md) FR-10, FR-11, §6.4.

| File | Vai trò |
|---|---|
| [`backend/app/agent/decision.py`](../../../backend/app/agent/decision.py) | Pydantic: 9 action, intent, `DecisionProposal`, `PedagogicalDecision`, `StudentState` |
| [`contracts/agent/`](../../../contracts/agent/fixtures.v1.json) | JSON Schema xuất từ Pydantic và fixtures tình huống `2(x - 3) = 10` |
| [`tests/test_agent_decision.py`](../../../tests/test_agent_decision.py) | Kiểm tra bộ action, ràng buộc hình dạng và fixtures |
| [`research/agent/external_moves.py`](../../../research/agent/external_moves.py) | Thống kê nhãn Bridge/MathDial dùng trong tài liệu này |
| [`backend/app/agent/gate.py`](../../../backend/app/agent/gate.py) | Policy gate: các luật ở §6 |

Policy gate, Rule-policy và khung LangGraph dùng hợp đồng này được mô tả ở [langgraph-skeleton.v1.md](langgraph-skeleton.v1.md).

## 1. Bài học từ dữ liệu ngoài

Hai bộ dữ liệu được dùng để **kiểm tra thiết kế**, không để huấn luyện hay đánh giá. Cả hai đều bằng tiếng Anh, không thuộc chương trình Việt Nam.

**Bridge** (Wang et al., NAACL 2024). 700 đoạn dạy kèm thật, giáo viên chuyên gia gắn nhãn ba bước: loại lỗi → chiến lược → ý định. Học sinh là học sinh **lớp 1–5** ở Mỹ, chủ đề gồm cả hình học, nên chỉ dùng được ở mức chiến lược chung. Nhãn lỗi `diagnose` trong dữ liệu tương ứng với nhãn "not-sure" trong bài báo: giáo viên chưa chắc học sinh sai gì và sẽ thử chẩn đoán (§4.2.1).

| Loại lỗi (Bridge) | Chiến lược chuyên gia chọn nhiều nhất |
|---|---|
| `diagnose`: chưa rõ nguyên nhân (128) | `ask_question` 66, `provide_similar_problem` 22, `explain_concept` 18 |
| `guess`: đoán mò (239) | `explain_concept` 76, `ask_question` 49, `provide_strategy` 37 |
| `right-idea`: đúng hướng (129) | `explain_concept` 33, `ask_question` 27, `provide_hint` 23 |
| `careless`: cẩu thả (55) | `provide_correction` 16, `ask_question` 14 |
| `misinterpret`: hiểu sai đề (45) | `ask_question` 20, `simplify_question` 12 |

**MathDial** (Macina et al., EMNLP 2023 Findings). 2.861 hội thoại, 18.607 lượt giáo viên. Tỷ lệ các loại lượt: `focus` 36,6%, `generic` 23,9%, `probing` 22,9%, `telling` 16,6%. Có 397 hội thoại (13,9%) giáo viên tự báo phải lộ đáp án thì học sinh mới sửa được. Lưu ý: giáo viên là người thật, nhưng **học sinh do LLM đóng vai**. Học sinh mô phỏng có thể "cứng đầu" hơn học sinh thật, nên tỷ lệ `telling` chỉ là tham khảo, không phải mức chuẩn.

Kết luận áp vào thiết kế:

1. Khi chưa rõ nguyên nhân lỗi, chuyên gia **hỏi trước** rồi mới hỗ trợ. Điều này ủng hộ thứ tự ưu tiên clarify → diagnose → hỗ trợ của plan §9.
2. Chiến lược phụ thuộc loại lỗi: lỗi cẩu thả thì nhắc kiểm tra, hiểu sai đề thì làm rõ đề, đoán mò thì quay về khái niệm. Vì vậy `PedagogicalDecision` phải trỏ tới bằng chứng lỗi (`evidence`) chứ không chỉ ghi tên action.
3. Trong MathDial, giáo viên "nói thẳng" khoảng 1/6 số lượt (với học sinh mô phỏng). Nếu cả người dạy còn khó tránh, LLM càng khó. Vì vậy chống lộ đáp án phải là một **bước kiểm tra riêng** sau khi sinh phản hồi, không thể chỉ dựa vào prompt.
4. Bridge cho thấy chất lượng phản hồi của GPT-4 tăng khi được đưa quyết định của chuyên gia trước khi viết. Đây là căn cứ để **tách bước quyết định (Agent) khỏi bước viết câu (generator)**.

## 2. Bộ action chuẩn

Giữ đúng 9 action của PRD FR-10 và không thêm tên strategy mới. Mỗi action có một số **intent** (mục đích cụ thể). Mỗi intent chỉ thuộc một action và cho generator biết cần viết loại câu nào. "Tự sửa", "giải thích khái niệm", "đổi độ khó" là intent hoặc mức hỗ trợ của action, đúng như PRD yêu cầu.

| Action | Dùng khi | Intent | Mức hint | Bắt buộc có | Tính là hỗ trợ |
|---|---|---|---|---|---|
| `clarify` | Input mơ hồ, sai cú pháp, không chấm được, hiểu sai đề | `resolve_input`, `restate_task` | 0 | evidence | Không |
| `diagnose` | Nghi lỗi nhưng bằng chứng ít; chỉ có đáp án cuối ở bài nhiều skill; kiểm tra prerequisite | `elicit_reasoning`, `distinguish_hypothesis`, `probe_prerequisite` | 0 | skill, evidence (+ edge nếu `probe_prerequisite`) | Có |
| `minimal_hint` | Lỗi thao tác đơn lẻ, gần đúng, cần tự sửa | `prompt_self_check`, `locate_error`, `recall_rule` | 1–2 | skill, evidence | Có |
| `conceptual_question` | Misconception có bằng chứng | `target_misconception` | 0–2 | skill, evidence | Có |
| `backtrack` | Prerequisite có dấu hiệu yếu | `review_prerequisite` | 0–1 | skill, evidence, edge, problem (bài của concept nền) | Có |
| `scaffold` | Đã lên hint cao mà vẫn kẹt | `decompose_step`, `analogous_example`, `explain_concept` | 3–4 | skill, evidence, content | Có |
| `check_transfer` | Làm đúng sau hỗ trợ, cần bài độc lập | `independent_check` | 0 | skill, evidence, problem | Không |
| `next_problem` | Đủ bằng chứng sẵn sàng, quay lại sau backtrack, đổi bài khi kẹt quá giới hạn | `continue_practice`, `advance_difficulty`, `advance_concept`, `return_to_parent`, `switch_problem` | 0 | skill, evidence, problem | Không |
| `end_session` | Học sinh dừng, đạt mục tiêu, hết ngân sách, kẹt quá giới hạn, hết bài, lỗi hệ thống | `student_request`, `session_goal_met`, `budget_exhausted`, `stuck_limit`, `content_exhausted`, `system_fallback` | 0 | không có payload | Không |

Thang hint (plan §9) khớp với action như sau:

```text
0  câu hỏi gợi mở / chẩn đoán      → diagnose, conceptual_question, backtrack
1  nhắc kiến thức / tự kiểm tra     → minimal_hint, conceptual_question
2  gợi ý cụ thể hơn                 → minimal_hint, conceptual_question
3  chia nhỏ / minh họa bằng bài khác → scaffold (decompose_step, analogous_example)
4  giải thích khái niệm, ví dụ khác → scaffold (explain_concept, analogous_example)
```

`diagnose` được tính là hỗ trợ một cách **bảo thủ**, vì câu hỏi chẩn đoán đã ngầm báo bước nào có vấn đề. Member 1 cần xác nhận quy tắc này khi tính observation eligibility.

**Thứ tự ưu tiên** (plan §9): clarify → diagnose → hỗ trợ → check_transfer → next_problem. Riêng `end_session` với intent `student_request` hoặc `budget_exhausted` **luôn đứng trước tất cả**, vì học sinh xin dừng thì phải được dừng (plan §10). Xem hàm `priority()`.

## 3. Ánh xạ nhãn ngoài sang action

Ánh xạ này phụ thuộc ngữ cảnh. Bảng dưới đây ghi trường hợp chính và dùng làm gợi ý khi viết prompt, rubric và bộ tình huống.

| Bridge `z_what` | Action (intent) | Ghi chú |
|---|---|---|
| `ask_question` | `diagnose` (`elicit_reasoning`) hoặc `conceptual_question` | Hỏi vì sao chọn → diagnose; hỏi vào bản chất → conceptual |
| `explain_concept` | `scaffold` (`explain_concept`, mức 4) | Chỉ ở mức cao, phải dùng ví dụ khác bài đang làm |
| `provide_hint` | `minimal_hint` (`locate_error` / `recall_rule`) | |
| `provide_strategy` | `minimal_hint` (`prompt_self_check`) hoặc `scaffold` (`decompose_step`) | |
| `provide_correction` | `minimal_hint` (`locate_error`, mức 2) | Nếu đưa ra kết quả đúng của bài hiện tại thì **bị cấm** |
| `provide_similar_problem` | `check_transfer` sau khi làm đúng; `scaffold` (`analogous_example`) khi đang dạy | |
| `simplify_question` | `scaffold` (`decompose_step`) hoặc `clarify` (`restate_task`) | |
| `provide_example` | `scaffold` (`analogous_example`) | |
| `affirm_correct_answer`, `encourage_student` | Không phải action | Lời khen là một phần câu chữ đi kèm action |
| visual aid | Ngoài phạm vi | Hệ thống không có hình |

| MathDial | Action | Ghi chú |
|---|---|---|
| `probing` | `diagnose`, `conceptual_question` | |
| `focus` | `minimal_hint`, `conceptual_question`, `scaffold` (`decompose_step`) | |
| `telling` | Cấm với bài đang làm | Chỉ được dùng trong `scaffold` mức 4 trên **ví dụ khác** |
| `generic` | Không phải action | Chào hỏi, khen, câu chuyển tiếp |

## 4. `PedagogicalDecision`

Gồm hai tầng:

- **`DecisionProposal`**: đầu ra của Agent hoặc Rule-policy, trước policy gate. Gồm: `action`, `intent`, `target_skill_id`, `hint_level`, `evidence` (loại + ID), `content_ids`, `edge_ids`, `problem_id`, `reason` (≤ 300 ký tự). **Không có trường ghi mastery** và mọi trường lạ đều bị từ chối (PRD FR10-AC5).
- **`PedagogicalDecision`**: bản ghi trong decision log. Gồm các ID của lượt, `state_version`, `proposed`, `gate`, `final`, `final_source`, `fallback_reason`, `tool_calls_used` (≤ 3), `tool_errors`, `candidate_edge_ids` (mọi cạnh KG trả về trong lượt; cạnh được dùng nằm ở `final.edge_ids`), `kg_source`, `graph_version`, `regenerations_used` (≤ 1), `agent_usage` (lần gọi LLM của Agent: model trả về, phiên bản prompt, token vào/đã cache/ra (null nếu provider không trả), latency API, chi phí và bảng giá, lỗi nếu có; chỉ có khi `proposed_by = agent`), `decision_latency_ms` (thời gian proposer → gate → fallback, mọi cấu hình), `config` (cấu hình thí nghiệm, phiên bản policy/prompt/model/KB/graph).

Quy tắc truy vết, được kiểm tra trong code:

| Tình huống | Bắt buộc |
|---|---|
| Gate chấp nhận | `final` trùng `proposed`, `final_source` = người đề xuất |
| Gate từ chối | Có `violated_rules`, `final_source = fallback`, `fallback_reason = gate_rejected` |
| Agent lỗi hoặc timeout | `proposed = null`, không có gate, `fallback_reason` là `agent_*` hoặc `budget_exhausted` |
| Mọi quyết định fallback | Phải có `fallback_gate` với trạng thái `accepted`: luật dự phòng cũng phải qua gate |
| Cấu hình `rule_policy` | Không có đề xuất từ Agent, không có lỗi kiểu `agent_*` |

Kiểm tra **hình dạng** đề xuất (mã `S01`–`S09`) nằm trong `structural_violations()`. Ví dụ: intent không thuộc action, mức hint sai, backtrack không có cạnh KG, scaffold không có nội dung, end_session có payload.

**Giới hạn đã biết:** JSON Schema xuất ra **yếu hơn** Pydantic. Ràng buộc giữa action, intent, mức hint và trường bắt buộc chỉ nằm trong `structural_violations()`, không có trong file `.schema.json`. Phía khác (frontend, LLM structured output) đọc schema sẽ không tự biết các ràng buộc này. Mọi đề xuất vẫn phải đi qua Pydantic ở backend.

## 5. `StudentState`: những gì Agent được đọc

| Nhóm | Trường | Ai cung cấp |
|---|---|---|
| Định danh lượt | `student_id`, `session_id`, `state_version`, `turn_id`, `request_id`, `status`, `trigger` | Member 1 (API) |
| Bài hiện tại | `current`: problem/version, opportunity, concept, target skill, template family, relation, độ khó | Member 1 |
| Chấm bài | `latest_assessment`: status, bước sai đầu, skill, họ lỗi, misconception, diagnosis status, `final_answer_only`. **Không có đáp án** | Member 1 |
| Observation | `observation`: eligible, reason, ID | Member 1 |
| Kỹ năng | `skills[]`: `p_mastery`, số observation độc lập, ≤ 5 kết quả độc lập gần nhất, số lần đúng có hỗ trợ, phiên bản tham số | Member 1 (BKT) |
| Giả thuyết | `hypotheses[]`: ID riêng, misconception, skill, suspected/supported/ruled_out, evidence | Member 1 + Member 3 |
| Hỗ trợ | `support`: mức hint, số lượt hỗ trợ trên nút hiện tại, số lượt không tiến triển | Member 3 |
| Điều hướng | `return_stack` (≤ 2 tầng), `visited_concept_ids`, `attempted_problem_ids` (bài đã giao trong phiên, không giao lại làm bài mới) | Member 3 |
| Bài làm và lời nhắn | `latest_submission` (≤ 12 dòng, đúng các dòng analyzer đã chấm ra `latest_assessment`, xóa khi đổi bài); `latest_student_message` (lời nhắn tự do của lượt này, có thể nói khác bài làm) | Member 1 + Member 3 |
| Lịch sử | `recent_turns` (≤ 12) | Member 3 |
| Kiểm tra prerequisite | `probes` (≤ 6, xóa khi đổi bài): câu hỏi kiểm tra đã hỏi, gắn với lượt trả lời và kết quả xác minh (`pending` / `unverified` / `demonstrated` / `not_demonstrated`) | Member 3 |
| Ngân sách | `budget`: tool calls còn lại (≤ 3), lần sinh lại (≤ 1) | Member 3 |
| Sẵn sàng | `readiness`: `ready_to_advance`, điều kiện chưa đạt. Tính bằng node xác định theo plan §10, không phải Agent | Member 1 + Member 3 |

`latest_submission` và `latest_student_message` là dữ liệu người dùng, không phải chỉ dẫn cho Agent. Hai trường tách riêng để analyzer và Agent luôn thấy cùng một bài làm: nộp bài thì bài làm là `steps`, không có `steps` thì là từng dòng của `message` (tối đa 12 dòng × 160 ký tự, quá thì request bị từ chối).

Kết quả truy xuất RAG và KG **không nằm trong state**. Chúng là kết quả tool trong lượt (`TurnContext`): `current_problem_prompt` (đề bài công khai của bài đang làm, không có đáp án), `retrieved`, `edges` (prerequisite 1–2 tầng, mỗi cạnh có `depth` và `review_status`), `next_concepts` (concept kế tiếp), `problems`. Gate sẽ đối chiếu `content_ids` và `edge_ids` với kết quả tool đó. Chi tiết KG: [knowledge-graph.v1.md](knowledge-graph.v1.md).

**Ablation**, giữ cùng schema và chỉ đổi phần được nhìn thấy:

| Cấu hình | Khác biệt trong state / tool |
|---|---|
| No-BKT | `p_mastery = null`, `mastery_view = "none"`: không có bản tóm tắt mastery nào, chỉ còn evidence log thô |
| Heuristic | `p_mastery = null`, `mastery_view = "recent_ratio"`: policy dùng tỷ lệ đúng của `recent_independent` với ngưỡng riêng |
| No-KG | Không có tool KG; `edge_ids` luôn rỗng; không được backtrack, `probe_prerequisite` hay `advance_concept` |
| No-RAG | Không có tool RAG; `content_ids` chỉ chứa template đã duyệt |
| Rule-policy | Cùng state, quyết định bằng luật |

## 6. Luật policy gate (đã cài trong `gate.py`)

Gate nhận `StudentState` (đã chiếu theo cấu hình ablation), đề xuất và `TurnContext` (kết quả tool trong lượt). Mỗi luật có test riêng trong `tests/test_agent_policy.py`.

| Mã | Luật | Căn cứ |
|---|---|---|
| G01 | Assessment `needs_clarification` / `unverified` sau khi nộp bài: chỉ được `clarify` hoặc `end_session` | plan §9 |
| G02 | Mức hint tăng tối đa 1 bậc mỗi lượt (không nhảy từ 0 lên 3) | plan §9 |
| G03 | Mọi evidence ID phải có trong state | FR10-AC1 |
| G04 | `content_ids` ⊆ nội dung truy xuất trong lượt; mức tiết lộ ≤ mức hint | FR09-AC2/3 |
| G05 | `edge_ids` ⊆ cạnh KG trả về trong lượt. Với prerequisite: các cạnh phải nối thành đường từ concept hiện tại (tối đa 2 tầng) tới concept chứa skill đích, không có cạnh thừa. Với `advance_concept`: cạnh phải nằm trong `next_concepts` và dẫn tới concept của bài được chọn | plan §8.4, FR08-AC2 |
| G06 | Lỗi mới chặn `check_transfer` và `next_problem` loại tiếp tục / tăng / quay lại (mastery cao không ghi đè lỗi mới) | FR10-AC2 |
| G07 | `advance_*` cần `readiness.ready_to_advance` | plan §10 |
| G08 | `backtrack`: return stack < 2; mỗi bước chỉ lùi một tầng (tới prerequisite trực tiếp); concept nền chưa có trong nhánh hiện tại; không backtrack khi vừa làm đúng | plan §8.4, §10, FR10-AC2, FR08-AC4 |
| G09 | `return_to_parent`: `problem_id` phải bằng đỉnh return stack | plan §8.4 |
| G10 | ≥ 6 lượt hỗ trợ trên cùng nút mà **chưa làm đúng**: chỉ được `scaffold`, `backtrack`, `next_problem` (`switch_problem`), `end_session`; `switch_problem` chỉ dùng khi đã kẹt. Vừa làm đúng thì không còn kẹt (ví dụ được quay lại bài gốc) | plan §10 |
| G11 | Mức hint ≥ 3 mà vẫn sai: không dùng `minimal_hint` / `conceptual_question` nữa; phải dùng ví dụ khác, chẩn đoán hoặc prerequisite | plan §10 |
| G12 | `check_transfer` phải khác template family với bài vừa hỗ trợ | plan §6 |
| G13 | Bài được chọn phải có trong problem bank, đúng skill đích, khác bài hiện tại và chưa giao trong phiên | plan §6, §13 |
| G14 | Học sinh xin tạm dừng: chỉ được `end_session` / `student_request` | plan §10 |
| G16 | `check_transfer` chỉ sau khi vừa làm đúng | plan §9 |
| G17 | `conceptual_question` và `distinguish_hypothesis` phải trỏ tới một giả thuyết đang mở của đúng skill | plan §9 |
| G18 | `backtrack` cần bằng chứng về đúng skill nền được chọn: lỗi vừa chấm quy cho skill đó, câu trả lời cho câu hỏi kiểm tra đã được xác minh là chưa đạt, giả thuyết lỗi đang mở, hoặc ước lượng thấp (≥ 2 observation). Graph chỉ đưa ứng viên; đã hỏi kiểm tra mà chưa có câu trả lời được xác minh thì chưa phải bằng chứng | FR08-AC3 |
| G19 | `advance_concept` phải trích đúng một cạnh KG tới concept kế tiếp; không có KG (No-KG hoặc tool lỗi) thì không chuyển concept | plan §8.4, §18.1 |
| G20 | `check_transfer`, `continue_practice`, `switch_problem`, `advance_difficulty` giữ nguyên skill và concept của bài đang làm; `advance_difficulty` phải sang bài khó hơn (không biết độ khó bài hiện tại thì từ chối). Chuyển concept chỉ qua `advance_concept`, ôn prerequisite chỉ qua `backtrack` | plan §6, §9, §10 |

Không có G15: ngân sách tool (≤ 3 lần mỗi lượt) được chặn ngay trong contract `TurnContext`. Nơi gọi tool phải dừng khi hết ngân sách, nên gate không cần kiểm tra lại.

## 7. Cần chốt với nhóm

**Với Member 1:**
1. Thang hint là **0–4** theo plan §9, trong khi code nháp hiện tại (`TutorResponse`, `SessionPublic`) dùng 0–3.
2. Assessment có thêm `final_answer_only` không? Danh sách mã `error_family` và lý do eligibility là gì?
3. Có đồng ý tính `diagnose` là hỗ trợ (bảo thủ) không?
4. Ai tính `readiness`, và ở node nào?
5. Return stack và support state được lưu trong checkpoint LangGraph hay trong bảng session?

**Với Member 2:**
1. Định dạng content ID, và có trường disclosure level để gate kiểm tra G04 không?
2. Phản hồi gửi UI gồm: message, action, intent, hint level, next actions. UI có cần hiển thị riêng nhãn "ví dụ khác" (`analogous_example`) và "bài kiểm tra mới" (`check_transfer`) không?
3. API RAG có trả đúng các ID được đưa vào context, để log không ghi nguồn chưa dùng?

**Thay đổi so với bản đầu (14/11/2026, khi nối KG thật và sau review):** thêm trường tùy chọn vào `TurnContext`, `GraphEdge`, `PedagogicalDecision` (kể cả `agent_usage` khi nối Agent LLM) và `StudentState.probes` (liệt kê ở §4, §5); thêm luật G18, G19 và siết G05, G08. Sau review trước commit: thêm G20, sửa G10 (vừa làm đúng thì không còn kẹt), thêm `StudentState.latest_submission`, `CurrentTask.difficulty`, `PedagogicalDecision.workflow_version`. `contract_version` giữ `agent-contract-0.1.0` vì hợp đồng chưa chốt với nhóm; `gate_version` lên `gate-0.4.0`, Rule-policy lên `rule-policy-0.4.0`.

**Việc kỹ thuật còn lại (Member 3):**
- Biến thể strict của `DecisionProposal` cho structured output (mọi trường bắt buộc, cho phép null) đã có: `OUTPUT_SCHEMA` trong `llm_proposer.py`.
- Các quyết định mẫu trong `fixtures.v1.json` chỉ minh họa định dạng bản ghi. Gate được kiểm tra trên `scenarios.dev.v1.json`, nơi mỗi tình huống có state và context đầy đủ.
- Bước `--check` của `export_agent_contracts.py` chưa có trong CI, vì file workflow dùng chung cả nhóm.

## 8. Lệnh

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_agent_decision.py -q
.\.venv\Scripts\python.exe scripts/exports/export_agent_contracts.py --check
.\.venv\Scripts\python.exe research/agent/external_moves.py --data-dir data/external
```

Script thống kê cần dữ liệu Bridge và MathDial trong `data/external/` (thư mục bị Git ignore).
