from django.db import models

from common.models import OrganizationScopedModel


class Warehouse(OrganizationScopedModel):
    name = models.CharField(max_length=255)


class Zone(OrganizationScopedModel):
    warehouse = models.ForeignKey(
        Warehouse, on_delete=models.CASCADE, related_name="zones"
    )
    name = models.CharField(max_length=255)

    class Meta:
        unique_together = ("organization", "warehouse", "name")


class Location(OrganizationScopedModel):
    zone = models.ForeignKey(Zone, on_delete=models.CASCADE, related_name="locations")
    code = models.CharField(max_length=64)
    length_in = models.DecimalField(max_digits=10, decimal_places=2)
    width_in = models.DecimalField(max_digits=10, decimal_places=2)
    height_in = models.DecimalField(max_digits=10, decimal_places=2)
    load_limit_lbs = models.DecimalField(max_digits=10, decimal_places=2)
    temperature_zone = models.CharField(
        max_length=32,
        choices=[
            ("ambient", "Ambient"),
            ("controlled", "Controlled"),
            ("chilled", "Chilled"),
            ("frozen", "Frozen"),
        ],
        default="ambient",
    )
    restricted_handling_flags = models.JSONField(default=list)
    capacity_slots = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("organization", "code")
        indexes = [
            models.Index(fields=["organization", "zone"]),
            models.Index(fields=["organization", "temperature_zone"]),
        ]


class PickupPoint(OrganizationScopedModel):
    name = models.CharField(max_length=255)
    address_line1 = models.CharField(max_length=255)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=120)
    state = models.CharField(max_length=2)
    postal_code = models.CharField(max_length=10)
    country = models.CharField(max_length=2, default="US")
    contact_phone = models.CharField(max_length=32, blank=True, default="")
    encrypted_address_line1 = models.TextField(blank=True, default="")
    encrypted_address_line2 = models.TextField(blank=True, default="")
    encrypted_city = models.TextField(blank=True, default="")
    encrypted_state = models.TextField(blank=True, default="")
    encrypted_postal_code = models.TextField(blank=True, default="")
    encrypted_country = models.TextField(blank=True, default="")
    encrypted_contact_phone = models.TextField(blank=True, default="")
    capacity_limit = models.PositiveIntegerField()
    assigned_group_leader = models.ForeignKey(
        "iam.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_pickup_points",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=["organization", "state", "city"]),
            models.Index(fields=["organization", "assigned_group_leader"]),
        ]


class Weekday(models.IntegerChoices):
    MONDAY = 0, "Monday"
    TUESDAY = 1, "Tuesday"
    WEDNESDAY = 2, "Wednesday"
    THURSDAY = 3, "Thursday"
    FRIDAY = 4, "Friday"
    SATURDAY = 5, "Saturday"
    SUNDAY = 6, "Sunday"


class PickupPointBusinessHour(OrganizationScopedModel):
    pickup_point = models.ForeignKey(
        PickupPoint,
        on_delete=models.CASCADE,
        related_name="business_hours",
    )
    weekday = models.PositiveSmallIntegerField(choices=Weekday.choices)
    opens_at = models.TimeField()
    closes_at = models.TimeField()

    class Meta:
        unique_together = ("organization", "pickup_point", "weekday")
        indexes = [
            models.Index(fields=["organization", "pickup_point", "weekday"]),
        ]


class PickupPointClosure(OrganizationScopedModel):
    pickup_point = models.ForeignKey(
        PickupPoint,
        on_delete=models.CASCADE,
        related_name="closures",
    )
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    reason = models.CharField(max_length=255)

    class Meta:
        indexes = [
            models.Index(fields=["organization", "pickup_point", "starts_at"]),
            models.Index(fields=["organization", "pickup_point", "ends_at"]),
        ]


class OnboardingStatus(models.TextChoices):
    SUBMITTED = "submitted", "Submitted"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class GroupLeaderOnboarding(OrganizationScopedModel):
    applicant = models.ForeignKey(
        "iam.User",
        on_delete=models.CASCADE,
        related_name="leader_onboarding_applications",
    )
    pickup_point = models.ForeignKey(
        PickupPoint,
        on_delete=models.SET_NULL,
        related_name="leader_onboarding_applications",
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=16,
        choices=OnboardingStatus.choices,
        default=OnboardingStatus.SUBMITTED,
    )
    document_title = models.CharField(max_length=255)
    document_type = models.CharField(max_length=64)
    document_reference = models.CharField(max_length=255)
    document_metadata = models.JSONField(default=dict)
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        "iam.User",
        on_delete=models.SET_NULL,
        related_name="reviewed_leader_onboarding_applications",
        null=True,
        blank=True,
    )
    review_notes = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["organization", "applicant", "status"]),
            models.Index(fields=["organization", "status", "submitted_at"]),
        ]
