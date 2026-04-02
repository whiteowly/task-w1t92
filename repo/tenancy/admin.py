from django.contrib import admin

from tenancy.models import Organization, TenantConfigVersion, TenantEncryptionConfig


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "slug", "timezone", "is_active", "created_at")
    search_fields = ("name", "slug")


@admin.register(TenantConfigVersion)
class TenantConfigVersionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "organization",
        "version_number",
        "created_at",
        "rollback_deadline_at",
    )
    list_filter = ("organization",)


@admin.register(TenantEncryptionConfig)
class TenantEncryptionConfigAdmin(admin.ModelAdmin):
    list_display = ("id", "organization", "key_identifier", "created_at")
