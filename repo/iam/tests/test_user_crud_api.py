from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from iam.models import AuthSession, Role, UserOrganizationRole
from observability.models import AuditLog
from tenancy.models import Organization
from django.utils import timezone
from datetime import timedelta

User = get_user_model()


class UserDetailUpdateDeleteApiTests(TestCase):
    """Tests for GET/PUT/PATCH/DELETE /api/v1/auth/users/{id}/"""

    def setUp(self):
        self.org = Organization.objects.create(
            name="User CRUD Org", slug="user-crud-org", timezone="UTC"
        )
        self.other_org = Organization.objects.create(
            name="Other Org", slug="other-org-uc", timezone="UTC"
        )
        self.password = "ValidPass123!"

        self.admin = User.objects.create_user(
            username="uc-admin", password=self.password, full_name="Admin"
        )
        self.target_user = User.objects.create_user(
            username="uc-target", password=self.password, full_name="Target User",
            email="target@example.com",
        )
        self.member = User.objects.create_user(
            username="uc-member", password=self.password, full_name="Member"
        )
        self.other_admin = User.objects.create_user(
            username="uc-other-admin", password=self.password, full_name="Other Admin"
        )

        self._assign_role(self.admin, self.org, "administrator")
        self._assign_role(self.target_user, self.org, "member")
        self._assign_role(self.member, self.org, "member")
        self._assign_role(self.other_admin, self.other_org, "administrator")

        self.admin_client = self._build_client(self.admin, self.org)
        self.member_client = self._build_client(self.member, self.org)
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

    def test_retrieve_user_detail(self):
        resp = self.admin_client.get(f"/api/v1/auth/users/{self.target_user.id}/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["username"], "uc-target")
        self.assertEqual(data["full_name"], "Target User")
        self.assertIn("role_codes", data)
        self.assertIn("member", data["role_codes"])

    def test_retrieve_user_forbidden_for_member(self):
        resp = self.member_client.get(f"/api/v1/auth/users/{self.target_user.id}/")
        self.assertEqual(resp.status_code, 403)

    def test_retrieve_user_cross_tenant_returns_404(self):
        resp = self.other_admin_client.get(f"/api/v1/auth/users/{self.target_user.id}/")
        self.assertEqual(resp.status_code, 404)

    def test_partial_update_user(self):
        resp = self.admin_client.patch(
            f"/api/v1/auth/users/{self.target_user.id}/",
            {"full_name": "Updated Name"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["full_name"], "Updated Name")
        self.target_user.refresh_from_db()
        self.assertEqual(self.target_user.full_name, "Updated Name")
        self.assertTrue(
            AuditLog.objects.filter(action="user.update", resource_id=str(self.target_user.id)).exists()
        )

    def test_full_update_user(self):
        resp = self.admin_client.put(
            f"/api/v1/auth/users/{self.target_user.id}/",
            {
                "username": "uc-target",
                "full_name": "Fully Updated",
                "email": "updated@example.com",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["full_name"], "Fully Updated")
        self.assertEqual(resp.json()["email"], "updated@example.com")

    def test_update_user_forbidden_for_member(self):
        resp = self.member_client.patch(
            f"/api/v1/auth/users/{self.target_user.id}/",
            {"full_name": "Hacked"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_delete_user_deactivates_roles(self):
        resp = self.admin_client.delete(f"/api/v1/auth/users/{self.target_user.id}/")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(
            UserOrganizationRole.objects.filter(
                user=self.target_user, organization=self.org, is_active=True
            ).exists()
        )
        self.assertTrue(
            AuditLog.objects.filter(action="user.deactivate", resource_id=str(self.target_user.id)).exists()
        )

    def test_delete_user_forbidden_for_member(self):
        resp = self.member_client.delete(f"/api/v1/auth/users/{self.target_user.id}/")
        self.assertEqual(resp.status_code, 403)

    def test_delete_user_cross_tenant_returns_404(self):
        resp = self.other_admin_client.delete(f"/api/v1/auth/users/{self.target_user.id}/")
        self.assertEqual(resp.status_code, 404)

    def test_update_user_with_role_change(self):
        resp = self.admin_client.patch(
            f"/api/v1/auth/users/{self.target_user.id}/",
            {"roles": ["group_leader"]},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        active_roles = list(
            UserOrganizationRole.objects.filter(
                user=self.target_user, organization=self.org, is_active=True
            ).values_list("role__code", flat=True)
        )
        self.assertIn("group_leader", active_roles)
        self.assertNotIn("member", active_roles)
