import threading
import time
from datetime import timedelta
from importlib import import_module
from io import StringIO

import pytest
from django.apps import apps as global_apps
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.urls import reverse
from django.utils import timezone

from apps.accounts.groups import MANAGER_GROUP
from apps.accounts.models import User
from apps.tickets import selectors, services
from apps.tickets.models import Category, Comment, Ticket, TicketHistory

pytestmark = pytest.mark.django_db

backfill_module = import_module("apps.tickets.migrations.0003_backfill_resolved_at")


@pytest.fixture
def setup_data():
    cat = Category.objects.create(name="Mạng")
    customer = User.objects.create_user("khach01", password="123", role=User.Role.CUSTOMER)
    other = User.objects.create_user("khach02", password="123", role=User.Role.CUSTOMER)
    agent1 = User.objects.create_user("agent01", password="123", role=User.Role.AGENT)
    agent2 = User.objects.create_user("agent02", password="123", role=User.Role.AGENT)
    manager = User.objects.create_user(
        "quanly01", password="123", role=User.Role.MANAGER, is_staff=True
    )
    return {
        "cat": cat,
        "customer": customer,
        "other": other,
        "agent1": agent1,
        "agent2": agent2,
        "manager": manager,
    }


def make_ticket(data, **kwargs):
    fields = {
        "title": "Không vào được VPN",
        "description": "Chi tiết",
        "category": data["cat"],
        "created_by": data["customer"],
    }
    fields.update(kwargs)
    return Ticket.objects.create(**fields)


@pytest.mark.parametrize("field, value", [("title", ""), ("priority", 9)])
def test_check_constraints_reject_invalid_ticket(setup_data, field, value):
    with pytest.raises(IntegrityError), transaction.atomic():
        make_ticket(setup_data, **{field: value})


def test_seed_tickets_bulk_creates_tickets_and_comments(setup_data):
    call_command("seed_tickets", count=50, comments=2, stdout=StringIO())
    assert Ticket.objects.count() == 50
    assert Comment.objects.count() > 0
    assert not Ticket.objects.filter(status=Ticket.Status.NEW, assignee__isnull=False).exists()


def test_ticket_list_comment_count_hides_internal_for_customer(client, setup_data):
    ticket = make_ticket(setup_data)
    Comment.objects.create(ticket=ticket, author=setup_data["customer"], content="a")
    Comment.objects.create(ticket=ticket, author=setup_data["agent1"], content="b")
    Comment.objects.create(
        ticket=ticket, author=setup_data["agent1"], content="nội bộ", is_internal=True
    )

    client.force_login(setup_data["customer"])
    row = client.get(reverse("tickets:list")).context["tickets"][0]
    assert row.comment_count == 2

    client.force_login(setup_data["manager"])
    row = client.get(reverse("tickets:list")).context["tickets"][0]
    assert row.comment_count == 3


def test_ticket_list_query_count_does_not_grow_with_rows(
    client, setup_data, django_assert_max_num_queries
):
    for i in range(25):
        t = make_ticket(setup_data, title=f"Ticket {i}", assignee=setup_data["agent1"])
        Comment.objects.create(ticket=t, author=setup_data["agent1"], content="x")

    client.force_login(setup_data["manager"])
    with django_assert_max_num_queries(8):
        resp = client.get(reverse("tickets:list"))
    assert resp.status_code == 200


def test_manage_users_counts_with_subquery(client, setup_data, django_assert_max_num_queries):
    make_ticket(setup_data, assignee=setup_data["agent1"])
    make_ticket(setup_data, assignee=setup_data["agent1"])
    make_ticket(setup_data, created_by=setup_data["other"])

    client.force_login(setup_data["manager"])
    with django_assert_max_num_queries(5):
        resp = client.get(reverse("tickets:manage_users"))
    users = {u.username: u for u in resp.context["users_list"]}
    assert users["khach01"].created_count == 2
    assert users["khach02"].created_count == 1
    assert users["agent01"].assigned_count == 2
    assert users["agent02"].assigned_count == 0


