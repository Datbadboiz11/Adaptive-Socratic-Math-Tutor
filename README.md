# Adaptive Socratic Math Tutor — Mở

Trợ lý học Toán bằng câu hỏi gợi mở, thuộc đề tài **VIN-02: Nghiên cứu và xây dựng trợ lý AI dạy học Toán theo phương pháp Socratic thích ứng sử dụng AI Agent**.

## Trạng thái hiện tại

Repository hiện chứa **brief, PRD, kế hoạch và prototype giao diện tương tác**. Backend, gia sư AI, xác thực và mô hình theo dõi kiến thức của sản phẩm chưa được triển khai. Các phản hồi và hồ sơ trong prototype là dữ liệu mô phỏng.

Mục tiêu đồ án là 30–50 concept, hướng tới 40 concept. Lát cắt MVP G2 đề xuất tập trung vào một chủ đề chạy end-to-end; xem [kế hoạch MVP](plan/README.md).

## Xem prototype

Clone repo:

```powershell
git clone https://github.com/Datbadboiz11/Adaptive-Socratic-Math-Tutor.git
cd Adaptive-Socratic-Math-Tutor
```

Mở `design/index.html` bằng Chrome hoặc Edge. Không cần npm, API key hay backend để xem giao diện.

Hoặc dùng Python 3 phục vụ các file:

```powershell
python -m http.server 8765 --bind 127.0.0.1 --directory design
```

Truy cập <http://127.0.0.1:8765>. Thanh dưới có Wireframe, Luồng và Kịch bản. Chi tiết ở [hướng dẫn thiết kế](design/README.md).

Prototype lưu phiên trong localStorage của trình duyệt. Font web là tùy chọn, có font dự phòng khi offline. Chưa có biến môi trường bắt buộc; `.env.example` sẽ được bổ sung khi triển khai dịch vụ thật.

## Thử luồng mẫu

Chọn **Kịch bản → Bắt đầu bài**, với đề `2(x - 3) = 10`:

1. Gửi `2x - 3 = 10`, `2x = 13`, `x = 6.5` trên các dòng riêng để xem gợi mở cho lỗi phân phối.
2. Sửa thành `2x - 6 = 10`, `2x = 16`, `x = 8` để xem trạng thái đúng sau hỗ trợ.
3. Chọn bài mới, sau đó xem báo cáo phiên.

Đây là kịch bản kiểm thử UI, không phải bằng chứng chấm Toán/LLM chạy thật.

## Tài liệu

| Tài liệu | Nội dung |
|---|---|
| [Brief](brief_de_tai_socratic_math_tutor.md) | Bài toán, phạm vi và giá trị nghiên cứu |
| [PRD](PRD_Adaptive_Socratic_Math_Tutor.md) | Yêu cầu chức năng, dữ liệu và nghiệm thu |
| [Kế hoạch đồ án](plan_de_tai_socratic_math_tutor.md) | Lộ trình đầy đủ và thực nghiệm |
| [Kế hoạch phần tiếp theo](plan/README.md) | 6 phần triển khai và bàn giao MVP G2 |
| [Đặc tả thiết kế](design/DESIGN_SPEC.md) | Màu sắc, bố cục, component và trạng thái |
| [UI flow](design/USER_FLOWS.md) | Luồng sử dụng và ngoại lệ |
| [Quy trình đóng góp](CONTRIBUTING.md) | Nhánh, PR và review |
| [Thiết lập repository](docs/REPOSITORY_SETUP.md) | Cấu hình và những việc cần quản lý trên GitHub |

## Kiểm tra

Kiểm tra cơ bản dùng Node.js và Python 3, không cần thư viện ngoài:

```powershell
node --check design/app.js
python -m py_compile design/audit_ui.py
python scripts/check_repository.py
```

GitHub Actions chạy các kiểm tra này khi push hoặc mở PR vào `main`. Đây là kiểm tra cú pháp và cấu trúc tài liệu, chưa phải kiểm thử backend hoặc chất lượng AI.

Để chạy kiểm tra trình duyệt tùy chọn trong một môi trường Python riêng:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install playwright
.\.venv\Scripts\python.exe -m playwright install chromium
```

Giữ HTTP server ở trên đang chạy, rồi dùng terminal thứ hai:

```powershell
.\.venv\Scripts\python.exe design/audit_ui.py
```

Runner ghi lại ảnh và kết quả trong `design/previews/`; xem diff trước khi commit những thay đổi được tạo lại. [Kết quả prototype đã lưu](design/previews/qa-results.json) được phân biệt với evidence MVP sẽ thu sau.

## Dữ liệu và thông tin nhạy cảm

`data/` không được đưa lên Git vì chứa dataset tải riêng. Các bộ dữ liệu bên ngoài cần tuân thủ điều kiện truy cập/sử dụng; README dữ liệu và pipeline tái lập sẽ được bổ sung khi triển khai phần nghiên cứu. API keys, `.env`, môi trường ảo và file DB cục bộ cũng được bỏ qua.

Chưa chọn giấy phép phân phối mã nguồn; không tự áp một giấy phép cho dataset bên ngoài. Nhóm sẽ quyết định giấy phép phù hợp sau.
