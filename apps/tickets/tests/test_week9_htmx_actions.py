import pytest
from django.test import Client
from django.urls import reverse

from apps.tickets.models import Comment, Ticket

from .factories import (
    AgentFactory,
    CategoryFactory,
    CustomerFactory,
    ManagerFactory,
    TicketFactory,
)

pytestmark = pytest.mark.django_db

HTMX = {"HTTP_HX_REQUEST": "true"}
OOB_IDS = [
    "messages",
    "ticket-summary",
    "ticket-actions",
    "ticket-comments",
    "ticket-attachments",
    "ticket-history",
    "count-comments",
    "count-history",
]


@pytest.fixture
def ticket():
    return TicketFactory(category=CategoryFactory(), status="new")


def _url(name, ticket):
    return reverse(f"tickets:{name}", args=[ticket.pk])


def test_trang_chi_tiet_dung_hx_post_va_swap_none(client, ticket):
    client.force_login(ManagerFactory())
    html = client.get(_url("detail", ticket)).content.decode()
    for name in ["assign", "change_status", "add_comment"]:
        assert f'hx-post="{_url(name, ticket)}"' in html
    assert html.count('hx-swap="none"') == 3
    assert "hx-swap-oob" not in html
    assert '"X-CSRFToken"' in html


def test_doi_trang_thai_htmx_tra_cac_khoi_oob(client, ticket):
    client.force_login(AgentFactory())
    resp = client.post(_url("change_status", ticket), {"status": "resolved"}, **HTMX)
    html = resp.content.decode()
    assert resp.status_code == 200
    assert "<!doctype html>" not in html
    for oob_id in OOB_IDS:
        assert f'id="{oob_id}"' in html
    assert html.count('hx-swap-oob="true"') >= len(OOB_IDS)
    assert "Đã chuyển trạng thái sang Đã xử lý" in html
    assert '<span class="mv-status mv-status-resolved">Đã xử lý</span>' in html
    assert "Mới → <strong>Đã xử lý</strong>" in html
    ticket.refresh_from_db()
    assert ticket.status == Ticket.Status.RESOLVED


def test_doi_trang_thai_khong_htmx_van_redirect(client, ticket):
    client.force_login(AgentFactory())
    resp = client.post(_url("change_status", ticket), {"status": "in_progress"})
    assert resp.status_code == 302
    assert resp.url == _url("detail", ticket)


def test_dong_ticket_an_form_binh_luan_va_thao_tac(client, ticket):
    client.force_login(ManagerFactory())
    resp = client.post(_url("change_status", ticket), {"status": "closed"}, **HTMX)
    html = resp.content.decode()
    assert "Ticket đã đóng, không thể bình luận thêm." in html
    assert "Ticket đã đóng, không thể đổi trạng thái." in html
    assert "Ticket đã đóng, không thể gán lại." in html
    assert f'hx-post="{_url("add_comment", ticket)}"' not in html


def test_doi_trang_thai_ticket_dong_bao_loi_nghiep_vu(client):
    closed = TicketFactory(category=CategoryFactory(), status="closed")
    client.force_login(AgentFactory())
    resp = client.post(_url("change_status", closed), {"status": "new"}, **HTMX)
    html = resp.content.decode()
    assert "mv-alert-error" in html
    assert "Không thể chuyển trạng thái từ Đã đóng" in html
    closed.refresh_from_db()
    assert closed.status == Ticket.Status.CLOSED


def test_khach_doi_trang_thai_htmx_bi_tu_choi(client):
    me = CustomerFactory()
    mine = TicketFactory(category=CategoryFactory(), created_by=me)
    client.force_login(me)
    resp = client.post(_url("change_status", mine), {"status": "closed"}, **HTMX)
    assert "Khách hàng không được tự đổi trạng thái" in resp.content.decode()
    mine.refresh_from_db()
    assert mine.status == Ticket.Status.NEW


def test_gan_htmx_cap_nhat_nguoi_xu_ly_va_trang_thai(client, ticket):
    agent = AgentFactory(username="agent_htmx")
    client.force_login(ManagerFactory())
    resp = client.post(_url("assign", ticket), {"agent_id": str(agent.pk)}, **HTMX)
    html = resp.content.decode()
    assert "Đã gán ticket cho nhân viên agent_htmx" in html
    assert '<div class="mv-detail-person">agent_htmx</div>' in html
    assert "mv-status-in_progress" in html
    ticket.refresh_from_db()
    assert ticket.assignee == agent


@pytest.mark.parametrize("agent_id", ["", "abc", "00000000-0000-0000-0000-000000000000"])
def test_gan_nguoi_khong_hop_le_bao_loi(client, ticket, agent_id):
    client.force_login(ManagerFactory())
    resp = client.post(_url("assign", ticket), {"agent_id": agent_id}, **HTMX)
    assert resp.status_code == 200
    assert "Vui lòng chọn một nhân viên hỗ trợ hợp lệ." in resp.content.decode()
    ticket.refresh_from_db()
    assert ticket.assignee is None


