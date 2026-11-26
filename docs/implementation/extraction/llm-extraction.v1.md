# LLM extraction cho Analyzer, bản v1

**Trạng thái:** bản nháp của Member 3, code và test xong. Hợp đồng chờ Member 1 review (PRD §8: Member 1 review hợp đồng extraction). **Chưa chạy với model thật**; mọi test dùng LLM giả.
**Liên quan:** plan §8.2, PRD FR-04, FR-05; grammar nhập bài [`g2-v1`](../mvp/phase1/INPUT_GRAMMAR.md); [Agent LLM](../agent/llm-agent.v1.md) (dùng chung client và cách đo chi phí).

## 1. Vai trò

Học sinh có thể nộp bài lẫn chữ và công thức: "em nhân 2 vào ngoặc được 2x - 3 = 10". Extraction tách bài làm đó thành các bước theo grammar, để validator của Member 1 chấm.

**LLM chỉ tách, không chấm.** Đúng hay sai do luật và SymPy quyết định (FR-05). Extraction không bao giờ sửa bài làm: học sinh viết sai thì bước sai phải đến validator nguyên như vậy, nếu không thì chẩn đoán lỗi và BKT đều sai theo.

```text
bài làm ──→ luật g2-v1 ──(mọi dòng đúng cú pháp)──────────────────────────→ các bước  (không gọi LLM)
               │──(6,5; 1/2x; nhiều "="; không có "=")──────────────────────→ hỏi lại   (không gọi LLM)
               └──(chữ lẫn công thức, số thứ tự...)──→ LLM chọn đoạn ──→ chốt chặn ──→ các bước hoặc hỏi lại
```

LLM chỉ được gọi khi luật không tự quyết được. Trên bộ ca dev, 19/32 ca được luật xử lý mà không gọi model.

## 2. Thành phần

| File | Nội dung |
|---|---|
| `backend/app/extraction/contracts.py` | Hợp đồng `ExtractionResult`, `ExtractedStep`, `ExtractionRecord`, danh sách lý do `Reason` |
| `backend/app/extraction/grammar.py` | Cú pháp `g2-v1` ở mức ký hiệu: chuẩn hóa ký tự, tách token, kiểm tra một phương trình. Không làm toán |
| `backend/app/extraction/guards.py` | Chốt chặn đầu ra LLM: chép nguyên văn, không cắt bớt, không bỏ sót |
| `backend/app/extraction/extractor.py` | `StepExtractor`: luật → LLM → chốt chặn; lời dặn và schema đầu ra |
| `backend/app/agent/graph.py` | Điểm nối `Services.extractor` trong node `analyze` (mặc định tắt) và `extraction_log` |
| `contracts/extraction/` | Schema xuất từ Pydantic và bộ ca dev `cases.dev.v1.json` (32 ca) |
| `research/extraction/evaluate_extraction.py` | Script đo trên bộ ca dev |
| `research/llm_support.py` | Phần chung của các script có gọi LLM: đọc `.env`, xin xác nhận, thống kê chi phí |
| `tests/test_extraction.py` | 218 test, không gọi mạng |

Phiên bản ghi vào log: `extractor_version = extractor-0.1.0` (luật và chốt chặn), `prompt_version = extraction-prompt-0.1.0` (lời dặn và schema; chỉ có khi đã gọi LLM), `grammar_version = g2-v1`.

## 3. Hợp đồng extraction → validator

`ExtractionResult`:

| Trường | Ý nghĩa |
|---|---|
| `status` | `extracted` hoặc `needs_clarification` |
| `method` | `rules` (không gọi LLM) hoặc `llm` (LLM chọn đoạn, luật kiểm tra lại) |
| `steps[]` | Theo thứ tự: `role` (`restated_problem` hoặc `step`), `index` (số bước từ 1; null với dòng chép đề), `line` (dòng của bài nộp), `source` (đúng đoạn học sinh viết), `normalized` (dạng chuẩn hóa không khoảng trắng) |
| `reasons[]` | Lý do hỏi lại (§4); chỉ có khi `needs_clarification` |

Quy tắc:
- `needs_clarification` không mang bước nào: validator không bao giờ nhận bài làm dở.
- Dòng chép lại đề (trùng nguyên một phương trình trong đề) được giữ với `role = restated_problem`, không đánh số (FR04-AC1). Chỉ dòng đầu tiên mới có thể là dòng chép đề.
- `normalized` chỉ khác `source` ở phép chuẩn hóa ký tự tất định của grammar: bỏ khoảng trắng; `−`, `–` thành `-`; `×`, `·` thành `*`; `÷` thành `/`; `X` thành `x`. Không có số hay phép toán nào được thêm, bớt hay sửa. Test `test_normalized_differs_from_source_only_by_deterministic_mapping` kiểm tra điều này trên mọi ca.
- `graded_lines()` trả các bước giải ở dạng chuẩn hóa: đó là phần đưa cho analyzer.

