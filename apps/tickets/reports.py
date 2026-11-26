from datetime import date, datetime
from pathlib import Path

from django.conf import settings
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font

from . import selectors

REPORTS_DIR = "reports"
HEADERS = [
    "Mã",
    "Tiêu đề",
    "Danh mục",
    "Độ ưu tiên",
    "Trạng thái",
    "Người tạo",
    "Người xử lý",
    "Ngày tạo",
    "Ngày giải quyết",
]
COLUMN_WIDTHS = [12, 50, 20, 12, 14, 16, 16, 20, 20]


def _naive(value: datetime | None) -> datetime | None:
    return timezone.localtime(value).replace(tzinfo=None) if value else None


def report_path(name: str) -> Path:
    return Path(settings.MEDIA_ROOT) / REPORTS_DIR / name


def build_tickets_report(date_from: date, date_to: date, name: str) -> tuple[Path, int]:
    """Ghi danh sách ticket trong khoảng ngày ra tệp .xlsx, trả về đường dẫn và số dòng."""
    path = report_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)

    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("Tickets")
    for index, width in enumerate(COLUMN_WIDTHS):
        sheet.column_dimensions[chr(ord("A") + index)].width = width

    bold = Font(bold=True)
    header = []
    for title in HEADERS:
        cell = WriteOnlyCell(sheet, value=title)
        cell.font = bold
        header.append(cell)
    sheet.append(header)

    rows = 0
    for ticket in selectors.tickets_created_between(date_from, date_to).iterator(chunk_size=2000):
        sheet.append(
            [
                ticket.short_id,
                ticket.title,
                ticket.category.name if ticket.category else "",
                ticket.get_priority_display(),
                ticket.get_status_display(),
                ticket.created_by.username,
                ticket.assignee.username if ticket.assignee else "",
                _naive(ticket.created_at),
                _naive(ticket.resolved_at),
            ]
        )
        rows += 1

    workbook.save(path)
    return path, rows
