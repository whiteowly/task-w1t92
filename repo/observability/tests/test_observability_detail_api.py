from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from common.constants import RoleCode
from iam.models import AuthSession, Role, UserOrganizationRole
from observability.models import AuditLog, MetricsSnapshot, ReportExport
from observability.services import log_audit_event
from tenancy.models import Organization

User = get_user_model()


class _DummyRequest:
    request_id = "req-detail-1"
    META = {"REMOTE_ADDR": "127.0.0.1"}


class ObservabilityDetailApiTests(TestCase):
    """Tests for audit-log detail, metrics detail, report-exports list."""

    def setUp(self):
        self.org = Organization.objects.create(
            name="Obs Detail Org", slug="obs-detail-org", timezone="UTC"
        )
        self.other_org = Organization.objects.create(
            name="Obs Other Org", slug="obs-other-org", timezone="UTC"
        )
        self.password = "ValidPass123!"

        self.admin = User.objects.create_user(
            username="od-admin", password=self.password, full_name="Admin"
        )
        self.member = User.objects.create_user(
            username="od-member", password=self.password, full_name="Member"
        )
        self.other_admin = User.objects.create_user(
            username="od-other-admin", password=self.password, full_name="Other Admin"
        )

        self._assign_role(self.admin, self.org, RoleCode.ADMINISTRATOR.value)
        self._assign_role(self.member, self.org, RoleCode.MEMBER.value)
        self._assign_role(self.other_admin, self.other_org, RoleCode.ADMINISTRATOR.value)

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

    # ---- Audit Log Detail ----

    def test_retrieve_audit_log(self):
        log_audit_event(
            action="test.detail",
            organization=self.org,
            actor_user=self.admin,
            request=_DummyRequest(),
            resource_type="test",
            resource_id="42",
            metadata={"key": "value", "password": "secret123"},
        )
        audit_log = AuditLog.objects.filter(
            organization=self.org, action="test.detail"
        ).first()
        resp = self.admin_client.get(f"/api/v1/observability/audit-logs/{audit_log.id}/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["action"], "test.detail")
        self.assertEqual(data["resource_type"], "test")
        self.assertEqual(data["resource_id"], "42")
        # Sensitive fields should be redacted
        self.assertEqual(data["metadata"]["password"], "***REDACTED***")

    def test_audit_log_detail_forbidden_for_member(self):
        log_audit_event(
            action="test.forbidden",
            organization=self.org,
            actor_user=self.admin,
            request=_DummyRequest(),
            resource_type="test",
            resource_id="1",
        )
        audit_log = AuditLog.objects.filter(
            organization=self.org, action="test.forbidden"
        ).first()
        resp = self.member_client.get(f"/api/v1/observability/audit-logs/{audit_log.id}/")
        self.assertEqual(resp.status_code, 403)

    def test_audit_log_detail_cross_tenant_isolation(self):
        log_audit_event(
            action="test.iso",
            organization=self.org,
            actor_user=self.admin,
            request=_DummyRequest(),
            resource_type="test",
            resource_id="3",
        )
        audit_log = AuditLog.objects.filter(
            organization=self.org, action="test.iso"
        ).first()
        resp = self.other_admin_client.get(
            f"/api/v1/observability/audit-logs/{audit_log.id}/"
        )
        self.assertEqual(resp.status_code, 404)

    def test_audit_log_list_with_filters(self):
        log_audit_event(
            action="user.create",
            organization=self.org,
            actor_user=self.admin,
            request=_DummyRequest(),
            resource_type="user",
            resource_id="10",
            result="success",
        )
        log_audit_event(
            action="user.delete",
            organization=self.org,
            actor_user=self.admin,
            request=_DummyRequest(),
            resource_type="user",
            resource_id="11",
            result="failure",
        )
        resp = self.admin_client.get(
            "/api/v1/observability/audit-logs/?action=user.create"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)
        self.assertEqual(resp.json()[0]["action"], "user.create")

        resp = self.admin_client.get(
            "/api/v1/observability/audit-logs/?result=failure"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)
        self.assertEqual(resp.json()[0]["action"], "user.delete")

    # ---- Metrics Snapshot Detail ----

    def test_retrieve_metrics_snapshot(self):
        snapshot = MetricsSnapshot.objects.create(
            organization=self.org,
            metric_key="ops.summary.v1",
            payload={"clubs_total": 5, "events_total": 10},
            captured_at=timezone.now(),
        )
        resp = self.admin_client.get(
            f"/api/v1/observability/metrics-snapshots/{snapshot.id}/"
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["metric_key"], "ops.summary.v1")
        self.assertEqual(data["payload"]["clubs_total"], 5)

    def test_metrics_snapshot_detail_cross_tenant_isolation(self):
        snapshot = MetricsSnapshot.objects.create(
            organization=self.org,
            metric_key="ops.summary.v1",
            payload={},
            captured_at=timezone.now(),
        )
        resp = self.other_admin_client.get(
            f"/api/v1/observability/metrics-snapshots/{snapshot.id}/"
        )
        self.assertEqual(resp.status_code, 404)

    # ---- Report Exports List ----

    def test_list_report_exports(self):
        ReportExport.objects.create(
            organization=self.org,
            report_type="audit_log_csv",
            status="completed",
            file_path="/tmp/test_export.csv",
            generated_at=timezone.now(),
            requested_by_user_id=self.admin.id,
            report_metadata={"row_count": 10, "file_size_bytes": 1024, "sha256": "a" * 64},
        )
        resp = self.admin_client.get("/api/v1/observability/report-exports/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)
        self.assertEqual(resp.json()[0]["report_type"], "audit_log_csv")
        self.assertEqual(resp.json()[0]["status"], "completed")

    def test_list_report_exports_tenant_isolated(self):
        ReportExport.objects.create(
            organization=self.org,
            report_type="audit_log_csv",
            status="completed",
            file_path="/tmp/org_a.csv",
            generated_at=timezone.now(),
        )
        ReportExport.objects.create(
            organization=self.other_org,
            report_type="audit_log_csv",
            status="completed",
            file_path="/tmp/org_b.csv",
            generated_at=timezone.now(),
        )
        resp = self.other_admin_client.get("/api/v1/observability/report-exports/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)
