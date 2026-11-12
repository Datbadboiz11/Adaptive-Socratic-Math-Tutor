# Nội dung báo cáo lần 2 — Hướng tiếp cận và kiến trúc đề xuất

Điều chỉnh ngày 26/10/2026 theo yêu cầu tập trung vào hướng làm. Phần nội dung chính gồm 12 slide, tính cả bìa, thời lượng tham khảo 15 phút. Ba slide nghiên cứu liên quan đã soạn riêng có thể chèn vào bộ trình chiếu; không tự sửa nội dung của chúng.

## Chỉ dẫn cho Canva AI

Tạo 12 slide tiếng Việt tỷ lệ 16:9. Phong cách báo cáo học thuật, nền sáng, xanh đậm/xanh ngọc, chữ tương phản và dễ đọc. Ưu tiên sơ đồ khối, bảng dữ liệu, ví dụ toán. Không thêm slide phụ, mục lục, chia việc nhóm hoặc slide cảm ơn.

Chỉ đưa phần NỘI DUNG HIỂN THỊ và CHÚ THÍCH lên slide. Dùng phần GHI CHÚ cho speaker notes nếu có. Phần BỐ CỤC là chỉ dẫn thiết kế, không phải chữ để trình chiếu. Giữ nguồn ngắn tại cuối slide tương ứng.

Mục đích lần này là làm rõ HƯỚNG TIẾP CẬN VÀ KIẾN TRÚC ĐỀ XUẤT. Không tạo slide tiến độ embedding, kết quả chạy Kaggle, số vector hoặc so sánh model. Không tự chèn bảng AUC/Recall, số test hay phần trăm hoàn thành. Các workflow và chính sách dưới đây là thiết kế cần kiểm chứng, không phải tuyên bố đã hoàn thành. Slide 1 chỉ có tên đề tài. Không tự sửa tên đề tài hoặc phạm vi đăng ký.

## Slide 1 — Tên đề tài

NỘI DUNG HIỂN THỊ

Nghiên cứu và xây dựng trợ lý AI dạy học Toán theo phương pháp Socratic thích ứng sử dụng tác tử AI

BỐ CỤC

Bìa tối giản, tên đề tài chia thành các dòng dễ đọc. Không thêm công nghệ, số liệu hoặc mô tả dài.

GHI CHÚ

Lần trước nhóm trình bày vấn đề và nghiên cứu liên quan. Lần này giải thích nhóm định giải quyết bài toán bằng cách nào, các thành phần phối hợp ra sao và sẽ kiểm chứng phương án đó như thế nào.

## Slide 2 — Hướng tiếp cận của đề tài

NỘI DUNG HIỂN THỊ

Hệ thống lựa chọn hỗ trợ dựa trên bằng chứng trong bài làm và hồ sơ người học.

- Xác minh bước giải trước khi đưa ra nhận xét.
- Phân biệt lỗi quan sát được với giả thuyết nguyên nhân.
- Theo dõi bằng chứng theo kỹ năng và lịch sử trợ giúp.
- Chọn câu hỏi, gợi ý hoặc kiến thức nền để người học tự làm tiếp.
- Kiểm tra khả năng tự làm bằng cơ hội làm bài phù hợp tiếp theo.

Phạm vi kiểm chứng theo kế hoạch: khoảng 40 concept được lựa chọn thuộc Toán số, Đại số và Hàm số, phủ THCS–THPT.

CHÚ THÍCH

Hướng tiếp cận đề xuất. Phạm vi concept không đồng nghĩa bao phủ toàn bộ chương trình hoặc đã triển khai hoàn chỉnh.

BỐ CỤC

Một câu nêu nguyên tắc ở phía trên. Bên dưới là các bước có quan hệ, nhấn việc lựa chọn hỗ trợ theo bằng chứng. Không thêm số liệu tiến độ hoặc số bài đã biên soạn.

GHI CHÚ

