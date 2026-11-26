import logging
from datetime import date
from smtplib import SMTPException
from typing import Any
from uuid import uuid4

from celery import shared_task
from celery.signals import task_failure, task_retry
from django.core.cache import cache
from django.core.mail import send_mail
from django.utils import timezone

from apps.accounts.models import User

from . import reports, selectors
from .models import Comment, Ticket

logger = logging.getLogger(__name__)

REMINDER_LIST_LIMIT = 50
REMINDER_KEY_TTL = 2 * 24 * 3600

RETRY_OPTIONS = {
    "autoretry_for": (SMTPException, OSError),
    "retry_backoff": 30,
    "retry_backoff_max": 600,
    "retry_jitter": True,
    "max_retries": 5,
    "ignore_result": True,
}


def _label(status: str) -> str:
    return str(Ticket.Status(status).label) if status in Ticket.Status.values else status


def _skip(event: str, reason: str, **fields: Any) -> int:
    logger.info("Bỏ qua gửi email", extra={"event": event, "reason": reason, **fields})
    return 0


def _sent(event: str, count: int, **fields: Any) -> int:
    logger.info("Đã gửi email", extra={"event": event, "sent": count, **fields})
    return count


@task_retry.connect
def _log_task_retry(sender: Any = None, request: Any = None, reason: Any = None, **_: Any) -> None:
    logger.warning(
        "Tác vụ thất bại, sẽ thử lại",
        extra={
            "task": getattr(sender, "name", None),
            "task_id": getattr(request, "id", None),
            "retries": getattr(request, "retries", None),
            "error": type(reason).__name__,
        },
    )


@task_failure.connect
def _log_task_failure(
    sender: Any = None, task_id: str | None = None, exception: BaseException | None = None, **_: Any
) -> None:
    logger.error(
        "Tác vụ thất bại hẳn",
        extra={
            "task": getattr(sender, "name", None),
            "task_id": task_id,
            "error": type(exception).__name__,
        },
    )


@shared_task(**RETRY_OPTIONS)
def notify_status_changed(
    ticket_id: str, old_status: str, new_status: str, actor_id: str | None = None
) -> int:
    """Gửi email cho người tạo ticket khi trạng thái ticket thay đổi."""
    ticket = Ticket.objects.select_related("created_by").filter(pk=ticket_id).first()
    event = "notify_status_changed"
    if ticket is None:
        return _skip(event, "ticket_not_found", ticket_id=ticket_id)
    owner = ticket.created_by
    if not owner.email:
        return _skip(event, "no_email", ticket_id=ticket_id)
    if str(owner.pk) == actor_id:
        return _skip(event, "actor_is_owner", ticket_id=ticket_id)
    count = send_mail(
        subject=f"[TicketDesk] #{ticket.short_id} chuyển sang {_label(new_status)}",
        message=(
            f"Xin chào {owner.get_full_name() or owner.username},\n\n"
            f'Ticket #{ticket.short_id} "{ticket.title}" đã chuyển trạng thái '
            f"từ {_label(old_status)} sang {_label(new_status)}.\n\n"
            "TicketDesk"
        ),
        from_email=None,
        recipient_list=[owner.email],
    )
    return _sent(event, count, ticket_id=ticket_id, new_status=new_status)


@shared_task(**RETRY_OPTIONS)
def notify_new_comment(comment_id: str) -> int:
    """Gửi email cho bên còn lại của ticket khi có bình luận công khai mới."""
    comment = (
        Comment.objects.select_related("ticket__created_by", "ticket__assignee", "author")
        .filter(pk=comment_id)
        .first()
    )
    event = "notify_new_comment"
    if comment is None:
        return _skip(event, "comment_not_found", comment_id=comment_id)
    if comment.is_internal:
        return _skip(event, "internal_note", comment_id=comment_id)
    ticket = comment.ticket
    recipient = ticket.assignee if comment.author_id == ticket.created_by_id else ticket.created_by
    if recipient is None or recipient.pk == comment.author_id:
        return _skip(event, "no_recipient", comment_id=comment_id)
    if not recipient.email:
        return _skip(event, "no_email", comment_id=comment_id)
    count = send_mail(
        subject=f"[TicketDesk] Bình luận mới trên #{ticket.short_id}",
        message=(
            f"Xin chào {recipient.get_full_name() or recipient.username},\n\n"
            f"{comment.author.username} vừa bình luận trên ticket #{ticket.short_id} "
            f'"{ticket.title}":\n\n{comment.content}\n\n'
            "TicketDesk"
        ),
        from_email=None,
        recipient_list=[recipient.email],
    )
    return _sent(event, count, comment_id=comment_id, ticket_id=str(ticket.pk))


def _reminder_body(tickets: list[Ticket], total: int, hours: int) -> str:
    now = timezone.now()
    lines = [
        f"Hiện có {total} ticket còn mở quá {hours} giờ chưa được xử lý xong:",
        "",
    ]
    for ticket in tickets:
        age_hours = int((now - ticket.created_at).total_seconds() // 3600)
        assignee = ticket.assignee.username if ticket.assignee else "Chưa gán"
        lines.append(
            f"- #{ticket.short_id} [{ticket.get_status_display()}] {ticket.title} "
            f"— {age_hours} giờ — người xử lý: {assignee}"
        )
    if total > len(tickets):
        lines.append(f"... và {total - len(tickets)} ticket khác.")
    lines += ["", "TicketDesk"]
    return "\n".join(lines)


@shared_task(**RETRY_OPTIONS)
def remind_overdue_tickets(hours: int = selectors.SLA_HOURS) -> int:
    """Gửi một email tổng hợp ticket quá hạn SLA cho Manager, tối đa một lần mỗi ngày."""
    overdue = selectors.sla_overdue_tickets(hours)
    total = overdue.count()
    event = "remind_overdue_tickets"
    if total == 0:
        return _skip(event, "no_overdue", hours=hours)
    recipients = list(
        User.objects.filter(role=User.Role.MANAGER, is_active=True)
        .exclude(email="")
        .values_list("email", flat=True)
    )
    if not recipients:
        return _skip(event, "no_manager_email", overdue=total)

    key = f"tickets:sla-reminder:{timezone.localdate().isoformat()}"
    if not cache.add(key, 1, timeout=REMINDER_KEY_TTL):
        return _skip(event, "already_sent_today", overdue=total)
    try:
        count = send_mail(
            subject=f"[TicketDesk] {total} ticket quá hạn SLA {hours} giờ",
            message=_reminder_body(list(overdue[:REMINDER_LIST_LIMIT]), total, hours),
            from_email=None,
            recipient_list=recipients,
        )
    except Exception:
        cache.delete(key)
        raise
    return _sent(event, count, overdue=total, recipients=len(recipients))


@shared_task(bind=True)
def export_tickets_report(self, user_id: str, date_from: str, date_to: str) -> dict:
    """Xuất ticket tạo trong khoảng ngày ra tệp Excel trong MEDIA_ROOT/reports/."""
    start, end = date.fromisoformat(date_from), date.fromisoformat(date_to)
    task_id = self.request.id or uuid4().hex
    name = f"tickets_{start:%Y%m%d}_{end:%Y%m%d}_{task_id[:8]}.xlsx"
    _, rows = reports.build_tickets_report(start, end, name)
    logger.info(
        "Đã xuất báo cáo Excel",
        extra={"event": "export_tickets_report", "task_id": task_id, "rows": rows, "file": name},
    )
    return {"file": name, "rows": rows, "user_id": user_id}
