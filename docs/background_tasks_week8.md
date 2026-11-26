# Tuần 8 — Tác vụ nền và tích hợp

Mục tiêu: đưa các việc chạy lâu hoặc phụ thuộc hệ thống ngoài (gửi email, xuất Excel, nhắc việc định kỳ) ra khỏi request web, để người dùng không phải chờ và một dịch vụ ngoài bị lỗi không làm hỏng thao tác chính.

| User story | Tính năng tuần 8 |
|---|---|
| US-12 Thông báo email | Email khi ticket đổi trạng thái / có bình luận mới, gửi nền qua Celery |
| US-13 Dashboard, SLA | Nhắc ticket quá hạn SLA 24 giờ hằng ngày (Celery Beat); cache thống kê |
| US-15 Xuất Excel | Xuất báo cáo ticket ra `.xlsx` chạy nền, tải về khi xong |

## 1. Kiến trúc

```
 Trình duyệt / API client
          │  HTTP
          ▼
 ┌──────────────────┐  transaction.on_commit → task.delay()   ┌──────────────┐
 │  Django (web)    │ ──────────────────────────────────────▶ │ Redis DB 0   │ broker + kết quả task
 │  services.py     │                                         └──────┬───────┘
 │  api/views.py    │ ◀── cache thống kê, chủ sở hữu export ──┐      │ lấy task
 └──────────────────┘                                         │      ▼
          │                                         ┌─────────┴────┐ ┌──────────────────┐
          ▼                                         │ Redis DB 1   │ │ Celery worker    │── SMTP ──▶ Mailpit :1025
 ┌──────────────────┐                               │ (cache)      │ │ tasks.py         │           (xem ở :8025)
 │ PostgreSQL 16    │ ◀─────────────────────────────┴──────────────┴─│ reports.py       │── MEDIA_ROOT/reports/*.xlsx
 └──────────────────┘                                                └──────────────────┘
                                                                              ▲
                                                     Celery Beat ── 8:00 ─────┘ remind_overdue_tickets
```

- **Web** chỉ ghi DB và đẩy một thông điệp nhỏ (id của ticket/bình luận) vào hàng đợi; task tự đọc lại dữ liệu mới nhất từ DB.
- Task được đẩy bằng `transaction.on_commit`: nếu transaction rollback thì không có email nào được gửi, và worker không bao giờ đọc thấy dữ liệu chưa commit.
- Cấu hình: `config/celery.py`, khối `CELERY_*`, `CACHES`, `LOGGING` trong `config/settings/base.py`; test dùng `CELERY_TASK_ALWAYS_EAGER`, `LocMemCache`, email `locmem` (`config/settings/test.py`).

## 2. Cách chạy ở máy dev

```bash
docker compose up -d --wait                   # db (Postgres 16), redis (7), mailpit
cp .env.example .env                          # REDIS_URL, CACHE_URL, EMAIL_HOST=localhost, EMAIL_PORT=1025
uv run python manage.py migrate
uv run python manage.py runserver

# Terminal 2 — worker (Windows bắt buộc --pool=solo)
uv run celery -A config worker -l info --pool=solo

# Terminal 3 — lịch định kỳ
uv run celery -A config beat -l info
```

- Hộp thư Mailpit: <http://localhost:8025>.
- Trên Windows, nếu log tiếng Việt hiện thành `Đ...` thì đặt `PYTHONIOENCODING=utf-8` trước khi chạy worker/runserver.
- Chạy thử một task bằng tay: `uv run python manage.py shell -c "from apps.tickets.tasks import remind_overdue_tickets; remind_overdue_tickets.delay()"`.

## 3. Danh sách tác vụ

