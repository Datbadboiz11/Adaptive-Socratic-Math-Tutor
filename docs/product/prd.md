# PRODUCT REQUIREMENTS DOCUMENT — VIN-02

**Dự án:** Adaptive Socratic Math Tutor  
**Tên đề tài:** Nghiên cứu và xây dựng trợ lý AI dạy học Toán theo phương pháp Socratic thích ứng sử dụng AI Agent  
**Phiên bản:** 0.2 — ngày 25/09/2026  
**Trạng thái:** Draft để triển khai và kiểm chứng bằng pilot; chưa phải kết quả thực nghiệm  
**Nhóm / thời gian:** 3 thành viên / 12 tuần

## 1. Mục đích và quan hệ giữa tài liệu

PRD quy định hành vi sản phẩm, phạm vi nghiệm thu và tiêu chí kiểm tra. [Brief](brief.md) tóm tắt mục tiêu và giá trị; [plan](../planning/project-plan.md) mô tả phương pháp, danh mục concept và kế hoạch thực nghiệm chi tiết. Bản 0.2 đồng bộ các quyết định từ plan, thay các mô tả cũ về cập nhật sau từng attempt, giải thích trực tiếp bài hiện tại, prototype tuần 8 và baseline cộng dồn.

Khi thay phạm vi, observation, policy, dữ liệu hoặc tiêu chí đánh giá, ghi quyết định và cập nhật các tài liệu liên quan trong cùng lần thay đổi. Không dùng brief để suy ra ngoại lệ với PRD. Những ngưỡng ghi là ban đầu phải được thử trên dev rồi khóa trước test; không được hạ theo kết quả test để tuyên bố đạt.

## 2. Bài toán, người dùng và mục tiêu

### 2.1. Bài toán sản phẩm

Học sinh cần biết bước nào cần kiểm tra và nhận mức hỗ trợ phù hợp để tự giải tiếp. Hệ thống phân tích bằng chứng học tập, duy trì Student Model qua các phiên và chọn can thiệp Socratic có thể truy vết. Khả năng giải đúng bài chưa đủ chứng minh khả năng dạy phù hợp.

Giá trị dự kiến là cải thiện chẩn đoán và lựa chọn can thiệp so với baseline cụ thể. Không khẳng định chung mọi chatbot đều không lưu lịch sử hoặc không cá nhân hóa; không coi mastery tăng là bằng chứng trực tiếp về learning gain.

### 2.2. Người dùng

- **Chính:** học sinh THCS–THPT luyện các dạng Toán cơ bản đến trung bình trong danh mục; có thể nhập văn bản, biểu thức và các bước giải.
- **Phụ:** giáo viên/người hướng dẫn xem kết quả được phép truy cập. Dashboard riêng không phải điều kiện của vòng học cốt lõi.
- **Nhóm biên soạn:** quản lý nội dung, review và phiên bản bằng file/script; không yêu cầu xây CMS hay hệ quản lý lớp học.

### 2.3. Mục tiêu

| Mã | Mục tiêu | Bằng chứng nghiệm thu |
|---|---|---|
| G1 | Xác minh bước giải và đề xuất giả thuyết lỗi | Bộ bước giải có nhãn, ca cách giải khác và ca chưa đủ bằng chứng |
| G2 | Theo dõi kiến thức theo skill | Observation hợp lệ, BKT tái lập, dự đoán trước cập nhật |
| G3 | Chọn hỗ trợ theo người học | Decision log và so sánh chất lượng can thiệp có kiểm soát |
| G4 | Gợi mở đúng toán, đúng mức hỗ trợ | Rubric, kiểm tra tiết lộ và lỗi toán nghiêm trọng |
| G5 | Sử dụng KG/RAG có căn cứ | Edge/content IDs đã dùng, relevance và ablation |
| G6 | Dùng được qua nhiều phiên | Retry, resume, report và kiểm tra tách biệt người học |

## 3. Phạm vi và định nghĩa

### 3.1. Phạm vi nghiệm thu

- **30–50 concept**, mục tiêu **40**, thuộc Toán số, Đại số và Hàm số, phủ cả THCS và THPT. Danh mục N01–N10, A01–A10, E01–E10, F01–F10 tại mục 5 của plan là danh mục đề xuất cần rà soát ở tuần 1–2.
- Mỗi concept có mục tiêu, lớp đã đối chiếu chương trình, skill, prerequisite đã duyệt, dạng bài hỗ trợ, tối thiểu 6 bài thuộc ít nhất 3 họ mẫu, ít nhất 3 ví dụ giải, lỗi thường gặp, hint ladder, test và người review.
- Bài hỗ trợ được giới hạn theo dạng đã mô tả. Học sinh chủ yếu làm bài từ problem bank; đề tự nhập chỉ được tiếp nhận khi xác định được dạng hỗ trợ và dữ liệu để kiểm chứng. Ngoài phạm vi không được tự chấm sai hoặc cập nhật BKT.
- Hàm số có thể dùng công thức, bảng giá trị và đồ thị sinh từ dữ liệu; không yêu cầu đọc hình ảnh đầu vào.
- Concept rộng như các phép tính phân thức hoặc mũ/logarit phải tách hành vi đo trong registry. Không bắt buộc một concept chỉ có một skill.

**Prototype tuần 4:** đủ module và 8–10 concept đại diện. **Bản nghiệm thu:** đủ danh mục 30–50 đã chốt, mục tiêu 40. Khi trễ không được dùng prototype ít concept thay bản nghiệm thu; thay danh mục phải ghi quyết định, vẫn giữ phạm vi đã đăng ký và cập nhật ma trận độ phủ.

### 3.2. Ngoài phạm vi bắt buộc

Hình học; OCR/ảnh/chữ viết tay; voice; mobile native; LMS đầy đủ; fine-tuning; multi-agent/GraphRAG phức tạp; triển khai hàng nghìn người dùng; chứng minh hiệu quả học tập dài hạn. Giới hạn/đạo hàm chỉ cân nhắc sau khi hoàn tất danh mục và không vượt 50 concept.

### 3.3. Thuật ngữ vận hành

| Thuật ngữ | Định nghĩa |
|---|---|
| Concept | Đơn vị nội dung trên graph |
| Skill | Hành vi quan sát được, có quy tắc chấm và dùng để theo dõi BKT |
| Turn | Một lượt tương tác; không mặc định là bằng chứng đúng/sai |
| Attempt | Một lần trả lời cho bài/bước; có thể là sửa lại sau hỗ trợ |
| Opportunity | Bài/bước đo một skill đã xác định, có ID và mục tiêu đo |
| Observation hợp lệ | Kết quả đầu tiên có thể xác minh của opportunity đủ điều kiện để cập nhật BKT |
| Tự làm / độc lập | Không có trợ giúp trực tiếp cho opportunity đang đo; không có nghĩa chưa từng học skill đó hoặc các quan sát độc lập thống kê |
| Mastery | Xác suất trạng thái biết skill theo mô hình BKT; không phải điểm thi hoặc tỷ lệ nội dung hiểu chắc chắn |
| Misconception | Giả thuyết hiểu sai khái niệm; trạng thái và mức bằng chứng phải được phân biệt với lỗi thao tác |

Lịch sử hướng dẫn cùng skill, độ tương tự bài và nguồn sinh vẫn được lưu. Bài sửa lại không trở thành opportunity mới bằng cách đổi ID. Bài chỉ thay số ngay sau ví dụ được ghi là luyện tập gần; điều kiện dùng làm observation phải được quy định trước trong protocol, không mặc định là bằng chứng chuyển giao mạnh. BKT chuẩn chưa mô hình hóa đầy đủ việc học trong lượt có hỗ trợ; các lượt này vẫn được lưu và dùng trong policy.