def test_stats_selectors(setup_data):
    now = timezone.now()
    make_ticket(setup_data)
    old = make_ticket(setup_data)
    Ticket.objects.filter(pk=old.pk).update(created_at=now - timedelta(days=5))
    make_ticket(setup_data, status=Ticket.Status.IN_PROGRESS, assignee=setup_data["agent1"])
    done = make_ticket(
        setup_data,
        status=Ticket.Status.RESOLVED,
        assignee=setup_data["agent1"],
        priority=Ticket.Priority.HIGH,
    )
    Ticket.objects.filter(pk=done.pk).update(created_at=now - timedelta(hours=10), resolved_at=now)

    summary = selectors.ticket_summary()
    assert summary["total"] == 4
    assert summary["new"] == 2
    assert summary["unassigned"] == 2
    assert summary["overdue"] == 1
    assert summary["done_pct"] == 25

    agents = {a.username: a for a in selectors.agent_workload()}
    assert agents["agent01"].total == 2
    assert agents["agent01"].in_progress == 1
    assert agents["agent01"].avg_resolve_display == "10 giờ"
    assert agents["agent02"].avg_resolve_display == "—"


def test_stats_page_only_for_manager(client, setup_data):
    url = reverse("tickets:manage_stats")
    client.force_login(setup_data["agent1"])
    assert client.get(url).status_code == 302
    client.force_login(setup_data["manager"])
    assert client.get(url).status_code == 200


def test_backfill_resolved_at_migration(setup_data):
    resolved = make_ticket(setup_data, status=Ticket.Status.RESOLVED)
    closed = make_ticket(setup_data, status=Ticket.Status.CLOSED)
    kept_time = timezone.now() - timedelta(days=1)
    kept = make_ticket(setup_data, status=Ticket.Status.RESOLVED, resolved_at=kept_time)
    still_open = make_ticket(setup_data)
    history = TicketHistory.objects.create(
        ticket=resolved,
        actor=setup_data["agent1"],
        field="Trạng thái",
        old_value="Đang xử lý",
        new_value="Đã xử lý",
    )

    backfill_module.backfill_resolved_at(global_apps, None)

    for t in (resolved, closed, kept, still_open):
        t.refresh_from_db()
    assert resolved.resolved_at == history.created_at
    assert closed.resolved_at == closed.updated_at
    assert kept.resolved_at == kept_time
    assert still_open.resolved_at is None


def test_manager_group_permissions_and_signal(setup_data):
    group = Group.objects.get(name=MANAGER_GROUP)
    manager = setup_data["manager"]
    assert group in manager.groups.all()
    assert manager.has_perm("tickets.change_ticket")
    assert not manager.has_perm("accounts.change_user")

    manager.role = User.Role.AGENT
    manager.save()
    assert not manager.groups.filter(name=MANAGER_GROUP).exists()


def test_manager_can_open_ticket_admin(client, setup_data):
    url = reverse("admin:tickets_ticket_changelist")
    client.force_login(setup_data["manager"])
    assert client.get(url).status_code == 200
    assert client.get(reverse("admin:accounts_user_changelist")).status_code == 403
    client.force_login(setup_data["agent1"])
    assert client.get(url).status_code == 302


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
@pytest.mark.skipif(connection.vendor != "postgresql", reason="Cần PostgreSQL để khoá dòng")
def test_concurrent_assign_keeps_full_history(setup_data, monkeypatch):
    ticket = make_ticket(setup_data)
    original_save = Ticket.save

    def slow_save(self, *args, **kwargs):
        time.sleep(0.3)
        return original_save(self, *args, **kwargs)

    monkeypatch.setattr(Ticket, "save", slow_save)
    errors = []

    def run(agent):
        try:
            stale = Ticket.objects.get(pk=ticket.pk)
            services.assign_ticket(ticket=stale, agent=agent, actor=setup_data["manager"])
        except Exception as exc:
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=run, args=(setup_data[k],)) for k in ("agent1", "agent2")]
    for th in threads:
        th.start()
    for th in threads:
        th.join()

    assert errors == []
    assignee_history = list(
        TicketHistory.objects.filter(ticket=ticket, field="Người xử lý")
        .order_by("created_at")
        .values_list("old_value", "new_value")
    )
    assert assignee_history[0][0] == "Chưa gán"
    assert assignee_history[1][0] == assignee_history[0][1]
    assert TicketHistory.objects.filter(ticket=ticket, field="Trạng thái").count() == 1