Câu hỏi nghiên cứu chính là thông tin về lỗi, kiến thức và lịch sử hỗ trợ có giúp chọn can thiệp phù hợp hơn không. LLM hỗ trợ suy luận và diễn đạt, còn xác minh toán, cập nhật Student Model và quyền truy cập cần đi qua cơ chế riêng. Chưa thay đổi phạm vi trong plan chỉ vì mô hình có thể trả lời ngoài danh mục.

NGUỒN CUỐI SLIDE

Project-plan, mục 5–8 và 17; PRD, mục 2–4.

## Slide 3 — Kiến trúc hệ thống đề xuất

NỘI DUNG HIỂN THỊ

Luồng xử lý chính:
1. Student UI / API: nhận bài làm và nạp phiên.
2. Validator / Analyzer: kiểm tra toán, phân tích bằng chứng lỗi.
3. Observation Builder / BKT: kiểm tra điều kiện quan sát, cập nhật trạng thái khi hợp lệ.
4. Agent: đọc trạng thái, chọn hành động và công cụ.
5. Policy / Generator / Output checks: kiểm soát hỗ trợ, tạo và kiểm tra phản hồi.
6. Persistence / Checkpoint: lưu kết quả, chờ tương tác tiếp theo.

Các công cụ Agent có thể gọi khi cần:
- Knowledge Graph: lấy prerequisite ứng viên.
- RAG: lấy nội dung dạy học hợp lệ.
- Problem Selector: chọn bài luyện tập hoặc kiểm tra.

Lựa chọn kỹ thuật trong thiết kế: FastAPI/Pydantic, LangGraph, PostgreSQL/pgvector, Neo4j.

CHÚ THÍCH

Kiến trúc mục tiêu, chưa tích hợp đầy đủ các khối. Agent không được tùy ý sửa BKT.

BỐ CỤC

Sơ đồ khối từ trên xuống. Agent có nhánh tới KG, RAG và Problem Selector với nhãn “khi cần”. LangGraph thể hiện điều phối, không phải model suy luận. Dùng nét đứt cho Agent và vòng đa lượt chưa hoàn tất. Gắn pgvector “Code đã có, chờ kiểm chứng DB”. BKT đã có baseline và triển khai trong MVP một chủ đề, chưa tích hợp đủ pilot.

GHI CHÚ

Tách nhiệm vụ xác minh toán, theo dõi trạng thái và diễn đạt phản hồi. Model LLM chính cho hệ thống đầy đủ cần được chốt bằng benchmark. Qwen3-Embedding-4B dùng cho embedding, không phải model sinh câu trả lời gia sư. Không bắt buộc mọi lượt phải gọi KG/RAG.

NGUỒN CUỐI SLIDE

Project-plan, mục 7–8 và 14–15; PRD, mục 7.

## Slide 4 — Workflow minh họa trên một bài làm sai

NỘI DUNG HIỂN THỊ

Đề bài: Giải phương trình 2(x − 3) = 10.

Bài làm học sinh:
1. 2x − 3 = 10
2. 2x = 13
3. x = 6,5

Xác minh: bước 1 sai vì 2(x − 3) không tương đương 2x − 3.

Giả thuyết cần làm rõ: học sinh có thể chỉ nhân hệ số với số hạng đầu.

Câu hỏi hỗ trợ minh họa:
“Nếu viết thành hai nhóm (x − 3) + (x − 3), phần −3 xuất hiện bao nhiêu lần?”

Theo thiết kế:
- Ghi việc sửa đúng sau gợi ý là kết quả có hỗ trợ.
- Dùng bài mới phù hợp để kiểm tra khả năng tự làm.

CHÚ THÍCH

Tình huống minh họa thiết kế, chưa phải demo end-to-end của đầy đủ các module.

BỐ CỤC