## 4. Hành trình học và nguyên tắc bắt buộc

```text
Đăng nhập → Nạp hồ sơ hoặc prior khi chưa có dữ liệu
    → Chọn concept / chẩn đoán ngắn tùy chọn → Chọn bài đã duyệt
    → Nhận bước giải → Parser / xác minh toán / giả thuyết lỗi
    → Kiểm tra observation → Cập nhật BKT nếu đủ điều kiện
    → Agent đọc state, chọn công cụ/hành động khi cần
    → Policy gate → Sinh phản hồi → Kiểm tra toán và mức tiết lộ
    → Lưu kết quả / checkpoint → Hiển thị → Chờ học sinh
    → Tiếp tục / bài mới / backtrack có quay lại / dừng → Learning report
```

- Một lần sai không đủ khẳng định misconception bền vững; không chấm sai các skill khác chỉ vì lỗi kéo theo.
- Không tự đưa nghiệm/lời giải hoàn chỉnh của bài đang làm ở bất kỳ hint level nào. Khi cần giải thích, dùng ví dụ khác; nếu thao tác sắp gợi ý chính là đáp án cuối thì chuyển sang ví dụ khác.
- Khi học sinh đã tự đưa đáp án đúng được xác minh, có thể xác nhận đúng; không cần che kết quả học sinh đã tự tìm được.
- Chỉ node xác định được cập nhật BKT; Agent không tự sửa mastery hay tham số.
- KG/RAG được gọi khi phù hợp mục tiêu, không bắt buộc mọi turn phải truy xuất. Không cho LLM tự sinh câu trả lời thay học sinh.
- Dữ liệu của học sinh này không được dùng để trả report/state cá nhân của học sinh khác.

### Ví dụ chuẩn dùng xuyên tài liệu

Bài `2(x - 3) = 10`; học sinh viết `2x - 3 = 10`, `2x = 13`, `x = 6.5`. **Bước sai đầu tiên là 1**, đánh số các bước học sinh từ 1 và không tính đề. Hai phép biến đổi sau hợp lệ theo phương trình học sinh đang có.

Analyzer xác minh lỗi phân phối và đề xuất `M_DIST_01` ở trạng thái `suspected`. Skill phân phối phải được xác định từ cấu trúc bước/dạng bài đã duyệt. Câu hỏi có thể là: “Nếu viết hai nhóm (x - 3) thành (x - 3) + (x - 3), phần -3 xuất hiện bao nhiêu lần?”

Sửa đúng sau câu hỏi này được ghi là có hỗ trợ. Bài mới tự làm cung cấp bằng chứng tiếp theo nếu đủ điều kiện; không gán sẵn mức tăng mastery hoặc bắt buộc backtrack chỉ vì mastery thấp.

## 5. Functional Requirements

**P0:** bắt buộc ở bản nghiệm thu. **P1:** bổ sung sau khi P0 ổn định. **P2:** tùy chọn. Prototype tuần 4 triển khai một phần độ phủ nhưng phải chứng minh vòng xử lý cốt lõi; không thay đổi định nghĩa P0 của bản nghiệm thu.

### FR-01 — Hồ sơ và quyền truy cập · P0

Học sinh đăng nhập, tải hồ sơ và lịch sử của mình. Không yêu cầu tên thật, địa chỉ hoặc số điện thoại cho chức năng tutoring.

**Nghiệm thu:**

- FR01-AC1: Hai tài khoản thử nghiệm có state/mastery tách biệt; tài khoản A không đọc hoặc sửa session/report của B bằng cách thay ID.
- FR01-AC2: Hồ sơ mới hiển thị “chưa đủ dữ liệu”, nguồn prior và không bị mặc định yếu mọi skill.
- FR01-AC3: Nếu bật dashboard giáo viên, chỉ hồ sơ được cấp quyền mới xem được; có quy tắc cấp quyền đơn giản, không cần quản lý trường/lớp.

### FR-02 — Chọn chủ đề và đầu vào chẩn đoán · P0/P1

Chọn concept trong phạm vi và vào bài học là P0. Bài diagnostic riêng là P1; khi chưa có diagnostic vẫn phải có luồng chọn bài cho người mới.

**Nghiệm thu:**

- FR02-AC1: Chọn một concept đã công bố sẽ trả bài hợp lệ hoặc thông báo chưa có bài phù hợp; không tạo bài chưa duyệt để lấp chỗ trống.
- FR02-AC2: Khi có mastery, quyết định chọn bài ghi cả evidence count và lịch sử hỗ trợ; prior không bị trình bày như kết quả kiểm tra.
- FR02-AC3: Khi nhận đề tự nhập ngoài dạng hỗ trợ, hướng người học về dạng có hỗ trợ, không thêm observation sai.

### FR-03 — Chọn bài và tạo opportunity · P0

Chọn từ problem bank đã duyệt theo mục tiêu, skill, độ khó, lịch sử và prerequisite khi cần.

**Nghiệm thu:**

- FR03-AC1: Bài có problem ID, version, concept/skill mapping, dạng, miền xác định, độ khó và đáp án/reference dành riêng cho validator.
- FR03-AC2: Opportunity ghi student, problem/version, skill mục tiêu, nguồn bài, mức tương tự bài vừa học và trạng thái hỗ trợ. Bài nhiều skill có thể có các opportunity theo bước được định nghĩa rõ; không cập nhật tất cả skill từ đáp án cuối.
- FR03-AC3: Mục tiêu đo được xác định từ task/step contract đã duyệt; không suy ra hàng loạt skill yếu chỉ từ một lỗi. Chưa quy được skill thì hỏi chẩn đoán trước khi tạo observation.
- FR03-AC4: Hết bài mới phù hợp phải báo rõ hoặc dùng bài ôn có nhãn; không gọi bài lặp là phép kiểm tra chuyển giao độc lập.

### FR-04 — Nhập câu trả lời và bước giải · P0

Nhận văn bản, biểu thức có cấu trúc, nhiều dòng hoặc chỉ đáp án cuối. Giao diện phân biệt đề, bài làm, ví dụ hỗ trợ và bài kiểm tra mới.

**Nghiệm thu:**

- FR04-AC1: Hiển thị công thức và giữ thứ tự bước học sinh; đánh số từ 1, không tính dòng đề được nhắc lại.
- FR04-AC2: Với input rỗng/mơ hồ/không phân tích được, trả hướng dẫn nhập lại và không ghi sai BKT.
- FR04-AC3: Đáp án cuối có thể được chấm khi đủ điều kiện nhưng không bịa bước sai; bài nhiều skill chưa đủ bằng chứng thì hỏi thêm.
- FR04-AC4: Mỗi lần gửi có request ID; UI thể hiện đang xử lý/lỗi/có thể thử lại và dùng lại request ID khi retry cùng lần gửi.

### FR-05 — Xác minh và phân tích bước giải · P0

Kết hợp parser giới hạn, luật theo dạng, kiểm tra toán có điều kiện và LLM extraction. Pydantic chỉ kiểm tra cấu trúc. Bộ kiểm tra toán phải có ma trận dạng bài, phép kiểm tra và điều kiện trả `unverified`.

**Nghiệm thu:**

