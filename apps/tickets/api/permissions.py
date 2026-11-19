from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.accounts.models import User


class IsManager(BasePermission):
    """Chỉ cho phép người dùng có vai trò Quản lý hoặc Superuser."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        user = request.user
        return bool(
            user and user.is_authenticated and (user.role == User.Role.MANAGER or user.is_superuser)
        )


class IsManagerOrReadOnly(BasePermission):
    """Mọi người dùng đăng nhập được đọc; chỉ Quản lý được thêm, sửa, xóa."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return bool(user.role == User.Role.MANAGER or user.is_superuser)


class IsAgentOrManager(BasePermission):
    """Cho phép Nhân viên hỗ trợ hoặc Quản lý thực hiện thao tác."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (user.role in (User.Role.AGENT, User.Role.MANAGER) or user.is_superuser)
        )


class IsStaffOrOwnerReadOnly(BasePermission):
    """Nhân viên/quản lý toàn quyền (xóa chỉ quản lý); khách hàng chỉ đọc và sửa ticket của mình."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request: Request, view: APIView, obj) -> bool:
        user = request.user
        if request.method == "DELETE":
            return bool(user.role == User.Role.MANAGER or user.is_superuser)
        if user.role in (User.Role.AGENT, User.Role.MANAGER) or user.is_superuser:
            return True
        return bool(
            obj.created_by_id == user.id
            and (request.method in SAFE_METHODS or request.method in ("PATCH", "PUT"))
        )


class IsOwnerOrManager(BasePermission):
    """Cho phép chủ sở hữu ticket hoặc Quản lý thực hiện thao tác (ví dụ đóng ticket)."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request: Request, view: APIView, obj) -> bool:
        user = request.user
        return bool(
            user.role == User.Role.MANAGER or user.is_superuser or obj.created_by_id == user.id
        )


class IsUploaderOrManager(BasePermission):
    """Chỉ người tải tệp lên hoặc Quản lý mới được xóa tệp đính kèm."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request: Request, view: APIView, obj) -> bool:
        user = request.user
        return bool(
            user.role == User.Role.MANAGER or user.is_superuser or obj.uploaded_by_id == user.id
        )
