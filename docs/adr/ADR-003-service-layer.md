# ADR-003: Đặt logic nghiệp vụ trong tầng service

- **Ngày:** 21/10/2026
- **Trạng thái:** Đã chấp nhận

## Bối cảnh
Cùng một nghiệp vụ (ví dụ gán ticket) được gọi từ giao diện web, REST API và test; nếu viết trong view sẽ bị lặp code và khó kiểm thử.

## Quyết định
Mỗi app có `services.py` chứa các hàm nghiệp vụ; view và serializer không ghi trực tiếp vào model mà gọi service.

## Hệ quả
- **(+)** View mỏng, dễ viết unit test cho service, quy tắc chuyển trạng thái nằm một chỗ.
- **(−)** Thêm một tầng mã nguồn, cần thống nhất quy ước đặt tên hàm.
