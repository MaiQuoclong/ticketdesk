import pytest
from django.urls import reverse

from .factories import (
    AgentFactory,
    CategoryFactory,
    CustomerFactory,
    ManagerFactory,
    TicketFactory,
)

pytestmark = pytest.mark.django_db

LOGIN = reverse("accounts:login")
PASSWORD = "matkhau123"


def _login(client, user, **extra):
    return client.post(LOGIN, {"username": user.username, "password": PASSWORD, **extra})


def test_trang_dang_nhap_co_nhan_cho_o_nhap(client):
    html = client.get(LOGIN).content.decode()
    assert 'for="id_username"' in html
    assert 'for="id_password"' in html
    assert 'autocomplete="current-password"' in html


def test_manager_dang_nhap_chuyen_toi_dashboard(client):
    resp = _login(client, ManagerFactory())
    assert resp.status_code == 302
    assert resp.url == reverse("tickets:manage_stats")


@pytest.mark.parametrize("factory", [AgentFactory, CustomerFactory])
def test_agent_va_khach_dang_nhap_chuyen_toi_danh_sach(client, factory):
    resp = _login(client, factory())
    assert resp.url == reverse("tickets:list")


def test_tham_so_next_duoc_uu_tien_hon_vai_tro(client):
    ticket = TicketFactory(category=CategoryFactory())
    target = reverse("tickets:detail", args=[ticket.pk])
    resp = _login(client, ManagerFactory(), next=target)
    assert resp.url == target


def test_next_tro_ra_ngoai_bi_bo_qua(client):
    resp = _login(client, AgentFactory(), next="https://evil.example.com/")
    assert resp.url == reverse("tickets:list")


def test_sai_mat_khau_hien_loi_va_giu_ten_dang_nhap(client):
    user = CustomerFactory(username="khach_sai_mk")
    resp = client.post(LOGIN, {"username": user.username, "password": "sai"})
    html = resp.content.decode()
    assert resp.status_code == 200
    assert 'role="alert"' in html
    assert 'value="khach_sai_mk"' in html


def test_da_dang_nhap_vao_lai_trang_login_thi_chuyen_huong(client):
    client.force_login(ManagerFactory())
    resp = client.get(LOGIN)
    assert resp.status_code == 302
    assert resp.url == reverse("tickets:manage_stats")


def test_danh_sach_hien_bang_du_cot_theo_wireframe(client):
    agent = AgentFactory(username="agent_xu_ly")
    TicketFactory(title="Không vào được VPN", category=CategoryFactory(), assignee=agent)
    client.force_login(ManagerFactory())
    html = client.get(reverse("tickets:list")).content.decode()
    assert 'id="ticket-table"' in html
    for col in ["Mã", "Tiêu đề", "Trạng thái", "Ưu tiên", "Người xử lý", "Ngày tạo"]:
        assert f'<th scope="col">{col}</th>' in html
    assert "Không vào được VPN" in html
    assert "agent_xu_ly" in html


def test_loc_theo_nguoi_xu_ly(client):
    cat = CategoryFactory()
    a1 = AgentFactory()
    a2 = AgentFactory()
    TicketFactory(title="Ticket của A1", category=cat, assignee=a1)
    TicketFactory(title="Ticket của A2", category=cat, assignee=a2)
    TicketFactory(title="Ticket chưa gán", category=cat, assignee=None)
    client.force_login(ManagerFactory())
    url = reverse("tickets:list")

    html = client.get(url, {"assignee": a1.pk}).content.decode()
    assert "Ticket của A1" in html
    assert "Ticket của A2" not in html

    html = client.get(url, {"assignee": "none"}).content.decode()
    assert "Ticket chưa gán" in html
    assert "Ticket của A1" not in html

    html = client.get(url, {"assignee": "abc"}).content.decode()
    assert "Ticket của A1" in html
    assert "Ticket chưa gán" in html


def test_khach_khong_thay_bo_loc_nguoi_xu_ly_va_tham_so_bi_bo_qua(client):
    cat = CategoryFactory()
    customer = CustomerFactory()
    agent = AgentFactory()
    TicketFactory(title="Của tôi, chưa gán", category=cat, created_by=customer)
    TicketFactory(title="Của tôi, đã gán", category=cat, created_by=customer, assignee=agent)
    client.force_login(customer)
    html = client.get(reverse("tickets:list"), {"assignee": "none"}).content.decode()
    assert 'name="assignee"' not in html
    assert "Của tôi, chưa gán" in html
    assert "Của tôi, đã gán" in html


def test_phan_trang_giu_bo_loc(client):
    cat = CategoryFactory()
    for i in range(21):
        TicketFactory(title=f"Máy in số {i}", category=cat, priority=3)
    client.force_login(ManagerFactory())
    html = client.get(reverse("tickets:list"), {"q": "Máy in", "priority": "3"}).content.decode()
    assert "Trang 1 / 2" in html
    assert "?q=M%C3%A1y+in&amp;priority=3&amp;page=2" in html


def test_danh_sach_rong_hien_thong_bao(client):
    client.force_login(CustomerFactory())
    html = client.get(reverse("tickets:list")).content.decode()
    assert "Chưa có ticket nào phù hợp" in html


def test_loc_danh_muc_sai_dinh_dang_khong_loi_500(client):
    cat = CategoryFactory()
    other = CategoryFactory()
    TicketFactory(title="Ticket mạng", category=cat)
    TicketFactory(title="Ticket phần cứng", category=other)
    client.force_login(ManagerFactory())
    url = reverse("tickets:list")

    resp = client.get(url, {"category": "abc"})
    assert resp.status_code == 200
    assert "Ticket mạng" in resp.content.decode()

    html = client.get(url, {"category": str(cat.pk)}).content.decode()
    assert "Ticket mạng" in html
    assert "Ticket phần cứng" not in html
