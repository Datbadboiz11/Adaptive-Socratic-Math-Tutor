# Hướng dẫn chấm rubric Socratic, bản v1

**Trạng thái:** bản nháp `socratic-rubric-0.1.0` của Member 3, **chưa pilot**. Sáu chiều và điều kiện đạt 2 điểm lấy nguyên từ plan §19.2. Mô tả mức 1, mức 0 và các ví dụ là phần bổ sung, cần sửa sau khi hai người chấm thử trên bộ pilot.
**Căn cứ:** plan §19.1, §19.2; PRD §9.4, §9.6. **Quy trình và công cụ:** [rating-workflow.v1.md](rating-workflow.v1.md). **Định nghĩa trong code:** [`research/evaluation/rubric.py`](../../../research/evaluation/rubric.py).

Tài liệu này là phần giao cho người chấm. Đọc hết trước khi chấm câu đầu tiên.

## 1. Bạn chấm gì

Mỗi mục trong `items.md` là một **lượt** của gia sư. Mục gồm ngữ cảnh trước lượt đó (đề, bài làm, kết quả chấm bài, lịch sử hỗ trợ) và **câu gia sư gửi học sinh**. Bạn chấm câu đó theo sáu chiều, mỗi chiều 0, 1 hoặc 2 điểm, rồi đánh dấu vi phạm nghiêm trọng nếu có.

- **Chỉ chấm câu gia sư gửi.** Đừng đoán hệ thống nào viết câu, và đừng chấm theo việc bạn nghĩ hệ thống đã "định làm gì".
- **Chấm từng chiều độc lập.** Một câu lộ đáp án vẫn có thể rõ ràng (2 điểm "Rõ ràng"). Đừng hạ mọi chiều vì một lỗi.
- **Dùng ngữ cảnh.** "Bám lỗi" và "Phù hợp người học" chỉ chấm được khi đối chiếu với bài làm, kết quả chấm và lịch sử.
- **Đáp án** được ghi trong ngữ cảnh để bạn chấm "Đúng toán" và "Không tiết lộ". Học sinh không thấy dòng đó.
- **Không có xác suất mastery.** Ngữ cảnh chỉ có bằng chứng quan sát được (số lần tự làm, đúng/sai gần nhất, số lần được hỗ trợ). Bạn tự đánh giá mức hỗ trợ có hợp không từ bằng chứng đó; giá trị BKT không phải đáp án chuẩn (PRD §9.4).
- **Nhiều cách dạy đều có thể đạt.** Không có một câu "đúng" duy nhất cho mỗi lượt.

Ví dụ bên dưới dùng cùng một ngữ cảnh, trừ khi ghi khác (tình huống dev SC-01):

> Đề: Giải phương trình 2(x - 3) = 10. Đáp án: x = 8.
> Bài làm: (1) `2x - 3 = 10`, (2) `2x = 13`, (3) `x = 6.5`.
> Kết quả chấm: sai; bước sai đầu tiên là bước 1; họ lỗi `distribution_error` (nhân 2 chưa đủ các số hạng trong ngoặc), giả thuyết còn ở mức nghi ngờ. Đây là lần sai đầu tiên trên bước này, chưa có gợi ý nào.

## 2. Sáu chiều

### 2.1. Đúng toán (`math_correct`)

| Điểm | Khi nào |
|---|---|
| 2 | Không có phát biểu hay biến đổi sai, giữ điều kiện áp dụng. |
| 1 | Có chỗ thiếu chính xác nhỏ (diễn đạt, thiếu điều kiện) nhưng không dẫn học sinh tới kết quả sai. |
| 0 | Có phát biểu hoặc biến đổi sai. |

- 2: "Ở bước 1, em đã nhân 2 với những số hạng nào trong ngoặc?"
- 1: "Nhớ là chuyển vế thì phải đổi dấu nhé, em xem lại bước 1?" Quy tắc thiếu điều kiện (chỉ áp dụng cho số hạng của một tổng), dù không làm sai bài này.
- 0: "Ở bước 2 em viết 2x = 12, em làm thế nào ra được?" Học sinh viết `2x = 13`; gia sư trích sai bài làm.
- 0 kèm cờ **lỗi toán nghiêm trọng**: "Bước 1 của em đúng rồi, 2(x - 3) bằng 2x - 3." Xác nhận một biến đổi sai là đúng.

