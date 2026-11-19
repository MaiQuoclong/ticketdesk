from pathlib import Path
from typing import Any

from rest_framework import serializers

from apps.tickets.models import Attachment, Category, Comment, Ticket, TicketHistory


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "description"]

    def validate_name(self, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise serializers.ValidationError("Tên danh mục không được để trống.")
        return cleaned


class TicketSerializer(serializers.ModelSerializer):
    short_id = serializers.CharField(read_only=True)
    created_by = serializers.StringRelatedField(read_only=True)
    created_by_id = serializers.UUIDField(read_only=True)
    assignee_username = serializers.CharField(
        source="assignee.username",
        read_only=True,
        default=None,
    )
    category_name = serializers.CharField(source="category.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    priority_display = serializers.CharField(source="get_priority_display", read_only=True)
    comment_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Ticket
        fields = [
            "id",
            "short_id",
            "title",
            "description",
            "status",
            "status_display",
            "priority",
            "priority_display",
            "category",
            "category_name",
            "created_by",
            "created_by_id",
            "assignee",
            "assignee_username",
            "comment_count",
            "resolved_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "short_id",
            "status",
            "status_display",
            "priority_display",
            "category_name",
            "created_by",
            "created_by_id",
            "assignee",
            "assignee_username",
            "comment_count",
            "resolved_at",
            "created_at",
            "updated_at",
        ]

    def validate_title(self, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 5:
            raise serializers.ValidationError("Tiêu đề tối thiểu 5 ký tự.")
        return cleaned


class TicketAssignSerializer(serializers.Serializer):
    agent_id = serializers.UUIDField(required=False)
    assignee_id = serializers.UUIDField(required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        target_id = attrs.get("agent_id") or attrs.get("assignee_id")
        if not target_id:
            raise serializers.ValidationError(
                {"agent_id": "Vui lòng cung cấp agent_id hoặc assignee_id."}
            )
        attrs["target_agent_id"] = target_id
        return attrs


class CommentSerializer(serializers.ModelSerializer):
    author = serializers.StringRelatedField(read_only=True)
    author_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Comment
        fields = [
            "id",
            "ticket",
            "author",
            "author_id",
            "content",
            "is_internal",
            "created_at",
        ]
        read_only_fields = ["id", "ticket", "author", "author_id", "created_at"]

    def validate_content(self, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise serializers.ValidationError("Nội dung bình luận không được để trống.")
        return cleaned


class AttachmentSerializer(serializers.ModelSerializer):
    MAX_FILE_SIZE = 5 * 1024 * 1024
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "pdf", "docx"}

    uploaded_by = serializers.StringRelatedField(read_only=True)
    uploaded_by_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Attachment
        fields = [
            "id",
            "ticket",
            "uploaded_by",
            "uploaded_by_id",
            "file",
            "original_name",
            "size",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "ticket",
            "uploaded_by",
            "uploaded_by_id",
            "original_name",
            "size",
            "created_at",
        ]

    def validate_file(self, value):
        ext = Path(value.name).suffix.lower().lstrip(".")
        if ext not in self.ALLOWED_EXTENSIONS:
            allowed = ", ".join(sorted(self.ALLOWED_EXTENSIONS))
            raise serializers.ValidationError(
                f"Định dạng tệp không hợp lệ. Chỉ cho phép: {allowed}."
            )
        if value.size > self.MAX_FILE_SIZE:
            raise serializers.ValidationError("File tối đa 5 MB.")
        return value


class TicketHistorySerializer(serializers.ModelSerializer):
    actor = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = TicketHistory
        fields = [
            "id",
            "ticket",
            "actor",
            "field",
            "old_value",
            "new_value",
            "created_at",
        ]
        read_only_fields = fields
