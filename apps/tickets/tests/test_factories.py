import pytest

from apps.accounts.models import User
from apps.tickets.models import Ticket

from .factories import (
    AgentFactory,
    AttachmentFactory,
    CategoryFactory,
    CommentFactory,
    ManagerFactory,
    TicketFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


def test_user_factory_creates_user_with_usable_password():
    user = UserFactory()

    assert user.role == User.Role.CUSTOMER
    assert user.check_password("matkhau123")
    assert User.objects.filter(pk=user.pk).exists()


def test_role_factories_set_role_and_staff_flag():
    agent = AgentFactory()
    manager = ManagerFactory()

    assert agent.role == User.Role.AGENT
    assert manager.role == User.Role.MANAGER
    assert manager.is_staff


def test_get_or_create_reuses_same_username_and_category_name():
    assert UserFactory(username="trung") == UserFactory(username="trung")
    assert CategoryFactory(name="Mạng") == CategoryFactory(name="Mạng")


def test_ticket_factory_builds_related_objects():
    ticket = TicketFactory()

    assert ticket.status == Ticket.Status.NEW
    assert ticket.title
    assert ticket.category_id is not None
    assert ticket.created_by.role == User.Role.CUSTOMER
    assert ticket.assignee is None


def test_comment_and_attachment_factories_follow_ticket_owner():
    comment = CommentFactory()
    attachment = AttachmentFactory()

    assert comment.author == comment.ticket.created_by
    assert attachment.uploaded_by == attachment.ticket.created_by
    assert attachment.file.name.endswith(".png")
    attachment.file.delete(save=False)