Đề và bài làm bên trái, bằng chứng/câu hỏi bên phải. Chỉ đánh dấu bước 1. Hai bước sau hợp lệ theo phương trình sai mà học sinh đang có, không tô thành hai lỗi mới.

GHI CHÚ

Biết phép biến đổi sai chưa đủ để kết luận nguyên nhân suy nghĩ. Có thể là sơ suất hoặc thiếu hiểu biết, nên cần hỏi chẩn đoán. Các lượt sửa sau hint không tự thành các observation độc lập mới cho BKT. Bộ chấm và mẫu lỗi là nền tảng hiện có; quyết định và phản hồi đa lượt còn cần tích hợp.

NGUỒN CUỐI SLIDE

Project-plan, mục 6; PRD, ví dụ chuẩn và quy tắc observation.

## Slide 5 — Dữ liệu cần cho từng thành phần

NỘI DUNG HIỂN THỊ

| Nhóm dữ liệu | Thông tin cần có | Mục đích |
|---|---|---|
| Lịch sử tương tác học tập | Người học, kỹ năng, thứ tự, đúng/sai, trợ giúp | Fit và đánh giá BKT |
| Kho kiến thức tiếng Việt | Concept, prerequisite, giải thích, bài tập và mức gợi ý | Cung cấp nội dung và quan hệ kiến thức |
| Bài làm có nhãn | Bước đúng/sai, bước sai đầu tiên, họ lỗi và mức đủ bằng chứng | Phát triển, đánh giá Analyzer |
| Tình huống hội thoại và truy xuất | Nhu cầu hỗ trợ, nội dung phù hợp, hành động chấp nhận được | Đánh giá retrieval và lựa chọn can thiệp |

Nguyên tắc: có nguồn và phiên bản; tách dữ liệu phát triển với đánh giá; chỉ công bố nội dung đã duyệt.

CHÚ THÍCH

Dữ liệu BKT và dữ liệu tri thức có vai trò khác nhau. Không dùng trạng thái kiến thức suy luận làm nhãn thật.

BỐ CỤC

Bảng bốn hàng, giúp người nghe thấy dữ liệu nào phục vụ bài toán AI nào. Không đưa số vector hoặc danh sách file output.

GHI CHÚ

ASSISTments 2017 là nguồn tương tác dùng cho benchmark BKT; dữ liệu này chưa tự trở thành taxonomy kỹ năng tiếng Việt. Kho tri thức và bộ bài làm cần biên soạn/review theo phạm vi đã chọn. Dữ liệu synthetic có thể kiểm tra thuật toán nhưng không chứng minh hiệu quả với người học thật. Nội dung cần gắn trạng thái nháp/đã duyệt, source và version. Không kể các nguồn chưa sử dụng như kết quả huấn luyện đã có.

NGUỒN CUỐI SLIDE

Project-plan, mục 11–12, 16 và 19; PRD, mục 6 và 9.

## Slide 6 — Student Model và cơ chế cập nhật BKT

NỘI DUNG HIỂN THỊ

Student Model dự kiến lưu theo kỹ năng:
- Ước lượng kiến thức P(L).
- Số observation hợp lệ và lịch sử kết quả.
- Mức hỗ trợ đã dùng và giả thuyết lỗi có bằng chứng.

| Tình huống | Cách xử lý theo thiết kế |
|---|---|
| Lần trả lời đầu tiên, tự làm, chấm được, skill rõ | Tạo observation và cập nhật BKT một lần |
| Sửa đúng sau gợi ý | Lưu kết quả có hỗ trợ, không thêm observation chuẩn |
| Xin gợi ý hoặc đầu vào chưa xác minh | Ghi sự kiện, chưa cập nhật đúng/sai |
| Gửi lại cùng request | Dùng khóa chống trùng, không cập nhật lại |

BKT dự đoán kết quả trước khi dùng đáp án hiện tại, sau đó cập nhật trạng thái khi observation hợp lệ.

CHÚ THÍCH

