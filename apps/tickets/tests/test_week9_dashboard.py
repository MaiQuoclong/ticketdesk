import json
import re
from datetime import timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.tickets import selectors
from apps.tickets.models import Ticket

from .factories import (
    AgentFactory,
    CategoryFactory,
    CustomerFactory,
    ManagerFactory,
    TicketFactory,
)

pytestmark = pytest.mark.django_db

URL = reverse("tickets:manage_stats")


def _old(ticket, hours):
    Ticket.objects.filter(pk=ticket.pk).update(created_at=timezone.now() - timedelta(hours=hours))


def _chart_json(html):
    match = re.search(r'<script id="dashboard-data" type="application/json">(.*?)</script>', html)
    assert match
    return json.loads(match.group(1))


def test_dashboard_co_bieu_do_va_nut_xuat_excel(client):
    client.force_login(ManagerFactory())
    html = client.get(URL).content.decode()
    assert 'id="chart-status"' in html
    assert 'id="chart-agents"' in html
    assert "chart.js@4" in html
    assert "js/dashboard.js" in html
    assert "js/export.js" in html
    assert f'data-start-url="{reverse("api-v1-report-export")}"' in html
    assert 'name="csrfmiddlewaretoken"' in html


def test_du_lieu_bieu_do_trang_thai_mau_trung_nhan(client):
    cat = CategoryFactory()
    TicketFactory.create_batch(2, category=cat, status="new")
    TicketFactory(category=cat, status="resolved")
    client.force_login(ManagerFactory())
    data = _chart_json(client.get(URL).content.decode())
    assert data["status"]["labels"] == ["Mới", "Đang xử lý", "Đã xử lý", "Đã đóng"]
    assert data["status"]["values"] == [2, 0, 1, 0]
    assert data["status"]["colors"] == [
        selectors.STATUS_COLORS[c] for c in ["new", "in_progress", "resolved", "closed"]
    ]


def test_du_lieu_bieu_do_theo_nguoi_xu_ly(client):
    cat = CategoryFactory()
    a1 = AgentFactory(username="agent_a")
    TicketFactory(category=cat, assignee=a1, status="in_progress")
    TicketFactory(category=cat, assignee=a1, status="closed")
    client.force_login(ManagerFactory())
    data = _chart_json(client.get(URL).content.decode())
    idx = data["agents"]["labels"].index("agent_a")
    by_label = {ds["label"]: ds["data"][idx] for ds in data["agents"]["datasets"]}
    assert by_label == {"Đang xử lý": 1, "Đã xử lý": 0, "Đã đóng": 1}
    colors = [ds["backgroundColor"] for ds in data["agents"]["datasets"]]
    assert colors == [selectors.STATUS_COLORS[c] for c in ["in_progress", "resolved", "closed"]]


def test_json_script_chong_xss_ten_nhan_vien(client):
    AgentFactory(username="</script><b>x")
    client.force_login(ManagerFactory())
    html = client.get(URL).content.decode()
    assert "</script><b>x" not in html
    assert "\\u003C/script\\u003E" in html


def test_danh_sach_qua_sla_to_do_va_chi_ticket_mo(client):
    cat = CategoryFactory()
    overdue = TicketFactory(title="Quá hạn máy chủ", category=cat, status="new")
    _old(overdue, selectors.SLA_HOURS + 5)
    done_old = TicketFactory(title="Cũ nhưng đã xong", category=cat, status="resolved")
    _old(done_old, selectors.SLA_HOURS + 5)
    TicketFactory(title="Mới tạo", category=cat, status="new")
    client.force_login(ManagerFactory())
    html = client.get(URL).content.decode()
    assert 'class="mv-overdue-row"' in html
    assert "Quá hạn máy chủ" in html
    assert "Cũ nhưng đã xong" not in html
    assert "Mới tạo" not in html
    assert "Quá SLA 24 giờ (1)" in html


def test_danh_sach_qua_sla_gioi_han_va_ghi_chu(client):
    cat = CategoryFactory()
    for _ in range(22):
        _old(TicketFactory(category=cat, status="new"), selectors.SLA_HOURS + 1)
    client.force_login(ManagerFactory())
    html = client.get(URL).content.decode()
    assert html.count('class="mv-overdue-row"') == 20
    assert "Đang hiện 20 ticket cũ nhất trên tổng 22." in html


def test_khong_co_ticket_qua_sla(client):
    client.force_login(ManagerFactory())
    html = client.get(URL).content.decode()
    assert "Không có ticket nào quá SLA." in html


def test_ngay_mac_dinh_xuat_excel_dau_thang_den_hom_nay(client):
    client.force_login(ManagerFactory())
    html = client.get(URL).content.decode()
    today = timezone.localdate()
    assert f'value="{today.replace(day=1).isoformat()}"' in html
    assert f'value="{today.isoformat()}"' in html


@pytest.mark.parametrize("factory", [AgentFactory, CustomerFactory])
def test_khong_phai_manager_khong_vao_dashboard(client, factory):
    client.force_login(factory())
    resp = client.get(URL)
    assert resp.status_code == 302
    assert resp.url == reverse("tickets:list")


def test_fetch_xuat_excel_bang_phien_web_va_csrf(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    TicketFactory(category=CategoryFactory())
    web = Client(enforce_csrf_checks=True)
    web.force_login(ManagerFactory())
    html = web.get(URL).content.decode()
    token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', html).group(1)
    today = timezone.localdate().isoformat()
    body = json.dumps({"date_from": today, "date_to": today})
    start = reverse("api-v1-report-export")

    blocked = web.post(start, body, content_type="application/json")
    assert blocked.status_code == 403

    resp = web.post(start, body, content_type="application/json", HTTP_X_CSRFTOKEN=token)
    assert resp.status_code == 202
    task_id = resp.json()["task_id"]

    status = web.get(f"{start}{task_id}/").json()
    assert status["status"] == "success"
    assert status["rows"] == 1
    download = web.get(status["download_url"])
    assert download.status_code == 200


def test_fetch_xuat_excel_khong_co_du_lieu_tra_loi_ro_rang(client):
    client.force_login(ManagerFactory())
    resp = client.post(
        reverse("api-v1-report-export"),
        {"date_from": "2001-01-01", "date_to": "2001-01-02"},
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Không có dữ liệu trong khoảng thời gian đã chọn."
