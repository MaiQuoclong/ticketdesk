# Hướng dẫn sử dụng Tài liệu Swagger UI & Bộ Collection Bruno / Postman (Tuần 6)

## 1. Tài liệu OpenAPI & Swagger UI trực tuyến
Khi chạy server (`uv run python manage.py runserver`), truy cập:
- **Swagger UI:** `http://127.0.0.1:8000/api/docs/`
- **OpenAPI Schema (YAML/JSON):** `http://127.0.0.1:8000/api/schema/`

### Cách xác thực JWT trên Swagger UI
1. Gọi endpoint `POST /api/v1/auth/login/` (hoặc `POST /api/token/`) với tài khoản mẫu:
   - Quản lý: `quanly01` / `matkhau123`
   - Nhân viên hỗ trợ: `agent01` / `matkhau123`
   - Khách hàng: `khachhang01` / `matkhau123`
2. Sao chép giá trị trường `access` trong JSON phản hồi.
3. Nhấn nút **Authorize** ở góc phải trên cùng của Swagger UI, dán `<access_token>` vào ô `jwtAuth (http, Bearer)` rồi nhấn **Authorize**.

---

## 2. Nhập bộ Collection vào Postman hoặc Bruno
- **Postman:** Mở Postman → **Import** → chọn tệp `docs/api_collection/ticketdesk_postman_collection.json`.
- **Bruno:** Mở Bruno → **Import Collection** → chọn Postman Collection `docs/api_collection/ticketdesk_postman_collection.json` (hoặc mở thư mục `docs/api_collection`).

---

## 3. Kiểm thử nhanh bằng `curl`
```bash
# 1. Đăng nhập lấy cặp Access & Refresh Token
curl -X POST http://127.0.0.1:8000/api/v1/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username": "khachhang01", "password": "matkhau123"}'

# 2. Lọc & tìm kiếm danh sách Ticket
curl "http://127.0.0.1:8000/api/v1/tickets/?status=new&search=VPN" \
  -H "Authorization: Bearer <access_token>"

# 3. Kiểm thử chống lỗi IDOR (dùng token của khachhang01 đọc ticket của khachhang02 -> nhận 404 Not Found)
curl http://127.0.0.1:8000/api/v1/tickets/<ticket_id_cua_khachhang02>/ \
  -H "Authorization: Bearer <access_token>"
```
