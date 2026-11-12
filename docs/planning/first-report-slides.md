# Nội dung báo cáo tổng quan lần đầu — VIN-02

Ngày biên soạn: 10/10/2026. Bố cục: 13 slide chính; thời lượng tham khảo 10–15 phút. Đây là đề xuất đề tài, không phải báo cáo tiến độ hoặc kết quả thực nghiệm của nhóm.

Mỗi slide có nội dung để chép lên PowerPoint và ghi chú để thuyết trình. Không cần đưa toàn bộ ghi chú lên slide.

## Slide 1 — Tên đề tài

**Nghiên cứu và xây dựng trợ lý AI dạy học Toán theo phương pháp Socratic thích ứng sử dụng tác tử AI**

## Slide 2 — Tổng quan đề tài

- Xây dựng trợ lý AI hỗ trợ học Toán THCS–THPT bằng tiếng Việt.
- Tiếp nhận câu trả lời và từng bước giải của học sinh.
- Kiểm tra bài làm, xác định bước cần sửa và hỏi thêm khi chưa đủ bằng chứng.
- Theo dõi kiến thức qua lịch sử học để điều chỉnh mức hỗ trợ.
- Hướng dẫn bằng câu hỏi gợi mở, gợi ý và hoạt động ôn kiến thức nền.

**Socratic:** dùng câu hỏi để giúp người học tự suy luận. **Thích ứng:** điều chỉnh cách hỗ trợ theo bài làm và bằng chứng học tập của từng người.

Ghi chú thuyết trình: Socratic không có nghĩa chỉ liên tục đặt câu hỏi. Khi học sinh mắc kẹt, hệ thống có thể tăng mức gợi ý hoặc giải thích bằng một ví dụ khác, rồi để học sinh quay lại bài đang làm.

Nguồn nội bộ: Brief, mục 1–5; PRD, mục 2–4.

## Slide 3 — Bối cảnh và nhu cầu

- PISA 2025: **58% học sinh Việt Nam đạt ít nhất Level 2 Toán**, tương ứng khoảng **42% dưới Level 2**.
- **69% học sinh Việt Nam được khảo sát tự báo cáo dùng chatbot AI hỗ trợ học ít nhất hằng tuần**.
- Đặt ra nhu cầu hỗ trợ học tập bằng AI có nội dung đúng và cách hướng dẫn phù hợp.
- Đề tài tập trung vào chất lượng hỗ trợ khi học sinh làm bài và gặp khó khăn.

Ghi chú thuyết trình: Các tỷ lệ thuộc khảo sát học sinh 15 tuổi của PISA, không phải toàn bộ học sinh Việt Nam. Level 2 là ngưỡng năng lực PISA, không phải ngưỡng đỗ môn Toán. Tỷ lệ dùng AI nói về học tập nói chung, không riêng Toán. Hai số liệu tạo bối cảnh, không chứng minh AI gây yếu Toán hoặc giải pháp nhóm sẽ cải thiện điểm số.

