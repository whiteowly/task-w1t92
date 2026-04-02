from django.contrib import admin

from observability.models import AuditLog, MetricsSnapshot, ReportExport


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "organization",
        "actor_user",
        "action",
        "result",
        "created_at",
    )
    list_filter = ("organization", "result", "action")
    search_fields = ("action", "request_id", "resource_id")


@admin.register(MetricsSnapshot)
class MetricsSnapshotAdmin(admin.ModelAdmin):
    list_display = ("id", "organization", "metric_key", "captured_at", "created_at")
    list_filter = ("organization", "metric_key")


@admin.register(ReportExport)
class ReportExportAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "organization",
        "report_type",
        "status",
        "generated_at",
        "created_at",
    )
    list_filter = ("organization", "status", "report_type")
