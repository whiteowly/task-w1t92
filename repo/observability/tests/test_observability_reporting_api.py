from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from common.constants import RoleCode
from iam.models import AuthSession, Role, UserOrganizationRole
from observability.models import MetricsSnapshot
from observability.services import log_audit_event
from tenancy.models import Organization

User = get_user_model()


class _DummyRequest:
    request_id = "req-obsv-1"
    META = {"REMOTE_ADDR": "127.0.0.1"}


class ObservabilityReportingApiTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(
            name="Org A", slug="org-a", timezone="UTC"
        )
        self.admin = User.objects.create_user(
            username="obs-admin",
            password="ValidPass123!",
        )
        self.member = User.objects.create_user(
            username="obs-member",
            password="ValidPass123!",
        )

        self._assign_role(self.admin, self.org, RoleCode.ADMINISTRATOR.value)
        self._assign_role(self.member, self.org, RoleCode.MEMBER.value)

        self.admin_client = self._build_client(self.admin, self.org)
        self.member_client = self._build_client(self.member, self.org)

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

    def test_metrics_snapshot_generate_and_audit_log_reads(self):
        log_audit_event(
            action="observability.test.seed",
            organization=self.org,
            actor_user=self.admin,
            request=_DummyRequest(),
            resource_type="test_resource",
            resource_id="1",
            metadata={"token": "secret-token"},
        )

        generate_resp = self.admin_client.post(
            "/api/v1/observability/metrics-snapshots/generate/",
            {"metric_key": "ops.summary.v1"},
            format="json",
        )
        self.assertEqual(generate_resp.status_code, 201)
        self.assertEqual(generate_resp.json()["metric_key"], "ops.summary.v1")
        self.assertIn("clubs_total", generate_resp.json()["payload"])
        self.assertIn("pickup_points_total", generate_resp.json()["payload"])

        self.assertEqual(
            MetricsSnapshot.objects.filter(organization=self.org).count(), 1
        )

        metrics_list = self.admin_client.get("/api/v1/observability/metrics-snapshots/")
        self.assertEqual(metrics_list.status_code, 200)
        self.assertEqual(len(metrics_list.json()), 1)

        audit_list = self.admin_client.get(
            "/api/v1/observability/audit-logs/?action=observability.test.seed"
        )
        self.assertEqual(audit_list.status_code, 200)
        self.assertEqual(len(audit_list.json()), 1)
        self.assertEqual(audit_list.json()[0]["metadata"]["token"], "***REDACTED***")

        forbidden = self.member_client.get("/api/v1/observability/audit-logs/")
        self.assertEqual(forbidden.status_code, 403)

    def test_report_export_generates_local_file_and_metadata(self):
        log_audit_event(
            action="observability.test.export_seed",
            organization=self.org,
            actor_user=self.admin,
            request=_DummyRequest(),
            resource_type="report_seed",
            resource_id="2",
            metadata={"reason": "seed"},
        )

        export_resp = self.admin_client.post(
            "/api/v1/observability/report-exports/",
            {"report_type": "audit_log_csv"},
            format="json",
        )
        self.assertEqual(export_resp.status_code, 201)
        payload = export_resp.json()
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["report_type"], "audit_log_csv")

        report_path = Path(payload["file_path"]).resolve()
        export_root = Path(settings.EXPORT_ROOT).resolve()
        self.assertTrue(report_path.is_file())
        self.assertTrue(report_path.is_relative_to(export_root))
        self.assertEqual(
            report_path.parent, (export_root / "observability_reports").resolve()
        )

        metadata = payload["report_metadata"]
        self.assertGreater(metadata["file_size_bytes"], 0)
        self.assertGreaterEqual(metadata["row_count"], 1)
        self.assertEqual(len(metadata["sha256"]), 64)
