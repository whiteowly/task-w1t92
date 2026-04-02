from django.db import models

from common.models import TimestampedModel


class ScheduledJob(TimestampedModel):
    code = models.CharField(max_length=128, unique=True)
    description = models.CharField(max_length=255, blank=True)
    handler = models.CharField(max_length=255)
    interval_seconds = models.PositiveIntegerField(default=300)
    next_run_at = models.DateTimeField(db_index=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    is_enabled = models.BooleanField(default=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.CharField(max_length=128, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["is_enabled", "next_run_at"]),
        ]
