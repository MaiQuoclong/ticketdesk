import logging
from typing import Any
from uuid import uuid4

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User

from .models import Comment, Ticket, TicketHistory
from .tasks import notify_new_comment, notify_status_changed, send_webhook

logger = logging.getLogger(__name__)


class TicketServiceError(Exception):
    """Lỗi nghiệp vụ chung khi thao tác với Ticket."""


class TicketClosedError(TicketServiceError):
    """Lỗi khi thao tác trên Ticket đã đóng."""


def _lock(ticket: Ticket) -> Ticket:
    """Khoá dòng ticket tới hết transaction để hai request đồng thời không ghi đè nhau."""
    return Ticket.objects.select_for_update().get(pk=ticket.pk)


def _sync(target: Ticket, source: Ticket, fields: list[str]) -> None:
    for field in fields:
        setattr(target, field, getattr(source, field))


def _enqueue(task: Any, *args: str) -> None:
    def send() -> None:
        try:
            task.delay(*args)
        except Exception:
            logger.exception(
                "Không đưa được tác vụ vào hàng đợi",
                extra={"event": "enqueue_failed", "task": task.name},
            )

    transaction.on_commit(send)


def _queue_status_email(ticket: Ticket, old_status: str, actor: User) -> None:
    _enqueue(notify_status_changed, str(ticket.pk), old_status, ticket.status, str(actor.pk))
    if settings.WEBHOOK_URL:
        _enqueue(
            send_webhook,
            "ticket.status_changed",
            str(ticket.pk),
            uuid4().hex,
            old_status,
            ticket.status,
            str(actor.pk),
        )


@transaction.atomic
def assign_ticket(*, ticket: Ticket, agent: User, actor: User) -> Ticket:
    """Gán người xử lý cho ticket và ghi lại lịch sử thay đổi."""
    original, ticket = ticket, _lock(ticket)
    if ticket.status == Ticket.Status.CLOSED:
        raise TicketClosedError("Ticket đã đóng, không thể gán người xử lý.")
    if agent.role != User.Role.AGENT:
        raise TicketServiceError("Người được gán phải có vai trò Nhân viên hỗ trợ.")

    old_assignee = ticket.assignee.username if ticket.assignee else "Chưa gán"
    old_status_value = ticket.status
    old_status = ticket.get_status_display()

    ticket.assignee = agent
    if ticket.status == Ticket.Status.NEW:
        ticket.status = Ticket.Status.IN_PROGRESS
    ticket.save(update_fields=["assignee", "status", "updated_at"])
    _sync(original, ticket, ["assignee", "status", "updated_at"])

    TicketHistory.objects.create(
        ticket=ticket,
        actor=actor,
        field="Người xử lý",
        old_value=old_assignee,
        new_value=agent.username,
    )
    if old_status != ticket.get_status_display():
        TicketHistory.objects.create(
            ticket=ticket,
            actor=actor,
            field="Trạng thái",
            old_value=old_status,
            new_value=ticket.get_status_display(),
        )
        _queue_status_email(ticket, old_status_value, actor)
    return original


@transaction.atomic
def change_ticket_status(*, ticket: Ticket, new_status: str, actor: User) -> Ticket:
    """Chuyển trạng thái ticket theo đúng quy tắc vòng đời và lưu lịch sử."""
    original, ticket = ticket, _lock(ticket)
    if ticket.status == Ticket.Status.CLOSED:
        raise TicketClosedError("Không thể chuyển trạng thái từ Đã đóng sang trạng thái khác.")

    if new_status not in Ticket.Status.values:
        raise TicketServiceError("Trạng thái không hợp lệ.")

    if ticket.status == new_status:
        return original

    old_status_value = ticket.status
    old_display = ticket.get_status_display()
    ticket.status = new_status
    update_fields = ["status", "updated_at"]

    if new_status == Ticket.Status.RESOLVED and not ticket.resolved_at:
        ticket.resolved_at = timezone.now()
        update_fields.append("resolved_at")

    ticket.save(update_fields=update_fields)
    _sync(original, ticket, ["status", "resolved_at", "updated_at"])

    TicketHistory.objects.create(
        ticket=ticket,
        actor=actor,
        field="Trạng thái",
        old_value=old_display,
        new_value=ticket.get_status_display(),
    )
    _queue_status_email(ticket, old_status_value, actor)
    return original


@transaction.atomic
def add_comment(
    *, ticket: Ticket, author: User, content: str, is_internal: bool = False
) -> Comment:
    """Thêm bình luận vào ticket (chỉ Agent/Manager mới được tạo ghi chú nội bộ)."""
    ticket = _lock(ticket)
    if ticket.status == Ticket.Status.CLOSED:
        raise TicketClosedError("Ticket đã đóng, không thể thêm bình luận mới.")

    internal_flag = is_internal if author.role in (User.Role.AGENT, User.Role.MANAGER) else False
    comment = Comment.objects.create(
        ticket=ticket,
        author=author,
        content=content.strip(),
        is_internal=internal_flag,
    )
    if not comment.is_internal:
        _enqueue(notify_new_comment, str(comment.pk))
    return comment