`ExtractionRecord` là một dòng trong `extraction_log` của phiên: `turn_id`, các phiên bản, kết quả, `usage` (token, latency, chi phí; null khi không gọi LLM) và `llm_output` (đúng chuỗi model trả về, trước chốt chặn). Giữ `llm_output` để khi đọc lại phân biệt được model cắt sai với chốt chặn từ chối nhầm (NFR-04). Dùng chung kiểu `LLMUsage` với Agent.

## 4. Khi nào hỏi lại

| Lý do | Ai phát hiện | Ví dụ |
|---|---|---|
| `empty`, `no_equation`, `no_steps` | Luật | Bài rỗng; chỉ ghi "8"; chỉ chép lại đề |
| `decimal_comma` | Luật | `x = 6,5` (grammar: không tự biến thành 65 hay 6.5) |
| `ambiguous_fraction` | Luật | `1/2x` (là `(1/2)x` hay `1/(2x)`?) |
| `chained_equals` | Luật hoặc LLM | `2x = 10 + 6 = 16` |
| `syntax`, `too_many_steps`, `step_too_long` | Luật | Sai cú pháp; quá 12 bước hoặc 160 ký tự |
| `mixed_text` | Luật, khi không bật LLM | Chữ lẫn công thức |
| `math_in_words`, `unsupported_notation`, `unreadable` | LLM | "hai x bằng mười sáu"; `x^2`, ẩn `y`, dấu `:` |
| `not_verbatim`, `partial_span`, `unextracted_math` | Chốt chặn | LLM sửa, cắt bớt hoặc bỏ sót bài làm (§5) |
| `llm_unavailable`, `llm_invalid_output` | Hệ thống | Timeout, lỗi mạng, model từ chối, JSON hỏng |

Khi phải hỏi lại, node `analyze` trả `needs_clarification` cho Agent, không gọi analyzer và không ghi BKT. Agent chọn `clarify / resolve_input` (luật G01).

## 5. Chốt chặn: LLM không được sửa bài làm

LLM chỉ trả **danh sách đoạn** (`spans`) được chép từ bài làm. Dạng chuẩn hóa được luật tính lại từ chính các token của bài làm, không lấy từ chữ LLM viết. Trước đó, `guards.py` kiểm tra:

| Chặn | Ví dụ |
|---|---|
| Đoạn không có trong bài làm, hoặc sai thứ tự (`not_verbatim`) | Học sinh viết `2x - 3 = 10`, LLM trả `2x - 6 = 10` |
| Đoạn chỉ là một phần biểu thức (`partial_span`) | Lấy `x = 16` từ `2x = 16`; `x = 6` từ `x = 6,5`; `x = 8` từ `x = 8^2`, `√x = 8`, `x = 8y`, `x = 8 : 2`, `x = 8²`, `x = 8 π`, `x = 8 sin(2)`, `x = 8 (sin 2)`, `x = 8!`, `x = 8°` |
| Còn ký hiệu toán nằm ngoài mọi đoạn (`unextracted_math`) | LLM bỏ qua bước sai để bài trông đúng; bỏ qua `x^2`, `√64`, `3!` đứng ngoài phương trình |

Ranh giới đoạn và phần nằm ngoài đoạn được xét theo **mọi ký hiệu toán**, kể cả ký hiệu grammar chưa hỗ trợ (`^`, `√`, `:`, `%`, `±`, `|`, số mũ `²`, chữ cái đứng riêng như `y`): ký hiệu chưa hỗ trợ vẫn là toán học sinh đã viết, bỏ nó đi là đổi bài làm. Ký hiệu được nhận theo **nội dung**, không theo loại token: chữ Hy Lạp (`π`, `α`), tên hàm và hằng (`sin`, `cos`, `log`, `ln`, `sqrt`, `pi`...) và mọi chữ dính liền dấu `(` (`f(2)`) đều là toán dù bị tách thành token chữ. Ngoặc sau phương trình chỉ là chú thích khi bên trong hoàn toàn là lời văn: `(chuyển vế)`, `(bước 2)` thì được; `(sin 2)`, `(2)`, `(π)` thì không. Bản đầu chỉ xét ký hiệu thuộc grammar, bản sau chỉ xét theo loại token, nên để lọt các ca trên (hai lần review 14/11).

