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

## Chạy với PostgreSQL (Tuần 5)
```bash
docker compose up -d --wait          # chạy PostgreSQL 16 trong container
cp .env.example .env                 # DATABASE_URL trỏ tới postgres://ticketdesk:...@localhost:5432/ticketdesk
uv sync
uv run python manage.py migrate
uv run python manage.py seed_demo
uv run python manage.py runserver
```
Vào psql: `docker exec -it ticketdesk-db psql -U ticketdesk`

## Tác vụ nền: Celery, Redis, Mailpit (Tuần 8)
```bash
docker compose up -d --wait                         # db, redis, mailpit
uv run python manage.py runserver
uv run celery -A config worker -l info --pool=solo  # terminal 2 (Windows cần --pool=solo)
uv run celery -A config beat -l info                # terminal 3: nhắc SLA 8:00 hằng ngày
```
- Email thông báo xem ở Mailpit: http://localhost:8025
- Xuất Excel: `POST /api/v1/reports/export/` → `GET /api/v1/reports/export/{task_id}/` → `.../download/`
- Log: `LOG_FORMAT=keyvalue|json`, `LOG_LEVEL=INFO`; trên Windows đặt `PYTHONIOENCODING=utf-8` để log tiếng Việt hiển thị đúng
- Chi tiết: [docs/background_tasks_week8.md](docs/background_tasks_week8.md)