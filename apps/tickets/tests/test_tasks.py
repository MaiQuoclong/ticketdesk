import logging
from datetime import timedelta
from smtplib import SMTPException
from unittest import mock

import pytest
from celery.exceptions import Retry
from django.conf import settings
from django.core import mail
from django.core.cache import cache
from django.utils import timezone

from apps.tickets import services, tasks
from apps.tickets.models import Ticket
from apps.tickets.tests.factories import (
    AgentFactory,
    CommentFactory,
    CustomerFactory,
    ManagerFactory,
    TicketFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def people():
    customer = CustomerFactory(email="khach@example.com")
    agent = AgentFactory(email="agent@example.com")
    ticket = TicketFactory(created_by=customer)
    return {"customer": customer, "agent": agent, "ticket": ticket}


def _make_old(hours: int = 30, **kwargs) -> Ticket:
    ticket = TicketFactory(**kwargs)
    Ticket.objects.filter(pk=ticket.pk).update(created_at=timezone.now() - timedelta(hours=hours))
    return ticket


def _events(caplog, event: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records if getattr(r, "event", None) == event]


def test_assign_sends_status_email_to_owner_after_commit(
    people, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks() as callbacks:
        services.assign_ticket(
            ticket=people["ticket"], agent=people["agent"], actor=people["agent"]
        )
        assert mail.outbox == []

    for callback in callbacks:
        callback()

    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.to == ["khach@example.com"]
    assert people["ticket"].short_id in message.subject
    assert "Đang xử lý" in message.subject
    assert "từ Mới sang Đang xử lý" in message.body


def test_no_email_when_transaction_rolls_back(people, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        services.change_ticket_status(
            ticket=people["ticket"], new_status=Ticket.Status.RESOLVED, actor=people["agent"]
        )

    assert any(cb.__qualname__ == "_enqueue.<locals>.send" for cb in callbacks)
    assert mail.outbox == []


def test_status_email_skipped_when_owner_acts(people, django_capture_on_commit_callbacks, caplog):
    caplog.set_level(logging.INFO, logger="apps.tickets.tasks")
    with django_capture_on_commit_callbacks(execute=True):
        services.change_ticket_status(
            ticket=people["ticket"], new_status=Ticket.Status.CLOSED, actor=people["customer"]
        )

    assert mail.outbox == []
    assert _events(caplog, "notify_status_changed")[0].reason == "actor_is_owner"


def test_status_email_skipped_when_owner_has_no_email(django_capture_on_commit_callbacks, caplog):
    caplog.set_level(logging.INFO, logger="apps.tickets.tasks")
    ticket = TicketFactory(created_by=CustomerFactory(email=""))
    with django_capture_on_commit_callbacks(execute=True):
        services.change_ticket_status(
            ticket=ticket, new_status=Ticket.Status.RESOLVED, actor=AgentFactory()
        )

    assert mail.outbox == []
    assert _events(caplog, "notify_status_changed")[0].reason == "no_email"


def test_status_email_for_missing_ticket_returns_zero(caplog):
    caplog.set_level(logging.INFO, logger="apps.tickets.tasks")

    result = tasks.notify_status_changed.run(
        "00000000-0000-0000-0000-000000000000", "new", "resolved"
    )

    assert result == 0
    assert _events(caplog, "notify_status_changed")[0].reason == "ticket_not_found"


def test_status_email_shows_raw_value_for_unknown_status(people):
    sent = tasks.notify_status_changed.run(str(people["ticket"].pk), "new", "archived")

    assert sent == 1
    assert "archived" in mail.outbox[0].subject


def test_customer_comment_notifies_assignee(people, django_capture_on_commit_callbacks):
    ticket = people["ticket"]
    Ticket.objects.filter(pk=ticket.pk).update(assignee=people["agent"])
    ticket.refresh_from_db()

    with django_capture_on_commit_callbacks(execute=True):
        services.add_comment(ticket=ticket, author=people["customer"], content="Vẫn chưa được")

    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["agent@example.com"]
    assert "Vẫn chưa được" in mail.outbox[0].body


def test_agent_comment_notifies_customer(people, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        services.add_comment(ticket=people["ticket"], author=people["agent"], content="Đã kiểm tra")

    assert [m.to for m in mail.outbox] == [["khach@example.com"]]


def test_internal_note_never_queues_email(people, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        services.add_comment(
            ticket=people["ticket"], author=people["agent"], content="Nội bộ", is_internal=True
        )

    assert callbacks == []
    assert mail.outbox == []


@pytest.mark.parametrize(
    ("setup", "reason"),
    [
        ("internal", "internal_note"),
        ("unassigned", "no_recipient"),
        ("no_email", "no_email"),
        ("missing", "comment_not_found"),
    ],
)
def test_comment_email_skip_reasons(people, caplog, setup, reason):
    caplog.set_level(logging.INFO, logger="apps.tickets.tasks")
    ticket = people["ticket"]
    if setup == "internal":
        comment_id = str(CommentFactory(ticket=ticket, author=people["agent"], is_internal=True).pk)
    elif setup == "unassigned":
        comment_id = str(CommentFactory(ticket=ticket, author=people["customer"]).pk)
    elif setup == "no_email":
        people["customer"].email = ""
        people["customer"].save()
        comment_id = str(CommentFactory(ticket=ticket, author=people["agent"]).pk)
    else:
        comment_id = "00000000-0000-0000-0000-000000000000"

    assert tasks.notify_new_comment.run(comment_id) == 0
    assert mail.outbox == []
    assert _events(caplog, "notify_new_comment")[0].reason == reason


def test_email_tasks_retry_with_backoff_on_smtp_errors():
    for task in (
        tasks.notify_status_changed,
        tasks.notify_new_comment,
        tasks.remind_overdue_tickets,
    ):
        assert task.autoretry_for == (SMTPException, OSError)
        assert task.max_retries == 5
        assert task.retry_backoff == 30
        assert task.retry_backoff_max == 600
        assert task.retry_jitter is True


def test_smtp_error_schedules_retry(people):
    with mock.patch("apps.tickets.tasks.send_mail", side_effect=SMTPException("down")) as send:
        with pytest.raises(Retry):
            tasks.notify_status_changed.delay(str(people["ticket"].pk), "new", "resolved")

    assert send.call_count == 1


def test_task_retry_signal_logs_warning(caplog):
    caplog.set_level(logging.WARNING, logger="apps.tickets.tasks")

    tasks.task_retry.send(
        sender=tasks.notify_status_changed,
        request=mock.Mock(id="abc", retries=2),
        reason=SMTPException("down"),
    )

    record = caplog.records[-1]
    assert record.levelno == logging.WARNING
    assert (record.task, record.task_id, record.retries, record.error) == (
        "apps.tickets.tasks.notify_status_changed",
        "abc",
        2,
        "SMTPException",
    )


def test_task_failure_signal_logs_error(caplog):
    caplog.set_level(logging.ERROR, logger="apps.tickets.tasks")

    tasks.task_failure.send(
        sender=tasks.notify_new_comment, task_id="abc", exception=ConnectionRefusedError()
    )

    record = caplog.records[-1]
    assert record.levelno == logging.ERROR
    assert (record.task, record.task_id, record.error) == (
        "apps.tickets.tasks.notify_new_comment",
        "abc",
        "ConnectionRefusedError",
    )


def test_smtp_down_does_not_break_status_change(people, django_capture_on_commit_callbacks):
    with mock.patch("apps.tickets.tasks.send_mail", side_effect=SMTPException("down")):
        with django_capture_on_commit_callbacks(execute=True):
            services.change_ticket_status(
                ticket=people["ticket"], new_status=Ticket.Status.RESOLVED, actor=people["agent"]
            )

    people["ticket"].refresh_from_db()
    assert people["ticket"].status == Ticket.Status.RESOLVED


def test_broker_down_is_logged_and_request_still_succeeds(
    people, django_capture_on_commit_callbacks, caplog
):
    caplog.set_level(logging.ERROR, logger="apps.tickets.services")
    with mock.patch.object(
        tasks.notify_status_changed, "delay", side_effect=ConnectionError("redis down")
    ):
        with django_capture_on_commit_callbacks(execute=True):
            services.change_ticket_status(
                ticket=people["ticket"], new_status=Ticket.Status.RESOLVED, actor=people["agent"]
            )

    people["ticket"].refresh_from_db()
    assert people["ticket"].status == Ticket.Status.RESOLVED
    record = _events(caplog, "enqueue_failed")[0]
    assert record.task == "apps.tickets.tasks.notify_status_changed"
    assert record.exc_info is not None


def test_sla_reminder_sent_once_per_day_to_managers_with_email():
    ManagerFactory(email="ql1@example.com")
    ManagerFactory(email="ql2@example.com")
    ManagerFactory(email="")
    ManagerFactory(email="nghi@example.com", is_active=False)
    overdue_new = _make_old()
    overdue_progress = _make_old(status=Ticket.Status.IN_PROGRESS, assignee=AgentFactory())
    _make_old(status=Ticket.Status.RESOLVED)
    TicketFactory()

    assert tasks.remind_overdue_tickets.delay().get() == 1
    assert tasks.remind_overdue_tickets.delay().get() == 0

    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert sorted(message.to) == ["ql1@example.com", "ql2@example.com"]
    assert "2 ticket" in message.subject
    assert overdue_new.short_id in message.body
    assert overdue_progress.short_id in message.body
    assert "Chưa gán" in message.body


def test_sla_reminder_runs_again_next_day():
    ManagerFactory(email="ql@example.com")
    _make_old()
    assert tasks.remind_overdue_tickets.run() == 1

    tomorrow = timezone.now() + timedelta(days=1)
    with mock.patch("apps.tickets.tasks.timezone.localdate", return_value=tomorrow.date()):
        assert tasks.remind_overdue_tickets.run() == 1

    assert len(mail.outbox) == 2


def test_sla_reminder_lists_at_most_limit(monkeypatch):
    monkeypatch.setattr(tasks, "REMINDER_LIST_LIMIT", 2)
    ManagerFactory(email="ql@example.com")
    for _ in range(3):
        _make_old()

    tasks.remind_overdue_tickets.run()

    assert "... và 1 ticket khác." in mail.outbox[0].body


@pytest.mark.parametrize("case", ["no_overdue", "no_manager_email"])
def test_sla_reminder_skips(caplog, case):
    caplog.set_level(logging.INFO, logger="apps.tickets.tasks")
    if case == "no_overdue":
        ManagerFactory(email="ql@example.com")
        TicketFactory()
    else:
        ManagerFactory(email="")
        _make_old()

    assert tasks.remind_overdue_tickets.run() == 0
    assert mail.outbox == []
    assert _events(caplog, "remind_overdue_tickets")[0].reason == case


def test_sla_reminder_smtp_error_releases_daily_key_for_retry():
    ManagerFactory(email="ql@example.com")
    _make_old()
    key = f"tickets:sla-reminder:{timezone.localdate().isoformat()}"

    with mock.patch("apps.tickets.tasks.send_mail", side_effect=SMTPException("down")):
        with pytest.raises(SMTPException):
            tasks.remind_overdue_tickets.run()
    assert cache.get(key) is None

    assert tasks.remind_overdue_tickets.run() == 1
    assert cache.get(key) == 1


def test_beat_schedule_runs_sla_reminder_daily_at_8():
    entry = settings.CELERY_BEAT_SCHEDULE["remind-overdue-tickets-daily"]

    assert entry["task"] == "apps.tickets.tasks.remind_overdue_tickets"
    assert entry["schedule"].hour == {8}
    assert entry["schedule"].minute == {0}
