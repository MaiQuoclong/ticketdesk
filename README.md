# TicketDesk — Hệ thống tiếp nhận và xử lý yêu cầu hỗ trợ nội bộ

Dự án Capstone chương trình thực tập Full-stack Python/Django tại **Công ty TNHH Rainscales Việt Nam**.

- **Sinh viên thực hiện:** Mai Quốc Long (`22115053122227`)
- **Công nghệ:** Python 3.12+, Django, Django REST Framework, PostgreSQL 16, Redis 7, Celery, HTMX, Docker, GitHub Actions.

## Cài đặt môi trường phát triển (Tuần 1)

```bash
# Cài đặt dependencies bằng uv
uv sync

# Chạy kiểm tra chất lượng code (Ruff)
uv run ruff check .
uv run ruff format --check .

# Chạy bộ kiểm thử tự động (Pytest)
uv run pytest
```
