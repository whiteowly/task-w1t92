from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from common.constants import RoleCode
from common.pii import decrypt_pii_value
from iam.models import AuthSession, Role, UserOrganizationRole
from logistics.models import (
    GroupLeaderOnboarding,
    OnboardingStatus,
    PickupPoint,
    PickupPointBusinessHour,
    PickupPointClosure,
)
from observability.models import AuditLog
from tenancy.models import Organization

User = get_user_model()


class PickupPointAndOnboardingApiTests(TestCase):
    def setUp(self):
        self.org_a = Organization.objects.create(
            name="Org A", slug="org-a", timezone="UTC"
        )
        self.org_b = Organization.objects.create(
            name="Org B", slug="org-b", timezone="UTC"
        )

        self.admin_a = User.objects.create_user(
            username="log-admin-a", password="ValidPass123!"
        )
        self.manager_a = User.objects.create_user(
            username="log-manager-a", password="ValidPass123!"
        )
        self.reviewer_a = User.objects.create_user(
            username="log-reviewer-a", password="ValidPass123!"
        )
        self.group_leader_a = User.objects.create_user(
            username="log-leader-a", password="ValidPass123!"
        )
        self.group_leader_b = User.objects.create_user(
            username="log-leader-b", password="ValidPass123!"
        )
        self.manager_b = User.objects.create_user(
            username="log-manager-b", password="ValidPass123!"
        )

        self._assign_role(self.admin_a, self.org_a, RoleCode.ADMINISTRATOR.value)
        self._assign_role(self.manager_a, self.org_a, RoleCode.CLUB_MANAGER.value)
        self._assign_role(
            self.reviewer_a, self.org_a, RoleCode.COUNSELOR_REVIEWER.value
        )
        self._assign_role(self.group_leader_a, self.org_a, RoleCode.GROUP_LEADER.value)
        self._assign_role(self.group_leader_b, self.org_a, RoleCode.GROUP_LEADER.value)
        self._assign_role(self.manager_b, self.org_b, RoleCode.CLUB_MANAGER.value)

        self.admin_client = self._build_client(self.admin_a, self.org_a)
        self.manager_client = self._build_client(self.manager_a, self.org_a)
        self.reviewer_client = self._build_client(self.reviewer_a, self.org_a)
        self.group_leader_client = self._build_client(self.group_leader_a, self.org_a)

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

    def _create_pickup_point(self):
        response = self.manager_client.post(
            "/api/v1/logistics/pickup-points/",
            {
                "name": "Downtown Pickup",
                "address_line1": "123 Main St",
                "address_line2": "Suite 5",
                "city": "Springfield",
                "state": "CA",
                "postal_code": "94105",
                "country": "US",
                "capacity_limit": 200,
                "assigned_group_leader": self.group_leader_a.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        return PickupPoint.objects.get(id=response.json()["id"])

    def test_pickup_point_setup_validations_and_hours_closures(self):
        invalid_state = self.manager_client.post(
            "/api/v1/logistics/pickup-points/",
            {
                "name": "Bad State",
                "address_line1": "1 X St",
                "city": "Somewhere",
                "state": "California",
                "postal_code": "94105",
                "country": "US",
                "capacity_limit": 10,
            },
            format="json",
        )
        self.assertEqual(invalid_state.status_code, 400)

        invalid_zip = self.manager_client.post(
            "/api/v1/logistics/pickup-points/",
            {
                "name": "Bad Zip",
                "address_line1": "1 X St",
                "city": "Somewhere",
                "state": "CA",
                "postal_code": "ABC",
                "country": "US",
                "capacity_limit": 10,
            },
            format="json",
        )
        self.assertEqual(invalid_zip.status_code, 400)

        pickup_point = self._create_pickup_point()

        invalid_hours = self.manager_client.post(
            "/api/v1/logistics/pickup-point-business-hours/",
            {
                "pickup_point": pickup_point.id,
                "weekday": 1,
                "opens_at": "18:00:00",
                "closes_at": "09:00:00",
            },
            format="json",
        )
        self.assertEqual(invalid_hours.status_code, 400)

        valid_hours = self.manager_client.post(
            "/api/v1/logistics/pickup-point-business-hours/",
            {
                "pickup_point": pickup_point.id,
                "weekday": 1,
                "opens_at": "09:00:00",
                "closes_at": "18:00:00",
            },
            format="json",
        )
        self.assertEqual(valid_hours.status_code, 201)

        invalid_closure = self.manager_client.post(
            "/api/v1/logistics/pickup-point-closures/",
            {
                "pickup_point": pickup_point.id,
                "starts_at": "2026-04-10T10:00:00Z",
                "ends_at": "2026-04-10T09:00:00Z",
                "reason": "Bad window",
            },
            format="json",
        )
        self.assertEqual(invalid_closure.status_code, 400)

        valid_closure = self.manager_client.post(
            "/api/v1/logistics/pickup-point-closures/",
            {
                "pickup_point": pickup_point.id,
                "starts_at": "2026-04-10T09:00:00Z",
                "ends_at": "2026-04-10T17:00:00Z",
                "reason": "Maintenance",
            },
            format="json",
        )
        self.assertEqual(valid_closure.status_code, 201)

        self.assertEqual(
            PickupPointBusinessHour.objects.filter(pickup_point=pickup_point).count(), 1
        )
        self.assertEqual(
            PickupPointClosure.objects.filter(pickup_point=pickup_point).count(), 1
        )

    def test_onboarding_submission_and_review_workflow_with_audit(self):
        pickup_point = self._create_pickup_point()

        submit_resp = self.group_leader_client.post(
            "/api/v1/logistics/group-leader-onboardings/",
            {
                "pickup_point": pickup_point.id,
                "document_title": "ID Verification",
                "document_type": "government_id",
                "document_reference": "DOC-123",
                "document_metadata": {"issuer": "DMV", "expires": "2030-01-01"},
            },
            format="json",
        )
        self.assertEqual(submit_resp.status_code, 201)
        onboarding_id = submit_resp.json()["id"]

        review_resp = self.reviewer_client.post(
            f"/api/v1/logistics/group-leader-onboardings/{onboarding_id}/review/",
            {"decision": "approved", "review_notes": "Looks good"},
            format="json",
        )
        self.assertEqual(review_resp.status_code, 200)
        self.assertEqual(review_resp.json()["status"], OnboardingStatus.APPROVED)

        onboarding = GroupLeaderOnboarding.objects.get(id=onboarding_id)
        self.assertEqual(onboarding.reviewed_by_id, self.reviewer_a.id)
        self.assertIsNotNone(onboarding.reviewed_at)

        audit_actions = set(
            AuditLog.objects.filter(
                resource_type="leader_onboarding", resource_id=str(onboarding_id)
            ).values_list("action", flat=True)
        )
        self.assertIn("leader_onboarding.submit", audit_actions)
        self.assertIn("leader_onboarding.review.approved", audit_actions)

    def test_invalid_review_transition_and_permissions(self):
        pickup_point = self._create_pickup_point()
        onboarding = GroupLeaderOnboarding.objects.create(
            organization=self.org_a,
            applicant=self.group_leader_a,
            pickup_point=pickup_point,
            status=OnboardingStatus.SUBMITTED,
            document_title="Doc",
            document_type="id",
            document_reference="ABC",
            document_metadata={},
        )

        approve_resp = self.reviewer_client.post(
            f"/api/v1/logistics/group-leader-onboardings/{onboarding.id}/review/",
            {"decision": "approved", "review_notes": "ok"},
            format="json",
        )
        self.assertEqual(approve_resp.status_code, 200)

        reject_after_approved = self.reviewer_client.post(
            f"/api/v1/logistics/group-leader-onboardings/{onboarding.id}/review/",
            {"decision": "rejected", "review_notes": "too late"},
            format="json",
        )
        self.assertEqual(reject_after_approved.status_code, 400)
        self.assertEqual(
            reject_after_approved.json()["error"]["code"],
            "leader_onboarding.invalid_transition",
        )

        leader_review_attempt = self.group_leader_client.post(
            f"/api/v1/logistics/group-leader-onboardings/{onboarding.id}/review/",
            {"decision": "rejected", "review_notes": "not allowed"},
            format="json",
        )
        self.assertEqual(leader_review_attempt.status_code, 403)

    def test_tenant_isolation_and_group_leader_context_reads(self):
        other_org_pickup = PickupPoint.objects.create(
            organization=self.org_b,
            name="Other Org Pickup",
            address_line1="999 Elsewhere Rd",
            city="Elsewhere",
            state="CA",
            postal_code="94107",
            country="US",
            capacity_limit=100,
            assigned_group_leader=None,
        )
        other_org_onboarding = GroupLeaderOnboarding.objects.create(
            organization=self.org_b,
            applicant=self.manager_b,
            pickup_point=other_org_pickup,
            status=OnboardingStatus.SUBMITTED,
            document_title="Other Org Doc",
            document_type="id",
            document_reference="ORG-B-1",
            document_metadata={},
        )

        detail_other_org = self.manager_client.get(
            f"/api/v1/logistics/pickup-points/{other_org_pickup.id}/"
        )
        self.assertEqual(detail_other_org.status_code, 404)

        onboarding_other_org = self.manager_client.get(
            f"/api/v1/logistics/group-leader-onboardings/{other_org_onboarding.id}/"
        )
        self.assertEqual(onboarding_other_org.status_code, 404)

        own_pickup = self._create_pickup_point()
        PickupPoint.objects.create(
            organization=self.org_a,
            name="Unassigned",
            address_line1="45 Side St",
            city="Springfield",
            state="CA",
            postal_code="94111",
            country="US",
            capacity_limit=50,
            assigned_group_leader=None,
        )

        leader_list_resp = self.group_leader_client.get(
            "/api/v1/logistics/pickup-points/"
        )
        self.assertEqual(leader_list_resp.status_code, 200)
        ids = {entry["id"] for entry in leader_list_resp.json()}
        self.assertEqual(ids, {own_pickup.id})

        onboarding_self = GroupLeaderOnboarding.objects.create(
            organization=self.org_a,
            applicant=self.group_leader_a,
            pickup_point=own_pickup,
            status=OnboardingStatus.SUBMITTED,
            document_title="Self Doc",
            document_type="id",
            document_reference="SELF-1",
            document_metadata={},
        )
        GroupLeaderOnboarding.objects.create(
            organization=self.org_a,
            applicant=self.group_leader_b,
            pickup_point=own_pickup,
            status=OnboardingStatus.SUBMITTED,
            document_title="Other Doc",
            document_type="id",
            document_reference="OTHER-1",
            document_metadata={},
        )

        onboarding_list = self.group_leader_client.get(
            "/api/v1/logistics/group-leader-onboardings/"
        )
        self.assertEqual(onboarding_list.status_code, 200)
        onboarding_ids = {entry["id"] for entry in onboarding_list.json()}
        self.assertEqual(onboarding_ids, {onboarding_self.id})

        create_pickup_as_leader = self.group_leader_client.post(
            "/api/v1/logistics/pickup-points/",
            {
                "name": "Leader Create",
                "address_line1": "Nope",
                "city": "Springfield",
                "state": "CA",
                "postal_code": "94105",
                "country": "US",
                "capacity_limit": 10,
            },
            format="json",
        )
        self.assertEqual(create_pickup_as_leader.status_code, 403)

    def test_pickup_point_pii_encrypted_at_rest_and_masked_responses(self):
        raw_address_line1 = "123 Main Street"
        raw_address_line2 = "Suite 500"
        raw_city = "Springfield"
        raw_state = "CA"
        raw_postal = "94105"
        raw_country = "US"
        raw_phone = "(415) 555-1212"

        create_resp = self.manager_client.post(
            "/api/v1/logistics/pickup-points/",
            {
                "name": "PII Protected Pickup",
                "address_line1": raw_address_line1,
                "address_line2": raw_address_line2,
                "city": raw_city,
                "state": raw_state,
                "postal_code": raw_postal,
                "country": raw_country,
                "contact_phone": raw_phone,
                "capacity_limit": 150,
                "assigned_group_leader": self.group_leader_a.id,
            },
            format="json",
        )
        self.assertEqual(create_resp.status_code, 201)
        response_payload = create_resp.json()
        self.assertNotEqual(response_payload["address_line1"], raw_address_line1)
        self.assertNotEqual(response_payload["postal_code"], raw_postal)
        self.assertEqual(response_payload["contact_phone"], "***-***-1212")

        pickup_point = PickupPoint.objects.get(id=response_payload["id"])
        self.assertNotEqual(pickup_point.address_line1, raw_address_line1)
        self.assertNotEqual(pickup_point.city, raw_city)
        self.assertNotEqual(pickup_point.state, raw_state)
        self.assertNotEqual(pickup_point.postal_code, raw_postal)
        self.assertNotEqual(pickup_point.contact_phone, "4155551212")

        self.assertTrue(pickup_point.encrypted_address_line1)
        self.assertTrue(pickup_point.encrypted_postal_code)
        self.assertTrue(pickup_point.encrypted_contact_phone)

        self.assertEqual(
            decrypt_pii_value(pickup_point.encrypted_address_line1), raw_address_line1
        )
        self.assertEqual(
            decrypt_pii_value(pickup_point.encrypted_address_line2), raw_address_line2
        )
        self.assertEqual(decrypt_pii_value(pickup_point.encrypted_city), raw_city)
        self.assertEqual(decrypt_pii_value(pickup_point.encrypted_state), raw_state)
        self.assertEqual(
            decrypt_pii_value(pickup_point.encrypted_postal_code), raw_postal
        )
        self.assertEqual(decrypt_pii_value(pickup_point.encrypted_country), raw_country)
        self.assertEqual(
            decrypt_pii_value(pickup_point.encrypted_contact_phone), "4155551212"
        )

        detail_resp = self.manager_client.get(
            f"/api/v1/logistics/pickup-points/{pickup_point.id}/"
        )
        self.assertEqual(detail_resp.status_code, 200)
        self.assertEqual(detail_resp.json()["contact_phone"], "***-***-1212")
        self.assertNotEqual(detail_resp.json()["address_line1"], raw_address_line1)

    def test_member_can_submit_onboarding_and_approval_grants_group_leader_role(self):
        member = User.objects.create_user(
            username="log-member-a",
            password="ValidPass123!",
        )
        self._assign_role(member, self.org_a, RoleCode.MEMBER.value)
        member_client = self._build_client(member, self.org_a)
        pickup_point = self._create_pickup_point()

        submit_resp = member_client.post(
            "/api/v1/logistics/group-leader-onboardings/",
            {
                "pickup_point": pickup_point.id,
                "document_title": "Member Application",
                "document_type": "government_id",
                "document_reference": "DOC-MEMBER-1",
                "document_metadata": {"issuer": "DMV"},
            },
            format="json",
        )
        self.assertEqual(submit_resp.status_code, 201)
        onboarding_id = submit_resp.json()["id"]

        review_resp = self.reviewer_client.post(
            f"/api/v1/logistics/group-leader-onboardings/{onboarding_id}/review/",
            {"decision": "approved", "review_notes": "approved"},
            format="json",
        )
        self.assertEqual(review_resp.status_code, 200)

        self.assertTrue(
            UserOrganizationRole.objects.filter(
                user=member,
                organization=self.org_a,
                role__code=RoleCode.GROUP_LEADER.value,
                is_active=True,
            ).exists()
        )