- FR05-AC1: Trả `verified_correct`, `verified_incorrect`, `unverified` hoặc `needs_clarification`, cùng bằng chứng và phương pháp xác minh; không bắt buộc boolean đúng/sai khi chưa chấm được.
- FR05-AC2: Với ví dụ chuẩn, chỉ ra bước 1; không tạo hai lỗi mới từ các bước kéo theo.
- FR05-AC3: Chấp nhận `2(x-3)=10 → x-3=5` nếu hợp lệ, dù khác reference solution.
- FR05-AC4: Kiểm tra miền xác định/điều kiện khi xử lý phân thức, phương trình, bất phương trình, căn, mũ/logarit. Thử số tìm phản ví dụ không được coi là chứng minh tương đương.
- FR05-AC5: Câu trả lời bằng lời chưa được rule hoặc đáp án duyệt xác minh có thể nhận phản hồi thận trọng nhưng không thành observation chuẩn.
- FR05-AC6: Báo coverage và lỗi theo từng dạng trong evaluation; không chỉ đo accuracy trên ca dễ đã quyết định.

### FR-06 — Giả thuyết misconception · P0

Tách lỗi quan sát được, họ lỗi và giả thuyết hiểu sai. Confidence tự báo cáo của LLM không phải xác suất đã hiệu chỉnh hoặc điều kiện duy nhất để cập nhật state.

**Nghiệm thu:**

- FR06-AC1: Cho phép không có candidate, nhãn unknown/other và trạng thái chưa đủ bằng chứng; không ép mọi lỗi vào taxonomy.
- FR06-AC2: Một lỗi phân phối đơn lẻ tạo candidate `suspected`; lịch sử/câu hỏi chẩn đoán bổ sung bằng chứng theo guideline để chuyển trạng thái `supported`, không khẳng định suy nghĩ bên trong học sinh.
- FR06-AC3: Lưu evidence IDs và skill liên quan; Agent có thể dùng candidate để hỏi chẩn đoán trước khi backtrack.
- FR06-AC4: Lưu lịch sử thay đổi giả thuyết, kể cả bị bác bỏ; report phân biệt suspected với supported.

### FR-07 — Student Model và BKT · P0

Lưu P(L), số observation đủ điều kiện, lịch sử hỗ trợ, prediction trước đáp án, state trước/sau, timestamp và parameter version. Công thức online theo mục 8.3 của plan; đối chiếu implementation với tính tay và thư viện.

**Nghiệm thu:**

- FR07-AC1: Câu trả lời đầu tiên tự làm, được xác minh và quy được một skill cập nhật tối đa một lần cho student/opportunity/skill. Ghi dự đoán trước khi dùng đáp án.
- FR07-AC2: Sửa sau hint, xin hint, chat xã giao, dừng phiên, input chưa chấm được hoặc lặp opportunity không thêm observation chuẩn. Vẫn lưu sự kiện để policy/report sử dụng.
- FR07-AC3: Retry cùng request, resume hoặc gửi đồng thời không tạo observation trùng; observation và mastery được ghi nhất quán.
- FR07-AC4: P(L) nằm trong [0,1], tham số không suy biến; replay cùng log và parameter version cho cùng kết quả trong sai số số học đã định nghĩa.
- FR07-AC5: Skill chưa đủ dữ liệu dùng default/pooled parameters có nhãn nguồn. Đổi tham số tạo version mới và có quy tắc replay/khởi tạo lại, không âm thầm trộn state.
- FR07-AC6: Không dùng tham số benchmark nước ngoài cho taxonomy Việt Nam nếu chưa ghi căn cứ ánh xạ; không coi benchmark đó là xác nhận mastery người học Việt Nam.

### FR-08 — Knowledge Graph · P0

Lưu concept và cạnh có nguồn/version/người duyệt. `PREREQUISITE_OF` hướng A → B nghĩa là A cần trước B; `RELATED_TO` và `PART_OF` không thay thế prerequisite. Chọn concept tiếp theo là quyết định động, không cần cạnh `NEXT_CONCEPT` cố định.

**Nghiệm thu:**

- FR08-AC1: Kiểm tra prerequisite DAG, cạnh đảo chiều/ID thiếu khi nạp registry; dữ liệu lỗi không được công bố.
- FR08-AC2: Truy xuất prerequisite trực tiếp và tối đa 2 tầng với edge IDs. Agent ghi ứng viên nào được dùng/bỏ và bằng chứng học sinh liên quan.
- FR08-AC3: Graph không tự kết luận học sinh yếu toàn bộ prerequisite. Trường hợp chưa có bằng chứng phải chẩn đoán trước khi coi đó là điểm yếu.
- FR08-AC4: Backtrack lưu bài gốc và return stack, không lặp concept đã ghé trong cùng nhánh; quay lại được sau khi hoàn tất hỗ trợ.

### FR-09 — RAG và truy xuất nội dung · P0

Lấy nội dung đã duyệt theo mục tiêu và mức hỗ trợ: lọc metadata rồi xếp hạng ngữ nghĩa; biết ID thì có thể lấy trực tiếp. KB chứa lời giải phục vụ validator nhưng generator chỉ nhận phần được phép.

**Nghiệm thu:**

- FR09-AC1: Chunk có content ID, concept/skill, loại, nguồn, version, độ khó, lớp, review status và disclosure level. Test filter không trả nội dung sai scope hoặc chưa duyệt.
- FR09-AC2: Generator không nhận reference solution của bài hiện tại từ retrieval. Log ghi content IDs thực tế được đưa vào context; không gắn nguồn chưa lấy.
- FR09-AC3: Không có tài liệu phù hợp thì dùng template đã duyệt hoặc hỏi làm rõ; không tự bịa citation.
- FR09-AC4: Đánh giá retrieval bằng query/relevance labels; chốt K trên dev và so với baseline chỉ lọc metadata.

### FR-10 — Agent và pedagogical policy · P0

Agent chọn hành động từ tập giới hạn; policy gate kiểm tra tính hợp lệ trước khi sinh phản hồi. Tách quyết định động của Agent khỏi luật bắt buộc và workflow LangGraph.

Hành động chuẩn: `clarify`, `diagnose`, `minimal_hint`, `conceptual_question`, `backtrack`, `scaffold`, `check_transfer`, `next_problem`, `end_session`. Tự sửa, giải thích khái niệm hoặc đổi độ khó là mục đích/mức hỗ trợ của các hành động này; không duy trì nhiều bộ tên strategy mâu thuẫn.

**Nghiệm thu:**

- FR10-AC1: Decision có action, skill mục tiêu, evidence IDs, mức hint, lý do ngắn và content/edge IDs nếu đã dùng. Không yêu cầu lưu chuỗi suy nghĩ nội bộ.
- FR10-AC2: Ưu tiên làm rõ → xác minh/chẩn đoán → hỗ trợ → kiểm tra chuyển giao → chuyển bài. Mastery cao không ghi đè lỗi mới; mastery thấp không tự động buộc backtrack khi học sinh đang làm đúng.
- FR10-AC3: Trên các cặp tình huống mà lịch sử/bằng chứng tạo nhu cầu hỗ trợ khác nhau, hành động phải thuộc tập phù hợp được gán nhãn. Không yêu cầu mọi cặp khác mastery đều có action khác.
- FR10-AC4: Action bị cấm hoặc thiếu bằng chứng phải bị gate từ chối và chuyển fallback hợp lệ; log giữ đề xuất và quyết định sau gate.
- FR10-AC5: Agent không có quyền ghi mastery, sửa tham số BKT hoặc thay dữ liệu người học ngoài các thao tác được định nghĩa.

### FR-11 — LangGraph và tính nhất quán lượt xử lý · P0

LangGraph nạp state, điều phối node xác định và Agent, checkpoint rồi chờ input. Tool calls và sinh lại phản hồi có ngân sách.