### 2.2. Bám lỗi (`error_focus`)

| Điểm | Khi nào |
|---|---|
| 2 | Hướng đến đúng vấn đề có bằng chứng ở lượt này (bước sai, họ lỗi, bài chưa đọc được...). |
| 1 | Liên quan đến bài nhưng chung chung, hoặc chỉ chạm một phần vấn đề. |
| 0 | Không liên quan đến vấn đề có bằng chứng, hoặc nhắm vào chỗ không có lỗi. |

- 2: "Ở bước 1, em đã nhân 2 với những số hạng nào trong ngoặc?"
- 1: "Em xem lại bài làm của mình nhé, có chỗ nào chưa ổn không?"
- 0: "Ở bước 3, em chia 13 cho 2 đã đúng chưa?" Bước 3 không sai.

"Vấn đề có bằng chứng" không chỉ là lỗi: bài không đọc được, học sinh xin gợi ý, học sinh đã làm đúng cũng là vấn đề của lượt. Ví dụ học sinh vừa làm đúng (SC-10) mà gia sư khen đúng việc học sinh đã sửa rồi giao bài mới thì đạt 2.

### 2.3. Phù hợp người học (`learner_fit`)

| Điểm | Khi nào |
|---|---|
| 2 | Mức hỗ trợ phù hợp bằng chứng làm bài độc lập, số lần đã được hỗ trợ và lịch sử. |
| 1 | Hỗ trợ hơi nhiều hoặc hơi ít so với bằng chứng. |
| 0 | Rõ ràng không phù hợp: chỉ cách làm chi tiết khi mới sai lần đầu, hoặc lặp câu hỏi chung khi học sinh đã bế tắc nhiều lượt. |

- 2: lần sai đầu, gia sư hỏi chẩn đoán: "Ở bước 1, em đã nhân 2 với những số hạng nào trong ngoặc?"
- 1: lần sai đầu, gia sư nhắc luôn quy tắc: "Khi nhân một số với một hiệu trong ngoặc, em nhân số đó với từng số hạng. Em xem lại bước 1 nhé?" Hợp lý nhưng hơi nhiều so với lần sai đầu.
- 0: lần sai đầu, gia sư chỉ từng thao tác: "Em nhân 2 với x, rồi nhân 2 với -3, sau đó cộng 6 vào hai vế."
- 0, ngữ cảnh khác (SC-14: đã hỗ trợ 6 lượt, 4 lượt không tiến triển): gia sư lại hỏi "Em xem lại bài nhé, có chỗ nào chưa ổn không?"

Mức hỗ trợ (plan §9): 0 hỏi mở/chẩn đoán; 1 nhắc kiến thức hoặc mời tự kiểm tra; 2 gợi ý cụ thể hơn, học sinh vẫn tự làm; 3 chia nhỏ bước hoặc minh họa trên bài khác; 4 giải thích khái niệm bằng ví dụ khác rồi để học sinh tự làm.

### 2.4. Gợi mở (`elicits`)

| Điểm | Khi nào |
|---|---|
| 2 | Để học sinh thực hiện phần suy luận tiếp theo. |
| 1 | Có mời học sinh làm, nhưng câu hỏi chỉ cần đáp có/không hoặc đã làm gần hết phần suy luận. |
| 0 | Làm thay phần suy luận tiếp theo, hoặc không mời học sinh làm gì. |

- 2: "Nếu viết 2(x - 3) thành (x - 3) + (x - 3), em thấy số -3 xuất hiện mấy lần?"
- 1: "Ở bước 1 em phải nhân 2 với cả -3 nữa, đúng không?" Câu hỏi đã chứa câu trả lời.
- 0: "Bước 1 phải là 2x - 6 = 10 nhé." Làm thay bước của học sinh.

### 2.5. Không tiết lộ (`no_reveal`)

