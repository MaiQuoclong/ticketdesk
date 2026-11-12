import random
import time
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.tickets.models import Category, Comment, Ticket

TITLES = [
    "Máy tính không khởi động",
    "Không kết nối được VPN",
    "Máy in báo kẹt giấy",
    "Quên mật khẩu email công ty",
    "Phần mềm kế toán báo lỗi",
    "Wi-Fi tầng 3 chập chờn",
    "Cần cấp quyền thư mục dự án",
    "Màn hình nhấp nháy",
]


class Command(BaseCommand):
    help = "Tạo dữ liệu lớn (mặc định 10.000 ticket) để đo hiệu năng truy vấn (Tuần 5)"

    def add_arguments(self, parser) -> None:
        parser.add_argument("--count", type=int, default=10_000, help="Số ticket cần tạo")
        parser.add_argument(
            "--comments", type=int, default=3, help="Số bình luận tối đa mỗi ticket"
        )
        parser.add_argument(
            "--clear", action="store_true", help="Xoá toàn bộ ticket cũ trước khi tạo"
        )

    def handle(self, *args, count: int, comments: int, clear: bool, **options) -> None:
        cats = list(Category.objects.all())
        customers = list(User.objects.filter(role=User.Role.CUSTOMER))
        agents = list(User.objects.filter(role=User.Role.AGENT))
        if not (cats and customers and agents):
            raise CommandError("Chưa có danh mục/người dùng. Chạy `manage.py seed_demo` trước.")

        start = time.perf_counter()
        now = timezone.now()
        with transaction.atomic():
            if clear:
                Ticket.objects.all().delete()

            tickets = []
            for i in range(count):
                status = random.choice(Ticket.Status.values)
                tickets.append(
                    Ticket(
                        title=f"{random.choice(TITLES)} #{i + 1}",
                        description="Mô tả mẫu sinh tự động để đo hiệu năng.",
                        category=random.choice(cats),
                        created_by=random.choice(customers),
                        assignee=None if status == Ticket.Status.NEW else random.choice(agents),
                        status=status,
                        priority=random.choice(Ticket.Priority.values),
                    )
                )
            Ticket.objects.bulk_create(tickets, batch_size=1000)

            # auto_now_add luôn ghi đè created_at, nên rải lại ngày tạo trong 90 ngày gần nhất
            for t in tickets:
                t.created_at = now - timedelta(minutes=random.randint(0, 90 * 24 * 60))
            Ticket.objects.bulk_update(tickets, ["created_at"], batch_size=1000)

            people = customers + agents
            comment_objs = [
                Comment(ticket=t, author=random.choice(people), content="Bình luận mẫu.")
                for t in tickets
                for _ in range(random.randint(0, comments))
            ]
            Comment.objects.bulk_create(comment_objs, batch_size=1000)

        elapsed = time.perf_counter() - start
        self.stdout.write(
            self.style.SUCCESS(
                f"Đã tạo {count} ticket và {len(comment_objs)} bình luận trong {elapsed:.1f}s"
            )
        )
