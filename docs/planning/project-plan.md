# KẾ HOẠCH CHI TIẾT ĐỀ TÀI VIN-02

## Tên đề tài

**Nghiên cứu và xây dựng trợ lý AI dạy học Toán theo phương pháp Socratic thích ứng sử dụng AI Agent**

### Ràng buộc đã đăng ký

- Thời gian: **12 tuần**, nhóm **3 người**.
- Đối tượng: học sinh **THCS và THPT**; nội dung: **Toán số, Đại số và Hàm số**, không bao gồm Hình học.
- Phạm vi: **30–50 khái niệm lõi**. Kế hoạch dùng **40 khái niệm** làm danh mục mục tiêu để phân công và nghiệm thu.
- Giữ đủ **Student Model, BKT, RAG, Knowledge Graph, AI Agent và LangGraph**.
- Đánh giá ba trục: **phát hiện misconception, theo dõi trạng thái kiến thức và chất lượng chiến lược Socratic thích ứng**.
- Prototype ít concept ở giai đoạn đầu là mốc tích hợp, không thay thế phạm vi sản phẩm cuối.

---

## 1. Tổng quan đề tài

Đề tài xây dựng trợ lý AI hỗ trợ học Toán theo phương pháp Socratic. Hệ thống phân tích câu trả lời và bước giải, xác minh lỗi, đề xuất giả thuyết misconception, theo dõi kiến thức theo kỹ năng và chọn câu hỏi gợi mở phù hợp.

Hệ thống không tự đưa lời giải hoàn chỉnh của bài đang làm. Khi học sinh mắc kẹt, hệ thống tăng mức hỗ trợ, giải thích khái niệm qua ví dụ khác hoặc quay lại prerequisite, rồi để học sinh tiếp tục giải.

```text
Học sinh trả lời
    -> Phân tích và kiểm tra bước giải
    -> Đề xuất/chẩn đoán misconception
    -> Tạo observation; cập nhật BKT nếu đủ điều kiện
    -> Agent đọc Student Model, tra Knowledge Graph và RAG khi cần
    -> Chọn chiến lược trong giới hạn pedagogical policy
    -> Sinh và kiểm tra câu hỏi/gợi ý
    -> Lưu trạng thái, chờ học sinh trả lời
```

## 2. Vì sao cần làm đề tài này?

Khả năng giải đúng bài Toán chưa đủ để bảo đảm một hệ thống dạy phù hợp với từng học sinh. Với bài `2(x - 3) = 10`, việc trả ngay `x = 8` không cho biết học sinh có hiểu tính phân phối, có đang thiếu kiến thức nền hay chỉ mắc lỗi tính toán.

Đề tài xây dựng **Student Model tường minh, lưu được qua các phiên** và cơ chế ra quyết định dựa trên mô hình này. Giá trị cần kiểm chứng là chất lượng chẩn đoán và can thiệp, không chỉ khả năng sinh câu hỏi nghe giống giáo viên.

## 3. Pain points chính

| Vấn đề | Cơ chế đề xuất | Bằng chứng cần đo |
|---|---|---|
| Học sinh nhận đáp án quá sớm | Socratic policy và kiểm tra mức tiết lộ | Tỷ lệ tiết lộ đáp án |
| Không biết sai ở đâu | Phân tích từng chuyển bước | Độ chính xác bước sai đầu tiên |
| Không phân biệt sơ suất và misconception | Giả thuyết lỗi và câu hỏi chẩn đoán | F1, sai chẩn đoán, trường hợp chưa đủ bằng chứng |
| Khác biệt trình độ | Student Model và BKT | Dự đoán lượt tiếp theo và mức phù hợp của can thiệp |
| Thiếu prerequisite | Graph kết hợp bằng chứng học sinh | Chất lượng chọn prerequisite |
| Nội dung không bám kiến thức đã duyệt | RAG và validator | Chất lượng truy xuất, tính đúng toán học |
| Hỏi lặp hoặc hỗ trợ quá lâu | Hint ladder và giới hạn vòng lặp | Lặp câu hỏi, số lượt không tiến triển |
| Khó theo dõi tiến bộ | Lịch sử observation và learning report | Tính nhất quán giữa log, mastery và báo cáo |

Không mặc định chatbot khác không có khả năng cá nhân hóa, hoặc RAG loại bỏ hoàn toàn hallucination. Các phép so sánh phải dùng baseline được mô tả cụ thể.

## 4. Đối tượng sử dụng

**Học sinh là người dùng chính:** nhập bài/bước giải, nhận câu hỏi gợi mở, luyện bài phù hợp, xem tiến trình và tiếp tục phiên trước.

**Giáo viên:** xem lịch sử lỗi, mức kiến thức ước lượng và nội dung cần ôn. Dashboard ở mức phục vụ quan sát và thực nghiệm; không mở rộng thành hệ thống quản lý trường/lớp.

## 5. Phạm vi đề tài

### 5.1. Danh mục mục tiêu: 40 khái niệm

| Nhóm | Mã | Danh mục theo thứ tự mã |
|---|---|---|
| Toán số | N01–N10 | Cộng trừ số có dấu; nhân chia số có dấu; thứ tự phép tính; phân số tương đương và rút gọn; quy đồng và so sánh phân số; cộng trừ phân số; nhân chia phân số; chuyển đổi phân số–thập phân–phần trăm; lũy thừa với số mũ nguyên; căn bậc hai số học |
| Biểu thức đại số | A01–A10 | Thay giá trị vào biểu thức; tính phân phối; thu gọn hạng tử đồng dạng; nhân đơn thức và đa thức; bình phương một tổng/hiệu; hiệu hai bình phương; phân tích nhân tử bằng đặt nhân tử chung; phân tích nhân tử bằng hằng đẳng thức/nhóm; rút gọn phân thức và điều kiện xác định; cộng trừ nhân chia phân thức |
| Phương trình và bất phương trình | E01–E10 | Phép biến đổi tương đương và điều kiện; phương trình bậc nhất một ẩn; lập phương trình từ bài toán bằng lời; phương trình tích; phương trình chứa ẩn ở mẫu; phương trình bậc hai và biệt thức; hệ thức Viète cơ bản; giải hệ bậc nhất bằng thế; giải hệ bậc nhất bằng cộng đại số; bất phương trình bậc nhất và quy tắc đổi chiều |
| Hàm số, mũ và logarit | F01–F10 | Khái niệm hàm số và giá trị hàm; tập xác định; hệ số góc và giá trị ban đầu của hàm bậc nhất; nghiệm và dấu hàm bậc nhất; đỉnh và trục đối xứng của hàm bậc hai; khoảng đồng biến/nghịch biến của hàm bậc hai; dấu tam thức bậc hai và bất phương trình bậc hai; hàm số mũ và quy tắc lũy thừa với điều kiện áp dụng; logarit và quy tắc logarit; phương trình mũ/logarit cơ bản |

Tuần 1–2, đối chiếu **chương trình môn Toán** và nhờ người có chuyên môn rà soát tên, lớp, yêu cầu cần đạt, biên giới từng concept. Bảng là danh mục triển khai đề xuất, chưa phải kết quả đối chiếu chương trình. Có thể thay concept trùng lặp trong cùng miền khi chốt, nhưng phải giữ **30–50 concept, đủ ba mảng và cả THCS–THPT**. Giới hạn/đạo hàm cơ bản có thể bổ sung trong giới hạn 50 concept sau khi hoàn thành danh mục đã chốt.

### 5.2. Độ phủ thực chất

- **Concept** là đơn vị nội dung trên graph; **skill** là hành vi quan sát được để cập nhật BKT. Ban đầu ưu tiên một skill chính/concept; tách thêm khi có bài và bằng chứng phù hợp.
- Một bài liên quan nhiều concept nhưng một observation BKT chỉ đo một skill xác định. Không chấm sai tất cả prerequisite từ một đáp án sai.
- Mỗi concept phải có mục tiêu, prerequisite đã duyệt, ít nhất **6 bài thuộc ít nhất 3 mẫu bài**, ví dụ giải, lỗi thường gặp, hint ladder và ca test. Node chỉ có tên chưa được tính là hoàn thành.
- Dạng bài hỗ trợ là các dạng cơ bản được mô tả cho từng concept, không phải mọi bài nâng cao của THCS–THPT. Input ngoài dạng hỗ trợ phải có phản hồi rõ và không tự chấm sai.
- Input chính: văn bản, biểu thức toán có cấu trúc và các bước giải. Với hàm số, hỗ trợ công thức, bảng giá trị và đồ thị sinh từ dữ liệu khi cần; không yêu cầu đọc ảnh đề hoặc chữ viết tay.
- Không có Hình học. Không biến nhận dạng ảnh, giọng nói, mobile app hoặc fine-tuning thành điều kiện hoàn thành.

## 6. Workflow minh họa

Bài: `2(x - 3) = 10`. Học sinh viết:

```text
2x - 3 = 10
2x = 13
x = 6.5
```

Validator xác nhận bước đầu sai: `2(x - 3)` không bằng `2x - 3`. Hai phép biến đổi sau hợp lệ theo phương trình học sinh đang có; không tự xem chúng là hai lỗi mới.

Analyzer đề xuất `M_DIST_01: chỉ phân phối cho số hạng đầu` với trạng thái **suspected**. Agent kết hợp lịch sử, mastery và prerequisite để hỏi:

> Nếu viết hai nhóm (x - 3) thành (x - 3) + (x - 3), em thấy phần -3 xuất hiện bao nhiêu lần?

