# Thiết lập repository

Repository: <https://github.com/Datbadboiz11/Adaptive-Socratic-Math-Tutor>

## Cấu hình trong mã nguồn

- `.gitignore`: giữ `data/`, secrets, môi trường ảo, build, log và DB cục bộ ngoài Git.
- `.gitattributes`, `.editorconfig`: UTF-8, thống nhất xuống dòng và cách thụt lề.
- `README.md`: trạng thái thật, cách chạy prototype, kiểm tra và chỉ mục tài liệu.
- `CONTRIBUTING.md`: nhánh riêng → PR → CI/review → squash merge.
- `.github/`: mẫu issue/PR và workflow kiểm tra cú pháp/cấu trúc tài liệu.
- `scripts/check_repository.py`: kiểm tra link tương đối và các file không nên theo dõi; không thay thế công cụ phát hiện mọi dạng secrets.

## Chính sách remote mục tiêu

Nhánh mặc định `main`; bật Issues; ưu tiên squash merge, tự xóa nhánh sau merge. Giữ nguyên quyền public/private hiện có của repo, không tự bật GitHub Pages hoặc xuất bản website.

Bảo vệ `main` nếu gói GitHub/quyền hiện có hỗ trợ: PR bắt buộc, check `repository-checks` phải đạt, nhánh phải cập nhật, không force-push/xóa nhánh và phải giải quyết hội thoại review. Chưa bắt buộc số lượt approval khi chưa có collaborator; nhóm có thể đặt 1 approval khi đã mời đủ thành viên. Admin có thể cần quyền xử lý sự cố; quy trình thông thường vẫn đi qua PR.

Các cài đặt remote phải được xác minh trực tiếp sau thao tác; nội dung mục này mô tả chính sách mục tiêu, không khẳng định thao tác đã thành công. Xem thông báo bàn giao hoặc Settings để biết trạng thái thực tế.

## Việc cần thông tin từ chủ repo

- Username GitHub các thành viên để mời cộng tác; không tự đoán danh tính/quyền.
- Giấy phép mã nguồn nếu nhóm muốn phát hành; chưa tự thêm LICENSE.
- API model và tài khoản dịch vụ khi triển khai backend; hiện chưa cần secrets GitHub Actions.

Commit khởi tạo chỉ đưa tài liệu/prototype/cấu hình hiện có lên repo, chưa triển khai kế hoạch MVP. Lịch sử ≥10 PR cho gate cần các PR thực tế được review và merge sau đó.
