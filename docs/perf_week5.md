# Báo cáo tối ưu truy vấn — Tuần 5 (ORM nâng cao & PostgreSQL)

## 1. Môi trường đo

| Mục | Giá trị |
| :--- | :--- |
| CSDL | PostgreSQL 16 (Docker Compose, container `ticketdesk-db`) |
| Dữ liệu | 10.004 ticket, 15.020 bình luận (sinh bằng `manage.py seed_tickets`) |
| Cách đo | Django test `Client` + `CaptureQueriesContext`, lấy thời gian nhỏ nhất của 3 lần, `DEBUG=True` |
| Công cụ hỗ trợ | `django-debug-toolbar` (panel SQL), `QuerySet.explain(analyze=True)` |
| Tài khoản | `admin` (xem toàn bộ), `agent01`, `khachhang01` |

Thời gian là thời gian xử lý request phía server trên máy dev, chỉ dùng để so sánh tương đối.

## 2. Tổng hợp kết quả

| Vấn đề | Trước | Sau | Kỹ thuật |
| :--- | :--- | :--- | :--- |
| N+1 ở danh sách ticket (bản không `select_related`) | 61 query, 100 ms | 6 query, 31–38 ms | `select_related` |
| Thêm cột "Bình luận" ở danh sách | 26 query, 62 ms | 6 query, 35 ms | `Subquery` + `Coalesce` |
| `/manage/users/` đếm ticket theo người dùng | 3 query, 323 ms | 3 query, 19 ms | 2 `Subquery` thay cho 2 `Count` JOIN |
| Lọc ticket theo trạng thái, sắp xếp mới nhất | — | Index Scan, 0,2 ms | Index `(status, -created_at)` |
| Gán ticket đồng thời | Mất 1 lần cập nhật | Lịch sử đầy đủ, đúng thứ tự | `select_for_update` |

## 3. Chi tiết

### 3.1 N+1 khi bỏ `select_related`

Code tuần 4 đã dùng `select_related` đủ. Để minh hoạ, bản "ngây thơ" (không commit) bỏ `select_related`, mỗi dòng phải truy vấn riêng `category`, `created_by`, `assignee`.

| Trang | Query ngây thơ | Query hiện tại | Thời gian ngây thơ | Thời gian hiện tại |
| :--- | :--- | :--- | :--- | :--- |
| `/` | 61 (55 lặp) | 6 | 100 ms | 31–38 ms |
| `/?status=in_progress` | 66 (59 lặp) | 6 | 101 ms | 21–28 ms |
| `/?q=VPN` | 61 | 6 | 123 ms | 37–52 ms |
| `/<id>/` chi tiết | 12 | 6 | 21 ms | 14–15 ms |
| `/manage/history/` | 19 (15 lặp) | 3 | 26 ms | 15–16 ms |

Số query của bản hiện tại không đổi theo số dòng hiển thị. Test `test_ticket_list_query_count_does_not_grow_with_rows` giữ ngưỡng này (tối đa 8 query với 25 ticket).

### 3.2 Đếm bình luận ở danh sách (commit #5)

| Cách làm | Query | Thời gian `/` | Nhận xét |
| :--- | :--- | :--- | :--- |
| `{{ ticket.comments.count }}` trong template | 26 | 62 ms | N+1: thêm 20 query `COUNT` cho 20 dòng |
| `annotate(Count("comments"))` | 6 | 95 ms | JOIN + `GROUP BY` toàn bộ 10k dòng rồi mới `LIMIT`; mất `Meta.ordering` |
| `Subquery` + `Coalesce` (chọn) | 6 | 35 ms | Subquery chỉ chạy cho 20 dòng của trang |

EXPLAIN của cách được chọn: subquery chạy `loops=20` qua index `tickets_comment.ticket_id`, thời gian thực thi 14 ms. Khách hàng chỉ đếm bình luận không nội bộ (lọc ngay trong subquery).

```python
comment_count = comments.order_by().values("ticket").annotate(n=Count("id")).values("n")
qs.annotate(comment_count=Coalesce(Subquery(comment_count, output_field=IntegerField()), 0))
```

### 3.3 Trang quản lý người dùng (commit #6)

Trước: `annotate(created_count=Count("created_tickets"), assigned_count=Count("assigned_tickets"))`. Hai LEFT JOIN nhân dòng với nhau (17.468 dòng trung gian), phải sort khoảng 340 ms, và có thể đếm sai nếu không dùng `distinct=True`.

Sau: helper `_count_tickets_by(field)` tạo một `Subquery` đếm riêng cho từng cột.

| | Query | Thời gian | EXPLAIN |
| :--- | :--- | :--- | :--- |
| Trước | 3 | 323–334 ms | 2 LEFT JOIN → 17.468 dòng, sort ~340 ms |
| Sau | 3 | 17–19 ms | 9 ms |

