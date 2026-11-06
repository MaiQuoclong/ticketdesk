# Tài liệu Yêu cầu Hệ thống TicketDesk (v1.0 — Tuần 2)

## 1. Stakeholder và Phạm vi dự án

### 1.1 Danh sách các bên liên quan (Stakeholders)
- **Khách hàng (`CUSTOMER`):** Nhân viên nội bộ trong doanh nghiệp gửi yêu cầu hỗ trợ kỹ thuật (phần cứng, phần mềm, mạng, tài khoản), theo dõi tiến độ, bình luận và đính kèm tệp.
- **Nhân viên hỗ trợ (`AGENT`):** Kỹ thuật viên IT Helpdesk tiếp nhận các ticket được gán, xử lý sự cố, cập nhật trạng thái (`IN_PROGRESS` -> `RESOLVED`), trao đổi công khai hoặc viết ghi chú nội bộ (`is_internal`).
- **Quản lý bộ phận hỗ trợ (`MANAGER`):** Điều phối và gán người xử lý (`assign`), quản lý danh mục sự cố, xem lịch sử thay đổi, theo dõi Dashboard thống kê SLA và xuất báo cáo Excel.
- **Lập trình viên tích hợp:** Tích hợp với hệ thống qua REST API xác thực bằng JWT và tra cứu tài liệu Swagger.

### 1.2 Phạm vi dự án & Xếp ưu tiên MoSCoW
- **Must have (Bắt buộc cho MVP):**
  - US-01: Đăng nhập theo vai trò (`CUSTOMER`, `AGENT`, `MANAGER`)
  - US-02: Quản lý danh mục sự cố (`Category`)
  - US-03: Khách hàng tạo ticket
  - US-04: Khách hàng chỉ xem ticket của mình (RBAC & chống IDOR)
  - US-05: Quản lý gán người xử lý (`assign`)
  - US-06: Nhân viên hỗ trợ cập nhật trạng thái ticket (`IN_PROGRESS` -> `RESOLVED` -> `CLOSED`)
  - US-07: Bình luận công khai và ghi chú nội bộ trên ticket
  - US-08: Xem lịch sử thay đổi ticket (`TicketHistory` chỉ đọc)
  - US-09: Phân trang, tìm kiếm và lọc danh sách ticket
  - US-10: Xác thực REST API bằng JWT (lưu & thu hồi `Refreshtoken`)
- **Should have (Nên có):**
  - US-11: Đính kèm file vào ticket (giới hạn 5MB, định dạng `.png`, `.jpg`, `.pdf`, `.docx`)
  - US-12: Gửi email thông báo chạy nền qua Celery + Redis
  - US-13: Dashboard thống kê và cảnh báo quá hạn SLA (24 giờ)
  - US-14: Tài liệu API tự động với Swagger UI (`/api/docs/`)
- **Could have (Có thì tốt):**
  - US-15: Xuất báo cáo Excel (`.xlsx`) chạy nền qua Celery
  - US-16: Cập nhật trạng thái, bình luận và lọc động không tải lại trang bằng HTMX
- **Won't have (Ngoài phạm vi MVP lần này):**
  - Chat trực tiếp hai chiều thời gian thực (WebSocket)
  - Ứng dụng di động riêng (iOS/Android)
  - Tích hợp tổng đài thoại (VoIP)

### 1.3 Yêu cầu phi chức năng (Non-Functional Requirements)
- **Bảo mật:** Mật khẩu băm एक chiều; khách hàng tuyệt đối không xem được ticket hoặc ghi chú nội bộ của người khác; kiểm soát định dạng và dung lượng tệp tải lên (tối đa 5MB); HTTPS bắt buộc trên môi trường production.
- **Hiệu năng:** 95% request danh sách ticket (20 ticket/trang) phản hồi dưới 500ms với quy mô 10.000 ticket; các tác vụ gửi email và xuất Excel đẩy vào hàng đợi Celery để không chặn phản hồi HTTP.
- **Vận hành:** Sao lưu cơ sở dữ liệu PostgreSQL tự động hằng ngày, thời gian khôi phục (RTO) dưới 1 giờ.

---