Mastery là ước lượng theo mô hình, không phải điểm thi hoặc tỷ lệ kiến thức hiểu chắc chắn.

BỐ CỤC

Một Student Model nhỏ với các trường dữ liệu, bên cạnh bảng điều kiện cập nhật. Không trình bày AUC, số dòng đã xử lý hoặc thông báo model đã train xong.

GHI CHÚ

BKT có bốn tham số cơ bản: prior biết trước, chuyển sang biết, đoán đúng và sơ suất. Quy tắc tách kết quả có hỗ trợ là lựa chọn observation bảo thủ trong thiết kế, không phải khẳng định BKT nào cũng buộc loại mọi lượt có trợ giúp. Sự học trong lúc được hỗ trợ vẫn có thể xảy ra; hệ thống ghi nhận và cần cơ hội làm độc lập để thu thêm bằng chứng. Điều kiện tự làm được xét theo lịch sử trợ giúp được ghi nhận, không đồng nghĩa độc lập thống kê hoặc quan sát được mọi trợ giúp bên ngoài.

NGUỒN CUỐI SLIDE

Project-plan, mục 8.3 và 16; PRD FR-07; observation-protocol.md.

## Slide 7 — Xác minh toán và phân tích lỗi

NỘI DUNG HIỂN THỊ

Hai nhiệm vụ được tách biệt:

| Nhiệm vụ | Kết quả cần trả |
|---|---|
| Mathematical Validator | Tính đúng/tương đương và bước sai đầu tiên khi đủ căn cứ |
| Error Analyzer | Họ lỗi nghi ngờ, kỹ năng liên quan và câu hỏi cần làm rõ |

Nguyên tắc xử lý:
- Chấp nhận cách giải khác nếu hợp lệ trong phạm vi được hỗ trợ.
- Không tính lỗi kéo theo thành nhiều lỗi độc lập.
- Không suy ra bước sai khi chỉ nhận một đáp án cuối.
- Giữ trạng thái chưa xác minh/cần làm rõ nếu thiếu căn cứ.

Giả thuyết nguyên nhân phải đi kèm bằng chứng, không khẳng định suy nghĩ của học sinh từ một lần sai.

CHÚ THÍCH

Thiết kế kiểm chứng theo dạng bài. LLM extraction hoặc confidence tự sinh không thay thế xác minh toán.

BỐ CỤC

Hai thành phần nối nhau, bảng đầu ra ngắn. Liên hệ ví dụ sai phân phối ở slide 4. Không dùng một nhãn “AI hiểu nguyên nhân” chung cho cả hai nhiệm vụ.

GHI CHÚ

Plan kết hợp luật toán, công cụ kiểm chứng theo dạng bài, LLM structured extraction khi cần và mẫu lỗi. Bộ chấm hiện có không đồng nghĩa đã hỗ trợ mọi lời giải tự do hoặc đã triển khai tất cả các công cụ trong thiết kế. Đối với bước cần điều kiện xác định/tập nghiệm, phải kiểm tra điều kiện chứ không chỉ so sánh chuỗi. Pydantic kiểm tra cấu trúc, không chứng minh nội dung do LLM sinh là đúng. Nội dung ngoài phạm vi không được tự chấm sai hoặc cập nhật BKT.

NGUỒN CUỐI SLIDE

Project-plan, mục 8.2; PRD FR-05–06; analyzer.v1.md.

## Slide 8 — Knowledge Graph và lựa chọn kiến thức nền

NỘI DUNG HIỂN THỊ

Knowledge Graph tổ chức:
- Concept và kỹ năng liên quan.
- Quan hệ prerequisite và nguồn của quan hệ.
- Mục tiêu học, phạm vi bài và trạng thái review.

Ví dụ quan hệ kiến thức đề xuất:
- Nhân chia số có dấu là kiến thức nền của tính phân phối.
- Tính phân phối và thu gọn hạng tử là kiến thức nền của một số dạng phương trình bậc nhất.

