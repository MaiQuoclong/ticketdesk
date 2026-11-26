import io
import uuid
from datetime import datetime, timedelta
from typing import Any
from unittest import mock

import pytest
from django.utils import timezone
from openpyxl import load_workbook
from rest_framework.test import APIClient

from apps.tickets import reports, tasks
from apps.tickets.models import Ticket
from apps.tickets.tests.factories import (
    AgentFactory,
    CategoryFactory,
    CustomerFactory,
    ManagerFactory,
    TicketFactory,
)

pytestmark = pytest.mark.django_db
URL = "/api/v1/reports/export/"


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


def client_for(user) -> Any:
    client = APIClient()
    client.force_authenticate(user)
    return client


def _created(ticket: Ticket, when: datetime) -> None:
    Ticket.objects.filter(pk=ticket.pk).update(created_at=when)


def _read_rows(content: bytes) -> list[tuple]:
    sheet = load_workbook(io.BytesIO(content)).active
    assert sheet is not None
    return list(sheet.iter_rows(values_only=True))


def _range(days: int = 7) -> dict[str, str]:
    today = timezone.localdate()
    return {"date_from": str(today - timedelta(days=days)), "date_to": str(today)}


def test_build_report_writes_header_and_rows_in_range():
    today = timezone.localdate()
    agent = AgentFactory(username="agent_xl")
    inside = TicketFactory(
        title="Máy in hỏng",
        category=CategoryFactory(name="Phần cứng"),
        created_by=CustomerFactory(username="khach_xl"),
        assignee=agent,
        status=Ticket.Status.RESOLVED,
        priority=Ticket.Priority.HIGH,
        resolved_at=timezone.now(),
    )
    unassigned = TicketFactory()
    before = TicketFactory()
    _created(before, timezone.now() - timedelta(days=10))

    path, rows = reports.build_tickets_report(today - timedelta(days=1), today, "r.xlsx")

    assert rows == 2
    assert path == reports.report_path("r.xlsx") and path.is_file()
    data = _read_rows(path.read_bytes())
    assert list(data[0]) == reports.HEADERS
    first = data[1]
    assert first[:7] == (
        inside.short_id,
        "Máy in hỏng",
        "Phần cứng",
        "Cao",
        "Đã xử lý",
        "khach_xl",
        "agent_xl",
    )
    assert isinstance(first[7], datetime) and first[7].tzinfo is None
    assert first[7].date() == timezone.localtime(inside.created_at).date()
    assert isinstance(first[8], datetime)
    assert data[2][0] == unassigned.short_id
    assert data[2][6] is None and data[2][8] is None


def test_build_report_includes_both_boundary_days():
    today = timezone.localdate()
    start = today - timedelta(days=3)
    first_day = TicketFactory()
    _created(first_day, timezone.make_aware(datetime.combine(start, datetime.min.time())))
    TicketFactory()
    outside = TicketFactory()
    _created(
        outside,
        timezone.make_aware(datetime.combine(start, datetime.min.time())) - timedelta(seconds=1),
    )

    _, rows = reports.build_tickets_report(start, today, "b.xlsx")

    assert rows == 2


def test_export_task_returns_file_and_row_count():
    TicketFactory.create_batch(2)
    today = timezone.localdate()

    result = tasks.export_tickets_report.apply(
        args=("user-1", str(today), str(today)), task_id="abcdef12-0000"
    ).get()

    assert result == {"file": result["file"], "rows": 2, "user_id": "user-1"}
    assert result["file"].startswith(f"tickets_{today:%Y%m%d}_{today:%Y%m%d}_abcdef12")
    assert reports.report_path(result["file"]).is_file()


