from smtplib import SMTPException

from celery import shared_task
from django.core.mail import send_mail

from .models import Comment, Ticket

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
