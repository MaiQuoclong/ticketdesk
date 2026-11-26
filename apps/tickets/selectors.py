import logging
import time
from datetime import date, timedelta
from typing import Any

from django.core.cache import cache
from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q, QuerySet
from django.utils import timezone

from apps.accounts.models import User

from .models import Category, Ticket

OVERDUE_AFTER = timedelta(days=3)
OPEN_STATUSES = [Ticket.Status.NEW, Ticket.Status.IN_PROGRESS]
SLA_HOURS = 24
STATS_CACHE_KEY = "tickets:dashboard-stats"
STATS_CACHE_TIMEOUT = 300
CACHE_RETRY_AFTER = 30
_cache_state = {"down_until": 0.0}

logger = logging.getLogger(__name__)


def tickets_created_between(date_from: date, date_to: date) -> QuerySet[Ticket]:
    """Ticket tạo trong khoảng ngày [date_from, date_to] theo giờ địa phương."""
    return (
        Ticket.objects.select_related("created_by", "assignee", "category")
        .filter(created_at__date__gte=date_from, created_at__date__lte=date_to)
        .order_by("created_at")
    )


def sla_overdue_tickets(hours: int = SLA_HOURS) -> QuerySet[Ticket]:
    """Ticket còn mở (Mới / Đang xử lý) đã tạo quá số giờ SLA, cũ nhất lên trước."""
    cutoff = timezone.now() - timedelta(hours=hours)
    return (
        Ticket.objects.select_related("created_by", "assignee", "category")
        .filter(status__in=OPEN_STATUSES, created_at__lt=cutoff)
        .order_by("created_at")
    )


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


def agent_workload() -> list[Any]:
    resolve_time = ExpressionWrapper(
        F("assigned_tickets__resolved_at") - F("assigned_tickets__created_at"),
        output_field=DurationField(),
    )
    agents: list[Any] = list(
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


def compute_dashboard_stats() -> dict[str, Any]:
    """Toàn bộ số liệu thống kê dưới dạng dict/list thuần để lưu được vào cache."""
    summary = ticket_summary()
    total = summary["total"]
    return {
        "summary": summary,
        "by_status": tickets_by_status(total),
        "by_priority": tickets_by_priority(total),
        "by_category": [
            {
                "id": str(cat.pk),
                "name": cat.name,
                "total": getattr(cat, "total", 0),
                "open": getattr(cat, "open", 0),
            }
            for cat in tickets_by_category()
        ],
        "agents": [
            {
                "id": str(agent.pk),
                "username": agent.username,
                "total": agent.total,
                "in_progress": agent.in_progress,
                "resolved": agent.resolved,
                "closed": agent.closed,
                "avg_resolve_display": agent.avg_resolve_display,
            }
            for agent in agent_workload()
        ],
    }


def _cache_available() -> bool:
    return time.monotonic() >= _cache_state["down_until"]


def _mark_cache_down(action: str) -> None:
    _cache_state["down_until"] = time.monotonic() + CACHE_RETRY_AFTER
    logger.warning(
        "Cache lỗi, tạm bỏ qua cache",
        extra={"event": "cache_down", "action": action, "retry_after": CACHE_RETRY_AFTER},
        exc_info=True,
    )


def dashboard_stats() -> dict[str, Any]:
    """Thống kê dashboard lấy từ cache (5 phút); cache lỗi thì tính trực tiếp từ CSDL."""
    if not _cache_available():
        return compute_dashboard_stats()
    try:
        stats = cache.get_or_set(STATS_CACHE_KEY, compute_dashboard_stats, STATS_CACHE_TIMEOUT)
    except Exception:
        _mark_cache_down("đọc thống kê")
        return compute_dashboard_stats()
    return stats if isinstance(stats, dict) else compute_dashboard_stats()


def invalidate_stats() -> None:
    try:
        cache.delete(STATS_CACHE_KEY)
    except Exception:
        _mark_cache_down("xoá thống kê")
