from django.db import migrations
from django.db.models import F, OuterRef, Subquery
from django.db.models.functions import Coalesce, Greatest

DONE_STATUSES = ["resolved", "closed"]
DONE_LABELS = ["Đã xử lý", "Đã đóng"]


def backfill_resolved_at(apps, schema_editor):
    Ticket = apps.get_model("tickets", "Ticket")
    TicketHistory = apps.get_model("tickets", "TicketHistory")

    first_done_at = (
        TicketHistory.objects.filter(
            ticket=OuterRef("pk"), field="Trạng thái", new_value__in=DONE_LABELS
        )
        .order_by("created_at")
        .values("created_at")[:1]
    )
    Ticket.objects.filter(status__in=DONE_STATUSES, resolved_at__isnull=True).update(
        resolved_at=Greatest(Coalesce(Subquery(first_done_at), F("updated_at")), F("created_at"))
    )


class Migration(migrations.Migration):
    dependencies = [
        ("tickets", "0002_ticket_indexes_constraints"),
    ]

    operations = [
        migrations.RunPython(backfill_resolved_at, migrations.RunPython.noop),
    ]
