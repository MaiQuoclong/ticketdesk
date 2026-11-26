import logging
from datetime import timedelta
from typing import Any
from unittest import mock

import pytest
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from apps.tickets import selectors, services
from apps.tickets.models import Ticket
from apps.tickets.tests.factories import (
    AgentFactory,
    CategoryFactory,
    ManagerFactory,
    TicketFactory,
)

pytestmark = pytest.mark.django_db
SUMMARY_URL = "/api/v1/dashboard/summary/"
SLA_URL = "/api/v1/dashboard/sla-overdue/"


@pytest.fixture(autouse=True)
def cache_up(monkeypatch):
    monkeypatch.setitem(selectors._cache_state, "down_until", 0.0)


@pytest.fixture
def manager_api() -> Any:
    client = APIClient()
    client.force_authenticate(ManagerFactory())
    return client


def _age(ticket: Ticket, hours: float) -> None:
    Ticket.objects.filter(pk=ticket.pk).update(created_at=timezone.now() - timedelta(hours=hours))


def test_summary_overdue_matches_sla_overdue_list(manager_api):
    _age(TicketFactory(), 30)
    _age(TicketFactory(status=Ticket.Status.IN_PROGRESS, assignee=AgentFactory()), 25)
    _age(TicketFactory(status=Ticket.Status.RESOLVED), 48)
    _age(TicketFactory(status=Ticket.Status.CLOSED), 48)
    _age(TicketFactory(), 23)
    TicketFactory()

    summary = manager_api.get(SUMMARY_URL).data["summary"]
    sla = manager_api.get(SLA_URL).data

    assert summary["overdue"] == 2
    assert summary["overdue"] == sla["count"]
    assert summary["overdue"] == selectors.sla_overdue_tickets().count()


def test_stats_page_shows_sla_overdue_box(client):
    _age(TicketFactory(status=Ticket.Status.IN_PROGRESS, assignee=AgentFactory()), 30)
    client.force_login(ManagerFactory())

    resp = client.get("/manage/stats/")

    assert resp.status_code == 200
    assert resp.context["summary"]["overdue"] == 1
    assert f"Quá SLA {selectors.SLA_HOURS} giờ" in resp.content.decode()


def test_second_request_is_served_from_cache(manager_api, django_assert_max_num_queries):
    TicketFactory.create_batch(3)
    manager_api.get(SUMMARY_URL)
    assert cache.get(selectors.STATS_CACHE_KEY) is not None

    with mock.patch.object(selectors, "compute_dashboard_stats") as compute:
        resp = manager_api.get(SUMMARY_URL)

    compute.assert_not_called()
    assert resp.data["summary"]["total"] == 3


def test_cache_invalidated_after_ticket_created_assigned_and_closed(
    manager_api, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        ticket = TicketFactory()
    assert manager_api.get(SUMMARY_URL).data["summary"]["new"] == 1

    agent = AgentFactory()
    manager_api.get(SUMMARY_URL)
    with django_capture_on_commit_callbacks(execute=True):
        services.assign_ticket(ticket=ticket, agent=agent, actor=agent)
    assert cache.get(selectors.STATS_CACHE_KEY) is None
    data = manager_api.get(SUMMARY_URL).data
    assert data["summary"]["in_progress"] == 1
    assert any(a["username"] == agent.username and a["in_progress"] == 1 for a in data["agents"])

    with django_capture_on_commit_callbacks(execute=True):
        services.change_ticket_status(ticket=ticket, new_status=Ticket.Status.CLOSED, actor=agent)
    assert manager_api.get(SUMMARY_URL).data["summary"]["closed"] == 1


def test_cache_invalidated_after_category_change(manager_api, django_capture_on_commit_callbacks):
    manager_api.get(SUMMARY_URL)
    with django_capture_on_commit_callbacks(execute=True):
        category = CategoryFactory()

    names = [row["name"] for row in manager_api.get(SUMMARY_URL).data["by_category"]]
    assert category.name in names


def test_cache_not_invalidated_before_commit(manager_api, django_capture_on_commit_callbacks):
    manager_api.get(SUMMARY_URL)
    with django_capture_on_commit_callbacks(execute=False):
        TicketFactory()

    assert cache.get(selectors.STATS_CACHE_KEY) is not None


def test_login_does_not_clear_stats_cache(client):
    manager = ManagerFactory()
    selectors.dashboard_stats()

    client.post("/accounts/login/", {"username": manager.username, "password": "matkhau123"})

    assert cache.get(selectors.STATS_CACHE_KEY) is not None


def test_cache_down_falls_back_to_db_and_skips_cache_for_a_while(caplog):
    caplog.set_level(logging.WARNING, logger="apps.tickets.selectors")
    TicketFactory()

    with mock.patch.object(
        selectors.cache, "get_or_set", side_effect=ConnectionError("redis down")
    ) as get_or_set:
        assert selectors.dashboard_stats()["summary"]["total"] == 1
        assert selectors.dashboard_stats()["summary"]["total"] == 1

    assert get_or_set.call_count == 1
    assert selectors._cache_state["down_until"] > 0
    record = next(r for r in caplog.records if getattr(r, "event", None) == "cache_down")
    assert record.action == "đọc thống kê"

    with mock.patch.object(selectors.time, "monotonic", return_value=10**9):
        selectors.dashboard_stats()
    assert cache.get(selectors.STATS_CACHE_KEY) is not None


def test_invalidate_when_cache_down_does_not_raise():
    with mock.patch.object(selectors.cache, "delete", side_effect=ConnectionError("down")):
        selectors.invalidate_stats()

    assert selectors._cache_state["down_until"] > 0


def test_unexpected_cached_value_is_recomputed():
    TicketFactory()
    cache.set(selectors.STATS_CACHE_KEY, "hỏng")

    assert selectors.dashboard_stats()["summary"]["total"] == 1


def test_export_returns_503_when_cache_down(manager_api):
    TicketFactory()
    today = timezone.localdate()
    with mock.patch("apps.tickets.api.views.cache") as fake_cache:
        fake_cache.set.side_effect = ConnectionError("down")
        fake_cache.delete.side_effect = ConnectionError("down")
        resp = manager_api.post(
            "/api/v1/reports/export/", {"date_from": str(today), "date_to": str(today)}
        )

    assert resp.status_code == 503
    assert resp.data["code"] == "queue_unavailable"
