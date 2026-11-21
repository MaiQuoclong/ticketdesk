# Tuần 7 — Chiến lược kiểm thử và báo cáo coverage

## 1. Công cụ

| Công cụ | Vai trò |
|---|---|
| `pytest` + `pytest-django` | Chạy test, fixture `client`, `settings`, `django_db`, `django_assert_max_num_queries` |
| `pytest-cov` | Đo coverage (có branch), cấu hình ở `[tool.coverage.*]` trong `pyproject.toml` |
| `factory-boy` + `faker` (`vi_VN`) | Sinh dữ liệu hợp lệ thay cho dữ liệu cứng (`apps/tickets/tests/factories.py`) |
| `rest_framework.test.APIClient` | Gọi API, `force_authenticate` hoặc header `Bearer` thật |
| `ruff` | Lint + format |
| `mypy` + `django-stubs` + `djangorestframework-stubs` | Kiểm tra kiểu cho code nghiệp vụ |
| `pre-commit` | Chạy `ruff`, `ruff-format`, `mypy` trước mỗi commit |

Cấu hình test (`config/settings/test.py`): `MD5PasswordHasher` để tạo user nhanh, email backend `locmem`.
`addopts = "-q --reuse-db"` giữ lại DB test giữa các lần chạy; thêm `--create-db` khi đổi migration.

## 2. Kim tự tháp test của TicketDesk

```
                ┌───────────────┐
                │  E2E (chưa)   │   Tuần 9–10: Playwright trên giao diện HTMX
            ┌───┴───────────────┴───┐
            │  Integration / API    │   test_api.py, test_week6_api.py, view HTML ở test_week4/5
        ┌───┴───────────────────────┴───┐
        │  Unit: model, service, factory │   test_models.py, test_services.py, test_factories.py
        └────────────────────────────────┘
```

| Tầng | File | Số test | Kiểm tra gì |
|---|---|---|---|
| Unit | `test_factories.py` | 5 | Factory tạo dữ liệu hợp lệ, `django_get_or_create`, quan hệ |
| Unit | `test_models.py` | 15 | Giá trị mặc định, `CheckConstraint`, `unique`, `PROTECT`/`SET_NULL`/`CASCADE`, ordering, `__str__` |
| Unit | `test_services.py` | 14 | `assign_ticket`, `change_ticket_status`, `add_comment` và các lỗi `TicketClosedError`/`TicketServiceError` |
| Integration | `test_api.py` | 84 | Mọi endpoint REST theo tiêu chí nghiệm thu US-01 … US-14 |
| Integration | `test_week4.py` | 5 | View HTML: IDOR 404, ẩn ghi chú nội bộ |
| Integration | `test_week5.py` | 12 | Số query không tăng theo số dòng, selector thống kê, data migration, nhóm Quản lý, admin, race condition (Postgres) |
| Integration | `test_week6_api.py` | 10 | Kịch bản API dài (luồng đầy đủ) của tuần 6 |
| — | `tests/test_sales.py` | 4 | Bài tập tuần 1 |
| | **Tổng** | **149** | |

Mọi test viết theo mẫu **AAA** (Arrange – Act – Assert), mỗi test một hành vi, tên test mô tả hành vi
(`test_customer_accessing_others_ticket_returns_404`). Dữ liệu tạo bằng factory, test chỉ ghi trường
quan trọng với kịch bản.

## 3. Map test ↔ tiêu chí nghiệm thu (docs/requirements_v1.md)

