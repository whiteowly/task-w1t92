from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from common.constants import RoleCode
from finance.models import (
    CommissionRule,
    LedgerEntry,
    Settlement,
    WithdrawalBlacklist,
    WithdrawalRequest,
)
from iam.models import AuthSession, Role, UserOrganizationRole
from tenancy.models import Organization

User = get_user_model()


class FinanceCrudApiTests(TestCase):
    """Tests for finance list/detail/update/delete endpoints."""

    def setUp(self):
        self.org = Organization.objects.create(
            name="Finance CRUD Org", slug="fin-crud-org", timezone="UTC"
        )
        self.other_org = Organization.objects.create(
            name="Finance Other Org", slug="fin-other-org", timezone="UTC"
        )
        self.password = "ValidPass123!"

        self.admin = User.objects.create_user(
            username="fc-admin", password=self.password, full_name="Admin"
        )
        self.reviewer = User.objects.create_user(
            username="fc-reviewer", password=self.password, full_name="Reviewer"
        )
        self.leader = User.objects.create_user(
            username="fc-leader", password=self.password, full_name="Leader"
        )
        self.other_admin = User.objects.create_user(
            username="fc-other-admin", password=self.password, full_name="Other Admin"
        )

        self._assign_role(self.admin, self.org, RoleCode.ADMINISTRATOR.value)
        self._assign_role(self.reviewer, self.org, RoleCode.COUNSELOR_REVIEWER.value)
        self._assign_role(self.leader, self.org, RoleCode.GROUP_LEADER.value)
        self._assign_role(
            self.other_admin, self.other_org, RoleCode.ADMINISTRATOR.value
        )

        self.admin_client = self._build_client(self.admin, self.org)
        self.reviewer_client = self._build_client(self.reviewer, self.org)
        self.leader_client = self._build_client(self.leader, self.org)
        self.other_admin_client = self._build_client(self.other_admin, self.other_org)

    def _assign_role(self, user, org, role_code):
        role = Role.objects.get(code=role_code)
        UserOrganizationRole.objects.create(user=user, organization=org, role=role)

    def _build_client(self, user, org):
        session = AuthSession.objects.create(
            session_key=AuthSession.new_session_key(),
            user=user,
            organization=org,
            last_activity_at=timezone.now(),
            expires_at=timezone.now() + timedelta(hours=2),
        )
        client = APIClient()
        client.credentials(HTTP_X_SESSION_KEY=session.session_key)
        return client

    # ---- Commission Rules ----

    def test_list_commission_rules(self):
        CommissionRule.objects.create(
            organization=self.org,
            model_type="fixed_per_order",
            fixed_amount=Decimal("10.00"),
            tenant_cap_amount=Decimal("500.00"),
            effective_from="2026-01-01",
        )
        resp = self.admin_client.get("/api/v1/finance/commission-rules/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)
        self.assertEqual(resp.json()[0]["model_type"], "fixed_per_order")

    def test_retrieve_commission_rule(self):
        rule = CommissionRule.objects.create(
            organization=self.org,
            model_type="fixed_per_order",
            fixed_amount=Decimal("15.00"),
            tenant_cap_amount=Decimal("1000.00"),
            effective_from="2026-01-01",
        )
        resp = self.admin_client.get(f"/api/v1/finance/commission-rules/{rule.id}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["fixed_amount"], "15.00")

    def test_update_commission_rule(self):
        rule = CommissionRule.objects.create(
            organization=self.org,
            model_type="fixed_per_order",
            fixed_amount=Decimal("10.00"),
            tenant_cap_amount=Decimal("500.00"),
            effective_from="2026-01-01",
        )
        resp = self.admin_client.patch(
            f"/api/v1/finance/commission-rules/{rule.id}/",
            {"fixed_amount": "20.00"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["fixed_amount"], "20.00")

    def test_full_update_commission_rule(self):
        rule = CommissionRule.objects.create(
            organization=self.org,
            model_type="fixed_per_order",
            fixed_amount=Decimal("10.00"),
            tenant_cap_amount=Decimal("500.00"),
            effective_from="2026-01-01",
        )
        resp = self.admin_client.put(
            f"/api/v1/finance/commission-rules/{rule.id}/",
            {
                "model_type": "fixed_per_order",
                "fixed_amount": "12.50",
                "percentage": None,
                "tenant_cap_amount": "700.00",
                "effective_from": "2026-02-01",
                "effective_to": "2026-12-31",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["fixed_amount"], "12.50")

    def test_delete_commission_rule(self):
        rule = CommissionRule.objects.create(
            organization=self.org,
            model_type="fixed_per_order",
            fixed_amount=Decimal("10.00"),
            tenant_cap_amount=Decimal("500.00"),
            effective_from="2026-01-01",
        )
        resp = self.admin_client.delete(f"/api/v1/finance/commission-rules/{rule.id}/")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(CommissionRule.objects.filter(id=rule.id).exists())

    def test_commission_rule_reviewer_can_list_not_create(self):
        CommissionRule.objects.create(
            organization=self.org,
            model_type="fixed_per_order",
            fixed_amount=Decimal("10.00"),
            tenant_cap_amount=Decimal("500.00"),
            effective_from="2026-01-01",
        )
        resp = self.reviewer_client.get("/api/v1/finance/commission-rules/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)

        resp = self.reviewer_client.post(
            "/api/v1/finance/commission-rules/",
            {
                "model_type": "fixed_per_order",
                "fixed_amount": "5.00",
                "tenant_cap_amount": "100.00",
                "effective_from": "2026-02-01",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_commission_rule_cross_tenant_isolation(self):
        rule = CommissionRule.objects.create(
            organization=self.org,
            model_type="fixed_per_order",
            fixed_amount=Decimal("10.00"),
            tenant_cap_amount=Decimal("500.00"),
            effective_from="2026-01-01",
        )
        resp = self.other_admin_client.get(
            f"/api/v1/finance/commission-rules/{rule.id}/"
        )
        self.assertEqual(resp.status_code, 404)

    # ---- Settlements ----

    def test_list_settlements(self):
        Settlement.objects.create(
            organization=self.org,
            period_year=2026,
            period_month=3,
            generated_at=timezone.now(),
            hold_until=timezone.now() + timedelta(days=7),
            total_amount=Decimal("100.00"),
            status="on_hold",
            source_metadata={},
        )
        resp = self.admin_client.get("/api/v1/finance/settlements/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)
        self.assertEqual(resp.json()[0]["period_year"], 2026)
        self.assertEqual(resp.json()[0]["period_month"], 3)

    def test_retrieve_settlement(self):
        settlement = Settlement.objects.create(
            organization=self.org,
            period_year=2026,
            period_month=2,
            generated_at=timezone.now(),
            hold_until=timezone.now() + timedelta(days=7),
            total_amount=Decimal("200.00"),
            status="on_hold",
            source_metadata={},
        )
        resp = self.admin_client.get(f"/api/v1/finance/settlements/{settlement.id}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["total_amount"], "200.00")

    def test_settlement_leader_can_list(self):
        Settlement.objects.create(
            organization=self.org,
            period_year=2026,
            period_month=1,
            generated_at=timezone.now(),
            hold_until=timezone.now() + timedelta(days=7),
            total_amount=Decimal("50.00"),
            status="on_hold",
            source_metadata={},
        )
        resp = self.leader_client.get("/api/v1/finance/settlements/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)

    # ---- Withdrawal Blacklist ----

    def test_list_withdrawal_blacklist(self):
        WithdrawalBlacklist.objects.create(
            organization=self.org,
            user=self.leader,
            reason="Test",
            is_active=True,
        )
        resp = self.admin_client.get("/api/v1/finance/withdrawal-blacklist/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)
        self.assertEqual(resp.json()[0]["reason"], "Test")

    def test_retrieve_withdrawal_blacklist(self):
        bl = WithdrawalBlacklist.objects.create(
            organization=self.org,
            user=self.leader,
            reason="Fraud",
            is_active=True,
        )
        resp = self.admin_client.get(f"/api/v1/finance/withdrawal-blacklist/{bl.id}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["reason"], "Fraud")

    def test_full_update_withdrawal_blacklist(self):
        bl = WithdrawalBlacklist.objects.create(
            organization=self.org,
            user=self.leader,
            reason="Initial",
            is_active=True,
        )
        resp = self.admin_client.put(
            f"/api/v1/finance/withdrawal-blacklist/{bl.id}/",
            {
                "user": self.leader.id,
                "reason": "Updated Reason",
                "is_active": False,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["reason"], "Updated Reason")
        self.assertFalse(resp.json()["is_active"])

    def test_delete_withdrawal_blacklist(self):
        bl = WithdrawalBlacklist.objects.create(
            organization=self.org,
            user=self.leader,
            reason="Removing",
            is_active=True,
        )
        resp = self.admin_client.delete(
            f"/api/v1/finance/withdrawal-blacklist/{bl.id}/"
        )
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(WithdrawalBlacklist.objects.filter(id=bl.id).exists())

    def test_blacklist_leader_forbidden(self):
        resp = self.leader_client.get("/api/v1/finance/withdrawal-blacklist/")
        self.assertEqual(resp.status_code, 403)

    # ---- Withdrawal Requests ----

    def test_list_withdrawal_requests(self):
        WithdrawalRequest.objects.create(
            organization=self.org,
            requester=self.leader,
            amount=Decimal("100.00"),
            status="approved",
        )
        resp = self.admin_client.get("/api/v1/finance/withdrawal-requests/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)

    def test_retrieve_withdrawal_request(self):
        wr = WithdrawalRequest.objects.create(
            organization=self.org,
            requester=self.leader,
            amount=Decimal("150.00"),
            status="pending_review",
            requires_reviewer_approval=True,
        )
        resp = self.admin_client.get(f"/api/v1/finance/withdrawal-requests/{wr.id}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["amount"], "150.00")
        self.assertTrue(resp.json()["requires_reviewer_approval"])

    def test_leader_sees_only_own_withdrawal_requests(self):
        WithdrawalRequest.objects.create(
            organization=self.org,
            requester=self.leader,
            amount=Decimal("50.00"),
            status="approved",
        )
        WithdrawalRequest.objects.create(
            organization=self.org,
            requester=self.admin,
            amount=Decimal("75.00"),
            status="approved",
        )
        resp = self.leader_client.get("/api/v1/finance/withdrawal-requests/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)
        self.assertEqual(resp.json()[0]["amount"], "50.00")

    # ---- Ledger Entries ----

    def test_retrieve_ledger_entry(self):
        entry = LedgerEntry.objects.create(
            organization=self.org,
            entry_type="settlement_generated",
            amount=Decimal("42.00"),
            direction="credit",
            reference_type="settlement",
            reference_id="test-settlement",
            occurred_at=timezone.now(),
            metadata={"scope": "test"},
        )
        resp = self.admin_client.get(f"/api/v1/finance/ledger-entries/{entry.id}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["amount"], "42.00")
        self.assertEqual(resp.json()["entry_type"], "settlement_generated")
        self.assertEqual(resp.json()["reference_id"], "test-settlement")

    def test_ledger_entry_cross_tenant_isolation(self):
        entry = LedgerEntry.objects.create(
            organization=self.org,
            entry_type="settlement_generated",
            amount=Decimal("42.00"),
            direction="credit",
            reference_type="settlement",
            reference_id="iso-settlement",
            occurred_at=timezone.now(),
            metadata={},
        )
        resp = self.other_admin_client.get(
            f"/api/v1/finance/ledger-entries/{entry.id}/"
        )
        self.assertEqual(resp.status_code, 404)