Học sinh trả lời rồi tự sửa thành `2x - 6`. Kết quả này được lưu là **làm đúng sau hỗ trợ**, không coi hai lượt trả lời sau hint là hai lần làm đúng độc lập để tăng BKT.

Bước sai ban đầu tạo tối đa một observation hợp lệ cho skill tính phân phối. Agent kiểm tra chuyển giao bằng bài mới chưa kèm hint, chẳng hạn khai triển một biểu thức có cấu trúc khác như `-2(3y + 4)`, nếu độ khó phù hợp. Dùng bài chỉ thay số ngay sau hướng dẫn phải ghi rõ là luyện tập gần, không coi là bằng chứng chuyển giao mạnh.

Mastery cập nhật theo observation và bộ tham số đã lưu; không gán sẵn mức tăng. Agent quay lại bài phương trình khi bằng chứng cho thấy phù hợp và ghi lý do quyết định.

## 7. Kiến trúc hệ thống

```text
Student UI -> API -> LangGraph: nạp session và Student Model
                         |
                         v
           Parser -> Mathematical Validator -> Error Analyzer
                         |
                         v
           Observation Builder -> BKT nếu hợp lệ -> lưu state
                         |
                         v
            AI Agent đọc state và chọn công cụ/hành động
                |                  |                    |
                v                  v                    v
          Knowledge Graph     RAG trên KB        Problem Selector
                +------------------+--------------------+
                                   |
                                   v
                  Pedagogical Policy kiểm tra hành động
                                   |
                                   v
                 Sinh câu hỏi -> kiểm tra toán/mức tiết lộ
                                   |
                                   v
                  Checkpoint -> phản hồi -> chờ học sinh
```

LangGraph điều phối toàn bộ lượt xử lý. Mỗi lượt kết thúc bằng checkpoint, chờ input tiếp theo; không để LLM tự sinh câu trả lời thay học sinh. Toàn bộ log liên kết bằng `session_id`, `turn_id`, `opportunity_id` và phiên bản state.

## 8. Các module chính

### 8.1. Student Interface

Chat có vùng nhập bước giải, render công thức, bài hiện tại, mức hỗ trợ, tiến trình skill và learning report. Có trạng thái đang xử lý, input thiếu, không xác minh được, mất kết nối và tiếp tục phiên.

Hiển thị mastery là **ước lượng**, kèm số quan sát độc lập và trạng thái “chưa đủ dữ liệu”. Không trình bày 82% như điểm thi hay xác suất chắc chắn học sinh hiểu 82% nội dung. Retry không sinh thêm observation.

### 8.2. Answer / Step Analyzer

Kết hợp **rule-based checking + SymPy/kiểm tra toán có điều kiện + LLM structured extraction + misconception KB**.

Ví dụ output cho bước sai ở mục 6:

```json
{
  "assessment_status": "verified_incorrect",
  "first_error_step": 1,
  "primary_skill_id": "A02",
  "error_family": "distribution_error",
  "misconception_candidate": "M_DIST_01",
  "diagnosis_status": "suspected",
  "evidence": "2(x - 3) was transformed into 2x - 3",
  "verification_method": "symbolic_and_rule",
  "needs_clarification": false
}
```

Bước học sinh đánh số từ 1, không tính đề bài. Hợp đồng output và quy tắc:

- Tách **xác minh tính đúng** khỏi **chẩn đoán nguyên nhân**. Một lần sai chưa chứng minh misconception bền vững.
- Chấp nhận nhiều cách giải. `2(x-3)=10 -> x-3=5` hợp lệ dù khác lời giải mẫu.
- Kiểm tra miền xác định, biến đổi tương đương và tập nghiệm theo dạng bài; lưu điều kiện phát sinh. Thử số giúp tìm phản ví dụ, không phải chứng minh tương đương.
- Gán skill từ cấu trúc bài/bước đã duyệt rồi đối chiếu hành vi. Không tự phạt các skill ở bước sau chỉ do lỗi kéo theo.
- Cho phép `verified_correct`, `verified_incorrect`, `unverified`, `needs_clarification`. Misconception có thể là `null`, `unknown` hoặc `other`; nghi ngờ thì hỏi chẩn đoán.
- Chỉ có đáp án cuối: chấm kết quả khi đủ điều kiện, không khẳng định bước sai. Bài nhiều kỹ năng cần hỏi thêm trước khi gán observation.
- Pydantic bảo đảm cấu trúc, không bảo đảm nội dung đúng. Confidence do LLM tự sinh không được coi là xác suất đã hiệu chỉnh.
- Parser giới hạn cú pháp, ký hiệu, độ dài và thời gian tính. Không thực thi trực tiếp văn bản người dùng bằng `eval` hoặc parser không kiểm soát.
- Với câu trả lời bằng lời chưa được rule/đáp án duyệt xác minh, lưu nhận xét của LLM dưới trạng thái chưa xác minh; không tự đưa vào BKT chuẩn.

### 8.3. Student Model + Bayesian Knowledge Tracing

Mỗi skill lưu `P(L)`, số observation độc lập, lịch sử hỗ trợ, giả thuyết lỗi, timestamp và `parameter_version`. `P(L)` là xác suất trạng thái biết kỹ năng **theo mô hình**, khác với xác suất trả lời đúng và mức hiểu biết đo trực tiếp.

Tham số BKT: `P(L0)` là prior, `P(T)` là xác suất chuyển sang biết sau một cơ hội học, `P(G)` là đoán đúng khi chưa biết, `P(S)` là sai khi đã biết. Ưu tiên dùng thư viện pyBKT cho fit/benchmark, kiểm thử công thức online đối chiếu kết quả thư viện.

**Đơn vị quan sát:** một learning opportunity là bài/bước chẩn đoán có ID, đo một skill xác định. Turn hội thoại không đồng nhất với opportunity.

| Tình huống | Xử lý |
|---|---|
| Câu trả lời đầu tiên có thể chấm, làm độc lập, skill rõ | Cập nhật BKT một lần |
| Sửa sau hint, xem lời giải hoặc lặp cùng opportunity | Lưu kết quả có hỗ trợ, không thêm observation chuẩn |
| Xin hint, chat xã giao, không chấm được hoặc input mơ hồ | Không cập nhật đúng/sai |
| Đáp án cuối của bài nhiều skill, chưa có bằng chứng quy lỗi | Hỏi chẩn đoán; không cập nhật đồng loạt |
| Retry cùng request | Khóa idempotency, không cập nhật lần hai |

“Độc lập” nghĩa là chưa nhận trợ giúp liên quan đến opportunity/skill đang đo; cần lưu cả nguồn bài và mức tương tự với bài vừa được hướng dẫn. Quy tắc bảo thủ này giữ observation nhất quán nhưng BKT chuẩn chưa mô hình hóa đầy đủ việc học trong các lượt có hỗ trợ. Các lượt đó vẫn được lưu và dùng trong policy; kiểm tra bằng opportunity độc lập tiếp theo. Biến thể BKT có hỗ trợ chỉ triển khai bổ sung khi có dữ liệu để kiểm chứng.

Với `p = P(L)` trước observation, `G = P(G)`, `S = P(S)`, `T = P(T)`:

```text
P(correct_next) = p * (1 - S) + (1 - p) * G

Nếu đúng: posterior = p * (1 - S) / P(correct_next)
Nếu sai:  posterior = p * S / (p * S + (1 - p) * (1 - G))

p_next = posterior + (1 - posterior) * T
```

Lưu dự đoán **trước khi dùng đáp án**, sau đó cập nhật posterior và bước chuyển học tập. Không cộng mastery theo số lần chat. Kiểm soát tham số suy biến, mẫu số bằng 0, quan hệ `G < 1-S`; ghi cấu hình và ràng buộc khi fit. BKT chuẩn giả định không quên; hạn chế về khoảng cách thời gian giữa các phiên phải được nêu trong báo cáo.

### 8.4. Knowledge Graph

Neo4j lưu concept và quan hệ. Node có ID, tên tiếng Việt, mô tả, lớp, mục tiêu học, skill liên kết, nguồn và phiên bản. Cạnh chính:

- `PREREQUISITE_OF`: A là kiến thức cần trước B; chiều A -> B.
- `RELATED_TO`: liên quan, không có nghĩa phải học trước.
- `PART_OF`: thành phần của một chủ đề.

Các cạnh prerequisite bắt buộc tạo thành DAG; kiểm tra chu trình, cạnh đảo chiều và prerequisite thiếu. Mỗi cạnh có căn cứ và người duyệt. Không dùng một chuỗi minh họa như cấu trúc đầy đủ của chương trình.

Graph trả prerequisite ứng viên; Student Model và câu hỏi chẩn đoán cung cấp bằng chứng học sinh thiếu gì. Chọn concept tiếp theo là quyết định động, không cần cạnh `NEXT_CONCEPT` cố định. Backtrack 1–2 tầng, giữ ngăn xếp để quay lại bài đang học.

### 8.5. RAG

KB có giải thích, ví dụ, bài tập, lời giải chuẩn, misconception và hint. Mỗi chunk lưu `content_id`, concept/skill, loại nội dung, lớp, độ khó, nguồn, phiên bản, mức tiết lộ và trạng thái duyệt.

