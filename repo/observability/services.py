from __future__ import annotations

import csv
import hashlib
import json
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from clubs.models import Club, MemberStatus, Membership
from common.exceptions import DomainAPIException
from content.models import AssetState, ContentAsset, ContentDownloadRequestLog
from events.models import Event, EventCheckIn, EventRegistration
from logistics.models import GroupLeaderOnboarding, OnboardingStatus, PickupPoint
from observability.models import AuditLog
from observability.models import MetricsSnapshot, ReportExport


SENSITIVE_KEYS = {
    "password",
    "new_password",
    "old_password",
    "session_key",
    "token",
    "redeem_code",
    "address_line1",
    "address_line2",
    "city",
    "state",
    "postal_code",
    "country",
    "contact_phone",
    "config_payload",
    "credit_card",
    "card_number",
    "cvv",
    "authorization",
    "api_key",
    "private_key",
    "access_token",
    "refresh_token",
}

REDACTION_TOKEN = "***REDACTED***"

METRICS_KEY_OPS_SUMMARY = "ops.summary.v1"
REPORT_TYPE_AUDIT_LOG_CSV = "audit_log_csv"
REPORT_TYPE_METRICS_SNAPSHOT_JSON = "metrics_snapshot_json"


STRICT_SENSITIVE_SUFFIXES = {
    "password",
    "newpassword",
    "oldpassword",
    "passwd",
    "passwdhash",
    "token",
    "accesstoken",
    "refreshtoken",
    "sessionkey",
    "redeemcode",
    "secret",
    "secretkey",
    "secretvalue",
    "apikey",
    "privatekey",
    "privatekeypem",
    "credential",
    "credentialhash",
    "authorization",
    "ssn",
    "phone",
    "address",
    "addressline1",
    "addressline2",
    "postalcode",
    "country",
    "city",
    "state",
    "contactphone",
    "creditcard",
    "cardnumber",
    "cvv",
    "accountnumber",
}

OPAQUE_SENSITIVE_KEYS = {
    "configpayload",
}

NORMALIZED_SENSITIVE_KEYS = {
    "".join(ch for ch in key.lower() if ch.isalnum()) for key in SENSITIVE_KEYS
}


def _normalize_path_segment(segment: str) -> str:
    return "".join(ch for ch in segment.lower() if ch.isalnum())


def _should_redact_path(path: tuple[str, ...]) -> bool:
    if not path:
        return False
    leaf = path[-1]
    if leaf in NORMALIZED_SENSITIVE_KEYS:
        return True
    if leaf in OPAQUE_SENSITIVE_KEYS:
        return True
    return any(leaf.endswith(suffix) for suffix in STRICT_SENSITIVE_SUFFIXES)


def _redact_value(value, *, path: tuple[str, ...] = ()):
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            child_path = (*path, _normalize_path_segment(key))
            if _should_redact_path(child_path):
                redacted[key] = REDACTION_TOKEN
            else:
                redacted[key] = _redact_value(item, path=child_path)
        return redacted
    if isinstance(value, list):
        return [_redact_value(item, path=(*path, "[]")) for item in value]
    return value


def _redact(payload: dict | None) -> dict:
    payload = payload or {}
    return _redact_value(payload)


def log_audit_event(
    *,
    action: str,
    request,
    organization=None,
    actor_user=None,
    result: str = "success",
    resource_type: str = "",
    resource_id: str = "",
    metadata: dict | None = None,
    before_data: dict | None = None,
    after_data: dict | None = None,
) -> AuditLog:
    return AuditLog.objects.create(
        organization=organization,
        actor_user=actor_user,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        result=result,
        request_id=getattr(request, "request_id", ""),
        ip_address=request.META.get("REMOTE_ADDR"),
        metadata=_redact(metadata),
        before_data=_redact(before_data),
        after_data=_redact(after_data),
    )


def build_operational_metrics_payload(*, organization) -> dict:
    now = timezone.now()
    one_day_ago = now - timedelta(days=1)

    return {
        "clubs_total": Club.objects.filter(organization=organization).count(),
        "memberships_active": Membership.objects.filter(
            organization=organization,
            status=MemberStatus.ACTIVE,
        ).count(),
        "events_total": Event.objects.filter(organization=organization).count(),
        "events_upcoming": Event.objects.filter(
            organization=organization,
            starts_at__gte=now,
        ).count(),
        "event_registrations_total": EventRegistration.objects.filter(
            organization=organization
        ).count(),
        "event_checkins_total": EventCheckIn.objects.filter(
            organization=organization
        ).count(),
        "pickup_points_total": PickupPoint.objects.filter(
            organization=organization
        ).count(),
        "onboardings_pending": GroupLeaderOnboarding.objects.filter(
            organization=organization,
            status=OnboardingStatus.SUBMITTED,
        ).count(),
        "content_assets_published": ContentAsset.objects.filter(
            organization=organization,
            state=AssetState.PUBLISHED,
        ).count(),
        "content_download_requests_24h": ContentDownloadRequestLog.objects.filter(
            organization=organization,
            requested_at__gte=one_day_ago,
        ).count(),
    }