def test_gan_cho_khach_hang_bi_tu_choi(client, ticket):
    client.force_login(ManagerFactory())
    customer = CustomerFactory()
    resp = client.post(_url("assign", ticket), {"agent_id": str(customer.pk)}, **HTMX)
    assert "Vui lòng chọn một nhân viên hỗ trợ hợp lệ." in resp.content.decode()


def test_agent_gan_bi_tu_choi(client, ticket):
    client.force_login(AgentFactory())
    agent = AgentFactory()
    resp = client.post(_url("assign", ticket), {"agent_id": str(agent.pk)}, **HTMX)
    assert "Chỉ Quản lý mới có quyền gán" in resp.content.decode()


def test_binh_luan_htmx_them_vao_danh_sach_va_xoa_o_nhap(client, ticket):
    client.force_login(ticket.created_by)
    resp = client.post(_url("add_comment", ticket), {"content": "Tôi đã thử khởi động lại"}, **HTMX)
    html = resp.content.decode()
    assert "Đã gửi bình luận." in html
    assert '<div class="mv-comment-body">Tôi đã thử khởi động lại</div>' in html
    assert '<span id="count-comments" hx-swap-oob="true">1</span>' in html
    assert ">Tôi đã thử khởi động lại</textarea>" not in html
    assert Comment.objects.filter(ticket=ticket).count() == 1


def test_binh_luan_rong_bao_loi(client, ticket):
    client.force_login(ticket.created_by)
    resp = client.post(_url("add_comment", ticket), {"content": ""}, **HTMX)
    assert "Nội dung bình luận không hợp lệ." in resp.content.decode()
    assert Comment.objects.count() == 0


def test_binh_luan_ticket_dong_bao_loi(client):
    closed = TicketFactory(category=CategoryFactory(), status="closed")
    client.force_login(AgentFactory())
    resp = client.post(_url("add_comment", closed), {"content": "Nội dung muộn"}, **HTMX)
    assert "Ticket đã đóng, không thể thêm bình luận mới." in resp.content.decode()
    assert Comment.objects.count() == 0


def test_ghi_chu_noi_bo_khong_lo_cho_khach_qua_htmx(client, ticket):
    client.force_login(AgentFactory())
    client.post(
        _url("add_comment", ticket),
        {"content": "Nội bộ: kiểm tra RAM", "is_internal": "on"},
        **HTMX,
    )
    client.force_login(ticket.created_by)
    resp = client.post(_url("add_comment", ticket), {"content": "Khách hỏi"}, **HTMX)
    html = resp.content.decode()
    assert "Nội bộ: kiểm tra RAM" not in html
    assert '<span id="count-comments" hx-swap-oob="true">1</span>' in html


def test_khach_khac_htmx_tra_404(client, ticket):
    client.force_login(CustomerFactory())
    resp = client.post(_url("add_comment", ticket), {"content": "xin chào"}, **HTMX)
    assert resp.status_code == 404


def test_chua_dang_nhap_htmx_tra_hx_redirect(client, ticket):
    resp = client.post(_url("change_status", ticket), {"status": "closed"}, **HTMX)
    assert resp.status_code == 204
    assert resp["HX-Redirect"].startswith(reverse("accounts:login"))
    assert "next=" in resp["HX-Redirect"]


def test_chua_dang_nhap_khong_htmx_redirect_login(client, ticket):
    resp = client.post(_url("add_comment", ticket), {"content": "x"})
    assert resp.status_code == 302
    assert reverse("accounts:login") in resp.url


def test_thieu_csrf_bi_chan(ticket):
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(AgentFactory())
    resp = csrf_client.post(_url("change_status", ticket), {"status": "closed"}, **HTMX)
    assert resp.status_code == 403
    ticket.refresh_from_db()
    assert ticket.status == Ticket.Status.NEW


def test_xoa_loc_cap_nhat_qua_oob_khi_loc_htmx(client):
    client.force_login(ManagerFactory())
    url = reverse("tickets:list")
    html = client.get(url, {"q": "vpn"}, **HTMX).content.decode()
    assert '<span id="clear-filter" hx-swap-oob="true"><a href="/"' in html
    html = client.get(url, **HTMX).content.decode()
    assert '<span id="clear-filter" hx-swap-oob="true"></span>' in html


def test_xoa_loc_trang_day_du_khong_co_oob(client):
    client.force_login(ManagerFactory())
    html = client.get(reverse("tickets:list"), {"q": "vpn"}).content.decode()
    assert html.count('id="clear-filter"') == 1
    assert 'id="clear-filter" hx-swap-oob' not in html
    assert "Xóa lọc" in html
