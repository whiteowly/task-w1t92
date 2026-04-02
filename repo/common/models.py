from django.db import models

from common.managers import OrganizationScopedManager


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class OrganizationScopedModel(TimestampedModel):
    organization = models.ForeignKey(
        "tenancy.Organization",
        on_delete=models.PROTECT,
        db_index=True,
        related_name="%(app_label)s_%(class)s_items",
    )

    objects = OrganizationScopedManager()

    class Meta:
        abstract = True
