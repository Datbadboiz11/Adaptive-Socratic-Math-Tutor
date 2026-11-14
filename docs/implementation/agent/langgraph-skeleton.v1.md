# Policy gate, Rule-policy và khung LangGraph, bản v1

**Trạng thái:** khung chạy được từ đầu đến cuối với **stub** thay cho phần của Member 1 và Member 2. Knowledge Graph đã là bản thật ([knowledge-graph.v1.md](knowledge-graph.v1.md)). Agent LLM đã có ([llm-agent.v1.md](llm-agent.v1.md)) nhưng **chưa chạy với model thật**; proposer mặc định vẫn là Rule-policy để chạy không cần API.
**Hợp đồng dữ liệu:** [pedagogical-decision.v1.md](pedagogical-decision.v1.md).

## 1. Luồng một lượt

```text
START → load ──(request trùng)──→ END
          │
          ▼
       analyze → observe → readiness → context → decide → generate → verify → commit → END
```

| Node | Việc | Ai làm thật | Hiện tại |
|---|---|---|---|
| `load` | Đọc state phiên từ checkpoint; request đã xử lý thì dừng ngay, không chấm lại | Member 3 | Thật |
| `analyze` | Chấm bài (khi nộp bài); cập nhật số lượt không tiến triển và giả thuyết lỗi; gắn lượt này với câu hỏi kiểm tra prerequisite đang chờ và xác minh câu trả lời | Member 1 (chấm), Member 3 (giả thuyết, xác minh câu trả lời) | Chấm bằng stub so khớp chuỗi; xác minh câu trả lời là stub luôn trả `unverified` |
| `observe` | Xét observation hợp lệ, cập nhật BKT | Member 1 | Stub: BKT tham số mặc định |
| `readiness` | Tính điều kiện sẵn sàng chuyển concept (plan §10) | Member 1 + Member 3 | Thật, ngưỡng khởi đầu |
| `context` | Gọi tool: KG, RAG, problem bank (≤ 3 lần). Neo4j lỗi thì KG dùng bản đọc từ file; tool hỏng hẳn thì chạy tiếp không có tool. Cả hai đều ghi `tool_errors` vào decision log | Member 3 (KG), Member 2 (RAG) | KG thật (registry, kể cả cạnh nháp); RAG và problem bank là stub |
| `decide` | Agent đề xuất → policy gate → fallback → `PedagogicalDecision`; ghi token/latency/chi phí của lần gọi LLM | Member 3 | Thật; Agent = Rule-policy hoặc Agent LLM (`LLMProposer`), chọn theo cấu hình |
| `generate` | Viết câu trả lời từ quyết định và nội dung được phép | Member 3 | Template |
| `verify` | Kiểm tra lộ đáp án; vi phạm thì thay bằng câu dự phòng (1 lần) | Member 3 | Chỉ so khớp đáp án cuối |
| `commit` | Áp tác động của quyết định (mức hint, đổi bài, return stack, trạng thái phiên), tăng `state_version`, ghi decision log | Member 3 | Thật |

`TutorEngine` (trong `backend/app/agent/graph.py`) là điểm vào cho API: `start()`, `turn()`, `state()`, `decisions()`. Mỗi phiên là một `thread_id` trong checkpointer. Mặc định dùng `InMemorySaver`; khi nối DB thì truyền checkpointer PostgreSQL vào.

**Mỗi `request_id` được xử lý đúng một lần, kể cả khi gửi đồng thời.** `turn()` đọc checkpoint, kiểm tra request và chạy graph trong cùng một khóa của phiên (`SessionLocks`). Mặc định mọi engine trong một tiến trình dùng chung `PROCESS_SESSION_LOCKS`; chạy nhiều tiến trình thì phải truyền bản khóa dùng chung giữa các tiến trình (ví dụ advisory lock PostgreSQL). Trong khóa, `turn()` xử lý theo ba trường hợp:

