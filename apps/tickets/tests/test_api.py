from datetime import timedelta
from typing import Any

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.models import RefreshToken
from apps.tickets.models import Category, Ticket, TicketHistory

from .factories import (
    AgentFactory,
    AttachmentFactory,
    CategoryFactory,
    CommentFactory,
    CustomerFactory,
    ManagerFactory,
    TicketFactory,
)

pytestmark = pytest.mark.django_db

TICKETS = "/api/v1/tickets/"


@pytest.fixture
def api() -> Any:
    return APIClient()


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


def login(api, user) -> dict:
    resp = api.post(
        "/api/v1/auth/login/", {"username": user.username, "password": "matkhau123"}, format="json"
    )
    assert resp.status_code == 200
    return resp.data


def test_login_with_valid_credentials_returns_tokens_and_role(api):
    customer = CustomerFactory()

    data = login(api, customer)

    assert data["access"] and data["refresh"]
    assert data["user"]["role"] == "customer"


@pytest.mark.parametrize("username", ["khachsai", "khongtontai"])
def test_login_with_wrong_password_or_unknown_user_returns_401(api, username):
    CustomerFactory(username="khachsai")

    resp = api.post("/api/v1/auth/login/", {"username": username, "password": "sai"}, format="json")

    assert resp.status_code == 401
    assert resp.data["code"] == "invalid_credentials"


def test_login_of_inactive_user_returns_401(api):
    user = CustomerFactory(is_active=False)

    resp = api.post(
        "/api/v1/auth/login/", {"username": user.username, "password": "matkhau123"}, format="json"
    )

    assert resp.status_code == 401


def test_bearer_token_gives_access_to_ticket_list(api):
    customer = CustomerFactory()
    TicketFactory(created_by=customer)
    access = login(api, customer)["access"]
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    resp = api.get(TICKETS)

    assert resp.status_code == 200
    assert resp.data["count"] == 1


def test_ticket_list_without_token_returns_401(api):
    assert api.get(TICKETS).status_code == 401


def test_expired_access_token_returns_401(api):
    token = AccessToken.for_user(CustomerFactory())
    token.set_exp(lifetime=-timedelta(minutes=1))
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    resp = api.get(TICKETS)

    assert resp.status_code == 401
    assert "results" not in resp.data


def test_garbage_bearer_token_returns_401(api):
    api.credentials(HTTP_AUTHORIZATION="Bearer abc.def.ghi")

    assert api.get(TICKETS).status_code == 401


def test_refresh_returns_new_access_token(api):
    refresh = login(api, CustomerFactory())["refresh"]

    resp = api.post("/api/v1/auth/refresh/", {"refresh": refresh}, format="json")

    assert resp.status_code == 200
    assert resp.data["access"]


def test_refresh_with_revoked_token_returns_401(api):
    refresh = login(api, CustomerFactory())["refresh"]
    RefreshToken.objects.filter(token=refresh).update(is_revoked=True)

    resp = api.post("/api/v1/auth/refresh/", {"refresh": refresh}, format="json")

    assert resp.status_code == 401
    assert resp.data["code"] == "token_revoked"


def test_refresh_with_expired_record_returns_401(api):
    refresh = login(api, CustomerFactory())["refresh"]
    RefreshToken.objects.filter(token=refresh).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )

    resp = api.post("/api/v1/auth/refresh/", {"refresh": refresh}, format="json")

    assert resp.status_code == 401


def test_refresh_with_invalid_string_returns_401(api):
    resp = api.post("/api/v1/auth/refresh/", {"refresh": "khong-hop-le"}, format="json")

    assert resp.status_code == 401
    assert resp.data["code"] == "token_not_valid"


def test_refresh_without_body_returns_400(api):
    assert api.post("/api/v1/auth/refresh/", {}, format="json").status_code == 400


def test_logout_revokes_refresh_token(api):
    customer = CustomerFactory()
    tokens = login(api, customer)
    api.force_authenticate(customer)

    resp = api.post("/api/v1/auth/logout/", {"refresh": tokens["refresh"]}, format="json")

    assert resp.status_code in (200, 204, 205)
    assert RefreshToken.objects.get(token=tokens["refresh"]).is_revoked


