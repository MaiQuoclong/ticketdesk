from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User

from .models import Comment, Ticket, TicketHistory


class TicketServiceError(Exception):
    """Lỗi nghiệp vụ chung khi thao tác với Ticket."""


class TicketClosedError(TicketServiceError):
    """Lỗi khi thao tác trên Ticket đã đóng."""


@transaction.atomic
def assign_ticket(*, ticket: Ticket, agent: User, actor: User) -> Ticket:
    """Gán người xử lý cho ticket và ghi lại lịch sử thay đổi."""
    if ticket.status == Ticket.Status.CLOSED:
        raise TicketClosedError("Ticket đã đóng, không thể gán người xử lý.")
    if agent.role != User.Role.AGENT:
        raise TicketServiceError("Người được gán phải có vai trò Nhân viên hỗ trợ.")

    old_assignee = ticket.assignee.username if ticket.assignee else "Chưa gán"
    old_status = ticket.get_status_display()

    ticket.assignee = agent
    if ticket.status == Ticket.Status.NEW:
        ticket.status = Ticket.Status.IN_PROGRESS
    ticket.save(update_fields=["assignee", "status", "updated_at"])

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
    return ticket


@transaction.atomic
def change_ticket_status(*, ticket: Ticket, new_status: str, actor: User) -> Ticket:
    """Chuyển trạng thái ticket theo đúng quy tắc vòng đời và lưu lịch sử."""
    if ticket.status == Ticket.Status.CLOSED:
        raise TicketClosedError("Không thể chuyển trạng thái từ Đã đóng sang trạng thái khác.")

    if new_status not in Ticket.Status.values:
        raise TicketServiceError("Trạng thái không hợp lệ.")

    if ticket.status == new_status:
        return ticket

    old_display = ticket.get_status_display()
    ticket.status = new_status
    update_fields = ["status", "updated_at"]

    if new_status == Ticket.Status.RESOLVED and not ticket.resolved_at:
        ticket.resolved_at = timezone.now()
        update_fields.append("resolved_at")

    ticket.save(update_fields=update_fields)

    TicketHistory.objects.create(
        ticket=ticket,
        actor=actor,
        field="Trạng thái",
        old_value=old_display,
        new_value=ticket.get_status_display(),
    )
    return ticket


@transaction.atomic
def add_comment(
    *, ticket: Ticket, author: User, content: str, is_internal: bool = False
) -> Comment:
    """Thêm bình luận vào ticket (chỉ Agent/Manager mới được tạo ghi chú nội bộ)."""
    if ticket.status == Ticket.Status.CLOSED:
        raise TicketClosedError("Ticket đã đóng, không thể thêm bình luận mới.")

    internal_flag = is_internal if author.role in (User.Role.AGENT, User.Role.MANAGER) else False
    return Comment.objects.create(
        ticket=ticket,
        author=author,
        content=content.strip(),
        is_internal=internal_flag,
    )
