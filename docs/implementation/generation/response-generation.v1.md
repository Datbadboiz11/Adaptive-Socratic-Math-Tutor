# Sinh và kiểm tra phản hồi, bản v1

**Trạng thái:** bản nháp của Member 3, code và test xong. Với model thật **đã chạy một lô 96 lượt trên bộ dev** ([ablation-runner §5.1](../evaluation/ablation-runner.v1.md)); mọi test dùng LLM giả. Mặc định graph vẫn viết câu bằng template. LLM chỉ viết câu khi được bật.

**Căn cứ:** plan §8.5, §9 (hint ladder), §13 bước 7, §18.2; PRD FR-12, FR-13, FR09-AC2/AC3, FR11-AC3.

## 1. Vai trò

Agent (hoặc Rule-policy) chọn *làm gì*: action, intent, mức hint, nội dung được trích. Bước này chỉ viết *câu gửi học sinh* theo đúng quyết định đó, rồi kiểm tra câu trước khi gửi. Bước này không đổi quyết định và không ghi state học sinh.

Tách hai bước là theo bài học từ Bridge và MathDial ([pedagogical-decision.v1.md](../agent/pedagogical-decision.v1.md) §1): quyết định của chuyên gia giúp LLM viết tốt hơn, còn người dạy cũng hay "nói thẳng" đáp án. Vì vậy chống lộ đáp án phải là **bước kiểm tra riêng**, không dựa vào prompt.

Mọi cấu hình ablation dùng cùng generator và verifier (plan §18.1: Rule-policy "dùng cùng generator").

## 2. Thành phần

| File (`backend/app/generation/`) | Việc |
|---|---|
| `contracts.py` | `ResponseInput` (phần generator được thấy), `ResponseAttempt`, `ResponseRecord`, mã lỗi `Check` |
| `templates.py` | Template theo intent (chuyển từ `agent/stubs.py`), câu an toàn, câu hệ thống |
| `llm_generator.py` | Lời dặn, hướng dẫn theo intent, schema đầu ra, `LLMResponseGenerator` |
| `math_text.py` | Đọc các đoạn toán trong câu tiếng Việt: vế, đẳng thức, ký hiệu ngoài phạm vi |
| `equivalence.py` | So tương đương hai vế bậc nhất (hệ số hữu tỉ); ngoài phạm vi trả "chưa xác minh được" |
| `wording.py` | Đọc lời văn: tách câu, lời khẳng định "đúng", thao tác giải được nêu ra |
| `verifier.py` | `ResponseVerifier` giữ đáp án riêng (`AnswerKeys`), kiểm tra câu |
| `responder.py` | Điều phối: sinh → kiểm tra → sinh lại → template |

## 3. Generator được thấy gì

| Gửi cho generator | Không gửi |
|---|---|
| Quyết định sau gate: action, intent, `hint_level`, `reason` | Đáp án, lời giải tham chiếu (chỉ verifier có) |
| Đề bài đang làm và đề bài vừa giao (công khai) | `student_id`, `session_id`, mastery, tham số BKT |
| Nội dung trong `final.content_ids`; gate đã kiểm tra mức tiết lộ ≤ `hint_level` | Nội dung khác đã truy xuất nhưng quyết định không trích |
| Kết quả chấm: trạng thái, bước sai đầu tiên, họ lỗi | |
| Tên chủ đề của skill mà quyết định nhắm tới (`target_skill`): tên concept trong registry, ví dụ "Tính phân phối" | Mã skill, mô tả hành vi quan sát được của skill |
| Bài làm và lời nhắn của học sinh (là dữ liệu, không phải chỉ dẫn) | |
| 3 câu gia sư vừa gửi (để không lặp), lý do bị từ chối khi sinh lại | Bản nháp bị từ chối |

Test `test_generator_input_has_no_answer_and_no_identity` kiểm tra trên cả 16 ca: input không chứa đáp án của bài cần giữ, cũng không chứa định danh học sinh.

Lời dặn khoảng 850 token, input một ca khoảng 130–200 token (ước lượng 4 ký tự/token, chưa đo thật). Mỗi intent có một dòng hướng dẫn (`INTENT_GUIDE`), cùng ý với template của intent đó. Thang hint lấy nguyên từ PRD FR-13.

## 4. Kiểm tra trước khi gửi

