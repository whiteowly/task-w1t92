from datetime import UTC, datetime, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from clubs.models import Club
from events.models import Event, EventRegistration
from finance.models import CommissionRule, LedgerEntry, Settlement
from observability.models import AuditLog
from scheduler.models import ScheduledJob
from scheduler.services import run_job
from tenancy.models import Organization

User = get_user_model()


class SettlementSchedulerJobTests(TestCase):
    def _seed_registration_for_april_2026(self, organization, username_suffix):
        participant = User.objects.create_user(
            username=f"scheduler-member-{username_suffix}",
            password="ValidPass123!",
        )
        club = Club.objects.create(
            organization=organization,
            name=f"Finance Club {username_suffix}",
            code=f"FIN-{username_suffix}",
        )
        event = Event.objects.create(
            organization=organization,
            club=club,
            title="Settlement Source Event",
            starts_at=timezone.now(),
            ends_at=timezone.now() + timedelta(hours=1),
            eligible_member_count_snapshot=1,
        )
        registration = EventRegistration.objects.create(
            organization=organization,
            event=event,
            member=participant,
        )
        EventRegistration.objects.filter(id=registration.id).update(
            registered_at=datetime(2026, 4, 15, 12, 0, tzinfo=UTC)
        )

    def test_scheduler_job_generates_monthly_settlement_at_local_cutoff(self):
        org = Organization.objects.create(
            name="NY Org",
            slug="ny-org",
            timezone="America/New_York",
        )
        CommissionRule.objects.create(
            organization=org,
            model_type="fixed_per_order",
            fixed_amount=Decimal("10.00"),
            tenant_cap_amount=Decimal("500.00"),
            effective_from=datetime(2025, 1, 1, tzinfo=UTC).date(),
        )
        self._seed_registration_for_april_2026(org, "ny")

        job = ScheduledJob.objects.create(
            code="test-finance-monthly-settlement",
            handler="finance.settlement.monthly",
            interval_seconds=900,
            next_run_at=timezone.now(),
            is_enabled=True,
        )

        not_due = datetime(2026, 5, 1, 5, 59, tzinfo=UTC)  # 01:59 local NY
        run_job(job, now=not_due)
        self.assertFalse(Settlement.objects.filter(organization=org).exists())

        due = datetime(2026, 5, 1, 6, 0, tzinfo=UTC)  # 02:00 local NY
        run_job(job, now=due)

        settlement = Settlement.objects.get(organization=org)
        self.assertEqual(settlement.period_year, 2026)
        self.assertEqual(settlement.period_month, 4)
        self.assertEqual(settlement.total_amount, Decimal("10.00"))
        self.assertTrue(
            LedgerEntry.objects.filter(
                organization=org,
                entry_type="settlement_generated",
                reference_type="settlement",
                reference_id=str(settlement.id),
            ).exists()
        )
        self.assertTrue(
            AuditLog.objects.filter(
                organization=org,
                action="settlement.generate",
                resource_id=str(settlement.id),
                request_id="scheduler",
                actor_user__isnull=True,
            ).exists()
        )

    def test_scheduler_job_uses_each_tenant_local_calendar(self):
        tokyo_org = Organization.objects.create(
            name="Tokyo Org",
            slug="tokyo-org",
            timezone="Asia/Tokyo",
        )
        ny_org = Organization.objects.create(
            name="NY Org 2",
            slug="ny-org-2",
            timezone="America/New_York",
        )

        for org in [tokyo_org, ny_org]:
            CommissionRule.objects.create(
                organization=org,
                model_type="fixed_per_order",
                fixed_amount=Decimal("10.00"),
                tenant_cap_amount=Decimal("500.00"),
                effective_from=datetime(2025, 1, 1, tzinfo=UTC).date(),
            )
            self._seed_registration_for_april_2026(org, org.slug)

        job = ScheduledJob.objects.create(
            code="test-finance-monthly-settlement-timezones",
            handler="finance.settlement.monthly",
            interval_seconds=900,
            next_run_at=timezone.now(),
            is_enabled=True,
        )

        run_time = datetime(2026, 5, 1, 0, 5, tzinfo=UTC)
        # Tokyo local: 09:05 on day 1 (due); NY local: 20:05 on previous day (not due)
        run_job(job, now=run_time)

        self.assertTrue(Settlement.objects.filter(organization=tokyo_org).exists())
        self.assertFalse(Settlement.objects.filter(organization=ny_org).exists())