**Dấu câu dùng danh sách trắng, không dùng danh sách đen.** Ngay sát một biểu thức chỉ được phép các dấu chắc chắn là dấu câu: `.`, `,`, `?`, `…` và ngoặc kép (cùng `!` khi đứng trước biểu thức, cách một khoảng trắng, như "đúng rồi! x = 8"). Mọi dấu khác (`!`, `°`, `&`, `#`, `~`...) đứng sát biểu thức có thể là ký hiệu (giai thừa, độ...): không phân biệt được với dấu câu thì coi là toán và hỏi lại. Ở phần ngoài đoạn, dấu đứng ngay sau số, ẩn hay ngoặc đóng (`3!`, `30°`) cũng là toán. Bản trước dùng danh sách ký hiệu nên `x = 8!` bị tách thành `x=8` (review lần ba, 14/11); test `test_any_punctuation_glued_after_an_expression_blocks_the_span` quét mọi dấu ASCII để lỗi kiểu này không lặp lại.

**Phép toán viết bằng lời sát phương trình** cũng là phần còn lại của biểu thức: từ chỉ phép toán (`nhân`, `chia`, `cộng`, `trừ`, `mũ`, `căn`, `lần`, `phần`, `bình phương`, `lũy thừa`..., có dấu và không dấu) đứng ngay trước hoặc ngay sau đoạn (`x = 8 nhân 2`, `căn x = 8`, `x = 8, nhân 2`) thì đoạn đó bị chặn. Cùng từ đó nằm xa phương trình là lời văn và không bị chặn (`em nhân 2 vào ngoặc rồi được x = 8`).

So khớp theo token, bỏ qua khoảng trắng, và số là một khối, nên LLM không thể ghép `6 5` thành `65`. Số thứ tự đầu dòng (`1)`, `2.`), nhãn bằng chữ ("Bước 1:", "Đáp số:", "câu a:"; dấu `:` dính liền nhãn, sau đó có khoảng trắng; số hay chữ cái đứng riêng chỉ là nhãn khi đứng sau một chữ lời văn) và chú thích trong ngoặc ("(chuyển vế)") không bị coi là phần biểu thức. Nếu LLM gộp hai bước nối bằng mũi tên vào một đoạn, hệ thống tự tách ra.

Test `test_any_altered_or_dropped_span_is_blocked` lấy mọi ca LLM tách được, đổi một chữ số hoặc bỏ một đoạn trong đầu ra của LLM, và kiểm tra lần nào cũng bị chặn.

## 6. Gọi model

Dùng chung client OpenAI với Agent (`app/llm/client.py`): `gpt-4o-mini`, structured output strict, không thử lại, timeout `AGENT_LLM_TIMEOUT_SECONDS`, `store = false`. Chỉ gửi **đề bài công khai và bài làm**, không gửi định danh học sinh. Lời dặn nói rõ đề và bài làm là dữ liệu, không phải chỉ dẫn; ca `EX-26` có lời nhắn cố chèn lệnh.

Lời dặn khoảng 450 token, input của một ca khoảng 20–35 token (ước lượng 4 ký tự/token; tiếng Việt có thể tốn hơn, chưa đo thật). Lời dặn ngắn hơn ngưỡng 1.024 token nên provider không cache.

## 7. Nối vào LangGraph

`Services(extractor=StepExtractor(client))` bật extraction. Mặc định `extractor = None`: bài làm đi thẳng tới analyzer như trước.

Extraction là node riêng `extract`, đứng ngay trước `analyze`. LangGraph lưu checkpoint sau mỗi node, nên kết quả và chi phí lần gọi LLM được lưu trước khi analyzer chạy. Analyzer lỗi rồi gửi lại đúng request thì graph chạy tiếp từ `analyze` với kết quả đã lưu: không gọi LLM lần hai, log không mất lần gọi đầu (bản đầu để chung một node nên mất cả hai, review 14/11).

- Chỉ áp cho concept grammar phủ (`G2_V1_CONCEPTS = {"E02"}`); bài của concept khác đi thẳng tới analyzer.
- Tách được thì analyzer chấm `graded_lines()`, và `StudentState.latest_submission` lưu đúng các dòng đó, nên Agent thấy đúng bài đã chấm.
- Mỗi lần extraction chạy được ghi vào `extraction_log` (`TutorEngine.extractions()`).
- `WORKFLOW_VERSION` lên `tutor-graph-0.4.0`.

## 8. Chạy đánh giá

```powershell
# Chỉ luật (bỏ qua ca cần LLM), không gọi API
.\.venv\Scripts\python.exe research/extraction/evaluate_extraction.py
# Đường LLM với LLM giả trả đúng "oracle" của từng ca; không gọi API
.\.venv\Scripts\python.exe research/extraction/evaluate_extraction.py --llm fake
# GỌI API THẬT (tốn phí): chỉ gọi cho các ca cần LLM (13/32)
.\.venv\Scripts\python.exe research/extraction/evaluate_extraction.py --llm openai --yes --out data/extraction_runs/dev-001.jsonl
```