Câu của LLM phải qua **mọi** kiểm tra. Template chỉ cần **không lộ đáp án**: chữ trong template cố định, phần chèn vào là nội dung đã duyệt và đề bài công khai.

| Mã | Bắt được | Căn cứ |
|---|---|---|
| `answer_leak` | Đáp án cuối của bài đang làm hoặc bài vừa giao, so **theo giá trị**: "x = 8", "8 = x", "x bằng 8", "nghiệm là 16/2", "x = 4·2", "Đáp số: 2^3", "-8 - 6y" cho "-6y - 8". Biểu thức chép nguyên từ đề hay bài làm ("Khai triển -2(3y + 4)") tương đương đáp án nhưng không bị tính. Học sinh đã tự giải đúng (được xác minh) thì được xác nhận đáp án bài đó | FR12-AC2 |
| `math_unverified` | Có toán verifier không đọc được (√, ≤, π, ², "căn 64", "2 mũ 3", tích hai biểu thức có biến), nên không chứng minh được là không lộ đáp án. Coi như không đạt: sinh lại hoặc dùng template | FR12-AC1 |
| `unsourced_equation` | Đẳng thức không có trong đề, nội dung được trích, bài làm hay lời nhắn của học sinh. Chuỗi "a = b = c" trong nguồn cho phép cả "a = c" | FR12-AC1, FR12-AC3, FR09-AC3 |
| `unsourced_expression` | Biểu thức có biến không nằm trong các nguồn trên, kể cả không có dấu "=": "Bước 1 phải là 2x - 6". Một phần của biểu thức có trong nguồn ("x - 3" trong "2(x - 3)") thì được dùng | FR-13 (học sinh tự làm bước), FR12-AC3 |
| `unverified_affirmation` | Câu kể nói bài làm hay một bước là đúng ("là phép khai triển đúng", "đúng rồi", "chính xác") khi bài chưa được xác minh đúng. **Trích lại** bước của học sinh thì được; **xác nhận** nó thì không. Dạng hỏi ("có đúng không") và phủ định ("chưa đúng") không bị tính | FR12-AC2, FR05-AC5 |
| `hint_level_exceeded` | Chỉ cách làm quá mức hint. Mức 0–1: chỉ được hỏi, hoặc nhắc thao tác có trong nội dung đã duyệt/đề bài; câu kể bảo học sinh làm thao tác mới ("em cộng 6 vào hai vế") bị chặn. Mọi mức: không kể quá **một** thao tác mới, vì một chuỗi thao tác ("nhân…, rồi cộng…, và chia…") là dàn bài lời giải | plan §9, FR-13 |
| `missing_question` | Action là câu hỏi (`diagnose`, `conceptual_question`) mà câu không hỏi gì | `ACTION_SPECS`, FR-12 |
| `unknown_content` | `content_ids_used` có ID ngoài quyết định | FR09-AC2 |
| `missing_content` | Scaffold không dùng nội dung đã duyệt | FR12-AC3 |
| `too_many_questions` | Quá 1 dấu "?" | FR-12, rubric "Rõ ràng" |
| `too_long` | Quá 500 ký tự (ngưỡng khởi đầu, chốt trên dev) | FR-12 "ngắn" |
| `repeated_message` | Trùng nguyên văn (bỏ qua hoa thường, khoảng trắng) một trong 3 câu vừa gửi | FR13-AC2 |
| `answer_key_missing` | Không có đáp án để kiểm tra, nên không gọi LLM | §18.2 |

Năm mã `answer_key_missing`, `answer_leak`, `math_unverified`, `unsourced_equation`, `unsourced_expression`, cùng phần không phụ thuộc mức hint của `hint_level_exceeded` (kể ra quá một thao tác mới), không cần quyết định của policy, nên nằm riêng ở `ResponseVerifier.solution_checks`. `check_generated` gọi hàm này rồi thêm phần theo mức hint (ở mức 0–1 bảo học sinh làm thao tác mới); kết quả kiểm tra của hệ thống không đổi. Socratic LLM baseline cũng dùng nó để có cùng policy về tiết lộ với hệ thống (plan §18.2; [ablation-runner §3.1](../evaluation/ablation-runner.v1.md)).

