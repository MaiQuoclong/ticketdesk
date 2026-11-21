from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from unfold.admin import ModelAdmin
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from .models import RefreshToken, User

admin.site.unregister(Group)


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm
    list_display = ["username", "email", "role", "is_staff", "is_active"]
    list_filter = ["role", "is_staff", "is_active"]
    fieldsets = tuple(BaseUserAdmin.fieldsets or ()) + (
        ("Phân quyền TicketDesk", {"fields": ("role",)}),
    )
    add_fieldsets = tuple(BaseUserAdmin.add_fieldsets) + (
        ("Phân quyền TicketDesk", {"fields": ("role",)}),
    )
    search_fields = ["username", "email", "first_name", "last_name"]


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    pass


@admin.register(RefreshToken)
class RefreshTokenAdmin(ModelAdmin):
    list_display = ["user", "is_revoked", "expires_at", "created_at"]
    list_filter = ["is_revoked", "created_at"]
    search_fields = ["user__username", "user__email"]
    list_select_related = ["user"]
