import uuid

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models


class Category(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField("Tên danh mục", max_length=100, unique=True)
    description = models.TextField("Mô tả", blank=True)

    class Meta:
        verbose_name = "Danh mục"
        verbose_name_plural = "Danh mục"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Ticket(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "Mới"
        IN_PROGRESS = "in_progress", "Đang xử lý"
        RESOLVED = "resolved", "Đã xử lý"
        CLOSED = "closed", "Đã đóng"

    class Priority(models.IntegerChoices):
        LOW = 1, "Thấp"
        MEDIUM = 2, "Trung bình"
        HIGH = 3, "Cao"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField("Tiêu đề", max_length=200)
    description = models.TextField("Mô tả")
    status = models.CharField(
        "Trạng thái",
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
    )
    priority = models.IntegerField(
        "Mức độ ưu tiên",
        choices=Priority.choices,
        default=Priority.MEDIUM,
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="tickets",
        verbose_name="Danh mục",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_tickets",
        verbose_name="Người tạo",
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_tickets",
        verbose_name="Người xử lý",
    )
    resolved_at = models.DateTimeField("Thời điểm xử lý xong", null=True, blank=True)
    created_at = models.DateTimeField("Ngày tạo", auto_now_add=True)
    updated_at = models.DateTimeField("Cập nhật lần cuối", auto_now=True)

    class Meta:
        verbose_name = "Ticket"
        verbose_name_plural = "Ticket"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"], name="ticket_status_created_idx"),
            models.Index(fields=["assignee", "status"], name="ticket_assignee_status_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=~models.Q(title=""), name="ticket_title_not_empty"),
            models.CheckConstraint(
                condition=models.Q(priority__in=[1, 2, 3]), name="ticket_priority_valid"
            ),
        ]

    @property
    def short_id(self) -> str:
        return f"TD-{str(self.id)[:6].upper()}"

    def __str__(self) -> str:
        return f"#{self.short_id} {self.title}"


class Comment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.CASCADE,
        related_name="comments",
        verbose_name="Ticket",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="comments",
        verbose_name="Tác giả",
    )
    content = models.TextField("Nội dung bình luận")
    is_internal = models.BooleanField("Ghi chú nội bộ (ẩn với khách hàng)", default=False)
    created_at = models.DateTimeField("Thời gian", auto_now_add=True)

    class Meta:
        verbose_name = "Bình luận"
        verbose_name_plural = "Bình luận"
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"Bình luận của {self.author} trên {self.ticket.short_id}"


class Attachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.CASCADE,
        related_name="attachments",
        verbose_name="Ticket",
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="attachments",
        verbose_name="Người tải lên",
    )
    file = models.FileField(
        "Tệp đính kèm",
        upload_to="attachments/%Y/%m/",
        validators=[FileExtensionValidator(["png", "jpg", "jpeg", "pdf", "docx"])],
    )
    original_name = models.CharField("Tên tệp gốc", max_length=255)
    size = models.PositiveIntegerField("Dung lượng (bytes)", default=0)
    created_at = models.DateTimeField("Thời gian tải lên", auto_now_add=True)

    class Meta:
        verbose_name = "Tệp đính kèm"
        verbose_name_plural = "Tệp đính kèm"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.original_name


class TicketHistory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.CASCADE,
        related_name="histories",
        verbose_name="Ticket",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="ticket_histories",
        verbose_name="Người thực hiện",
    )
    field = models.CharField("Trường thay đổi", max_length=50)
    old_value = models.TextField("Giá trị cũ", blank=True)
    new_value = models.TextField("Giá trị mới", blank=True)
    created_at = models.DateTimeField("Thời gian", auto_now_add=True)

    class Meta:
        verbose_name = "Lịch sử Ticket"
        verbose_name_plural = "Lịch sử Ticket"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.ticket.short_id}: {self.field} ({self.old_value} -> {self.new_value})"
