# Quy trình làm việc của nhóm

## Nhánh và pull request

`main` là bản tích hợp ổn định. Sau lần khởi tạo repository, thực hiện từng thay đổi có ý nghĩa trên nhánh riêng và mở PR về `main`.

```powershell
git switch main
git pull --ff-only origin main
git switch -c feat/session-api
# Sửa file và kiểm tra, sau đó stage đúng các file cần đưa lên.
git add <cac-file-da-kiem-tra>
git commit -m "feat: add session API"
git push -u origin feat/session-api
```

Mở tab **Pull requests → New pull request** trên GitHub. Ghi vấn đề, thay đổi, cách kiểm tra và giới hạn. Nhờ một thành viên khác review khi có thể, đợi CI đạt rồi **Squash and merge**. Xóa nhánh làm việc sau khi merge.

Tên nhánh gợi ý: `feat/…`, `fix/…`, `docs/…`, `test/…`, `chore/…`. Không commit thẳng lên `main` cho công việc thông thường; không force-push `main`.

## Checklist trước PR

- Chỉ chứa những thay đổi thuộc mục tiêu của PR; mô tả liên kết với phần kế hoạch/issue nếu có.
- Không có API key, `.env`, dataset thô, dữ liệu học sinh hoặc dependency đã cài.
- Chạy kiểm tra liên quan; nếu chưa chạy, ghi rõ thay vì đánh dấu đạt.
- Thay đổi UI có ảnh phù hợp; thay đổi hành vi có output hoặc bước tái hiện.
- Tách kết quả mô phỏng khỏi kết quả từ hệ thống thật.

## Theo dõi gate MVP

Gate yêu cầu ≥10 PR đã merge. Commit khởi tạo không tự trở thành PR. Dùng [bảng công việc dự kiến](plan/README.md) để chia thay đổi có ý nghĩa và ghi các link PR thực tế khi hoàn thành. Không tạo PR rỗng hoặc chia nhỏ vô nghĩa để tăng số lượng.

## Thiết lập máy thành viên

Mỗi người dùng Git identity và tài khoản GitHub của chính mình. Chủ repo mời thành viên ở **Settings → Collaborators** bằng username của họ; không chia sẻ token hoặc đăng nhập của chủ repo. Kiểm tra README để chạy prototype và các check hiện có.