**Cách so:** `math_text` tách câu thành các đoạn toán (số, biến một chữ cái, phép toán, ngoặc, "=" hoặc chữ "bằng" giữa hai biểu thức), rồi chuẩn hóa từng vế: chữ thường, bỏ khoảng trắng, dấu Unicode về ASCII, bỏ dấu nhân trước biến hoặc ngoặc. Luật về nguồn so chuỗi. Riêng đáp án thì so **giá trị** qua `Equivalence`: bản mặc định (`linear_equivalent`) đưa mỗi vế về dạng bậc nhất có hệ số hữu tỉ, không dùng `eval`; ngoài phạm vi thì trả `None` ("chưa xác minh được"), và verifier coi đó là `math_unverified`. Bộ so SymPy của Member 1 có thể thay qua `ResponseVerifier(answer_keys, equivalence=...)`.

Hai luật về nguồn đi cùng nhau, nên LLM không thể đưa vào câu một bước toán mới có biến, dù đúng hay sai. Mọi phép toán có biến phải chép từ nội dung đã duyệt hoặc từ bài của học sinh. Luật lời văn (`wording`) chỉ đọc từ ngữ, và xét theo **mệnh đề**, không theo dấu "?" cuối câu:

- Câu được tách mệnh đề tại dấu phẩy, chấm phẩy, hai chấm (số thập phân "6,5" không bị tách). Mệnh đề phụ mở đầu bằng "khi", "nếu", "trước khi"… được gộp vào mệnh đề sau.
- Mệnh đề hỏi là mệnh đề cuối của câu có "?", hoặc mệnh đề có từ để hỏi (nào, gì, sao, bao nhiêu, mấy, đâu). Trong "Em hãy cộng sáu vào hai vế nhé, em hiểu chưa?" chỉ mệnh đề sau là hỏi.
- Lời khẳng định "đúng"/"chính xác" bị tính ở **mọi** mệnh đề, kể cả câu hỏi ("vì sao bước 2 đúng?" vẫn ngầm khẳng định). Không tính dạng phủ định ("chưa đúng") và dạng hỏi ngay sau ("đúng không", "đúng chưa", "đúng hay sai").
- Thao tác: "nhân/chia/cộng/trừ" khi có đối tượng ngay sau ("nhân 2", "cộng sáu vào"), "chuyển vế", "khai triển", "rút gọn", "phá ngoặc", "đổi dấu". Nhờ vậy "phép nhân", "chia nhỏ", "trừ khi" không bị tính. Thao tác chỉ được coi là "đang hỏi" khi nằm trong mệnh đề hỏi **và** không có từ mệnh lệnh đứng trước ("hãy", "cần", "phải", "nên", "thử"): "em thử cộng 6 xem được gì?" là lời bảo làm.

Bộ so tương đương theo thứ tự ưu tiên thông thường: dấu âm một ngôi lỏng hơn lũy thừa (`-2^2 = -4`, `(-2)^2 = 4`), lũy thừa kết hợp từ phải sang.

## 5. Luồng

```text
LLM ──(đạt)──→ gửi (llm)
 │──(lỗi sửa được, còn ngân sách)──→ LLM sinh lại, kèm mã lỗi ──(đạt)──→ gửi (llm)
 └──(vẫn không đạt / timeout, sai schema / thiếu đáp án)──→ template ──→ template an toàn ──→ câu hệ thống
```

- Tối đa **1 lần sinh lại** (`MAX_REGENERATIONS`, PRD FR11-AC3), đếm bằng `StudentState.budget.regenerations_remaining`, và ghi vào `PedagogicalDecision.regenerations_used`.
- Timeout, lỗi provider hoặc sai schema thì **không sinh lại**, dùng template ngay (FR11-AC3: "lỗi schema dùng policy luật và template").
- Thay bằng template là **fallback, không phải sinh lại**. Bản trước tính việc này là một lần sinh lại; nay `regenerations_used = 0` khi chỉ có template thay thế.
- Lý do gửi kèm khi sinh lại chỉ có mã lỗi và câu hướng dẫn sửa (`FEEDBACK`), **không chứa đáp án hay bản nháp bị từ chối**.

`final_source` trong `TutorReply`: `template` khi không bật LLM; `llm`; `template_fallback` khi template thay cho câu của LLM hoặc template đầy đủ bị chặn; `system` khi cả template an toàn cũng bị chặn.

## 6. Nối vào LangGraph

`Services(response_generator=LLMResponseGenerator(client))` bật LLM viết câu. Mặc định là `None`: graph viết câu bằng template như trước. `Services.verifier` mặc định đọc đáp án của bài mẫu (`stubs.demo_answer_key`). Bản thật lấy đáp án từ problem bank.