Nguồn: [OECD, PISA 2025 Results — Viet Nam Country Note](https://www.oecd.org/en/publications/pisa-2025-results-volume-i-country-notes_2d4ff9ea-en/viet-nam_d652623e-en.html), công bố 08/09/2026. Khoảng 42% được tính bằng 100% − 58% từ tỷ lệ đã làm tròn.

## Slide 4 — Pain point của người học

| Khó khăn | Nhu cầu hỗ trợ |
|---|---|
| Biết đáp án sai nhưng chưa biết sai ở đâu | Chỉ ra bước cần kiểm tra |
| Một lỗi có thể do sơ suất hoặc hiểu sai | Hỏi thêm để làm rõ nguyên nhân |
| Thiếu kiến thức nền để giải tiếp | Chọn nội dung ôn phù hợp |
| Sửa đúng sau gợi ý nhưng chưa chắc tự làm được | Kiểm tra bằng bài mới tự làm |
| Mức hỗ trợ không phù hợp | Điều chỉnh theo tiến triển và lịch sử học |

Ghi chú thuyết trình: Đây là các tình huống đề tài hướng tới, không phải tỷ lệ đã đo trên người dùng của nhóm. Một bài sai chưa đủ để kết luận học sinh có một hiểu sai bền vững.

Nguồn: Brief, mục 2 và 4; project-plan, mục 3; [Daheim et al., EMNLP 2024](https://aclanthology.org/2024.emnlp-main.478/).

## Slide 5 — Tình huống minh họa

**Đề bài:** Giải phương trình `2(x − 3) = 10`.

**Bài làm của học sinh:**

```text
1. 2x − 3 = 10
2. 2x = 13
3. x = 6,5
```

- Bước sai đầu tiên: bước 1, ở phép phân phối.
- Hai bước sau biến đổi hợp lệ theo phương trình sai ở bước 1; không quy thành hai lỗi mới.
- Giả thuyết cần kiểm tra: học sinh chỉ nhân 2 với hạng tử đầu.
- Câu hỏi gợi mở: **“Nếu viết thành (x − 3) + (x − 3), phần −3 xuất hiện bao nhiêu lần?”**
- Học sinh sửa bài; hệ thống chọn bài mới để kiểm tra khả năng tự làm.

Ghi chú thuyết trình: Đây là kịch bản thiết kế dự kiến. Hệ thống xác minh lỗi toán trước, rồi dùng câu hỏi để tìm hiểu nguyên nhân. Hoàn thành sau trợ giúp được phân biệt với tự làm đúng.

Nguồn nội bộ: Brief, mục 4; PRD, ví dụ chuẩn ở mục 4.

## Slide 6 — Các giải pháp và nghiên cứu liên quan

| Đại diện | Hướng tiếp cận | Bài học tham khảo |
|---|---|---|
| Symbolab | Cung cấp lời giải từng bước | Trình bày biến đổi rõ ràng |
| ALEKS | Đánh giá kiến thức và học thích ứng | Sử dụng trạng thái người học để chọn nội dung |
| Khanmigo | Hội thoại hướng dẫn người học tự tìm đáp án | Câu hỏi gợi mở và hỗ trợ qua tương tác |
| MathDial | Nghiên cứu dữ liệu hội thoại gia sư Toán | Đánh giá phản hồi sư phạm, tránh tiết lộ lời giải sớm |

**Bài học cho đề tài:** cần phối hợp kiểm tra bài làm, theo dõi người học và lựa chọn hỗ trợ; giá trị phải được kiểm chứng bằng so sánh.

Ghi chú thuyết trình: Bảng mô tả các hướng tiếp cận theo tài liệu công khai, không xếp hạng sản phẩm và không kết luận chúng thiếu một thành phần bên trong. Đề tài tham khảo các hệ thống đã có để xác định phạm vi nghiên cứu của nhóm.

Nguồn: [Symbolab](https://www.symbolab.com/solver), [McGraw Hill — ALEKS](https://learn.mheducation.com/aleks.html), [Khanmigo](https://www.khanmigo.ai/), [MathDial, 2023](https://aclanthology.org/2023.findings-emnlp.372/).

## Slide 7 — Vấn đề nghiên cứu trọng tâm

**Làm thế nào để AI xác định bước cần sửa và chọn cách hỗ trợ phù hợp, giúp học sinh tiếp tục tự giải Toán?**

- MathDial ghi nhận mô hình trong nghiên cứu có thể phản hồi sai hoặc tiết lộ lời giải quá sớm.
- Daheim et al. nghiên cứu **1.002 chuỗi giải có giáo viên gán nhãn bước sai đầu tiên**; xác định đúng lỗi vẫn là nhiệm vụ khó.
- Trong thí nghiệm Pardos & Bhandari, trung bình **32% gợi ý ChatGPT ban đầu không qua kiểm tra chất lượng** trên 75 bài được dùng để sinh gợi ý.
- Nhóm nghiên cứu việc kết hợp bằng chứng từ bước giải, lịch sử kiến thức và nội dung hỗ trợ trong gia sư Toán tiếng Việt.

Ghi chú thuyết trình: Ba nghiên cứu hỗ trợ lý do cần kiểm tra phản hồi và phân tích lỗi. Con số 32% thuộc cấu hình ChatGPT 3.5 và bộ bài cụ thể trong nghiên cứu năm 2024; không đại diện mọi model hiện nay. Việc kết hợp các thành phần là giả thuyết cần kiểm chứng, chưa phải bằng chứng đề tài tốt hơn sản phẩm khác.

Nguồn: [MathDial, 2023](https://aclanthology.org/2023.findings-emnlp.372/); [Daheim et al., 2024](https://aclanthology.org/2024.emnlp-main.478/); [Pardos & Bhandari, PLOS ONE 2024](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0304013).

## Slide 8 — Mục tiêu và giá trị dự kiến

- Xây dựng trợ lý học Toán bằng tiếng Việt theo phương pháp Socratic thích ứng.
- Xác minh bài làm và cung cấp phản hồi dựa trên bằng chứng lỗi.
- Theo dõi trạng thái kiến thức để điều chỉnh hỗ trợ qua các phiên học.
- Giúp học sinh hiểu lý do được hỗ trợ và xem tiến trình dựa trên bài làm.
- Đánh giá chất lượng hỗ trợ bằng các cấu hình so sánh có kiểm soát.

**Giá trị dự kiến:** học sinh biết bước cần sửa và nội dung cần ôn; giáo viên có thông tin về lỗi và tiến trình; nhóm có bộ nội dung/đánh giá tiếng Việt và thực nghiệm có thể tái lập.

Ghi chú thuyết trình: Đây là mục tiêu cần đạt và giá trị dự kiến. Học sinh được biết vì sao hệ thống đề nghị ôn kiến thức nền hoặc đổi cách hỗ trợ; khi chưa đủ bằng chứng, hệ thống hỏi thêm thay vì kết luận chắc chắn. Tiến trình phân biệt tự làm với làm sau trợ giúp, không tăng chỉ vì nhắn thêm hoặc xin gợi ý. Nhóm chưa tuyên bố tăng điểm, giảm thời gian học hoặc thay thế giáo viên. Câu hỏi nghiên cứu là liệu mô hình kiến thức và bằng chứng lỗi có giúp chọn hỗ trợ phù hợp hơn baseline hay không.

Nguồn nội bộ: Brief, mục 1, 2 và 8; PRD, mục 2, FR-10, FR-16 và FR-18; project-plan, mục 8.1 và 8.7.

## Slide 9 — Người dùng và phạm vi

- **Người dùng chính:** học sinh THCS–THPT học bằng tiếng Việt.
- **Người dùng hỗ trợ:** giáo viên/người hướng dẫn theo dõi lịch sử lỗi và tiến trình.
- **Nội dung:** Toán số, Đại số, Hàm số.
- **Quy mô mục tiêu:** 40 khái niệm lõi, trong phạm vi đăng ký 30–50.
- **Hình thức:** ứng dụng web; nhập văn bản, biểu thức hoặc bước giải.

**Ngoài phạm vi bắt buộc:** Hình học, nhận dạng chữ viết tay/ảnh, giọng nói và hệ thống quản lý trường học đầy đủ.

Ghi chú thuyết trình: Mỗi concept cần nội dung và bài tập có chất lượng, không chỉ một tên trong danh mục. Ví dụ: phép toán số hữu tỉ, phân số, phân phối, thu gọn biểu thức, phương trình và giá trị hàm số. Nội dung cần đối chiếu chương trình và review chuyên môn.

Nguồn nội bộ: Brief, mục 3; PRD, mục 3; project-plan, mục 5.

## Slide 10 — Input và output

| Đầu vào | Đầu ra dự kiến |
|---|---|
| Bài toán được chọn trong phạm vi hỗ trợ | Kết quả kiểm tra bài làm |
| Câu trả lời hoặc từng bước giải | Bước sai đầu tiên khi xác minh được |
| Lịch sử làm bài và nhận trợ giúp | Giả thuyết nguyên nhân sai hoặc yêu cầu làm rõ |
| Trạng thái kiến thức đã lưu | Câu hỏi gợi mở, gợi ý hoặc hoạt động ôn nền |
| Yêu cầu “Chưa hiểu”, “Gợi ý nhẹ” hoặc “Ví dụ khác” | Hỗ trợ phù hợp và lý do can thiệp ngắn |
| Phản hồi tiếp theo của học sinh | Báo cáo tự làm/có hỗ trợ và nội dung cần luyện tiếp |

**Nguyên tắc:** ghi rõ khi chưa xác minh được; phân biệt tự làm với làm sau hỗ trợ; mức kiến thức là ước lượng.

Ghi chú thuyết trình: Các đầu vào được xem xét kết hợp, không phải mỗi hàng là một ánh xạ riêng. Một phần đầu ra là phân tích nội bộ để chọn phản hồi; học sinh nhìn thấy câu hỏi/gợi ý, lý do can thiệp ngắn và báo cáo dễ hiểu. Có thể yêu cầu hỗ trợ bằng hội thoại; nút thao tác nhanh là phần nên có, không phải yêu cầu bắt buộc. Yêu cầu hỗ trợ không được tính là một câu trả lời đúng/sai để cập nhật kiến thức. Hệ thống không tự tiết lộ lời giải hoàn chỉnh của bài đang làm.

Nguồn nội bộ: PRD, mục 3–4, FR-10, FR-13, FR-16 và FR-18; project-plan, mục 8.1 và 8.7.

## Slide 11 — Hướng giải quyết tổng thể

**Kiểm tra bài làm → hiểu khó khăn và trạng thái kiến thức → chọn hỗ trợ → kiểm tra khả năng tự làm tiếp.**

| Thành phần | Vai trò |
|---|---|
| Analyzer / bộ kiểm tra toán | Xác minh bước giải, cung cấp bằng chứng lỗi |
| Student Model / BKT | Lưu lịch sử và ước lượng kiến thức theo kỹ năng |
| Knowledge Graph | Liên kết khái niệm với kiến thức nền cần thiết |
| RAG | Lấy nội dung giải thích/gợi ý từ kho đã duyệt |
| AI Agent | Chọn hỏi chẩn đoán, gợi ý, ôn nền hoặc bài mới |
| LangGraph | Điều phối xử lý và lưu trạng thái phiên học |

Ghi chú thuyết trình: LLM hỗ trợ hội thoại và quyết định trong giới hạn cho phép. Kiểm tra toán và cập nhật kiến thức có quy tắc riêng. Hệ thống dự kiến lưu bằng chứng lỗi, nội dung kiến thức đã sử dụng, hành động và lý do ngắn để nhóm kiểm tra lại quyết định của AI và phục vụ đánh giá; không yêu cầu hiển thị chuỗi suy nghĩ nội bộ. Màn hình xem log là công cụ nội bộ nên có, còn việc lưu bằng chứng là yêu cầu bắt buộc. Không cần trình bày công thức BKT hoặc API ở báo cáo này; chỉ làm rõ vai trò và lý do cần từng thành phần.

Nguồn nội bộ: Brief, mục 5; project-plan, mục 7–9; PRD, FR-19 và NFR-04.

## Slide 12 — Dữ liệu và cách đánh giá

**Dữ liệu dự kiến**

| Nguồn | Vai trò |
|---|---|
| ASSISTments 2017 | Benchmark theo dõi kiến thức từ lịch sử làm bài |
| FoundationalASSIST | Bổ sung đề bài, câu trả lời đầu tiên và liên kết kỹ năng |
| Dữ liệu tiếng Việt tự xây | Nội dung, bài tập, lỗi, gợi ý và tình huống đánh giá |

**Ba trục đánh giá**

- **Phân tích lỗi:** xác định đúng bước cần sửa, tránh báo sai bài làm hợp lệ.
- **Theo dõi kiến thức:** dự đoán kết quả tự làm tiếp theo và kiểm tra chất lượng xác suất.
- **Hỗ trợ Socratic:** phản hồi đúng toán, phù hợp người học, giúp tiến triển và hạn chế tiết lộ đáp án.

Ghi chú thuyết trình: Dataset công khai và dữ liệu tiếng Việt có vai trò khác nhau; không mặc định log công khai có nhãn nguyên nhân sai hoặc đầy đủ bước giải. So sánh với chatbot được prompt Socratic, policy luật và các bản bỏ từng thành phần để kiểm tra giá trị giải pháp. Mục tiêu 800–1.200 bản ghi có nhãn trong plan là ngân sách công việc, không phải số liệu đã có hay chứng minh cỡ mẫu đủ mạnh.

Nguồn nội bộ: Brief, mục 6; project-plan, mục 11–12 và 17–19. Nguồn dữ liệu: [ASSISTments 2017](https://sites.google.com/view/assistmentsdatamining/dataset), [FoundationalASSIST](https://huggingface.co/datasets/ASSISTments/FoundationalASSIST).

## Slide 13 — Kế hoạch và phân công

**Thời gian dự kiến: 12 tuần; nhóm 3 người.**

| Giai đoạn | Mục tiêu |
|---|---|
| Tuần 1–2 | Chốt phạm vi, chuẩn bị dữ liệu và tiêu chí đánh giá |
| Tuần 3–4 | Tích hợp vòng gia sư trên 8–10 concept đại diện |
| Tuần 5–7 | Mở rộng tới danh mục mục tiêu, hoàn thiện cấu hình so sánh |
| Tuần 8–10 | Thực nghiệm, phân tích kết quả và giới hạn |
| Tuần 11–12 | Hoàn thiện sản phẩm, báo cáo và demo |

**Phân công đầu mối đề xuất theo plan:**

- Thành viên 1: bộ chấm/Analyzer, Student Model/BKT và đánh giá liên quan.
- Thành viên 2: kho kiến thức, KG/RAG và quy trình review nội dung.
- Thành viên 3: Agent, giao diện/API, tích hợp và đánh giá hệ thống.

Ghi chú thuyết trình: Cả ba cùng biên soạn, review và gán nhãn dữ liệu. Đây là phân công dự kiến, không mô tả đóng góp đã thực hiện của từng thành viên. Giai đoạn pilot 8–10 concept là mốc tích hợp; phạm vi mục tiêu cuối vẫn là 40.

Nguồn nội bộ: Brief, mục 7; project-plan, mục 23–25.

## Nguồn nội bộ và cách sử dụng

- [Brief](../product/brief.md): mục tiêu, giá trị, ví dụ và kế hoạch.
- [PRD](../product/prd.md): hành vi, phạm vi, input/output và nguyên tắc.
- [Plan tổng](project-plan.md): module, dữ liệu, đánh giá và phân công.
- Hai báo cáo tham khảo do người dùng cung cấp: `C:/Users/LENOVO/Downloads/deep-research-report.md` và `C:/Users/LENOVO/Downloads/deep-research-report (1).md`. Dùng để tìm luận cứ; số liệu trên slide dẫn về nguồn gốc đã kiểm tra.

Đây là ghi chú biên soạn, không phải slide thứ 14. Giữ nguồn nhỏ trên slide có số liệu/nghiên cứu. Không sao chép các mã trích dẫn nội bộ từ hai báo cáo research sang slide. Không đưa kết quả triển khai hoặc test kỹ thuật của nhóm vào như bằng chứng hiệu quả học tập.