| Điểm | Khi nào |
|---|---|
| 2 | Không đưa đáp án hay lời giải hoàn chỉnh, cũng không đưa bước sửa đúng của bài hiện tại. |
| 1 | Lộ một phần: đưa kết quả trung gian hoặc bước sửa đúng của một bước, học sinh vẫn còn ít nhất một bước biến đổi phải tự làm. |
| 0 | Đưa đáp án cuối hoặc lời giải hoàn chỉnh, kể cả viết dạng tương đương hoặc gọi đó là bước sửa đúng của bước cuối. |

- 2: "Ở bước 1, em đã nhân 2 với những số hạng nào trong ngoặc?"
- 1: "Bước 1 phải là 2x - 6 = 10, giờ em làm tiếp nhé." Học sinh còn phải tự chuyển vế và chia.
- 0 kèm cờ **tiết lộ**: "Nghiệm là x = 8." Cũng tính khi viết dạng khác: "Nghiệm là 16/2.", "x bằng 2 mũ 3", hoặc kể lần lượt các bước đến hết bài.
- 0 kèm cờ **tiết lộ**: "Bước 3 phải là x = 8 nhé." Bước được sửa chính là đáp án cuối.

Ranh giới giữa 1 và 0: sau phần gia sư đã đưa, học sinh còn phải tự làm **ít nhất một bước biến đổi** thì là 1. Nếu chỉ còn ghi kết quả hoặc tính một phép số học (như từ "x = 16/2") thì bài coi như đã được giải thay: 0 điểm và đánh cờ.

Lưu ý:
- **Được 1 điểm ở chiều này chưa có nghĩa là hỗ trợ tốt.** Câu đưa sẵn một bước sửa đúng không làm lượt thất bại, nhưng vẫn bị chấm thấp ở "Gợi mở" (làm thay bước của học sinh) và ở "Phù hợp người học" nếu bằng chứng chưa cần hỗ trợ đến mức đó.
- Học sinh **đã tự giải đúng** bài (kết quả chấm "đúng") thì gia sư xác nhận lại đáp án của chính học sinh không phải tiết lộ.
- Câu **giao bài mới** thì đáp án bài mới cũng không được lộ. Đề và đáp án bài mới được ghi ngay dưới câu giao bài. Ở phiếu ghép cặp, câu A và câu B có dòng riêng vì hai hệ thống có thể giao hai bài khác nhau.
- Ví dụ trên **một bài khác** (khác số, khác đề) không phải tiết lộ bài hiện tại.

### 2.6. Rõ ràng (`clarity`)

| Điểm | Khi nào |
|---|---|
| 2 | Ngắn, hiểu được, không hỏi dồn nhiều việc. |
| 1 | Hiểu được nhưng dài, vòng vo hoặc hỏi hai việc. |
| 0 | Khó hiểu, mâu thuẫn hoặc hỏi dồn nhiều việc. |

- 2: "Ở bước 1, em đã nhân 2 với những số hạng nào trong ngoặc?"
- 1: "Em xem bước 1 nhân thế nào, rồi kiểm tra luôn bước 2 có chuyển vế đúng không?"
- 0: "Em xem lại bước 1 đi, bước 2 nữa, mà em có nhớ quy tắc phân phối không, nó là gì, em áp dụng vào bài này thế nào, rồi kết quả cuối em có thay vào đề chưa?"

## 3. Vi phạm nghiêm trọng

Plan §19.2: lỗi toán nghiêm trọng hoặc tiết lộ lời giải làm lượt đó **thất bại dù tổng điểm cao**. Ghi `1` vào cột tương ứng khi có:

| Cờ | Khi nào | Điểm bắt buộc |
|---|---|---|
| `serious_math_error` | Sai ở chính kiến thức hoặc bước đang dạy, hoặc xác nhận một bước sai là đúng; học sinh có thể tin vào điều sai đó. Lỗi nhỏ, dễ nhận ra (trích nhầm một con số) thì chỉ cho 0 hoặc 1 điểm, không đánh cờ. | "Đúng toán" = 0 |
| `solution_revealed` | Đưa đáp án cuối hoặc lời giải hoàn chỉnh của bài hiện tại hay bài vừa giao, kể cả dạng tương đương. | "Không tiết lộ" = 0 |

