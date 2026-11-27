import hashlib
import hmac
import json
import logging
from datetime import date
from smtplib import SMTPException
from typing import Any
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError
from uuid import uuid4

from celery import shared_task
from celery.signals import task_failure, task_retry
from django.conf import settings
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


WEBHOOK_SENT_TTL = 7 * 24 * 3600
WEBHOOK_SIGNATURE_HEADER = "X-TicketDesk-Signature"


class WebhookServerError(Exception):
    """Máy nhận webhook trả lỗi 5xx, cần thử lại."""


def webhook_signature(body: bytes, secret: str) -> str:
    """Chữ ký HMAC-SHA256 của thân request, dạng sha256=<hex>."""
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _webhook_payload(
    event: str,
    event_id: str,
    ticket: Ticket,
    old_status: str,
    new_status: str,
    actor_id: str | None,
) -> dict[str, Any]:
    return {
        "event": event,
        "event_id": event_id,
        "occurred_at": timezone.now().isoformat(),
        "ticket": {
            "id": str(ticket.pk),
            "short_id": ticket.short_id,
            "title": ticket.title,
            "old_status": old_status,
            "new_status": new_status,
            "assignee_id": str(ticket.assignee_id) if ticket.assignee_id else None,
        },
        "actor_id": actor_id,
    }


@shared_task(
    autoretry_for=(WebhookServerError, URLError, TimeoutError),
    retry_backoff=30,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=5,
    ignore_result=True,
)
def send_webhook(
    event: str,
    ticket_id: str,
    event_id: str,
    old_status: str,
    new_status: str,
    actor_id: str | None = None,
) -> int:
    """POST sự kiện ticket tới WEBHOOK_URL, ký HMAC-SHA256, mỗi event_id chỉ gửi một lần."""
    url = settings.WEBHOOK_URL
    if not url:
        return 0
    log = {"event": "send_webhook", "webhook_event": event, "event_id": event_id}
    key = f"tickets:webhook-sent:{event_id}"
    if cache.get(key):
        logger.info("Bỏ qua webhook đã gửi", extra={**log, "reason": "already_sent"})
        return 0
    ticket = Ticket.objects.filter(pk=ticket_id).first()
    if ticket is None:
        logger.info("Bỏ qua webhook", extra={**log, "reason": "ticket_not_found"})
        return 0

    payload = _webhook_payload(event, event_id, ticket, old_status, new_status, actor_id)
    body = json.dumps(payload, ensure_ascii=False).encode()
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "TicketDesk-Webhook/1.0",
        "X-TicketDesk-Event": event,
        "X-TicketDesk-Event-Id": event_id,
    }
    if settings.WEBHOOK_SECRET:
        headers[WEBHOOK_SIGNATURE_HEADER] = webhook_signature(body, settings.WEBHOOK_SECRET)
    req = urllib_request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib_request.urlopen(req, timeout=settings.WEBHOOK_TIMEOUT) as response:
            status = response.status
    except HTTPError as error:
        if error.code >= 500:
            raise WebhookServerError(f"HTTP {error.code}") from error
        logger.warning("Webhook bị từ chối, không thử lại", extra={**log, "status": error.code})
        return 0

    cache.set(key, 1, timeout=WEBHOOK_SENT_TTL)
    logger.info("Đã gửi webhook", extra={**log, "status": status})
    return 1