| Tình huống | Xử lý |
|---|---|
| Request đã hoàn tất, kể cả khi đã có lượt khác xen giữa | Trả lại phản hồi đã lưu (`duplicate = true`), không chạy graph |
| Lượt trước lỗi giữa chừng, gửi lại **cùng** request | Chạy tiếp từ node bị lỗi trong checkpoint; không phân tích lại, không thêm bằng chứng |
| Lượt trước lỗi giữa chừng, gửi request **khác** | Từ chối bằng `TurnInProgress` (API nên trả 409); client phải gửi lại request cũ trước |

## 2. Đảm bảo đã có test

| Yêu cầu | Test |
|---|---|
| Nhiều lượt liên tiếp: chẩn đoán → hỏi khái niệm → gợi ý → chia nhỏ → backtrack → quay lại → kiểm tra chuyển giao | `test_full_session_flow` |
| BKT chỉ cập nhật ở lần làm độc lập đầu tiên; đúng sau hỗ trợ không tăng observation | `test_bkt_only_updates_on_independent_first_attempt` |
| Gửi lại cùng request không xử lý lần hai | `test_duplicate_request_is_not_processed_twice` |
| Gửi lại request cũ sau khi đã có lượt khác xen giữa vẫn nhận phản hồi cũ | `test_old_request_replayed_after_other_turns_returns_stored_reply` |
| Lỗi giữa lượt rồi gửi lại: chạy tiếp, không tính thêm bằng chứng | `test_retry_after_mid_turn_failure_resumes_without_reanalysis` |
| Tool KG/RAG lỗi không làm hỏng lượt | `test_tool_failure_degrades_instead_of_breaking_turn` |
| Neo4j tắt: vẫn backtrack được nhờ bản đọc từ file, lỗi được ghi log một lần | `test_neo4j_outage_falls_back_to_registry_without_losing_kg` |
| Chỉ dùng cạnh đã duyệt thì hiện không có cạnh nào (registry còn nháp) | `test_approved_only_kg_gives_no_edges_while_registry_is_draft` |
| Hỏi kiểm tra prerequisite chưa phải bằng chứng: xin gợi ý hoặc câu trả lời chưa xác minh không dẫn tới backtrack; chỉ câu trả lời được xác minh là chưa đạt mới dẫn tới | `test_asking_a_probe_is_not_evidence_for_backtrack`, `test_unverified_probe_answer_is_not_evidence`, `test_verified_failed_probe_allows_backtrack`, `test_demonstrated_probe_blocks_backtrack_and_reprobe` |
| Agent không chuyển concept được khi không trích cạnh KG hoặc không có KG | `test_agent_cannot_advance_concept_without_kg_edge` |
| Engine mới đọc tiếp phiên qua checkpointer **dùng chung trong cùng tiến trình**. Chưa chứng minh khởi động lại tiến trình thật (xem §5) | `test_new_engine_reads_shared_checkpointer` |
| Tạm dừng không bị ghi thành câu trả lời sai; tiếp tục được | `test_pause_resume_and_completed_session` |
| Agent lỗi (sai schema, timeout, exception) hoặc bị gate từ chối đều có fallback và được ghi log | `test_agent_failures_fall_back`, `test_agent_proposal_rejected_by_gate_is_logged` |
| Phản hồi lộ đáp án bị thay | `test_answer_leak_is_replaced` |
| No-KG không backtrack; No-BKT che mastery khỏi policy nhưng BKT vẫn chạy | `test_no_kg_cannot_backtrack`, `test_no_bkt_hides_mastery_from_policy_only` |
| Mỗi luật gate có test vi phạm riêng | `tests/test_agent_policy.py` |
| Hai request đồng thời (cùng hoặc khác `request_id`, cùng hoặc khác engine) được xử lý lần lượt, không trùng lượt | `test_concurrent_same_request_is_processed_once`, `test_two_engines_sharing_checkpointer_and_locks_process_once`, `test_concurrent_different_requests_run_one_after_another` |
| Analyzer và Agent thấy cùng một bài làm; lời nhắn giữ riêng | `test_graded_work_and_message_reach_the_agent_separately`, `test_submission_comes_from_steps_or_message_lines` |
| Vừa làm đúng bài nền sau 6 lượt hỗ trợ thì quay lại bài gốc | `test_solved_after_support_limit_returns_to_parent` |
| Agent LLM trong graph: mỗi lượt ghi `agent_usage`; LLM timeout thì fallback và vẫn ghi latency | `test_engine_with_llm_agent_logs_usage_per_turn` (các test còn lại của Agent LLM trong `tests/test_agent_llm.py`) |
| Mọi cấu hình đều ghi thời gian proposer → gate → fallback (`decision_latency_ms`) | `test_engine_records_decision_latency_for_rule_policy`, `test_run_decision_times_the_whole_chain` |