def test_logout_with_token_of_other_user_returns_401(api):
    tokens = login(api, CustomerFactory())
    api.force_authenticate(CustomerFactory())

    resp = api.post("/api/v1/auth/logout/", {"refresh": tokens["refresh"]}, format="json")

    assert resp.status_code == 401
    assert not RefreshToken.objects.get(token=tokens["refresh"]).is_revoked


def test_logout_requires_login(api):
    assert api.post("/api/v1/auth/logout/", {"refresh": "x"}, format="json").status_code == 401


def test_me_returns_current_user(api):
    agent = AgentFactory()
    api.force_authenticate(agent)

    resp = api.get("/api/v1/accounts/me/")

    assert resp.status_code == 200
    assert resp.data["username"] == agent.username
    assert resp.data["role"] == "agent"


def test_me_requires_login(api):
    assert api.get("/api/v1/accounts/me/").status_code == 401


def test_agents_endpoint_lists_only_agents(api):
    agent = AgentFactory()
    CustomerFactory()
    ManagerFactory()
    api.force_authenticate(ManagerFactory())

    resp = api.get("/api/v1/accounts/agents/")

    assert resp.status_code == 200
    assert [u["username"] for u in resp.data] == [agent.username]


def test_category_list_is_readable_by_customer(api):
    CategoryFactory(name="Phần cứng")
    api.force_authenticate(CustomerFactory())

    resp = api.get("/api/v1/categories/")

    assert resp.status_code == 200
    assert "Phần cứng" in str(resp.data)


def test_manager_creates_category(api):
    api.force_authenticate(ManagerFactory())

    resp = api.post("/api/v1/categories/", {"name": "Phần cứng"}, format="json")

    assert resp.status_code == 201
    assert Category.objects.filter(name="Phần cứng").exists()


@pytest.mark.parametrize("factory", [CustomerFactory, AgentFactory])
def test_non_manager_cannot_create_category(api, factory):
    api.force_authenticate(factory())

    resp = api.post("/api/v1/categories/", {"name": "Phần cứng"}, format="json")

    assert resp.status_code == 403
    assert not Category.objects.filter(name="Phần cứng").exists()


def test_create_category_with_duplicate_name_returns_400(api):
    CategoryFactory(name="Phần mềm")
    api.force_authenticate(ManagerFactory())

    resp = api.post("/api/v1/categories/", {"name": "Phần mềm"}, format="json")

    assert resp.status_code == 400


def test_delete_category_in_use_returns_409(api):
    ticket = TicketFactory(category=CategoryFactory(name="Phần mềm"))
    api.force_authenticate(ManagerFactory())

    resp = api.delete(f"/api/v1/categories/{ticket.category_id}/")

    assert resp.status_code == 409
    assert resp.data["code"] == "category_in_use"
    assert Category.objects.filter(pk=ticket.category_id).exists()


def test_delete_unused_category_returns_204(api):
    category = CategoryFactory()
    api.force_authenticate(ManagerFactory())

    resp = api.delete(f"/api/v1/categories/{category.pk}/")

    assert resp.status_code == 204
    assert not Category.objects.filter(pk=category.pk).exists()


def test_customer_creates_ticket_with_new_status(api):
    customer = CustomerFactory()
    category = CategoryFactory()
    api.force_authenticate(customer)
    payload = {
        "title": "Máy in tầng 3 hỏng",
        "description": "Không in được",
        "priority": Ticket.Priority.HIGH,
        "category": str(category.pk),
    }

    resp = api.post(TICKETS, payload, format="json")

    assert resp.status_code == 201
    ticket = Ticket.objects.get(pk=resp.data["id"])
    assert ticket.status == Ticket.Status.NEW
    assert ticket.created_by == customer
    assert resp.data["short_id"].startswith("TD-")


def test_create_ticket_requires_login(api):
    assert api.post(TICKETS, {"title": "Máy in hỏng"}, format="json").status_code == 401


@pytest.mark.parametrize("title", ["", "   ", "abc"])
def test_create_ticket_with_empty_or_short_title_returns_400(api, title):
    api.force_authenticate(CustomerFactory())
    payload = {"title": title, "description": "Mô tả", "category": str(CategoryFactory().pk)}

    resp = api.post(TICKETS, payload, format="json")

    assert resp.status_code == 400
    assert "title" in resp.data
    assert not Ticket.objects.exists()


