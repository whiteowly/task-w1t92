from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from iam.models import AuthSession, LoginFailure, Role, User, UserOrganizationRole


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ("username",)
    list_display = (
        "id",
        "username",
        "full_name",
        "is_active",
        "is_staff",
        "created_at",
    )
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Personal info", {"fields": ("full_name", "email")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login",)}),
    )
    add_fieldsets = (
        (
            None,
            {"classes": ("wide",), "fields": ("username", "password1", "password2")},
        ),
    )
    search_fields = ("username", "full_name")


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "created_at")
    search_fields = ("code", "name")


@admin.register(UserOrganizationRole)
class UserOrganizationRoleAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "role", "is_active", "created_at")
    list_filter = ("organization", "role", "is_active")


@admin.register(AuthSession)
class AuthSessionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "organization",
        "expires_at",
        "revoked_at",
        "created_at",
    )
    list_filter = ("organization",)
    search_fields = ("session_key", "user__username")


@admin.register(LoginFailure)
class LoginFailureAdmin(admin.ModelAdmin):
    list_display = (
        "username",
        "organization",
        "failed_attempts",
        "locked_until",
        "last_failed_at",
    )
    list_filter = ("organization",)