**Nghiệm thu:**

- FR11-AC1: State liên kết student/session/turn/request/opportunity, state version, assessment, observation eligibility, mastery, evidence count, hypothesis, hint level, return stack, tool budget và decision.
- FR11-AC2: Mỗi lượt kết thúc ở trạng thái chờ học sinh hoặc kết thúc phiên; không tự tạo input học sinh để chạy tiếp vòng lặp.
- FR11-AC3: Giới hạn khởi đầu tối đa 3 tool calls cho quyết định và 1 lần sinh lại phản hồi/lượt. Hết budget/timeout/lỗi schema dùng policy luật và template; log nguyên nhân fallback.
- FR11-AC4: Mô phỏng lỗi sau DB commit nhưng trước checkpoint không làm BKT cập nhật lại khi resume; có đối soát/replay hoặc cơ chế khôi phục tương đương.
- FR11-AC5: Hai request dùng cùng state version không ghi đè âm thầm. Request đến sau nhận trạng thái đang xử lý/xung đột để tải lại và gửi tiếp phù hợp; không ghép hai câu trả lời thành một opportunity mới ngoài ý muốn.

### FR-12 — Sinh và kiểm tra phản hồi Socratic · P0

Phản hồi bám bằng chứng, ngắn và ưu tiên một câu hỏi rõ ràng. Có thể xác nhận kết quả, giải thích ví dụ khác hoặc thông báo kết thúc mà không buộc mọi phản hồi phải là câu hỏi.

**Nghiệm thu:**

- FR12-AC1: Kiểm tra toán, điều kiện áp dụng và mức tiết lộ trước hiển thị. Phản hồi bị phát hiện sai/tiết lộ được sinh lại tối đa một lần rồi dùng fallback đã duyệt nếu vẫn không đạt.
- FR12-AC2: Generator không tự đưa nghiệm hoặc lời giải hoàn chỉnh bài hiện tại ở hint level cao, khi xin đáp án hoặc khi sắp hết lượt. Có thể xác nhận đáp án học sinh đã tự đưa ra và được xác minh.
- FR12-AC3: Nếu phần gợi ý chính là thao tác cho ra đáp án cuối, chuyển sang ví dụ khác; ví dụ phải có nội dung riêng và được gắn nhãn rõ.
- FR12-AC4: Chỉ stream trạng thái xử lý hoặc phản hồi đã qua kiểm tra; không phát raw output rồi rút lại sau khi lộ đáp án.
- FR12-AC5: Đánh giá độc lập đầu ra đã hiển thị để đo lỗi còn lọt; việc validator cho qua không tự trở thành nhãn đúng toán.

### FR-13 — Hint ladder · P0

| Mức | Hỗ trợ được phép |
|---|---|
| 0 | Câu hỏi gợi mở/chẩn đoán |
| 1 | Nhắc kiến thức hoặc đề nghị kiểm tra thao tác |
| 2 | Gợi ý cụ thể hơn nhưng học sinh vẫn thực hiện bước suy luận |
| 3 | Chia nhỏ thao tác hoặc minh họa một phần bằng bài khác |
| 4 | Giải thích khái niệm bằng ví dụ khác, sau đó kiểm tra tự làm |

**Nghiệm thu:**

- FR13-AC1: Tăng mức theo tiến triển, yêu cầu hỗ trợ và lịch sử; không tăng chỉ vì số tin nhắn hoặc retry.
- FR13-AC2: Không lặp nguyên văn câu hỏi; trường hợp hỏi khác chữ nhưng cùng nội dung gây bế tắc được đưa vào đánh giá lặp nhiều lượt.
- FR13-AC3: Sau hỗ trợ, lưu kết quả có hỗ trợ và mức đã dùng; không coi là nhiều lần làm đúng độc lập.
- FR13-AC4: `Explanation` luôn tuân FR-12; việc hết lượt không mở quyền tiết lộ bài hiện tại.

### FR-14 — Dừng, chuyển bài và kết thúc phiên · P0

Heuristic ban đầu để xem xét chuyển concept: P(L) ≥ 0.8; ít nhất 3 observations hợp lệ; 2 bài tự làm gần nhất đúng thuộc mẫu khác nhau; không còn giả thuyết lỗi quan trọng chưa kiểm tra và prerequisite phù hợp. Đây không phải ngưỡng thành thạo phổ quát.

**Nghiệm thu:**

- FR14-AC1: Hai lần sửa đúng sau hint không thỏa điều kiện hai bài tự làm. Policy kiểm tra bằng evidence log, không chỉ attempt count.
- FR14-AC2: Nếu tới hint 3 vẫn mắc kẹt, đổi cách hỗ trợ hoặc kiểm tra prerequisite. Sau 6 lượt hỗ trợ tại cùng nút mắc kẹt phải thoát nhánh, chuyển phương án hoặc cho kết thúc; bộ đếm không reset chỉ do rephrase/retry.
- FR14-AC3: Backtrack tối đa 2 tầng, không vòng lặp; phân biệt dừng bài, chuyển concept và kết thúc phiên.
- FR14-AC4: Học sinh có thể dừng bất kỳ lúc nào; không ghi thành câu trả lời sai. Phiên dừng có thể resume hoặc bắt đầu bài khác theo lựa chọn.
- FR14-AC5: Ngưỡng được thử trên dev, lưu config/version và khóa trước test; không sửa theo kết quả test để đạt mục tiêu.

### FR-15 — Lưu và tiếp tục phiên · P0

Lưu bài, các lượt, hypotheses, hỗ trợ, observation, decision, mastery và vị trí học hiện tại.

**Nghiệm thu:**

- FR15-AC1: Tải lại trang hoặc đăng nhập lại nạp đúng bài/version, lịch sử, hint level và return stack; không reset mastery.
- FR15-AC2: Retry sau mất mạng trả kết quả đã lưu hoặc trạng thái đang xử lý; không chạy lại side effect đã hoàn tất.
- FR15-AC3: Phiên bị gián đoạn có trạng thái rõ. Nếu đang xử lý khi dừng, khôi phục theo trạng thái đã commit; không tạo thêm observation từ thao tác dừng.

### FR-16 — Tiến trình học sinh · P0 cơ bản / P1 mở rộng

Hiển thị skill đã luyện, mastery ước lượng, evidence count, nguồn tham số, ngày cập nhật và trạng thái thiếu dữ liệu. Biểu đồ nâng cao là P1.

**Nghiệm thu:**

- FR16-AC1: Người mới thấy “chưa đủ dữ liệu”; không chỉ hiện một phần trăm như điểm thi.
- FR16-AC2: Giá trị hiển thị khớp state/version và số observations; kết quả sau hỗ trợ không cộng vào số lần tự làm.
- FR16-AC3: Hypothesis được gắn suspected/supported/đã bác bỏ phù hợp; không biến mọi candidate thành danh sách điểm yếu đã xác nhận.

### FR-17 — Dashboard giáo viên · P2

Nếu triển khai, cho người được cấp quyền xem report, lịch sử lỗi và gợi ý ôn; không xây quản lý trường/lớp.

**Nghiệm thu khi có tính năng:**

- FR17-AC1: Chỉ xem học sinh được cấp quyền; dữ liệu nhất quán với report và log.
- FR17-AC2: Hiển thị giới hạn của mastery và giả thuyết lỗi giống giao diện học sinh; không suy luận xếp hạng năng lực từ vài observations.

### FR-18 — Learning report · P0

Report cuối phiên và khi quay lại gồm concept/skill đã luyện, kết quả tự làm và có hỗ trợ, lỗi có bằng chứng, state trước/sau và nội dung gợi ý ôn.