def test_create_ticket_with_invalid_priority_returns_400(api):
    api.force_authenticate(CustomerFactory())
    payload = {
        "title": "Máy in hỏng",
        "description": "Mô tả",
        "priority": 9,
        "category": str(CategoryFactory().pk),
    }

    assert api.post(TICKETS, payload, format="json").status_code == 400


def test_create_ticket_ignores_read_only_status_and_assignee(api):
    api.force_authenticate(CustomerFactory())
    payload = {
        "title": "Máy in hỏng",
        "description": "Mô tả",
        "category": str(CategoryFactory().pk),
        "status": Ticket.Status.CLOSED,
        "assignee": str(AgentFactory().pk),
    }

    resp = api.post(TICKETS, payload, format="json")

    ticket = Ticket.objects.get(pk=resp.data["id"])
    assert ticket.status == Ticket.Status.NEW
    assert ticket.assignee is None


def test_customer_only_sees_own_tickets(api):
    me = CustomerFactory()
    TicketFactory.create_batch(3, created_by=me)
    TicketFactory()
    api.force_authenticate(me)

    resp = api.get(TICKETS)

    assert resp.status_code == 200
    assert resp.data["count"] == 3


def test_agent_sees_all_tickets(api):
    TicketFactory.create_batch(3)
    api.force_authenticate(AgentFactory())

    assert api.get(TICKETS).data["count"] == 3


@pytest.mark.parametrize("method", ["get", "patch", "delete"])
def test_customer_accessing_others_ticket_returns_404(api, method):
    ticket = TicketFactory()
    api.force_authenticate(CustomerFactory())

    resp = getattr(api, method)(f"{TICKETS}{ticket.pk}/", {"title": "Sửa trộm"}, format="json")

    assert resp.status_code == 404
    ticket.refresh_from_db()
    assert ticket.title != "Sửa trộm"


def test_owner_can_update_own_ticket(api):
    ticket = TicketFactory()
    api.force_authenticate(ticket.created_by)

    resp = api.patch(f"{TICKETS}{ticket.pk}/", {"title": "Tiêu đề mới hơn"}, format="json")

    assert resp.status_code == 200
    ticket.refresh_from_db()
    assert ticket.title == "Tiêu đề mới hơn"


def test_update_closed_ticket_returns_409(api):
    ticket = TicketFactory(status=Ticket.Status.CLOSED)
    api.force_authenticate(ticket.created_by)

    resp = api.patch(f"{TICKETS}{ticket.pk}/", {"title": "Tiêu đề mới hơn"}, format="json")

    assert resp.status_code == 409
    assert resp.data["code"] == "ticket_closed"


def test_owner_cannot_delete_own_ticket(api):
    ticket = TicketFactory()
    api.force_authenticate(ticket.created_by)

    assert api.delete(f"{TICKETS}{ticket.pk}/").status_code == 403


def test_manager_deletes_ticket(api):
    ticket = TicketFactory()
    api.force_authenticate(ManagerFactory())

    assert api.delete(f"{TICKETS}{ticket.pk}/").status_code == 204
    assert not Ticket.objects.filter(pk=ticket.pk).exists()


def test_filter_by_status_paginates_with_count_and_links(api):
    TicketFactory.create_batch(45, status=Ticket.Status.IN_PROGRESS)
    TicketFactory.create_batch(5)
    api.force_authenticate(AgentFactory())

    resp = api.get(TICKETS, {"status": "in_progress", "page": 2, "page_size": 20})

    assert resp.status_code == 200
    assert resp.data["count"] == 45
    assert len(resp.data["results"]) == 20
    assert resp.data["next"] and resp.data["previous"]


def test_filter_by_invalid_status_returns_400(api):
    api.force_authenticate(AgentFactory())

    assert api.get(TICKETS, {"status": "ABC"}).status_code == 400


def test_page_out_of_range_returns_404(api):
    TicketFactory()
    api.force_authenticate(AgentFactory())

    assert api.get(TICKETS, {"page": 999}).status_code == 404


