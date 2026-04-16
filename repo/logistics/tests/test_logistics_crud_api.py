from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from common.constants import RoleCode
from iam.models import AuthSession, Role, UserOrganizationRole
from logistics.models import (
    Location,
    PickupPoint,
    PickupPointBusinessHour,
    PickupPointClosure,
    Warehouse,
    Zone,
)
from observability.models import AuditLog
from tenancy.models import Organization

User = get_user_model()


class LogisticsCrudApiTests(TestCase):
    """Tests for hierarchy CRUD, pickup-point business-hours/closures retrieve/update/delete."""

    def setUp(self):
        self.org = Organization.objects.create(
            name="Logistics Org", slug="logistics-org", timezone="UTC"
        )
        self.other_org = Organization.objects.create(
            name="Logistics Other Org", slug="logistics-other-org", timezone="UTC"
        )
        self.password = "ValidPass123!"

        self.admin = User.objects.create_user(
            username="log-admin", password=self.password, full_name="Admin"
        )
        self.group_leader = User.objects.create_user(
            username="log-leader", password=self.password, full_name="Leader"
        )
        self.member = User.objects.create_user(
            username="log-member", password=self.password, full_name="Member"
        )
        self.other_admin = User.objects.create_user(
            username="log-other-admin", password=self.password, full_name="Other Admin"
        )

        self._assign_role(self.admin, self.org, RoleCode.ADMINISTRATOR.value)
        self._assign_role(self.group_leader, self.org, RoleCode.GROUP_LEADER.value)
        self._assign_role(self.member, self.org, RoleCode.MEMBER.value)
        self._assign_role(
            self.other_admin, self.other_org, RoleCode.ADMINISTRATOR.value
        )

        self.admin_client = self._build_client(self.admin, self.org)
        self.leader_client = self._build_client(self.group_leader, self.org)
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

    # ---- Warehouse CRUD ----

    def test_list_warehouses(self):
        Warehouse.objects.create(organization=self.org, name="WH A")
        Warehouse.objects.create(organization=self.org, name="WH B")
        resp = self.admin_client.get("/api/v1/logistics/warehouses/")
        self.assertEqual(resp.status_code, 200)
        names = [w["name"] for w in resp.json()]
        self.assertIn("WH A", names)
        self.assertIn("WH B", names)

    def test_retrieve_warehouse(self):
        wh = Warehouse.objects.create(organization=self.org, name="WH Detail")
        resp = self.admin_client.get(f"/api/v1/logistics/warehouses/{wh.id}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["name"], "WH Detail")

    def test_update_warehouse(self):
        wh = Warehouse.objects.create(organization=self.org, name="WH Old")
        resp = self.admin_client.patch(
            f"/api/v1/logistics/warehouses/{wh.id}/",
            {"name": "WH New"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["name"], "WH New")
        self.assertTrue(AuditLog.objects.filter(action="warehouse.update").exists())

    def test_full_update_warehouse(self):
        wh = Warehouse.objects.create(organization=self.org, name="WH Full Old")
        resp = self.admin_client.put(
            f"/api/v1/logistics/warehouses/{wh.id}/",
            {"name": "WH Full New"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["name"], "WH Full New")

    def test_delete_warehouse(self):
        wh = Warehouse.objects.create(organization=self.org, name="WH Del")
        resp = self.admin_client.delete(f"/api/v1/logistics/warehouses/{wh.id}/")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(Warehouse.objects.filter(id=wh.id).exists())
        self.assertTrue(AuditLog.objects.filter(action="warehouse.delete").exists())

    def test_warehouse_member_forbidden(self):
        resp = self.member_client.get("/api/v1/logistics/warehouses/")
        self.assertEqual(resp.status_code, 403)

    # ---- Zone CRUD ----

    def test_list_zones(self):
        wh = Warehouse.objects.create(organization=self.org, name="ZWH")
        Zone.objects.create(organization=self.org, warehouse=wh, name="Zone A")
        resp = self.admin_client.get("/api/v1/logistics/zones/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)

    def test_retrieve_zone(self):
        wh = Warehouse.objects.create(organization=self.org, name="ZWH2")
        zone = Zone.objects.create(
            organization=self.org, warehouse=wh, name="Zone Detail"
        )
        resp = self.admin_client.get(f"/api/v1/logistics/zones/{zone.id}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["name"], "Zone Detail")

    def test_update_zone(self):
        wh = Warehouse.objects.create(organization=self.org, name="ZUWH")
        zone = Zone.objects.create(organization=self.org, warehouse=wh, name="Zone Old")
        resp = self.admin_client.patch(
            f"/api/v1/logistics/zones/{zone.id}/",
            {"name": "Zone New"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["name"], "Zone New")
        self.assertTrue(AuditLog.objects.filter(action="zone.update").exists())

    def test_full_update_zone(self):
        wh = Warehouse.objects.create(organization=self.org, name="ZFUWH")
        zone = Zone.objects.create(
            organization=self.org, warehouse=wh, name="Zone Full Old"
        )
        resp = self.admin_client.put(
            f"/api/v1/logistics/zones/{zone.id}/",
            {"warehouse": wh.id, "name": "Zone Full New"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["name"], "Zone Full New")

    def test_delete_zone(self):
        wh = Warehouse.objects.create(organization=self.org, name="ZDWH")
        zone = Zone.objects.create(organization=self.org, warehouse=wh, name="Zone Del")
        resp = self.admin_client.delete(f"/api/v1/logistics/zones/{zone.id}/")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(Zone.objects.filter(id=zone.id).exists())

    # ---- Location CRUD ----

    def test_list_locations(self):
        wh = Warehouse.objects.create(organization=self.org, name="LWH")
        zone = Zone.objects.create(organization=self.org, warehouse=wh, name="LZone")
        Location.objects.create(
            organization=self.org,
            zone=zone,
            code="LOC-A",
            length_in=10,
            width_in=10,
            height_in=10,
            load_limit_lbs=100,
        )
        resp = self.admin_client.get("/api/v1/logistics/locations/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)

    def test_retrieve_location(self):
        wh = Warehouse.objects.create(organization=self.org, name="LRWH")
        zone = Zone.objects.create(organization=self.org, warehouse=wh, name="LRZone")
        loc = Location.objects.create(
            organization=self.org,
            zone=zone,
            code="LOC-R",
            length_in=10,
            width_in=10,
            height_in=10,
            load_limit_lbs=100,
        )
        resp = self.admin_client.get(f"/api/v1/logistics/locations/{loc.id}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["code"], "LOC-R")

    def test_update_location(self):
        wh = Warehouse.objects.create(organization=self.org, name="LUWH")
        zone = Zone.objects.create(organization=self.org, warehouse=wh, name="LUZone")
        loc = Location.objects.create(
            organization=self.org,
            zone=zone,
            code="LOC-U",
            length_in=10,
            width_in=10,
            height_in=10,
            load_limit_lbs=100,
        )
        resp = self.admin_client.patch(
            f"/api/v1/logistics/locations/{loc.id}/",
            {"load_limit_lbs": "200.00"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["load_limit_lbs"], "200.00")
        self.assertTrue(AuditLog.objects.filter(action="location.update").exists())

    def test_full_update_location(self):
        wh = Warehouse.objects.create(organization=self.org, name="LFUWH")
        zone = Zone.objects.create(organization=self.org, warehouse=wh, name="LFUZone")
        loc = Location.objects.create(
            organization=self.org,
            zone=zone,
            code="LOC-FU",
            length_in=10,
            width_in=10,
            height_in=10,
            load_limit_lbs=100,
            temperature_zone="ambient",
            restricted_handling_flags=[],
            capacity_slots=1,
        )
        resp = self.admin_client.put(
            f"/api/v1/logistics/locations/{loc.id}/",
            {
                "zone": zone.id,
                "code": "LOC-FU",
                "length_in": "11.00",
                "width_in": "12.00",
                "height_in": "13.00",
                "load_limit_lbs": "140.00",
                "temperature_zone": "chilled",
                "restricted_handling_flags": ["fragile"],
                "capacity_slots": 4,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["temperature_zone"], "chilled")

    def test_delete_location(self):
        wh = Warehouse.objects.create(organization=self.org, name="LDWH")
        zone = Zone.objects.create(organization=self.org, warehouse=wh, name="LDZone")
        loc = Location.objects.create(
            organization=self.org,
            zone=zone,
            code="LOC-D",
            length_in=10,
            width_in=10,
            height_in=10,
            load_limit_lbs=100,
        )
        resp = self.admin_client.delete(f"/api/v1/logistics/locations/{loc.id}/")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(Location.objects.filter(id=loc.id).exists())

    # ---- Pickup Point Business Hours CRUD ----

    def test_retrieve_business_hour(self):
        pp = PickupPoint.objects.create(
            organization=self.org,
            name="BH PP",
            address_line1="123 St",
            city="NYC",
            state="NY",
            postal_code="10001",
            capacity_limit=50,
            assigned_group_leader=self.group_leader,
        )
        bh = PickupPointBusinessHour.objects.create(
            organization=self.org,
            pickup_point=pp,
            weekday=0,
            opens_at="09:00",
            closes_at="17:00",
        )
        resp = self.admin_client.get(
            f"/api/v1/logistics/pickup-point-business-hours/{bh.id}/"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["weekday"], 0)

    def test_update_business_hour(self):
        pp = PickupPoint.objects.create(
            organization=self.org,
            name="BH Update PP",
            address_line1="124 St",
            city="NYC",
            state="NY",
            postal_code="10002",
            capacity_limit=50,
            assigned_group_leader=self.group_leader,
        )
        bh = PickupPointBusinessHour.objects.create(
            organization=self.org,
            pickup_point=pp,
            weekday=1,
            opens_at="09:00",
            closes_at="17:00",
        )
        resp = self.admin_client.patch(
            f"/api/v1/logistics/pickup-point-business-hours/{bh.id}/",
            {
                "pickup_point": pp.id,
                "weekday": 1,
                "opens_at": "09:00",
                "closes_at": "18:00",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["closes_at"], "18:00:00")

    def test_full_update_business_hour(self):
        pp = PickupPoint.objects.create(
            organization=self.org,
            name="BH Full PP",
            address_line1="124A St",
            city="NYC",
            state="NY",
            postal_code="10002",
            country="US",
            capacity_limit=50,
            assigned_group_leader=self.group_leader,
        )
        bh = PickupPointBusinessHour.objects.create(
            organization=self.org,
            pickup_point=pp,
            weekday=2,
            opens_at="08:00",
            closes_at="16:00",
        )
        resp = self.admin_client.put(
            f"/api/v1/logistics/pickup-point-business-hours/{bh.id}/",
            {
                "pickup_point": pp.id,
                "weekday": 2,
                "opens_at": "08:30",
                "closes_at": "16:30",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["opens_at"], "08:30:00")

    def test_delete_business_hour(self):
        pp = PickupPoint.objects.create(
            organization=self.org,
            name="BH Del PP",
            address_line1="125 St",
            city="NYC",
            state="NY",
            postal_code="10003",
            capacity_limit=50,
        )
        bh = PickupPointBusinessHour.objects.create(
            organization=self.org,
            pickup_point=pp,
            weekday=2,
            opens_at="09:00",
            closes_at="17:00",
        )
        resp = self.admin_client.delete(
            f"/api/v1/logistics/pickup-point-business-hours/{bh.id}/"
        )
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(PickupPointBusinessHour.objects.filter(id=bh.id).exists())

    def test_list_business_hours(self):
        pp = PickupPoint.objects.create(
            organization=self.org,
            name="BH List PP",
            address_line1="126 St",
            city="NYC",
            state="NY",
            postal_code="10004",
            capacity_limit=50,
        )
        PickupPointBusinessHour.objects.create(
            organization=self.org,
            pickup_point=pp,
            weekday=3,
            opens_at="09:00",
            closes_at="17:00",
        )
        resp = self.admin_client.get("/api/v1/logistics/pickup-point-business-hours/")
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()), 1)

    # ---- Pickup Point Closure CRUD ----

    def test_retrieve_closure(self):
        pp = PickupPoint.objects.create(
            organization=self.org,
            name="CL PP",
            address_line1="127 St",
            city="NYC",
            state="NY",
            postal_code="10005",
            capacity_limit=50,
            assigned_group_leader=self.group_leader,
        )
        cl = PickupPointClosure.objects.create(
            organization=self.org,
            pickup_point=pp,
            starts_at=timezone.now(),
            ends_at=timezone.now() + timedelta(hours=4),
            reason="Holiday",
        )
        resp = self.admin_client.get(
            f"/api/v1/logistics/pickup-point-closures/{cl.id}/"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["reason"], "Holiday")

    def test_update_closure(self):
        pp = PickupPoint.objects.create(
            organization=self.org,
            name="CL Update PP",
            address_line1="128 St",
            city="NYC",
            state="NY",
            postal_code="10006",
            capacity_limit=50,
            assigned_group_leader=self.group_leader,
        )
        starts = timezone.now()
        ends = starts + timedelta(hours=4)
        cl = PickupPointClosure.objects.create(
            organization=self.org,
            pickup_point=pp,
            starts_at=starts,
            ends_at=ends,
            reason="Old Reason",
        )
        resp = self.admin_client.patch(
            f"/api/v1/logistics/pickup-point-closures/{cl.id}/",
            {
                "pickup_point": pp.id,
                "starts_at": starts.isoformat(),
                "ends_at": ends.isoformat(),
                "reason": "New Reason",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["reason"], "New Reason")

    def test_full_update_closure(self):
        pp = PickupPoint.objects.create(
            organization=self.org,
            name="CL Full PP",
            address_line1="128A St",
            city="NYC",
            state="NY",
            postal_code="10006",
            country="US",
            capacity_limit=50,
            assigned_group_leader=self.group_leader,
        )
        starts = timezone.now()
        ends = starts + timedelta(hours=4)
        cl = PickupPointClosure.objects.create(
            organization=self.org,
            pickup_point=pp,
            starts_at=starts,
            ends_at=ends,
            reason="Old Full Reason",
        )
        resp = self.admin_client.put(
            f"/api/v1/logistics/pickup-point-closures/{cl.id}/",
            {
                "pickup_point": pp.id,
                "starts_at": starts.isoformat(),
                "ends_at": ends.isoformat(),
                "reason": "Full New Reason",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["reason"], "Full New Reason")

    def test_delete_closure(self):
        pp = PickupPoint.objects.create(
            organization=self.org,
            name="CL Del PP",
            address_line1="129 St",
            city="NYC",
            state="NY",
            postal_code="10007",
            capacity_limit=50,
            assigned_group_leader=self.group_leader,
        )
        cl = PickupPointClosure.objects.create(
            organization=self.org,
            pickup_point=pp,
            starts_at=timezone.now(),
            ends_at=timezone.now() + timedelta(hours=4),
            reason="Closing",
        )
        resp = self.admin_client.delete(
            f"/api/v1/logistics/pickup-point-closures/{cl.id}/"
        )
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(PickupPointClosure.objects.filter(id=cl.id).exists())

    def test_list_closures(self):
        pp = PickupPoint.objects.create(
            organization=self.org,
            name="CL List PP",
            address_line1="130 St",
            city="NYC",
            state="NY",
            postal_code="10008",
            capacity_limit=50,
        )
        PickupPointClosure.objects.create(
            organization=self.org,
            pickup_point=pp,
            starts_at=timezone.now(),
            ends_at=timezone.now() + timedelta(hours=4),
            reason="Storm",
        )
        resp = self.admin_client.get("/api/v1/logistics/pickup-point-closures/")
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()), 1)

    # ---- Pickup Point delete ----

    def test_delete_pickup_point(self):
        pp = PickupPoint.objects.create(
            organization=self.org,
            name="PP Del",
            address_line1="131 St",
            city="NYC",
            state="NY",
            postal_code="10009",
            capacity_limit=50,
        )
        resp = self.admin_client.delete(f"/api/v1/logistics/pickup-points/{pp.id}/")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(PickupPoint.objects.filter(id=pp.id).exists())
        self.assertTrue(AuditLog.objects.filter(action="pickup_point.delete").exists())

    def test_full_update_pickup_point(self):
        pp = PickupPoint.objects.create(
            organization=self.org,
            name="PP Full Old",
            address_line1="131A St",
            city="NYC",
            state="NY",
            postal_code="10009",
            country="US",
            capacity_limit=50,
            assigned_group_leader=self.group_leader,
        )
        resp = self.admin_client.put(
            f"/api/v1/logistics/pickup-points/{pp.id}/",
            {
                "name": "PP Full New",
                "address_line1": "500 Updated Ave",
                "address_line2": "Suite 20",
                "city": "New York",
                "state": "NY",
                "postal_code": "10012",
                "country": "US",
                "contact_phone": "2125550100",
                "capacity_limit": 75,
                "assigned_group_leader": self.group_leader.id,
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["name"], "PP Full New")

    def test_group_leader_sees_only_assigned_business_hours(self):
        pp_assigned = PickupPoint.objects.create(
            organization=self.org,
            name="Assigned PP",
            address_line1="132 St",
            city="NYC",
            state="NY",
            postal_code="10010",
            capacity_limit=50,
            assigned_group_leader=self.group_leader,
        )
        pp_other = PickupPoint.objects.create(
            organization=self.org,
            name="Other PP",
            address_line1="133 St",
            city="NYC",
            state="NY",
            postal_code="10011",
            capacity_limit=50,
        )
        PickupPointBusinessHour.objects.create(
            organization=self.org,
            pickup_point=pp_assigned,
            weekday=0,
            opens_at="09:00",
            closes_at="17:00",
        )
        PickupPointBusinessHour.objects.create(
            organization=self.org,
            pickup_point=pp_other,
            weekday=1,
            opens_at="09:00",
            closes_at="17:00",
        )
        resp = self.leader_client.get("/api/v1/logistics/pickup-point-business-hours/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)
