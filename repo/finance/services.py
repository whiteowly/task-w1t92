from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db import models, transaction
from django.utils import timezone
from rest_framework import status

from common.exceptions import DomainAPIException
from events.models import EventRegistration
from finance.models import (
    CommissionModel,
    CommissionRule,
    LedgerEntry,
    LedgerEntryType,
    Settlement,
    SettlementStatus,
    WithdrawalBlacklist,
    WithdrawalRequest,
    WithdrawalStatus,
)
from observability.services import log_audit_event

DAILY_WITHDRAWAL_CAP = Decimal("500.00")
WEEKLY_WITHDRAWAL_REQUEST_CAP = 2
REVIEW_THRESHOLD = Decimal("250.00")


def _organization_tz(organization) -> ZoneInfo:
    return ZoneInfo(organization.timezone or "UTC")


def _month_range_utc_for_local_previous_month(*, run_at_utc, organization):
    org_tz = _organization_tz(organization)
    run_local = run_at_utc.astimezone(org_tz)

    year = run_local.year
    month = run_local.month - 1
    if month == 0:
        month = 12
        year -= 1

    period_start_local = datetime(year, month, 1, 0, 0, tzinfo=org_tz)
    if month == 12:
        period_end_local = datetime(year + 1, 1, 1, 0, 0, tzinfo=org_tz)
    else:
        period_end_local = datetime(year, month + 1, 1, 0, 0, tzinfo=org_tz)

    return (
        year,
        month,
        period_start_local.astimezone(UTC),
        period_end_local.astimezone(UTC),
    )


def _active_commission_rule(*, organization, as_of_date):
    rules = CommissionRule.objects.filter(
        organization=organization,
        effective_from__lte=as_of_date,
    ).filter(
        models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=as_of_date)
    )
    return rules.order_by("-effective_from", "-id").first()


def _compute_settlement_amount(*, organization, period_start_utc, period_end_utc):
    registration_count = EventRegistration.objects.filter(
        organization=organization,
        registered_at__gte=period_start_utc,
        registered_at__lt=period_end_utc,
    ).count()

    eligible_amount = Decimal(registration_count)
    rule = (
        CommissionRule.objects.filter(
            organization=organization,
            effective_from__lte=period_end_utc.date(),
        )
        .filter(
            models.Q(effective_to__isnull=True)
            | models.Q(effective_to__gte=period_start_utc.date())
        )
        .order_by("-effective_from", "-id")
        .first()
    )

    if rule is None:
        return Decimal("0.00"), {
            "registration_count": registration_count,
            "eligible_amount": str(eligible_amount),
            "commission_rule_id": None,
        }

    if rule.model_type == CommissionModel.FIXED_PER_ORDER:
        total = Decimal(registration_count) * Decimal(
            rule.fixed_amount or Decimal("0.00")
        )
    else:
        percentage = Decimal(rule.percentage or Decimal("0.00")) / Decimal("100")
        total = eligible_amount * percentage

    if total > rule.tenant_cap_amount:
        total = Decimal(rule.tenant_cap_amount)

    return total.quantize(Decimal("0.01")), {
        "registration_count": registration_count,
        "eligible_amount": str(eligible_amount),
        "commission_rule_id": rule.id,
        "commission_model": rule.model_type,
    }


@transaction.atomic
def generate_monthly_settlement(*, organization, actor, request, run_at_utc=None):
    run_at_utc = run_at_utc or timezone.now()
    org_tz = _organization_tz(organization)
    run_local = run_at_utc.astimezone(org_tz)

    if run_local.day != 1 or run_local.hour < 2:
        raise DomainAPIException(
            code="settlement.not_due",
            message="Settlement generation is allowed only from day 1 at 02:00 local time.",
        )

    period_year, period_month, start_utc, end_utc = (
        _month_range_utc_for_local_previous_month(
            run_at_utc=run_at_utc,
            organization=organization,
        )
    )

    existing = Settlement.objects.filter(
        organization=organization,
        period_year=period_year,
        period_month=period_month,
    ).first()
    if existing:
        return existing, False

    total_amount, source_metadata = _compute_settlement_amount(
        organization=organization,
        period_start_utc=start_utc,
        period_end_utc=end_utc,
    )

    hold_until_local = run_local + timedelta(days=7)
    hold_until_utc = hold_until_local.astimezone(UTC)

    settlement = Settlement.objects.create(
        organization=organization,
        period_year=period_year,
        period_month=period_month,
        generated_at=run_at_utc,
        hold_until=hold_until_utc,
        status=SettlementStatus.ON_HOLD,
        total_amount=total_amount,
        source_metadata=source_metadata,
    )

    LedgerEntry.objects.create(
        organization=organization,
        entry_type=LedgerEntryType.SETTLEMENT_GENERATED,
        amount=total_amount,
        direction="credit",
        reference_type="settlement",
        reference_id=str(settlement.id),
        occurred_at=run_at_utc,
        metadata={"period_year": period_year, "period_month": period_month},
    )

    log_audit_event(
        action="settlement.generate",
        organization=organization,
        actor_user=actor,
        request=request,
        resource_type="settlement",
        resource_id=str(settlement.id),
        metadata={"period_year": period_year, "period_month": period_month},
    )

    return settlement, True


def _withdrawal_day_bounds_utc(*, now_utc, organization):
    org_tz = _organization_tz(organization)
    local = now_utc.astimezone(org_tz)
    start_local = datetime(local.year, local.month, local.day, 0, 0, tzinfo=org_tz)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def _withdrawal_week_bounds_utc(*, now_utc, organization):
    org_tz = _organization_tz(organization)
    local = now_utc.astimezone(org_tz)
    start_local = datetime(
        local.year, local.month, local.day, 0, 0, tzinfo=org_tz
    ) - timedelta(days=local.weekday())
    end_local = start_local + timedelta(days=7)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


