import hashlib
import hmac
import json
from io import BytesIO
from unittest import mock
from urllib.error import HTTPError, URLError

import pytest
from celery.exceptions import Retry
from django.core.cache import cache

from apps.tickets import services, tasks
from apps.tickets.models import Ticket
from apps.tickets.tests.factories import AgentFactory, CustomerFactory, TicketFactory

pytestmark = pytest.mark.django_db

URL = "https://hooks.example.com/ticketdesk"
SECRET = "bi-mat-webhook"


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def webhook_on(settings):
    settings.WEBHOOK_URL = URL
    settings.WEBHOOK_SECRET = SECRET
    settings.WEBHOOK_TIMEOUT = 3
    return settings


@pytest.fixture
def ticket():
    return TicketFactory(created_by=CustomerFactory(email="khach@example.com"))


def _response(status: int = 200) -> mock.MagicMock:
    response = mock.MagicMock()
    response.status = status
    response.__enter__.return_value = response
    return response


def _call(ticket: Ticket, event_id: str = "evt-1") -> int:
    return tasks.send_webhook(
        "ticket.status_changed", str(ticket.pk), event_id, "new", "in_progress", None
    )


def test_send_webhook_posts_signed_json(webhook_on, ticket):
    with mock.patch.object(tasks.urllib_request, "urlopen", return_value=_response()) as urlopen:
        assert _call(ticket) == 1

    req = urlopen.call_args.args[0]
    assert urlopen.call_args.kwargs["timeout"] == 3
    assert req.full_url == URL
    assert req.get_method() == "POST"
    payload = json.loads(req.data)
    assert payload["event"] == "ticket.status_changed"
    assert payload["event_id"] == "evt-1"
    assert payload["ticket"]["id"] == str(ticket.pk)
    assert payload["ticket"]["new_status"] == "in_progress"
    expected = "sha256=" + hmac.new(SECRET.encode(), req.data, hashlib.sha256).hexdigest()
    assert req.get_header("X-ticketdesk-signature") == expected
    assert req.get_header("X-ticketdesk-event-id") == "evt-1"


def test_signature_helper_matches_receiver_check():
    body = b'{"a": 1}'
    signature = tasks.webhook_signature(body, SECRET)
    digest = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    assert hmac.compare_digest(signature, f"sha256={digest}")


def test_no_signature_header_without_secret(webhook_on, ticket):
    webhook_on.WEBHOOK_SECRET = ""
    with mock.patch.object(tasks.urllib_request, "urlopen", return_value=_response()) as urlopen:
        _call(ticket)
    assert urlopen.call_args.args[0].get_header("X-ticketdesk-signature") is None


def test_disabled_when_url_empty(settings, ticket):
    settings.WEBHOOK_URL = ""
    with mock.patch.object(tasks.urllib_request, "urlopen") as urlopen:
        assert _call(ticket) == 0
    urlopen.assert_not_called()


def test_same_event_id_sent_once(webhook_on, ticket):
    with mock.patch.object(tasks.urllib_request, "urlopen", return_value=_response()) as urlopen:
        assert _call(ticket) == 1
        assert _call(ticket) == 0
        assert _call(ticket, event_id="evt-2") == 1
    assert urlopen.call_count == 2


def test_missing_ticket_skipped(webhook_on):
    with mock.patch.object(tasks.urllib_request, "urlopen") as urlopen:
        result = tasks.send_webhook(
            "ticket.status_changed",
            "00000000-0000-0000-0000-000000000000",
            "evt-x",
            "new",
            "closed",
        )
    assert result == 0
    urlopen.assert_not_called()


def _http_error(code: int) -> HTTPError:
    return HTTPError(URL, code, "lỗi", {}, BytesIO(b""))  # type: ignore[arg-type]


def test_4xx_not_retried(webhook_on, ticket):
    with (
        mock.patch.object(tasks.urllib_request, "urlopen", side_effect=_http_error(400)),
        mock.patch.object(tasks.send_webhook, "retry") as retry,
    ):
        assert _call(ticket) == 0
    retry.assert_not_called()
    assert cache.get("tickets:webhook-sent:evt-1") is None


@pytest.mark.parametrize(
    "error",
    [_http_error(503), URLError("connection refused"), TimeoutError("timed out")],
)
def test_5xx_and_network_errors_retried(webhook_on, ticket, error):
    with (
        mock.patch.object(tasks.urllib_request, "urlopen", side_effect=error),
        mock.patch.object(tasks.send_webhook, "retry", side_effect=Retry()) as retry,
        pytest.raises(Retry),
    ):
        _call(ticket)
    retry.assert_called_once()
    assert cache.get("tickets:webhook-sent:evt-1") is None


def test_retry_policy_is_bounded():
    assert tasks.send_webhook.max_retries == 5
    expected = {tasks.WebhookServerError, URLError, TimeoutError}
    assert expected.issubset(set(tasks.send_webhook.autoretry_for))


def test_status_change_enqueues_webhook_on_commit(
    webhook_on, ticket, django_capture_on_commit_callbacks
):
    agent = AgentFactory()
    with (
        mock.patch.object(tasks.urllib_request, "urlopen", return_value=_response()) as urlopen,
        django_capture_on_commit_callbacks(execute=False) as callbacks,
    ):
        services.assign_ticket(ticket=ticket, agent=agent, actor=agent)
        urlopen.assert_not_called()
    with mock.patch.object(tasks.urllib_request, "urlopen", return_value=_response()) as urlopen:
        for callback in callbacks:
            callback()
    payload = json.loads(urlopen.call_args.args[0].data)
    assert payload["ticket"]["old_status"] == "new"
    assert payload["ticket"]["new_status"] == "in_progress"
    assert payload["actor_id"] == str(agent.pk)


def test_status_change_without_url_does_not_enqueue(
    settings, ticket, django_capture_on_commit_callbacks
):
    settings.WEBHOOK_URL = ""
    agent = AgentFactory()
    with (
        mock.patch.object(tasks.send_webhook, "delay") as delay,
        django_capture_on_commit_callbacks(execute=True),
    ):
        services.change_ticket_status(ticket=ticket, new_status="resolved", actor=agent)
    delay.assert_not_called()
