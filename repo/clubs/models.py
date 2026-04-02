from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from common.models import OrganizationScopedModel


class MemberStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    PENDING = "pending", "Pending"
    SUSPENDED = "suspended", "Suspended"
    ALUMNI = "alumni", "Alumni"
    BANNED = "banned", "Banned"


class Club(OrganizationScopedModel):
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=64)

    class Meta:
        unique_together = ("organization", "code")


class Department(OrganizationScopedModel):
    club = models.ForeignKey(Club, on_delete=models.CASCADE, related_name="departments")
    name = models.CharField(max_length=255)


class Membership(OrganizationScopedModel):
    member = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships"
    )
    club = models.ForeignKey(Club, on_delete=models.CASCADE, related_name="memberships")
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="memberships",
    )
    status = models.CharField(
        max_length=16, choices=MemberStatus.choices, default=MemberStatus.PENDING
    )
    status_effective_date = models.DateField(null=True, blank=True)

    class Meta:
        unique_together = ("organization", "member", "club")


class MembershipStatusLog(OrganizationScopedModel):
    membership = models.ForeignKey(
        Membership, on_delete=models.CASCADE, related_name="status_logs"
    )
    from_status = models.CharField(max_length=16, choices=MemberStatus.choices)
    to_status = models.CharField(max_length=16, choices=MemberStatus.choices)
    reason_code = models.CharField(max_length=64)
    effective_date = models.DateField()
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="membership_status_changes",
    )

    class Meta:
        indexes = [
            models.Index(fields=["organization", "membership", "effective_date"]),
        ]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValidationError("Membership status logs are immutable.")
        return super().save(*args, **kwargs)

    def delete(self, using=None, keep_parents=False):
        raise ValidationError("Membership status logs are immutable.")


class MembershipTransferLog(OrganizationScopedModel):
    membership = models.ForeignKey(
        Membership, on_delete=models.CASCADE, related_name="transfer_logs"
    )
    from_club = models.ForeignKey(
        Club,
        on_delete=models.PROTECT,
        related_name="outgoing_transfers",
    )
    from_department = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        related_name="outgoing_transfers",
        null=True,
        blank=True,
    )
    to_club = models.ForeignKey(
        Club,
        on_delete=models.PROTECT,
        related_name="incoming_transfers",
    )
    to_department = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        related_name="incoming_transfers",
        null=True,
        blank=True,
    )
    reason_code = models.CharField(max_length=64)
    effective_date = models.DateField()
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="membership_transfer_changes",
    )

    class Meta:
        indexes = [
            models.Index(fields=["organization", "membership", "effective_date"]),
        ]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValidationError("Membership transfer logs are immutable.")
        return super().save(*args, **kwargs)

    def delete(self, using=None, keep_parents=False):
        raise ValidationError("Membership transfer logs are immutable.")