Truy xuất theo trình tự: xác định mục tiêu -> lọc metadata -> xếp hạng ngữ nghĩa trong nội dung hợp lệ. Với ID đã biết thì lấy trực tiếp, không bắt buộc vector search. So sánh với baseline chỉ lọc metadata để đánh giá giá trị retrieval trên KB nhỏ.

Lời giải đầy đủ phục vụ validator; node sinh hint chỉ nhận phần được phép theo mức hỗ trợ. LLM vẫn có thể tự suy ra đáp án nên cần kiểm tra đầu ra. Khi không có tài liệu phù hợp, dùng template đã duyệt hoặc hỏi làm rõ; không gắn nguồn không được truy xuất.

### 8.6. AI Agent / LangGraph

**LangGraph điều phối, Agent ra quyết định sư phạm trong tập hành động giới hạn.** Agent đọc state để quyết định cần tra prerequisite, lấy ví dụ, hỏi chẩn đoán hay chọn bài tiếp theo. Không tự do thay đổi BKT hoặc dữ liệu người học.

State gồm bài hiện tại, câu trả lời, `turn_id/opportunity_id/state_version`, skill, assessment, observation eligibility, mastery trước/sau, evidence count, misconception, retrieved content IDs, lịch sử, hint level, return stack, tool budget và strategy.

Hành động: `clarify`, `diagnose`, `minimal_hint`, `conceptual_question`, `backtrack`, `scaffold`, `check_transfer`, `next_problem`, `end_session`.

Output quyết định có action, skill mục tiêu, ID bằng chứng, mức hint và lý do ngắn có thể kiểm tra. Không yêu cầu lưu chuỗi suy nghĩ nội bộ. Policy gate kiểm tra action và mức hỗ trợ; validator kiểm tra phản hồi trước khi gửi.

Giới hạn khởi đầu: tối đa 3 tool calls cho ra quyết định và 1 lần sinh lại phản hồi mỗi lượt; đo trên dev rồi chốt. Timeout hoặc lỗi schema chuyển sang policy luật và template, có log fallback. Mỗi lượt checkpoint rồi chờ input; cập nhật mastery là node xác định, không phải quyền tùy ý của Agent.

## 9. Pedagogical Policy

| Bằng chứng/trạng thái | Hành động ưu tiên |
|---|---|
| Chưa hiểu đề hoặc input chưa rõ | Clarify, chưa cập nhật BKT |
| Lỗi số học đơn lẻ, lịch sử tốt | Nhắc kiểm tra thao tác |
| Nghi lỗi concept nhưng bằng chứng còn ít | Câu hỏi chẩn đoán |
| Lỗi concept có bằng chứng lặp lại | Câu hỏi khái niệm hoặc scaffold |
| Prerequisite có dấu hiệu yếu | Kiểm tra prerequisite rồi backtrack nếu cần |
| Gần đúng | Tạo cơ hội tự sửa |
| Không tiến triển hoặc xin thêm hỗ trợ | Tăng mức hint |
| Làm đúng sau hỗ trợ | Bài kiểm tra độc lập |
| Đủ bằng chứng sẵn sàng | Tăng độ khó/chuyển concept theo graph |

Thứ tự ưu tiên: làm rõ -> xác minh/chẩn đoán -> hỗ trợ -> kiểm tra chuyển giao -> chuyển bài. Mastery cao không được ghi đè bằng chứng lỗi mới; mastery thấp không tự động buộc backtrack nếu học sinh đang làm đúng.

Hint ladder:

```text
0 -> Câu hỏi gợi mở/chẩn đoán
1 -> Nhắc kiến thức hoặc đề nghị tự kiểm tra
2 -> Gợi ý cụ thể hơn, để học sinh tự thực hiện
3 -> Chia nhỏ thao tác hoặc minh họa một phần bằng bài khác
4 -> Giải thích khái niệm với ví dụ khác, rồi kiểm tra độc lập
```

Tăng mức theo tiến triển và nhu cầu hỗ trợ, không máy móc theo số tin nhắn. Không tự đưa nghiệm/lời giải hoàn chỉnh của bài đang làm. Nếu thao tác được hỏi chính là đáp án cuối, dùng ví dụ khác để giải thích.

## 10. Điều kiện dừng Socratic Loop

Cấu hình ban đầu để **xem xét** chuyển concept:

- `P(L) >= 0.8`, ít nhất 3 observations độc lập;
- 2 bài độc lập gần nhất đúng, thuộc mẫu bài khác nhau;
- không còn giả thuyết lỗi quan trọng chưa kiểm tra và prerequisite phù hợp.

Đây là heuristic cần thử trên dev, không là ngưỡng thành thạo có giá trị phổ quát. Nếu tăng tới hint 3 mà vẫn mắc kẹt, minh họa bằng ví dụ khác hoặc kiểm tra prerequisite. Sau 6 lượt hỗ trợ trên cùng nút mắc kẹt, dừng nhánh hiện tại, chuyển cách hỗ trợ hoặc cho học sinh kết thúc.

Phân biệt dừng bài, kết thúc phiên và chuyển concept. Backtrack tối đa 2 tầng, lưu concept đã ghé để tránh vòng lặp. Học sinh tạm dừng không được ghi thành câu trả lời sai. Chốt các ngưỡng trước test chính thức.

---

## 11. Dataset cần chuẩn bị

### 11.1. FoundationalASSIST

