from datetime import UTC, datetime, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from clubs.models import Club, MemberStatus, Membership
from common.constants import RoleCode
from events.models import Event, EventRegistration
from finance.models import LedgerEntry, Settlement, WithdrawalRequest
from iam.models import AuthSession, Role, UserOrganizationRole
from tenancy.models import Organization

User = get_user_model()


class FinanceApiTests(TestCase):
    def setUp(self):
        self.org_a = Organization.objects.create(
            name="Org A", slug="org-a", timezone="America/New_York"
        )
        self.org_b = Organization.objects.create(
            name="Org B", slug="org-b", timezone="UTC"
        )

        self.admin_a = User.objects.create_user(
            username="fin-admin-a", password="ValidPass123!"
        )
        self.reviewer_a = User.objects.create_user(
            username="fin-reviewer-a", password="ValidPass123!"
        )
        self.group_leader_a = User.objects.create_user(
            username="fin-leader-a", password="ValidPass123!"
        )
        self.group_leader_b = User.objects.create_user(
            username="fin-leader-b", password="ValidPass123!"
        )
        self.group_leader_c = User.objects.create_user(
            username="fin-leader-c", password="ValidPass123!"
        )
        self.admin_b = User.objects.create_user(
            username="fin-admin-b", password="ValidPass123!"
        )

        self._assign_role(self.admin_a, self.org_a, RoleCode.ADMINISTRATOR.value)
        self._assign_role(
            self.reviewer_a, self.org_a, RoleCode.COUNSELOR_REVIEWER.value
        )
        self._assign_role(self.group_leader_a, self.org_a, RoleCode.GROUP_LEADER.value)
        self._assign_role(self.group_leader_b, self.org_a, RoleCode.GROUP_LEADER.value)
        self._assign_role(self.group_leader_c, self.org_a, RoleCode.GROUP_LEADER.value)
        self._assign_role(self.admin_b, self.org_b, RoleCode.ADMINISTRATOR.value)

        self.admin_client = self._build_client(self.admin_a, self.org_a)
        self.reviewer_client = self._build_client(self.reviewer_a, self.org_a)
        self.leader_client = self._build_client(self.group_leader_a, self.org_a)
        self.leader_b_client = self._build_client(self.group_leader_b, self.org_a)
        self.leader_c_client = self._build_client(self.group_leader_c, self.org_a)
        self.admin_b_client = self._build_client(self.admin_b, self.org_b)

    def _assign_role(self, user, organization, role_code):
        role = Role.objects.get(code=role_code)
        UserOrganizationRole.objects.create(
            user=user, organization=organization, role=role
        )

    def _build_client(self, user, organization):
        session = AuthSession.objects.create(
            session_key=AuthSession.new_session_key(),
            user=user,
            organization=organization,
            last_activity_at=timezone.now(),
            expires_at=timezone.now() + timedelta(hours=2),
        )
        client = APIClient()
        client.credentials(HTTP_X_SESSION_KEY=session.session_key)
        return client

    def test_commission_rule_models_validation(self):
        invalid_fixed = self.admin_client.post(
            "/api/v1/finance/commission-rules/",
            {
                "model_type": "fixed_per_order",
                "tenant_cap_amount": "1000.00",
                "effective_from": "2026-01-01",
            },
            format="json",
        )
        self.assertEqual(invalid_fixed.status_code, 400)

        invalid_percentage = self.admin_client.post(
            "/api/v1/finance/commission-rules/",
            {
                "model_type": "percentage_eligible",
                "percentage": "150.00",
                "tenant_cap_amount": "1000.00",
                "effective_from": "2026-01-01",
            },
            format="json",
        )
        self.assertEqual(invalid_percentage.status_code, 400)

        valid_fixed = self.admin_client.post(
            "/api/v1/finance/commission-rules/",
            {
                "model_type": "fixed_per_order",
                "fixed_amount": "10.00",
                "tenant_cap_amount": "1000.00",
                "effective_from": "2026-01-01",
            },
            format="json",
        )
        self.assertEqual(valid_fixed.status_code, 201)

    def test_withdrawal_blacklist_caps_and_reviewer_threshold(self):
        blacklist_resp = self.admin_client.post(
            "/api/v1/finance/withdrawal-blacklist/",
            {"user": self.group_leader_a.id, "reason": "Fraud flag", "is_active": True},
            format="json",
        )
        self.assertEqual(blacklist_resp.status_code, 201)

        blacklisted_withdraw = self.leader_client.post(
            "/api/v1/finance/withdrawal-requests/",
            {"requester": self.group_leader_a.id, "amount": "100.00"},
            format="json",
        )
        self.assertEqual(blacklisted_withdraw.status_code, 403)
        self.assertEqual(
            blacklisted_withdraw.json()["error"]["code"], "withdrawal.blacklisted"
        )

        self.admin_client.patch(
            f"/api/v1/finance/withdrawal-blacklist/{blacklist_resp.json()['id']}/",
            {"is_active": False, "reason": "Cleared"},
            format="json",
        )

        low_value_request = self.leader_client.post(
            "/api/v1/finance/withdrawal-requests/",
            {"requester": self.group_leader_a.id, "amount": "200.00"},
            format="json",
        )
        self.assertEqual(low_value_request.status_code, 201)
        low_value_id = low_value_request.json()["id"]
        self.assertFalse(low_value_request.json()["requires_reviewer_approval"])
        self.assertEqual(low_value_request.json()["status"], "approved")
        self.assertEqual(
            LedgerEntry.objects.filter(
                reference_type="withdrawal_request", reference_id=str(low_value_id)
            ).count(),
            1,
        )

        low_value_review_attempt = self.reviewer_client.post(
            f"/api/v1/finance/withdrawal-requests/{low_value_id}/review/",
            {"decision": "approved", "review_notes": "should not be needed"},
            format="json",
        )
        self.assertEqual(low_value_review_attempt.status_code, 400)
        self.assertEqual(
            low_value_review_attempt.json()["error"]["code"],
            "withdrawal.invalid_transition",
        )

        threshold_request = self.leader_client.post(
            "/api/v1/finance/withdrawal-requests/",
            {"requester": self.group_leader_a.id, "amount": "260.00"},
            format="json",
        )
        self.assertEqual(threshold_request.status_code, 201)
        request_id = threshold_request.json()["id"]
        self.assertTrue(threshold_request.json()["requires_reviewer_approval"])
        self.assertEqual(threshold_request.json()["status"], "pending_review")
        self.assertEqual(
            LedgerEntry.objects.filter(
                reference_type="withdrawal_request", reference_id=str(request_id)
            ).count(),
            0,
        )

        leader_review_attempt = self.leader_client.post(
            f"/api/v1/finance/withdrawal-requests/{request_id}/review/",
            {"decision": "approved", "review_notes": "self"},
            format="json",
        )
        self.assertEqual(leader_review_attempt.status_code, 403)

        reviewer_approve = self.reviewer_client.post(
            f"/api/v1/finance/withdrawal-requests/{request_id}/review/",
            {"decision": "approved", "review_notes": "approved"},
            format="json",
        )
        self.assertEqual(reviewer_approve.status_code, 200)
        self.assertEqual(reviewer_approve.json()["status"], "approved")
        self.assertEqual(
            LedgerEntry.objects.filter(
                reference_type="withdrawal_request", reference_id=str(request_id)
            ).count(),
            1,
        )

        # Daily cap
        first_daily = self.leader_b_client.post(
            "/api/v1/finance/withdrawal-requests/",
            {"requester": self.group_leader_b.id, "amount": "300.00"},
            format="json",
        )
        self.assertEqual(first_daily.status_code, 201)
        second_daily = self.leader_b_client.post(
            "/api/v1/finance/withdrawal-requests/",
            {"requester": self.group_leader_b.id, "amount": "250.00"},
            format="json",
        )
        self.assertEqual(second_daily.status_code, 400)
        self.assertEqual(
            second_daily.json()["error"]["code"], "withdrawal.daily_cap_exceeded"
        )

        # Weekly cap
        first_week = self.leader_c_client.post(
            "/api/v1/finance/withdrawal-requests/",
            {"requester": self.group_leader_c.id, "amount": "100.00"},
            format="json",
        )
        self.assertEqual(first_week.status_code, 201)
        self.assertEqual(first_week.json()["status"], "approved")
        second_week = self.leader_c_client.post(
            "/api/v1/finance/withdrawal-requests/",
            {"requester": self.group_leader_c.id, "amount": "100.00"},
            format="json",
        )
        self.assertEqual(second_week.status_code, 201)
        self.assertEqual(second_week.json()["status"], "approved")
        third_week = self.leader_c_client.post(
            "/api/v1/finance/withdrawal-requests/",
            {"requester": self.group_leader_c.id, "amount": "50.00"},
            format="json",
        )
        self.assertEqual(third_week.status_code, 400)
        self.assertEqual(
            third_week.json()["error"]["code"], "withdrawal.weekly_cap_exceeded"
        )

    def test_settlement_generation_timing_hold_metadata_and_tenant_isolation(self):
        self.admin_client.post(
            "/api/v1/finance/commission-rules/",
            {
                "model_type": "fixed_per_order",
                "fixed_amount": "10.00",
                "tenant_cap_amount": "500.00",
                "effective_from": "2025-01-01",
            },
            format="json",
        )

        club = Club.objects.create(
            organization=self.org_a, name="Finance Club", code="FIN"
        )
        Membership.objects.create(
            organization=self.org_a,
            member=self.group_leader_a,
            club=club,
            status=MemberStatus.ACTIVE,
        )
        event = Event.objects.create(
            organization=self.org_a,
            club=club,
            title="April Event",
            starts_at=timezone.now(),
            ends_at=timezone.now() + timedelta(hours=1),
            eligible_member_count_snapshot=1,
        )
        registration = EventRegistration.objects.create(
            organization=self.org_a,
            event=event,
            member=self.group_leader_a,
        )
        EventRegistration.objects.filter(id=registration.id).update(
            registered_at=datetime(2026, 4, 15, 15, 0, tzinfo=UTC)
        )

        not_due_at = datetime(2026, 5, 1, 5, 59, tzinfo=UTC)  # 01:59 local NY
        not_due_resp = self.admin_client.post(
            "/api/v1/finance/settlements/generate/",
            {"run_at": not_due_at.isoformat()},
            format="json",
        )
        self.assertEqual(not_due_resp.status_code, 400)
        self.assertEqual(not_due_resp.json()["error"]["code"], "settlement.not_due")

        due_at = datetime(2026, 5, 1, 6, 0, tzinfo=UTC)  # 02:00 local NY
        due_resp = self.admin_client.post(
            "/api/v1/finance/settlements/generate/",
            {"run_at": due_at.isoformat()},
            format="json",
        )
        self.assertEqual(due_resp.status_code, 201)
        settlement_payload = due_resp.json()["settlement"]
        self.assertEqual(settlement_payload["period_year"], 2026)
        self.assertEqual(settlement_payload["period_month"], 4)
        self.assertEqual(Decimal(settlement_payload["total_amount"]), Decimal("10.00"))

        settlement = Settlement.objects.get(id=settlement_payload["id"])
        self.assertEqual(
            settlement.hold_until,
            datetime(2026, 5, 8, 6, 0, tzinfo=UTC),
        )

        duplicate_resp = self.admin_client.post(
            "/api/v1/finance/settlements/generate/",
            {"run_at": due_at.isoformat()},
            format="json",
        )
        self.assertEqual(duplicate_resp.status_code, 200)
        self.assertFalse(duplicate_resp.json()["created"])

        other_settlement = Settlement.objects.create(
            organization=self.org_b,
            period_year=2026,
            period_month=4,
            generated_at=timezone.now(),
            hold_until=timezone.now() + timedelta(days=7),
            total_amount=Decimal("1.00"),
            status="on_hold",
            source_metadata={},
        )
        cross_tenant = self.admin_client.get(
            f"/api/v1/finance/settlements/{other_settlement.id}/"
        )
        self.assertEqual(cross_tenant.status_code, 404)
