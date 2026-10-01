# Kế hoạch phần tiếp theo — từ prototype đến MVP G2

**Ngày lập:** 01/10/2026.  
**Trạng thái:** Chỉ lập kế hoạch; chưa triển khai các hạng mục bên dưới.  
**Hạn theo thông báo người dùng cung cấp:** 23:59 Chủ nhật, 04/10/2026. Lịch bên dưới dùng giờ Việt Nam; đối chiếu múi giờ của thông báo trước khi nộp.

## 1. Điểm xuất phát

- Đã có [brief](../brief_de_tai_socratic_math_tutor.md), [PRD 0.2](../PRD_Adaptive_Socratic_Math_Tutor.md) và [kế hoạch đồ án](../plan_de_tai_socratic_math_tutor.md).
- Đã có [prototype Mở](../design/README.md), UI flow và kiểm tra giao diện. Phản hồi, hồ sơ và tiến trình trong prototype đang là mô phỏng.
- Chủ repo đã tạo [Adaptive-Socratic-Math-Tutor](https://github.com/Datbadboiz11/Adaptive-Socratic-Math-Tutor). Thư mục dự án đang được kết nối với repo này; xem [thiết lập repository](../docs/REPOSITORY_SETUP.md). Chưa có backend/frontend sản phẩm hoặc cấu hình chạy các dịch vụ MVP.
- Có dữ liệu trong `data/`; việc có file không đồng nghĩa đã tiền xử lý, đánh giá hoặc fit BKT.

## 2. Đọc và thực hiện theo thứ tự

| Phần | Nội dung | Đầu ra chính |
|---|---|---|
| [Phần 1](phan1_chot_pham_vi_va_chuan_bi.md) | Chốt phạm vi và chuẩn bị | Danh sách MVP, contract, nội dung mẫu, repo và phân công |
| [Phần 2](phan2_backend_va_du_lieu.md) | Backend và lưu dữ liệu | API, DB, session, submit/retry/resume, report |
| [Phần 3](phan3_gia_su_socratic.md) | Xử lý Toán và gia sư | Validator, observation, BKT tối thiểu, luồng Socratic thật |
| [Phần 4](phan4_frontend_va_tich_hop.md) | Frontend và tích hợp | Một hành trình sử dụng chạy xuyên suốt |
| [Phần 5](phan5_kiem_thu_va_bang_chung.md) | Kiểm thử và evidence | Ít nhất 5 ca manual có output thực tế |
| [Phần 6](phan6_dong_goi_va_nop_mvp.md) | Đóng gói, demo và nộp | README, sơ đồ, video 3 phút, ≥10 PR merged, thư mục tổng hợp |

Phần 2 và 3 dùng chung contract từ phần 1. Thành viên frontend có thể dựng component ở phần 4 trong lúc backend làm việc; chỉ được đánh dấu tích hợp xong khi đã nối dịch vụ thật.

## 3. MVP G2 và đồ án cuối kỳ

Đề xuất G2 làm một lát cắt nhỏ: **phương trình bậc nhất một ẩn**, từ chọn bài đến báo cáo. Đây là phạm vi đề xuất cho gate gần nhất, không sửa các yêu cầu nghiệm thu của PRD. Ảnh thông báo chưa nêu số concept hay thành phần kỹ thuật tối thiểu; nhóm cần đối chiếu rubric G2 nếu có.

| Cần cho bản G2 đề xuất | Sau khi G2 chạy ổn định |
|---|---|
| Một chủ đề, nội dung và dạng bài được duyệt | Mốc 8–10 concept và mục tiêu 40 concept theo PRD |
| Kiểm tra bước giải trong phạm vi công bố | Thêm dạng toán, đánh giá analyzer trên tập rộng |
| Gia sư gợi mở có kiểm tra đầu ra, giới hạn lượt | KG/RAG đầy đủ, policy và thực nghiệm ablation |
| Log evidence, BKT tối thiểu với tham số có version | Fit/benchmark KT và kiểm tra khả năng chuyển miền |
| Lưu phiên, retry an toàn, report từ DB | Pilot học sinh, tối ưu hiệu năng và mở rộng UI |

Nếu chưa hoàn thành BKT/LangGraph hoặc thành phần nào đã cam kết, phải ghi rõ tình trạng trong README và demo. Không gọi bản giảm phạm vi là đã hoàn thành toàn bộ P0 của PRD. Không dành thời gian fit dataset, thêm OCR, dashboard giáo viên hay làm lại phong cách UI trước khi có luồng chạy thật.

## 4. Lịch mục tiêu

Lịch này giả định 3 thành viên như brief, có môi trường chạy và ngân sách API. Đây là lịch gấp; cuối mỗi ngày kiểm tra đầu ra thực tế.

| Ngày | Mốc cần đạt | Nếu chậm |
|---|---|---|
| 01/10 | Chốt phần 1; dựng API/DB và frontend; tạo phiên, đọc một bài từ DB | Giảm màn hình phụ, giữ một chủ đề và một hành trình |
| 02/10 | Submit → validator → phản hồi Socratic → lưu kết quả chạy được | Dừng mở rộng nội dung; giải quyết tích hợp trước |
| 03/10 | Report, resume, retry, kiểm thử; các PR chức năng được review/merge | Ưu tiên sửa lỗi chấm toán, trùng observation, lộ lời giải, mất phiên |
| 04/10 trước 15:00 | Chạy từ môi trường sạch, chốt commit và evidence | Ghi giới hạn còn lại trung thực; không thêm tính năng |
| 04/10 trước 20:00 | Hoàn tất video, README, sơ đồ, danh sách PR và link tổng hợp | Giữ khoảng dự phòng cho lỗi upload/quyền truy cập |
| 04/10 trước 23:59 | Đại diện nhóm nộp `/gate submit` theo hướng dẫn Discord | Lưu xác nhận nộp |

## 5. Chia công việc thành PR có ý nghĩa

Các tên sau là **kế hoạch PR**, chưa phải PR đã tạo hoặc merge. Kiểm tra PR hợp lệ đã có trong repo và tránh tạo trùng. PR được review trước khi merge; mỗi PR ghi thay đổi, cách kiểm tra và giới hạn.

| PR dự kiến | Nội dung | Đầu mối | Phụ thuộc |
|---|---|---|---|
| 01 | Khung repo, cấu hình môi trường, cách chạy và health check | TV3 | Chốt repo |
| 02 | Schema DB, migration, profile/session/opportunity | TV1 | 01 + contract |
| 03 | Registry, bộ bài và nội dung gợi ý đã duyệt; seed chạy lại được | TV2 | 02 |
| 04 | API tạo phiên, lấy bài, nộp bài; trạng thái lỗi có schema | TV3 | 02, 03 |
| 05 | Validator phương trình và kiểm tra bước sai đầu tiên | TV1 | Contract phần 1 |
| 06 | Observation, BKT có version, chống ghi lặp | TV1 | 02, 05 |
| 07 | Luồng LangGraph, policy Socratic, LLM và fallback | TV3 | 03–06 |
| 08 | UI phiên học và tích hợp API, loading/error/retry | TV3; TV2 hỗ trợ UI | 04, 07 |
| 09 | Lưu draft, pause/resume, kết thúc và report từ DB | TV2; TV1 review | 06–08 |
| 10 | Kiểm thử hồi quy trọng yếu và bộ manual evidence | Cả nhóm | 09 |
| 11 | README, sơ đồ thực tế, kịch bản demo và chỉ mục bàn giao | TV2 | Bản đã kiểm thử |

TV3 đang có tải tích hợp lớn: TV2 hỗ trợ chuyển UI, report và tài liệu; TV1 review retry/state. Có thể thay đầu mối theo năng lực. Không tách thay đổi vô nghĩa chỉ để đủ số lượng PR.

## 6. Checklist tổng

- [ ] Phạm vi G2 đã chốt và phù hợp rubric được cung cấp.
- [ ] Luồng học chạy bằng backend và dữ liệu thật của phiên thử.
- [ ] Các trạng thái hỗ trợ/độc lập/chưa xác minh được ghi đúng.
- [ ] ≥10 PR hợp lệ đã merge vào nhánh nộp.
- [ ] ≥5 ca manual có output thực tế và bằng chứng.
- [ ] Sơ đồ khớp đúng các thành phần đang chạy.
- [ ] Người khác làm theo README chạy được.
- [ ] Video khoảng 3 phút bám một luồng end-to-end.
- [ ] Các link nộp truy cập được; đã lưu xác nhận gate.

**Bước bắt đầu khi triển khai:** mở phần 1, chốt phạm vi, repository, người phụ trách và môi trường. Các checkbox hiện đều để trống vì đây mới là kế hoạch.