**Nghiệm thu:**

- FR18-AC1: Từng số liệu về bài/observation/mastery đối soát được với log; phiên không có observation mới không hiển thị mức tăng suy đoán.
- FR18-AC2: Bài đúng sau hỗ trợ không được mô tả là đã tự làm đúng; không suy ra “đã thành thạo” chỉ từ kết thúc bài.
- FR18-AC3: Recommendation có căn cứ, phân biệt prerequisite ứng viên với phần đã xác nhận cần ôn. Dữ liệu chưa đủ được nói rõ.
- FR18-AC4: Nội dung report tôn trọng chính sách tiết lộ; không tự chèn lời giải hoàn chỉnh của bài học sinh chưa tự giải xong.

## 6. Dữ liệu và hợp đồng đầu ra

### 6.1. Nguồn dữ liệu

- **ASSISTments 2017:** KT chính ban đầu. Audit release, label, skill, thứ tự, hint/scaffold/attempt; chọn một release chuẩn, không nối bản full và training chồng lặp. `training_label.csv` không phải nhãn đúng/sai từng bài; `Ln`, `AveKnow` không là ground truth mastery. Loại biến biết tương lai và tổng hợp toàn lịch sử khỏi đầu vào dự đoán.
- **Junyi:** benchmark bổ sung khi pipeline chính hoàn thành. Đối chiếu `ucid` với `Info_Content` trước khi xem như skill; báo riêng dataset.
- **FoundationalASSIST:** bổ sung khi có quyền truy cập; kiểm tra định nghĩa score và hỗ trợ. Không là phụ thuộc chặn tiến độ.
- **KB và bộ đánh giá tiếng Việt:** nội dung tự biên soạn hoặc có quyền sử dụng, đối chiếu chương trình môn Toán; LLM chỉ hỗ trợ bản nháp, phải review toán và sư phạm.

Nguồn tham khảo, giới hạn dữ liệu công khai và chi tiết preprocessing tại mục 11, 16, 32 của plan. Lưu version/ngày tải/điều kiện sử dụng của bản thực tế; không tự gộp skill chỉ vì tên gần giống.

### 6.2. Quy mô công việc mục tiêu

| Thành phần | Mục tiêu |
|---|---|
| Concept hoàn chỉnh | 40; phạm vi nghiệm thu 30–50 đã chốt |
| Prerequisite edges | Khoảng 50–100 theo quan hệ đã duyệt, không thêm cho đủ số |
| Bài tập | 240–300; ≥6/concept, ≥3 họ mẫu/concept |
| Ví dụ giải | 120–160; ≥3/concept |
| Misconception | 50–100 nhãn chi tiết dưới khoảng 12–20 họ lỗi |
| Hint | Ít nhất một ladder đủ mức/concept, kiểm tra template khi tái sử dụng |
| Records bước giải | 800–1.200 |
| Tình huống thích ứng | 160–200, tối thiểu 4/concept |
| Query có relevance labels | 120–200 |

Các số trên là ngân sách công việc, không phải cỡ mẫu bảo đảm ý nghĩa thống kê. Một bài authoring có thể dùng làm ví dụ và sinh nhiều records, nhưng mọi biến thể cùng nguồn phải được quản lý khi chia tập. Nội dung test riêng không được đưa vào kho phục vụ generator.

### 6.3. Registry và kiểm duyệt

Registry là nguồn chuẩn, dùng ID ổn định và script đồng bộ PostgreSQL/Neo4j/index. Từng concept ghi mục tiêu, skill quan sát được, dạng bài hỗ trợ, cách xác minh, ca ngoài phạm vi, nguồn, reviewer và version. Mỗi dạng có cả ca đúng theo cách khác và ca không đủ bằng chứng.

| Nhóm dạng | Yêu cầu validator phải mô tả |
|---|---|
| Khai triển/thu gọn | Tương đương biểu thức trong miền đã khai báo |
| Phương trình | Điều kiện, tính hợp lệ của chuyển bước và tập nghiệm khi cần |
| Bất phương trình | Điều kiện đổi chiều, biểu diễn khoảng/tập |
| Bài toán bằng lời | Biến, đơn vị và mô hình phương trình được chấp nhận |
| Hàm số/căn/mũ/logarit | Miền xác định, mục tiêu đo và điều kiện dùng quy tắc |

Hai người thử guideline trên pilot, review chéo nội dung; test bước giải/tình huống được gán độc lập trước hòa giải, lưu cả nhãn ban đầu. Người đã xem test không dùng thông tin đó tinh chỉnh thành phần được đánh giá. Ghi giới hạn nếu chưa có người đánh giá độc lập bên ngoài; liên hệ giáo viên/chuyên gia từ tuần 1.

### 6.4. Hợp đồng dữ liệu tối thiểu

Tên field và enum phải được chốt cùng fixtures ở tuần 1; các ví dụ dưới đây thể hiện nội dung bắt buộc. Concept ID và skill ID có thể trùng khi mapping một-một nhưng vẫn là hai thực thể khác nhau.

| Record | Trường tối thiểu |
|---|---|
| Problem | ID/version, concept IDs, skill mapping, primary skill, template family/source group, difficulty, domain, question, reference/alternative methods, step-skill map, split, source, review status |
| Opportunity | ID, student/session, problem/version, target skill, step/task scope, assistance history, similarity/source, eligibility |
| Observation | ID, opportunity/skill, assessment/evidence IDs, correctness, prediction before update, parameter version, state before/after, timestamp |
| StudentState | student/session, version, current problem/opportunity, skill states/evidence counts, hypotheses, hint level, return stack, budget, status |
| PedagogicalDecision | action, target skill, evidence IDs, hint level, content/edge IDs, reason, gate result, fallback, config version |
| KB chunk | content ID/version, concept/skill, type, grade, difficulty, source, review status, disclosure level, embedding version |

Assessment minh họa cho ví dụ chuẩn:

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

Ví dụ này không tự bảo đảm observation đủ điều kiện. Observation Builder còn kiểm tra opportunity, trợ giúp, skill mapping và việc đã cập nhật hay chưa. Với ca chưa xác minh, correctness không bị ép thành false; hypothesis có thể null/unknown/other theo taxonomy đã chốt.

## 7. Kiến trúc và lựa chọn kỹ thuật

```text
Student UI → FastAPI → LangGraph nạp state/checkpoint
    → Parser → Mathematical Validator → Error Analyzer
    → Observation Builder → BKT nếu hợp lệ → Lưu state
    → Agent chọn công cụ/hành động
        ↔ Knowledge Graph / RAG / Problem Selector
    → Policy gate → Generator → Output checks
    → Lưu kết quả/checkpoint → Phản hồi → Chờ học sinh
```

| Thành phần | Lựa chọn ban đầu |
|---|---|
| UI | Next.js/React, render công thức |
| API/schema | FastAPI, Pydantic |
| Điều phối | LangGraph; LangChain tùy chọn |
| LLM | Một API model chính; chốt ID/version/cấu hình sau benchmark tuần 2 |
| Toán | SymPy + luật theo dạng + reference answers đã duyệt |
| Student Model | Python; pyBKT cho fit/benchmark và đối chiếu online |
| Lưu trữ/truy xuất | PostgreSQL + pgvector; không duy trì thêm Qdrant trong phạm vi cơ sở |
| Graph | Neo4j |
| Giao tiếp | HTTP trước; SSE bổ sung sau khi ổn định, chỉ phát nội dung đã kiểm tra |
| Triển khai | Docker Compose |
| Evaluation | Python scripts/config, raw outputs và log có version |

