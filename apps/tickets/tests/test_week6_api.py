from datetime import timedelta
from typing import Any

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import RefreshToken, User
from apps.tickets.models import Category, Comment, Ticket, TicketHistory

pytestmark = pytest.mark.django_db


@pytest.fixture
def api() -> Any:
    return APIClient()


@pytest.fixture
def api_data():
    cat_net = Category.objects.create(name="Mạng & Đường truyền", description="Sự cố mạng")
    cat_hw = Category.objects.create(name="Phần cứng", description="Sự cố thiết bị")
    customer = User.objects.create_user("khach01", password="matkhau123", role=User.Role.CUSTOMER)
    other = User.objects.create_user("khach02", password="matkhau123", role=User.Role.CUSTOMER)
    agent = User.objects.create_user("agent01", password="matkhau123", role=User.Role.AGENT)
    manager = User.objects.create_user(
        "quanly01",
        password="matkhau123",
        role=User.Role.MANAGER,
        is_staff=True,
    )
    return {
        "cat_net": cat_net,
        "cat_hw": cat_hw,
        "customer": customer,
        "other": other,
        "agent": agent,
        "manager": manager,
    }


def create_ticket(api_data, **kwargs) -> Ticket:
    defaults = {
        "title": "Không kết nối được VPN nội bộ",
        "description": "Chi tiết sự cố kết nối VPN từ xa.",
        "category": api_data["cat_net"],
        "created_by": api_data["customer"],
        "priority": Ticket.Priority.MEDIUM,
    }
    defaults.update(kwargs)
    return Ticket.objects.create(**defaults)


def test_jwt_login_refresh_and_logout_revokes_token(api, api_data):
    bad_resp = api.post(
        "/api/v1/auth/login/",
        {"username": "khach01", "password": "sai_mat_khau"},
        format="json",
    )
    assert bad_resp.status_code == 401
    assert bad_resp.data["code"] == "invalid_credentials"

    login_resp = api.post(
        "/api/v1/auth/login/",
        {"username": "khach01", "password": "matkhau123"},
        format="json",
    )
    assert login_resp.status_code == 200
    access_token = login_resp.data["access"]
    refresh_token = login_resp.data["refresh"]
    assert login_resp.data["user"]["username"] == "khach01"
    assert RefreshToken.objects.filter(token=refresh_token, is_revoked=False).exists()

    api.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
    me_resp = api.get("/api/v1/accounts/me/")
    assert me_resp.status_code == 200
    assert me_resp.data["role"] == User.Role.CUSTOMER

    refresh_resp = api.post(
        "/api/v1/auth/refresh/",
        {"refresh": refresh_token},
        format="json",
    )
    assert refresh_resp.status_code == 200
    assert "access" in refresh_resp.data

    logout_resp = api.post(
        "/api/v1/auth/logout/",
        {"refresh": refresh_token},
        format="json",
    )
    assert logout_resp.status_code == 204
    assert RefreshToken.objects.get(token=refresh_token).is_revoked is True

    revoked_resp = api.post(
        "/api/v1/auth/refresh/",
        {"refresh": refresh_token},
        format="json",
    )
    assert revoked_resp.status_code == 401
    assert revoked_resp.data["code"] == "token_revoked"


def test_accounts_agents_endpoint_permissions(api, api_data):
    assert api.get("/api/v1/accounts/agents/").status_code == 401

    api.force_authenticate(user=api_data["customer"])
    assert api.get("/api/v1/accounts/agents/").status_code == 403

    api.force_authenticate(user=api_data["agent"])
    resp = api.get("/api/v1/accounts/agents/")
    assert resp.status_code == 200
    assert len(resp.data) == 1
    assert resp.data[0]["username"] == "agent01"


def test_category_crud_permissions_and_protected_delete_409(api, api_data):
    api.force_authenticate(user=api_data["customer"])
    assert api.get("/api/v1/categories/").status_code == 200
    assert api.post("/api/v1/categories/", {"name": "Phần mềm"}, format="json").status_code == 403

    api.force_authenticate(user=api_data["manager"])
    create_resp = api.post(
        "/api/v1/categories/",
        {"name": "Phần mềm", "description": "Lỗi ứng dụng"},
        format="json",
    )
    assert create_resp.status_code == 201
    cat_id = create_resp.data["id"]

    patch_resp = api.patch(
        f"/api/v1/categories/{cat_id}/",
        {"description": "Đã cập nhật"},
        format="json",
    )
    assert patch_resp.status_code == 200
    assert patch_resp.data["description"] == "Đã cập nhật"

    ticket = create_ticket(api_data, category_id=cat_id)
    conflict_resp = api.delete(f"/api/v1/categories/{cat_id}/")
    assert conflict_resp.status_code == 409
    assert conflict_resp.data["code"] == "category_in_use"

    ticket.delete()
    assert api.delete(f"/api/v1/categories/{cat_id}/").status_code == 204