def test_search_and_filter_by_priority_and_assignee(api):
    agent = AgentFactory()
    target = TicketFactory(title="Lỗi VPN văn phòng", priority=3, assignee=agent)
    TicketFactory(title="Máy in hỏng", priority=3)
    api.force_authenticate(ManagerFactory())

    by_search = api.get(TICKETS, {"search": "VPN"})
    by_filter = api.get(TICKETS, {"priority": 3, "assignee": str(agent.pk)})

    assert [t["id"] for t in by_search.data["results"]] == [str(target.pk)]
    assert [t["id"] for t in by_filter.data["results"]] == [str(target.pk)]


def test_ordering_by_priority(api):
    TicketFactory(priority=1)
    TicketFactory(priority=3)
    api.force_authenticate(AgentFactory())

    resp = api.get(TICKETS, {"ordering": "-priority"})

    assert [t["priority"] for t in resp.data["results"]] == [3, 1]


def test_manager_assigns_ticket_to_agent(api):
    ticket = TicketFactory()
    agent = AgentFactory()
    api.force_authenticate(ManagerFactory())

    resp = api.post(f"{TICKETS}{ticket.pk}/assign/", {"agent_id": str(agent.pk)}, format="json")

    assert resp.status_code == 200
    assert resp.data["status"] == Ticket.Status.IN_PROGRESS
    ticket.refresh_from_db()
    assert ticket.assignee == agent


def test_agent_cannot_assign_ticket(api):
    ticket = TicketFactory()
    agent = AgentFactory()
    api.force_authenticate(agent)

    resp = api.post(f"{TICKETS}{ticket.pk}/assign/", {"agent_id": str(agent.pk)}, format="json")

    assert resp.status_code == 403
    ticket.refresh_from_db()
    assert ticket.assignee is None


def test_assign_without_agent_id_returns_400(api):
    ticket = TicketFactory()
    api.force_authenticate(ManagerFactory())

    assert api.post(f"{TICKETS}{ticket.pk}/assign/", {}, format="json").status_code == 400


def test_assign_to_customer_returns_404(api):
    ticket = TicketFactory()
    api.force_authenticate(ManagerFactory())

    resp = api.post(
        f"{TICKETS}{ticket.pk}/assign/", {"agent_id": str(CustomerFactory().pk)}, format="json"
    )

    assert resp.status_code == 404


def test_assign_closed_ticket_returns_409(api):
    ticket = TicketFactory(status=Ticket.Status.CLOSED)
    api.force_authenticate(ManagerFactory())

    resp = api.post(
        f"{TICKETS}{ticket.pk}/assign/", {"agent_id": str(AgentFactory().pk)}, format="json"
    )

    assert resp.status_code == 409
    assert resp.data["code"] == "ticket_closed"


def test_agent_resolves_ticket_and_sets_resolved_at(api):
    agent = AgentFactory()
    ticket = TicketFactory(assignee=agent, status=Ticket.Status.IN_PROGRESS)
    api.force_authenticate(agent)

    resp = api.post(f"{TICKETS}{ticket.pk}/resolve/")

    assert resp.status_code == 200
    ticket.refresh_from_db()
    assert ticket.status == Ticket.Status.RESOLVED
    assert ticket.resolved_at is not None
    assert TicketHistory.objects.filter(ticket=ticket, field="Trạng thái").count() == 1


def test_customer_cannot_resolve_ticket(api):
    ticket = TicketFactory()
    api.force_authenticate(ticket.created_by)

    assert api.post(f"{TICKETS}{ticket.pk}/resolve/").status_code == 403


def test_resolve_closed_ticket_returns_409(api):
    ticket = TicketFactory(status=Ticket.Status.CLOSED)
    api.force_authenticate(AgentFactory())

    resp = api.post(f"{TICKETS}{ticket.pk}/resolve/")

    assert resp.status_code == 409
    ticket.refresh_from_db()
    assert ticket.status == Ticket.Status.CLOSED


def test_owner_closes_own_ticket(api):
    ticket = TicketFactory(status=Ticket.Status.RESOLVED)
    api.force_authenticate(ticket.created_by)

    resp = api.post(f"{TICKETS}{ticket.pk}/close/")

    assert resp.status_code == 200
    assert resp.data["status"] == Ticket.Status.CLOSED


def test_agent_cannot_close_ticket(api):
    ticket = TicketFactory()
    api.force_authenticate(AgentFactory())

    assert api.post(f"{TICKETS}{ticket.pk}/close/").status_code == 403


