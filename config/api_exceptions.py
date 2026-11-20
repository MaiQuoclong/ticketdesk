from typing import Any

from django.db.models import ProtectedError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

from apps.tickets.services import TicketClosedError, TicketServiceError


def custom_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """Chuẩn hoá phản hồi lỗi REST API theo định dạng detail và code."""
    if isinstance(exc, TicketClosedError):
        return Response(
            {"detail": str(exc), "code": "ticket_closed"},
            status=status.HTTP_409_CONFLICT,
        )
    if isinstance(exc, TicketServiceError):
        return Response(
            {"detail": str(exc), "code": "service_error"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if isinstance(exc, ProtectedError):
        return Response(
            {
                "detail": "Không thể xóa danh mục đang có ticket gắn kèm.",
                "code": "category_in_use",
            },
            status=status.HTTP_409_CONFLICT,
        )

    response = exception_handler(exc, context)
    if response is not None and isinstance(response.data, dict):
        detail = response.data.get("detail")
        if detail is not None and "code" not in response.data:
            code = getattr(detail, "code", "error")
            response.data["code"] = str(code)
    return response
