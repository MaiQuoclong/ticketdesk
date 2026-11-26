import logging
from typing import cast
from uuid import UUID, uuid4

from celery.result import AsyncResult
from django.conf import settings
from django.core.cache import cache
from django.db.models import Count, IntegerField, OuterRef, ProtectedError, Subquery
from django.db.models.functions import Coalesce
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.tickets import reports, selectors
from apps.tickets.models import Attachment, Category, Comment, Ticket
from apps.tickets.services import (
    TicketClosedError,
    add_comment,
    assign_ticket,
    change_ticket_status,
)
from apps.tickets.tasks import export_tickets_report

from .permissions import (
    IsAgentOrManager,
    IsManager,
    IsManagerOrReadOnly,
    IsOwnerOrManager,
    IsStaffOrOwnerReadOnly,
    IsUploaderOrManager,
)
from .serializers import (
    AttachmentSerializer,
    CategorySerializer,
    CommentSerializer,
    DashboardSummarySerializer,
    ReportExportRequestSerializer,
    ReportExportStatusSerializer,
    TicketAssignSerializer,
    TicketHistorySerializer,
    TicketSerializer,
)

logger = logging.getLogger(__name__)

XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
EXPORT_STATES = {
    "PENDING": "pending",
    "RECEIVED": "pending",
    "STARTED": "running",
    "RETRY": "running",
    "SUCCESS": "success",
}