def test_close_already_closed_ticket_returns_409(api):
    ticket = TicketFactory(status=Ticket.Status.CLOSED)
    api.force_authenticate(ManagerFactory())

    assert api.post(f"{TICKETS}{ticket.pk}/close/").status_code == 409


def test_customer_cannot_close_others_ticket(api):
    ticket = TicketFactory()
    api.force_authenticate(CustomerFactory())

    assert api.post(f"{TICKETS}{ticket.pk}/close/").status_code == 404


def test_comments_are_listed_in_time_order_with_author(api):
    ticket = TicketFactory()
    first = CommentFactory(ticket=ticket)
    second = CommentFactory(ticket=ticket)
    api.force_authenticate(ticket.created_by)

    resp = api.get(f"{TICKETS}{ticket.pk}/comments/")

    assert resp.status_code == 200
    assert [c["id"] for c in resp.data] == [str(first.pk), str(second.pk)]
    assert resp.data[0]["author"] == ticket.created_by.username


def test_customer_does_not_see_internal_note(api):
    ticket = TicketFactory()
    CommentFactory(ticket=ticket, author=AgentFactory(), is_internal=True)
    public = CommentFactory(ticket=ticket)
    api.force_authenticate(ticket.created_by)

    resp = api.get(f"{TICKETS}{ticket.pk}/comments/")

    assert [c["id"] for c in resp.data] == [str(public.pk)]


def test_agent_sees_internal_note(api):
    ticket = TicketFactory()
    CommentFactory(ticket=ticket, author=AgentFactory(), is_internal=True)
    api.force_authenticate(AgentFactory())

    assert len(api.get(f"{TICKETS}{ticket.pk}/comments/").data) == 1


def test_internal_comments_not_counted_for_customer(api):
    ticket = TicketFactory()
    CommentFactory(ticket=ticket, author=AgentFactory(), is_internal=True)
    CommentFactory(ticket=ticket)
    api.force_authenticate(ticket.created_by)

    resp = api.get(f"{TICKETS}{ticket.pk}/")

    assert resp.data["comment_count"] == 1


def test_post_comment_returns_201(api):
    ticket = TicketFactory()
    api.force_authenticate(ticket.created_by)

    resp = api.post(f"{TICKETS}{ticket.pk}/comments/", {"content": "Vẫn lỗi"}, format="json")

    assert resp.status_code == 201
    assert ticket.comments.count() == 1


def test_post_empty_comment_returns_400(api):
    ticket = TicketFactory()
    api.force_authenticate(ticket.created_by)

    resp = api.post(f"{TICKETS}{ticket.pk}/comments/", {"content": "   "}, format="json")

    assert resp.status_code == 400
    assert not ticket.comments.exists()


def test_comment_on_closed_ticket_returns_409(api):
    ticket = TicketFactory(status=Ticket.Status.CLOSED)
    api.force_authenticate(ticket.created_by)

    resp = api.post(f"{TICKETS}{ticket.pk}/comments/", {"content": "Còn lỗi"}, format="json")

    assert resp.status_code == 409


def test_customer_cannot_comment_on_others_ticket(api):
    ticket = TicketFactory()
    api.force_authenticate(CustomerFactory())

    resp = api.post(f"{TICKETS}{ticket.pk}/comments/", {"content": "Xin chào"}, format="json")

    assert resp.status_code == 404


def test_upload_valid_attachment_returns_201(api):
    ticket = TicketFactory()
    api.force_authenticate(ticket.created_by)
    upload = SimpleUploadedFile("loi.png", b"\x89PNG" + b"0" * 1024, content_type="image/png")

    resp = api.post(f"{TICKETS}{ticket.pk}/attachments/", {"file": upload}, format="multipart")

    assert resp.status_code == 201
    assert resp.data["original_name"] == "loi.png"
    assert api.get(f"{TICKETS}{ticket.pk}/attachments/").data[0]["id"] == resp.data["id"]


def test_upload_exe_returns_400(api):
    ticket = TicketFactory()
    api.force_authenticate(ticket.created_by)
    upload = SimpleUploadedFile("setup.exe", b"MZ", content_type="application/octet-stream")

    resp = api.post(f"{TICKETS}{ticket.pk}/attachments/", {"file": upload}, format="multipart")

    assert resp.status_code == 400
    assert not ticket.attachments.exists()


