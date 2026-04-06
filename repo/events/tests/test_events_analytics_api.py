from datetime import datetime, timedelta, timezone as _tz

UTC = _tz.utc

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


class EventsAnalyticsApiTests(TestCase):
    def setUp(self):
        self.org_a = Organization.objects.create(
            name="Org A", slug="org-a", timezone="UTC"
        )
        self.org_b = Organization.objects.create(
            name="Org B", slug="org-b", timezone="UTC"
        )

        self.manager_a = User.objects.create_user(
            username="events-manager-a", password="ValidPass123!"
        )
        self.manager_b = User.objects.create_user(
            username="events-manager-b", password="ValidPass123!"
        )
        self.member_a = User.objects.create_user(
            username="events-member-a", password="ValidPass123!"
        )
        self.member_b = User.objects.create_user(
            username="events-member-b", password="ValidPass123!"
        )
        self.group_leader = User.objects.create_user(
            username="events-leader-a", password="ValidPass123!"
        )

        self._assign_role(self.manager_a, self.org_a, RoleCode.CLUB_MANAGER.value)
        self._assign_role(self.manager_b, self.org_b, RoleCode.CLUB_MANAGER.value)
        self._assign_role(self.member_a, self.org_a, RoleCode.MEMBER.value)
        self._assign_role(self.member_b, self.org_a, RoleCode.MEMBER.value)
        self._assign_role(self.group_leader, self.org_a, RoleCode.GROUP_LEADER.value)

        self.manager_client = self._build_client(self.manager_a, self.org_a)
        self.member_client = self._build_client(self.member_a, self.org_a)
        self.group_leader_client = self._build_client(self.group_leader, self.org_a)

        self.club_a = Club.objects.create(
            organization=self.org_a, name="Events Club", code="EVT"
        )
        self.club_b = Club.objects.create(
            organization=self.org_b, name="Other Club", code="OTH"
        )

        Membership.objects.create(
            organization=self.org_a,
            member=self.member_a,
            club=self.club_a,
            status=MemberStatus.ACTIVE,
        )
        Membership.objects.create(
            organization=self.org_a,
            member=self.member_b,
            club=self.club_a,
            status=MemberStatus.ACTIVE,
        )

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

    def _create_event(self, *, submitted_snapshot=None):
        payload = {
            "club": self.club_a.id,
            "title": "Museum Tour",
            "starts_at": "2026-04-02T10:00:00Z",
            "ends_at": "2026-04-02T12:00:00Z",
        }
        if submitted_snapshot is not None:
            payload["eligible_member_count_snapshot"] = submitted_snapshot

        response = self.manager_client.post(
            "/api/v1/events/events/",
            payload,
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        return Event.objects.get(id=response.json()["id"])

    def test_event_workflow_happy_path_registration_checkin_reconcile_download(self):
        event = self._create_event(submitted_snapshot=2)

        reg_resp = self.member_client.post(
            "/api/v1/events/registrations/",
            {"event": event.id, "member": self.member_a.id},
            format="json",
        )
        self.assertEqual(reg_resp.status_code, 201)

        checkin_resp = self.manager_client.post(
            "/api/v1/events/checkins/",
            {"event": event.id, "member": self.member_a.id},
            format="json",
        )
        self.assertEqual(checkin_resp.status_code, 201)

        reconcile_remove = self.manager_client.post(
            "/api/v1/events/reconciliations/",
            {
                "event": event.id,
                "member": self.member_a.id,
                "action": "remove_check_in",
                "reason_code": "MANUAL_FIX",
                "notes": "Bad badge scan",
            },
            format="json",
        )
        self.assertEqual(reconcile_remove.status_code, 201)

        reconcile_mark = self.manager_client.post(
            "/api/v1/events/reconciliations/",
            {
                "event": event.id,
                "member": self.member_a.id,
                "action": "mark_checked_in",
                "reason_code": "MANUAL_FIX",
                "notes": "Confirmed attendance",
            },
            format="json",
        )
        self.assertEqual(reconcile_mark.status_code, 201)

        download_resp = self.member_client.post(
            "/api/v1/events/resource-downloads/",
            {
                "event": event.id,
                "member": self.member_a.id,
                "resource_key": "guide-v1.pdf",
            },
            format="json",
        )
        self.assertEqual(download_resp.status_code, 201)

        self.assertEqual(EventRegistration.objects.filter(event=event).count(), 1)
        self.assertEqual(EventCheckIn.objects.filter(event=event).count(), 1)
        self.assertEqual(
            EventAttendanceReconciliation.objects.filter(event=event).count(), 2
        )
        self.assertEqual(EventResourceDownload.objects.filter(event=event).count(), 1)

        audit_actions = set(
            AuditLog.objects.filter(organization=self.org_a).values_list(
                "action", flat=True
            )
        )
        self.assertIn("event.checkin.capture", audit_actions)
        self.assertIn("event.attendance.reconcile", audit_actions)
        self.assertIn("event.resource_download.track", audit_actions)

    def test_duplicate_and_invalid_registration_checkin_cases(self):
        event = self._create_event(submitted_snapshot=2)

        first_registration = self.member_client.post(
            "/api/v1/events/registrations/",
            {"event": event.id, "member": self.member_a.id},
            format="json",
        )
        self.assertEqual(first_registration.status_code, 201)

        duplicate_registration = self.member_client.post(
            "/api/v1/events/registrations/",
            {"event": event.id, "member": self.member_a.id},
            format="json",
        )
        self.assertEqual(duplicate_registration.status_code, 409)
        self.assertEqual(
            duplicate_registration.json()["error"]["code"],
            "event.registration_duplicate",
        )

        invalid_checkin = self.manager_client.post(
            "/api/v1/events/checkins/",
            {"event": event.id, "member": self.member_b.id},
            format="json",
        )
        self.assertEqual(invalid_checkin.status_code, 400)
        self.assertEqual(
            invalid_checkin.json()["error"]["code"],
            "event.checkin_requires_registration",
        )

        valid_checkin = self.manager_client.post(
            "/api/v1/events/checkins/",
            {"event": event.id, "member": self.member_a.id},
            format="json",
        )
        self.assertEqual(valid_checkin.status_code, 201)

        duplicate_checkin = self.manager_client.post(
            "/api/v1/events/checkins/",
            {"event": event.id, "member": self.member_a.id},
            format="json",
        )
        self.assertEqual(duplicate_checkin.status_code, 409)
        self.assertEqual(
            duplicate_checkin.json()["error"]["code"],
            "event.checkin_duplicate",
        )

    def test_tenant_isolation_for_event_surfaces(self):
        event_org_b = Event.objects.create(
            organization=self.org_b,
            club=self.club_b,
            title="Other Tenant Event",
            starts_at=timezone.now(),
            ends_at=timezone.now() + timedelta(hours=1),
            eligible_member_count_snapshot=1,
        )

        detail_resp = self.manager_client.get(
            f"/api/v1/events/events/{event_org_b.id}/"
        )
        self.assertEqual(detail_resp.status_code, 404)

        register_resp = self.manager_client.post(
            "/api/v1/events/registrations/",
            {"event": event_org_b.id, "member": self.member_a.id},
            format="json",
        )
        self.assertEqual(register_resp.status_code, 400)

    def test_analytics_summary_and_distribution_are_correct(self):
        member_c = User.objects.create_user(
            username="events-member-c", password="ValidPass123!"
        )
        member_d = User.objects.create_user(
            username="events-member-d", password="ValidPass123!"
        )
        self._assign_role(member_c, self.org_a, RoleCode.MEMBER.value)
        self._assign_role(member_d, self.org_a, RoleCode.MEMBER.value)
        Membership.objects.create(
            organization=self.org_a,
            member=member_c,
            club=self.club_a,
            status=MemberStatus.ACTIVE,
        )
        Membership.objects.create(
            organization=self.org_a,
            member=member_d,
            club=self.club_a,
            status=MemberStatus.ACTIVE,
        )

        event = self._create_event(submitted_snapshot=1)

        EventRegistration.objects.create(
            organization=self.org_a,
            event=event,
            member=self.member_a,
        )
        EventRegistration.objects.create(
            organization=self.org_a,
            event=event,
            member=self.member_b,
        )

        checkin = EventCheckIn.objects.create(
            organization=self.org_a,
            event=event,
            member=self.member_a,
        )
        EventCheckIn.objects.filter(id=checkin.id).update(
            checked_in_at=datetime(2026, 4, 2, 10, 7, tzinfo=UTC)
        )

        EventResourceDownload.objects.create(
            organization=self.org_a,
            event=event,
            member=self.member_b,
            resource_key="catalog.pdf",
        )

        summary_resp = self.manager_client.get(
            f"/api/v1/analytics/events/summary/?event_id={event.id}"
        )
        self.assertEqual(summary_resp.status_code, 200)
        summary = summary_resp.json()
        self.assertEqual(summary["eligible_members"], 4)
        self.assertEqual(summary["registrations"], 2)
        self.assertEqual(summary["checked_in"], 1)
        self.assertEqual(summary["conversion_rate"], 0.5)
        self.assertEqual(summary["attendance_rate"], 0.5)
        self.assertEqual(summary["active_members_last_30_days"], 2)

        distribution_resp = self.manager_client.get(
            f"/api/v1/analytics/events/checkin-distribution/?event_id={event.id}"
        )
        self.assertEqual(distribution_resp.status_code, 200)
        buckets = distribution_resp.json()["buckets"]
        bucket_map = {entry["bucket"]: entry["count"] for entry in buckets}
        self.assertEqual(bucket_map["10:00"], 1)
        self.assertEqual(sum(bucket_map.values()), 1)

    def test_group_leader_cannot_mutate_event_participation_records(self):
        event = self._create_event()

        registration_response = self.group_leader_client.post(
            "/api/v1/events/registrations/",
            {"event": event.id, "member": self.member_a.id},
            format="json",
        )
        self.assertEqual(registration_response.status_code, 403)

        checkin_response = self.group_leader_client.post(
            "/api/v1/events/checkins/",
            {"event": event.id, "member": self.member_a.id},
            format="json",
        )
        self.assertEqual(checkin_response.status_code, 403)

        download_response = self.group_leader_client.post(
            "/api/v1/events/resource-downloads/",
            {
                "event": event.id,
                "member": self.member_a.id,
                "resource_key": "leader.pdf",
            },
            format="json",
        )
        self.assertEqual(download_response.status_code, 403)

    def test_member_write_rules_enforce_self_only_and_no_member_checkin(self):
        event = self._create_event()

        register_other_response = self.member_client.post(
            "/api/v1/events/registrations/",
            {"event": event.id, "member": self.member_b.id},
            format="json",
        )
        self.assertEqual(register_other_response.status_code, 403)

        register_self_response = self.member_client.post(
            "/api/v1/events/registrations/",
            {"event": event.id, "member": self.member_a.id},
            format="json",
        )
        self.assertEqual(register_self_response.status_code, 201)

        member_checkin_response = self.member_client.post(
            "/api/v1/events/checkins/",
            {"event": event.id, "member": self.member_a.id},
            format="json",
        )
        self.assertEqual(member_checkin_response.status_code, 403)

        download_other_response = self.member_client.post(
            "/api/v1/events/resource-downloads/",
            {
                "event": event.id,
                "member": self.member_b.id,
                "resource_key": "other.pdf",
            },
            format="json",
        )
        self.assertEqual(download_other_response.status_code, 403)

    def test_event_snapshot_is_not_client_forgeable(self):
        event = self._create_event(submitted_snapshot=999)
        self.assertEqual(event.eligible_member_count_snapshot, 2)

        patch_response = self.manager_client.patch(
            f"/api/v1/events/events/{event.id}/",
            {"title": "Museum Tour Updated", "eligible_member_count_snapshot": 1234},
            format="json",
        )
        self.assertEqual(patch_response.status_code, 200)
        event.refresh_from_db()
        self.assertEqual(event.eligible_member_count_snapshot, 2)

    def test_mixed_non_manager_roles_are_self_scoped_for_list_views(self):
        mixed_user = User.objects.create_user(
            username="events-mixed-member", password="ValidPass123!"
        )
        self._assign_role(mixed_user, self.org_a, RoleCode.MEMBER.value)
        self._assign_role(mixed_user, self.org_a, RoleCode.GROUP_LEADER.value)
        mixed_client = self._build_client(mixed_user, self.org_a)

        Membership.objects.create(
            organization=self.org_a,
            member=mixed_user,
            club=self.club_a,
            status=MemberStatus.ACTIVE,
        )

        event = self._create_event()
        EventRegistration.objects.create(
            organization=self.org_a,
            event=event,
            member=mixed_user,
        )
        EventRegistration.objects.create(
            organization=self.org_a,
            event=event,
            member=self.member_b,
        )
        EventResourceDownload.objects.create(
            organization=self.org_a,
            event=event,
            member=mixed_user,
            resource_key="mixed.pdf",
        )
        EventResourceDownload.objects.create(
            organization=self.org_a,
            event=event,
            member=self.member_b,
            resource_key="other.pdf",
        )

        registrations_resp = mixed_client.get(
            f"/api/v1/events/registrations/?event_id={event.id}"
        )
        self.assertEqual(registrations_resp.status_code, 200)
        registrations = registrations_resp.json()
        self.assertEqual(len(registrations), 1)
        self.assertEqual(registrations[0]["member"], mixed_user.id)

        downloads_resp = mixed_client.get(
            f"/api/v1/events/resource-downloads/?event_id={event.id}"
        )
        self.assertEqual(downloads_resp.status_code, 200)
        downloads = downloads_resp.json()
        self.assertEqual(len(downloads), 1)
        self.assertEqual(downloads[0]["member"], mixed_user.id)