| Task (`apps/tickets/tasks.py`) | Gọi từ | Tham số | Thử lại | Chống chạy trùng |
|---|---|---|---|---|
| `notify_status_changed` | `services.assign_ticket`, `services.change_ticket_status` | `ticket_id`, `old_status`, `new_status`, `actor_id` | `SMTPException`, `OSError`; tối đa 5 lần; chờ 30 s tăng dần tới 600 s, có jitter | Gửi 1 mail cho mỗi lần đổi trạng thái |
| `notify_new_comment` | `services.add_comment` | `comment_id` | như trên | Ghi chú nội bộ không đẩy task |
| `remind_overdue_tickets` | Celery Beat, 8:00 hằng ngày | `hours=24` | như trên | Khoá theo ngày `tickets:sla-reminder:<YYYY-MM-DD>` (`cache.add`, giữ 2 ngày) |
| `export_tickets_report` | `POST /api/v1/reports/export/` | `user_id`, `date_from`, `date_to` | Không (lỗi trả `failure` cho người dùng) | Mỗi yêu cầu một `task_id`, tên file chứa 8 ký tự đầu của id |

Nguyên tắc chung (theo giáo trình): task **nhận id, không nhận object**; giới hạn thời gian `CELERY_TASK_TIME_LIMIT=300 s` (soft 240 s); `acks_late` + `prefetch_multiplier=1` để worker chết giữa chừng thì task được giao lại; task email `ignore_result=True` để không ghi kết quả thừa vào Redis.

## 4. Email thông báo (US-12)

| Sự kiện | Người nhận | Không gửi khi |
|---|---|---|
| Ticket đổi trạng thái (gán → Đang xử lý, Đã xử lý, Đã đóng…) | Người tạo ticket | Chính người tạo thao tác; người tạo không có email; ticket không còn |
| Bình luận công khai mới | Khách bình luận → người xử lý; nhân viên bình luận → khách | Ghi chú nội bộ; ticket chưa gán người xử lý; người nhận không có email |

Mỗi lần bỏ qua đều có log `msg="Bỏ qua gửi email" event=<task> reason=<lý do>` để tra được vì sao một người không nhận mail.

## 5. Nhắc ticket quá hạn SLA (US-13)

- **Định nghĩa quá hạn SLA** (dùng chung ở một chỗ, `selectors.sla_cutoff` / `sla_overdue_tickets`): ticket **Mới hoặc Đang xử lý** tạo **quá 24 giờ**, đúng kịch bản 2 của US-13 (“quá 24 giờ chưa RESOLVED”).
- Ô “Quá SLA 24 giờ” ở `/manage/stats/`, trường `summary.overdue` của `GET /api/v1/dashboard/summary/`, danh sách `GET /api/v1/dashboard/sla-overdue/` và email nhắc đều cho **cùng một con số**. (Trước tuần 8, ô trên trang thống kê đếm ticket Mới quá 3 ngày — đã bỏ để khớp tài liệu yêu cầu.)
- Email gửi 1 lần/ngày cho mọi Manager đang hoạt động có email, liệt kê tối đa 50 ticket cũ nhất (mã, trạng thái, tuổi theo giờ, người xử lý) và dòng “... và N ticket khác”.

## 6. Xuất báo cáo Excel (US-15)

| Endpoint (chỉ Manager) | Kết quả |
|---|---|
| `POST /api/v1/reports/export/` body `{"date_from": "2026-11-01", "date_to": "2026-11-26"}` | `202` + `task_id`, `status: "pending"` |
| `GET /api/v1/reports/export/{task_id}/` | `status`: `pending` / `running` / `success` / `failure`; khi `success` có `rows` và `download_url` |
| `GET /api/v1/reports/export/{task_id}/download/` | Tệp `.xlsx` (`Content-Disposition: attachment`) |

- Lỗi: thiếu/sai ngày, `date_from > date_to`, khoảng quá 366 ngày → `400`; khoảng không có ticket → `400 {"code": "no_data", "detail": "Không có dữ liệu trong khoảng thời gian đã chọn."}`; hàng đợi hoặc Redis lỗi → `503 queue_unavailable`; Agent/Khách → `403`; Manager khác hoặc `task_id` lạ → `404`.
- Tệp gồm 9 cột: Mã, Tiêu đề, Danh mục, Độ ưu tiên, Trạng thái, Người tạo, Người xử lý, Ngày tạo, Ngày giải quyết. Ghi bằng `openpyxl` chế độ `write_only` + `iterator(chunk_size=2000)` nên không nạp hết ticket vào RAM.
- Tệp nằm trong `MEDIA_ROOT/reports/`, chỉ tải được qua endpoint có kiểm tra quyền (không public qua `/media/`). Chủ sở hữu của `task_id` lưu trong cache `reports:export:<id>` cùng thời hạn kết quả task (1 giờ).
- Chạy thật trên DB dev: `POST` trả `202` trong 0,29 s; worker xuất **10.004 dòng trong 4,5 s**, tệp ~500 KB.
- Swagger (`/api/docs/`) và bộ Postman (`docs/api_collection/`, nhóm “6. Báo cáo Excel chạy nền (Manager)”) đã có 3 request này.

