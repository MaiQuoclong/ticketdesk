from datetime import timedelta

from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q, QuerySet
from django.utils import timezone

from apps.accounts.models import User

from .models import Category, Ticket

OVERDUE_AFTER = timedelta(days=3)
OPEN_STATUSES = [Ticket.Status.NEW, Ticket.Status.IN_PROGRESS]


def ticket_summary() -> dict:
    overdue_before = timezone.now() - OVERDUE_AFTER
    summary = Ticket.objects.aggregate(
        total=Count("id"),
        new=Count("id", filter=Q(status=Ticket.Status.NEW)),
        in_progress=Count("id", filter=Q(status=Ticket.Status.IN_PROGRESS)),
        resolved=Count("id", filter=Q(status=Ticket.Status.RESOLVED)),
        closed=Count("id", filter=Q(status=Ticket.Status.CLOSED)),
        unassigned=Count("id", filter=Q(assignee__isnull=True, status__in=OPEN_STATUSES)),
        overdue=Count("id", filter=Q(status=Ticket.Status.NEW, created_at__lt=overdue_before)),
        high_open=Count("id", filter=Q(priority=Ticket.Priority.HIGH, status__in=OPEN_STATUSES)),
    )
    done = summary["resolved"] + summary["closed"]
    summary["done_pct"] = round(done * 100 / summary["total"]) if summary["total"] else 0
    return summary


def _with_pct(rows: list[dict], total: int) -> list[dict]:
    for row in rows:
        row["pct"] = round(row["total"] * 100 / total) if total else 0
    return rows


def tickets_by_status(total: int) -> list[dict]:
    labels = dict(Ticket.Status.choices)
    rows = Ticket.objects.values("status").annotate(total=Count("id")).order_by("-total")
    return _with_pct([{**r, "label": labels[r["status"]]} for r in rows], total)


def tickets_by_priority(total: int) -> list[dict]:
    labels = dict(Ticket.Priority.choices)
    rows = Ticket.objects.values("priority").annotate(total=Count("id")).order_by("-priority")
    return _with_pct([{**r, "label": labels[r["priority"]]} for r in rows], total)


def tickets_by_category() -> QuerySet[Category]:
    return Category.objects.annotate(
        total=Count("tickets"),
        open=Count("tickets", filter=Q(tickets__status__in=OPEN_STATUSES)),
    ).order_by("-total")


def format_duration(value: timedelta | None) -> str:
    if value is None:
        return "—"
    hours = int(value.total_seconds() // 3600)
    days, hours = divmod(hours, 24)
    if days:
        return f"{days} ngày {hours} giờ"
    return f"{hours} giờ" if hours else "< 1 giờ"


def agent_workload() -> list[User]:
    resolve_time = ExpressionWrapper(
        F("assigned_tickets__resolved_at") - F("assigned_tickets__created_at"),
        output_field=DurationField(),
    )
    agents = list(
        User.objects.filter(role=User.Role.AGENT)
        .annotate(
            total=Count("assigned_tickets"),
            in_progress=Count(
                "assigned_tickets",
                filter=Q(assigned_tickets__status=Ticket.Status.IN_PROGRESS),
            ),
            resolved=Count(
                "assigned_tickets", filter=Q(assigned_tickets__status=Ticket.Status.RESOLVED)
            ),
            closed=Count(
                "assigned_tickets", filter=Q(assigned_tickets__status=Ticket.Status.CLOSED)
            ),
            avg_resolve=Avg(resolve_time),
        )
        .order_by("-in_progress", "username")
    )
    for agent in agents:
        agent.avg_resolve_display = format_duration(agent.avg_resolve)
    return agents
