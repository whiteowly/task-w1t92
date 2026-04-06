from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from iam.models import Role, UserOrganizationRole
from observability.models import AuditLog
from tenancy.models import Organization

User = get_user_model()


class OrganizationApiTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(
            name="Main Org", slug="main-org", timezone="UTC"
        )
        self.password = "ValidPass123!"

        self.admin = User.objects.create_user(
            username="org-admin", password=self.password, full_name="Org Admin"
        )
        self.member = User.objects.create_user(
            username="org-member", password=self.password, full_name="Org Member"
        )

        admin_role = Role.objects.get(code="administrator")
        member_role = Role.objects.get(code="member")
        UserOrganizationRole.objects.create(
            user=self.admin, organization=self.org, role=admin_role
        )
        UserOrganizationRole.objects.create(
            user=self.member, organization=self.org, role=member_role
        )

        self.admin_client = self._authenticated_client(self.admin, self.org)
        self.member_client = self._authenticated_client(self.member, self.org)

    def _authenticated_client(self, user, org):
        client = APIClient()
        resp = client.post(
            "/api/v1/auth/login/",
            {
                "organization_slug": org.slug,
                "username": user.username,
                "password": self.password,
            },
            format="json",
        )
        client.credentials(HTTP_X_SESSION_KEY=resp.json()["session_key"])
        return client

    def test_create_organization_is_forbidden_for_tenant_scoped_api(self):
        resp = self.admin_client.post(
            "/api/v1/tenancy/organizations/",
            {"name": "New Org", "slug": "new-org", "timezone": "US/Eastern"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(Organization.objects.filter(slug="new-org").exists())
        self.assertFalse(AuditLog.objects.filter(action="organization.create").exists())

    def test_list_organizations_scoped_to_own_tenant(self):
        Organization.objects.create(name="Another", slug="another-org", timezone="UTC")
        resp = self.admin_client.get("/api/v1/tenancy/organizations/")
        self.assertEqual(resp.status_code, 200)
        slugs = [o["slug"] for o in resp.json()]
        self.assertIn("main-org", slugs)
        self.assertNotIn("another-org", slugs)

    def test_update_organization(self):
        resp = self.admin_client.patch(
            f"/api/v1/tenancy/organizations/{self.org.id}/",
            {"name": "Updated Org"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.org.refresh_from_db()
        self.assertEqual(self.org.name, "Updated Org")

    def test_non_admin_gets_403(self):
        resp = self.member_client.get("/api/v1/tenancy/organizations/")
        self.assertEqual(resp.status_code, 403)

        resp = self.member_client.post(
            "/api/v1/tenancy/organizations/",
            {"name": "Forbidden Org", "slug": "forbidden-org"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_cross_tenant_isolation(self):
        other_org = Organization.objects.create(
            name="Other Org", slug="other-org", timezone="UTC"
        )
        other_admin = User.objects.create_user(
            username="other-org-admin", password=self.password, full_name="Other Admin"
        )
        admin_role = Role.objects.get(code="administrator")
        UserOrganizationRole.objects.create(
            user=other_admin, organization=other_org, role=admin_role
        )
        other_client = self._authenticated_client(other_admin, other_org)

        resp = other_client.get("/api/v1/tenancy/organizations/")
        self.assertEqual(resp.status_code, 200)
        slugs = [o["slug"] for o in resp.json()]
        self.assertIn("other-org", slugs)
        self.assertNotIn("main-org", slugs)

        resp = other_client.get(f"/api/v1/tenancy/organizations/{self.org.id}/")
        self.assertEqual(resp.status_code, 404)

        resp = other_client.patch(
            f"/api/v1/tenancy/organizations/{self.org.id}/",
            {"name": "Hacked"},
            format="json",
        )
        self.assertEqual(resp.status_code, 404)

        resp = other_client.delete(f"/api/v1/tenancy/organizations/{self.org.id}/")
        self.assertEqual(resp.status_code, 404)