## 2. Danh sách User Story và Tiêu chí nghiệm thu (Given / When / Then)

### US-01: Đăng nhập theo vai trò
- **Story:** Là người dùng hệ thống, tôi muốn đăng nhập bằng tài khoản và mật khẩu để sử dụng các chức năng phù hợp với quyền hạn của mình.
- **Kịch bản 1 (Thành công):**
  - `Given` tài khoản `nhanvien01` tồn tại và đang hoạt động.
  - `When` người dùng nhập đúng tên đăng nhập và mật khẩu hợp lệ.
  - `Then` hệ thống cấp phiên làm việc (Session/JWT) và chuyển hướng tới màn hình tương ứng với vai trò (`Customer`, `Agent`, `Manager`).
- **Kịch bản 2 (Thất bại do sai thông tin):**
  - `Given` người dùng ở trang đăng nhập.
  - `When` người dùng nhập sai mật khẩu hoặc tài khoản không tồn tại.
  - `Then` hệ thống hiển thị thông báo lỗi `"Tài khoản hoặc mật khẩu không chính xác"` và không tạo phiên đăng nhập.

### US-02: Quản lý danh mục sự cố
- **Story:** Là quản lý hỗ trợ, tôi muốn tạo, sửa và xóa danh mục sự cố để phân loại yêu cầu hỗ trợ rõ ràng.
- **Kịch bản 1 (Thành công):**
  - `Given` quản lý `quanly01` đã đăng nhập.
  - `When` quản lý tạo danh mục mới `"Phần cứng"`.
  - `Then` danh mục được lưu thành công và xuất hiện trong danh sách chọn khi tạo ticket.
- **Kịch bản 2 (Không xóa được danh mục đang có ticket):**
  - `Given` danh mục `"Phần mềm"` đang có ticket tham chiếu.
  - `When` quản lý thực hiện xóa danh mục `"Phần mềm"`.
  - `Then` hệ thống từ chối xóa với mã lỗi `409 Conflict` do ràng buộc `PROTECT`.

### US-03: Khách hàng tạo ticket
- **Story:** Là khách hàng, tôi muốn tạo ticket với tiêu đề, mô tả và mức độ ưu tiên để gửi yêu cầu hỗ trợ tới bộ phận xử lý.
- **Kịch bản 1 (Thành công):**
  - `Given` khách hàng `khachhang01` đã đăng nhập và đang ở trang `"Tạo ticket"`.
  - `When` khách hàng nhập đầy đủ tiêu đề, mô tả, chọn mức ưu tiên `"Cao"` và bấm `"Gửi"`.
  - `Then` hệ thống tạo ticket mới có mã định danh (ví dụ `TK-0001`), trạng thái `OPEN`, lưu thời điểm tạo và hiển thị thông báo `"Tạo ticket thành công"`.
- **Kịch bản 2 (Thất bại do thiếu dữ liệu):**
  - `Given` khách hàng đang ở trang `"Tạo ticket"`.
  - `When` khách hàng để trống tiêu đề và bấm `"Gửi"`.
  - `Then` hệ thống hiển thị lỗi `"Tiêu đề không được để trống"` và không tạo ticket.

### US-04: Khách hàng chỉ xem ticket của mình
- **Story:** Là khách hàng, tôi muốn xem danh sách ticket do mình tạo, đồng thời người khác không xem được ticket của tôi, để bảo đảm tính riêng tư.
- **Kịch bản 1 (Thành công):**
  - `Given` khách hàng `khachhang01` đã tạo 3 ticket.
  - `When` khách hàng mở trang `"Ticket của tôi"`.
  - `Then` hệ thống hiển thị đúng 3 ticket của `khachhang01`, không có ticket của người khác.
- **Kịch bản 2 (Thất bại do truy cập trái phép):**
  - `Given` khách hàng `khachhang01` đã đăng nhập và ticket `TK-0005` thuộc về `khachhang02`.
  - `When` `khachhang01` truy cập trực tiếp đường dẫn chi tiết của `TK-0005`.
  - `Then` hệ thống trả lỗi `403` hoặc `404` và không hiển thị nội dung ticket.