def test_create_ticket_requires_auth_validates_title_and_ignores_readonly_fields(
    api,
    api_data,
):
    assert api.post("/api/v1/tickets/", {"title": "Máy in hỏng"}).status_code == 401

    api.force_authenticate(user=api_data["customer"])
    short_resp = api.post(
        "/api/v1/tickets/",
        {
            "title": "Lỗi",
            "description": "Tiêu đề quá ngắn",
            "category": str(api_data["cat_net"].id),
        },
        format="json",
    )
    assert short_resp.status_code == 400
    assert "title" in short_resp.data

    valid_resp = api.post(
        "/api/v1/tickets/",
        {
            "title": "Máy in tầng 3 báo lỗi kẹt giấy",
            "description": "Đèn đỏ nhấp nháy liên tục",
            "category": str(api_data["cat_hw"].id),
            "priority": Ticket.Priority.HIGH,
            "status": Ticket.Status.CLOSED,
            "assignee": str(api_data["agent"].id),
        },
        format="json",
    )
    assert valid_resp.status_code == 201
    assert valid_resp.data["status"] == Ticket.Status.NEW
    assert valid_resp.data["assignee"] is None
    assert valid_resp.data["created_by"] == "khach01"


def test_customer_only_sees_own_tickets_and_idor_returns_404(api, api_data):
    own_1 = create_ticket(api_data, title="Ticket số 1 của khách 1")
    create_ticket(api_data, title="Ticket số 2 của khách 1")
    other_ticket = create_ticket(
        api_data,
        title="Ticket riêng của khách 2",
        created_by=api_data["other"],
    )

    api.force_authenticate(user=api_data["customer"])
    list_resp = api.get("/api/v1/tickets/")
    assert list_resp.status_code == 200
    assert list_resp.data["count"] == 2

    assert api.get(f"/api/v1/tickets/{other_ticket.id}/").status_code == 404
    assert (
        api.patch(
            f"/api/v1/tickets/{other_ticket.id}/",
            {"title": "Cố tình sửa ticket người khác"},
            format="json",
        ).status_code
        == 404
    )
    assert api.delete(f"/api/v1/tickets/{own_1.id}/").status_code == 403

    api.force_authenticate(user=api_data["manager"])
    assert api.delete(f"/api/v1/tickets/{own_1.id}/").status_code == 204


def test_ticket_filter_search_ordering_and_pagination(api, api_data):
    create_ticket(
        api_data,
        title="Sự cố máy in văn phòng",
        status=Ticket.Status.NEW,
        priority=Ticket.Priority.LOW,
    )
    create_ticket(
        api_data,
        title="Mất kết nối VPN khu vực A",
        status=Ticket.Status.IN_PROGRESS,
        priority=Ticket.Priority.HIGH,
        assignee=api_data["agent"],
    )
    create_ticket(
        api_data,
        title="Cài đặt phần mềm VPN mới",
        status=Ticket.Status.IN_PROGRESS,
        priority=Ticket.Priority.MEDIUM,
        assignee=api_data["agent"],
    )

    api.force_authenticate(user=api_data["agent"])
    filtered = api.get("/api/v1/tickets/?status=in_progress&search=VPN&ordering=priority")
    assert filtered.status_code == 200
    assert filtered.data["count"] == 2
    priorities = [item["priority"] for item in filtered.data["results"]]
    assert priorities == [Ticket.Priority.MEDIUM, Ticket.Priority.HIGH]

    paged = api.get("/api/v1/tickets/?page_size=2")
    assert paged.status_code == 200
    assert paged.data["count"] == 3
    assert len(paged.data["results"]) == 2
    assert paged.data["next"] is not None


