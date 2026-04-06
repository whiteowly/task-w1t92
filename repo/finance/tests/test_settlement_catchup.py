from datetime import datetime, timedelta, timezone as _tz

UTC = _tz.utc
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from clubs.models import Club
from events.models import Event, EventRegistration
from finance.models import CommissionRule, Settlement
from finance.services import generate_monthly_settlement
from tenancy.models import Organization

User = get_user_model()


class _FakeRequest:
    request_id = "test"
    META = {"REMOTE_ADDR": "127.0.0.1"}


class SettlementCatchupTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(
            name="Catchup Org", slug="catchup-org", timezone="UTC"
        )
        CommissionRule.objects.create(
            organization=self.org,
            model_type="fixed_per_order",
            fixed_amount=Decimal("10.00"),
            tenant_cap_amount=Decimal("500.00"),
            effective_from=datetime(2025, 1, 1, tzinfo=UTC).date(),
        )
        participant = User.objects.create_user(
            username="catchup-member", password="ValidPass123!"
        )
        club = Club.objects.create(
            organization=self.org, name="Catchup Club", code="CU-1"
        )
        event = Event.objects.create(
            organization=self.org,
            club=club,
            title="Catchup Event",
            starts_at=timezone.now(),
            ends_at=timezone.now() + timedelta(hours=1),
            eligible_member_count_snapshot=1,
        )
        reg = EventRegistration.objects.create(
            organization=self.org, event=event, member=participant
        )
        EventRegistration.objects.filter(id=reg.id).update(
            registered_at=datetime(2026, 4, 15, 12, 0, tzinfo=UTC)
        )
        self.request = _FakeRequest()

    def test_day3_generation_is_rejected(self):
        from common.exceptions import DomainAPIException

        run_at = datetime(2026, 5, 3, 10, 0, tzinfo=UTC)
        with self.assertRaises(DomainAPIException) as ctx:
            generate_monthly_settlement(
                organization=self.org,
                actor=None,
                request=self.request,
                run_at_utc=run_at,
            )
        self.assertEqual(ctx.exception.error_code, "settlement.not_due")
        self.assertFalse(Settlement.objects.filter(organization=self.org).exists())

    def test_day2_generation_is_rejected(self):
        from common.exceptions import DomainAPIException

        run_at = datetime(2026, 5, 2, 10, 0, tzinfo=UTC)
        with self.assertRaises(DomainAPIException) as ctx:
            generate_monthly_settlement(
                organization=self.org,
                actor=None,
                request=self.request,
                run_at_utc=run_at,
            )
        self.assertEqual(ctx.exception.error_code, "settlement.not_due")
        self.assertFalse(Settlement.objects.filter(organization=self.org).exists())

    def test_day1_before_2am_still_rejected(self):
        from common.exceptions import DomainAPIException

        run_at = datetime(2026, 5, 1, 1, 0, tzinfo=UTC)
        with self.assertRaises(DomainAPIException) as ctx:
            generate_monthly_settlement(
                organization=self.org,
                actor=None,
                request=self.request,
                run_at_utc=run_at,
            )
        self.assertEqual(ctx.exception.error_code, "settlement.not_due")
