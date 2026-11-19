from django.db.models import ProtectedError
from rest_framework import status, viewsets
from rest_framework.request import Request
from rest_framework.response import Response

from apps.tickets.models import Category

from .permissions import IsManagerOrReadOnly
from .serializers import CategorySerializer


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