PostgreSQL lưu profiles, sessions/turns, registry, opportunities/observations, mastery/history, parameter versions, diagnosis history, decisions và evaluation runs. pgvector lưu embeddings cùng metadata/version; Neo4j đồng bộ graph từ registry. Unique constraint theo student/opportunity/skill, request idempotency và state version bảo vệ cập nhật.

Không cho Agent truy cập SQL/ghi state tùy ý. Benchmark tuần 2 đo độ đúng, structured output, tiếng Việt, latency và chi phí; chưa cam kết model cụ thể trước phép đo. Nếu embedding thay đổi, tạo lại index nhất quán. Cache phản hồi cá nhân hóa phải chứa student/state/config version để tránh dùng lẫn.

## 8. Non-functional Requirements

### NFR-01 — Reliability và khôi phục · P0

- Có regression cho mất mạng, timeout, schema lỗi, retry, resume, cạnh graph lỗi và hai request đồng thời.
- Log liên kết request/turn/opportunity/session và versions; phục hồi không lặp side effect BKT.
- Khi model/retrieval không khả dụng, trả fallback phù hợp hoặc thông báo có thể thử lại; không tự đánh giá học sinh sai vì lỗi dịch vụ.
- DB và checkpoint không nhất quán phải được phát hiện và đối soát; giao diện không hiển thị state suy đoán như đã lưu thành công.

### NFR-02 — Hiệu năng và chi phí · P0 đo lường

Mục tiêu kỹ thuật ban đầu: **p95 khoảng 10 giây/lượt** trên cấu hình thử đã mô tả. Đo từ lúc API nhận request hợp lệ đến khi có phản hồi đã kiểm tra và trạng thái cần thiết đã lưu; thời gian chờ học sinh không tính vào lượt. Streaming không thay thế full-completion latency.

Báo p50/p95, tỷ lệ lỗi/fallback, số model/tool calls, token và chi phí/lượt/phiên; ghi model, hardware, mạng, tải đồng thời, cache và số lượt đo. Không loại lượt fallback hoặc timeout khỏi báo cáo để cải thiện chỉ số. Chốt budget/API và cấu hình tải ở tuần 2 từ pilot, không suy rộng demo thành khả năng phục vụ quy mô lớn.

### NFR-03 — Dữ liệu người học và quyền truy cập · P0

- Dùng ID giả danh, tách tài khoản khỏi log học tập; free text có thể chứa thông tin nhận dạng dù ID đã giả danh.
- Trước pilot, thống nhất thông báo, sự đồng ý phù hợp, quyền dừng, phạm vi thu thập, thời gian lưu/xóa và người có quyền xem với người phụ trách.
- Nêu nội dung gửi nhà cung cấp LLM, loại thông tin nhận dạng không cần thiết. Dữ liệu thật/API key không vào repo hoặc public demo.
- Có thủ tục xóa dữ liệu theo ID với phạm vi đã công bố; không cần xây UI quản trị riêng. Demo dùng hồ sơ tổng hợp và ghi rõ nguồn.

### NFR-04 — Truy vết và tái lập · P0

Lưu assessment/evidence, điều kiện observation, prediction/state trước-sau, parameter version, content/edge IDs, action, gate result, hint, fallback và versions model/prompt/KB/config. Lý do quyết định là giải thích ngắn có thể kiểm tra, không phải chuỗi suy nghĩ nội bộ. Evaluation có config, split manifest, raw outputs và script tính metric.

### NFR-05 — Giới hạn thực thi và nội dung · P0

Parser có allowlist cú pháp, giới hạn độ dài và timeout; không thực thi input bằng eval hoặc parser không kiểm soát. Công cụ chỉ được thực hiện hành động có schema/quyền rõ. Nội dung học sinh và tài liệu retrieval là dữ liệu, không được ghi đè policy, quyền truy cập hoặc lệnh cập nhật BKT. Có ca kiểm tra input yêu cầu bỏ policy/đưa đáp án; xử lý theo FR-12.

## 9. Research Evaluation và mục tiêu chất lượng

### 9.1. Câu hỏi và chỉ số

| Câu hỏi | Thí nghiệm / chỉ số |
|---|---|
| RQ1a: BKT dự đoán kết quả tiếp theo ra sao? | KT benchmark so với tỷ lệ đúng theo skill và mô hình lịch sử đơn giản; log loss, AUC, Brier/calibration |
| RQ1b: BKT có cải thiện can thiệp? | Full/No-BKT/Heuristic; rubric ghép cặp và lỗi nghiêm trọng |
| RQ2: Graph giúp chọn prerequisite ra sao? | Full/No-KG trên tình huống phù hợp; tỷ lệ chọn trong tập chấp nhận được |
| RQ3: RAG giúp nội dung/hint ra sao? | Recall@K, nDCG@K; Full/No-RAG và chấm đầu ra |
| RQ4: Phát hiện lỗi/misconception chính xác đến đâu? | Bước sai đầu tiên, macro-F1 họ lỗi, support từng lớp, coverage và lỗi trên phần đã quyết định |
| RQ5: Agent có lợi gì so với luật? | Full/Rule-policy cùng thông tin và generator; rubric, latency, cost |

RQ1b và RQ4 là trọng tâm. Không yêu cầu mọi phép so sánh phải cải thiện có ý nghĩa thống kê; báo cả kết quả không cải thiện. Theo dõi trạng thái biết là biến ẩn: không lấy chính mastery suy luận làm nhãn thật.

### 9.2. Baseline và ablation

| Cấu hình | Thay đổi so với Full |
|---|---|
| Full | Analyzer + BKT + KG + RAG + Agent trong LangGraph |
| No-BKT | Bỏ mastery và tóm tắt suy từ BKT; giữ evidence log |
| Heuristic | Thay BKT bằng tỷ lệ đúng tối đa 5 observations hợp lệ gần nhất/skill và evidence count |
| No-KG | Bỏ truy graph/cạnh prerequisite và thông tin quan hệ đó trong metadata/prompt; giữ nhãn concept/skill |
| No-RAG | Bỏ truy xuất nội dung dạy; giữ đề, state, policy và validator |
| Rule-policy | Giữ analyzer/BKT/KG/RAG và generator; thay quyết định bằng luật đã chốt, vẫn chạy LangGraph |
| Socratic LLM | Prompt Socratic, cùng đề và cửa sổ hội thoại, không có Student Model dài hạn/KG/RAG; tham chiếu cấp hệ thống |

Các ablation giữ cùng analyzer, validator, bank và phần prompt chung; cùng model/version, cấu hình sinh, giới hạn đầu ra và policy tiết lộ. No-KG không loại được kiến thức có sẵn trong LLM; kết luận giới hạn ở giá trị graph được cung cấp rõ cho hệ thống. Ghi token/cost thực tế thay vì giả định ngân sách bằng nhau.

Đánh giá một lượt từ cùng lịch sử/state trước lượt để ghép cặp. Đánh giá nhiều lượt dùng các quỹ đạo riêng và ghi người học thật/script/mô phỏng; không coi các turn trong session là mẫu độc lập. Ngưỡng Heuristic chọn trên dev với ngân sách tương đương, không áp nguyên ngưỡng BKT.

### 9.3. Split, nhãn chuẩn và chống rò rỉ

