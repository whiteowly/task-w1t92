from django.contrib import admin

from scheduler.models import ScheduledJob


@admin.register(ScheduledJob)
class ScheduledJobAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "handler",
        "interval_seconds",
        "next_run_at",
        "is_enabled",
        "last_error",
    )
    list_filter = ("is_enabled",)
    search_fields = ("code", "handler")