## 7. Cache thống kê

- `selectors.dashboard_stats()` = `cache.get_or_set("tickets:dashboard-stats", compute_dashboard_stats, 300)`, dùng chung cho `/manage/stats/` và `GET /api/v1/dashboard/summary/`. Cache là Redis DB 1 (`CACHE_URL`).
- **Xoá cache khi dữ liệu đổi:** `apps/tickets/signals.py` bắt `post_save`/`post_delete` của Ticket, Category, User và gọi `invalidate_stats()` qua `on_commit` (bỏ qua lần lưu chỉ `last_login` khi đăng nhập). Lệnh `seed_tickets` dùng `bulk_create` (không phát signal) nên gọi `invalidate_stats()` trực tiếp.
- **Redis chết:** đọc/xoá cache lỗi → tính thẳng từ DB, ghi log `event=cache_down` và bỏ qua cache trong 30 s để các request sau không phải chờ timeout (timeout kết nối 0,5 s, đọc 1 s).

Số đo (Django test Client, user `admin`, DB 10.004 ticket, lấy min của 5 lần; đo lại sau commit #7 cho kết quả như nhau):

| Trang | Không cache | Có cache | Ghi chú |
|---|---|---|---|
| `/manage/stats/` | 56 ms / 7 query | **25 ms / 2 query** | 2 query còn lại: session + user |
| `/api/v1/dashboard/summary/` | 52–55 ms / 7 query | **20–21 ms / 2 query** | |
| Redis tắt (trước khi xử lý) | ~4.000 ms mỗi request | — | Chờ timeout kết nối |
| Redis tắt (sau khi xử lý) | ~1.500 ms request đầu, ~50 ms các request sau | — | Như không có cache |

## 8. Logging có cấu trúc

- `config/logging.py`: `KeyValueFormatter` (mặc định) và `JsonFormatter`; chọn bằng biến môi trường `LOG_FORMAT=keyvalue|json`, mức log của `apps` bằng `LOG_LEVEL`.
- Web, worker và beat dùng chung định dạng (`CELERY_WORKER_HIJACK_ROOT_LOGGER=False`).
- Ví dụ thật từ worker:

```
time=2026-11-26T03:57:46.525+00:00 level=INFO logger=apps.tickets.tasks msg="Đã gửi email" event=remind_overdue_tickets sent=1 overdue=5095 recipients=2
time=2026-11-26T03:57:46.572+00:00 level=INFO logger=apps.tickets.tasks msg="Bỏ qua gửi email" event=notify_status_changed reason=ticket_not_found ticket_id=00000000-...
level=WARNING logger=apps.tickets.tasks msg="Tác vụ thất bại, sẽ thử lại" task=apps.tickets.tasks.notify_status_changed task_id=... retries=2 error=SMTPException
level=ERROR logger=apps.tickets.services msg="Không đưa được tác vụ vào hàng đợi" event=enqueue_failed task=apps.tickets.tasks.notify_status_changed
```

- **Không log dữ liệu nhạy cảm:** chỉ ghi id, số lượng, tên lỗi; không ghi địa chỉ email, nội dung bình luận, mật khẩu hay token.

## 9. Xử lý sự cố

| Tình huống | Hành vi | Đã kiểm chứng |
|---|---|---|
| SMTP (Mailpit) chết | Thao tác của người dùng vẫn thành công; task log WARNING và thử lại sau 26–30 s, tăng dần, tối đa 5 lần; hết lượt → log ERROR | Chạy thật: tắt Mailpit → `retry in 26s`, bật lại → mail tới. Test: `test_smtp_error_schedules_retry`, `test_smtp_down_does_not_break_status_change` |
| Redis (broker) chết | Request vẫn thành công, không email; log `enqueue_failed`. Thời gian chờ broker giới hạn ~2 s (`CELERY_BROKER_CONNECTION_TIMEOUT`, `socket_connect_timeout`, `TASK_PUBLISH_RETRY_POLICY`) — trước khi giới hạn request treo **109 s**, sau còn **4,2 s**. Xuất Excel trả `503` | Chạy thật + `test_broker_down_is_logged_and_request_still_succeeds`, `test_export_returns_503_*` |
| Task nhắc SLA chạy 2 lần trong ngày (beat khởi động lại, gọi tay) | Lần 2 không gửi (`reason=already_sent_today`) | Chạy thật: lần 2 trả 0. Test: `test_sla_reminder_sent_once_per_day_to_managers_with_email` |
| Gửi mail nhắc lỗi giữa chừng | Xoá khoá ngày rồi raise để retry → lần sau vẫn gửi được, không mất nhắc nhở | `test_sla_reminder_smtp_error_releases_daily_key_for_retry` |
| Transaction rollback | Không đẩy task, không email | `test_no_email_when_transaction_rolls_back` |
| Worker chết khi đang chạy task | `acks_late` → Redis giao lại task cho worker khác | Cấu hình |

Lưu ý idempotent: email đổi trạng thái/bình luận có thể bị gửi lặp nếu worker chết **sau** khi gửi nhưng **trước** khi xác nhận task (đánh đổi của `acks_late`); chấp nhận được với email thông báo. Tác vụ cần chính xác tuyệt đối (nhắc SLA) có khoá theo ngày.

## 10. Kiểm thử

| File | Số test | Nội dung |
|---|---|---|
| `test_tasks.py` | 26 | Email đúng người nhận sau commit, lý do bỏ qua, cấu hình retry, signal retry/failure, SMTP/broker chết, nhắc SLA 1 lần/ngày, lịch Beat |
| `test_reports.py` | 19 | Nội dung tệp Excel, luồng 202 → success → tải tệp, 400/401/403/404/503, map trạng thái Celery, OpenAPI |
| `test_cache_stats.py` | 11 | Đọc từ cache, xoá cache khi dữ liệu đổi / chưa commit thì chưa xoá, Redis chết, số quá hạn khớp giữa dashboard và SLA |
| `test_logging.py` | 4 | Định dạng key=value và JSON, cấu hình `LOGGING` |
| **Tổng dự án** | **209** | 149 (tuần 1–7) + 60 (tuần 8) |

- Công cụ: `mail.outbox` (email `locmem`), fixture `django_capture_on_commit_callbacks`, `unittest.mock` giả lập SMTP/Redis lỗi, `CELERY_TASK_ALWAYS_EAGER`.
- Coverage: **75% → 86%** (`tasks.py`, `reports.py`, `services.py`, `api/views.py`, `signals.py` 100%). `pyproject.toml` có `fail_under = 70`: coverage dưới 70% thì lệnh test báo lỗi.
- Để chắc test bắt được lỗi thật, đã thử phá code ở 6 chỗ (quá hạn chỉ đếm ticket Mới, bỏ khoá ngày, không nhả khoá khi SMTP lỗi, không xoá cache, gửi task trước commit, bỏ kiểm tra chủ sở hữu tệp xuất) — lần nào cũng có test đỏ.

```bash
uv run pytest --cov=apps --cov-report=term-missing
```

## 11. Ngoài phạm vi tuần 8

- **Sentry** (nhắc trong tiêu chí US-12): để tuần triển khai; hiện lỗi task được ghi log ERROR có `task`, `task_id`, `error`.
- **Upload đính kèm có kiểm tra định dạng/dung lượng** (lịch T5 của giáo trình): đã làm từ tuần 6 (`AttachmentSerializer`: png/jpg/jpeg/pdf/docx, ≤ 5 MB), test trong `test_api.py`.
- **Gửi email thật qua Gmail SMTP**: commit #9 tuần 8.
