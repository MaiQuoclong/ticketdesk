import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.tickets.models import Category, Ticket
from apps.tickets.services import (
    TicketClosedError,
    add_comment,
    assign_ticket,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def sample_setup():
    cat = Category.objects.create(name="Phần mềm")
    customer1 = User.objects.create_user(
        username="khach01", password="123", role=User.Role.CUSTOMER
    )
    customer2 = User.objects.create_user(
        username="khach02", password="123", role=User.Role.CUSTOMER
    )
    agent = User.objects.create_user(username="agent01", password="123", role=User.Role.AGENT)
    manager = User.objects.create_user(username="quanly01", password="123", role=User.Role.MANAGER)
    t1 = Ticket.objects.create(
        title="Lỗi không mở được phần mềm",
        description="Chi tiết lỗi",
        category=cat,
        created_by=customer1,
    )
    t2 = Ticket.objects.create(
        title="Ticket của khách hàng 2",
        description="Chi tiết lỗi 2",
        category=cat,
        created_by=customer2,
    )
    return {
        "cat": cat,
        "customer1": customer1,
        "customer2": customer2,
        "agent": agent,
        "manager": manager,
        "t1": t1,
        "t2": t2,
    }


def test_customer_only_sees_own_tickets(client, sample_setup):
    client.force_login(sample_setup["customer1"])
    resp = client.get(reverse("tickets:list"))
    assert resp.status_code == 200
    tickets = list(resp.context["tickets"])
    assert tickets == [sample_setup["t1"]]


def test_customer_cannot_view_other_customer_ticket(client, sample_setup):
    client.force_login(sample_setup["customer1"])
    resp = client.get(reverse("tickets:detail", kwargs={"pk": sample_setup["t2"].pk}))
    assert resp.status_code == 404


def test_assign_ticket_updates_status_and_history(sample_setup):
    ticket = sample_setup["t1"]
    updated = assign_ticket(
        ticket=ticket,
        agent=sample_setup["agent"],
        actor=sample_setup["manager"],
    )
    assert updated.assignee == sample_setup["agent"]
    assert updated.status == Ticket.Status.IN_PROGRESS
    assert updated.histories.count() >= 1


def test_cannot_assign_closed_ticket(sample_setup):
    ticket = sample_setup["t1"]
    ticket.status = Ticket.Status.CLOSED
    ticket.save()
    with pytest.raises(TicketClosedError):
        assign_ticket(
            ticket=ticket,
            agent=sample_setup["agent"],
            actor=sample_setup["manager"],
        )


def test_internal_comment_hidden_from_customer(client, sample_setup):
    ticket = sample_setup["t1"]
    add_comment(
        ticket=ticket,
        author=sample_setup["agent"],
        content="Ghi chú mật nội bộ",
        is_internal=True,
    )
    client.force_login(sample_setup["customer1"])
    resp = client.get(reverse("tickets:detail", kwargs={"pk": ticket.pk}))
    assert resp.status_code == 200
    assert len(resp.context["comments"]) == 0