`generate` và `verify` là hai node; `verify` không đạt thì quay lại `generate`. LangGraph checkpoint sau mỗi node, nên câu của LLM được lưu trước khi kiểm tra. Verify lỗi rồi gửi lại đúng request thì graph kiểm tra lại câu đã lưu, không gọi model lần nữa (`test_retry_after_verify_failure_does_not_call_the_llm_again`).

Mỗi lượt ghi một `ResponseRecord` vào `response_log` (`TutorEngine.responses()`): mọi lần sinh, kèm lỗi, usage, đầu ra thô của model (NFR-04), phiên bản template/verifier/prompt. Schema: `contracts/generation/ResponseRecord.schema.json`. `WORKFLOW_VERSION` lên `tutor-graph-0.5.0`.

## 7. Chạy đánh giá

```powershell
# Chỉ verifier: câu oracle và các câu lỗi đã gán nhãn; không gọi API
.\.venv\Scripts\python.exe research/generation/evaluate_generation.py
# Thêm đường LLM với LLM giả trả câu oracle; không gọi API
.\.venv\Scripts\python.exe research/generation/evaluate_generation.py --llm fake
# GỌI API THẬT (tốn phí): 16 ca, tối đa 2 lần gọi mỗi ca (kể cả sinh lại)
.\.venv\Scripts\python.exe research/generation/evaluate_generation.py --llm openai --yes --out data/generation_runs/dev-001.jsonl
```

Bộ ca `contracts/generation/cases.dev.v1.json` dùng lại 16 tình huống của Agent ([langgraph-skeleton.v1.md](../agent/langgraph-skeleton.v1.md) §4) với quyết định Rule-policy của từng tình huống: phủ cả 9 action nhưng chỉ 15/25 intent. Mỗi ca có một câu oracle (phải qua verifier) và có thể có câu lỗi gán nhãn (26 câu, gồm sáu câu của hai lần review, làm ca hồi quy).

| Chỉ số | Ý nghĩa |
|---|---|
| `exact`, `tp/fp/fn` theo mã lỗi | Verifier báo đúng tập lỗi của câu đã gán nhãn |
| `oracle_passed` | Câu viết đúng không bị chặn nhầm |
| `first_accepted`, `regenerated`, `final_sources` | Câu của model qua ngay, phải sinh lại, hay rơi về template/câu hệ thống |
| `llm_violations` | Model hay vi phạm lỗi nào |
| `llm_calls`, `api_ms`, token, `cost_usd_known` | Vận hành, cùng cách tính với Agent |

Kết quả hiện có: verifier 42/42 khớp, 16/16 câu oracle qua; LLM giả 16/16 qua ngay. Sáu câu của review cũng được test qua `TutorEngine` (`test_review_messages_never_reach_the_student`): LLM viết câu lỗi cả hai lần thì học sinh nhận template. **Không phải kết quả độc lập:** câu lỗi do chính người viết verifier soạn. Câu của model thật phải được chấm độc lập theo rubric (plan §19.2, PRD FR12-AC5; [quy trình chấm](../evaluation/rating-workflow.v1.md)); verifier cho qua không phải nhãn "đúng toán". File `--out` giữ câu đã gửi và mọi lần sinh để chấm.

### 7.1. Sửa sau lượt chạy model thật trên bộ dev (`response-prompt-0.3.0`, `templates-0.2.0`, `response-verifier-0.4.0`)

Lượt chạy 96 lượt ([ablation-runner §5.1](../evaluation/ablation-runner.v1.md)) cho thấy hai lỗi, đều ở `diagnose`:

- **Model hỏi hai câu trong một lượt** (35/41 lỗi verifier tìm thấy): mở bằng câu hỏi có/không "Em có nhớ ... không?" rồi mới hỏi câu thật. Sinh lại chỉ sửa được 10/25 lượt, nên 15 lượt phải gửi câu template.
  - Luật 4 của lời dặn giờ nói cụ thể: cả câu có tối đa một dấu hỏi, không mở bằng câu hỏi có/không rồi hỏi tiếp.
  - Lý do gửi kèm khi sinh lại (`too_many_questions`) nói rõ cách sửa: giữ đúng một câu hỏi, bỏ câu mở đầu có/không.
  - Bản nháp bị từ chối vẫn không được gửi lại cho model, vì nó có thể chứa đáp án (`test_rejected_message_is_regenerated_once_with_feedback_and_no_answer`).