def test_upload_file_over_5mb_returns_400(api):
    ticket = TicketFactory()
    api.force_authenticate(ticket.created_by)
    upload = SimpleUploadedFile("lon.pdf", b"0" * (5 * 1024 * 1024 + 1))

    resp = api.post(f"{TICKETS}{ticket.pk}/attachments/", {"file": upload}, format="multipart")

    assert resp.status_code == 400
    assert not ticket.attachments.exists()


def test_upload_to_closed_ticket_returns_409(api):
    ticket = TicketFactory(status=Ticket.Status.CLOSED)
    api.force_authenticate(ticket.created_by)
    upload = SimpleUploadedFile("loi.png", b"\x89PNG", content_type="image/png")

    resp = api.post(f"{TICKETS}{ticket.pk}/attachments/", {"file": upload}, format="multipart")

    assert resp.status_code == 409


def test_uploader_deletes_own_attachment(api):
    attachment = AttachmentFactory()
    api.force_authenticate(attachment.uploaded_by)

    assert api.delete(f"/api/v1/attachments/{attachment.pk}/").status_code == 204


def test_agent_cannot_delete_attachment_of_others(api):
    attachment = AttachmentFactory()
    api.force_authenticate(AgentFactory())

    assert api.delete(f"/api/v1/attachments/{attachment.pk}/").status_code == 403


def test_customer_cannot_read_attachment_of_others_ticket(api):
    attachment = AttachmentFactory()
    api.force_authenticate(CustomerFactory())

    assert api.get(f"/api/v1/attachments/{attachment.pk}/").status_code == 404


def test_history_lists_all_changes_with_actor_and_values(api):
    ticket = TicketFactory()
    manager, agent = ManagerFactory(), AgentFactory()
    api.force_authenticate(manager)
    api.post(f"{TICKETS}{ticket.pk}/assign/", {"agent_id": str(agent.pk)}, format="json")
    api.post(f"{TICKETS}{ticket.pk}/resolve/")

    resp = api.get(f"{TICKETS}{ticket.pk}/history/")

    assert resp.status_code == 200
    assert len(resp.data) == 3
    assert {"actor", "old_value", "new_value", "created_at"} <= set(resp.data[0])
    assert all(h["actor"] == manager.username for h in resp.data)


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_history_cannot_be_modified(api, method):
    ticket = TicketFactory()
    TicketHistory.objects.create(ticket=ticket, field="Trạng thái", old_value="a", new_value="b")
    api.force_authenticate(ManagerFactory())

    resp = getattr(api, method)(f"{TICKETS}{ticket.pk}/history/", {}, format="json")

    assert resp.status_code == 405
    assert TicketHistory.objects.filter(ticket=ticket).count() == 1


def test_dashboard_summary_counts_by_status(api):
    TicketFactory.create_batch(4)
    TicketFactory.create_batch(6, status=Ticket.Status.RESOLVED)
    api.force_authenticate(ManagerFactory())

    resp = api.get("/api/v1/dashboard/summary/")

    assert resp.status_code == 200
    assert resp.data["summary"]["total"] == 10
    counts = {row["status"]: row["total"] for row in resp.data["by_status"]}
    assert counts["new"] == 4
    assert counts["resolved"] == 6


@pytest.mark.parametrize("url", ["/api/v1/dashboard/summary/", "/api/v1/dashboard/sla-overdue/"])
def test_dashboard_forbidden_for_agent(api, url):
    api.force_authenticate(AgentFactory())

    assert api.get(url).status_code == 403


def test_sla_overdue_lists_only_open_tickets_older_than_24h(api):
    overdue = TicketFactory()
    resolved_old = TicketFactory(status=Ticket.Status.RESOLVED)
    TicketFactory()
    Ticket.objects.filter(pk__in=[overdue.pk, resolved_old.pk]).update(
        created_at=timezone.now() - timedelta(hours=30)
    )
    api.force_authenticate(ManagerFactory())

    resp = api.get("/api/v1/dashboard/sla-overdue/")

    assert resp.status_code == 200
    assert [t["id"] for t in resp.data["results"]] == [str(overdue.pk)]


def test_swagger_docs_are_public_and_api_requires_auth(api):
    assert api.get("/api/docs/").status_code == 200
    assert api.get("/api/schema/").status_code == 200
    assert api.get(TICKETS).status_code == 401
