from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from common.constants import RoleCode
from iam.models import AuthSession, Role, UserOrganizationRole
from logistics.models import Location, Warehouse, Zone
from tenancy.models import Organization

User = get_user_model()


class TenantHierarchyApiTests(TestCase):
    def setUp(self):
        self.org_a = Organization.objects.create(
            name="Org A", slug="org-a", timezone="UTC"
        )
        self.org_b = Organization.objects.create(
            name="Org B", slug="org-b", timezone="UTC"
        )

        self.admin_a = User.objects.create_user(
            username="hier-admin-a", password="ValidPass123!"
        )
        self.manager_a = User.objects.create_user(
            username="hier-manager-a", password="ValidPass123!"
        )
        self.admin_b = User.objects.create_user(
            username="hier-admin-b", password="ValidPass123!"
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

    def test_hierarchy_admin_crud_and_location_validation(self):
        warehouse_resp = self.admin_client.post(
            "/api/v1/logistics/warehouses/",
            {"name": "Main Warehouse"},
            format="json",
        )
        self.assertEqual(warehouse_resp.status_code, 201)
        warehouse_id = warehouse_resp.json()["id"]

        zone_resp = self.admin_client.post(
            "/api/v1/logistics/zones/",
            {"warehouse": warehouse_id, "name": "Zone A"},
            format="json",
        )
        self.assertEqual(zone_resp.status_code, 201)
        zone_id = zone_resp.json()["id"]

        invalid_flag_resp = self.admin_client.post(
            "/api/v1/logistics/locations/",
            {
                "zone": zone_id,
                "code": "LOC-1",
                "length_in": "12.00",
                "width_in": "10.00",
                "height_in": "8.00",
                "load_limit_lbs": "100.00",
                "temperature_zone": "ambient",
                "restricted_handling_flags": ["invalid_flag"],
                "capacity_slots": 5,
            },
            format="json",
        )
        self.assertEqual(invalid_flag_resp.status_code, 400)

        invalid_dim_resp = self.admin_client.post(
            "/api/v1/logistics/locations/",
            {
                "zone": zone_id,
                "code": "LOC-2",
                "length_in": "0.00",
                "width_in": "10.00",
                "height_in": "8.00",
                "load_limit_lbs": "100.00",
                "temperature_zone": "ambient",
                "restricted_handling_flags": ["fragile"],
                "capacity_slots": 5,
            },
            format="json",
        )
        self.assertEqual(invalid_dim_resp.status_code, 400)

        valid_location_resp = self.admin_client.post(
            "/api/v1/logistics/locations/",
            {
                "zone": zone_id,
                "code": "LOC-3",
                "length_in": "12.00",
                "width_in": "10.00",
                "height_in": "8.00",
                "load_limit_lbs": "100.00",
                "temperature_zone": "chilled",
                "restricted_handling_flags": ["fragile", "temperature_sensitive"],
                "capacity_slots": 5,
            },
            format="json",
        )
        self.assertEqual(valid_location_resp.status_code, 201)

        location = Location.objects.get(id=valid_location_resp.json()["id"])
        self.assertEqual(location.temperature_zone, "chilled")
        self.assertEqual(
            location.restricted_handling_flags, ["fragile", "temperature_sensitive"]
        )

    def test_hierarchy_permissions_and_tenant_isolation(self):
        manager_create = self.manager_client.post(
            "/api/v1/logistics/warehouses/",
            {"name": "Should Fail"},
            format="json",
        )
        self.assertEqual(manager_create.status_code, 403)

        warehouse_b = Warehouse.objects.create(
            organization=self.org_b, name="B Warehouse"
        )
        zone_b = Zone.objects.create(
            organization=self.org_b, warehouse=warehouse_b, name="B Zone"
        )
        location_b = Location.objects.create(
            organization=self.org_b,
            zone=zone_b,
            code="B-LOC",
            length_in="5.00",
            width_in="5.00",
            height_in="5.00",
            load_limit_lbs="50.00",
            temperature_zone="ambient",
            restricted_handling_flags=[],
            capacity_slots=2,
        )

        self.assertEqual(
            self.admin_client.get(
                f"/api/v1/logistics/warehouses/{warehouse_b.id}/"
            ).status_code,
            404,
        )
        self.assertEqual(
            self.admin_client.get(f"/api/v1/logistics/zones/{zone_b.id}/").status_code,
            404,
        )
        self.assertEqual(
            self.admin_client.get(
                f"/api/v1/logistics/locations/{location_b.id}/"
            ).status_code,
            404,
        )
