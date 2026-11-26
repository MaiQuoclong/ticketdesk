from django import template
from django.utils.html import format_html

from apps.tickets.models import Ticket

register = template.Library()

STATUS_LABELS = dict(Ticket.Status.choices)
PRIORITY_LABELS = dict(Ticket.Priority.choices)


def _status_code(value):
    return getattr(value, "status", value)


def _priority_code(value):
    raw = getattr(value, "priority", value)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


@register.filter
def status_label(value):
    code = _status_code(value)
    return STATUS_LABELS.get(code, code or "")


@register.filter
def priority_label(value):
    code = _priority_code(value)
    return PRIORITY_LABELS.get(code, "")


@register.filter
def status_badge(value):
    code = _status_code(value)
    if code not in STATUS_LABELS:
        return ""
    return format_html('<span class="mv-status mv-status-{}">{}</span>', code, STATUS_LABELS[code])


@register.filter
def priority_badge(value):
    code = _priority_code(value)
    if code not in PRIORITY_LABELS:
        return ""
    return format_html(
        '<span class="mv-priority mv-priority-{}" title="Độ ưu tiên">P{} · {}</span>',
        code,
        code,
        PRIORITY_LABELS[code],
    )