Cách dùng trong quyết định:
1. Xác định concept liên quan đến lỗi.
2. Tra prerequisite ứng viên.
3. Đối chiếu bằng chứng người học hoặc hỏi chẩn đoán.
4. Ôn nền nếu cần, giữ ngữ cảnh để quay lại bài gốc.

CHÚ THÍCH

Graph cung cấp quan hệ kiến thức, không tự chứng minh người học thiếu prerequisite.

BỐ CỤC

Graph nhỏ từ các quan hệ trên. Đặt Student Model và câu hỏi chẩn đoán cạnh bước lựa chọn ôn. Không tô tất cả prerequisite thành kỹ năng yếu.

GHI CHÚ

Các cạnh cần nguồn và người duyệt, kiểm tra chu trình và chiều quan hệ. Neo4j là lựa chọn lưu graph trong plan, registry có ID/version là nguồn đồng bộ. Backtrack được giới hạn và có đường quay lại; không tự chuyển qua nhiều chủ đề khiến học sinh mất mục tiêu. Những cạnh minh họa hiện ở trạng thái đề xuất, không coi là kết luận chương trình hoặc chẩn đoán học sinh.

NGUỒN CUỐI SLIDE

Project-plan, mục 8.4 và 14; PRD FR-08; registry.v1.json.

## Slide 9 — Truy xuất nội dung và tạo phản hồi Socratic

NỘI DUNG HIỂN THỊ

Nội dung hỗ trợ cần phù hợp cả mục tiêu học và mức trợ giúp được phép.

Luồng đề xuất:
1. Xác định nhu cầu từ bài làm và quyết định hỗ trợ.
2. Chọn nội dung đúng concept, loại nội dung, mức gợi ý và trạng thái duyệt.
3. Xếp hạng trong tập nội dung hợp lệ khi cần tìm theo ý nghĩa.
4. Sinh phản hồi bám bằng chứng và nguồn đã lấy.
5. Kiểm tra tính đúng toán, mức tiết lộ trước khi hiển thị.

Phản hồi có thể là câu hỏi chẩn đoán, gợi ý, xác nhận kết quả hoặc giải thích qua ví dụ khác.

CHÚ THÍCH

RAG cung cấp căn cứ, không bảo đảm loại bỏ mọi phản hồi sai. Khi thiếu nội dung phù hợp, hỏi làm rõ hoặc dùng fallback đã duyệt.

BỐ CỤC

Sơ đồ từ nhu cầu hỗ trợ, lọc nội dung, truy xuất, tạo phản hồi tới kiểm tra. Không thêm model embedding, Kaggle, số vector hoặc bảng benchmark. Đáp án/lời giải chuẩn phục vụ bộ xác minh được đặt riêng khỏi nội dung cấp cho node sinh hint.

GHI CHÚ

Đã có content ID thì có thể lấy trực tiếp, không bắt buộc mọi lượt đều tìm ngữ nghĩa. Generator chỉ nhận nội dung được phép theo mức hỗ trợ; chính LLM vẫn có thể suy ra đáp án nên cần kiểm tra đầu ra. Socratic không phải cứ hỏi ngược: câu hỏi phải bám chướng ngại toán học, vừa khả năng người học và có cơ hội để họ tự thực hiện bước tiếp theo. Không coi cổng kiểm tra là bảo đảm tuyệt đối, cần đánh giá độc lập lỗi còn lọt.

NGUỒN CUỐI SLIDE

Project-plan, mục 8.5 và 9; PRD FR-09 và FR-12–13.

## Slide 10 — Agent lựa chọn can thiệp thích ứng

NỘI DUNG HIỂN THỊ

Đầu vào quyết định: bài làm hiện tại, kết quả xác minh, lịch sử hỗ trợ, bằng chứng theo skill và mục tiêu học.

