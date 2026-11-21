import pytest

from apps.tickets.models import Ticket, TicketHistory
from apps.tickets.services import (
    TicketClosedError,
    TicketServiceError,
    add_comment,
    assign_ticket,
    change_ticket_status,
)

from .factories import AgentFactory, CustomerFactory, ManagerFactory, TicketFactory

pytestmark = pytest.mark.django_db


def test_assign_ticket_sets_agent_and_moves_new_ticket_to_in_progress():
    ticket = TicketFactory()
    agent = AgentFactory()

    result = assign_ticket(ticket=ticket, agent=agent, actor=ManagerFactory())

    ticket.refresh_from_db()
    assert result.assignee == agent
    assert ticket.assignee == agent
    assert ticket.status == Ticket.Status.IN_PROGRESS


def test_assign_ticket_records_assignee_and_status_history():
    ticket = TicketFactory()
    agent = AgentFactory()
    manager = ManagerFactory()

    assign_ticket(ticket=ticket, agent=agent, actor=manager)

    histories = TicketHistory.objects.filter(ticket=ticket)
    assert {h.field for h in histories} == {"Người xử lý", "Trạng thái"}
    assert histories.get(field="Người xử lý").new_value == agent.username
    assert all(h.actor == manager for h in histories)


def test_reassign_in_progress_ticket_keeps_status_and_logs_only_assignee():
    first, second = AgentFactory(), AgentFactory()
    ticket = TicketFactory(assignee=first, status=Ticket.Status.IN_PROGRESS)

    assign_ticket(ticket=ticket, agent=second, actor=ManagerFactory())

    history = TicketHistory.objects.get(ticket=ticket)
    assert ticket.status == Ticket.Status.IN_PROGRESS
    assert history.old_value == first.username
    assert history.new_value == second.username


def test_cannot_assign_closed_ticket():
    ticket = TicketFactory(status=Ticket.Status.CLOSED)

    with pytest.raises(TicketClosedError):
        assign_ticket(ticket=ticket, agent=AgentFactory(), actor=ManagerFactory())

    ticket.refresh_from_db()
    assert ticket.assignee is None
    assert not TicketHistory.objects.filter(ticket=ticket).exists()


def test_cannot_assign_ticket_to_non_agent():
    ticket = TicketFactory()

    with pytest.raises(TicketServiceError):
        assign_ticket(ticket=ticket, agent=CustomerFactory(), actor=ManagerFactory())


def test_resolve_ticket_sets_resolved_at_and_logs_history():
    ticket = TicketFactory(status=Ticket.Status.IN_PROGRESS)

    change_ticket_status(ticket=ticket, new_status=Ticket.Status.RESOLVED, actor=AgentFactory())

    ticket.refresh_from_db()
    history = TicketHistory.objects.get(ticket=ticket)
    assert ticket.status == Ticket.Status.RESOLVED
    assert ticket.resolved_at is not None
    assert (history.old_value, history.new_value) == ("Đang xử lý", "Đã xử lý")


def test_resolving_again_keeps_original_resolved_at():
    ticket = TicketFactory(status=Ticket.Status.IN_PROGRESS)
    change_ticket_status(ticket=ticket, new_status=Ticket.Status.RESOLVED, actor=AgentFactory())
    first_resolved_at = ticket.resolved_at

    change_ticket_status(ticket=ticket, new_status=Ticket.Status.IN_PROGRESS, actor=AgentFactory())
    change_ticket_status(ticket=ticket, new_status=Ticket.Status.RESOLVED, actor=AgentFactory())

    ticket.refresh_from_db()
    assert ticket.resolved_at == first_resolved_at


def test_change_to_same_status_does_nothing():
    ticket = TicketFactory()

    change_ticket_status(ticket=ticket, new_status=Ticket.Status.NEW, actor=AgentFactory())

    assert not TicketHistory.objects.filter(ticket=ticket).exists()


def test_change_to_invalid_status_raises_error():
    ticket = TicketFactory()

    with pytest.raises(TicketServiceError):
        change_ticket_status(ticket=ticket, new_status="bogus", actor=AgentFactory())


def test_closed_ticket_cannot_change_status():
    ticket = TicketFactory(status=Ticket.Status.CLOSED)

    with pytest.raises(TicketClosedError):
        change_ticket_status(ticket=ticket, new_status=Ticket.Status.NEW, actor=ManagerFactory())


def test_add_comment_strips_content():
    ticket = TicketFactory()

    comment = add_comment(ticket=ticket, author=ticket.created_by, content="  Máy vẫn lỗi  ")

    assert comment.content == "Máy vẫn lỗi"
    assert comment.ticket == ticket


def test_customer_cannot_create_internal_note():
    ticket = TicketFactory()

    comment = add_comment(
        ticket=ticket, author=ticket.created_by, content="Ghi chú", is_internal=True
    )

    assert comment.is_internal is False


def test_agent_can_create_internal_note():
    ticket = TicketFactory()

    comment = add_comment(ticket=ticket, author=AgentFactory(), content="Nội bộ", is_internal=True)

    assert comment.is_internal is True


def test_cannot_comment_on_closed_ticket():
    ticket = TicketFactory(status=Ticket.Status.CLOSED)

    with pytest.raises(TicketClosedError):
        add_comment(ticket=ticket, author=ticket.created_by, content="Còn lỗi")

    assert not ticket.comments.exists()
