# PROJECT BRIEF — VIN-02

**Tên đề tài:** Nghiên cứu và xây dựng trợ lý AI dạy học Toán theo phương pháp Socratic thích ứng sử dụng AI Agent  
**Phiên bản:** 0.2 — cập nhật ngày 25/09/2026  
**Nhóm và thời gian:** 3 thành viên, 12 tuần  
**Tài liệu liên quan:** [PRD](prd.md) · [Kế hoạch chi tiết](../planning/project-plan.md)

## 1. Tóm tắt đề tài

Nhóm xây dựng trợ lý AI hỗ trợ học Toán THCS–THPT bằng câu hỏi gợi mở. Hệ thống phân tích câu trả lời và bước giải, xác minh lỗi, đề xuất giả thuyết misconception, theo dõi trạng thái kiến thức theo kỹ năng và chọn cách hỗ trợ phù hợp.

Student Model lưu bằng chứng học tập qua các phiên. Bayesian Knowledge Tracing (BKT) ước lượng trạng thái biết kỹ năng; Knowledge Graph cung cấp quan hệ kiến thức tiên quyết; RAG lấy nội dung đã duyệt; AI Agent chọn hành động sư phạm trong giới hạn policy. LangGraph điều phối xử lý, lưu trạng thái và chờ học sinh trả lời.

**Câu hỏi trọng tâm:** Mô hình kiến thức và bằng chứng lỗi có giúp hệ thống lựa chọn can thiệp Socratic phù hợp hơn các baseline được kiểm soát hay không?

## 2. Người dùng và giá trị dự kiến

Khi học sinh làm sai, chỉ cung cấp đáp án đúng chưa cho biết em sai ở đâu, có thiếu kiến thức nền hay cần mức hỗ trợ nào. Nhóm cần kiểm chứng khả năng chẩn đoán và can thiệp, bên cạnh độ đúng của phản hồi toán học.

- **Học sinh:** nhập bước giải, nhận gợi ý vừa đủ, ôn prerequisite khi có bằng chứng cần thiết, thử bài mới và tiếp tục phiên trước.
- **Giáo viên/người hướng dẫn:** xem lịch sử lỗi, kết quả tự làm so với có hỗ trợ và mastery ước lượng kèm số quan sát. Learning report cơ bản là bắt buộc; dashboard giáo viên riêng là phần bổ sung.
- **Đầu ra nghiên cứu:** tutoring engine, bộ nội dung/đánh giá tiếng Việt và thực nghiệm có thể tái lập.

Không mặc định mọi chatbot khác đều thiếu cá nhân hóa. Giá trị phải được so sánh với baseline cụ thể; không cam kết tăng kết quả học tập trước khi có bằng chứng.

## 3. Phạm vi

Nghiệm thu **30–50 concept thuộc Toán số, Đại số và Hàm số, phủ cả THCS và THPT**; mục tiêu triển khai **40 concept** theo danh mục trong plan. Tuần 1–2 đối chiếu chương trình môn Toán, rà chuyên môn và chốt dạng bài hỗ trợ.

Một concept hoàn chỉnh có mục tiêu, skill quan sát được, prerequisite đã duyệt, ít nhất 6 bài thuộc ít nhất 3 họ mẫu, ví dụ, lỗi thường gặp, hint ladder và test. Concept và skill không bắt buộc ánh xạ một-một.

Input chính là văn bản, biểu thức và bước giải. Ngoài phạm vi phải được báo rõ, không tự chấm sai. Không triển khai Hình học, OCR/chữ viết tay, voice, mobile app, LMS đầy đủ hoặc fine-tuning như điều kiện hoàn thành. Giới hạn/đạo hàm chỉ cân nhắc sau khi hoàn tất danh mục đã chốt và vẫn trong giới hạn 50 concept.

**Prototype cuối tuần 4** có 8–10 concept đại diện và đủ vòng xử lý; đây là mốc tích hợp nội bộ, không thay thế phạm vi nghiệm thu.

## 4. Ví dụ sử dụng

Với bài `2(x - 3) = 10`, học sinh viết:

```text
2x - 3 = 10
2x = 13
x = 6.5
```

Hệ thống xác minh bước 1 sai do khai triển. Hai bước sau hợp lệ theo phương trình học sinh đang có nên không bị tính thành hai lỗi mới. Analyzer đề xuất “chỉ phân phối cho số hạng đầu” ở trạng thái `suspected`, chưa kết luận misconception bền vững.

Agent có thể hỏi:

> Nếu viết hai nhóm (x - 3) thành (x - 3) + (x - 3), em thấy phần -3 xuất hiện bao nhiêu lần?

Khi học sinh sửa đúng sau gợi ý, hệ thống lưu **kết quả có hỗ trợ**, không thêm observation BKT chuẩn. Bài mới tự làm cung cấp bằng chứng tiếp theo khi đủ điều kiện. Mastery được tính từ observation hợp lệ và tham số đã lưu, không gán sẵn mức tăng.

Graph cung cấp prerequisite ứng viên; lịch sử và câu hỏi chẩn đoán giúp quyết định có cần quay lại kiến thức nền hay không.

## 5. Cơ chế và nguyên tắc

```text
Câu trả lời/bước giải
    → Xác minh toán và đề xuất giả thuyết lỗi
    → Kiểm tra điều kiện observation; cập nhật BKT tối đa một lần
    → Agent đọc Student Model, tra KG/RAG hoặc chọn bài khi cần
    → Policy kiểm tra hành động và mức hỗ trợ
    → Sinh, kiểm tra câu hỏi/gợi ý
    → Lưu trạng thái, chờ học sinh
```

