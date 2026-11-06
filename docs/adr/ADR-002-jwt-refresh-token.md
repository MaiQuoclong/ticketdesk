# ADR-002: Xác thực API bằng JWT, lưu refresh token trong CSDL

- **Ngày:** 21/10/2026
- **Trạng thái:** Đã chấp nhận

## Bối cảnh
API phục vụ cả giao diện web và ứng dụng bên ngoài; cần cơ chế không phụ thuộc session nhưng vẫn thu hồi được phiên khi người dùng đăng xuất.

## Quyết định
Dùng `djangorestframework-simplejwt`: access token sống 15 phút, refresh token sống 7 ngày và được lưu vào bảng `Refreshtoken`; đăng xuất đặt `is_revoked = True`.

## Hệ quả
- **(+)** Đăng xuất và thu hồi token có hiệu lực ngay.
- **(−)** Mỗi lần làm mới token phải truy vấn CSDL; cần tác vụ định kỳ dọn token hết hạn.
