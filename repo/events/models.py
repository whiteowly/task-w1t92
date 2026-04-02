from django.conf import settings
from django.db import models

from common.models import OrganizationScopedModel


class Event(OrganizationScopedModel):
    club = models.ForeignKey(
        "clubs.Club", on_delete=models.CASCADE, related_name="events"
    )
    title = models.CharField(max_length=255)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    eligible_member_count_snapshot = models.PositiveIntegerField(default=0)

    class Meta:
        indexes = [
            models.Index(fields=["organization", "club", "starts_at"]),
        ]


class EventRegistration(OrganizationScopedModel):
    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name="registrations"
    )
    member = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="event_registrations",
    )
    registered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("organization", "event", "member")
        indexes = [
            models.Index(fields=["organization", "event", "registered_at"]),
            models.Index(fields=["organization", "member", "registered_at"]),
        ]


class EventCheckIn(OrganizationScopedModel):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="checkins")
    member = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="event_checkins",
    )
    checked_in_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("organization", "event", "member")
        indexes = [
            models.Index(fields=["organization", "event", "checked_in_at"]),
            models.Index(fields=["organization", "member", "checked_in_at"]),
        ]


class ReconciliationAction(models.TextChoices):
    MARK_CHECKED_IN = "mark_checked_in", "Mark checked in"
    REMOVE_CHECK_IN = "remove_check_in", "Remove check-in"


class EventAttendanceReconciliation(OrganizationScopedModel):
    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name="reconciliations"
    )
    member = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="attendance_reconciliations",
    )
    action = models.CharField(max_length=32, choices=ReconciliationAction.choices)
    reason_code = models.CharField(max_length=64)
    notes = models.TextField(blank=True)
    reconciled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="attendance_reconciliation_actions",
    )
    reconciled_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["organization", "event", "reconciled_at"]),
            models.Index(fields=["organization", "member", "reconciled_at"]),
        ]


class EventResourceDownload(OrganizationScopedModel):
    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name="resource_downloads"
    )
    member = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="event_resource_downloads",
    )
    resource_key = models.CharField(max_length=128)
    downloaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["organization", "event", "downloaded_at"]),
            models.Index(fields=["organization", "member", "downloaded_at"]),
            models.Index(fields=["organization", "event", "resource_key"]),
        ]
