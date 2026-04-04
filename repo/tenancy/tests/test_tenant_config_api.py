from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from common.constants import RoleCode
from iam.models import AuthSession, Role, UserOrganizationRole
from observability.models import AuditLog
from tenancy.models import Organization, TenantConfigVersion

User = get_user_model()


class TenantConfigApiTests(TestCase):
    def setUp(self):
        self.org_a = Organization.objects.create(
            name="Org A", slug="org-a", timezone="UTC"
        )
        self.org_b = Organization.objects.create(
            name="Org B", slug="org-b", timezone="UTC"
        )

        self.admin_a = User.objects.create_user(
            username="cfg-admin-a", password="ValidPass123!"
        )
        self.manager_a = User.objects.create_user(
            username="cfg-manager-a", password="ValidPass123!"
        )
        self.admin_b = User.objects.create_user(
            username="cfg-admin-b", password="ValidPass123!"
        )

        self._assign_role(self.admin_a, self.org_a, RoleCode.ADMINISTRATOR.value)
        self._assign_role(self.manager_a, self.org_a, RoleCode.CLUB_MANAGER.value)
        self._assign_role(self.admin_b, self.org_b, RoleCode.ADMINISTRATOR.value)

        self.admin_client = self._build_client(self.admin_a, self.org_a)
        self.manager_client = self._build_client(self.manager_a, self.org_a)

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

    def test_config_version_creation_and_rollback_creates_new_version(self):
        baseline_get = self.admin_client.get("/api/v1/tenancy/config/")
        self.assertEqual(baseline_get.status_code, 200)
        self.assertEqual(baseline_get.json()["current_version"], 0)

        manager_update = self.manager_client.patch(
            "/api/v1/tenancy/config/",
            {
                "config_patch": {"features": {"alpha": True}},
                "change_summary": "manager try",
            },
            format="json",
        )
        self.assertEqual(manager_update.status_code, 403)

        v1_resp = self.admin_client.patch(
            "/api/v1/tenancy/config/",
            {
                "config_patch": {"features": {"alpha": True}, "timezone": "UTC"},
                "change_summary": "Enable alpha",
            },
            format="json",
        )
        self.assertEqual(v1_resp.status_code, 201)
        self.assertEqual(v1_resp.json()["version_number"], 1)

        v2_resp = self.admin_client.patch(
            "/api/v1/tenancy/config/",
            {
                "config_patch": {"features": {"beta": False}},
                "change_summary": "Set beta",
            },
            format="json",
        )
        self.assertEqual(v2_resp.status_code, 201)
        self.assertEqual(v2_resp.json()["version_number"], 2)

        versions_resp = self.admin_client.get("/api/v1/tenancy/config/versions/")
        self.assertEqual(versions_resp.status_code, 200)
        self.assertEqual(len(versions_resp.json()), 2)

        rollback_resp = self.admin_client.post(
            "/api/v1/tenancy/config/versions/1/rollback/",
            {"change_summary": "Rollback to v1"},
            format="json",
        )
        self.assertEqual(rollback_resp.status_code, 201)
        self.assertEqual(rollback_resp.json()["version_number"], 3)

        v1 = TenantConfigVersion.objects.get(organization=self.org_a, version_number=1)
        v3 = TenantConfigVersion.objects.get(organization=self.org_a, version_number=3)
        self.assertEqual(v3.config_payload, v1.config_payload)

        actions = set(
            AuditLog.objects.filter(
                organization=self.org_a, resource_type="tenant_config_version"
            ).values_list("action", flat=True)
        )
        self.assertIn("tenant_config.update", actions)
        self.assertIn("tenant_config.rollback", actions)

    def test_rollback_window_enforced_and_tenant_isolated(self):
        create_resp = self.admin_client.patch(
            "/api/v1/tenancy/config/",
            {
                "config_patch": {"ops": {"window": "A"}},
                "change_summary": "Create version for rollback test",
            },
            format="json",
        )
        self.assertEqual(create_resp.status_code, 201)
        version_id = create_resp.json()["id"]

        TenantConfigVersion.objects.filter(id=version_id).update(
            rollback_deadline_at=timezone.now() - timedelta(days=1)
        )

        rollback_expired_resp = self.admin_client.post(
            f"/api/v1/tenancy/config/versions/{version_id}/rollback/",
            {"change_summary": "too late"},
            format="json",
        )
        self.assertEqual(rollback_expired_resp.status_code, 400)
        self.assertEqual(
            rollback_expired_resp.json()["error"]["code"],
            "tenant_config.rollback_window_expired",
        )

        other_org_version = TenantConfigVersion.objects.create(
            organization=self.org_b,
            version_number=1,
            config_payload={"ops": {"region": "B"}},
            changed_by_user_id=self.admin_b.id,
            change_summary="Org B config",
            change_diff={"ops": {"from": None, "to": {"region": "B"}}},
            rollback_deadline_at=timezone.now() + timedelta(days=30),
        )

        cross_tenant_rollback = self.admin_client.post(
            f"/api/v1/tenancy/config/versions/{other_org_version.id}/rollback/",
            {"change_summary": "cross-tenant"},
            format="json",
        )
        self.assertEqual(cross_tenant_rollback.status_code, 404)

    def test_current_organization_returns_authenticated_org_details(self):
        response = self.admin_client.get("/api/v1/tenancy/organizations/current/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "id": self.org_a.id,
                "name": self.org_a.name,
                "slug": self.org_a.slug,
                "timezone": self.org_a.timezone,
                "is_active": True,
            },
        )

    def test_current_organization_requires_authentication(self):
        response = APIClient().get("/api/v1/tenancy/organizations/current/")

        self.assertEqual(response.status_code, 403)