Nguồn: [dataset card chính thức](https://huggingface.co/datasets/ASSISTments/FoundationalASSIST).

Có đề bài, câu trả lời đầu tiên và liên kết problem–skill; phù hợp benchmark KT và phân tích một số câu trả lời sai. Không mặc định có nhãn misconception hoặc đầy đủ bước giải/hội thoại. Dataset card nêu không lưu các lần thử tiếp theo; `discrete_score` còn phụ thuộc việc dùng hỗ trợ, nên câu trả lời đúng vẫn có thể mang điểm 0.

Ghi rõ mục tiêu dự đoán là “đúng độc lập theo định nghĩa dataset” hay “đáp án đúng”; không trộn hai nhãn. Kiểm tra phiên bản, điều kiện truy cập và quy tắc sử dụng. Đây là nguồn bổ sung khi đã được cấp quyền, không chặn tiến độ.

### 11.2. ASSISTments Data Mining Competition 2017

Nhóm đã có file trong `data`. Chọn làm **dataset KT chính ban đầu**, sau khi kiểm tra schema, số skill hợp lệ và ý nghĩa cột theo [mô tả chính thức](https://sites.google.com/view/assistmentsdatamining/dataset).

- Chuẩn hóa student ID, skill, thứ tự tương tác, đúng/sai, hint, số lần thử và loại activity.
- Tạo nhãn BKT từ log tương tác theo định nghĩa đã kiểm tra. Không dùng `training_label.csv` như nhãn đúng/sai từng bài; header hiện có chứa nhãn/thông tin cấp học sinh.
- Không dùng các cột suy luận sẵn như `Ln`, `AveKnow` làm ground truth mastery. Loại biến tổng hợp toàn lịch sử và biến biết tương lai khỏi đầu vào dự đoán.
- Chọn một bản release làm nguồn chuẩn; không nối bản full và các file training chồng lặp thành những observations mới.
- Loại trùng, phân biệt hint/scaffold với bài gốc, xử lý thiếu skill; báo cáo số dòng giữ/bỏ và lý do.
- Đọc theo chunk/cột cần thiết; giữ dữ liệu gốc bất biến.

### 11.3. Junyi Academy

Nguồn: [Junyi Academy Online Learning Activity Dataset](https://www.kaggle.com/datasets/junyiacademy/learning-activity-public-dataset-by-junyi-academy).

Dùng làm benchmark KT thứ hai nếu hoàn thành pipeline chính đúng mốc; dữ liệu đã có trong `data/archive`. `ucid` là ID nội dung, cần đối chiếu `Info_Content` trước khi xem như skill. `Log_Problem` có thông tin correctness và hint nhưng không mặc định chứa bước giải hay nhãn misconception.

Không gộp các skill khác nghĩa của Junyi, ASSISTments và taxonomy Việt Nam chỉ vì tên gần giống. Báo cáo riêng từng dataset; có thể dùng subset đã chốt trước để giảm thời gian xử lý, không chọn subset theo kết quả test.

### 11.4. Vietnamese Math Knowledge Base

Nguồn nội dung chính cho 40 concept: chương trình môn Toán, tài liệu có quyền sử dụng và bài tự biên soạn. Mỗi mục có nguồn, người biên soạn, người duyệt và phiên bản. LLM hỗ trợ tạo nháp, sau đó kiểm tra toán và sư phạm.

Problem record mẫu:

```json
{
  "problem_id": "LE_001",
  "template_family_id": "linear_with_distribution",
  "concept_ids": ["E02", "A02"],
  "primary_skill_id": "E02",
  "difficulty": 1,
  "question": "Giải 2(x - 3) = 10",
  "domain": "real",
  "reference_solution": ["2x - 6 = 10", "2x = 16", "x = 8"],
  "alternative_methods": ["divide_both_sides_first"],
  "step_skill_map": [{"step_id": "distribution", "skill_id": "A02"}],
  "misconception_ids": ["M_DIST_01"],
  "source_type": "self_authored",
  "review_status": "pending",
  "split": "authoring"
}
```

Khi triển khai, tên trường và nội dung tiếng Việt được chuẩn hóa; ví dụ chỉ minh họa schema. `reference_solution` không phải chuỗi duy nhất được chấp nhận. Metadata lớp phải được duyệt theo chương trình, không điền theo phỏng đoán.

Misconception record gồm ID, họ lỗi, skill liên quan, dấu hiệu quan sát, ví dụ sai, ví dụ dễ nhầm nhưng không phải lỗi đó, câu hỏi chẩn đoán, strategy gợi ý và nguồn/căn cứ. Phân biệt lỗi tính toán, lỗi ký hiệu, lỗi điều kiện và giả thuyết hiểu sai khái niệm.

### 11.5. Bộ dữ liệu bước giải và bộ tình huống thích ứng

Hai bộ cần xây riêng, không thay thế bằng log KT:

- **Bộ câu trả lời/bước giải có nhãn:** đề, cách giải của học sinh, bước sai đầu tiên, skill, họ lỗi, nhãn chi tiết nếu đủ bằng chứng, trạng thái không xác định, mức hỗ trợ và nhãn đúng/sai đã duyệt.
- **Bộ tình huống quyết định:** lịch sử trước lượt hiện tại, Student Model nhất quán với lịch sử, bài đang làm, lỗi, tài liệu có thể truy xuất, tập chiến lược chấp nhận được và hành động bị cấm.

Bao gồm bài đúng theo cách khác, lỗi kéo theo, chỉ có đáp án cuối, sai điều kiện, input mơ hồ, không đủ bằng chứng và xin đáp án trực tiếp. Nhãn chiến lược có thể có nhiều đáp án hợp lý, không ép một câu chữ duy nhất.

Tách `authoring/dev/test` theo **bài gốc và họ mẫu sinh bài**, không chia ngẫu nhiên các bước của cùng bài. Test không được dùng viết prompt, tạo luật lỗi hoặc điều chỉnh ngưỡng. KB có nội dung kiến thức tổng quát của concept, nhưng không chứa nguyên ca test, nhãn test hoặc lời giải test để generator truy xuất. Đáp án riêng của validator không được đưa sang node sinh hint.

Dữ liệu tổng hợp và dữ liệu học sinh thật phải gắn nguồn riêng, báo cáo riêng. Có thể tham khảo taxonomy teacher moves của [MathDial](https://aclanthology.org/2023.findings-emnlp.372/); dữ liệu này dùng giáo viên tương tác với học sinh mô phỏng, không thay thế bộ tiếng Việt hoặc nghiên cứu người học thật.

## 12. Quy mô dữ liệu tự xây

Mục tiêu dưới đây là **ngân sách công việc**, được kiểm tra bằng pilot tuần 2; không phải bằng chứng trước rằng cỡ mẫu đủ mạnh về thống kê.

| Thành phần | Mục tiêu và cách tính |
|---|---|
| Concept hoàn chỉnh | 40, trong phạm vi đăng ký 30–50 |
| Prerequisite edges | Khoảng 50–100, số thực tế theo quan hệ đã duyệt; không thêm cạnh để đủ chỉ tiêu |
| Bài tập | 240–300; tối thiểu 6/concept, ít nhất 3 họ mẫu/concept |
| Ví dụ giải | 120–160; tối thiểu 3/concept, có thể biên soạn từ bài authoring/dev |
| Misconception chi tiết | 50–100 kiểu, tổ chức dưới khoảng 12–20 họ lỗi để thống kê ổn định hơn |
| Hint | Ít nhất một ladder đủ mức/concept; tái sử dụng template theo họ lỗi, có kiểm tra từng concept |
| Câu trả lời/bước giải có nhãn | Khoảng 800–1.200 records; mỗi record có ngữ cảnh và nhãn kiểm chứng |
| Tình huống thích ứng | 160–200; tối thiểu 4/concept, gồm tình huống thường gặp và ngoại lệ |
| Bộ truy xuất có relevance labels | Khoảng 120–200 query, phủ concept và mục đích explanation/example/hint |

Với bộ bước giải, tách authoring/dev/test khoảng 50/20/30 theo nhóm bài/mẫu, sau đó điều chỉnh để bảo đảm độ phủ; **không áp tỷ lệ máy móc nếu làm mất lớp hiếm**. Test cần phủ đủ 40 concept, tối thiểu 4 records/concept và có cả đúng/sai.

Với bộ tình huống thích ứng, dành khoảng một nửa cho dev và một nửa cho test: **80–100 tình huống test**, ít nhất 2/concept. Các biến thể cùng bài/lịch sử hoặc cặp hồ sơ dùng chung mẫu phải nằm cùng split. Không áp tỷ lệ test 30% cho bộ này vì sẽ không đủ độ phủ tối thiểu. Công bố ma trận độ phủ thực tế, không suy ra từ tổng số mẫu.

Một bài có thể sinh nhiều records bước giải và một ví dụ giải có thể lấy từ bài authoring/dev đã duyệt; các mục trong bảng không nhất thiết là những bộ bài hoàn toàn riêng. Tuy nhiên, mọi biến thể cùng nguồn phải được gom nhóm trước khi chia tập để tránh rò rỉ.

Nếu nhóm bài quá ít để tách không rò rỉ, phải biên soạn thêm mẫu trước khi khóa test. F1 họ lỗi là chỉ số chính; F1 nhãn chi tiết phải kèm support, không kết luận chắc cho lớp chỉ có vài mẫu. Tối thiểu 10 mẫu test/họ lỗi là mục tiêu lập kế hoạch, chưa bảo đảm sai số nhỏ.

### Quy trình gán nhãn và kiểm duyệt

1. Hai người cùng thử gán nhãn một pilot nhỏ, viết guideline cho trường hợp mơ hồ và lỗi kéo theo.
2. Người biên soạn tạo record; người khác kiểm tra toán, nhãn và mức tiết lộ. Chuyên gia/giáo viên rà taxonomy, quy tắc và mẫu khó.
3. Test bước giải và tình huống được hai người gán nhãn độc lập trước hòa giải; lưu cả nhãn ban đầu, độ đồng thuận và nhãn cuối.
4. Theo dõi thời gian tạo/duyệt từ pilot, chia quota nội dung cho cả ba người; không dồn toàn bộ KB cho Member 2.
5. Khóa test và phiên bản KB/prompt. Thành viên trực tiếp phát triển detector không dùng test để tinh chỉnh; phân quyền hoặc quy trình kiểm soát truy cập, ghi rõ giới hạn nếu chưa có người đánh giá độc lập.

## 13. Workflow đầy đủ khi hệ thống chạy

1. **Nạp session:** xác thực người học, lấy state và phiên bản; học sinh mới có prior và có thể làm vài bài chẩn đoán, không bị mặc định yếu tất cả skill.
2. **Chọn bài:** Agent kết hợp mục tiêu, evidence count, mastery và graph; lấy bài đã duyệt, lưu mục tiêu đo và opportunity.
3. **Nhận bài làm:** lưu input một lần theo khóa idempotency; chuẩn hóa biểu thức và bước.
4. **Phân tích:** validator kiểm tra tính đúng, analyzer chỉ ra bước sai và giả thuyết lỗi; thiếu bằng chứng thì hỏi làm rõ.
5. **Cập nhật:** ghi prediction từ state trước observation, sau đó cập nhật BKT nếu hợp lệ; transaction chống cập nhật hai lần.
6. **Chọn can thiệp:** Agent tra prerequisite/nội dung/bài khi cần, chọn action dựa trên state; policy gate kiểm tra.
7. **Sinh phản hồi:** dùng nội dung được phép, kiểm tra toán và mức tiết lộ; fallback khi không đạt.
8. **Checkpoint và phản hồi:** lưu action, bằng chứng, source IDs, hint level, latency, token/cost; chờ lượt mới.
9. **Kết thúc/tiếp tục:** xử lý bài mới, backtrack hoặc dừng theo policy; ghi learning report với bằng chứng và giới hạn ước lượng.

Hội thoại hiển thị phân biệt bài đang làm, ví dụ hỗ trợ và bài kiểm tra mới. Khi resume/retry, không chạy lại cập nhật BKT đã hoàn tất.

## 14. Database đề xuất

Chốt **PostgreSQL + pgvector + Neo4j** để giữ đầy đủ RAG/KG, tránh duy trì thêm một vector DB độc lập.

| Thành phần | Nội dung |
|---|---|
| PostgreSQL | users/students, sessions, turns, problems, skills, concept–skill mapping |
| PostgreSQL | opportunities, observations, mastery, mastery_history, bkt_parameter_versions |
| PostgreSQL | misconception_taxonomy, diagnosis_history, pedagogical_decisions, evaluation_runs |
| pgvector trong PostgreSQL | KB chunks, embeddings, metadata, nguồn và mức tiết lộ |
| Neo4j | concept nodes, prerequisite/related/part-of edges và provenance |

ID concept/skill/problem ổn định xuyên các kho; taxonomy có phiên bản. Cấu hình một nguồn chuẩn cho nội dung registry và script đồng bộ graph/index để tránh sửa tay lệch nhau.

Ràng buộc duy nhất cho observation theo student, opportunity và skill; `turn_id` chống gửi trùng. Cập nhật observation + mastery trong transaction và kiểm soát phiên bản state khi có hai request đồng thời. Checkpoint LangGraph dùng cùng định danh session; có cơ chế đối soát/replay không lặp side effect khi DB và checkpoint chưa cùng hoàn tất.

## 15. Tech stack đề xuất

| Layer | Lựa chọn ban đầu |
|---|---|
| Frontend | Next.js/React, render công thức bằng thư viện phù hợp |
| Backend | FastAPI, Pydantic |
| Agent orchestration | LangGraph |
| LLM | Một API model chính, chốt model/version và cấu hình trước thí nghiệm |
| Toán | SymPy + luật theo dạng bài + reference answers đã duyệt |
| Student Model | Python + pyBKT; online update đối chiếu thư viện |
| Main DB / retrieval | PostgreSQL + pgvector |
| Knowledge Graph | Neo4j |
| Truyền phản hồi | HTTP; bổ sung SSE khi có bản tích hợp ổn định |
| Evaluation | Python, scripts/config tái lập được |
| Deployment | Docker Compose |

LangChain là tùy chọn. LangGraph giữ vòng đời, state và checkpoint; dùng framework không tự chứng minh đóng góp nghiên cứu. Tài liệu [LangGraph](https://docs.langchain.com/oss/python/langgraph/workflows-agents) phân biệt workflow định trước và agent quyết định động.

Benchmark nhỏ tuần 2 để chọn model theo độ đúng, structured output, tiếng Việt, latency và chi phí. Không mặc định phải tự host/fine-tune. Lưu phiên bản embedding và cấu hình retrieval; đổi embedding phải tạo lại index nhất quán.

Chỉ stream trạng thái xử lý hoặc nội dung đã qua kiểm tra; không stream raw hint trước validator rồi mới phát hiện đã tiết lộ đáp án. Cache KB/embedding; cache phản hồi cá nhân hóa phải có khóa chứa state và phiên bản, không dùng lẫn giữa người học.

## 16. Offline và Online BKT

### 16.1. Benchmark trên dữ liệu công khai

1. Chốt dataset/version, ý nghĩa label, skill mapping, quy tắc hint/scaffold và xử lý thiếu.
2. Chia **theo học sinh** thành train/dev/test trước khi fit; mọi tương tác của một học sinh chỉ thuộc một tập. Trong từng tập giữ thứ tự thời gian/action.
3. Fit tham số chỉ trên train; chọn cấu hình trên dev. Với học sinh test, khởi tạo prior rồi dự đoán từng lượt trước khi cập nhật bằng đáp án vừa quan sát; không refit tham số trên test.
4. So sánh BKT với tỷ lệ đúng theo skill tính từ train và mô hình đơn giản dùng lịch sử trước lượt hiện tại.
5. Báo AUC khi có đủ hai lớp, log loss, Brier score, calibration và số lượng dữ liệu. Accuracy là bổ sung; không dùng trạng thái BKT suy luận sẵn làm nhãn thật.

Nếu làm thêm đánh giá cá nhân đã biết, dùng chronological split riêng và báo rõ; không trộn kết quả này với khả năng tổng quát hóa sang học sinh mới.

### 16.2. Khởi tạo cho taxonomy tiếng Việt

Kết quả tốt trên ASSISTments/Junyi chỉ kiểm chứng phương pháp/pipeline ở nguồn đó, chưa xác nhận mastery cho học sinh Việt Nam.

- Tạo bảng ánh xạ nguồn–skill Việt Nam, ghi mức tương thích về kỹ năng, dạng bài và định nghĩa observation.
- Chỉ chuyển tham số như một phương án khởi tạo khi có căn cứ; không tự ghép theo tên gần giống.
- Với skill chưa có dữ liệu: dùng prior/tham số chung hoặc theo nhóm nội dung, đánh dấu `default/pooled`; không công bố là đã fit riêng.
- Dùng pilot tiếng Việt để kiểm tra và hiệu chỉnh khi có đủ dữ liệu. So sánh vài bộ tham số hợp lý, đo độ nhạy của mastery và quyết định policy.
- Không fit riêng 4 tham số/skill từ vài observations. Giữ đủ 40 concept, dùng pooling và nêu độ thiếu dữ liệu thay vì xóa skill.
- Giữ tập đánh giá riêng; dữ liệu synthetic phục vụ kiểm thử thuật toán, không chứng minh tham số phản ánh người học thật.

### 16.3. Online và cold start

Mỗi observation hợp lệ cập nhật state theo mục 8.3; lưu dự đoán trước cập nhật, state trước/sau và tham số sử dụng. Với học sinh mới, prior chưa phải kết luận về năng lực: dùng câu hỏi chẩn đoán ngắn và chọn bài phù hợp khi bằng chứng còn ít.

Nếu thay bộ tham số, tạo version mới và quy định khởi tạo lại/replay lịch sử hợp lệ; không âm thầm trộn state cũ với tham số mới. Báo cáo mastery luôn có evidence count, ngày cập nhật và nguồn tham số.

## 17. Research Questions

| RQ | Câu hỏi | Thí nghiệm/chỉ số trả lời |
|---|---|---|
| RQ1a | BKT dự đoán kết quả độc lập tiếp theo thế nào so với baseline đơn giản? | Benchmark KT; log loss, AUC, Brier/calibration |
| RQ1b | BKT có cải thiện lựa chọn can thiệp so với bỏ mastery hoặc dùng lịch sử đúng/sai đơn giản? | Full, No-BKT, Heuristic; rubric chiến lược |
| RQ2 | Prerequisite graph có cải thiện chọn kiến thức cần ôn/bài tiếp theo? | Full vs No-KG trên tình huống cần prerequisite |
| RQ3 | RAG có cải thiện bám nội dung, độ đúng và chất lượng hint? | Full vs No-RAG; retrieval metrics và chấm đầu ra |
| RQ4 | Hệ thống xác định bước sai và misconception chính xác đến đâu? | Bộ bước giải tiếng Việt; F1, localization, abstention |
| RQ5 | Agent chọn can thiệp có lợi gì so với policy luật với cùng thông tin? | Full vs Rule-policy; rubric, cost, latency |

RQ1b và RQ4 là trọng tâm phân tích; các RQ còn lại kiểm chứng vai trò những thành phần đã đăng ký. Không cần mọi ablation đều đạt cải thiện có ý nghĩa thống kê để có kết quả nghiên cứu hợp lệ; phải báo trung thực khi chưa có bằng chứng.

## 18. Baseline và Ablation

### 18.1. Các cấu hình

| Cấu hình | Khác biệt so với Full |
|---|---|
| Full | Analyzer + BKT + KG + RAG + Agent trong LangGraph |
| No-BKT | Không cung cấp mastery hoặc bản tóm tắt suy ra từ BKT; giữ evidence log và các thành phần còn lại |
| Heuristic | Thay BKT bằng tỷ lệ đúng của tối đa 5 observations độc lập gần nhất/skill; giữ evidence count, không gọi nó là xác suất mastery |
| No-KG | Bỏ cạnh prerequisite và truy graph; giữ nhãn concept/skill và nội dung không tiết lộ quan hệ prerequisite |
| No-RAG | Bỏ truy xuất nội dung dạy; giữ đề, state, policy và validator |
| Rule-policy | Giữ analyzer/BKT/KG/RAG, thay quyết định động bằng luật đã chốt; dùng cùng generator |
| Socratic LLM baseline | LLM được prompt Socratic, nhận đề và cùng cửa sổ hội thoại; không có student model dài hạn/KG/RAG |

Socratic LLM là tham chiếu cấp hệ thống, không dùng riêng nó để kết luận thành phần nào gây cải thiện. Rule-policy cũng chạy trong LangGraph để tránh lẫn tác động của framework và thuật toán quyết định.

### 18.2. Kiểm soát so sánh

- Cùng model/version, cấu hình sinh, cửa sổ lịch sử, giới hạn token đầu ra và policy về tiết lộ. Báo cả token/cost thực tế; không giả định ngân sách dùng thực tế bằng nhau khi số tool khác nhau.
- Các ablation giữ cùng analyzer, validator, problem bank và prompt cấu trúc; chỉ thay phần đã mô tả. Bộ verifier giữ đáp án riêng, không chuyển đáp án cho generator.
- No-KG phải loại cả trường prerequisite trong metadata/prompt; nếu vẫn giữ quan hệ đó ở nơi khác thì chưa phải ablation graph.
- Heuristic sử dụng cùng observations được phép như BKT; ngưỡng quyết định được chọn trên dev theo cùng ngân sách, không mặc định ngưỡng xác suất BKT áp nguyên cho heuristic.
- Dùng cùng lịch sử trước lượt đánh giá. Chấm offline ghép cặp các quyết định từ cùng state để tránh khác biệt quỹ đạo hội thoại làm nhiễu.
- Khi đánh giá multi-turn, chạy riêng từng quỹ đạo, gắn nguồn student thật/script/mô phỏng và không coi các lượt trong cùng session là mẫu độc lập.
- Thực hiện ablation trên tập tình huống phủ đủ concept. Kiểm thử độ ổn định nhiều lần trên một subset phân tầng đã chốt; báo số lần chạy.

Các cặp hồ sơ giả định mastery thấp/cao chỉ là test policy. Với hồ sơ lấy từ BKT, state phải tái lập từ lịch sử và bộ tham số, không chỉnh tay rồi tuyên bố là hiệu quả BKT. Đánh giá chấp nhận nhiều chiến lược phù hợp, không buộc “mastery thấp luôn backtrack”.

## 19. Evaluation

### 19.1. Metric và ground truth

| Thành phần | Chỉ số chính | Nhãn chuẩn và giới hạn |
|---|---|---|
| BKT | Log loss, AUC, Brier, calibration | Kết quả observation tương lai; không có nhãn thật cho latent mastery |
| Chấm bước giải | Accuracy đúng/sai, xác định bước sai đầu tiên | Bước giải được người duyệt xác minh, có cách giải khác |
| Misconception | Macro-F1 theo họ lỗi, precision/recall từng lớp | Nhãn chi tiết chỉ chấm khi đủ bằng chứng; báo support |
| Không chắc chắn | Coverage và lỗi trên phần đã quyết định; tỷ lệ hỏi làm rõ | Không loại mẫu abstain để làm đẹp F1; confusion matrix có unknown |
| RAG | Recall@K, nDCG@K; Hit@K bổ sung | Tập relevance được gán nhãn; chốt K trên dev |
| KG recommendation | Tỷ lệ chọn thuộc tập prerequisite chấp nhận được | Giáo viên/người đánh giá duyệt độc lập, không lấy chính graph làm đáp án duy nhất |
| Socratic strategy | Rubric trung bình, paired preference, vi phạm nghiêm trọng | Hai người chấm ẩn cấu hình, thứ tự ngẫu nhiên |
| Multi-turn | Tỷ lệ đạt mục tiêu scenario mà không tiết lộ lời giải, số lượt, lặp | Mục tiêu được chốt trước; không lấy mastery tăng làm thành công |
| Vận hành | Latency p50/p95, lỗi, fallback, chi phí/lượt và phiên | Ghi model, hardware, mạng và tải thử |
| Người dùng thật | Usability, khả năng làm bài mới độc lập; pre/post nếu tổ chức được | Pilot mô tả, chỉ kết luận nhân quả khi thiết kế đối chứng phù hợp |

Đối với phát hiện lỗi, tách “bước sai rõ”, “giả thuyết misconception” và “misconception được hỗ trợ bởi nhiều bằng chứng”. Nhãn testcase phải phản ánh mức có thể quan sát được, không gán chắc suy nghĩ bên trong học sinh.

### 19.2. Rubric Socratic

Mỗi chiều 0–2 điểm: 0 không đạt, 1 đạt một phần, 2 đạt rõ; guideline kèm ví dụ cụ thể.

| Chiều | Điều kiện đạt 2 |
|---|---|
| Đúng toán | Không có phát biểu/biến đổi sai, giữ điều kiện áp dụng |
| Bám lỗi | Câu hỏi hướng đến vấn đề có bằng chứng |
| Phù hợp người học | Mức hỗ trợ phù hợp mastery, evidence count và lịch sử |
| Gợi mở | Để học sinh thực hiện phần suy luận tiếp theo |
| Không tiết lộ | Không đưa đáp án/lời giải hoàn chỉnh của bài hiện tại |
| Rõ ràng | Ngắn, hiểu được, không hỏi dồn nhiều việc |

Báo từng chiều, không chỉ tổng điểm. Lỗi toán nghiêm trọng hoặc tiết lộ lời giải làm scenario thất bại dù tổng rubric cao. Hai người chấm độc lập; tính weighted kappa cho điểm thứ bậc và Cohen's kappa cho nhãn phân loại phù hợp, báo trước hòa giải. LLM-as-judge chỉ hỗ trợ, không là nguồn chấm duy nhất.

### 19.3. Quy trình thực nghiệm

1. Tuần 1–2 chốt RQ, split và định nghĩa metric; pilot rubric và annotation.
2. Tuần 3–7 chỉ dùng authoring/dev để sửa prompt, tham số, threshold và luật.
3. Cuối tuần 7 khóa test, cấu hình và script. Tuần 8–10 chạy chính thức, lưu raw outputs và log.
4. Nếu phát hiện lỗi code sau khóa, ghi thay đổi và chạy lại các cấu hình bị ảnh hưởng. Không sửa theo mẫu test rồi tiếp tục gọi đó là đánh giá trên test chưa thấy.
5. Báo khoảng tin cậy bằng bootstrap theo học sinh cho KT và theo scenario/nhóm bài cho đánh giá hội thoại; không bootstrap từng lượt như các quan sát độc lập.
6. Phân tích lỗi theo concept, họ lỗi, mức hỗ trợ và nguồn dữ liệu; báo trường hợp không thể chấm hoặc thiếu lớp.

### 19.4. Pilot người dùng

Liên hệ người phản biện nội dung và người hỗ trợ tuyển người học từ tuần 1, không đợi tuần 11. Mục tiêu vận hành là pilot nhỏ khoảng 12–20 người học thuộc THCS/THPT nếu tiếp cận được; đây không phải cỡ mẫu bảo đảm kết luận thống kê.

Usability và quan sát lỗi tương tác là mục tiêu chính của pilot. Nếu đo pre/post, dùng hai bộ tương đương, bài mới không hint, ghi thời gian luyện và kiến thức ban đầu; không diễn giải tăng điểm đơn nhóm thành hiệu quả nhân quả. Muốn so sánh tác động học tập cần nhóm đối chứng/phân nhóm thích hợp và tính cỡ mẫu riêng.

Nếu không tuyển được người học, vẫn thực hiện đầy đủ benchmark KT, bộ bước giải và chấm chuyên gia cho các chiến lược; báo rõ chưa chứng minh learning gain thực tế. Học sinh mô phỏng chỉ kiểm thử quy trình, không thay thế bằng chứng người học thật.

## 20. Success Criteria

### Điều kiện hoàn thành bắt buộc

- Đủ **40 concept mục tiêu** hoặc danh mục 30–50 đã chốt theo mục 5, có đủ nội dung và test; báo cáo độ phủ từng concept.
- Cả BKT, KG, RAG và Agent được dùng thật, có log chứng minh ảnh hưởng đến quyết định.
- BKT chỉ cập nhật observation hợp lệ; không lặp khi retry; state online đối chiếu công thức/thư viện.
- Analyzer chấp nhận cách giải hợp lệ khác, có nhánh chưa đủ bằng chứng và tránh phạt lỗi kéo theo.
- Có Socratic multi-turn, mức hỗ trợ tăng dần, backtrack có quay lại, dừng và resume.
- Có Student UI và learning report; dữ liệu lưu giữa các phiên.
- Có bộ bước giải test, benchmark KT, chấm rubric và baseline/ablation có thể tái lập.
- Công bố kết quả, độ bất định, lỗi còn tồn tại và giới hạn suy rộng.

### Mục tiêu chất lượng để quản lý tiến độ

Mốc ban đầu: Macro-F1 họ lỗi khoảng **0.75 trở lên**, tỷ lệ xác định đúng bước sai đầu tiên khoảng **0.80 trở lên**, Recall@5 khoảng **0.85 trở lên**, tỷ lệ phản hồi đúng toán khoảng **0.95 trở lên**, tỷ lệ tiết lộ đáp án không quá **5%**, latency p95 khoảng **10 giây/lượt** trong cấu hình thử đã mô tả.

Đây là mục tiêu kỹ thuật đề xuất, không phải kết quả có sẵn hoặc chuẩn ngành. Hiệu chỉnh mục tiêu theo pilot/dev trước khi khóa test, lưu lý do; không hạ ngưỡng sau khi thấy test để tuyên bố đạt. Các tỷ lệ phải kèm mẫu số và khoảng tin cậy. BKT/full có vượt baseline hay không là kết quả cần báo cáo, không được giả định trước.

---

## 21. Các pain point kỹ thuật

| Rủi ro | Xử lý trong phạm vi đã đăng ký |
|---|---|
| Khối lượng 40 concept lớn | Dùng schema/template theo họ dạng bài, chia nội dung cho cả ba, nghiệm thu theo ma trận độ phủ |
| Dataset công khai lệch taxonomy Việt Nam | Benchmark riêng; mapping có căn cứ, pooled/default parameters và sensitivity analysis |
| FoundationalASSIST chưa được cấp quyền | Tiếp tục bằng ASSISTments 2017 đã có; không chặn pipeline |
| BKT thiếu quan sát mỗi skill | Pool tham số theo nhóm, bài chẩn đoán và evidence count; giữ danh mục concept |
| Làm đúng nhờ hint bị tính như tự làm | Tách observations độc lập khỏi kết quả có hỗ trợ |
| Phân loại misconception quá chắc | Nhãn suspected/unknown, câu hỏi chẩn đoán, đánh giá abstention |
| Validator không xử lý được biểu thức | Giới hạn dạng hỗ trợ, nhánh unverified, giải thích input cần làm rõ |
| RAG/KG có nhưng không ảnh hưởng quyết định | Log source/edge IDs, action và evidence; ablation có kiểm soát |
| LLM đưa đáp án hoặc toán sai | Kiểm tra trước khi gửi, một lần sửa, fallback template đã duyệt |
| Vòng backtrack/hint kéo dài | Giới hạn tầng/lượt, return stack, cho phép kết thúc |
| Retry hoặc hai tab làm lệch mastery | Idempotency, transaction, version check và đối soát checkpoint |
| Latency/cost cao | Giới hạn tool/model calls, cache nội dung tĩnh, đo từ tuần 2 |
| Nhãn dữ liệu chủ quan | Guideline, hai người gán test độc lập, hòa giải và báo đồng thuận |
| Chưa có giáo viên phản biện | Liên hệ từ tuần 1; rà toán chéo trong nhóm, nêu giới hạn chuyên môn nếu chưa có chuyên gia |
| Thiếu người học pilot | Chốt sớm; vẫn hoàn thành evaluation kỹ thuật, không tuyên bố learning gain |
| Thay đổi model/API | Cố định model ID và ghi thời điểm/config; lưu outputs, không trộn các bản chạy không tương đương |

Khi chậm tiến độ, ưu tiên bỏ phần ngoài yêu cầu như voice, fine-tuning, benchmark dataset thứ hai hoặc dashboard nâng cao; không tự bỏ một trong các module đã đăng ký hay giảm dưới 30 concept.

## 22. Privacy và quản lý dữ liệu

Dùng ID giả danh, không yêu cầu tên thật, số điện thoại, địa chỉ cho chức năng tutoring. ID giả danh không tự làm toàn bộ dữ liệu trở thành vô danh: hội thoại tự do có thể chứa thông tin nhận dạng.

- Tách thông tin tài khoản khỏi log học tập; kiểm tra quyền truy cập theo người học.
- Trước pilot, thống nhất với người phụ trách/nhà trường về cách thông báo, sự đồng ý phù hợp với đối tượng học sinh, dữ liệu được thu và quyền dừng tham gia.
- Nêu rõ phần nội dung gửi tới nhà cung cấp LLM; loại thông tin nhận dạng không cần thiết trước khi gửi.
- Lưu tối thiểu skill, attempt, mức hỗ trợ, correctness, mastery, diagnosis, timestamp và dữ liệu cần cho đánh giá. Raw conversation chỉ lưu trong phạm vi đã thông báo.
- Quy định thời gian lưu, người có quyền xem, cách xóa và cách công bố ví dụ đã khử nhận dạng trước thu thập.
- Không đưa dữ liệu học sinh thật, API key hoặc dữ liệu nguồn bị hạn chế chia sẻ vào repo/public demo. Dùng hồ sơ tổng hợp cho trình diễn.

## 23. Chia việc nhóm 3 người

### 23.1. Trách nhiệm chính

| Thành viên | Module chịu trách nhiệm | Phần sản phẩm và evaluation đi kèm |
|---|---|---|
| Member 1 | Student Model, BKT, preprocessing, observation builder, mathematical validator/analyzer | API cập nhật state; benchmark KT; đánh giá bước sai/misconception; phối hợp Member 3 cho LLM extraction |
| Member 2 | Taxonomy/KB registry, Knowledge Graph, RAG, đồng bộ dữ liệu | Pipeline biên soạn/kiểm duyệt; đánh giá retrieval/prerequisite; dữ liệu learning report |
| Member 3 | AI Agent, pedagogical policy, LangGraph, session orchestration | Student UI, tích hợp API, checkpoint/resume, Docker; ablation policy và đo vận hành |

Đây là trách nhiệm đầu mối, không có nghĩa làm độc quyền. Member 2 điều phối nội dung nhưng **cả ba biên soạn khoảng 13–14 concept/người** và review chéo. Member 1 tập trung nền toán/BKT, Member 3 hỗ trợ extraction và giao diện nhập bước; Member 2 hỗ trợ report để tránh dồn toàn bộ sản phẩm cho Member 3.

Mỗi module có người review khác chủ sở hữu. Test đánh giá được phân công theo quy trình mục 12; người đã xem nhãn test không dùng thông tin đó tinh chỉnh thành phần đang được đánh giá.

### 23.2. Cách làm việc

- Tuần 1 chốt hợp đồng `Problem`, `Assessment`, `Observation`, `StudentState`, `PedagogicalDecision` cùng một số fixtures chung.
- Một lần tích hợp và chạy luồng thật mỗi tuần; không đợi xong mọi module mới ghép.
- Mỗi tuần có bảng độ phủ concept: nội dung, bài, validator, misconception, hints, test, reviewer.
- Đo giờ tạo/duyệt một concept và một record từ pilot; đối chiếu số giờ nhóm có thể dành mỗi tuần, cân bằng lại phân công.
- Viết báo cáo từ tuần 2; mỗi chủ module cập nhật phương pháp, quyết định và giới hạn ngay khi làm.
- Dành khoảng 15–20% quỹ thời gian cho tích hợp, sửa lỗi và chạy lại; ưu tiên công việc trên đường găng: taxonomy -> observation/assessment contract -> loop -> test -> experiments.

## 24. Kế hoạch 12 tuần

Các cột thành viên là các luồng chạy song song. Mốc concept tính theo checklist, không chỉ số node trên graph.

| Tuần | Member 1 | Member 2 | Member 3 | Mốc chung |
|---:|---|---|---|---|
| 1 | Audit schema KT, định nghĩa observation/validator | Chốt danh mục 40 và template nội dung | Skeleton API/UI/LangGraph, schema state | RQ, tiêu chí, phân công; liên hệ phản biện/pilot |
| 2 | Preprocess dataset chính, BKT baseline; checker các dạng đầu | Graph/KB mẫu, relevance/annotation guideline | Policy luật đầu tiên; thử model, token và latency | Pilot dữ liệu/rubric; chốt split và model; đo năng suất biên soạn |
| 3 | Online BKT, idempotency, analyzer v1 | RAG + KG nối API; review nội dung đợt 1 | Nối loop thật, session và UI nhập bước | Luồng chạy trên một số concept; fixtures và log liên thông |
| 4 | Validator/analyzer cho 8–10 concept đại diện | 8–10 concept hoàn chỉnh thuộc ba mảng; truy xuất đã lọc | Agent chọn action/tool, checkpoint/resume và fallback | **End-to-end v1**: đủ module, đa lượt, lưu giữa phiên |
| 5 | Mở rộng checker/detector, KT dev evaluation | Nội dung/graph/retrieval cho khoảng 20 concept | Backtrack/return, report cơ bản; cấu hình ablation | Khoảng 20 concept đạt checklist; review lỗi hệ thống |
| 6 | Độ phủ khoảng 30 concept; pooled params/sensitivity | Nội dung và test cho khoảng 30 concept | Kiểm thử tình huống, rubric dev, ổn định UI | Khoảng 30 concept, baseline/ablation chạy trên dev |
| 7 | Hoàn tất analyzer/BKT cho danh mục đã chốt | Hoàn tất 40 concept và kiểm duyệt dữ liệu | Hoàn tất full system và toàn bộ cấu hình so sánh | **Đủ 40 concept; khóa test, model, prompt, KB và ngưỡng** |
| 8 | Benchmark KT và detector chính thức | Retrieval/KG evaluation, chấm kết quả ẩn cấu hình | Full/ablation batch, log latency/cost | Kết quả sơ bộ và kiểm tra chất lượng phép đo |
| 9 | Phân tích lỗi theo skill/nhãn; kiểm tra leakage | Chấm rubric/hòa giải, báo cáo độ phủ | Chạy ổn định nhiều lần trên subset; hỗ trợ pilot | Hoàn tất thí nghiệm chính và pilot nếu tuyển được |
| 10 | Tổng hợp thống kê và hạn chế tham số | Báo cáo dữ liệu/annotation/graph | Hoàn thiện phân tích ablation và vận hành | Kết quả cuối, khoảng tin cậy, bản thảo báo cáo đầy đủ |
| 11 | Sửa lỗi cần thiết, regression checks | Rà nội dung và tài liệu bàn giao | Ổn định triển khai, diễn tập demo | Release candidate; thay đổi ảnh hưởng kết quả phải chạy lại phù hợp |
| 12 | Hoàn thiện phần phương pháp/kết quả | Hoàn thiện dữ liệu/phụ lục/tài liệu | Đóng gói demo, cấu hình và hướng dẫn chạy | Báo cáo, slides, demo và artifacts tái lập |

Ba người cùng biên soạn, review và gán nhãn mỗi tuần 2–7 ngoài nhiệm vụ đầu mối. Không để phần annotation đợi tới tuần 8.

Nếu mốc tuần 4 trễ, ưu tiên nối loop và sửa contract trước tính năng phụ. Nếu mốc độ phủ trễ, huy động cả ba vào authoring/validator và bỏ phần mở rộng ngoài đăng ký. Danh mục mục tiêu vẫn là 40; bất kỳ thay đổi danh mục cuối đều phải được chốt rõ trong khoảng 30–50 và cập nhật toàn bộ checklist, không âm thầm chỉ demo vài concept.

## 25. MVP và bản nghiệm thu

### MVP tích hợp nội bộ, cuối tuần 4

Đủ analyzer, Student Model/BKT, KG, RAG, Agent, LangGraph, chat nhiều lượt và persistence trên 8–10 concept đại diện. Đây là mốc kiểm tra kiến trúc, **không phải phạm vi nghiệm thu**.

### Bản nghiệm thu bắt buộc

- Đầy đủ danh mục **30–50 concept đã chốt**, kế hoạch mục tiêu 40, thuộc ba mảng THCS–THPT.
- Có kiểm tra bước giải, chẩn đoán misconception và xử lý chưa đủ bằng chứng.
- BKT cập nhật đúng quy tắc observation, có cold start và phiên bản tham số.
- KG/RAG ảnh hưởng thật tới quyết định và nội dung hỏi.
- Agent điều phối chiến lược trong LangGraph, có fallback và kiểm soát vòng lặp.
- UI dùng được, lưu phiên, learning report và demo nhiều hồ sơ.
- Đủ bộ dữ liệu, benchmark, baseline/ablation và rubric theo ba trục đánh giá đã đăng ký.

### Không bắt buộc

Voice, fine-tuning LLM, GraphRAG phức tạp, multi-agent, mobile app, dashboard nâng cao, nhận dạng ảnh/viết tay. Hình học nằm ngoài phạm vi.

## 26. Những lỗi cần tránh

- Dùng BKT chỉ để vẽ phần trăm nhưng Agent không dùng state.
- Dùng một lần làm đúng sau gợi ý để khẳng định đã thành thạo.
- Chấm sai nhiều skill từ một lỗi kéo theo, hoặc chấm sai cách giải khác lời giải mẫu.
- Lấy confidence tự báo cáo hoặc nhãn mastery do mô hình khác suy luận làm ground truth.
- Có graph nhưng quan hệ sai chiều/chưa duyệt; coi mọi prerequisite trên graph đều là điểm yếu học sinh.
- Gọi retrieval nhưng không dùng nội dung hoặc không kiểm soát mức tiết lộ.
- Gọi workflow cố định là đóng góp Agent mà không mô tả quyền quyết định và baseline luật.
- Tối ưu prompt/ngưỡng trên test; để bài chỉ thay số xuất hiện ở cả authoring và test.
- Chỉ báo điểm trung bình toàn hệ thống, che các concept/nhãn ít dữ liệu hoặc lỗi nặng.
- Tuyên bố tăng learning gain chỉ từ mastery tăng, scenario scripted hoặc học sinh mô phỏng.
- Chỉ hoàn thành 40 tên concept mà thiếu bài, validator, hints hoặc test.
- Để retry, resume hoặc hai request đồng thời cập nhật mastery nhiều lần.

## 27. Điểm khác biệt và đóng góp nghiên cứu

Đóng góp dự kiến gồm:

1. **Bộ nội dung và dữ liệu đánh giá tiếng Việt** phủ 30–50 concept, có quan hệ prerequisite, lỗi bước giải và tình huống can thiệp.
2. **Cơ chế tutoring thích ứng có thể truy vết:** kết hợp BKT, bằng chứng lỗi, graph và nội dung truy xuất để chọn hành động trong policy.
3. **Thực nghiệm kiểm soát thành phần:** tách giá trị BKT, KG, RAG và quyết định Agent, báo cả trường hợp không cải thiện.

Không tuyên bố thuật toán BKT mới, phương pháp Socratic mới hoặc tính mới chỉ vì ghép nhiều framework. Đóng góp thực tế phải gắn với kết quả và giới hạn dữ liệu.

### Related Work cần hoàn thành trong báo cáo

| Nhóm nghiên cứu | Cần đối chiếu | Nguồn khởi đầu |
|---|---|---|
| Knowledge Tracing | Giả định observation, estimate tham số, đánh giá dự đoán và latent mastery | pyBKT và các bài nghiên cứu được thư viện dẫn |
| Tutoring dialogue | Teacher moves, misconception, cân bằng gợi mở và tiết lộ | MathDial |
| Dữ liệu giáo dục | Nhãn đúng/sai, hint, skill mapping, khác biệt curriculum | ASSISTments 2017, FoundationalASSIST, Junyi |
| Agent/workflow | Quyết định động, state, công cụ, kiểm soát thực thi | Tài liệu LangGraph |
| Kiểm tra Toán | Biến đổi hợp lệ, điều kiện, giới hạn symbolic solver | Tài liệu SymPy |

Viết bảng so sánh theo ngôn ngữ, miền toán, Student Model, prerequisite, hỗ trợ bước giải và phương pháp đánh giá. Bảng chỉ kết luận sau khi đọc nguồn; không khẳng định hệ thống khác thiếu tính năng từ mô tả sơ lược.

## 28. Công dụng thực tế

**Với học sinh:** phát hiện bước cần kiểm tra, được gợi mở phù hợp, ôn kiến thức nền và thử lại trên bài độc lập.

**Với giáo viên:** xem lỗi có bằng chứng, mastery ước lượng kèm số quan sát, mức hỗ trợ học sinh cần và gợi ý nội dung ôn. Báo cáo phân biệt “đúng sau hỗ trợ” với “đúng độc lập”.

**Với nền tảng học tập:** có thể tái sử dụng tutoring engine, registry nội dung và decision log. Khả năng triển khai quy mô lớn hoặc nâng kết quả học tập cần nghiên cứu thêm, không suy ra chỉ từ demo đồ án.

## 29. Demo cuối kỳ

1. Mở hồ sơ tổng hợp Student A và Student B, lịch sử/parameter version được chuẩn bị minh bạch; state BKT tái lập từ log.
2. Cho làm bài trong danh mục, nhập một bước sai và xem bằng chứng analyzer.
3. Hiển thị observation hợp lệ, state trước/sau; thử gửi lại để chứng minh không cập nhật hai lần.
4. Xem Agent chọn câu hỏi, prerequisite và source IDs tương ứng; hai hồ sơ có thể nhận can thiệp khác khi bằng chứng hỗ trợ.
5. Học sinh sửa sau hint; report ghi kết quả có hỗ trợ, không tăng mastery như nhiều lần làm độc lập.
6. Đưa bài kiểm tra mới, cập nhật BKT từ kết quả độc lập; chuyển bài khi thỏa policy.
7. Minh họa thêm một bài Toán số và một bài Hàm số/THPT để chứng minh đa miền; mở ma trận test của toàn bộ 40 concept.
8. Thử cách giải khác, chỉ nhập đáp án cuối hoặc input mơ hồ; hệ thống xử lý đúng nhánh.
9. Dừng và mở lại phiên, xem learning report.
10. Trình bày bảng baseline/ablation thực tế và một trường hợp hệ thống chưa xử lý tốt.

Demo là minh họa hoạt động. Kết luận hiệu quả dựa trên toàn bộ evaluation, không dựa riêng vài tình huống đã chuẩn bị.

## 30. Elevator pitch

> Nhóm xây dựng trợ lý AI hỗ trợ học Toán THCS–THPT theo phương pháp Socratic trên khoảng 30–50 khái niệm lõi thuộc Toán số, Đại số và Hàm số. Hệ thống phân tích bước giải để chẩn đoán lỗi, dùng Student Model và Bayesian Knowledge Tracing theo dõi trạng thái kiến thức, kết hợp Knowledge Graph và RAG để lựa chọn nội dung, rồi để AI Agent chọn chiến lược gợi mở trong vòng hội thoại do LangGraph điều phối. Nhóm đánh giá khả năng phát hiện misconception, dự đoán kết quả học tập tiếp theo và chất lượng chiến lược thích ứng bằng dữ liệu có nhãn, rubric và thí nghiệm ablation.

## 31. Core của toàn đồ án

```text
Bằng chứng từ câu trả lời/bước giải
       + Trạng thái kiến thức BKT và mức đủ dữ liệu
       + Giả thuyết misconception
       + Quan hệ prerequisite đã duyệt
       + Nội dung truy xuất đúng mức hỗ trợ
                         |
                         v
              Quyết định sư phạm có căn cứ
                         |
                         v
              Câu hỏi/gợi ý được kiểm tra
                         |
                         v
              Bằng chứng học sinh ở lượt sau
```

Hợp đồng observation, độ đúng của analyzer và thiết kế evaluation là điều kiện để các module kết hợp có ý nghĩa. Từng module cần chỉ ra được input, output, fallback, phiên bản và phép đo.

## 32. Nguồn tham khảo

- [FoundationalASSIST: dataset card, trường dữ liệu và định nghĩa điểm](https://huggingface.co/datasets/ASSISTments/FoundationalASSIST).
- [ASSISTments Data Mining Competition 2017: dataset và liên kết mô tả cột](https://sites.google.com/view/assistmentsdatamining/dataset).
- [Junyi Academy Online Learning Activity Dataset](https://www.kaggle.com/datasets/junyiacademy/learning-activity-public-dataset-by-junyi-academy).
- [pyBKT: thư viện, biến thể và bài nghiên cứu nền tảng](https://github.com/CAHLR/pyBKT).
- [MathDial, Findings of EMNLP 2023](https://aclanthology.org/2023.findings-emnlp.372/).
- [LangGraph: Workflows and agents](https://docs.langchain.com/oss/python/langgraph/workflows-agents).
- [SymPy: giải phương trình đại số và các giới hạn cần lưu ý](https://docs.sympy.org/latest/guides/solving/solve-equation-algebraically.html).
- [Chương trình GDPT tổng thể 2018, Bộ GDĐT](https://moet.gov.vn/content/tintuc/Lists/News/Attachments/8421/chuong-trinh-tong-the-ctgdpt-2018.pdf).

Chương trình tổng thể chỉ cung cấp bối cảnh. Khi chốt grade/learning objective, phải bổ sung và đối chiếu **văn bản chương trình môn Toán**, ghi nguồn cụ thể ở registry. Các nguồn tham khảo được rà cho lần chỉnh kế hoạch ngày 20/09/2026; khi lấy dataset, lưu phiên bản và ngày tải thực tế.

## 33. Kết luận

Phạm vi giữ nguyên theo nội dung đăng ký: **30–50 khái niệm Toán số, Đại số và Hàm số THCS–THPT**, đủ **BKT, Student Model, RAG, Knowledge Graph, AI Agent và LangGraph**, không bao gồm Hình học. Kế hoạch dùng mục tiêu 40 concept, chia việc song song cho 3 người trong 12 tuần.

Khả năng hoàn thành phụ thuộc vào kỷ luật biên soạn/kiểm duyệt nội dung, tích hợp từ tuần 3–4 và khóa thực nghiệm đúng mốc. Ưu tiên là một hệ thống đủ độ phủ, có cơ chế thích ứng được kiểm chứng và kết quả báo cáo trung thực; không mở thêm tính năng ngoài yêu cầu trước khi hoàn thành những phần này.
