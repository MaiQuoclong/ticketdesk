import pytest
from django.urls import reverse

from .factories import AgentFactory, CategoryFactory, CustomerFactory, ManagerFactory, TicketFactory

pytestmark = pytest.mark.django_db

HTMX = {"HTTP_HX_REQUEST": "true"}
URL = reverse("tickets:list")


def test_request_thuong_tra_ca_trang(client):
    client.force_login(ManagerFactory())
    resp = client.get(URL)
    html = resp.content.decode()
    assert "<!doctype html>" in html
    assert (
        'hx-trigger="input changed delay:300ms from:#f-q, change from:.mv-filter-select, submit"'
        in html
    )
    assert 'hx-target="#ticket-table"' in html
    assert "HX-Request" in resp["Vary"]


def test_request_htmx_chi_tra_partial_bang(client):
    TicketFactory(title="Lỗi Outlook", category=CategoryFactory())
    client.force_login(ManagerFactory())
    resp = client.get(URL, {"q": "Outlook"}, **HTMX)
    html = resp.content.decode()
    assert resp.status_code == 200
    assert "<!doctype html>" not in html
    assert "mv-navbar" not in html
    assert html.lstrip().startswith('<div id="ticket-table">')
    assert "Lỗi Outlook" in html
    assert [t.name for t in resp.templates][0] == "tickets/_table.html"
    assert "HX-Request" in resp["Vary"]


def test_htmx_tim_kiem_loc_dung_ket_qua(client):
    cat = CategoryFactory()
    TicketFactory(title="Máy in kẹt giấy", category=cat, priority=3)
    TicketFactory(title="Máy in hết mực", category=cat, priority=1)
    TicketFactory(title="Quên mật khẩu", category=cat, priority=3)
    client.force_login(ManagerFactory())
    html = client.get(URL, {"q": "máy in", "priority": "3"}, **HTMX).content.decode()
    assert "Máy in kẹt giấy" in html
    assert "Máy in hết mực" not in html
    assert "Quên mật khẩu" not in html


def test_htmx_van_giu_phan_quyen_khach(client):
    cat = CategoryFactory()
    me = CustomerFactory()
    TicketFactory(title="Ticket của tôi", category=cat, created_by=me)
    TicketFactory(title="Ticket người khác", category=cat)
    client.force_login(me)
    html = client.get(URL, **HTMX).content.decode()
    assert "Ticket của tôi" in html
    assert "Ticket người khác" not in html


def test_htmx_khi_chua_dang_nhap_bi_chuyen_ve_login(client):
    resp = client.get(URL, **HTMX)
    assert resp.status_code == 204
    assert resp["HX-Redirect"].startswith(reverse("accounts:login"))


def test_chua_dang_nhap_request_thuong_van_302(client):
    resp = client.get(URL)
    assert resp.status_code == 302
    assert reverse("accounts:login") in resp.url


def test_khoi_phuc_lich_su_tra_ca_trang(client):
    client.force_login(AgentFactory())
    resp = client.get(URL, HTTP_HX_REQUEST="true", HTTP_HX_HISTORY_RESTORE_REQUEST="true")
    assert "<!doctype html>" in resp.content.decode()


def test_phan_trang_htmx_giu_bo_loc_va_tab(client):
    cat = CategoryFactory()
    for i in range(21):
        TicketFactory(title=f"VPN lỗi {i}", category=cat, status="new")
    client.force_login(ManagerFactory())
    html = client.get(URL, {"q": "VPN", "status": "new"}, **HTMX).content.decode()
    assert 'hx-get="?q=VPN&amp;status=new&amp;page=2"' in html
    assert 'hx-push-url="true"' in html
    assert 'href="?q=VPN&amp;status=in_progress"' in html
    assert 'class="mv-tab active"' in html

    page2 = client.get(URL, {"q": "VPN", "status": "new", "page": "2"}, **HTMX).content.decode()
    assert "Trang 2 / 2" in page2
