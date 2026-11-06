from django.contrib import admin

from .models import Attachment, Category, Comment, Ticket, TicketHistory


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "description"]
    search_fields = ["name"]


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = [
        "short_id",
        "title",
        "status",
        "priority",
        "category",
        "created_by",
        "assignee",
        "created_at",
    ]
    list_filter = ["status", "priority", "category"]
    search_fields = ["title", "description"]
    autocomplete_fields = ["assignee", "created_by"]


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ["ticket", "author", "is_internal", "created_at"]
    list_filter = ["is_internal", "created_at"]
    search_fields = ["content"]


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ["original_name", "ticket", "uploaded_by", "size", "created_at"]


@admin.register(TicketHistory)
class TicketHistoryAdmin(admin.ModelAdmin):
    list_display = ["ticket", "actor", "field", "old_value", "new_value", "created_at"]
    readonly_fields = ["ticket", "actor", "field", "old_value", "new_value", "created_at"]
