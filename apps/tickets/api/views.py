from django.db.models import Count, IntegerField, OuterRef, ProtectedError, Subquery
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.models import User
from apps.tickets.models import Attachment, Category, Comment, Ticket
from apps.tickets.services import (
    TicketClosedError,
    add_comment,
    assign_ticket,
    change_ticket_status,
)

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
    TicketAssignSerializer,
    TicketHistorySerializer,
    TicketSerializer,
)


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
        if user.is_authenticated and user.role == User.Role.CUSTOMER:
            qs = qs.filter(created_by=user)

        comments = Comment.objects.filter(ticket=OuterRef("pk"))
        if user.is_authenticated and user.role == User.Role.CUSTOMER:
            comments = comments.filter(is_internal=False)
        comment_count = comments.order_by().values("ticket").annotate(n=Count("id")).values("n")
        return qs.annotate(
            comment_count=Coalesce(Subquery(comment_count, output_field=IntegerField()), 0)
        )

    def perform_create(self, serializer: TicketSerializer) -> None:
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer: TicketSerializer) -> None:
        if serializer.instance.status == Ticket.Status.CLOSED:
            raise TicketClosedError("Ticket đã đóng, không thể chỉnh sửa.")
        serializer.save()

    @action(detail=True, methods=["post"], permission_classes=[IsManager])
    def assign(self, request: Request, pk=None) -> Response:
        ticket = self.get_object()
        payload = TicketAssignSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        agent = get_object_or_404(
            User,
            pk=payload.validated_data["target_agent_id"],
            role=User.Role.AGENT,
        )
        try:
            ticket = assign_ticket(ticket=ticket, agent=agent, actor=request.user)
        except TicketClosedError as exc:
            return Response(
                {"detail": str(exc), "code": "ticket_closed"},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(self.get_serializer(ticket).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], permission_classes=[IsAgentOrManager])
    def resolve(self, request: Request, pk=None) -> Response:
        ticket = self.get_object()
        try:
            ticket = change_ticket_status(
                ticket=ticket,
                new_status=Ticket.Status.RESOLVED,
                actor=request.user,
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
        try:
            ticket = change_ticket_status(
                ticket=ticket,
                new_status=Ticket.Status.CLOSED,
                actor=request.user,
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
        if request.method == "GET":
            qs = ticket.comments.select_related("author").order_by("created_at")
            if request.user.role == User.Role.CUSTOMER:
                qs = qs.filter(is_internal=False)
            return Response(CommentSerializer(qs, many=True).data, status=status.HTTP_200_OK)

        serializer = CommentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            comment = add_comment(
                ticket=ticket,
                author=request.user,
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
        if user.is_authenticated and user.role == User.Role.CUSTOMER:
            qs = qs.filter(ticket__created_by=user)
        return qs