def test_ticket_lifecycle_actions_assign_resolve_close_and_409_conflict(api, api_data):
    ticket = create_ticket(api_data)
    other_ticket = create_ticket(api_data, created_by=api_data["other"])

    api.force_authenticate(user=api_data["agent"])
    assert (
        api.post(
            f"/api/v1/tickets/{ticket.id}/assign/",
            {"agent_id": str(api_data["agent"].id)},
            format="json",
        ).status_code
        == 403
    )
    assert api.post(f"/api/v1/tickets/{ticket.id}/close/").status_code == 403

    api.force_authenticate(user=api_data["customer"])
    assert api.post(f"/api/v1/tickets/{ticket.id}/resolve/").status_code == 403
    assert api.post(f"/api/v1/tickets/{other_ticket.id}/close/").status_code == 404

    api.force_authenticate(user=api_data["manager"])
    assign_resp = api.post(
        f"/api/v1/tickets/{ticket.id}/assign/",
        {"agent_id": str(api_data["agent"].id)},
        format="json",
    )
    assert assign_resp.status_code == 200
    assert assign_resp.data["status"] == Ticket.Status.IN_PROGRESS
    assert assign_resp.data["assignee_username"] == "agent01"

    api.force_authenticate(user=api_data["agent"])
    resolve_resp = api.post(f"/api/v1/tickets/{ticket.id}/resolve/")
    assert resolve_resp.status_code == 200
    assert resolve_resp.data["status"] == Ticket.Status.RESOLVED
    assert resolve_resp.data["resolved_at"] is not None

    api.force_authenticate(user=api_data["customer"])
    close_resp = api.post(f"/api/v1/tickets/{ticket.id}/close/")
    assert close_resp.status_code == 200
    assert close_resp.data["status"] == Ticket.Status.CLOSED
    assert TicketHistory.objects.filter(ticket=ticket).count() == 4

    again_close = api.post(f"/api/v1/tickets/{ticket.id}/close/")
    assert again_close.status_code == 409
    assert again_close.data["code"] == "ticket_closed"

    patch_closed = api.patch(
        f"/api/v1/tickets/{ticket.id}/",
        {"title": "Sửa ticket đã đóng"},
        format="json",
    )
    assert patch_closed.status_code == 409
    assert patch_closed.data["code"] == "ticket_closed"

    api.force_authenticate(user=api_data["manager"])
    assign_closed = api.post(
        f"/api/v1/tickets/{ticket.id}/assign/",
        {"agent_id": str(api_data["agent"].id)},
        format="json",
    )
    assert assign_closed.status_code == 409
    assert assign_closed.data["code"] == "ticket_closed"


def test_ticket_comments_hides_internal_from_customer_and_blocks_closed_ticket(
    api,
    api_data,
):
    ticket = create_ticket(api_data)

    api.force_authenticate(user=api_data["customer"])
    c1_resp = api.post(
        f"/api/v1/tickets/{ticket.id}/comments/",
        {"content": "Bình luận của khách hàng", "is_internal": True},
        format="json",
    )
    assert c1_resp.status_code == 201
    assert c1_resp.data["is_internal"] is False

    api.force_authenticate(user=api_data["agent"])
    c2_resp = api.post(
        f"/api/v1/tickets/{ticket.id}/comments/",
        {"content": "Ghi chú nội bộ kỹ thuật", "is_internal": True},
        format="json",
    )
    assert c2_resp.status_code == 201
    assert c2_resp.data["is_internal"] is True
    assert len(api.get(f"/api/v1/tickets/{ticket.id}/comments/").data) == 2
    assert api.get(f"/api/v1/tickets/{ticket.id}/").data["comment_count"] == 2

    api.force_authenticate(user=api_data["customer"])
    cust_comments = api.get(f"/api/v1/tickets/{ticket.id}/comments/")
    assert cust_comments.status_code == 200
    assert len(cust_comments.data) == 1
    assert api.get(f"/api/v1/tickets/{ticket.id}/").data["comment_count"] == 1

    api.force_authenticate(user=api_data["other"])
    assert api.get(f"/api/v1/tickets/{ticket.id}/comments/").status_code == 404
    assert (
        api.post(
            f"/api/v1/tickets/{ticket.id}/comments/",
            {"content": "Bình luận trộm"},
            format="json",
        ).status_code
        == 404
    )

    Ticket.objects.filter(pk=ticket.pk).update(status=Ticket.Status.CLOSED)
    api.force_authenticate(user=api_data["customer"])
    closed_comment = api.post(
        f"/api/v1/tickets/{ticket.id}/comments/",
        {"content": "Bình luận vào ticket đã đóng"},
        format="json",
    )
    assert closed_comment.status_code == 409
    assert closed_comment.data["code"] == "ticket_closed"