class CategoryViewSet(viewsets.ModelViewSet):
    """CRUD danh mục sự cố: mọi người dùng đăng nhập được xem, chỉ Quản lý được thêm/sửa/xóa."""

    queryset = Category.objects.all().order_by("name")
    serializer_class = CategorySerializer
    permission_classes = [IsManagerOrReadOnly]
    search_fields = ["name", "description"]
    ordering_fields = ["name"]

    def destroy(self, request: Request, *args, **kwargs) -> Response:
        instance = self.get_object()
        try:
            self.perform_destroy(instance)
        except ProtectedError:
            return Response(
                {
                    "detail": "Không thể xóa danh mục đang có ticket gắn kèm.",
                    "code": "category_in_use",
                },
                status=status.HTTP_409_CONFLICT,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class TicketViewSet(viewsets.ModelViewSet):
    """CRUD Ticket, các action vòng đời, bình luận, tệp đính kèm và lịch sử thay đổi."""

    serializer_class = TicketSerializer
    permission_classes = [IsStaffOrOwnerReadOnly]
    filterset_fields = ["status", "priority", "category", "assignee"]
    search_fields = ["title", "description"]
    ordering_fields = ["created_at", "priority", "updated_at"]
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = Ticket.objects.select_related("created_by", "assignee", "category")
        user = self.request.user
        is_customer = (
            isinstance(user, User) and user.is_authenticated and user.role == User.Role.CUSTOMER
        )
        if is_customer:
            qs = qs.filter(created_by=cast(User, user))

        comments = Comment.objects.filter(ticket=OuterRef("pk"))
        if is_customer:
            comments = comments.filter(is_internal=False)
        comment_count = comments.order_by().values("ticket").annotate(n=Count("id")).values("n")
        return qs.annotate(
            comment_count=Coalesce(Subquery(comment_count, output_field=IntegerField()), 0)
        )

    def perform_create(self, serializer: BaseSerializer) -> None:
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer: BaseSerializer) -> None:
        if serializer.instance and serializer.instance.status == Ticket.Status.CLOSED:
            raise TicketClosedError("Ticket đã đóng, không thể chỉnh sửa.")
        serializer.save()

    @action(detail=True, methods=["post"], permission_classes=[IsManager])
    def assign(self, request: Request, pk=None) -> Response:
        ticket = self.get_object()
        actor = cast(User, request.user)
        payload = TicketAssignSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        agent = get_object_or_404(
            User,
            pk=payload.validated_data["target_agent_id"],
            role=User.Role.AGENT,
        )
        try:
            ticket = assign_ticket(ticket=ticket, agent=agent, actor=actor)
        except TicketClosedError as exc:
            return Response(
                {"detail": str(exc), "code": "ticket_closed"},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(self.get_serializer(ticket).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], permission_classes=[IsAgentOrManager])
    def resolve(self, request: Request, pk=None) -> Response:
        ticket = self.get_object()
        actor = cast(User, request.user)
        try:
            ticket = change_ticket_status(
                ticket=ticket,
                new_status=Ticket.Status.RESOLVED,
                actor=actor,
            )
        except TicketClosedError as exc:
            return Response(
                {"detail": str(exc), "code": "ticket_closed"},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(self.get_serializer(ticket).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], permission_classes=[IsOwnerOrManager])
    def close(self, request: Request, pk=None) -> Response:
        ticket = self.get_object()
        actor = cast(User, request.user)
        try:
            ticket = change_ticket_status(
                ticket=ticket,
                new_status=Ticket.Status.CLOSED,
                actor=actor,
            )
        except TicketClosedError as exc:
            return Response(
                {"detail": str(exc), "code": "ticket_closed"},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(self.get_serializer(ticket).data, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=["get", "post"],
        url_path="comments",
        permission_classes=[IsAuthenticated],
    )
    def comments(self, request: Request, pk=None) -> Response:
        ticket = self.get_object()
        user = cast(User, request.user)
        if request.method == "GET":
            qs = ticket.comments.select_related("author").order_by("created_at")
            if user.role == User.Role.CUSTOMER:
                qs = qs.filter(is_internal=False)
            return Response(CommentSerializer(qs, many=True).data, status=status.HTTP_200_OK)

        serializer = CommentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            comment = add_comment(
                ticket=ticket,
                author=user,
                content=serializer.validated_data["content"],
                is_internal=serializer.validated_data.get("is_internal", False),
            )
        except TicketClosedError as exc:
            return Response(
                {"detail": str(exc), "code": "ticket_closed"},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(CommentSerializer(comment).data, status=status.HTTP_201_CREATED)

    @action(
        detail=True,
        methods=["get", "post"],
        url_path="attachments",
        permission_classes=[IsAuthenticated],
        parser_classes=[MultiPartParser, FormParser, JSONParser],
    )
    def attachments(self, request: Request, pk=None) -> Response:
        ticket = self.get_object()
        if request.method == "GET":
            qs = ticket.attachments.select_related("uploaded_by").order_by("-created_at")
            data = AttachmentSerializer(qs, many=True, context={"request": request}).data
            return Response(data, status=status.HTTP_200_OK)

        if ticket.status == Ticket.Status.CLOSED:
            return Response(
                {
                    "detail": "Ticket đã đóng, không thể tải tệp đính kèm.",
                    "code": "ticket_closed",
                },
                status=status.HTTP_409_CONFLICT,
            )

        serializer = AttachmentSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        uploaded_file = serializer.validated_data["file"]
        attachment = serializer.save(
            ticket=ticket,
            uploaded_by=request.user,
            original_name=uploaded_file.name,
            size=uploaded_file.size,
        )
        return Response(
            AttachmentSerializer(attachment, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=True,
        methods=["get"],
        url_path="history",
        permission_classes=[IsAuthenticated],
    )
    def history(self, request: Request, pk=None) -> Response:
        ticket = self.get_object()
        qs = ticket.histories.select_related("actor").order_by("-created_at")
        return Response(TicketHistorySerializer(qs, many=True).data, status=status.HTTP_200_OK)


class AttachmentViewSet(
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Xem chi tiết và xóa tệp đính kèm (chỉ người tải lên hoặc Quản lý được xóa)."""

    serializer_class = AttachmentSerializer
    permission_classes = [IsAuthenticated, IsUploaderOrManager]

    def get_queryset(self):
        qs = Attachment.objects.select_related("ticket", "uploaded_by")
        user = self.request.user
        if isinstance(user, User) and user.is_authenticated and user.role == User.Role.CUSTOMER:
            qs = qs.filter(ticket__created_by=user)
        return qs


class DashboardSummaryAPIView(APIView):
    """Thống kê tổng hợp ticket theo trạng thái, ưu tiên, danh mục và hiệu suất agent."""

    permission_classes = [IsManager]
    serializer_class = DashboardSummarySerializer

    def get(self, request: Request) -> Response:
        summary = selectors.ticket_summary()
        total = summary["total"]
        categories = [
            {
                "id": str(cat.id),
                "name": cat.name,
                "total": getattr(cat, "total", 0),
                "open": getattr(cat, "open", 0),
            }
            for cat in selectors.tickets_by_category()
        ]
        agents = [
            {
                "id": str(agent.id),
                "username": agent.username,
                "total": getattr(agent, "total", 0),
                "in_progress": getattr(agent, "in_progress", 0),
                "resolved": getattr(agent, "resolved", 0),
                "closed": getattr(agent, "closed", 0),
                "avg_resolve_display": getattr(agent, "avg_resolve_display", "—"),
            }
            for agent in selectors.agent_workload()
        ]
        data = {
            "summary": summary,
            "by_status": selectors.tickets_by_status(total),
            "by_priority": selectors.tickets_by_priority(total),
            "by_category": categories,
            "agents": agents,
        }
        return Response(data, status=status.HTTP_200_OK)


class DashboardSlaOverdueAPIView(generics.ListAPIView):
    """Danh sách ticket quá hạn SLA (mặc định 24 giờ) vẫn đang ở trạng thái Mới hoặc Đang xử lý."""

    permission_classes = [IsManager]
    serializer_class = TicketSerializer
    queryset = Ticket.objects.none()

    def get_queryset(self):
        hours_str = str(self.request.GET.get("hours", "24"))
        hours = (
            int(hours_str) if hours_str.isdigit() and int(hours_str) > 0 else selectors.SLA_HOURS
        )
        comment_count = (
            Comment.objects.filter(ticket=OuterRef("pk"))
            .order_by()
            .values("ticket")
            .annotate(n=Count("id"))
            .values("n")
        )
        return selectors.sla_overdue_tickets(hours).annotate(
            comment_count=Coalesce(Subquery(comment_count, output_field=IntegerField()), 0)
        )


def _export_owner_key(task_id: str) -> str:
    return f"reports:export:{task_id}"


def _owned_export(request: Request, task_id: UUID) -> AsyncResult:
    if cache.get(_export_owner_key(str(task_id))) != str(request.user.pk):
        raise Http404
    return AsyncResult(str(task_id))


class ReportExportAPIView(APIView):
    """Yêu cầu xuất báo cáo Excel ticket theo khoảng ngày tạo (chạy nền)."""

    permission_classes = [IsManager]

    @extend_schema(
        request=ReportExportRequestSerializer, responses={202: ReportExportStatusSerializer}
    )
    def post(self, request: Request) -> Response:
        serializer = ReportExportRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        date_from = serializer.validated_data["date_from"]
        date_to = serializer.validated_data["date_to"]
        if not selectors.tickets_created_between(date_from, date_to).exists():
            return Response(
                {"detail": "Không có dữ liệu trong khoảng thời gian đã chọn.", "code": "no_data"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        task_id = str(uuid4())
        cache.set(_export_owner_key(task_id), str(request.user.pk), settings.CELERY_RESULT_EXPIRES)
        try:
            export_tickets_report.apply_async(
                args=(str(request.user.pk), date_from.isoformat(), date_to.isoformat()),
                task_id=task_id,
            )
        except Exception:
            logger.exception("Không đưa được tác vụ xuất báo cáo vào hàng đợi")
            cache.delete(_export_owner_key(task_id))
            return Response(
                {
                    "detail": "Hàng đợi tác vụ đang lỗi, vui lòng thử lại sau.",
                    "code": "queue_unavailable",
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        data = {"task_id": task_id, "status": "pending", "rows": None, "download_url": None}
        return Response(data, status=status.HTTP_202_ACCEPTED)


class ReportExportStatusAPIView(APIView):
    """Trạng thái tác vụ xuất báo cáo và đường dẫn tải khi đã xong."""

    permission_classes = [IsManager]

    @extend_schema(responses=ReportExportStatusSerializer)
    def get(self, request: Request, task_id: UUID) -> Response:
        result = _owned_export(request, task_id)
        state = EXPORT_STATES.get(result.state, "failure")
        data = {"task_id": str(task_id), "status": state, "rows": None, "download_url": None}
        if state == "success":
            data["rows"] = result.result["rows"]
            data["download_url"] = request.build_absolute_uri(
                f"/api/v1/reports/export/{task_id}/download/"
            )
        return Response(data, status=status.HTTP_200_OK)


class ReportExportDownloadAPIView(APIView):
    """Tải tệp Excel của tác vụ xuất báo cáo đã hoàn thành."""

    permission_classes = [IsManager]

    @extend_schema(responses={(200, XLSX_CONTENT_TYPE): bytes})
    def get(self, request: Request, task_id: UUID) -> FileResponse:
        result = _owned_export(request, task_id)
        if result.state != "SUCCESS":
            raise Http404
        name = result.result["file"]
        path = reports.report_path(name)
        if not path.is_file():
            raise Http404
        return FileResponse(
            path.open("rb"), as_attachment=True, filename=name, content_type=XLSX_CONTENT_TYPE
        )