def create_metrics_snapshot(*, organization, actor_user, request, metric_key: str):
    metric_key = (metric_key or "").strip() or METRICS_KEY_OPS_SUMMARY
    if metric_key != METRICS_KEY_OPS_SUMMARY:
        raise DomainAPIException(
            code="observability.metrics.unsupported_key",
            message="Unsupported metric_key.",
        )

    payload = build_operational_metrics_payload(organization=organization)
    snapshot = MetricsSnapshot.objects.create(
        organization=organization,
        metric_key=metric_key,
        payload=payload,
        captured_at=timezone.now(),
    )
    log_audit_event(
        action="observability.metrics_snapshot.generate",
        organization=organization,
        actor_user=actor_user,
        request=request,
        resource_type="metrics_snapshot",
        resource_id=str(snapshot.id),
        metadata={"metric_key": metric_key},
    )
    return snapshot


def _report_exports_root() -> Path:
    export_root = Path(settings.EXPORT_ROOT).resolve()
    reports_root = (export_root / "observability_reports").resolve()
    reports_root.mkdir(parents=True, exist_ok=True)
    return reports_root


def _build_report_file_path(
    *, organization_id: int, report_type: str, extension: str
) -> Path:
    reports_root = _report_exports_root()
    filename = f"org{organization_id}_{report_type}_{int(timezone.now().timestamp())}.{extension}"
    candidate = (reports_root / filename).resolve()
    if not str(candidate).startswith(str(reports_root)):
        raise DomainAPIException(
            code="observability.report.invalid_path",
            message="Report output path is outside allowed export root.",
            status_code=500,
        )
    return candidate


def _file_metadata(path: Path) -> dict:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "file_size_bytes": path.stat().st_size,
        "sha256": digest,
    }


def _generate_audit_log_csv_report(*, organization, output_path: Path) -> dict:
    logs = AuditLog.objects.filter(organization=organization).order_by(
        "created_at", "id"
    )
    with open(output_path, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=[
                "id",
                "created_at",
                "action",
                "resource_type",
                "resource_id",
                "result",
                "request_id",
                "actor_user_id",
            ],
        )
        writer.writeheader()
        for log in logs:
            writer.writerow(
                {
                    "id": log.id,
                    "created_at": log.created_at.isoformat(),
                    "action": log.action,
                    "resource_type": log.resource_type,
                    "resource_id": log.resource_id,
                    "result": log.result,
                    "request_id": log.request_id,
                    "actor_user_id": log.actor_user_id,
                }
            )
    metadata = _file_metadata(output_path)
    metadata["row_count"] = logs.count()
    return metadata


def _generate_metrics_snapshot_json_report(*, organization, output_path: Path) -> dict:
    snapshot = (
        MetricsSnapshot.objects.filter(organization=organization)
        .order_by("-captured_at", "-id")
        .first()
    )
    if snapshot is None:
        payload = build_operational_metrics_payload(organization=organization)
        snapshot = MetricsSnapshot.objects.create(
            organization=organization,
            metric_key=METRICS_KEY_OPS_SUMMARY,
            payload=payload,
            captured_at=timezone.now(),
        )

    report_body = {
        "snapshot_id": snapshot.id,
        "metric_key": snapshot.metric_key,
        "captured_at": snapshot.captured_at.isoformat(),
        "payload": snapshot.payload,
    }
    with open(output_path, "w", encoding="utf-8") as json_file:
        json.dump(report_body, json_file, indent=2, sort_keys=True)

    metadata = _file_metadata(output_path)
    metadata["snapshot_id"] = snapshot.id
    return metadata


@transaction.atomic
def create_report_export(
    *, organization, actor_user, request, report_type: str
) -> ReportExport:
    report_type = (report_type or "").strip()
    if report_type not in {
        REPORT_TYPE_AUDIT_LOG_CSV,
        REPORT_TYPE_METRICS_SNAPSHOT_JSON,
    }:
        raise DomainAPIException(
            code="observability.report.unsupported_type",
            message="Unsupported report_type.",
        )

    export = ReportExport.objects.create(
        organization=organization,
        report_type=report_type,
        status="pending",
        requested_by_user_id=getattr(actor_user, "id", None),
    )

    if report_type == REPORT_TYPE_AUDIT_LOG_CSV:
        output_path = _build_report_file_path(
            organization_id=organization.id,
            report_type=report_type,
            extension="csv",
        )
        metadata = _generate_audit_log_csv_report(
            organization=organization,
            output_path=output_path,
        )
    else:
        output_path = _build_report_file_path(
            organization_id=organization.id,
            report_type=report_type,
            extension="json",
        )
        metadata = _generate_metrics_snapshot_json_report(
            organization=organization,
            output_path=output_path,
        )

    export.status = "completed"
    export.file_path = str(output_path)
    export.generated_at = timezone.now()
    export.report_metadata = metadata
    export.save(
        update_fields=[
            "status",
            "file_path",
            "generated_at",
            "report_metadata",
            "updated_at",
        ]
    )

    log_audit_event(
        action="observability.report_export.create",
        organization=organization,
        actor_user=actor_user,
        request=request,
        resource_type="report_export",
        resource_id=str(export.id),
        metadata={
            "report_type": report_type,
            "file_path": str(output_path),
            "file_size_bytes": metadata.get("file_size_bytes"),
        },
    )
    return export
