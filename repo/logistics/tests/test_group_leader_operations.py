from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from iam.models import Role, UserOrganizationRole
from logistics.models import PickupPoint, PickupPointClosure
from observability.models import AuditLog
from tenancy.models import Organization

User = get_user_model()


class GroupLeaderOperationsTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(
            name="GL Org", slug="gl-org", timezone="UTC"
        )
        self.password = "ValidPass123!"

        self.manager = User.objects.create_user(
            username="gl-manager", password=self.password, full_name="Manager"
        )
        self.leader = User.objects.create_user(
            username="gl-leader", password=self.password, full_name="Leader"
        )
        self.other_leader = User.objects.create_user(
            username="gl-other-leader", password=self.password, full_name="Other Leader"
        )

        self._assign_role(self.manager, "club_manager")
        self._assign_role(self.leader, "group_leader")
        self._assign_role(self.other_leader, "group_leader")

        self.pickup = PickupPoint.objects.create(
            organization=self.org,
            name="Test PP",
            address_line1="123 Main",
            city="Town",
            state="CA",
            postal_code="12345",
            country="US",
            contact_phone="5551234567",
            capacity_limit=100,
            assigned_group_leader=self.leader,
        )
        self.other_pickup = PickupPoint.objects.create(
            organization=self.org,
            name="Other PP",
            address_line1="456 Oak",
            city="City",
            state="NY",
            postal_code="67890",
            country="US",
            contact_phone="5559876543",
            capacity_limit=50,
            assigned_group_leader=self.other_leader,
        )

        self.manager_client = self._authenticated_client(self.manager)
        self.leader_client = self._authenticated_client(self.leader)
        self.other_leader_client = self._authenticated_client(self.other_leader)

    def _assign_role(self, user, role_code):
        role = Role.objects.get(code=role_code)
        UserOrganizationRole.objects.create(user=user, organization=self.org, role=role)

    def _authenticated_client(self, user):
        client = APIClient()
        resp = client.post(
            "/api/v1/auth/login/",
            {
                "organization_slug": self.org.slug,
                "username": user.username,
                "password": self.password,
            },
            format="json",
        )
        if resp.status_code != 200:
            print(
                f"Login failed for {user.username}: status={resp.status_code} body={resp.content.decode('utf-8', errors='replace')}"
            )
        self.assertEqual(resp.status_code, 200)
        client.credentials(HTTP_X_SESSION_KEY=resp.json()["session_key"])
        return client

    def test_group_leader_creates_closure_for_assigned_point(self):
        now = timezone.now()
        resp = self.leader_client.post(
            "/api/v1/logistics/pickup-point-closures/",
            {
                "pickup_point": self.pickup.id,
                "starts_at": now.isoformat(),
                "ends_at": (now + timezone.timedelta(hours=4)).isoformat(),
                "reason": "Weather emergency",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(
            PickupPointClosure.objects.filter(
                pickup_point=self.pickup, reason="Weather emergency"
            ).exists()
        )
        self.assertTrue(
            AuditLog.objects.filter(action="pickup_point_closure.create").exists()
        )

    def test_group_leader_cannot_create_closure_for_unassigned_point(self):
        now = timezone.now()
        resp = self.leader_client.post(
            "/api/v1/logistics/pickup-point-closures/",
            {
                "pickup_point": self.other_pickup.id,
                "starts_at": now.isoformat(),
                "ends_at": (now + timezone.timedelta(hours=4)).isoformat(),
                "reason": "Should fail",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_group_leader_can_partial_update_assigned_pickup_point(self):
        resp = self.leader_client.patch(
            f"/api/v1/logistics/pickup-points/{self.pickup.id}/",
            {"name": "Updated PP Name"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.pickup.refresh_from_db()
        self.assertEqual(self.pickup.name, "Updated PP Name")

    def test_group_leader_cannot_update_unassigned_pickup_point(self):
        resp = self.leader_client.patch(
            f"/api/v1/logistics/pickup-points/{self.other_pickup.id}/",
            {"name": "Hacked"},
            format="json",
        )
        self.assertEqual(resp.status_code, 404)

    def test_manager_can_create_closure_for_any_point(self):
        now = timezone.now()
        resp = self.manager_client.post(
            "/api/v1/logistics/pickup-point-closures/",
            {
                "pickup_point": self.other_pickup.id,
                "starts_at": now.isoformat(),
                "ends_at": (now + timezone.timedelta(hours=4)).isoformat(),
                "reason": "Manager closure",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
