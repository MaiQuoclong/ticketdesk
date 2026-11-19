from django.db.models import Count, IntegerField, OuterRef, ProtectedError, Subquery
from django.db.models.functions import Coalesce
from rest_framework import status, viewsets
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.models import User
from apps.tickets.models import Category, Comment, Ticket
from apps.tickets.services import TicketClosedError

from .permissions import IsManagerOrReadOnly, IsStaffOrOwnerReadOnly
from .serializers import CategorySerializer, TicketSerializer


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
    """CRUD Ticket với phân trang, lọc, tìm kiếm, sắp xếp và lọc get_queryset chống IDOR."""

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