### US-05: Quản lý gán người xử lý
- **Story:** Là quản lý hỗ trợ, tôi muốn gán ticket cho một nhân viên hỗ trợ cụ thể để phân bổ công việc hợp lý.
- **Kịch bản 1 (Thành công):**
  - `Given` ticket `TK-0001` đang ở trạng thái `OPEN` và chưa có người xử lý; quản lý `quanly01` đã đăng nhập.
  - `When` quản lý chọn nhân viên `agent01` và bấm `"Gán"`.
  - `Then` ticket được gán cho `agent01`, trạng thái chuyển sang `ASSIGNED`, và lịch sử ghi lại `"quanly01 gán cho agent01"` kèm thời gian.
- **Kịch bản 2 (Thất bại do sai quyền):**
  - `Given` nhân viên hỗ trợ `agent01` đã đăng nhập.
  - `When` `agent01` cố gán ticket `TK-0001` cho `agent02`.
  - `Then` hệ thống trả lỗi `403 "Bạn không có quyền gán ticket"` và người xử lý của ticket không thay đổi.

### US-06: Nhân viên hỗ trợ cập nhật trạng thái ticket
- **Story:** Là nhân viên hỗ trợ, tôi muốn cập nhật trạng thái ticket (`IN_PROGRESS` -> `RESOLVED` -> `CLOSED`) để phản ánh đúng tiến độ xử lý.
- **Kịch bản 1 (Thành công):**
  - `Given` ticket `TK-0001` được gán cho `agent01` và đang ở trạng thái `IN_PROGRESS`.
  - `When` `agent01` chuyển trạng thái sang `RESOLVED`.
  - `Then` hệ thống cập nhật trạng thái, lưu thời điểm giải quyết (`resolved_at`) và ghi một bản ghi vào lịch sử.
- **Kịch bản 2 (Thất bại do chuyển trạng thái không hợp lệ):**
  - `Given` ticket `TK-0002` đang ở trạng thái `CLOSED`.
  - `When` nhân viên cố chuyển ticket sang `IN_PROGRESS`.
  - `Then` hệ thống hiển thị lỗi `"Không thể chuyển trạng thái từ CLOSED sang IN_PROGRESS"` (`409 Conflict`) và giữ nguyên trạng thái.

### US-07: Bình luận trên ticket
- **Story:** Là khách hàng hoặc nhân viên hỗ trợ, tôi muốn bình luận trên ticket để trao đổi thông tin về vấn đề cần xử lý.
- **Kịch bản 1 (Thành công):**
  - `Given` người dùng có quyền xem ticket `TK-0001`.
  - `When` người dùng nhập nội dung bình luận và bấm `"Gửi"`.
  - `Then` bình luận hiển thị trong ticket kèm tên tác giả và thời gian, sắp xếp theo thứ tự thời gian.
- **Kịch bản 2 (Ghi chú nội bộ bị ẩn với khách hàng):**
  - `Given` `agent01` đã thêm một bình luận đánh dấu `"Ghi chú nội bộ"` (`is_internal=True`) vào ticket `TK-0001`.
  - `When` khách hàng `khachhang01` mở chi tiết ticket `TK-0001`.
  - `Then` khách hàng không thấy ghi chú nội bộ đó, chỉ thấy các bình luận công khai.

### US-08: Xem lịch sử thay đổi ticket
- **Story:** Là quản lý hỗ trợ, tôi muốn xem toàn bộ lịch sử thay đổi của ticket để truy vết ai đã làm gì và vào lúc nào.
- **Kịch bản 1 (Thành công):**
  - `Given` ticket `TK-0001` đã đổi trạng thái 2 lần và đổi người xử lý 1 lần.
  - `When` quản lý mở tab `"Lịch sử"` của ticket.
  - `Then` hệ thống hiển thị 3 bản ghi, mỗi bản ghi có người thực hiện, giá trị cũ, giá trị mới và thời gian.
- **Kịch bản 2 (Lịch sử không thể chỉnh sửa):**
  - `Given` quản lý đang xem lịch sử ticket.
  - `When` có người cố sửa hoặc xóa một bản ghi lịch sử (qua giao diện hoặc API).
  - `Then` hệ thống từ chối với lỗi `403` hoặc `405` và lịch sử giữ nguyên.