| Tình huống minh họa | Hành động dự kiến |
|---|---|
| Đầu vào chưa rõ | Hỏi làm rõ |
| Một bước sai, chưa đủ căn cứ về nguyên nhân | Hỏi chẩn đoán |
| Có dấu hiệu lỗi thao tác đơn lẻ | Gợi ý kiểm tra thao tác |
| Mắc kẹt hoặc xin thêm hỗ trợ | Tăng mức giàn giáo phù hợp |
| Có bằng chứng prerequisite cần kiểm tra | Kiểm tra/ôn nền, sau đó quay lại |
| Sửa đúng sau hỗ trợ | Chọn bài mới để kiểm tra tự làm |

Agent đề xuất hành động; policy gate kiểm tra điều kiện và mức hỗ trợ trước khi thực thi.

CHÚ THÍCH

Chính sách đề xuất, cần đánh giá trên tình huống có nhãn. Mastery thấp không tự động buộc ôn nền.

BỐ CỤC

Bảng tình huống và lựa chọn, cạnh đó là các thông tin Agent đọc. Không trình bày như quy tắc buộc mọi trường hợp có duy nhất một câu trả lời đúng.

GHI CHÚ

Agent chọn trong tập hành động giới hạn; LangGraph điều phối state, tool và checkpoint. Policy gate chứa các ràng buộc bắt buộc, không phải mọi quyết định sư phạm đều do LLM tự do chọn. Lỗi mới không bị bỏ qua vì mastery trước đó cao. Khi thiếu bằng chứng không được bịa lý do; khi timeout/lỗi schema thì dùng policy luật và mẫu hỗ trợ hợp lệ. Dùng policy luật làm baseline để kiểm chứng giá trị quyết định động.

NGUỒN CUỐI SLIDE

Project-plan, mục 8.6, 9 và 18; PRD FR-10–11.

## Slide 11 — Vòng học và báo cáo tiến bộ có căn cứ

NỘI DUNG HIỂN THỊ

Vòng học dự kiến:
1. Nhận bài làm và phân tích bằng chứng.
2. Chọn hỗ trợ, chờ người học phản hồi.
3. Kiểm tra khả năng tự làm khi phù hợp.
4. Chuyển bài, ôn nền có quay lại hoặc kết thúc phiên.

Learning report cần phân biệt:
- Kết quả tự làm và kết quả sau trợ giúp.
- Ước lượng kiến thức cùng số observation hợp lệ.
- Lỗi đã quan sát và giả thuyết còn cần kiểm tra.
- Nội dung nên ôn, gắn bằng chứng và nguồn.

Lưu state/checkpoint để tiếp tục phiên, tránh retry tạo thêm observation.

CHÚ THÍCH

Mastery tăng hoặc làm đúng bài vừa được hướng dẫn chưa tự chứng minh learning gain hay hết misconception.

BỐ CỤC

Vòng học đơn giản bên cạnh một báo cáo minh họa bằng tên trường, không bịa dữ liệu người dùng hoặc phần trăm thành thạo. Phân biệt tiến bộ học tập với tiến độ lập trình dự án.

GHI CHÚ

Mỗi lượt chờ đầu vào thật, không tự tạo phản hồi học sinh để kéo dài loop. Dừng nhánh khi không tiến triển, có thể đổi cách hỗ trợ hoặc cho tạm dừng. Bài mới cần phù hợp mục tiêu đo, không coi đổi số ngay sau gợi ý là bằng chứng chuyển giao mạnh. Báo cáo giữ giới hạn ước lượng, số bằng chứng không phải khoảng tin cậy đã hiệu chỉnh. Việc kiểm tra, lưu phiên và đối soát cập nhật là yêu cầu thiết kế, không tuyên bố đã tích hợp hoàn chỉnh cho toàn phạm vi.

NGUỒN CUỐI SLIDE

Project-plan, mục 10 và 13; PRD FR-14–16 và FR-18.