## 3. Rule-policy v1

Thứ tự kiểm tra trong `rule_policy.py`, theo bảng plan §9:

1. Học sinh xin dừng → `end_session`.
2. Đã hỗ trợ ≥ 6 lượt trên cùng bước → đổi bài (`switch_problem`); hết bài thì dừng nhánh (`stuck_limit`).
3. Tiếp tục phiên, hoặc nhắn tin khi chưa có bài làm → nhắc lại đề (`clarify`).
4. Xin gợi ý trước khi nộp → `minimal_hint`.
5. Không chấm được → `clarify`.
6. **Làm đúng:**
   - Đang trong nhánh backtrack → quay lại bài trước.
   - Đúng sau hỗ trợ → `check_transfer` bằng bài khác họ mẫu.
   - Đủ điều kiện sẵn sàng → chuyển sang concept kế tiếp trên KG (bỏ concept còn prerequisite khác đang yếu), hoặc tăng độ khó.
   - Còn lại → luyện tiếp.
7. **Làm sai:**
   - Đã ở mức hint ≥ 3 → backtrack tới prerequisite trực tiếp **có bằng chứng học sinh đang thiếu**; chưa có bằng chứng thì hỏi kiểm tra prerequisite trước (mỗi skill một lần trên một bài; đã hỏi chưa phải là bằng chứng); không được thì dùng ví dụ khác mức 4; không có ví dụ thì hỏi lại cách nghĩ.
   - Xin gợi ý hoặc ≥ 2 lượt không tiến triển → tăng mức hint. Nếu misconception đã có bằng chứng lặp lại thì hỏi khái niệm.
   - Lỗi thao tác, lịch sử kỹ năng tốt → đề nghị tự kiểm tra.
   - Skill nền có ước lượng thấp → hỏi kiểm tra prerequisite trước, sau đó mới backtrack.
   - Có giả thuyết lỗi: còn nghi ngờ thì hỏi chẩn đoán; đã có bằng chứng (hoặc vừa chẩn đoán xong) thì hỏi khái niệm.
   - Chưa rõ nguyên nhân → hỏi học sinh giải thích cách làm.
   - Còn lại → gợi ý nhẹ.

Ngưỡng (0,4 / 0,6 / 0,8, ≥ 3 observation, 2 lượt không tiến triển) là **giá trị khởi đầu để thử trên dev**, chưa phải ngưỡng chốt (plan §10).

**Ba cách nhìn mastery** (`StudentState.mastery_view`, đặt bởi `project_state` theo cấu hình):

| Cấu hình | `mastery_view` | Policy được dùng | Hệ quả |
|---|---|---|---|
| Full, No-KG, No-RAG, Rule-policy | `bkt` | P(L) | |
| Heuristic | `recent_ratio` | Tỷ lệ đúng của ≤ 5 observation độc lập gần nhất, ngưỡng riêng trong `THRESHOLDS` | Vẫn nhận ra "lịch sử tốt" và "skill nền yếu" |
| No-BKT | `none` | Không có bản tóm tắt mastery; chỉ dùng bằng chứng của lượt hiện tại và evidence log thô | Không có luật dựa trên lịch sử; readiness chỉ xét số observation, hai lần độc lập gần nhất và giả thuyết mở |

Test `test_no_bkt_and_heuristic_decide_differently` kiểm tra hai cấu hình này cho quyết định khác nhau trên cùng tình huống. Ngưỡng của Heuristic hiện **trùng giá trị** với BKT và chưa tune; theo plan §18.2 phải chọn riêng trên dev.

