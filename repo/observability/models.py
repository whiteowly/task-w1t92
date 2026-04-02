from django.conf import settings
from django.db import models

from common.models import TimestampedModel


class AuditLog(TimestampedModel):
    organization = models.ForeignKey(
        "tenancy.Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=128)
    resource_type = models.CharField(max_length=64, blank=True)
    resource_id = models.CharField(max_length=64, blank=True)
    result = models.CharField(max_length=32, default="success")
    request_id = models.CharField(max_length=64, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    metadata = models.JSONField(default=dict)
    before_data = models.JSONField(default=dict)
    after_data = models.JSONField(default=dict)

    class Meta:
        indexes = [
            models.Index(fields=["organization", "created_at"]),
            models.Index(fields=["action", "created_at"]),
        ]


class MetricsSnapshot(TimestampedModel):
    organization = models.ForeignKey(
        "tenancy.Organization",
        on_delete=models.CASCADE,
        related_name="metrics_snapshots",
        null=True,
        blank=True,
    )
    metric_key = models.CharField(max_length=128)
    payload = models.JSONField(default=dict)
    captured_at = models.DateTimeField()

    class Meta:
        indexes = [
            models.Index(fields=["organization", "metric_key", "captured_at"]),
        ]


class ReportExport(TimestampedModel):
    organization = models.ForeignKey(
        "tenancy.Organization",
        on_delete=models.CASCADE,
        related_name="report_exports",
    )
    report_type = models.CharField(max_length=64)
    status = models.CharField(max_length=32, default="pending")
    file_path = models.CharField(max_length=512, blank=True)
    generated_at = models.DateTimeField(null=True, blank=True)
    requested_by_user_id = models.BigIntegerField(null=True, blank=True)
    report_metadata = models.JSONField(default=dict)

    class Meta:
        indexes = [
            models.Index(fields=["organization", "status", "created_at"]),
        ]