- **Câu template của `probe_prerequisite` không nói nó hỏi về phần nào** ("em nhắc lại quy tắc nền của dạng bài này"), và model cũng không được cho biết skill nền là gì.
  - `ResponseInput.target_skill_title` mang tên chủ đề của skill được nhắm, lấy từ tên concept trong registry (`kg_tool.skill_title`). Template và model cùng nhận tên này.
  - Khi quyết định không trích nội dung, template hỏi: *em nhắc lại bằng lời của mình cách làm của phần "Tính phân phối" được không?* Skill ngoài registry thì vẫn dùng câu chung cũ.
  - Verifier (`response-verifier-0.4.0`) bỏ qua chỗ **gọi tên** chủ đề khi tìm thao tác, vì 12/40 tên concept chứa tên phép toán. Một cụm trùng tên chủ đề chỉ được coi là tên khi đủ ba điều: đứng sau một danh từ gọi tên (phần, chủ đề, bài, mục), nằm trong ngoặc kép, và không có từ mệnh lệnh đứng ngay trước. Lời dặn yêu cầu model viết đúng dạng *phần "<tên>"*; câu template cũng viết dạng đó.
    - Cho qua: *mình hỏi lại về phần "Nhân chia số có dấu" nhé: tích của hai số âm mang dấu gì?*
    - Vẫn chặn ở mức hint 0: *em hãy thu gọn hạng tử đồng dạng ở vế trái nhé* (tên concept "Thu gọn hạng tử đồng dạng" dùng làm lời bảo làm), kể cả khi cụm đó nằm trong ngoặc kép (*em "thu gọn hạng tử đồng dạng" ở vế trái*, *em hãy làm phần "thu gọn hạng tử đồng dạng"*), và *em hãy nhân 2 với từng số hạng*.
    - Tên chủ đề không làm phép toán nào thành "đã cho". Test: `test_naming_the_target_topic_is_not_telling_the_method`, `test_an_instruction_that_reuses_the_topic_name_is_still_an_instruction`.
    - Chặn nhầm theo hướng an toàn: model nhắc tên chủ đề không đúng dạng trên, hoặc diễn đạt lại bằng chữ khác, thì câu có thể bị chặn. Cần đo trên model thật.
    - Còn lọt: đây là luật theo từ ngữ, không hiểu nghĩa câu. Một lời bảo làm viết đúng dạng tên và không dùng từ mệnh lệnh nào (*em làm phần "thu gọn hạng tử đồng dạng" ở vế trái nhé*) vẫn qua. Câu đã hiển thị vẫn phải chấm độc lập (FR12-AC5).

Chưa chạy lại với model thật, nên chưa biết tỷ lệ hỏi hai câu có giảm không. Tên concept trong registry vẫn là bản nháp chưa có người duyệt ([knowledge-graph.v1.md](../agent/knowledge-graph.v1.md)); câu hỏi kiểm tra tốt hơn vẫn phải là câu hỏi đã duyệt trong nội dung của Member 2.

## 8. Cần chốt với nhóm

**Member 2:**
1. UI cần phản hồi dạng một đoạn chữ (như hiện tại: `TutorReply.message`), hay tách trường (câu hỏi, mức gợi ý, "ví dụ khác")? Plan §23.1 ghi đây là điểm giao Member 3 ↔ Member 2.
2. Problem bank cung cấp đáp án cuối (`AnswerKey.final_answers`) **chỉ cho verifier**, ở dạng nào? Hiện dùng chuỗi như `"x=8"`, `"-6y-8"`.
3. Ai duyệt chữ của template (`TEMPLATE_VERSION`)? Template hiện là bản nháp của Member 3 nhưng được dùng làm "fallback đã duyệt" (FR12-AC1).

**Member 1:**
1. Verifier đã có interface `Equivalence = (a, b) -> bool | None` và bản bậc nhất tạm thời. Bộ so của validator (SymPy) có dùng được qua interface này không? Khi nào trả "chưa xác minh được"?
2. Đáp án trong problem bank và dạng chuẩn hóa của validator có dùng chung một dạng không?
3. Câu trả lời bằng lời chưa được xác minh chỉ nhận phản hồi thận trọng (FR05-AC5). Verifier hiện chặn mọi lời khẳng định "đúng" khi `assessment_status` khác `verified_correct`; quy ước này có khớp với trạng thái chấm của Member 1 không?