### US-09: Phân trang và lọc danh sách ticket
- **Story:** Là nhân viên hỗ trợ, tôi muốn lọc ticket theo trạng thái, mức ưu tiên, người xử lý và xem theo trang để tìm ticket nhanh chóng.
- **Kịch bản 1 (Thành công):**
  - `Given` hệ thống có 135 ticket, trong đó 50 ticket ở trạng thái `OPEN`.
  - `When` người dùng gọi `GET /api/v1/tickets/?status=OPEN&page=2&page_size=20`.
  - `Then` hệ thống trả 20 ticket `OPEN` (từ thứ 21 đến 40), kèm `count = 50` và các liên kết `next`/`previous`.
- **Kịch bản 2 (Tham số không hợp lệ):**
  - `Given` người dùng đang dùng chức năng lọc.
  - `When` gọi `?page=999` (vượt số trang) hoặc `?status=ABC` (giá trị không tồn tại).
  - `Then` hệ thống trả `404 "Trang không tồn tại"` hoặc `400 "Giá trị trạng thái không hợp lệ"`.

### US-10: Xác thực REST API bằng JWT
- **Story:** Là lập trình viên tích hợp, tôi muốn gọi REST API bằng JWT để thao tác với ticket từ ứng dụng khác một cách an toàn.
- **Kịch bản 1 (Thành công):**
  - `Given` lập trình viên có tài khoản hợp lệ.
  - `When` gửi `POST /api/v1/auth/login/` với tên đăng nhập và mật khẩu đúng, sau đó gọi `GET /api/v1/tickets/` kèm header `Authorization: Bearer <access_token>`.
  - `Then` hệ thống trả access token và refresh token, và lời gọi lấy danh sách ticket trả về `200` với dữ liệu đúng theo quyền của tài khoản.
- **Kịch bản 2 (Thất bại do thiếu hoặc hết hạn token):**
  - `Given` lời gọi API không kèm token, hoặc kèm token đã hết hạn.
  - `When` gọi `GET /api/v1/tickets/`.
  - `Then` hệ thống trả `401 "Chưa xác thực hoặc token hết hạn"` và không trả dữ liệu.

### US-11: Đính kèm file vào ticket
- **Story:** Là khách hàng, tôi muốn đính kèm ảnh hoặc tài liệu vào ticket để mô tả vấn đề rõ ràng hơn.
- **Kịch bản 1 (Thành công):**
  - `Given` hệ thống giới hạn file tối đa 5MB, chấp nhận định dạng `.png`, `.jpg`, `.pdf`, `.docx`.
  - `When` khách hàng tải lên file `loi.png` dung lượng 2MB.
  - `Then` file được lưu thành công, hiển thị trong danh sách đính kèm của ticket và có thể tải về.
- **Kịch bản 2 (Thất bại do sai định dạng hoặc quá dung lượng):**
  - `Given` khách hàng đang ở trang chi tiết ticket.
  - `When` khách hàng tải lên file `setup.exe`, hoặc file `video.mp4` dung lượng 10MB.
  - `Then` hệ thống hiển thị lỗi `"Định dạng không hợp lệ"` hoặc `"File vượt quá 5MB"` và không lưu file.

### US-12: Gửi email thông báo chạy nền
- **Story:** Là khách hàng, tôi muốn nhận email khi ticket của tôi thay đổi trạng thái hoặc có bình luận mới để nắm được tiến độ mà không cần đăng nhập.
- **Kịch bản 1 (Thành công):**
  - `Given` ticket `TK-0001` của `khachhang01` đang ở trạng thái `IN_PROGRESS`.
  - `When` `agent01` chuyển ticket sang `RESOLVED`.
  - `Then` hệ thống đưa tác vụ gửi email vào hàng đợi Celery, phản hồi thao tác ngay lập tức, và `khachhang01` nhận được email trong vòng 1 phút.