@transaction.atomic
def create_withdrawal_request(*, organization, requester, amount, actor, request):
    now = timezone.now()

    blacklisted = WithdrawalBlacklist.objects.filter(
        organization=organization,
        user=requester,
        is_active=True,
    ).exists()
    if blacklisted:
        raise DomainAPIException(
            code="withdrawal.blacklisted",
            message="Requester is blacklisted from withdrawals.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    day_start, day_end = _withdrawal_day_bounds_utc(
        now_utc=now, organization=organization
    )
    today_amount = WithdrawalRequest.objects.filter(
        organization=organization,
        requester=requester,
        requested_at__gte=day_start,
        requested_at__lt=day_end,
    ).aggregate(total=models.Sum("amount")).get("total") or Decimal("0.00")
    if today_amount + amount > DAILY_WITHDRAWAL_CAP:
        raise DomainAPIException(
            code="withdrawal.daily_cap_exceeded",
            message="Daily withdrawal cap exceeded ($500/day).",
        )

    week_start, week_end = _withdrawal_week_bounds_utc(
        now_utc=now, organization=organization
    )
    week_count = WithdrawalRequest.objects.filter(
        organization=organization,
        requester=requester,
        requested_at__gte=week_start,
        requested_at__lt=week_end,
    ).count()
    if week_count >= WEEKLY_WITHDRAWAL_REQUEST_CAP:
        raise DomainAPIException(
            code="withdrawal.weekly_cap_exceeded",
            message="Weekly withdrawal request cap exceeded (2/week).",
        )

    requires_reviewer_approval = amount > REVIEW_THRESHOLD
    initial_status = (
        WithdrawalStatus.PENDING_REVIEW
        if requires_reviewer_approval
        else WithdrawalStatus.APPROVED
    )

    request_obj = WithdrawalRequest.objects.create(
        organization=organization,
        requester=requester,
        amount=amount,
        status=initial_status,
        requires_reviewer_approval=requires_reviewer_approval,
        review_notes="auto_approved_under_threshold"
        if not requires_reviewer_approval
        else "",
        reviewed_at=now if not requires_reviewer_approval else None,
    )

    if not requires_reviewer_approval:
        LedgerEntry.objects.create(
            organization=organization,
            entry_type=LedgerEntryType.WITHDRAWAL_APPROVED,
            amount=amount,
            direction="debit",
            reference_type="withdrawal_request",
            reference_id=str(request_obj.id),
            occurred_at=now,
            metadata={
                "requester_id": requester.id,
                "approval_mode": "auto_under_threshold",
            },
        )

    log_audit_event(
        action="withdrawal.request.create",
        organization=organization,
        actor_user=actor,
        request=request,
        resource_type="withdrawal_request",
        resource_id=str(request_obj.id),
        metadata={
            "requester_id": requester.id,
            "amount": str(amount),
            "requires_reviewer_approval": request_obj.requires_reviewer_approval,
            "status": request_obj.status,
        },
    )

    if not requires_reviewer_approval:
        log_audit_event(
            action="withdrawal.request.auto_approved",
            organization=organization,
            actor_user=actor,
            request=request,
            resource_type="withdrawal_request",
            resource_id=str(request_obj.id),
            metadata={
                "requester_id": requester.id,
                "amount": str(amount),
                "threshold": str(REVIEW_THRESHOLD),
            },
        )

    return request_obj


@transaction.atomic
def review_withdrawal_request(
    *, withdrawal_request, decision, review_notes, reviewer, request
):
    withdrawal_request = WithdrawalRequest.objects.select_for_update().get(
        pk=withdrawal_request.pk
    )

    if withdrawal_request.status != WithdrawalStatus.PENDING_REVIEW:
        raise DomainAPIException(
            code="withdrawal.invalid_transition",
            message="Only pending withdrawal requests can be reviewed.",
        )

    if decision not in {WithdrawalStatus.APPROVED, WithdrawalStatus.REJECTED}:
        raise DomainAPIException(
            code="withdrawal.invalid_decision",
            message="Decision must be approved or rejected.",
        )

    if (
        withdrawal_request.amount > REVIEW_THRESHOLD
        and decision == WithdrawalStatus.APPROVED
        and reviewer is None
    ):
        raise DomainAPIException(
            code="withdrawal.reviewer_required",
            message="Reviewer approval is required for withdrawals over $250.",
        )

    withdrawal_request.status = decision
    withdrawal_request.review_notes = review_notes
    withdrawal_request.reviewed_by = reviewer
    withdrawal_request.reviewed_at = timezone.now()
    withdrawal_request.save(
        update_fields=[
            "status",
            "review_notes",
            "reviewed_by",
            "reviewed_at",
            "updated_at",
        ]
    )

    if decision == WithdrawalStatus.APPROVED:
        LedgerEntry.objects.create(
            organization=withdrawal_request.organization,
            entry_type=LedgerEntryType.WITHDRAWAL_APPROVED,
            amount=withdrawal_request.amount,
            direction="debit",
            reference_type="withdrawal_request",
            reference_id=str(withdrawal_request.id),
            occurred_at=timezone.now(),
            metadata={"requester_id": withdrawal_request.requester_id},
        )

    log_audit_event(
        action=f"withdrawal.request.review.{decision}",
        organization=withdrawal_request.organization,
        actor_user=reviewer,
        request=request,
        resource_type="withdrawal_request",
        resource_id=str(withdrawal_request.id),
        metadata={"decision": decision},
    )

    return withdrawal_request
