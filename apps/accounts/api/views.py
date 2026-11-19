from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User

from .serializers import (
    LoginSerializer,
    LogoutSerializer,
    TokenRefreshSerializer,
    UserSerializer,
)


class LoginAPIView(APIView):
    """Đăng nhập bằng username và password, cấp cặp JWT và lưu RefreshToken."""

    permission_classes = [AllowAny]
    serializer_class = LoginSerializer

    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class RefreshAPIView(APIView):
    """Cấp Access Token mới từ Refresh Token chưa bị thu hồi."""

    permission_classes = [AllowAny]
    serializer_class = TokenRefreshSerializer

    def post(self, request: Request) -> Response:
        serializer = TokenRefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class LogoutAPIView(APIView):
    """Thu hồi Refresh Token khi người dùng đăng xuất."""

    permission_classes = [IsAuthenticated]
    serializer_class = LogoutSerializer

    def post(self, request: Request) -> Response:
        serializer = LogoutSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeAPIView(APIView):
    """Trả về thông tin cá nhân của tài khoản đang đăng nhập."""

    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer

    def get(self, request: Request) -> Response:
        return Response(UserSerializer(request.user).data, status=status.HTTP_200_OK)


class AgentListAPIView(generics.ListAPIView):
    """Danh sách nhân viên kỹ thuật đang hoạt động phục vụ thao tác gán ticket."""

    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer
    pagination_class = None

    def get_queryset(self):
        user = self.request.user
        if user.role not in (User.Role.AGENT, User.Role.MANAGER) and not user.is_staff:
            raise PermissionDenied("Chỉ nhân viên hỗ trợ hoặc quản lý mới được xem danh sách này.")
        return User.objects.filter(role=User.Role.AGENT, is_active=True).order_by("username")
