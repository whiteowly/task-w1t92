from django.core.validators import RegexValidator
from django.core.exceptions import ValidationError
from django.db import models

from common.models import TimestampedModel


class Organization(TimestampedModel):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=80, unique=True)
    timezone = models.CharField(max_length=64, default="UTC")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.slug})"


class TenantConfigVersion(TimestampedModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="config_versions",
    )
    version_number = models.PositiveIntegerField()
    config_payload = models.JSONField(default=dict)
    changed_by_user_id = models.BigIntegerField(null=True, blank=True)
    change_summary = models.CharField(max_length=255, blank=True)
    change_diff = models.JSONField(default=dict)
    rollback_deadline_at = models.DateTimeField()

    class Meta:
        unique_together = ("organization", "version_number")
        ordering = ["-version_number"]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValidationError("Tenant configuration versions are immutable.")
        return super().save(*args, **kwargs)

    def delete(self, using=None, keep_parents=False):
        raise ValidationError("Tenant configuration versions are immutable.")


class TenantEncryptionConfig(TimestampedModel):
    organization = models.OneToOneField(
        Organization,
        on_delete=models.CASCADE,
        related_name="encryption_config",
    )
    key_identifier = models.CharField(
        max_length=64,
        validators=[RegexValidator(regex=r"^[a-zA-Z0-9_\-]+$")],
    )
