from rest_framework import serializers

from tenancy.models import Organization, TenantConfigVersion


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ["id", "name", "slug", "timezone", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class TenantConfigUpdateSerializer(serializers.Serializer):
    config_patch = serializers.JSONField()
    change_summary = serializers.CharField(
        max_length=255, required=False, allow_blank=True
    )

    def validate_config_patch(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("config_patch must be a JSON object.")
        return value


class TenantConfigVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = TenantConfigVersion
        fields = [
            "id",
            "version_number",
            "config_payload",
            "changed_by_user_id",
            "change_summary",
            "change_diff",
            "rollback_deadline_at",
            "created_at",
        ]


class TenantConfigRollbackSerializer(serializers.Serializer):
    change_summary = serializers.CharField(
        max_length=255, required=False, allow_blank=True
    )
