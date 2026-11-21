from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.utils import timezone

from apps.accounts.models import RefreshToken, User
from apps.tickets.models import Category, Comment, Ticket, TicketHistory

from .factories import (
    AgentFactory,
    AttachmentFactory,
    CategoryFactory,
    CommentFactory,
    CustomerFactory,
    TicketFactory,
)

pytestmark = pytest.mark.django_db


def test_ticket_defaults_to_new_status_and_medium_priority():
    ticket = TicketFactory()

    assert ticket.status == Ticket.Status.NEW
    assert ticket.priority == Ticket.Priority.MEDIUM
    assert ticket.resolved_at is None


def test_ticket_with_empty_title_violates_check_constraint():
    ticket = TicketFactory.build(title="")
    ticket.category = CategoryFactory()
    ticket.created_by = CustomerFactory()

    with pytest.raises(IntegrityError), transaction.atomic():
        ticket.save()


def test_ticket_with_invalid_priority_violates_check_constraint():
    ticket = TicketFactory()

    with pytest.raises(IntegrityError), transaction.atomic():
        Ticket.objects.filter(pk=ticket.pk).update(priority=9)


def test_ticket_str_contains_short_id_and_title():
    ticket = TicketFactory(title="Máy in hỏng")

    assert ticket.short_id == f"TD-{str(ticket.pk)[:6].upper()}"
    assert str(ticket) == f"#{ticket.short_id} Máy in hỏng"


def test_tickets_are_ordered_newest_first():
    old = TicketFactory()
    new = TicketFactory()
    Ticket.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=1))

    assert list(Ticket.objects.all()) == [new, old]


def test_deleting_category_in_use_is_protected():
    ticket = TicketFactory()

    with pytest.raises(ProtectedError):
        ticket.category.delete()

    assert Category.objects.filter(pk=ticket.category_id).exists()


def test_deleting_assignee_keeps_ticket_and_clears_assignee():
    agent = AgentFactory()
    ticket = TicketFactory(assignee=agent, status=Ticket.Status.IN_PROGRESS)

    agent.delete()
    ticket.refresh_from_db()

    assert ticket.assignee is None


def test_deleting_ticket_owner_cascades_to_tickets_and_comments():
    ticket = TicketFactory()
    CommentFactory(ticket=ticket)
    owner = ticket.created_by

    owner.delete()

    assert not Ticket.objects.filter(pk=ticket.pk).exists()
    assert not Comment.objects.filter(ticket_id=ticket.pk).exists()


def test_deleting_uploader_keeps_attachment():
    attachment = AttachmentFactory(uploaded_by=AgentFactory())

    attachment.uploaded_by.delete()
    attachment.refresh_from_db()

    assert attachment.uploaded_by is None
    attachment.file.delete(save=False)


def test_comments_are_ordered_oldest_first():
    ticket = TicketFactory()
    first = CommentFactory(ticket=ticket)
    second = CommentFactory(ticket=ticket)
    Comment.objects.filter(pk=second.pk).update(created_at=timezone.now() + timedelta(minutes=1))

    assert list(ticket.comments.all()) == [first, second]


def test_comment_defaults_to_public():
    assert CommentFactory().is_internal is False


def test_category_name_must_be_unique():
    Category.objects.create(name="Phần mềm")

    with pytest.raises(IntegrityError), transaction.atomic():
        Category.objects.create(name="Phần mềm")


def test_str_of_category_attachment_comment_and_history():
    ticket = TicketFactory(category=CategoryFactory(name="Mạng"))
    comment = CommentFactory(ticket=ticket)
    attachment = AttachmentFactory(ticket=ticket, original_name="loi.png")
    history = TicketHistory.objects.create(
        ticket=ticket, actor=ticket.created_by, field="status", old_value="new", new_value="closed"
    )

    assert str(ticket.category) == "Mạng"
    assert str(attachment) == "loi.png"
    assert str(comment) == f"Bình luận của {comment.author} trên {ticket.short_id}"
    assert str(history) == f"{ticket.short_id}: status (new -> closed)"
    attachment.file.delete(save=False)


def test_user_defaults_to_customer_and_str_shows_role():
    user = User.objects.create_user("khachmoi", password="matkhau123")

    assert user.role == User.Role.CUSTOMER
    assert str(user) == "khachmoi (Khách hàng)"


def test_refresh_token_str_shows_revoked_state():
    token = RefreshToken.objects.create(
        user=CustomerFactory(username="khachtoken"),
        token="abc",
        expires_at=timezone.now() + timedelta(days=7),
    )

    assert str(token) == "khachtoken (Hợp lệ)"
    token.is_revoked = True
    assert str(token) == "khachtoken (Đã thu hồi)"
