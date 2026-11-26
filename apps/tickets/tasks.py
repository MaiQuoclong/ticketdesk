from smtplib import SMTPException

from celery import shared_task
from django.core.cache import cache
from django.core.mail import send_mail
from django.utils import timezone

from apps.accounts.models import User

from . import selectors
from .models import Comment, Ticket

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


@shared_task(**RETRY_OPTIONS)
def notify_status_changed(
    ticket_id: str, old_status: str, new_status: str, actor_id: str | None = None
) -> int:
    """Gửi email cho người tạo ticket khi trạng thái ticket thay đổi."""
    ticket = Ticket.objects.select_related("created_by").filter(pk=ticket_id).first()
    if ticket is None:
        return 0
    owner = ticket.created_by
    if not owner.email or str(owner.pk) == actor_id:
        return 0
    return send_mail(
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


@shared_task(**RETRY_OPTIONS)
def notify_new_comment(comment_id: str) -> int:
    """Gửi email cho bên còn lại của ticket khi có bình luận công khai mới."""
    comment = (
        Comment.objects.select_related("ticket__created_by", "ticket__assignee", "author")
        .filter(pk=comment_id)
        .first()
    )
    if comment is None or comment.is_internal:
        return 0
    ticket = comment.ticket
    recipient = ticket.assignee if comment.author_id == ticket.created_by_id else ticket.created_by
    if recipient is None or not recipient.email or recipient.pk == comment.author_id:
        return 0
    return send_mail(
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
    if total == 0:
        return 0
    recipients = list(
        User.objects.filter(role=User.Role.MANAGER, is_active=True)
        .exclude(email="")
        .values_list("email", flat=True)
    )
    if not recipients:
        return 0

    key = f"tickets:sla-reminder:{timezone.localdate().isoformat()}"
    if not cache.add(key, 1, timeout=REMINDER_KEY_TTL):
        return 0
    try:
        return send_mail(
            subject=f"[TicketDesk] {total} ticket quá hạn SLA {hours} giờ",
            message=_reminder_body(list(overdue[:REMINDER_LIST_LIMIT]), total, hours),
            from_email=None,
            recipient_list=recipients,
        )
    except Exception:
        cache.delete(key)
        raise