- **Kịch bản 2 (Máy chủ mail bị lỗi):**
  - `Given` máy chủ SMTP tạm thời không phản hồi.
  - `When` tác vụ gửi email được thực thi.
  - `Then` Celery tự thử lại tối đa 3–5 lần, lỗi được ghi nhận trên Sentry, còn thao tác đổi trạng thái của người dùng vẫn thành công.

### US-13: Dashboard thống kê và SLA
- **Story:** Là quản lý hỗ trợ, tôi muốn xem dashboard thống kê ticket theo trạng thái, theo người xử lý và thời gian xử lý (SLA) để đánh giá hiệu suất bộ phận.
- **Kịch bản 1 (Thành công):**
  - `Given` hệ thống có 10 ticket, gồm 4 `OPEN` và 6 `RESOLVED`.
  - `When` quản lý mở trang Dashboard.
  - `Then` biểu đồ trạng thái hiển thị đúng 4 `OPEN` / 6 `RESOLVED`, kèm số ticket theo từng người xử lý và thời gian xử lý trung bình.
- **Kịch bản 2 (Cảnh báo quá SLA):**
  - `Given` SLA quy định ticket phải được giải quyết trong 24 giờ, và ticket `TK-0003` đã tạo 30 giờ nhưng chưa `RESOLVED`.
  - `When` quản lý mở Dashboard.
  - `Then` ticket `TK-0003` xuất hiện trong danh sách `"Quá SLA"` và được đánh dấu màu đỏ.

### US-14: Tài liệu API Swagger
- **Story:** Là lập trình viên tích hợp, tôi muốn xem tài liệu API dạng Swagger để hiểu và thử nghiệm các endpoint mà không cần đọc mã nguồn.
- **Kịch bản 1 (Thành công):**
  - `Given` hệ thống đang chạy.
  - `When` lập trình viên truy cập `/api/docs/`.
  - `Then` trang Swagger hiển thị đầy đủ các endpoint, tham số và schema; lập trình viên có thể bấm `"Authorize"`, nhập JWT và gọi thử API.
- **Kịch bản 2 (Gọi thử khi chưa xác thực):**
  - `Given` lập trình viên chưa nhập JWT trên Swagger.
  - `When` bấm `"Try it out"` cho `GET /api/v1/tickets/`.
  - `Then` API trả `401` và Swagger hiển thị rõ mã lỗi cùng thông báo.

### US-15: Xuất báo cáo Excel chạy nền
- **Story:** Là quản lý hỗ trợ, tôi muốn xuất báo cáo ticket theo khoảng thời gian ra file Excel để gửi cho ban lãnh đạo.
- **Kịch bản 1 (Thành công):**
  - `Given` quản lý chọn khoảng thời gian từ `01/10` đến `31/10`.
  - `When` quản lý bấm `"Xuất Excel"`.
  - `Then` hệ thống tạo tác vụ Celery, hiển thị ngay `"Báo cáo đang được tạo"`; khi hoàn tất, quản lý nhận được liên kết tải file `.xlsx`.
- **Kịch bản 2 (Không có dữ liệu):**
  - `Given` không có ticket nào trong khoảng thời gian đã chọn.
  - `When` quản lý bấm `"Xuất Excel"`.
  - `Then` hệ thống thông báo `"Không có dữ liệu trong khoảng thời gian này"` và không tạo file.

### US-16: Cập nhật ticket không cần tải lại trang — HTMX
- **Story:** Là nhân viên hỗ trợ, tôi muốn đổi trạng thái hoặc thêm bình luận mà không phải tải lại toàn bộ trang để thao tác nhanh hơn.
- **Kịch bản 1 (Thành công):**
  - `Given` `agent01` đang ở trang chi tiết ticket `TK-0001`.
  - `When` `agent01` gửi một bình luận mới.
  - `Then` chỉ khu vực bình luận được cập nhật qua HTMX, trang không tải lại và ô nhập liệu được xóa trống.
- **Kịch bản 2 (Lỗi khi gửi):**
  - `Given` kết nối tới máy chủ bị gián đoạn.
  - `When` `agent01` gửi bình luận.
  - `Then` hệ thống hiển thị thông báo lỗi ngay tại khu vực bình luận, giữ nguyên nội dung đã nhập để người dùng gửi lại.