def test_ticket_attachments_validation_permissions_and_history(
    api,
    api_data,
    tmp_path,
    settings,
):
    settings.MEDIA_ROOT = tmp_path
    ticket = create_ticket(api_data)

    api.force_authenticate(user=api_data["agent"])
    bad_ext = SimpleUploadedFile("script.exe", b"123", content_type="application/octet-stream")
    assert (
        api.post(
            f"/api/v1/tickets/{ticket.id}/attachments/",
            {"file": bad_ext},
            format="multipart",
        ).status_code
        == 400
    )

    too_large = SimpleUploadedFile(
        "huge.pdf",
        b"a" * (5 * 1024 * 1024 + 1),
        content_type="application/pdf",
    )
    assert (
        api.post(
            f"/api/v1/tickets/{ticket.id}/attachments/",
            {"file": too_large},
            format="multipart",
        ).status_code
        == 400
    )

    valid_file = SimpleUploadedFile("screenshot.png", b"png-data", content_type="image/png")
    upload_resp = api.post(
        f"/api/v1/tickets/{ticket.id}/attachments/",
        {"file": valid_file},
        format="multipart",
    )
    assert upload_resp.status_code == 201
    assert upload_resp.data["original_name"] == "screenshot.png"
    assert upload_resp.data["size"] == 8
    att_id = upload_resp.data["id"]

    api.force_authenticate(user=api_data["customer"])
    assert len(api.get(f"/api/v1/tickets/{ticket.id}/attachments/").data) == 1
    assert api.delete(f"/api/v1/attachments/{att_id}/").status_code == 403

    api.force_authenticate(user=api_data["other"])
    assert api.delete(f"/api/v1/attachments/{att_id}/").status_code == 404
    assert api.get(f"/api/v1/tickets/{ticket.id}/history/").status_code == 404

    api.force_authenticate(user=api_data["manager"])
    api.post(
        f"/api/v1/tickets/{ticket.id}/assign/",
        {"agent_id": str(api_data["agent"].id)},
        format="json",
    )
    hist_resp = api.get(f"/api/v1/tickets/{ticket.id}/history/")
    assert hist_resp.status_code == 200
    assert len(hist_resp.data) == 2
    assert api.delete(f"/api/v1/attachments/{att_id}/").status_code == 204


def test_dashboard_summary_sla_overdue_and_openapi_schema(api, api_data):
    overdue_ticket = create_ticket(api_data, title="Ticket quá hạn 36 giờ")
    Ticket.objects.filter(pk=overdue_ticket.pk).update(
        created_at=timezone.now() - timedelta(hours=36)
    )
    create_ticket(api_data, title="Ticket mới tạo 1 giờ")
    Comment.objects.create(ticket=overdue_ticket, author=api_data["customer"], content="Nhắc SLA")

    api.force_authenticate(user=api_data["customer"])
    assert api.get("/api/v1/dashboard/summary/").status_code == 403
    assert api.get("/api/v1/dashboard/sla-overdue/").status_code == 403

    api.force_authenticate(user=api_data["agent"])
    assert api.get("/api/v1/dashboard/summary/").status_code == 403
    assert api.get("/api/v1/dashboard/sla-overdue/").status_code == 403

    api.force_authenticate(user=api_data["manager"])
    summary_resp = api.get("/api/v1/dashboard/summary/")
    assert summary_resp.status_code == 200
    assert summary_resp.data["summary"]["total"] == 2
    assert len(summary_resp.data["by_status"]) >= 1
    assert len(summary_resp.data["agents"]) == 1

    sla_resp = api.get("/api/v1/dashboard/sla-overdue/?hours=24")
    assert sla_resp.status_code == 200
    assert sla_resp.data["count"] == 1
    assert sla_resp.data["results"][0]["id"] == str(overdue_ticket.id)
    assert sla_resp.data["results"][0]["comment_count"] == 1

    schema_resp = api.get("/api/schema/")
    assert schema_resp.status_code == 200
    assert "TicketDesk REST API" in schema_resp.content.decode("utf-8")

    docs_resp = api.get("/api/docs/")
    assert docs_resp.status_code == 200
    assert "swagger-ui" in docs_resp.content.decode("utf-8")
