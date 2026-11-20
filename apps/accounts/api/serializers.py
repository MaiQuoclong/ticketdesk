from typing import Any

from django.conf import settings
from django.contrib.auth import authenticate
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken as SimpleJWTRefreshToken

from apps.accounts.models import RefreshToken, User


class UserSerializer(serializers.ModelSerializer):
    role_display = serializers.CharField(source="get_role_display", read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "role",
            "role_display",
            "is_active",
            "date_joined",
        ]
        read_only_fields = fields


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        request = self.context.get("request")
        user = authenticate(
            request=request,
            username=attrs["username"],
            password=attrs["password"],
        )
        if user is None or not user.is_active:
            raise AuthenticationFailed(
                "Tên đăng nhập hoặc mật khẩu không đúng.",
                code="invalid_credentials",
            )

        jwt_refresh = SimpleJWTRefreshToken.for_user(user)
        refresh_str = str(jwt_refresh)
        access_str = str(jwt_refresh.access_token)
        lifetime = settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"]

        RefreshToken.objects.create(
            user=user,
            token=refresh_str,
            expires_at=timezone.now() + lifetime,
        )

        return {
            "access": access_str,
            "refresh": refresh_str,
            "user": UserSerializer(user).data,
        }


class TokenRefreshSerializer(serializers.Serializer):
    refresh = serializers.CharField()

    def validate(self, attrs: dict[str, Any]) -> dict[str, str]:
        token_str = attrs["refresh"]
        try:
            jwt_refresh = SimpleJWTRefreshToken(token_str)
        except TokenError as exc:
            raise AuthenticationFailed(
                "Refresh token không hợp lệ hoặc đã hết hạn.",
                code="token_not_valid",
            ) from exc

        record = RefreshToken.objects.filter(token=token_str).first()
        if record is None or record.is_revoked or record.expires_at <= timezone.now():
            raise AuthenticationFailed(
                "Refresh token đã bị thu hồi hoặc hết hạn.",
                code="token_revoked",
            )

        return {"access": str(jwt_refresh.access_token)}


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()

    def save(self, **kwargs: Any) -> None:
        token_str = self.validated_data["refresh"]
        user = self.context["request"].user
        record = RefreshToken.objects.filter(token=token_str, user=user).first()
        if record is None:
            raise AuthenticationFailed(
                "Refresh token không hợp lệ.",
                code="token_not_valid",
            )
        if not record.is_revoked:
            record.is_revoked = True
            record.save(update_fields=["is_revoked"])