## Slide 12 — Cách kiểm chứng hướng tiếp cận

NỘI DUNG HIỂN THỊ

| Thành phần/câu hỏi | Bằng chứng cần đo |
|---|---|
| Xác minh và phân tích lỗi | Đúng bước sai đầu tiên, F1 họ lỗi, xử lý chưa đủ bằng chứng |
| BKT | Dự đoán kết quả tiếp theo so với baseline đơn giản |
| KG/RAG | Chọn đúng kiến thức/nội dung, chất lượng hỗ trợ sau truy xuất |
| Agent và phản hồi | Phù hợp tình huống, đúng toán, mức tiết lộ và khả năng hành động |
| Vòng học | Đạt mục tiêu scenario, lưu/tiếp tục, latency và chi phí |

Thiết kế so sánh:
- Hệ thống đầy đủ so với các cấu hình bỏ/thay từng thành phần.
- Baseline LLM được prompt Socratic và baseline policy luật.
- Dùng dev để phát triển; khóa cấu hình và test trước thực nghiệm cuối.

CHÚ THÍCH

Đây là kế hoạch đánh giá. Có nhiều module hoặc dùng framework không tự chứng minh chất lượng tốt hơn.

BỐ CỤC

Một ma trận câu hỏi và phép đo. Không chèn điểm benchmark đã chạy, phần trăm hoàn thành hoặc lịch chưa chốt.

GHI CHÚ

Plan có Full, No-BKT, heuristic thay BKT, No-KG, No-RAG và Rule-policy. Giữ các yếu tố còn lại nhất quán để tách ảnh hưởng từng thành phần. Đánh giá retrieval không thay chất lượng phản hồi; xác minh tốt không tự chứng minh học sinh học tốt hơn. Tình huống script, học sinh mô phỏng và người học thật cần ghi nguồn riêng. Khi báo learning gain cần thiết kế đánh giá phù hợp; kết quả không cải thiện cũng cần công bố. Phần nghiên cứu liên quan có thể chèn ba slide đã chuẩn bị, không tự sửa các nội dung được yêu cầu giữ nguyên.

NGUỒN CUỐI SLIDE

Project-plan, mục 17–19 và 24–25; PRD, mục 9.

## Nguồn nội bộ — không tạo thêm slide

- [Plan tổng](project-plan.md): kiến trúc, workflow, chính sách và đánh giá.
- [PRD](../product/prd.md): yêu cầu từng module và nguyên tắc hỗ trợ.
- [Observation protocol](../research/data/observation-protocol.md): quy tắc observation.
- [Registry](../../content/curriculum/registry.v1.json): nguồn ví dụ quan hệ kiến thức, hiện là đề xuất.
- [Analyzer](../implementation/curriculum/analyzer.v1.md): đối chiếu phạm vi checker, không coi thiết kế là đã hoàn thành.

## Lưu ý cho người soạn — không tạo thêm slide

- Bản này tập trung hướng làm, không báo cáo tiến độ embedding, file output hoặc bảng kết quả model.
- Toàn bộ kiến trúc là thiết kế mục tiêu; không suy ra đã hoàn tất triển khai.
- Ví dụ workflow là tình huống minh họa, không gắn nhãn demo end-to-end.
- Lưu riêng việc xác minh bước sai và giả thuyết nguyên nhân.
- Số observation là bằng chứng hỗ trợ ước lượng, không phải xác suất tin cậy đã hiệu chỉnh.
- Không tự đổi phạm vi sang toàn bộ chương trình. Khoảng 40 concept là mục tiêu kiểm chứng trong plan hiện tại.
- Nội dung/quan hệ kiến thức cần review; không tuyên bố nháp đã được giáo viên duyệt.
- Ba slide MathDial, Daheim và Pardos & Bhandari là tài liệu soạn riêng; giữ nguyên nếu người dùng đã thêm.
