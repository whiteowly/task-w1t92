from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from clubs.models import Club, Department, MemberStatus, Membership, MembershipStatusLog
from common.constants import RoleCode
from iam.models import AuthSession, Role, UserOrganizationRole
from observability.models import AuditLog
from tenancy.models import Organization

User = get_user_model()


class MembershipLifecycleApiTests(TestCase):
    def setUp(self):
        self.org_a = Organization.objects.create(
            name="Org A", slug="org-a", timezone="UTC"
        )
        self.org_b = Organization.objects.create(
            name="Org B", slug="org-b", timezone="UTC"
        )

        self.manager_a = User.objects.create_user(
            username="manager-a", password="ValidPass123!"
        )
        self.member_a = User.objects.create_user(
            username="member-a", password="ValidPass123!"
        )
        self.manager_b = User.objects.create_user(
            username="manager-b", password="ValidPass123!"
        )
        self.member_role_user = User.objects.create_user(
            username="member-role", password="ValidPass123!"
        )
        self.outsider_user = User.objects.create_user(
            username="outside-member", password="ValidPass123!"
        )

        self._assign_role(self.manager_a, self.org_a, RoleCode.CLUB_MANAGER.value)
        self._assign_role(self.manager_b, self.org_b, RoleCode.CLUB_MANAGER.value)
        self._assign_role(self.member_role_user, self.org_a, RoleCode.MEMBER.value)
        self._assign_role(self.member_a, self.org_a, RoleCode.MEMBER.value)

        self.client_a = self._build_client(self.manager_a, self.org_a)
        self.client_member_role = self._build_client(self.member_role_user, self.org_a)

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

    def test_membership_happy_path_join_then_leave_creates_status_logs_and_audit(self):
        club_resp = self.client_a.post(
            "/api/v1/clubs/clubs/",
            {"name": "History Club", "code": "HIST"},
            format="json",
        )
        self.assertEqual(club_resp.status_code, 201)
        club_id = club_resp.json()["id"]

        dept_resp = self.client_a.post(
            "/api/v1/clubs/departments/",
            {"name": "Archives", "club": club_id},
            format="json",
        )
        self.assertEqual(dept_resp.status_code, 201)
        department_id = dept_resp.json()["id"]

        join_resp = self.client_a.post(
            "/api/v1/clubs/memberships/join/",
            {
                "member": self.member_a.id,
                "club": club_id,
                "department": department_id,
                "reason_code": "NEW_JOIN",
                "effective_date": "2026-04-02",
            },
            format="json",
        )
        self.assertEqual(join_resp.status_code, 201)
        self.assertEqual(join_resp.json()["status"], MemberStatus.ACTIVE)
        membership_id = join_resp.json()["id"]

        leave_resp = self.client_a.post(
            f"/api/v1/clubs/memberships/{membership_id}/leave/",
            {"reason_code": "GRADUATED", "effective_date": "2026-05-01"},
            format="json",
        )
        self.assertEqual(leave_resp.status_code, 200)
        self.assertEqual(leave_resp.json()["status"], MemberStatus.ALUMNI)

        logs = MembershipStatusLog.objects.filter(membership_id=membership_id).order_by(
            "id"
        )
        self.assertEqual(logs.count(), 2)
        self.assertEqual(logs[0].from_status, MemberStatus.PENDING)
        self.assertEqual(logs[0].to_status, MemberStatus.ACTIVE)
        self.assertEqual(logs[1].from_status, MemberStatus.ACTIVE)
        self.assertEqual(logs[1].to_status, MemberStatus.ALUMNI)

        audit_actions = set(
            AuditLog.objects.filter(
                resource_type="membership", resource_id=str(membership_id)
            ).values_list("action", flat=True)
        )
        self.assertIn("membership.join", audit_actions)
        self.assertIn("membership.leave", audit_actions)

    def test_invalid_transition_returns_normalized_error_and_does_not_create_log(self):
        club = Club.objects.create(organization=self.org_a, name="Debate", code="DEB")
        membership = Membership.objects.create(
            organization=self.org_a,
            member=self.member_a,
            club=club,
            status=MemberStatus.BANNED,
        )

        response = self.client_a.post(
            f"/api/v1/clubs/memberships/{membership.id}/status-change/",
            {
                "to_status": MemberStatus.ACTIVE,
                "reason_code": "APPEAL",
                "effective_date": "2026-04-02",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "membership.invalid_transition")
        self.assertEqual(
            MembershipStatusLog.objects.filter(membership=membership).count(),
            0,
        )

    def test_status_logs_are_immutable(self):
        club = Club.objects.create(organization=self.org_a, name="Art", code="ART")
        membership = Membership.objects.create(
            organization=self.org_a,
            member=self.member_a,
            club=club,
            status=MemberStatus.PENDING,
        )

        response = self.client_a.post(
            f"/api/v1/clubs/memberships/{membership.id}/status-change/",
            {
                "to_status": MemberStatus.ACTIVE,
                "reason_code": "APPROVED",
                "effective_date": "2026-04-02",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)

        status_log = MembershipStatusLog.objects.get(membership=membership)
        status_log.reason_code = "CHANGED"
        with self.assertRaises(ValidationError):
            status_log.save()
        with self.assertRaises(ValidationError):
            status_log.delete()

    def test_cross_tenant_access_denied_and_member_role_cannot_manage(self):
        other_club = Club.objects.create(
            organization=self.org_b,
            name="Other Org Club",
            code="OTHER",
        )

        cross_tenant_response = self.client_a.get(
            f"/api/v1/clubs/clubs/{other_club.id}/"
        )
        self.assertEqual(cross_tenant_response.status_code, 404)

        forbidden_response = self.client_member_role.post(
            "/api/v1/clubs/clubs/",
            {"name": "Should Fail", "code": "FAIL"},
            format="json",
        )
        self.assertEqual(forbidden_response.status_code, 403)

    def test_membership_bypass_routes_are_rejected(self):
        club = Club.objects.create(organization=self.org_a, name="Policy", code="POL")
        department = Department.objects.create(
            organization=self.org_a,
            club=club,
            name="Policy Dept",
        )
        membership = Membership.objects.create(
            organization=self.org_a,
            member=self.member_a,
            club=club,
            department=department,
            status=MemberStatus.ACTIVE,
        )

        create_response = self.client_a.post(
            "/api/v1/clubs/memberships/",
            {
                "member": self.member_a.id,
                "club": club.id,
                "department": department.id,
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, 405)

        update_response = self.client_a.patch(
            f"/api/v1/clubs/memberships/{membership.id}/",
            {"department": None},
            format="json",
        )
        self.assertEqual(update_response.status_code, 405)

        delete_response = self.client_a.delete(
            f"/api/v1/clubs/memberships/{membership.id}/",
        )
        self.assertEqual(delete_response.status_code, 405)

    def test_join_rejects_active_user_outside_active_organization(self):
        club = Club.objects.create(organization=self.org_a, name="Music", code="MUS")

        response = self.client_a.post(
            "/api/v1/clubs/memberships/join/",
            {
                "member": self.outsider_user.id,
                "club": club.id,
                "reason_code": "NEW_JOIN",
                "effective_date": "2026-04-02",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "common.validation_error")
        self.assertTrue(
            any(
                detail["field"] == "member"
                and "outside of active organization" in detail["message"].lower()
                for detail in payload["error"]["details"]
            )
        )
        self.assertFalse(
            Membership.objects.filter(
                organization=self.org_a,
                member=self.outsider_user,
                club=club,
            ).exists()
        )
