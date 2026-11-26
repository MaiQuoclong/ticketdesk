import json
import logging
from datetime import UTC, datetime
from typing import Any

RESERVED_ATTRS = frozenset(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {
    "message",
    "asctime",
    "color_message",
}


def _extra_fields(record: logging.LogRecord) -> dict[str, Any]:
    return {
        key: value
        for key, value in vars(record).items()
        if key not in RESERVED_ATTRS and not key.startswith("_")
    }


def _base_fields(record: logging.LogRecord) -> dict[str, Any]:
    return {
        "time": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
        "level": record.levelname,
        "logger": record.name,
        "msg": record.getMessage(),
    }


def _quote(value: Any) -> str:
    text = str(value)
    if text == "" or any(ch in text for ch in ' ="\n\t'):
        return json.dumps(text, ensure_ascii=False)
    return text


class KeyValueFormatter(logging.Formatter):
    """Định dạng log thành một dòng key=value, dễ đọc và dễ lọc bằng grep."""

    def format(self, record: logging.LogRecord) -> str:
        fields = {**_base_fields(record), **_extra_fields(record)}
        line = " ".join(f"{key}={_quote(value)}" for key, value in fields.items())
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


class JsonFormatter(logging.Formatter):
    """Định dạng log thành một đối tượng JSON trên mỗi dòng cho hệ thống thu thập log."""

    def format(self, record: logging.LogRecord) -> str:
        fields = {**_base_fields(record), **_extra_fields(record)}
        if record.exc_info:
            fields["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(fields, ensure_ascii=False, default=str)
