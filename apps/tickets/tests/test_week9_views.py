import pytest
from django.contrib.messages import get_messages
from django.urls import reverse

from apps.accounts.models import User
from apps.tickets.models import Category, Ticket, TicketHistory

from .factories import (
    AgentFactory,
    CategoryFactory,
    CustomerFactory,
    ManagerFactory,
    TicketFactory,
)

pytestmark = pytest.mark.django_db

HTMX = {"HTTP_HX_REQUEST": "true"}
MANAGE_PAGES = ["manage_users", "manage_categories", "manage_stats", "manage_history"]


def _messages(response) -> list[str]:
    return [str(m) for m in get_messages(response.wsgi_request)]


@pytest.fixture
def manager(client):
    user = ManagerFactory()
    client.force_login(user)
    return user


@pytest.mark.parametrize("page", MANAGE_PAGES)
@pytest.mark.parametrize("factory", [CustomerFactory, AgentFactory])
def test_trang_quan_ly_chan_non_manager(client, page, factory):
    client.force_login(factory())
    response = client.get(reverse(f"tickets:{page}"))
    assert response.status_code == 302
    assert response.url == reverse("tickets:list")
    assert any("Chỉ Quản lý" in m for m in _messages(response))


@pytest.mark.parametrize("page", MANAGE_PAGES)
def test_trang_quan_ly_mo_duoc_voi_manager(client, manager, page):
    assert client.get(reverse(f"tickets:{page}")).status_code == 200


def test_navbar_chi_hien_menu_quan_ly_cho_manager(client):
    client.force_login(CustomerFactory())
    assert reverse("tickets:manage_users") not in client.get(reverse("tickets:list")).text
    client.force_login(ManagerFactory())
    assert reverse("tickets:manage_users") in client.get(reverse("tickets:list")).text


@pytest.mark.parametrize(
    ("factory", "assign", "status"),
    [(CustomerFactory, False, False), (AgentFactory, False, True), (ManagerFactory, True, True)],
)
def test_nut_thao_tac_theo_vai_tro(client, factory, assign, status):
    user = factory()
    ticket = TicketFactory(created_by=user if factory is CustomerFactory else CustomerFactory())
    client.force_login(user)
    html = client.get(reverse("tickets:detail", args=[ticket.pk])).text
    assert (reverse("tickets:assign", args=[ticket.pk]) in html) is assign
    assert (reverse("tickets:change_status", args=[ticket.pk]) in html) is status


def test_sua_ticket_thanh_cong(client):
    customer = CustomerFactory()
    ticket = TicketFactory(created_by=customer)
    client.force_login(customer)
    response = client.post(
        reverse("tickets:edit", args=[ticket.pk]),
        {
            "title": "Tiêu đề đã sửa lại",
            "category": ticket.category_id,
            "priority": ticket.priority,
            "description": "Mô tả mới",
        },
    )
    assert response.status_code == 302
    assert response.url == reverse("tickets:detail", args=[ticket.pk])
    ticket.refresh_from_db()
    assert ticket.title == "Tiêu đề đã sửa lại"
    assert "Đã cập nhật thông tin ticket." in _messages(response)


def test_khach_khong_sua_duoc_ticket_nguoi_khac(client):
    client.force_login(CustomerFactory())
    ticket = TicketFactory(created_by=CustomerFactory())
    assert client.get(reverse("tickets:edit", args=[ticket.pk])).status_code == 404


def test_gan_ticket_da_dong_bao_loi_qua_htmx(client, manager):
    ticket = TicketFactory(status=Ticket.Status.CLOSED)
    response = client.post(
        reverse("tickets:assign", args=[ticket.pk]),
        {"agent_id": str(AgentFactory().pk)},
        **HTMX,
    )
    assert response.status_code == 200
    assert "đã đóng" in response.text
    ticket.refresh_from_db()
    assert ticket.assignee is None


def test_tao_nguoi_dung(client, manager):
    url = reverse("tickets:manage_users")
    data = {"action": "create_user", "username": "nv_moi", "password": "MatKhau@123"}
    response = client.post(url, {**data, "role": User.Role.MANAGER})
    assert response.status_code == 302
    created = User.objects.get(username="nv_moi")
    assert created.role == User.Role.MANAGER and created.is_staff
    assert created.check_password("MatKhau@123")

    response = client.post(url, {**data, "role": User.Role.AGENT})
    assert any("đã tồn tại" in m for m in _messages(response))

    client.post(url, {**data, "username": "khach_moi", "role": "hacker"})
    assert User.objects.get(username="khach_moi").role == User.Role.CUSTOMER


def test_tao_nguoi_dung_thieu_thong_tin(client, manager):
    response = client.post(
        reverse("tickets:manage_users"), {"action": "create_user", "username": "", "password": ""}
    )
    assert any("đầy đủ" in m for m in _messages(response))


def test_cap_nhat_nguoi_dung_va_khong_tu_khoa_minh(client, manager):
    url = reverse("tickets:manage_users")
    target = CustomerFactory()
    client.post(url, {"action": "update_user", "user_id": target.pk, "role": User.Role.AGENT})
    target.refresh_from_db()
    assert target.role == User.Role.AGENT
    assert target.is_active is False

    client.post(url, {"action": "update_user", "user_id": manager.pk, "role": User.Role.MANAGER})
    manager.refresh_from_db()
    assert manager.is_active is True


def test_quan_ly_danh_muc(client, manager):
    url = reverse("tickets:manage_categories")
    client.post(url, {"action": "create", "name": "Mạng nội bộ", "description": "LAN"})
    category = Category.objects.get(name="Mạng nội bộ")

    response = client.post(url, {"action": "create", "name": "mạng NỘI bộ"})
    assert any("đã tồn tại" in m for m in _messages(response))
    response = client.post(url, {"action": "create", "name": "  "})
    assert any("không được để trống" in m for m in _messages(response))

    client.post(
        url, {"action": "update", "category_id": category.pk, "name": "Mạng", "description": "x"}
    )
    category.refresh_from_db()
    assert (category.name, category.description) == ("Mạng", "x")

    client.post(url, {"action": "delete", "category_id": category.pk})
    assert not Category.objects.filter(pk=category.pk).exists()


def test_khong_xoa_danh_muc_con_ticket(client, manager):
    category = CategoryFactory()
    TicketFactory(category=category)
    response = client.post(
        reverse("tickets:manage_categories"), {"action": "delete", "category_id": category.pk}
    )
    assert Category.objects.filter(pk=category.pk).exists()
    assert any("PROTECT" in m for m in _messages(response))


def test_nhat_ky_he_thong_tim_kiem(client, manager):
    ticket = TicketFactory(title="Máy in tầng 3 hỏng")
    TicketHistory.objects.create(
        ticket=ticket, actor=manager, field="Trạng thái", old_value="Mới", new_value="Đã đóng"
    )
    other = TicketFactory(title="Không liên quan")
    TicketHistory.objects.create(
        ticket=other, actor=manager, field="Người xử lý", old_value="-", new_value="agent"
    )
    response = client.get(reverse("tickets:manage_history"), {"q": "máy in"})
    assert response.context["current_q"] == "máy in"
    assert [h.ticket_id for h in response.context["histories"]] == [ticket.pk]
