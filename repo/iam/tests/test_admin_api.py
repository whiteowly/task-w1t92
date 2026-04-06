from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from iam.models import Role, UserOrganizationRole
from observability.models import AuditLog
from tenancy.models import Organization

User = get_user_model()


class AdminUserApiTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(
            name="Admin Org", slug="admin-org", timezone="UTC"
        )
        self.other_org = Organization.objects.create(
            name="Other Org", slug="other-org", timezone="UTC"
        )
        self.password = "ValidPass123!"

        self.admin = User.objects.create_user(
            username="admin-user", password=self.password, full_name="Admin User"
        )
        self.member = User.objects.create_user(
            username="member-user", password=self.password, full_name="Member User"
        )
        self.other_admin = User.objects.create_user(
            username="other-admin", password=self.password, full_name="Other Admin"
        )

        self._assign_role(self.admin, self.org, "administrator")
        self._assign_role(self.member, self.org, "member")
        self._assign_role(self.other_admin, self.other_org, "administrator")

        self.admin_client = self._authenticated_client(self.admin, self.org)
        self.member_client = self._authenticated_client(self.member, self.org)
        self.other_admin_client = self._authenticated_client(
            self.other_admin, self.other_org
        )

    def _assign_role(self, user, org, role_code):
        role = Role.objects.get(code=role_code)
        UserOrganizationRole.objects.create(
            user=user, organization=org, role=role
        )

    def _authenticated_client(self, user, org):
        client = APIClient()
        resp = client.post(
            "/api/v1/auth/login/",
            {"organization_slug": org.slug, "username": user.username, "password": self.password},
            format="json",
        )
        client.credentials(HTTP_X_SESSION_KEY=resp.json()["session_key"])
        return client

    def test_create_user_with_role(self):
        resp = self.admin_client.post(
            "/api/v1/auth/users/",
            {
                "username": "new-user",
                "full_name": "New User",
                "password": "StrongPass789!",
                "roles": ["member"],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["username"], "new-user")
        user = User.objects.get(username="new-user")
        self.assertTrue(user.check_password("StrongPass789!"))
        self.assertTrue(
            UserOrganizationRole.objects.filter(
                user=user, organization=self.org, role__code="member", is_active=True
            ).exists()
        )
        self.assertTrue(
            AuditLog.objects.filter(action="user.create", resource_id=str(user.id)).exists()
        )

    def test_assign_role(self):
        resp = self.admin_client.post(
            f"/api/v1/auth/users/{self.member.id}/assign-role/",
            {"role_code": "group_leader"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(
            UserOrganizationRole.objects.filter(
                user=self.member, organization=self.org, role__code="group_leader", is_active=True
            ).exists()
        )
        self.assertTrue(
            AuditLog.objects.filter(action="user.role.assign").exists()
        )

    def test_revoke_role(self):
        self._assign_role(self.member, self.org, "group_leader")
        resp = self.admin_client.post(
            f"/api/v1/auth/users/{self.member.id}/revoke-role/",
            {"role_code": "group_leader"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(
            UserOrganizationRole.objects.filter(
                user=self.member, organization=self.org, role__code="group_leader", is_active=True
            ).exists()
        )
        self.assertTrue(
            AuditLog.objects.filter(action="user.role.revoke").exists()
        )

    def test_non_admin_gets_403(self):
        resp = self.member_client.get("/api/v1/auth/users/")
        self.assertEqual(resp.status_code, 403)

        resp = self.member_client.post(
            "/api/v1/auth/users/",
            {"username": "hacker", "password": "StrongPass789!"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_cross_tenant_isolation(self):
        resp = self.other_admin_client.get("/api/v1/auth/users/")
        self.assertEqual(resp.status_code, 200)
        usernames = [u["username"] for u in resp.json()]
        self.assertIn("other-admin", usernames)
        self.assertNotIn("admin-user", usernames)
        self.assertNotIn("member-user", usernames)

    def test_list_users(self):
        resp = self.admin_client.get("/api/v1/auth/users/")
        self.assertEqual(resp.status_code, 200)
        usernames = [u["username"] for u in resp.json()]
        self.assertIn("admin-user", usernames)
        self.assertIn("member-user", usernames)