Kết quả đếm của hai cách giống hệt nhau (đã so sánh từng người dùng).

### 3.4 Index và ràng buộc (commit #2)

| Index | Truy vấn hưởng lợi | EXPLAIN ANALYZE |
| :--- | :--- | :--- |
| `ticket_status_created_idx (status, -created_at)` | Danh sách lọc theo trạng thái, mới nhất trước | `Index Scan`, lấy 20 dòng, 0,23 ms, không cần Sort |
| `ticket_assignee_status_idx (assignee, status)` | Ticket của một agent theo trạng thái, thống kê khối lượng | `Bitmap Index Scan`, 1.278 dòng, 3,0 ms |

CheckConstraint ở mức CSDL: `ticket_title_not_empty` (title khác rỗng), `ticket_priority_valid` (priority ∈ {1, 2, 3}). Dữ liệu sai bị PostgreSQL từ chối kể cả khi ghi không qua form.

### 3.5 Sinh dữ liệu lớn (commit #3)

`seed_tickets --count 10000 --comments K` dùng `bulk_create` (batch 1000) và `bulk_update` để rải `created_at` trong 90 ngày. Kết quả: 10.000 ticket + 15.017 bình luận trong 6,7 giây.

### 3.6 Trang thống kê (commit #7)

`/manage/stats/` dùng `aggregate` + `Count(filter=Q(...))` để lấy toàn bộ số tổng hợp trong 1 query, cùng `values().annotate()` theo trạng thái, mức ưu tiên, danh mục và `Avg` thời gian xử lý của từng agent. Cả trang dùng 7 query, 32–35 ms trên 10k ticket.

### 3.7 Race condition khi gán / đổi trạng thái (commit #8)

Hai request gán cùng một ticket đồng thời (mô phỏng bằng 2 thread, `save` chậm 0,5 s):

| | Lịch sử "Người xử lý" | Lịch sử "Trạng thái" |
| :--- | :--- | :--- |
| Trước | `Chưa gán → agent02`, `Chưa gán → agent01` (mất 1 cập nhật) | 2 dòng `Mới → Đang xử lý` trùng |
| Sau | `Chưa gán → agent01`, `agent01 → agent02` | 1 dòng, đúng thứ tự |

`assign_ticket`, `change_ticket_status`, `add_comment` đọc lại ticket bằng `select_for_update()` trong `transaction.atomic`. Request thứ hai phải chờ request đầu commit, nên luôn thấy dữ liệu mới nhất. Test `test_concurrent_assign_keeps_full_history` tái hiện tình huống này; khi bỏ `select_for_update` test bị FAIL.

### 3.8 Data migration `resolved_at` (commit #9)

4.908 ticket ở trạng thái "Đã xử lý"/"Đã đóng" có `resolved_at = NULL`, nên thời gian xử lý trung bình hiện "—". Migration `0003_backfill_resolved_at` cập nhật bằng **một câu `UPDATE`**:

```python
resolved_at = Greatest(Coalesce(Subquery(first_done_at), F("updated_at")), F("created_at"))
```

Sau migration: 0 ticket thiếu `resolved_at`, không dòng nào có `resolved_at < created_at`, ticket đã có giá trị giữ nguyên. Migration chạy lại nhiều lần vẫn cho cùng kết quả; chiều ngược là `noop`.

## 4. Số liệu hiện tại (sau toàn bộ tuần 5)

| Trang | admin | agent01 | khachhang01 |
| :--- | :--- | :--- | :--- |
| `/` | 6 query, 38 ms | 6 query, 34 ms | 6 query, 30 ms |
| `/?status=in_progress` | 6 query, 25 ms | 6 query, 24 ms | 6 query, 25 ms |
| `/?q=VPN` | 6 query, 52 ms | 6 query, 51 ms | 6 query, 37 ms |
| `/<id>/` chi tiết | 6 query, 15 ms | 5 query, 13 ms | 404 (không phải ticket của mình) |
| `/manage/users/` | 3 query, 18 ms | 302 | 302 |
| `/manage/history/` | 3 query, 15 ms | 302 | 302 |
| `/manage/stats/` | 7 query, 32 ms | 302 | 302 |

Không trang nào còn query lặp (`dup = 0`).

## 5. Bài học

- Đo trước khi tối ưu: code tuần 4 vốn không còn N+1, chỗ chậm thật nằm ở `/manage/users/` (JOIN nhân dòng).
- `annotate(Count())` trên nhiều quan hệ dễ nhân dòng; `Subquery` đếm riêng an toàn và nhanh hơn khi chỉ cần vài cột đếm.
- Kiểm chứng index bằng `EXPLAIN ANALYZE`, không đoán.
- Ràng buộc quan trọng nên đặt ở CSDL (`CheckConstraint`, `select_for_update`), không chỉ ở form hay view.
- Viết test giữ ngưỡng số query và test tái hiện race condition để lỗi không quay lại.
