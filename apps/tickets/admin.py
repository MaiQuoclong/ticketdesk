from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import Attachment, Category, Comment, Ticket, TicketHistory


@admin.register(Category)
class CategoryAdmin(ModelAdmin):
    list_display = ["name", "description"]
    search_fields = ["name"]


class CommentInline(TabularInline):
    model = Comment
    extra = 0
    fields = ["author", "content", "is_internal", "created_at"]
    readonly_fields = ["created_at"]
    autocomplete_fields = ["author"]


@admin.register(Ticket)
class TicketAdmin(ModelAdmin):
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
    autocomplete_fields = ["assignee", "created_by", "category"]
    list_select_related = ["category", "created_by", "assignee"]
    list_filter_submit = True
    inlines = [CommentInline]


@admin.register(Comment)
class CommentAdmin(ModelAdmin):
    list_display = ["ticket", "author", "is_internal", "created_at"]
    list_filter = ["is_internal", "created_at"]
    search_fields = ["content"]
    list_select_related = ["ticket", "author"]
    autocomplete_fields = ["ticket", "author"]


@admin.register(Attachment)
class AttachmentAdmin(ModelAdmin):
    list_display = ["original_name", "ticket", "uploaded_by", "size", "created_at"]
    list_select_related = ["ticket", "uploaded_by"]


@admin.register(TicketHistory)
class TicketHistoryAdmin(ModelAdmin):
    list_display = ["ticket", "actor", "field", "old_value", "new_value", "created_at"]
    readonly_fields = ["ticket", "actor", "field", "old_value", "new_value", "created_at"]
    list_select_related = ["ticket", "actor"]
