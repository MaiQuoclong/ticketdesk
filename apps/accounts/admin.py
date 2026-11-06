from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ["username", "email", "role", "is_staff", "is_active"]
    list_filter = ["role", "is_staff", "is_active"]
    fieldsets = BaseUserAdmin.fieldsets + (("Phân quyền TicketDesk", {"fields": ("role",)}),)
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ("Phân quyền TicketDesk", {"fields": ("role",)}),
    )
    search_fields = ["username", "email", "first_name", "last_name"]