| User story | Kịch bản | Test tiêu biểu (`test_api.py` nếu không ghi khác) |
|---|---|---|
| US-01 Đăng nhập | Thành công / sai mật khẩu | `test_login_with_valid_credentials_returns_tokens_and_role`, `test_login_with_wrong_password_or_unknown_user_returns_401`, `test_login_of_inactive_user_returns_401` |
| US-02 Danh mục | Tạo / xoá khi còn ticket | `test_manager_creates_category`, `test_non_manager_cannot_create_category`, `test_delete_category_in_use_returns_409` |
| US-03 Tạo ticket | Thành công / thiếu tiêu đề | `test_customer_creates_ticket_with_new_status`, `test_create_ticket_with_empty_or_short_title_returns_400`; model: `test_ticket_with_empty_title_violates_check_constraint` |
| US-04 Chỉ xem ticket của mình | Danh sách / IDOR | `test_customer_only_sees_own_tickets`, `test_customer_accessing_others_ticket_returns_404`; HTML: `test_week4::test_customer_cannot_view_other_customer_ticket` |
| US-05 Gán người xử lý | Thành công / sai quyền | `test_manager_assigns_ticket_to_agent`, `test_agent_cannot_assign_ticket`; service: `test_assign_ticket_records_assignee_and_status_history` |
| US-06 Đổi trạng thái | Resolved / từ Closed | `test_agent_resolves_ticket_and_sets_resolved_at`, `test_resolve_closed_ticket_returns_409`; service: `test_closed_ticket_cannot_change_status` |
| US-07 Bình luận | Thứ tự / ẩn nội bộ | `test_comments_are_listed_in_time_order_with_author`, `test_customer_does_not_see_internal_note`; service: `test_customer_cannot_create_internal_note` |
| US-08 Lịch sử | 3 bản ghi / không sửa được | `test_history_lists_all_changes_with_actor_and_values`, `test_history_cannot_be_modified` (405) |
| US-09 Lọc, phân trang | Trang 2 / tham số sai | `test_filter_by_status_paginates_with_count_and_links`, `test_filter_by_invalid_status_returns_400`, `test_page_out_of_range_returns_404` |
| US-10 JWT | Bearer / thiếu, hết hạn token | `test_bearer_token_gives_access_to_ticket_list`, `test_ticket_list_without_token_returns_401`, `test_expired_access_token_returns_401`, `test_refresh_with_revoked_token_returns_401` |
| US-11 Đính kèm | Hợp lệ / sai định dạng, quá 5MB | `test_upload_valid_attachment_returns_201`, `test_upload_exe_returns_400`, `test_upload_file_over_5mb_returns_400` |
| US-12 Email chạy nền | — | Chưa có (Tuần 8: Celery) |
| US-13 Dashboard, SLA | Đếm trạng thái / quá 24h | `test_dashboard_summary_counts_by_status`, `test_sla_overdue_lists_only_open_tickets_older_than_24h` |
| US-14 Swagger | Mở docs / gọi khi chưa xác thực | `test_swagger_docs_are_public_and_api_requires_auth` |
| US-15 Xuất Excel | — | Chưa có (Tuần 8) |

Khác biệt giữa văn bản tiêu chí và code (test theo code thật): gán ticket chuyển sang `in_progress`
(model không có `ASSIGNED`); test kiểm mã HTTP và `code` lỗi, không so khớp câu thông báo.

## 4. Coverage trước / sau

Lệnh đo (PostgreSQL 16 qua Docker Compose):

```bash
docker compose up -d --wait
uv run pytest --cov=apps --cov-report=term-missing
```

**Trước:** chỉ bộ test tuần 1–6 (31 test). **Sau:** toàn bộ 149 test tuần 7.

| Module | Trước | Sau |
|---|---|---|
| `apps/tickets/services.py` | 92% | **100%** |
| `apps/tickets/api/views.py` | 96% | **100%** |
| `apps/tickets/models.py` | 95% | **100%** |
| `apps/accounts/models.py` | 90% | **100%** |
| `apps/tickets/selectors.py` | 96% | 96% |
| `apps/accounts/api/serializers.py` | 92% | **98%** |
| `apps/tickets/api/serializers.py` | 90% | 92% |
| `apps/tickets/api/permissions.py` | 88% | 88% |
| `apps/tickets/views.py` (HTML, HTMX) | 44% | 44% |
| **Tổng `apps`** | **80%** | **82%** |

Phần nghiệp vụ (models, services, selectors, API) đạt 88–100%, vượt yêu cầu ≥ 70%.
Phần còn thấp là `apps/tickets/views.py` (các view HTML/HTMX dùng cho giao diện) — sẽ bổ sung khi
làm frontend Tuần 9. Coverage cao không có nghĩa là test tốt: test phải kiểm kết quả có ý nghĩa
(trạng thái DB, mã lỗi, dữ liệu không bị lộ), không chỉ "chạy qua" dòng code.

## 5. Chất lượng code

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy apps config
uv run pre-commit run --all-files
```

- `mypy`: 0 lỗi trên 50 file. Thư mục test được bỏ qua (`ignore_errors`) vì stub của factory_boy
  không suy ra được kiểu model trả về.
- Lỗi phát hiện nhờ bộ test tuần 7: nhóm "Quản lý" chỉ được tạo trong data migration nên mất sau khi
  `TransactionTestCase` flush DB (test race) → chạy lại với `--reuse-db` thì 2 test lỗi. Sửa bằng
  receiver `post_migrate` (`apps/accounts/signals.py::ensure_manager_group`) tạo lại nhóm sau mỗi
  `migrate`/`flush`.
