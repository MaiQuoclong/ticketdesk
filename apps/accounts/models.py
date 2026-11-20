import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        CUSTOMER = "customer", "Khách hàng"
        AGENT = "agent", "Nhân viên hỗ trợ"
        MANAGER = "manager", "Quản lý"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.CharField(
        "Vai trò",
        max_length=20,
        choices=Role.choices,
        default=Role.CUSTOMER,
    )

    class Meta:
        verbose_name = "Người dùng"
        verbose_name_plural = "Người dùng"

    def __str__(self) -> str:
        return f"{self.username} ({self.get_role_display()})"


class RefreshToken(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="refresh_tokens",
        verbose_name="Người dùng",
    )
    token = models.TextField("Refresh Token", unique=True)
    expires_at = models.DateTimeField("Thời điểm hết hạn")
    is_revoked = models.BooleanField("Đã thu hồi", default=False)
    created_at = models.DateTimeField("Ngày tạo", auto_now_add=True)

    class Meta:
        verbose_name = "Refresh Token"
        verbose_name_plural = "Refresh Token"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        state = "Đã thu hồi" if self.is_revoked else "Hợp lệ"
        return f"{self.user.username} ({state})"
