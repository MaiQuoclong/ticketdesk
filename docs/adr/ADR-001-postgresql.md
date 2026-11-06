# ADR-001: Dùng PostgreSQL thay vì MySQL

- **Ngày:** 21/10/2026
- **Trạng thái:** Đã chấp nhận

## Bối cảnh
Hệ thống cần tìm kiếm toàn văn tiếng Việt trên tiêu đề và mô tả ticket, cần lưu dữ liệu linh hoạt dạng JSON cho lịch sử thay đổi; chương trình thực tập dùng PostgreSQL làm chuẩn.

## Quyết định
Dùng PostgreSQL 16, chạy bằng Docker ở cả môi trường dev và production.

## Hệ quả
- **(+)** Dùng được `SearchVector`, `JSONField`, kiểu `UUID` và `TIMESTAMPTZ` có sẵn.
- **(−)** Cần làm quen với `psql` và cách sao lưu/khôi phục (`pg_dump`/`pg_restore`) của PostgreSQL.