Chuỗi fallback trong `decide.py`: đề xuất → Rule-policy → `last_resort` (luôn hợp lệ: dừng an toàn). Mọi quyết định cuối đều qua gate. Nếu cả `last_resort` cũng bị gate từ chối thì đó là lỗi lập trình, hệ thống raise thay vì gửi phản hồi sai luật.

## 4. Bộ tình huống dev

`contracts/agent/scenarios.dev.v1.json` có 16 tình huống, phủ đủ 9 action: lỗi phân phối lần đầu, misconception lặp lại, lỗi tính toán với lịch sử tốt, input mơ hồ, xin gợi ý ở các mức, kẹt ở mức 3 (có KG và No-KG), đúng sau hỗ trợ, quay lại sau backtrack, sẵn sàng chuyển concept, tạm dừng, kẹt 6 lượt, skill nền yếu, xin gợi ý trước khi nộp.

Mỗi tình huống có `acceptable_actions` và `forbidden_actions` để dùng lại khi chấm Agent sau này. `expected_rule_action` chỉ là kết quả hồi quy của Rule-policy, không phải nhãn chuẩn duy nhất. Đây là dữ liệu **dev tự soạn**, không dùng làm test chính thức (plan §11.5, §19.3).

## 5. Giới hạn hiện tại

| Giới hạn | Ảnh hưởng | Khi nào xử lý |
|---|---|---|
| Analyzer, observation/BKT, RAG, problem bank đều là stub, chỉ có 7 bài mẫu | Chưa phản ánh chất lượng thật | Khi Member 1 và Member 2 có API |
| Cả 68 cạnh KG còn nháp; khung đang bật `include_drafts` | Chưa dùng được cho học sinh thật | Sau khi rà soát cạnh ([knowledge-graph.v1.md](knowledge-graph.v1.md) §7) |
| Agent LLM chưa chạy với model thật | Chưa có số liệu về chất lượng quyết định, latency và chi phí thật | Khi được phép dùng API ([llm-agent.v1.md](llm-agent.v1.md) §6) |
| Context gọi tool cố định, Agent chưa tự chọn tool | Chưa có quyết định "cần tra gì" | Sau khi có kết quả Agent LLM trên dev |
| Verifier chỉ so khớp đáp án cuối, chưa kiểm tra đúng toán | Câu sai toán vẫn lọt | Cùng Member 1 (SymPy) |
| Generator là template; dễ lặp câu khi cùng intent | Trải nghiệm kém | Bước sinh bằng LLM |
| Giả thuyết lỗi bị coi là `ruled_out` sau một lần làm đúng độc lập | Có thể đóng giả thuyết quá sớm | Chờ Member 1 xác nhận quy tắc |
| Readiness chưa kiểm tra "hai bài thuộc mẫu khác nhau" | Điều kiện §10 chưa đủ | Khi có lịch sử theo family |
| Checkpointer mặc định ở bộ nhớ | Mất khi tắt tiến trình thật; chưa có test khởi động lại bằng hai tiến trình riêng | Nối PostgreSQL cùng Member 1, rồi viết test hai tiến trình |
| Khóa phiên mặc định chỉ có tác dụng trong một tiến trình | Chạy nhiều worker API vẫn có thể xử lý trùng lượt | Cài `SessionLocks` bằng advisory lock PostgreSQL khi nối checkpointer DB (Member 1) |
| Decision log và bảng `processed` (request → phản hồi) nằm trong state, không giới hạn độ dài | Phiên dài sẽ nặng | Chuyển sang bảng DB có khóa `request_id` |
| Lượt lỗi giữa chừng mà gửi lại vẫn lỗi (ví dụ generator hỏng hẳn) thì phiên bị kẹt ở `TurnInProgress` | Học sinh không gửi được request mới | Thêm cơ chế hủy lượt dở dang có ghi log |

## 6. Lệnh

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_agent_decision.py tests/test_agent_policy.py tests/test_agent_graph.py tests/test_agent_llm.py tests/test_kg.py -q
.\.venv\Scripts\python.exe scripts/exports/export_agent_contracts.py --check
```
