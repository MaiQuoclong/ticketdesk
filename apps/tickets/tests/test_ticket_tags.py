from datetime import timedelta

import pytest
from django.template import Context, RequestContext, Template
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone

from apps.tickets.models import Ticket
from apps.tickets.templatetags.ticket_tags import (
    open_age,
    priority_badge,
    priority_label,
    status_badge,
    status_label,
)

from .factories import CategoryFactory, CustomerFactory, ManagerFactory, TicketFactory


def test_status_label_tu_ma_va_tu_ticket():
    assert status_label("in_progress") == "Đang xử lý"
    assert status_label(Ticket(status="closed")) == "Đã đóng"
    assert status_label("khong_co") == "khong_co"
    assert status_label(None) == ""


def test_priority_label_nhan_so_hoac_chuoi():
    assert priority_label(3) == "Cao"
    assert priority_label("1") == "Thấp"
    assert priority_label(Ticket(priority=2)) == "Trung bình"
    assert priority_label("abc") == ""
    assert priority_label(None) == ""


def test_status_badge_sinh_span_dung_lop():
    html = status_badge("resolved")
    assert html == '<span class="mv-status mv-status-resolved">Đã xử lý</span>'


def test_status_badge_ma_la_tra_rong_khong_chen_html():
    assert status_badge('"><script>alert(1)</script>') == ""


def test_priority_badge_sinh_span_dung_lop():
    html = priority_badge(Ticket(priority=3))
    assert 'class="mv-priority mv-priority-3"' in html
    assert "P3 · Cao" in html
    assert priority_badge(9) == ""


def test_filter_dung_trong_template_khong_bi_escape():
    out = Template("{% load ticket_tags %}{{ s|status_badge }}{{ p|priority_badge }}").render(
        Context({"s": "new", "p": 1})
    )
    assert '<span class="mv-status mv-status-new">Mới</span>' in out
    assert "mv-priority-1" in out


def test_querystring_giu_tham_so_loc_khi_doi_trang():
    request = RequestFactory().get("/tickets/", {"q": "máy in", "priority": "3", "page": "1"})
    out = Template("{% querystring page=2 %}").render(RequestContext(request))
    assert "q=m%C3%A1y+in" in out
    assert "priority=3" in out
    assert "page=2" in out


@pytest.mark.django_db
def test_trang_danh_sach_hien_badge_va_tab_giu_bo_loc(client):
    user = CustomerFactory()
    TicketFactory(
        title="Máy in tầng 3", created_by=user, category=CategoryFactory(), priority=3, status="new"
    )
    client.force_login(user)
    resp = client.get(reverse("tickets:list"), {"q": "in", "priority": "3"})
    html = resp.content.decode()
    assert resp.status_code == 200
    assert "mv-priority-3" in html
    assert "mv-status mv-status-new" in html
    assert "?q=in&amp;priority=3&amp;status=in_progress" in html


@pytest.mark.django_db
def test_trang_thong_ke_dung_badge(client):
    TicketFactory(category=CategoryFactory(), priority=2, status="in_progress")
    client.force_login(ManagerFactory())
    html = client.get(reverse("tickets:manage_stats")).content.decode()
    assert '<span class="mv-status mv-status-in_progress">Đang xử lý</span>' in html
    assert "mv-priority-2" in html


@pytest.mark.parametrize(
    ("age", "expected"),
    [
        (timedelta(days=105, hours=3, minutes=5), "105 ngày 3 giờ"),
        (timedelta(hours=26), "1 ngày 2 giờ"),
        (timedelta(hours=5, minutes=59), "5 giờ"),
        (timedelta(minutes=10), "< 1 giờ"),
    ],
)
def test_open_age_hien_tieng_viet(age, expected):
    assert open_age(timezone.now() - age) == expected


def test_open_age_none():
    assert open_age(None) == "—"
