from django.contrib.auth import get_user_model
from rest_framework import serializers

from common.constants import RoleCode
from content.models import (
    AssetState,
    ChapterACLPrincipal,
    ContentAsset,
    ContentAssetVersionLog,
    ContentDownloadToken,
    ContentEntitlement,
    ContentChapter,
    ContentChapterACL,
    ContentRedeemCode,
    DownloadTokenPurpose,
)
from content.storage_paths import normalize_storage_path

User = get_user_model()


class ContentAssetSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentAsset
        fields = [
            "id",
            "external_id",
            "title",
            "creator",
            "period",
            "style",
            "medium",
            "size",
            "source",
            "copyright_status",
            "tags",
            "state",
            "version",
            "allow_download",
            "allow_share",
            "storage_path",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "state", "version", "created_at", "updated_at"]

    def validate_tags(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("tags must be a list of strings.")
        return [str(item).strip() for item in value if str(item).strip()]

    def validate_storage_path(self, value):
        try:
            return normalize_storage_path(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc


class ContentChapterSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentChapter
        fields = ["id", "asset", "title", "order_index", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_asset(self, value):
        request = self.context["request"]
        if value.organization_id != request.organization.id:
            raise serializers.ValidationError("Asset is outside active organization.")
        return value


class ContentChapterACLSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentChapterACL
        fields = [
            "id",
            "chapter",
            "principal_type",
            "principal_value",
            "can_view",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        request = self.context["request"]
        chapter = attrs.get("chapter") or getattr(self.instance, "chapter", None)
        if chapter and chapter.organization_id != request.organization.id:
            raise serializers.ValidationError(
                {"chapter": "Chapter is outside active organization."}
            )

        principal_type = attrs.get(
            "principal_type", getattr(self.instance, "principal_type", None)
        )
        principal_value = attrs.get(
            "principal_value", getattr(self.instance, "principal_value", None)
        )

        if principal_type == ChapterACLPrincipal.ROLE:
            valid_roles = {role.value for role in RoleCode}
            if principal_value not in valid_roles:
                raise serializers.ValidationError(
                    {"principal_value": "Invalid role code for chapter ACL."}
                )
        elif principal_type == ChapterACLPrincipal.USER:
            try:
                user_id = int(principal_value)
            except (TypeError, ValueError) as exc:
                raise serializers.ValidationError(
                    {"principal_value": "User principal_value must be user id string."}
                ) from exc
            user = User.objects.filter(id=user_id).first()
            if user is None:
                raise serializers.ValidationError(
                    {"principal_value": "Referenced user does not exist."}
                )
            in_org = user.organization_roles.filter(
                organization=request.organization,
                is_active=True,
            ).exists()
            if not in_org:
                raise serializers.ValidationError(
                    {
                        "principal_value": "Referenced user is outside active organization."
                    }
                )
        return attrs


class ContentAssetVersionLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentAssetVersionLog
        fields = [
            "id",
            "asset",
            "version",
            "state",
            "changed_by",
            "change_reason",
            "snapshot",
            "created_at",
        ]


class AssetPublishSerializer(serializers.Serializer):
    pass


class ContentEntitlementSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentEntitlement
        fields = [
            "id",
            "user",
            "asset",
            "source",
            "is_active",
            "granted_by",
            "redeem_code_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "source",
            "granted_by",
            "redeem_code_id",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        request = self.context["request"]
        user = attrs.get("user")
        asset = attrs.get("asset")
        if asset and asset.organization_id != request.organization.id:
            raise serializers.ValidationError(
                {"asset": "Asset is outside active organization."}
            )
        if (
            user
            and not user.organization_roles.filter(
                organization=request.organization,
                is_active=True,
            ).exists()
        ):
            raise serializers.ValidationError(
                {"user": "User is outside active organization."}
            )
        return attrs


class ContentRedeemCodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentRedeemCode
        fields = [
            "id",
            "asset",
            "code_last4",
            "expires_at",
            "redeemed_at",
            "redeemed_by",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "code_last4",
            "redeemed_at",
            "redeemed_by",
            "created_at",
        ]

    def validate_asset(self, value):
        request = self.context["request"]
        if value.organization_id != request.organization.id:
            raise serializers.ValidationError("Asset is outside active organization.")
        return value


class ContentRedeemCodeCreateSerializer(serializers.Serializer):
    asset = serializers.PrimaryKeyRelatedField(queryset=ContentAsset.objects.all())
    expires_at = serializers.DateTimeField(required=False)

    def validate_asset(self, value):
        request = self.context["request"]
        if value.organization_id != request.organization.id:
            raise serializers.ValidationError("Asset is outside active organization.")
        return value


class ContentRedeemCodeRedeemSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=12, min_length=12)


class ContentDownloadTokenCreateSerializer(serializers.Serializer):
    asset = serializers.PrimaryKeyRelatedField(queryset=ContentAsset.objects.all())
    purpose = serializers.ChoiceField(
        choices=DownloadTokenPurpose.choices,
        default=DownloadTokenPurpose.DOWNLOAD,
    )

    def validate_asset(self, value):
        request = self.context["request"]
        if value.organization_id != request.organization.id:
            raise serializers.ValidationError("Asset is outside active organization.")
        return value


class ContentDownloadTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentDownloadToken
        fields = [
            "id",
            "asset",
            "token_hint",
            "purpose",
            "expires_at",
            "created_at",
        ]


class AssetImportItemSerializer(serializers.Serializer):
    external_id = serializers.CharField(max_length=128)
    title = serializers.CharField(max_length=255)
    creator = serializers.CharField(max_length=255, allow_blank=True, required=False)
    period = serializers.CharField(max_length=255, allow_blank=True, required=False)
    style = serializers.CharField(max_length=255, allow_blank=True, required=False)
    medium = serializers.CharField(max_length=255, allow_blank=True, required=False)
    size = serializers.CharField(max_length=255, allow_blank=True, required=False)
    source = serializers.CharField(max_length=255, allow_blank=True, required=False)
    copyright_status = serializers.CharField(
        max_length=255, allow_blank=True, required=False
    )
    tags = serializers.ListField(
        child=serializers.CharField(max_length=64), required=False
    )
    state = serializers.ChoiceField(choices=AssetState.choices, required=False)
    allow_download = serializers.BooleanField(required=False)
    allow_share = serializers.BooleanField(required=False)
    storage_path = serializers.CharField(
        max_length=512, allow_blank=True, required=False
    )

    def validate_storage_path(self, value):
        try:
            return normalize_storage_path(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc


class AssetImportJSONSerializer(serializers.Serializer):
    items = serializers.ListField(child=serializers.DictField())


class AssetImportCSVSerializer(serializers.Serializer):
    file = serializers.FileField(required=False)
    csv_content = serializers.CharField(required=False, allow_blank=False)

    def validate(self, attrs):
        if not attrs.get("file") and not attrs.get("csv_content"):
            raise serializers.ValidationError(
                "Provide either a CSV file upload or csv_content string."
            )
        return attrs