| Chỉ số | Ý nghĩa |
|---|---|
| `exact` | Khớp hoàn toàn: trạng thái, các bước, dòng chép đề, lý do |
| `by_rules` | Số ca xử lý bằng luật, không tốn lần gọi model |
| `clarification_precision` / `recall` | Trong các lần hỏi lại, bao nhiêu lần đúng; trong các ca cần hỏi lại, bắt được bao nhiêu |
| `silent_changes` | **Ca lọt:** hệ thống đưa sang chấm các bước khác đáp án của ca, hoặc lẽ ra phải hỏi lại. Đây là lỗi nguy hiểm nhất (sai kết quả chấm và BKT), và chỉ đo được trên ca có đáp án như bộ này |
| `fidelity_blocks` | Số lần chốt chặn đã chặn được LLM định sửa, cắt hoặc bỏ sót bài làm. Cho biết model hay làm sai đến đâu; **không** đo được ca lọt, vì ca lọt thì không bị chặn |
| `llm_calls`, `api_ms`, token, `cost_usd_known` | Vận hành, cùng cách tính với Agent |

Mỗi dòng kết quả (`--out`) giữ đầu ra thô của model (`llm_output`) và cấu hình chạy (`run`: phiên bản extractor/prompt/grammar, chế độ LLM, model, file ca), để tái lập và phân tích lỗi (NFR-04).

Kết quả hiện có: chỉ luật 19/19 khớp; LLM giả 32/32 khớp, `silent_changes = 0`. Đây là bộ dev tự soạn; LLM giả chỉ chứng minh đường xử lý chạy đúng, **không nói gì về chất lượng của model thật**.

## 9. Cần chốt với nhóm

**Member 1:**
1. Validator nhận chuỗi `normalized` theo `g2-v1`, hay cần cây biểu thức?
2. Extraction chạy trước mọi bài nộp (như hiện tại: luật xử lý bài sạch, không tốn API), hay chỉ khi parser của validator lỗi?
3. Dòng chép đề có bị loại khỏi đánh số như hiện tại không? Cách nhận dòng chép đề: trùng nguyên một phương trình trong đề.
4. Mở rộng grammar cho các concept khác ra sao? Hiện extraction chỉ áp cho E02.
5. Hai bổ sung so với đặc tả `g2-v1`: chấp nhận `X` hoa, và coi mũi tên hay dấu `;` là ngắt giữa hai bước. Đặc tả hiện ghi "V1 chưa nhận dấu mũi tên"; nếu Member 1 không đồng ý thì chỉ cần bỏ phần này.

**Member 2:**
1. UI nhập bài theo từng dòng (`steps`) hay gõ tự do (`message`)? Extraction nhận được cả hai.
2. Khi extraction trả `needs_clarification`, UI có muốn hiển thị lý do cụ thể ("viết 6.5 thay cho 6,5") không?

## 10. Giới hạn

| Giới hạn | Ảnh hưởng | Khi nào xử lý |
|---|---|---|
| Chưa chạy với model thật | Chưa biết model có hay sửa bài làm không (`fidelity_blocks`), có ca nào lọt không (`silent_changes`), tỷ lệ hỏi lại thừa, latency | Khi được phép dùng API |
| Chỉ phủ grammar `g2-v1` (E02) | 39 concept còn lại chưa có extraction | Khi Member 1 mở rộng grammar |
| Chưa xác minh câu trả lời cho câu hỏi kiểm tra prerequisite | `probe_checker` vẫn là stub trả "unverified" | Cần câu hỏi có đáp án (Member 2) và so sánh tương đương toán (Member 1) |
| Toán viết bằng lời **không** đứng sát phương trình ("x = 8 rồi nhân thêm 2") chưa bị luật chặn | Phần "nhân thêm 2" có thể bị bỏ; chỉ lời dặn LLM (`math_in_words`) ngăn. Luật không phân biệt được với lời văn thường ("em nhân 2 vào ngoặc rồi được...") | Đo bằng `silent_changes` trên bộ ca có đáp án và đọc lại `llm_output` của ca thật; thêm ca vào bộ dev khi gặp |
| Danh sách tên hàm (`MATH_WORDS`) là danh sách đóng | Tên hàm lạ viết cách dấu ngoặc ("x = 8 arccot 2") có thể bị coi là lời văn | Bổ sung khi gặp; tên hàm dính liền `(` thì đã luôn bị chặn |
| Toán viết bằng chữ chỉ được hỏi lại, không được chuyển thành công thức | Học sinh phải viết lại | Cân nhắc sau khi có số liệu thật; chuyển chữ thành công thức là diễn giải, phải có cách kiểm tra |
| Bộ ca dev nhỏ (32 ca) và tự soạn | Không dùng làm kết quả báo cáo | Mở rộng khi có bài làm thật từ pilot |

## 11. Lệnh

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_extraction.py -q
.\.venv\Scripts\python.exe research/extraction/evaluate_extraction.py --llm fake
.\.venv\Scripts\python.exe scripts/exports/export_agent_contracts.py --check
```