def test_export_flow_returns_202_then_success_and_downloadable_file():
    manager = ManagerFactory()
    TicketFactory.create_batch(3)
    _created(TicketFactory(), timezone.now() - timedelta(days=40))
    client = client_for(manager)

    resp = client.post(URL, _range())
    assert resp.status_code == 202
    assert resp.data["status"] == "pending"
    task_id = resp.data["task_id"]
    uuid.UUID(task_id)

    status_resp = client.get(f"{URL}{task_id}/")
    assert status_resp.status_code == 200
    assert status_resp.data["status"] == "success"
    assert status_resp.data["rows"] == 3
    assert status_resp.data["download_url"].endswith(f"{URL}{task_id}/download/")

    download = client.get(f"{URL}{task_id}/download/")
    assert download.status_code == 200
    assert download["Content-Type"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert "attachment" in download["Content-Disposition"]
    assert len(_read_rows(b"".join(download.streaming_content))) == 4


def test_export_result_is_private_to_requesting_manager():
    TicketFactory()
    task_id = client_for(ManagerFactory()).post(URL, _range()).data["task_id"]
    other = client_for(ManagerFactory())

    assert other.get(f"{URL}{task_id}/").status_code == 404
    assert other.get(f"{URL}{task_id}/download/").status_code == 404
    assert other.get(f"{URL}{uuid.uuid4()}/").status_code == 404


def test_export_empty_range_returns_400_no_data():
    TicketFactory()
    old_day = timezone.localdate() - timedelta(days=100)

    resp = client_for(ManagerFactory()).post(
        URL, {"date_from": str(old_day), "date_to": str(old_day)}
    )

    assert resp.status_code == 400
    assert resp.data["code"] == "no_data"
    assert resp.data["detail"] == "Không có dữ liệu trong khoảng thời gian đã chọn."


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"date_from": "2026-01-01"},
        {"date_from": "2026-02-01", "date_to": "2026-01-01"},
        {"date_from": "2024-01-01", "date_to": "2026-01-01"},
        {"date_from": "abc", "date_to": "2026-01-01"},
    ],
)
def test_export_invalid_payload_returns_400(payload):
    assert client_for(ManagerFactory()).post(URL, payload).status_code == 400


def test_export_requires_manager():
    TicketFactory()
    task_id = client_for(ManagerFactory()).post(URL, _range()).data["task_id"]

    for user in (AgentFactory(), CustomerFactory()):
        client = client_for(user)
        assert client.post(URL, _range()).status_code == 403
        assert client.get(f"{URL}{task_id}/").status_code == 403
        assert client.get(f"{URL}{task_id}/download/").status_code == 403
    assert APIClient().post(URL, _range()).status_code == 401


def test_export_returns_503_when_queue_unavailable():
    TicketFactory()
    with mock.patch.object(
        tasks.export_tickets_report, "apply_async", side_effect=ConnectionError("down")
    ):
        resp = client_for(ManagerFactory()).post(URL, _range())

    assert resp.status_code == 503
    assert resp.data["code"] == "queue_unavailable"


@pytest.mark.parametrize(
    ("celery_state", "expected"),
    [
        ("PENDING", "pending"),
        ("STARTED", "running"),
        ("FAILURE", "failure"),
        ("REVOKED", "failure"),
    ],
)
def test_export_status_maps_celery_states(celery_state, expected):
    manager = ManagerFactory()
    TicketFactory()
    client = client_for(manager)
    task_id = client.post(URL, _range()).data["task_id"]
    fake = mock.Mock(state=celery_state)

    with mock.patch("apps.tickets.api.views.AsyncResult", return_value=fake):
        resp = client.get(f"{URL}{task_id}/")
        download = client.get(f"{URL}{task_id}/download/")

    assert resp.status_code == 200
    assert resp.data == {
        "task_id": task_id,
        "status": expected,
        "rows": None,
        "download_url": None,
    }
    assert download.status_code == 404


def test_download_returns_404_when_file_was_removed():
    TicketFactory()
    client = client_for(ManagerFactory())
    task_id = client.post(URL, _range()).data["task_id"]
    files = list(reports.report_path("").glob("*.xlsx"))
    assert len(files) == 1
    files[0].unlink()

    assert client.get(f"{URL}{task_id}/download/").status_code == 404


def test_export_endpoints_in_openapi_schema():
    resp = client_for(ManagerFactory()).get("/api/schema/?format=json")

    paths = resp.json()["paths"]
    assert "/api/v1/reports/export/" in paths
    assert "/api/v1/reports/export/{task_id}/" in paths
    assert "/api/v1/reports/export/{task_id}/download/" in paths
