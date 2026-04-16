from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from clubs.models import Club, MemberStatus, Membership
from common.constants import RoleCode
from events.models import (
    Event,
    EventAttendanceReconciliation,
    EventCheckIn,
    EventRegistration,
    EventResourceDownload,
)
from iam.models import AuthSession, Role, UserOrganizationRole
from observability.models import AuditLog
from tenancy.models import Organization

User = get_user_model()


class EventsCrudApiTests(TestCase):
    """Tests for events list/detail/update/delete, checkins list, reconciliations list."""

    def setUp(self):
        self.org = Organization.objects.create(
            name="Events Org", slug="events-org", timezone="UTC"
        )
        self.other_org = Organization.objects.create(
            name="Events Other Org", slug="events-other-org", timezone="UTC"
        )
        self.password = "ValidPass123!"

        self.admin = User.objects.create_user(
            username="ev-admin", password=self.password, full_name="Admin"
        )
        self.member = User.objects.create_user(
            username="ev-member", password=self.password, full_name="Member"
        )
        self.other_admin = User.objects.create_user(
            username="ev-other-admin", password=self.password, full_name="Other Admin"
        )

        self._assign_role(self.admin, self.org, RoleCode.ADMINISTRATOR.value)
        self._assign_role(self.member, self.org, RoleCode.MEMBER.value)
        self._assign_role(self.other_admin, self.other_org, RoleCode.ADMINISTRATOR.value)

        self.admin_client = self._build_client(self.admin, self.org)
        self.member_client = self._build_client(self.member, self.org)
        self.other_admin_client = self._build_client(self.other_admin, self.other_org)

        self.club = Club.objects.create(
            organization=self.org, name="Ev Club", code="EVC"
        )
        Membership.objects.create(
            organization=self.org,
            member=self.member,
            club=self.club,
            status=MemberStatus.ACTIVE,
        )

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

    def _create_event(self, title="Test Event"):
        return Event.objects.create(
            organization=self.org,
            club=self.club,
            title=title,
            starts_at=timezone.now(),
            ends_at=timezone.now() + timedelta(hours=1),
            eligible_member_count_snapshot=10,
        )

    def test_list_events(self):
        self._create_event("Ev A")
        self._create_event("Ev B")
        resp = self.admin_client.get("/api/v1/events/events/")
        self.assertEqual(resp.status_code, 200)
        titles = [e["title"] for e in resp.json()]
        self.assertIn("Ev A", titles)
        self.assertIn("Ev B", titles)

    def test_list_events_tenant_isolated(self):
        self._create_event("Org A Event")
        other_club = Club.objects.create(
            organization=self.other_org, name="OC", code="OC"
        )
        Event.objects.create(
            organization=self.other_org,
            club=other_club,
            title="Org B Event",
            starts_at=timezone.now(),
            ends_at=timezone.now() + timedelta(hours=1),
            eligible_member_count_snapshot=5,
        )
        resp = self.admin_client.get("/api/v1/events/events/")
        self.assertEqual(resp.status_code, 200)
        titles = [e["title"] for e in resp.json()]
        self.assertIn("Org A Event", titles)
        self.assertNotIn("Org B Event", titles)

    def test_retrieve_event(self):
        event = self._create_event("Detail Event")
        resp = self.admin_client.get(f"/api/v1/events/events/{event.id}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["title"], "Detail Event")
        self.assertIn("starts_at", resp.json())
        self.assertIn("ends_at", resp.json())

    def test_full_update_event(self):
        event = self._create_event("Original Title")
        resp = self.admin_client.put(
            f"/api/v1/events/events/{event.id}/",
            {
                "club": self.club.id,
                "title": "Updated Title",
                "starts_at": event.starts_at.isoformat(),
                "ends_at": event.ends_at.isoformat(),
                "eligible_member_count_snapshot": 20,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["title"], "Updated Title")

    def test_delete_event(self):
        event = self._create_event("Delete Me")
        resp = self.admin_client.delete(f"/api/v1/events/events/{event.id}/")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(Event.objects.filter(id=event.id).exists())
        self.assertTrue(
            AuditLog.objects.filter(
                action="event.delete", resource_id=str(event.id)
            ).exists()
        )

    def test_delete_event_forbidden_for_member(self):
        event = self._create_event("Forbidden Delete")
        resp = self.member_client.delete(f"/api/v1/events/events/{event.id}/")
        self.assertEqual(resp.status_code, 403)

    def test_list_checkins(self):
        event = self._create_event("Checkin Event")
        EventRegistration.objects.create(
            organization=self.org, event=event, member=self.member
        )
        EventCheckIn.objects.create(
            organization=self.org, event=event, member=self.member
        )
        resp = self.admin_client.get("/api/v1/events/checkins/")
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()), 1)

    def test_list_checkins_filtered_by_event(self):
        event1 = self._create_event("CI Event 1")
        event2 = self._create_event("CI Event 2")
        EventCheckIn.objects.create(
            organization=self.org, event=event1, member=self.member
        )
        EventCheckIn.objects.create(
            organization=self.org, event=event2, member=self.admin
        )
        resp = self.admin_client.get(f"/api/v1/events/checkins/?event_id={event1.id}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)

    def test_list_reconciliations(self):
        event = self._create_event("Recon Event")
        EventAttendanceReconciliation.objects.create(
            organization=self.org,
            event=event,
            member=self.member,
            action="mark_checked_in",
            reason_code="late_arrival",
            reconciled_by=self.admin,
        )
        resp = self.admin_client.get("/api/v1/events/reconciliations/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)
        self.assertEqual(resp.json()[0]["action"], "mark_checked_in")

    def test_list_registrations_filtered_by_event(self):
        event = self._create_event("Reg Event")
        EventRegistration.objects.create(
            organization=self.org, event=event, member=self.member
        )
        resp = self.admin_client.get(f"/api/v1/events/registrations/?event_id={event.id}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)

    def test_list_resource_downloads(self):
        event = self._create_event("DL Event")
        EventResourceDownload.objects.create(
            organization=self.org,
            event=event,
            member=self.member,
            resource_key="slide-deck.pdf",
        )
        resp = self.admin_client.get("/api/v1/events/resource-downloads/")
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()), 1)
        self.assertEqual(resp.json()[0]["resource_key"], "slide-deck.pdf")
