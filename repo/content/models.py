from django.core.exceptions import ValidationError
from django.db import models

from common.models import OrganizationScopedModel


class AssetState(models.TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"


class ContentAsset(OrganizationScopedModel):
    external_id = models.CharField(max_length=128)
    title = models.CharField(max_length=255)
    creator = models.CharField(max_length=255, blank=True)
    period = models.CharField(max_length=255, blank=True)
    style = models.CharField(max_length=255, blank=True)
    medium = models.CharField(max_length=255, blank=True)
    size = models.CharField(max_length=255, blank=True)
    source = models.CharField(max_length=255, blank=True)
    copyright_status = models.CharField(max_length=255, blank=True)
    tags = models.JSONField(default=list)
    state = models.CharField(
        max_length=16, choices=AssetState.choices, default=AssetState.DRAFT
    )
    version = models.PositiveIntegerField(default=1)
    allow_download = models.BooleanField(default=False)
    allow_share = models.BooleanField(default=False)
    storage_path = models.CharField(max_length=512, blank=True)

    class Meta:
        unique_together = ("organization", "external_id")
        indexes = [
            models.Index(fields=["organization", "state"]),
            models.Index(fields=["organization", "title"]),
        ]


class ContentChapter(OrganizationScopedModel):
    asset = models.ForeignKey(
        ContentAsset,
        on_delete=models.CASCADE,
        related_name="chapters",
    )
    title = models.CharField(max_length=255)
    order_index = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("organization", "asset", "order_index")
        indexes = [
            models.Index(fields=["organization", "asset", "order_index"]),
        ]


class ChapterACLPrincipal(models.TextChoices):
    ROLE = "role", "Role"
    USER = "user", "User"


class ContentChapterACL(OrganizationScopedModel):
    chapter = models.ForeignKey(
        ContentChapter,
        on_delete=models.CASCADE,
        related_name="acl_entries",
    )
    principal_type = models.CharField(max_length=8, choices=ChapterACLPrincipal.choices)
    principal_value = models.CharField(max_length=64)
    can_view = models.BooleanField(default=True)

    class Meta:
        unique_together = (
            "organization",
            "chapter",
            "principal_type",
            "principal_value",
        )
        indexes = [
            models.Index(fields=["organization", "chapter"]),
            models.Index(fields=["organization", "principal_type", "principal_value"]),
        ]


class ContentAssetVersionLog(OrganizationScopedModel):
    asset = models.ForeignKey(
        ContentAsset,
        on_delete=models.CASCADE,
        related_name="version_logs",
    )
    version = models.PositiveIntegerField()
    state = models.CharField(max_length=16, choices=AssetState.choices)
    changed_by = models.ForeignKey(
        "iam.User",
        on_delete=models.PROTECT,
        related_name="content_version_changes",
    )
    change_reason = models.CharField(max_length=128)
    snapshot = models.JSONField(default=dict)

    class Meta:
        unique_together = ("organization", "asset", "version")
        indexes = [
            models.Index(fields=["organization", "asset", "version"]),
        ]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValidationError("Asset version logs are immutable.")
        return super().save(*args, **kwargs)

    def delete(self, using=None, keep_parents=False):
        raise ValidationError("Asset version logs are immutable.")


class EntitlementSource(models.TextChoices):
    SUBSCRIPTION = "subscription", "Subscription"
    REDEEM_CODE = "redeem_code", "Redeem code"


class ContentEntitlement(OrganizationScopedModel):
    user = models.ForeignKey(
        "iam.User",
        on_delete=models.CASCADE,
        related_name="content_entitlements",
    )
    asset = models.ForeignKey(
        ContentAsset,
        on_delete=models.CASCADE,
        related_name="entitlements",
    )
    source = models.CharField(max_length=32, choices=EntitlementSource.choices)
    is_active = models.BooleanField(default=True)
    granted_by = models.ForeignKey(
        "iam.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="granted_content_entitlements",
    )
    redeem_code_id = models.BigIntegerField(null=True, blank=True)

    class Meta:
        unique_together = ("organization", "user", "asset", "source")
        indexes = [
            models.Index(fields=["organization", "user", "asset", "is_active"]),
            models.Index(fields=["organization", "source", "is_active"]),
        ]


class ContentRedeemCode(OrganizationScopedModel):
    asset = models.ForeignKey(
        ContentAsset,
        on_delete=models.CASCADE,
        related_name="redeem_codes",
    )
    code_hash = models.CharField(max_length=64)
    code_last4 = models.CharField(max_length=4)
    expires_at = models.DateTimeField()
    redeemed_at = models.DateTimeField(null=True, blank=True)
    redeemed_by = models.ForeignKey(
        "iam.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="redeemed_content_codes",
    )
    created_by = models.ForeignKey(
        "iam.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_content_codes",
    )

    class Meta:
        unique_together = ("organization", "code_hash")
        indexes = [
            models.Index(fields=["organization", "asset", "expires_at"]),
            models.Index(fields=["organization", "redeemed_at"]),
        ]


class DownloadTokenPurpose(models.TextChoices):
    DOWNLOAD = "download", "Download"
    SHARE = "share", "Share"


class ContentDownloadToken(OrganizationScopedModel):
    user = models.ForeignKey(
        "iam.User",
        on_delete=models.CASCADE,
        related_name="content_download_tokens",
    )
    asset = models.ForeignKey(
        ContentAsset,
        on_delete=models.CASCADE,
        related_name="download_tokens",
    )
    token_hash = models.CharField(max_length=64)
    token_hint = models.CharField(max_length=16)
    purpose = models.CharField(max_length=16, choices=DownloadTokenPurpose.choices)
    expires_at = models.DateTimeField()

    class Meta:
        unique_together = ("organization", "token_hash")
        indexes = [
            models.Index(fields=["organization", "user", "expires_at"]),
            models.Index(fields=["organization", "asset", "expires_at"]),
        ]


class ContentDownloadRequestLog(OrganizationScopedModel):
    user = models.ForeignKey(
        "iam.User",
        on_delete=models.CASCADE,
        related_name="content_download_request_logs",
    )
    asset = models.ForeignKey(
        ContentAsset,
        on_delete=models.CASCADE,
        related_name="download_request_logs",
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=32)

    class Meta:
        indexes = [
            models.Index(fields=["organization", "user", "requested_at"]),
            models.Index(fields=["organization", "asset", "requested_at"]),
        ]


class ContentArtifact(OrganizationScopedModel):
    asset = models.ForeignKey(
        ContentAsset,
        on_delete=models.CASCADE,
        related_name="artifacts",
    )
    user = models.ForeignKey(
        "iam.User",
        on_delete=models.CASCADE,
        related_name="content_artifacts",
    )
    token = models.ForeignKey(
        ContentDownloadToken,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="artifacts",
    )
    source_path = models.CharField(max_length=512)
    artifact_path = models.CharField(max_length=512)
    mime_type = models.CharField(max_length=64)

    class Meta:
        indexes = [
            models.Index(fields=["organization", "asset", "created_at"]),
            models.Index(fields=["organization", "user", "created_at"]),
        ]