- KT: chia theo học sinh train/dev/test; giữ thứ tự; fit trên train, chọn trên dev. Với test, dự đoán trước cập nhật và không refit tham số. Chronological split nếu làm thêm phải báo riêng.
- Bộ bước giải: mục tiêu authoring/dev/test khoảng 50/20/30, chia theo nhóm bài và họ mẫu; test phủ 40 concept, tối thiểu 4 records/concept gồm đúng/sai. Báo support; không kết luận chắc ở lớp rất ít mẫu.
- Tình huống thích ứng: khoảng một nửa dev, một nửa test; test 80–100 tình huống, tối thiểu 2/concept. Các cặp hồ sơ hoặc biến thể cùng lịch sử/bài nằm cùng split.
- Chốt định nghĩa `template_family_id` và nhóm nguồn trước chia tập. Bài chỉ thay số/paraphrase cùng nguồn không được rơi vào nhiều split. Với test giữ riêng cả họ mẫu, mô tả rõ đó là đánh giá tổng quát hóa sang họ chưa dùng khi phát triển; họ test vẫn phải thuộc dạng đã tuyên bố hỗ trợ. Không học checker theo test rồi gọi đó là test chưa thấy.
- Nếu số họ/records không đủ tách và phủ lớp, biên soạn thêm trước khóa. Bộ kiểm tra hồi quy trên dạng đã phát triển có thể báo riêng, không gộp với test giữ riêng họ mẫu.
- KB có kiến thức concept tổng quát nhưng không chứa nguyên ca test/nhãn/lời giải test cho generator. Reference riêng của validator không đi vào context sinh hint.
- Dữ liệu synthetic và học sinh thật gắn nguồn và báo riêng. Log KT không thay thế bộ bước giải/misconception hoặc hội thoại tiếng Việt.

### 9.4. Rubric và đánh giá người chấm

Sáu chiều, mỗi chiều 0–2: đúng toán, bám lỗi, phù hợp người học, gợi mở, không tiết lộ, rõ ràng. Có guideline và ví dụ cho từng mức; báo từng chiều. Lỗi toán nghiêm trọng hoặc tiết lộ lời giải làm scenario thất bại dù tổng điểm cao.

Tập chiến lược phù hợp được gán từ lịch sử làm bài, mức hỗ trợ và bằng chứng lỗi; **không lấy giá trị/ngưỡng BKT làm đáp án chuẩn**. Chấp nhận nhiều can thiệp hợp lý. Hai người chấm độc lập, ẩn cấu hình, thứ tự ngẫu nhiên; lưu điểm trước hòa giải và độ đồng thuận. LLM judge chỉ hỗ trợ, không là nguồn duy nhất.

Không loại abstain để làm đẹp F1; báo confusion matrix/unknown và coverage. Graph recommendation có tập đáp án được người đánh giá duyệt độc lập, không lấy chính graph làm chuẩn duy nhất. Bootstrap theo học sinh cho KT và scenario/nhóm bài cho hội thoại; chốt subset phân tầng và số lần chạy lặp trước test.

### 9.5. Ngân sách công việc và pilot

Tuần 2 phải có bảng `đầu việc × số lượng × phút/đơn vị × số lượt review`, người thực hiện và giờ khả dụng. Đo thử thời gian tạo một concept, record, kiểm tra toán và chấm output. Với 80–100 tình huống × 7 cấu hình × 2 người, một lần chạy đã cần **1.120–1.400 lượt chấm**; giả sử 3 phút/lượt thì 56–70 giờ công, chưa gồm hòa giải hoặc chạy lặp. Đây là minh họa để lập ngân sách, không phải năng suất đã đo.

Liên hệ phản biện và tuyển pilot từ tuần 1. Mục tiêu 12–20 học sinh nếu tiếp cận được, chủ yếu kiểm tra usability, tương tác và khả năng tự làm bài mới. Pre/post đơn nhóm không chứng minh hiệu quả nhân quả. Không tuyển được vẫn làm đầy đủ evaluation kỹ thuật, nhưng phải ghi chưa chứng minh learning gain trên người học thật.

### 9.6. Mục tiêu kỹ thuật ban đầu

| Chỉ số | Mốc để quản lý tiến độ |
|---|---|
| Macro-F1 họ lỗi | Khoảng ≥0.75 |
| Xác định đúng bước sai đầu tiên | Khoảng ≥0.80 trên tập có nhãn bước sai, kèm kết quả toàn bộ và coverage |
| Recall@5 | Khoảng ≥0.85 |
| Phản hồi đúng toán | Khoảng ≥0.95, chấm độc lập đầu ra đã hiển thị |
| Tiết lộ đáp án/lời giải | Không quá 5% trên tập đánh giá; mọi vi phạm vẫn là lỗi cần phân tích |
| Latency | p95 khoảng 10 giây/lượt theo NFR-02 |

Đây không phải chuẩn ngành hoặc kết quả đạt sẵn. Policy vẫn cấm tiết lộ; mốc đo không phải cho phép generator cố ý vi phạm. Tỷ lệ phải có mẫu số, khoảng tin cậy và breakdown quan trọng; kết quả dưới mốc được báo trung thực. Hiệu chỉnh mục tiêu chỉ trên pilot/dev, ghi lý do trước khóa test.

## 10. Phân công và kế hoạch 12 tuần

### 10.1. Đầu mối và trách nhiệm chung

| Đầu mối | Chịu trách nhiệm chính | Phối hợp / review |
|---|---|---|
| Member 1 | Validator/analyzer, observation builder, preprocessing, BKT, benchmark KT và bộ bước giải | Member 3 hỗ trợ extraction/API; Member 2 hỗ trợ ca toán và review dữ liệu |
| Member 2 | Registry/KB, graph, retrieval, đồng bộ, nội dung report và evaluation liên quan | Cả ba biên soạn/review nội dung; Member 1 rà mapping skill/observation |
| Member 3 | Agent/policy/LangGraph, session/API/UI, checkpoint, triển khai và ablation | Member 1 review tính nhất quán state; Member 2 hỗ trợ report/nội dung |

Cả ba biên soạn khoảng 13–14 concept/người cho mục tiêu 40, review chéo và gán nhãn theo quy trình tách test khỏi tinh chỉnh. Không mặc định Member 2 tự làm toàn bộ KB hoặc Member 3 tự làm toàn bộ sản phẩm. Mỗi tuần tích hợp luồng thật, cập nhật ma trận độ phủ; viết báo cáo từ tuần 2 và dành 15–20% quỹ thời gian cho tích hợp/sửa lỗi.

### 10.2. Mốc chung

| Tuần | Kết quả và điều kiện kiểm tra |
|---:|---|
| 1 | Chốt RQ, danh mục đề xuất, schema/fixtures; skeleton API/UI/LangGraph; liên hệ người review/pilot |
| 2 | Audit KT, checker/policy đầu tiên, KB mẫu; pilot annotation/rubric; chốt split, model, nguồn nội dung, ngân sách giờ/cost và điều kiện đo |
| 3 | Online BKT và idempotency, KG/RAG nối API, luồng thật trên một số concept; log liên thông |
| 4 | Prototype 8–10 concept thuộc ba mảng, đủ analyzer/BKT/KG/RAG/Agent, nhiều lượt, fallback và lưu/tiếp tục phiên |
| 5 | Khoảng 20 concept hoàn chỉnh; backtrack/return; report cơ bản; baseline/ablation cấu hình được |
| 6 | Khoảng 30 concept; kiểm tra trên dev, sensitivity tham số và rubric; ổn định UI |
| 7 | Đủ 40 concept mục tiêu; hoàn tất mọi cấu hình; khóa test/model/prompt/KB/ngưỡng và script |
| 8 | Chạy benchmark, bộ bước giải, retrieval/KG và Full/ablation; chấm ẩn cấu hình |
| 9 | Phân tích lỗi/đồng thuận, kiểm tra leakage, chạy lặp subset; pilot nếu tuyển được |
| 10 | Kết quả cuối, khoảng tin cậy, phân tích giới hạn; bản thảo báo cáo đầy đủ |
| 11 | Regression, sửa lỗi cần thiết, rà tài liệu, release candidate; chạy lại phần thực nghiệm bị ảnh hưởng |
| 12 | Đóng gói demo/config/artifacts, báo cáo, slides và diễn tập bảo vệ |

