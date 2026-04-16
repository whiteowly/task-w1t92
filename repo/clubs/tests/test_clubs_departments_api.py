from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from clubs.models import (
    Club,
    Department,
    MemberStatus,
    Membership,
    MembershipTransferLog,
)
from common.constants import RoleCode
from iam.models import AuthSession, Role, UserOrganizationRole
from tenancy.models import Organization

User = get_user_model()


class ClubsDepartmentsCrudApiTests(TestCase):
    """Tests for clubs/departments CRUD + memberships list/detail/transfer/status-log."""

    def setUp(self):
        self.org = Organization.objects.create(
            name="Club Org", slug="club-org", timezone="UTC"
        )
        self.other_org = Organization.objects.create(
            name="Other Club Org", slug="other-club-org", timezone="UTC"
        )
        self.password = "ValidPass123!"

        self.admin = User.objects.create_user(
            username="cd-admin", password=self.password, full_name="Admin"
        )
        self.manager = User.objects.create_user(
            username="cd-manager", password=self.password, full_name="Manager"
        )
        self.member = User.objects.create_user(
            username="cd-member", password=self.password, full_name="Member"
        )
        self.other_admin = User.objects.create_user(
            username="cd-other-admin", password=self.password, full_name="Other Admin"
        )

        self._assign_role(self.admin, self.org, RoleCode.ADMINISTRATOR.value)
        self._assign_role(self.manager, self.org, RoleCode.CLUB_MANAGER.value)
        self._assign_role(self.member, self.org, RoleCode.MEMBER.value)
        self._assign_role(
            self.other_admin, self.other_org, RoleCode.ADMINISTRATOR.value
        )

        self.admin_client = self._build_client(self.admin, self.org)
        self.manager_client = self._build_client(self.manager, self.org)
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

    # ---- Clubs CRUD ----

    def test_list_clubs(self):
        Club.objects.create(organization=self.org, name="Alpha Club", code="ALPHA")
        Club.objects.create(organization=self.org, name="Beta Club", code="BETA")
        Club.objects.create(
            organization=self.other_org, name="Gamma Club", code="GAMMA"
        )

        resp = self.admin_client.get("/api/v1/clubs/clubs/")
        self.assertEqual(resp.status_code, 200)
        names = [c["name"] for c in resp.json()]
        self.assertIn("Alpha Club", names)
        self.assertIn("Beta Club", names)
        self.assertNotIn("Gamma Club", names)

    def test_retrieve_club(self):
        club = Club.objects.create(
            organization=self.org, name="Detail Club", code="DET"
        )
        resp = self.admin_client.get(f"/api/v1/clubs/clubs/{club.id}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["name"], "Detail Club")
        self.assertEqual(resp.json()["code"], "DET")

    def test_update_club(self):
        club = Club.objects.create(organization=self.org, name="Old Name", code="OLD")
        resp = self.admin_client.patch(
            f"/api/v1/clubs/clubs/{club.id}/",
            {"name": "New Name"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["name"], "New Name")
        club.refresh_from_db()
        self.assertEqual(club.name, "New Name")

    def test_full_update_club(self):
        club = Club.objects.create(organization=self.org, name="Full Old", code="FOLD")
        resp = self.admin_client.put(
            f"/api/v1/clubs/clubs/{club.id}/",
            {"name": "Full New", "code": "FNEW"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["name"], "Full New")
        self.assertEqual(resp.json()["code"], "FNEW")

    def test_delete_club(self):
        club = Club.objects.create(organization=self.org, name="Delete Me", code="DEL")
        resp = self.admin_client.delete(f"/api/v1/clubs/clubs/{club.id}/")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(Club.objects.filter(id=club.id).exists())

    def test_member_cannot_create_or_delete_club(self):
        resp = self.member_client.post(
            "/api/v1/clubs/clubs/",
            {"name": "Hack Club", "code": "HACK"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_club_manager_can_crud_clubs(self):
        resp = self.manager_client.post(
            "/api/v1/clubs/clubs/",
            {"name": "Manager Club", "code": "MGR"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        club_id = resp.json()["id"]
        resp = self.manager_client.get(f"/api/v1/clubs/clubs/{club_id}/")
        self.assertEqual(resp.status_code, 200)

    # ---- Departments CRUD ----

    def test_list_departments(self):
        club = Club.objects.create(organization=self.org, name="Dept Club", code="DEPT")
        Department.objects.create(organization=self.org, club=club, name="Dept A")
        Department.objects.create(organization=self.org, club=club, name="Dept B")

        resp = self.admin_client.get("/api/v1/clubs/departments/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 2)

    def test_list_departments_filtered_by_club(self):
        club1 = Club.objects.create(organization=self.org, name="C1", code="C1")
        club2 = Club.objects.create(organization=self.org, name="C2", code="C2")
        Department.objects.create(organization=self.org, club=club1, name="D1")
        Department.objects.create(organization=self.org, club=club2, name="D2")

        resp = self.admin_client.get(f"/api/v1/clubs/departments/?club_id={club1.id}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)
        self.assertEqual(resp.json()[0]["name"], "D1")

    def test_retrieve_department(self):
        club = Club.objects.create(organization=self.org, name="DC", code="DC")
        dept = Department.objects.create(
            organization=self.org, club=club, name="Retrieve Dept"
        )
        resp = self.admin_client.get(f"/api/v1/clubs/departments/{dept.id}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["name"], "Retrieve Dept")

    def test_update_department(self):
        club = Club.objects.create(organization=self.org, name="UC", code="UC")
        dept = Department.objects.create(
            organization=self.org, club=club, name="Old Dept"
        )
        resp = self.admin_client.patch(
            f"/api/v1/clubs/departments/{dept.id}/",
            {"name": "New Dept"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["name"], "New Dept")

    def test_full_update_department(self):
        club = Club.objects.create(organization=self.org, name="FUC", code="FUC")
        dept = Department.objects.create(
            organization=self.org, club=club, name="Dept Old"
        )
        resp = self.admin_client.put(
            f"/api/v1/clubs/departments/{dept.id}/",
            {"name": "Dept New", "club": club.id},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["name"], "Dept New")

    def test_delete_department(self):
        club = Club.objects.create(organization=self.org, name="DelC", code="DELC")
        dept = Department.objects.create(
            organization=self.org, club=club, name="Del Dept"
        )
        resp = self.admin_client.delete(f"/api/v1/clubs/departments/{dept.id}/")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(Department.objects.filter(id=dept.id).exists())

    def test_department_cross_tenant_isolation(self):
        club = Club.objects.create(organization=self.org, name="IsoC", code="ISO")
        dept = Department.objects.create(
            organization=self.org, club=club, name="Iso Dept"
        )
        resp = self.other_admin_client.get(f"/api/v1/clubs/departments/{dept.id}/")
        self.assertEqual(resp.status_code, 404)

    # ---- Memberships List/Detail/Transfer/Status-Log ----

    def test_list_memberships(self):
        club = Club.objects.create(organization=self.org, name="ML Club", code="MLC")
        Membership.objects.create(
            organization=self.org,
            member=self.member,
            club=club,
            status=MemberStatus.ACTIVE,
        )
        resp = self.admin_client.get("/api/v1/clubs/memberships/")
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()), 1)

    def test_list_memberships_filtered_by_club(self):
        club1 = Club.objects.create(organization=self.org, name="F1", code="F1")
        club2 = Club.objects.create(organization=self.org, name="F2", code="F2")
        Membership.objects.create(
            organization=self.org,
            member=self.member,
            club=club1,
            status=MemberStatus.ACTIVE,
        )
        Membership.objects.create(
            organization=self.org,
            member=self.admin,
            club=club2,
            status=MemberStatus.ACTIVE,
        )
        resp = self.admin_client.get(f"/api/v1/clubs/memberships/?club_id={club1.id}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)

    def test_retrieve_membership(self):
        club = Club.objects.create(organization=self.org, name="RetC", code="RETC")
        membership = Membership.objects.create(
            organization=self.org,
            member=self.member,
            club=club,
            status=MemberStatus.ACTIVE,
        )
        resp = self.admin_client.get(f"/api/v1/clubs/memberships/{membership.id}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "active")

    def test_membership_transfer(self):
        club_from = Club.objects.create(
            organization=self.org, name="From Club", code="FROM"
        )
        club_to = Club.objects.create(organization=self.org, name="To Club", code="TO")
        membership = Membership.objects.create(
            organization=self.org,
            member=self.member,
            club=club_from,
            status=MemberStatus.ACTIVE,
        )

        resp = self.admin_client.post(
            f"/api/v1/clubs/memberships/{membership.id}/transfer/",
            {
                "to_club": club_to.id,
                "reason_code": "relocation",
                "effective_date": "2026-04-16",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["club"], club_to.id)
        self.assertTrue(
            MembershipTransferLog.objects.filter(
                membership=membership,
                from_club=club_from,
                to_club=club_to,
            ).exists()
        )

    def test_membership_status_log(self):
        club = Club.objects.create(organization=self.org, name="SL Club", code="SLC")
        resp = self.admin_client.post(
            "/api/v1/clubs/memberships/join/",
            {
                "member": self.member.id,
                "club": club.id,
                "reason_code": "new_member",
                "effective_date": "2026-04-16",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        membership_id = resp.json()["id"]

        log_resp = self.admin_client.get(
            f"/api/v1/clubs/memberships/{membership_id}/status-log/"
        )
        self.assertEqual(log_resp.status_code, 200)
        self.assertGreaterEqual(len(log_resp.json()), 1)
        log_entry = log_resp.json()[0]
        self.assertIn("from_status", log_entry)
        self.assertIn("to_status", log_entry)
        self.assertIn("reason_code", log_entry)

    def test_membership_cross_tenant_isolation(self):
        club = Club.objects.create(organization=self.org, name="TIC", code="TIC")
        membership = Membership.objects.create(
            organization=self.org,
            member=self.member,
            club=club,
            status=MemberStatus.ACTIVE,
        )
        resp = self.other_admin_client.get(
            f"/api/v1/clubs/memberships/{membership.id}/"
        )
        self.assertEqual(resp.status_code, 404)
