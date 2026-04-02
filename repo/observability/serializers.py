from rest_framework import serializers

from observability.models import AuditLog, MetricsSnapshot, ReportExport
from observability.services import (
    METRICS_KEY_OPS_SUMMARY,
    REPORT_TYPE_AUDIT_LOG_CSV,
    REPORT_TYPE_METRICS_SNAPSHOT_JSON,
)


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = [
            "id",
            "organization",
            "actor_user",
            "action",
            "resource_type",
            "resource_id",
            "result",
            "request_id",
            "ip_address",
            "metadata",
            "before_data",
            "after_data",
            "created_at",
        ]


class MetricsSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = MetricsSnapshot
        fields = [
            "id",
            "organization",
            "metric_key",
            "payload",
            "captured_at",
            "created_at",
        ]


class MetricsSnapshotGenerateSerializer(serializers.Serializer):
    metric_key = serializers.ChoiceField(
        choices=[METRICS_KEY_OPS_SUMMARY],
        required=False,
        default=METRICS_KEY_OPS_SUMMARY,
    )


class ReportExportSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReportExport
        fields = [
            "id",
            "organization",
            "report_type",
            "status",
            "file_path",
            "generated_at",
            "requested_by_user_id",
            "report_metadata",
            "created_at",
        ]


class ReportExportCreateSerializer(serializers.Serializer):
    report_type = serializers.ChoiceField(
        choices=[REPORT_TYPE_AUDIT_LOG_CSV, REPORT_TYPE_METRICS_SNAPSHOT_JSON]
    )
