from django.db import models

from common.models import OrganizationScopedModel


class CommissionModel(models.TextChoices):
    FIXED_PER_ORDER = "fixed_per_order", "Fixed per order"
    PERCENTAGE_ELIGIBLE = "percentage_eligible", "Percentage of eligible amount"


class CommissionRule(OrganizationScopedModel):
    model_type = models.CharField(max_length=32, choices=CommissionModel.choices)
    fixed_amount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    percentage = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    tenant_cap_amount = models.DecimalField(max_digits=10, decimal_places=2)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["organization", "model_type", "effective_from"]),
            models.Index(fields=["organization", "effective_to"]),
        ]


class LedgerEntryType(models.TextChoices):
    COMMISSION_ACCRUAL = "commission_accrual", "Commission accrual"
    SETTLEMENT_GENERATED = "settlement_generated", "Settlement generated"
    WITHDRAWAL_APPROVED = "withdrawal_approved", "Withdrawal approved"
    WITHDRAWAL_REJECTED = "withdrawal_rejected", "Withdrawal rejected"


class LedgerEntry(OrganizationScopedModel):
    entry_type = models.CharField(max_length=32, choices=LedgerEntryType.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    direction = models.CharField(
        max_length=8, choices=[("credit", "Credit"), ("debit", "Debit")]
    )
    reference_type = models.CharField(max_length=64)
    reference_id = models.CharField(max_length=64)
    occurred_at = models.DateTimeField()
    metadata = models.JSONField(default=dict)

    class Meta:
        indexes = [
            models.Index(fields=["organization", "occurred_at"]),
            models.Index(fields=["organization", "entry_type", "occurred_at"]),
            models.Index(fields=["organization", "reference_type", "reference_id"]),
        ]


class SettlementStatus(models.TextChoices):
    GENERATED = "generated", "Generated"
    ON_HOLD = "on_hold", "On hold"
    RELEASABLE = "releasable", "Releasable"
    CLOSED = "closed", "Closed"


class Settlement(OrganizationScopedModel):
    period_year = models.PositiveIntegerField()
    period_month = models.PositiveSmallIntegerField()
    generated_at = models.DateTimeField()
    hold_until = models.DateTimeField()
    status = models.CharField(
        max_length=16,
        choices=SettlementStatus.choices,
        default=SettlementStatus.ON_HOLD,
    )
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    source_metadata = models.JSONField(default=dict)

    class Meta:
        unique_together = ("organization", "period_year", "period_month")
        indexes = [
            models.Index(fields=["organization", "generated_at"]),
            models.Index(fields=["organization", "hold_until"]),
        ]


class WithdrawalStatus(models.TextChoices):
    PENDING_REVIEW = "pending_review", "Pending review"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class WithdrawalRequest(OrganizationScopedModel):
    requester = models.ForeignKey(
        "iam.User",
        on_delete=models.CASCADE,
        related_name="withdrawal_requests",
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    requested_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=24,
        choices=WithdrawalStatus.choices,
        default=WithdrawalStatus.PENDING_REVIEW,
    )
    requires_reviewer_approval = models.BooleanField(default=False)
    review_notes = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        "iam.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_withdrawals",
    )

    class Meta:
        indexes = [
            models.Index(fields=["organization", "requester", "requested_at"]),
            models.Index(fields=["organization", "status", "requested_at"]),
        ]


class WithdrawalBlacklist(OrganizationScopedModel):
    user = models.ForeignKey(
        "iam.User",
        on_delete=models.CASCADE,
        related_name="withdrawal_blacklist_entries",
    )
    reason = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("organization", "user")
        indexes = [models.Index(fields=["organization", "is_active"])]