- Cho phép chưa đủ bằng chứng; tách bước sai khỏi nguyên nhân sai.
- Không đồng nhất lượt chat với opportunity học tập; retry không làm tăng số observation.
- Mastery là ước lượng theo mô hình, kèm evidence count và trạng thái thiếu dữ liệu.
- Không tự đưa nghiệm/lời giải hoàn chỉnh của bài đang làm, kể cả khi học sinh xin đáp án. Hỗ trợ mạnh bằng ví dụ khác, rồi để học sinh tiếp tục.
- Hint phụ thuộc tiến triển và nhu cầu; có giới hạn lượt, backtrack có đường quay lại và quyền dừng phiên.
- Khác mastery có thể dẫn đến khác can thiệp khi bằng chứng phù hợp; không ép mọi cặp hồ sơ phải nhận phản hồi khác nhau.

## 6. Dữ liệu và đánh giá

**ASSISTments 2017** là dataset KT chính ban đầu sau khi kiểm tra schema/label. **Junyi** là benchmark bổ sung nếu đủ thời gian; **FoundationalASSIST** chỉ bổ sung khi có quyền truy cập. Không mặc định các log có nhãn misconception/bước giải hoặc tham số chuyển được sang học sinh Việt Nam.

Nhóm tự xây KB, bộ bước giải và tình huống thích ứng tiếng Việt. Quy mô, split và quy trình gán nhãn theo PRD/plan; pilot tuần 2 kiểm tra năng suất trước khi chốt ngân sách công việc.

| Trục đánh giá | Bằng chứng |
|---|---|
| Lỗi/misconception | Bước sai đầu tiên, F1 họ lỗi, coverage và lỗi trên phần đã quyết định |
| Theo dõi kiến thức | Dự đoán lượt tiếp theo: log loss, AUC, Brier/calibration; tính nhất quán cập nhật |
| Socratic thích ứng | Rubric, vi phạm toán/tiết lộ, tình huống nhiều lượt và so sánh ghép cặp |

So sánh Full với No-BKT, Heuristic, No-KG, No-RAG, Rule-policy và Socratic LLM baseline. Người chấm dựa trên bằng chứng học tập, không lấy mastery BKT làm đáp án chuẩn. Test không dùng tinh chỉnh; các biến thể cùng nguồn nằm cùng split. Kết quả không cải thiện vẫn được báo cáo.

Pilot 12–20 học sinh là mục tiêu nếu tuyển được, chủ yếu đánh giá khả năng sử dụng và tương tác. Không suy ra hiệu quả học tập nhân quả từ mastery tăng, học sinh mô phỏng hoặc pre/post đơn nhóm.

## 7. Tổ chức và mốc thực hiện

Stack ban đầu: Next.js/React, FastAPI, Pydantic, LangGraph, SymPy + luật theo dạng bài, Python/pyBKT, PostgreSQL + pgvector, Neo4j và Docker Compose. Chọn một API model chính sau benchmark tuần 2; HTTP trước, SSE bổ sung sau khi luồng ổn định và chỉ phát nội dung đã kiểm tra.

| Đầu mối | Trách nhiệm |
|---|---|
| Member 1 | Validator/analyzer, observation builder, Student Model/BKT và đánh giá liên quan |
| Member 2 | Taxonomy/KB, graph, retrieval, đồng bộ dữ liệu và kiểm duyệt nội dung |
| Member 3 | Agent/policy/LangGraph, API/UI, phiên học, tích hợp và ablation |

Cả ba cùng biên soạn khoảng 13–14 concept/người, review chéo và gán nhãn theo quy trình tách test khỏi tinh chỉnh. Đo giờ công từ pilot; dành 15–20% thời gian cho tích hợp/sửa lỗi và viết báo cáo từ tuần 2.

| Mốc | Kết quả |
|---|---|
| Tuần 1–2 | Chốt phạm vi, hợp đồng dữ liệu, pilot nội dung/rubric, ngân sách giờ công và model |
| Tuần 3–4 | Luồng chạy thật; cuối tuần 4 đủ module, persistence và 8–10 concept |
| Tuần 5–7 | Mở rộng khoảng 20 → 30 → 40 concept; hoàn tất baseline và khóa thí nghiệm |
| Tuần 8–10 | Thực nghiệm chính, chấm kết quả, phân tích lỗi và pilot nếu tuyển được |
| Tuần 11–12 | Regression, đóng gói, báo cáo, slides và demo |

## 8. Điều kiện hoàn thành và đóng góp

Sản phẩm có web học sinh, đủ danh mục nghiệm thu, kiểm tra bước giải, Student Model/BKT, KG/RAG, Agent trong LangGraph, vòng hội thoại có giới hạn, lưu/tiếp tục phiên và learning report cơ bản. Có dữ liệu đã duyệt, benchmark, baseline/ablation và log tái lập quyết định.

Đóng góp dự kiến là bộ nội dung/đánh giá tiếng Việt, cơ chế thích ứng có thể truy vết và thực nghiệm kiểm soát thành phần. Không tuyên bố thuật toán BKT mới hoặc tính mới chỉ từ việc ghép framework.

## 9. Elevator pitch

> Nhóm xây dựng trợ lý AI học Toán THCS–THPT theo phương pháp Socratic trên khoảng 30–50 khái niệm lõi. Hệ thống phân tích bước giải, đề xuất giả thuyết lỗi, dùng BKT theo dõi kiến thức và kết hợp Knowledge Graph với RAG để AI Agent lựa chọn cách gợi mở phù hợp. Giá trị được kiểm chứng bằng đánh giá lỗi/misconception, dự đoán kết quả tiếp theo và chất lượng can thiệp so với các baseline có kiểm soát.
