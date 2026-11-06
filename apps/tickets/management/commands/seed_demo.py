from django.core.management.base import BaseCommand

from apps.accounts.models import User
from apps.tickets.models import Category, Ticket
from apps.tickets.services import add_comment, assign_ticket, change_ticket_status


class Command(BaseCommand):
    help = "Tạo dữ liệu mẫu cho dự án TicketDesk (Tuần 4)"

    def handle(self, *args, **options) -> None:
        # 1. Tạo tài khoản mẫu theo 3 vai trò
        admin_user, created = User.objects.get_or_create(
            username="admin",
            defaults={
                "email": "admin@rainscales.com",
                "role": User.Role.MANAGER,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        if created:
            admin_user.set_password("admin123")
            admin_user.save()

        users_spec = [
            ("quanly01", "quanly01@rainscales.com", User.Role.MANAGER, True),
            ("agent01", "agent01@rainscales.com", User.Role.AGENT, False),
            ("agent02", "agent02@rainscales.com", User.Role.AGENT, False),
            ("khachhang01", "khachhang01@rainscales.com", User.Role.CUSTOMER, False),
            ("khachhang02", "khachhang02@rainscales.com", User.Role.CUSTOMER, False),
        ]
        users: dict[str, User] = {}
        for username, email, role, is_staff in users_spec:
            u, is_new = User.objects.get_or_create(
                username=username,
                defaults={"email": email, "role": role, "is_staff": is_staff},
            )
            if is_new:
                u.set_password("matkhau123")
                u.save()
            users[username] = u

        # 2. Tạo danh mục sự cố
        categories_spec = [
            ("Phần cứng", "Sự cố máy tính, màn hình, máy in, thiết bị ngoại vi"),
            ("Phần mềm", "Lỗi cài đặt, bản quyền, ứng dụng văn phòng và ERP"),
            ("Mạng & Đường truyền", "Sự cố Wi-Fi, VPN, tường lửa, kết nối nội bộ"),
            ("Tài khoản & Phân quyền", "Cấp quyền truy cập, khôi phục mật khẩu, email công ty"),
        ]
        cats: dict[str, Category] = {}
        for name, desc in categories_spec:
            cat, _ = Category.objects.get_or_create(name=name, defaults={"description": desc})
            cats[name] = cat

        # 3. Tạo ticket mẫu nếu chưa có
        if Ticket.objects.exists():
            self.stdout.write(
                self.style.WARNING("Dữ liệu ticket mẫu đã tồn tại, bỏ qua bước tạo thêm.")
            )
            return

        t1 = Ticket.objects.create(
            title="Máy in tầng 3 báo lỗi kẹt giấy liên tục",
            description=(
                "Khi in tài liệu PDF từ 5 trang trở lên, máy in HP LaserJet tầng 3 "
                "báo đèn đỏ Paper Jam dù đã lấy giấy ra."
            ),
            priority=Ticket.Priority.HIGH,
            category=cats["Phần cứng"],
            created_by=users["khachhang01"],
        )
        assign_ticket(ticket=t1, agent=users["agent01"], actor=users["quanly01"])
        add_comment(
            ticket=t1,
            author=users["agent01"],
            content="Em đã lên kiểm tra, cụm sấy bị mòn rulo kéo giấy. Đang thay linh kiện mới.",
        )
        add_comment(
            ticket=t1,
            author=users["agent01"],
            content="Ghi chú nội bộ: Cần đặt thêm 2 bộ rulo dự phòng cho kho IT.",
            is_internal=True,
        )

        t2 = Ticket.objects.create(
            title="Không kết nối được VPN nội bộ khi làm việc từ xa",
            description=(
                "Ứng dụng FortiClient dừng ở 40% và báo lỗi "
                "Credential or SSLVPN configuration is wrong."
            ),
            priority=Ticket.Priority.HIGH,
            category=cats["Mạng & Đường truyền"],
            created_by=users["khachhang01"],
        )
        assign_ticket(ticket=t2, agent=users["agent02"], actor=users["quanly01"])
        change_ticket_status(
            ticket=t2, new_status=Ticket.Status.RESOLVED, actor=users["agent02"]
        )
        add_comment(
            ticket=t2,
            author=users["agent02"],
            content=(
                "Đã cấp lại chứng chỉ SSL VPN mới cho tài khoản khachhang01. "
                "Vui lòng thử kết nối lại."
            ),
        )

        Ticket.objects.create(
            title="Xin cấp quyền truy cập thư mục chia sẻ dự án Q4",
            description=(
                "Nhờ bộ phận IT cấp quyền Read/Write vào thư mục "
                "\\\\nas\\projects\\Q4-2026 cho nhóm kế toán."
            ),
            priority=Ticket.Priority.MEDIUM,
            category=cats["Tài khoản & Phân quyền"],
            created_by=users["khachhang01"],
        )

        t4 = Ticket.objects.create(
            title="Cài đặt môi trường Docker Desktop trên máy mới",
            description=(
                "Máy trạm mới nhận chưa bật sẵn WSL2 và Docker Desktop "
                "để chạy môi trường dev."
            ),
            priority=Ticket.Priority.LOW,
            category=cats["Phần mềm"],
            created_by=users["khachhang02"],
        )
        assign_ticket(ticket=t4, agent=users["agent01"], actor=users["quanly01"])
        change_ticket_status(ticket=t4, new_status=Ticket.Status.CLOSED, actor=users["quanly01"])

        self.stdout.write(
            self.style.SUCCESS(
                "Đã tạo dữ liệu mẫu thành công! "
                "Tài khoản: quanly01 / agent01 / khachhang01 (mật khẩu: matkhau123)"
            )
        )
