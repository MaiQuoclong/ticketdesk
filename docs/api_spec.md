# Đặc tả REST API — Hệ thống TicketDesk (Tuần 3)

## 1. Bảng đặc tả 28 Endpoints

### 1.1 Nhóm Xác thực & Người dùng (`Accounts`)
| Method | Endpoint | Mô tả chức năng | Status Code |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/auth/login/` | Đăng nhập bằng username/password, tạo cặp Access Token và lưu bản ghi vào `Refreshtoken` | `200`, `400`, `401` |
| `POST` | `/api/v1/auth/refresh/` | Gửi refresh token để cấp Access Token mới (kiểm tra `expires_at` và `is_revoked`) | `200`, `401` |
| `POST` | `/api/v1/auth/logout/` | Đăng xuất, cập nhật `is_revoked = True` cho token tương ứng | `204`, `401` |
| `GET` | `/api/v1/accounts/me/` | Lấy thông tin cá nhân của tài khoản đang đăng nhập | `200`, `401` |
| `GET` | `/api/v1/accounts/agents/` | Lấy danh sách nhân viên kỹ thuật phục vụ thao tác gán vé | `200`, `401`, `403` |

### 1.2 Nhóm Danh mục sự cố (`Category`)
| Method | Endpoint | Mô tả chức năng | Status Code |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/categories/` | Lấy danh sách tất cả các danh mục sự cố | `200`, `401` |
| `POST` | `/api/v1/categories/` | Tạo danh mục sự cố mới | `201`, `400`, `403` |
| `PUT` / `PATCH` | `/api/v1/categories/{id}/` | Sửa thông tin danh mục | `200`, `400`, `403`, `404` |
| `DELETE` | `/api/v1/categories/{id}/` | Xóa danh mục (chỉ xóa khi không có ticket nào ràng buộc) | `204`, `403`, `404`, `409` |

### 1.3 Nhóm Quản lý Yêu cầu (`Ticket`)
| Method | Endpoint | Mô tả chức năng | Status Code |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/tickets/` | Lọc và phân trang danh sách ticket (`Customer` chỉ xem ticket do mình tạo; `Agent` xem ticket được gán; `Manager` xem toàn bộ) | `200`, `400`, `401` |
| `POST` | `/api/v1/tickets/` | Tạo yêu cầu hỗ trợ mới | `201`, `400`, `401` |
| `GET` | `/api/v1/tickets/{id}/` | Xem chi tiết thông tin ticket | `200`, `403`, `404` |
| `PATCH` | `/api/v1/tickets/{id}/` | Cập nhật thông tin (tiêu đề, mô tả, mức độ ưu tiên) | `200`, `400`, `403`, `404` |
| `POST` | `/api/v1/tickets/{id}/assign/` | Gán ticket cho kỹ thuật viên xử lý (cập nhật trường `assignee_id`) | `200`, `403`, `404`, `409` |
| `POST` | `/api/v1/tickets/{id}/resolve/` | Kỹ thuật viên chuyển trạng thái ticket sang `RESOLVED` | `200`, `403`, `409` |
| `POST` | `/api/v1/tickets/{id}/close/` | Khách hàng hoặc Quản lý nghiệm thu và đóng ticket (`CLOSED`) | `200`, `403`, `409` |
| `DELETE` | `/api/v1/tickets/{id}/` | Xóa ticket khỏi hệ thống | `204`, `403`, `404` |

### 1.4 Nhóm Bình luận, Đính kèm và Lịch sử
| Method | Endpoint | Mô tả chức năng | Status Code |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/tickets/{id}/comments/` | Danh sách bình luận của ticket (`Customer` không thấy ghi chú nội bộ) | `200`, `403`, `404` |
| `POST` | `/api/v1/tickets/{id}/comments/` | Thêm bình luận; `Agent`/`Manager` có thể đánh dấu `is_internal` | `201`, `400`, `403`, `404`, `409` |
| `GET` | `/api/v1/tickets/{id}/attachments/` | Danh sách tệp đính kèm của ticket | `200`, `403`, `404` |
| `POST` | `/api/v1/tickets/{id}/attachments/` | Tải tệp lên (tối đa 5MB; `.png`, `.jpg`, `.pdf`, `.docx`) | `201`, `400`, `403`, `413` |
| `DELETE` | `/api/v1/attachments/{id}/` | Xóa tệp đính kèm (người tải lên hoặc `Manager`) | `204`, `403`, `404` |
| `GET` | `/api/v1/tickets/{id}/history/` | Xem lịch sử thay đổi của ticket (chỉ đọc) | `200`, `403`, `404` |

### 1.5 Nhóm Thống kê, Báo cáo và Tài liệu API
| Method | Endpoint | Mô tả chức năng | Status Code |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/dashboard/summary/` | Thống kê ticket theo trạng thái, theo người xử lý và thời gian xử lý trung bình (`Manager`) | `200`, `401`, `403` |
| `GET` | `/api/v1/dashboard/sla-overdue/` | Danh sách ticket quá SLA 24 giờ chưa `RESOLVED` | `200`, `401`, `403` |
| `POST` | `/api/v1/reports/export/` | Tạo tác vụ Celery xuất Excel theo khoảng thời gian, trả về `task_id` | `202`, `400`, `403` |
| `GET` | `/api/v1/reports/{task_id}/` | Kiểm tra trạng thái tác vụ và lấy liên kết tải tệp `.xlsx` | `200`, `404` |
| `GET` | `/api/docs/` | Tài liệu Swagger UI sinh tự động từ OpenAPI schema | `200` |

---

## 2. Quy ước chung của API
- **Đặt tên:** Resource là danh từ số nhiều, hành động là HTTP method; hành động nghiệp vụ không khớp CRUD (`assign`, `resolve`, `close`) dùng `POST` tới đường dẫn riêng.
- **Phân trang và lọc:** Danh sách trả về theo trang với tham số `?page=&page_size=` (mặc định 20), kèm `count`, `next`, `previous`; lọc theo `?status=`, `?priority=`, `?assignee=`.
- **Mã lỗi HTTP:**
  - `400 Bad Request`: Dữ liệu đầu vào sai
  - `401 Unauthorized`: Chưa đăng nhập hoặc token hết hạn
  - `403 Forbidden`: Không đủ quyền thực hiện thao tác
  - `404 Not Found`: Không tìm thấy tài nguyên
  - `409 Conflict`: Xung đột trạng thái nghiệp vụ (ví dụ gán hoặc bình luận vào ticket đã `CLOSED`)
  - `413 Payload Too Large`: Tệp đính kèm vượt quá 5MB
- **Định dạng lỗi thống nhất:**
```json
{
  "detail": "Ticket đã đóng",
  "code": "ticket_closed"
}
```