Có cờ thì chiều tương ứng phải là 0. Chiều ngược lại khác nhau giữa hai cờ:

- **"Không tiết lộ" = 0 thì luôn phải đánh cờ `solution_revealed`.** Mức 0 của chiều này chính là định nghĩa của cờ, nên điểm 0 mà thiếu cờ sẽ làm lượt đó không được tính là thất bại.
- "Đúng toán" có thể 0 mà không có cờ, khi lỗi nhỏ và dễ nhận ra.

Script chấm sẽ báo lỗi, kèm số dòng, nếu phiếu mâu thuẫn với các quy tắc trên.

## 4. Trường hợp đặc biệt

- **Không áp dụng (`na`).** Lượt không có việc học, như học sinh xin tạm dừng hoặc hết buổi (SC-13: "Mình tạm dừng ở đây nhé. Lần sau em có thể học tiếp từ bài đang làm."), thì "Bám lỗi" và "Gợi mở" ghi `na`. Bốn chiều còn lại luôn phải chấm. Chỉ dùng `na` cho lượt tạm dừng hoặc kết thúc phiên. Học sinh vừa làm đúng vẫn là lượt học (xem §2.2), không ghi `na`.
- **Không chấm được.** Câu bị cắt, không phải tiếng Việt, hay ngữ cảnh thiếu đến mức không chấm được thì ghi `1` ở cột `unratable`, để trống điểm, và **ghi lý do** ở cột `note`.
- **Không chắc giữa hai mức** thì chọn mức thấp hơn và ghi lý do ở `note`. Ghi chú này dùng để sửa guideline sau pilot.

## 5. So sánh từng cặp (nếu bộ bài có `pairs.md`)

Mỗi cặp có cùng ngữ cảnh và hai câu A, B của hai hệ thống. Chọn câu tốt hơn **cho học sinh ở lượt này**: `A`, `B`, hoặc `tie` khi hai câu tốt ngang nhau. Câu có vi phạm nghiêm trọng thua câu không có. Vị trí A/B được xáo riêng cho từng người chấm, nên đừng so đáp án với người khác theo chữ A/B.

## 6. Cách điền phiếu

1. Mở `items.md` và `ratings.csv` trong thư mục của bạn. Hai file cùng thứ tự; chấm theo mã ở cột `item_id`.
2. Mỗi dòng: sáu cột điểm (`0`, `1`, `2`, hoặc `na` cho hai chiều được phép), hai cột cờ (`1` nếu có, để trống nếu không), `unratable`, `note`. Cột `message` chỉ để đối chiếu, không cần sửa.
3. Dòng chưa điền gì được coi là chưa chấm; dòng điền dở sẽ bị báo lỗi.
4. Giữ nguyên dòng tiêu đề và lưu file ở dạng **CSV UTF-8**. Excel lưu bằng dấu phẩy, chấm phẩy hay tab đều đọc được; file thiếu cột hoặc sai mã hóa sẽ bị báo lỗi chứ không bị coi là chưa chấm.
5. **Chấm độc lập.** Không bàn với người chấm khác trước khi nộp phiếu, không mở `key.json`. Điểm trước hòa giải được giữ nguyên để tính độ đồng thuận (PRD §9.4).
6. Chấm xong thì gửi lại `ratings.csv` (và `pairs.csv` nếu có). Câu hai người chấm khác nhau sẽ được đưa vào buổi hòa giải.

## 7. Đối chiếu với guideline MRBench

Guideline chấm của MRBench (Maurya và cộng sự, NAACL 2025; bản tải về ở `data/external/mrbench/`) có tám chiều, mỗi chiều ba nhãn (phần lớn là Yes / To some extent / No). Rubric này không dùng lại các chiều đó mà theo plan §19.2. Hai cách làm học từ guideline đó: (1) cho người chấm thấy lời giải đúng (gold solution) để chấm việc lộ đáp án; (2) yêu cầu chấm từng chiều độc lập. Các chiều gần nhau: "Revealing of the Answer" ↔ Không tiết lộ; "Mistake Identification", "Mistake Location" ↔ Bám lỗi; "Providing Guidance" ↔ Gợi mở và Đúng toán.
