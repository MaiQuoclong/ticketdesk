# Thiết kế Wireframe 5 Màn hình chính (Tuần 3)

Wireframe 5 màn hình chính được phác thảo trên Figma ở mức khung (low-fidelity wireframe) để thống nhất bố cục và luồng thao tác trước khi lập trình giao diện.

| Màn hình | Vai trò sử dụng | Thành phần chính |
| :--- | :--- | :--- |
| **1. Đăng nhập** | Tất cả | Ô tên đăng nhập, mật khẩu, nút `"Đăng nhập"`, vùng hiển thị thông báo lỗi; đăng nhập xong chuyển hướng theo vai trò. |
| **2. Danh sách ticket** | Tất cả | Thanh lọc theo trạng thái, mức ưu tiên, người xử lý, ô tìm kiếm từ khóa; bảng danh sách ticket (mã, tiêu đề, trạng thái, ưu tiên, người xử lý, ngày tạo); thanh phân trang. |
| **3. Tạo ticket** | `Customer` | Form nhập tiêu đề, chọn danh mục, mức ưu tiên, mô tả chi tiết, khu vực kéo thả tệp đính kèm, nút `"Gửi"`. |
| **4. Chi tiết ticket** | Tất cả | Thông tin chi tiết ticket; khối thao tác `Gán` / `Đổi trạng thái` (hiển thị theo quyền); tab `Bình luận` (có ô đánh dấu ghi chú nội bộ cho `Agent`/`Manager`), tab `Đính kèm`, tab `Lịch sử`. |
| **5. Dashboard** | `Manager` | Thẻ số liệu tổng quan; biểu đồ ticket theo trạng thái và theo người xử lý; danh sách `"Quá SLA"` tô đỏ; nút `"Xuất Excel"`. |