Mốc concept tính theo checklist nội dung + validator + hints + test, không theo số node. Nếu tuần 4 trễ, ưu tiên contract/loop. Nếu độ phủ trễ, điều phối lại biên soạn và checker; bỏ benchmark thứ hai, streaming hoặc dashboard nâng cao trước khi thay phạm vi bắt buộc.

## 11. Rủi ro và quyết định còn mở

### 11.1. Rủi ro cần theo dõi

| Rủi ro | Cách xử lý / dấu hiệu cần hành động |
|---|---|
| Validator không phủ dạng đã hứa | Đo coverage theo dạng từ prototype; thu hẹp mô tả dạng hỗ trợ có ghi quyết định hoặc bổ sung checker, không âm thầm chấm bằng LLM |
| Authoring/gán nhãn vượt quỹ giờ | Dùng kết quả pilot tính lại ngân sách, chia việc cả ba và hoàn tất template trước mở rộng |
| Skill Việt Nam thiếu dữ liệu | Default/pooled có version, sensitivity và evidence count; không giả vờ fit riêng |
| Test bị dùng tinh chỉnh | Split manifest, gán quyền/quy trình, khóa artifacts; thay đổi sau khóa phải ghi và báo giới hạn |
| LLM sai toán/tiết lộ hoặc timeout | Gate, output checks, một lần sinh lại, template fallback; đánh giá lỗi còn lọt độc lập |
| Graph/RAG không cải thiện | Log và ablation; phân tích nguyên nhân, chấp nhận kết quả không cải thiện |
| Không tuyển được pilot/chuyên gia | Liên hệ sớm, review chéo có ghi giới hạn; không thay bằng mô phỏng rồi tuyên bố tác động thực tế |
| DB/checkpoint lệch | Transaction, idempotency, version check, recovery scenario và replay |

### 11.2. Cần chốt bằng pilot hoặc quyết định nhóm

| Quyết định | Hạn / đầu mối |
|---|---|
| Concept–skill–dạng bài, lớp/mục tiêu và nguồn nội dung có quyền sử dụng | Tuần 1–2; Member 2 cùng cả nhóm và người review |
| Eligibility cho bài luyện gần, step opportunities và mapping KT | Tuần 1–2; Member 1, cả nhóm review |
| Model/version, embedding/config, ngân sách API và môi trường đo | Tuần 2; Member 3 phối hợp Member 2 |
| Danh sách người review, năng suất authoring/chấm và giờ công khả dụng | Tuần 2; cả nhóm |
| Protocol split theo họ mẫu và kế hoạch test đủ độ phủ | Tuần 2; cả nhóm, kiểm tra lại trước khóa |
| Ngưỡng policy, số lần chạy lặp/subset và các metric chính | Trên dev; khóa cuối tuần 7 |
| Tuyển pilot, thông báo, lưu/xóa dữ liệu và quyền truy cập | Trước thu thập; đầu mối do nhóm chỉ định tuần 1 |

Các lựa chọn PostgreSQL + pgvector, Neo4j, API model, HTTP trước/SSE sau và dashboard giáo viên P2 đã là phương án cơ sở; chỉ mở lại khi có lý do thực nghiệm/kỹ thuật được ghi nhận.

## 12. Nghiệm thu và demo

### 12.1. Điều kiện nghiệm thu bắt buộc

- Đủ 30–50 concept đã chốt, mục tiêu 40, đúng ba mảng và cả THCS–THPT; có ma trận độ phủ thực chất.
- Toàn bộ P0 có bằng chứng theo acceptance criteria; yêu cầu chưa đạt phải được ghi rõ, không coi demo một ca là thay thế.
- Analyzer xử lý cách giải khác, lỗi kéo theo và chưa đủ bằng chứng; BKT đúng observation, version và không cập nhật lặp.
- KG/RAG/Agent có log sử dụng trong quyết định/nội dung; có fallback và vòng học có giới hạn.
- UI, lưu/tiếp tục phiên, tiến trình cơ bản và learning report hoạt động, dữ liệu người học tách biệt.
- Có bộ dữ liệu đã duyệt, KT benchmark, bộ bước giải, rubric, baseline/ablation, raw outputs và script/config tái lập.
- Công bố kết quả thực tế, chỉ số chưa đạt, khoảng bất định, lỗi còn tồn tại và giới hạn suy rộng; không yêu cầu giả định Full luôn vượt baseline.

### 12.2. Kịch bản demo

1. Mở Student A/B tổng hợp, ghi rõ nguồn và replay được BKT từ log; không chỉnh tay mastery rồi gọi đó là kết quả học thật.
2. Làm bài ví dụ chuẩn, nhập ba bước sai như mục 4; analyzer chỉ ra bước 1 và candidate suspected.
3. Hiển thị observation eligibility, prediction trước đáp án, state trước/sau và parameter version; gửi lại cùng request chứng minh không cập nhật lần hai.
4. Xem Agent dùng bằng chứng, edge/content IDs và policy để chọn can thiệp; không ép hai hồ sơ luôn khác action.
5. Học sinh sửa sau hint; report ghi đúng có hỗ trợ và không thêm observation chuẩn.
6. Đưa bài mới tự làm phù hợp mục tiêu, cập nhật khi đủ điều kiện, quay lại bài gốc hoặc chuyển bài theo policy.
7. Minh họa một bài Toán số và một bài Hàm số/THPT; mở ma trận độ phủ toàn danh mục.
8. Thử cách giải khác, chỉ đáp án cuối, input mơ hồ/ngoài phạm vi và xin đáp án; phản hồi đúng nhánh, không tự chấm sai hoặc tiết lộ.
9. Dừng/tải lại/đăng nhập lại để tiếp tục phiên; xem report khớp log và một ca fallback dịch vụ.
10. Trình bày kết quả baseline/ablation thực tế và ít nhất một trường hợp hệ thống xử lý chưa tốt.

Demo minh họa hành vi; kết luận nghiên cứu dựa trên toàn bộ evaluation.

## 13. Tóm tắt thay đổi phiên bản 0.2

- Đồng bộ phạm vi 40 concept mục tiêu, prototype tuần 4 và thực nghiệm tuần 8–10 với plan.
- Thay cập nhật BKT sau mọi attempt bằng observation đủ điều kiện, thêm idempotency/resume và parameter version.
- Bổ sung assessment chưa xác minh, giả thuyết lỗi, evidence và quy ước bước 1; bỏ confidence làm bảo chứng đúng.
- Thống nhất không tự giải hoàn chỉnh bài hiện tại, kiểm soát context RAG và đầu ra trước hiển thị.
- Thay yêu cầu khác mastery bắt buộc khác action bằng kiểm tra can thiệp phù hợp; đồng bộ ablation và nhãn chuẩn không lấy BKT làm đáp án.
- Đưa memory/resume, tiến trình/report cơ bản vào P0; thêm tiêu chí kiểm tra cho từng FR và các nhánh lỗi.
- Chốt stack cơ sở, metric có điều kiện đo, ngân sách giờ công và các quyết định thực sự còn mở.