## 9. Giới hạn

| Giới hạn | Ảnh hưởng | Khi nào xử lý |
|---|---|---|
| Tên của 5/40 concept chứa chữ mà verifier đọc là toán không kiểm tra được (N09 "Lũy thừa…", N10 "Căn bậc hai…", A05 và A06 "…bình phương…", F08 "…mũ… lũy thừa…") | Câu của model nhắc tên các chủ đề này bị chặn `math_unverified`, nên lượt đó gửi câu template. Câu template không bị ảnh hưởng. Bộ tình huống dev chưa có concept nào trong số này | Quyết định có miễn `math_unverified` cho chỗ gọi tên chủ đề hay không; đây là kiểm tra gắn với lộ đáp án nên cần review riêng |
| Với model thật mới có một lô 96 lượt trên bộ dev: 15 lượt phải gửi template, đều ở `diagnose` và hầu hết do `too_many_questions` | Số liệu đó là của `response-prompt-0.2.0`; chưa có số liệu cho bản đã sửa (§7.1) | Chạy lại bộ dev khi được phép dùng API |
| So tương đương chỉ cho biểu thức bậc nhất; luật về nguồn vẫn so chuỗi | Ngoài bậc nhất thì "chưa xác minh được", câu bị thay bằng template (an toàn nhưng tốn lượt). Một cách viết khác của bước có trong bài làm ("2·x - 3" cho "2x - 3" thì được, "-3 + 2x" thì không) bị coi là biểu thức mới | Bộ so của Member 1 |
| Với bài có đáp án là biểu thức/số, mọi vế tương đương đáp án mà không chép nguyên văn từ đề đều bị tính là lộ ("-7 + 3" khi đề là "(-7) + 3") | Thận trọng: có thể chặn nhầm câu chỉ viết lại đề | Đo tỷ lệ chặn trên model thật |
| Số viết bằng chữ không được nhận ("nghiệm là tám") | Lộ đáp án viết bằng chữ sẽ lọt | Thêm khi gặp trong dữ liệu thật |
| Luật lời văn chỉ bắt mẫu từ ngữ rõ ràng | Khen gián tiếp ("em làm hay lắm" khi bài sai), thao tác diễn đạt khác ("đưa 6 sang vế phải", "làm cho x đứng một mình") vẫn lọt; "đúng" nghĩa "chính" ("đúng một việc") có thể bị chặn nhầm | Chấm độc lập (FR12-AC5); thêm mẫu khi gặp |
| Câu hỏi giả định nêu một thao tác ("Nếu em cộng 6 vào hai vế thì em được gì?") được tính là hỏi, nên qua ở mức 0 | Thực chất là gợi ý một thao tác; chuỗi hai thao tác trở lên vẫn bị chặn | Xem trên câu thật của model rồi quyết định có coi là chỉ dẫn không |
| Không kiểm tra câu có đúng intent hay không, ngoài việc action câu hỏi phải có câu hỏi | Câu "qua" vẫn có thể lệch ý quyết định | Chấm rubric; cân nhắc LLM-as-judge làm phụ trợ (plan §19.2 không cho dùng làm nguồn chấm duy nhất) |
| Hai luật về nguồn rất chặt: LLM không viết được phép toán mới có biến, kể cả đúng | Có thể làm tăng tỷ lệ rơi về template | Đo `llm_violations` trên model thật rồi mới nới |
| Template chỉ được kiểm tra lộ đáp án | Chữ template lặp lại khi cùng intent | Template cần người duyệt (§8) |
| Biến được nhận là một chữ cái Latin đứng riêng | Chữ "a" hay "y" đứng riêng trong lời văn bị đọc thành biến | Chưa gặp trong bộ dev; theo dõi `oracle_passed` |
| Bộ ca dev nhỏ (16 oracle, 26 câu lỗi), tự soạn, mới phủ 15/25 intent | Không dùng làm kết quả báo cáo; 10 intent chưa có câu mẫu | Mở rộng bằng câu thật của model và pilot |

## 10. Lệnh

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_generation.py -q
.\.venv\Scripts\python.exe research/generation/evaluate_generation.py --llm fake
.\.venv\Scripts\python.exe scripts/exports/export_agent_contracts.py --check
```
