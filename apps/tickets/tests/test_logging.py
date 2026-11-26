import json
import logging
import sys

from django.conf import settings

from config.logging import JsonFormatter, KeyValueFormatter


def _record(msg: str = "Đã gửi email", exc: bool = False, **extra) -> logging.LogRecord:
    exc_info = None
    if exc:
        try:
            raise ValueError("lỗi thử")
        except ValueError:
            exc_info = sys.exc_info()
    record = logging.LogRecord("apps.tickets.tasks", logging.INFO, __file__, 1, msg, None, exc_info)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_keyvalue_formatter_outputs_single_line_with_extra_fields():
    line = KeyValueFormatter().format(_record(event="notify", sent=1, note="có dấu cách"))

    assert "\n" not in line
    assert line.startswith("time=")
    assert "level=INFO logger=apps.tickets.tasks" in line
    assert 'msg="Đã gửi email"' in line
    assert "event=notify sent=1" in line
    assert 'note="có dấu cách"' in line
    assert "pathname" not in line and "lineno" not in line


def test_keyvalue_formatter_quotes_empty_and_appends_traceback():
    output = KeyValueFormatter().format(_record(exc=True, reason=""))

    first, *rest = output.splitlines()
    assert 'reason=""' in first
    assert "ValueError: lỗi thử" in rest[-1]


def test_json_formatter_outputs_valid_json_per_line():
    output = JsonFormatter().format(_record(exc=True, event="enqueue_failed", task="x"))

    assert "\n" not in output
    data = json.loads(output)
    assert data["level"] == "INFO"
    assert data["msg"] == "Đã gửi email"
    assert data["event"] == "enqueue_failed"
    assert data["task"] == "x"
    assert "ValueError" in data["exc_info"]


def test_logging_settings_route_app_and_celery_logs_to_console():
    config = settings.LOGGING

    assert config["handlers"]["console"]["formatter"] in config["formatters"]
    for name in ("apps", "celery", "django"):
        assert config["loggers"][name]["handlers"] == ["console"]
    assert settings.CELERY_WORKER_HIJACK_ROOT_LOGGER is False
