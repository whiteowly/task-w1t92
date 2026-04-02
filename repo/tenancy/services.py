from __future__ import annotations

from copy import deepcopy
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from common.exceptions import DomainAPIException
from observability.services import log_audit_event
from tenancy.models import TenantConfigVersion


def _deep_merge(base: dict, patch: dict) -> dict:
    merged = deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _compute_top_level_diff(before: dict, after: dict) -> dict:
    keys = sorted(set(before.keys()) | set(after.keys()))
    diff = {}
    for key in keys:
        old = before.get(key)
        new = after.get(key)
        if old != new:
            diff[key] = {"from": old, "to": new}
    return diff


def get_latest_config_version(*, organization):
    return (
        TenantConfigVersion.objects.filter(organization=organization)
        .order_by("-version_number")
        .first()
    )


@transaction.atomic
def create_config_version(
    *,
    organization,
    actor,
    config_payload: dict,
    change_summary: str,
    change_diff: dict,
    request,
    audit_action: str,
):
    latest = get_latest_config_version(organization=organization)
    next_version = 1 if latest is None else latest.version_number + 1
    rollback_deadline = timezone.now() + timedelta(days=30)

    version = TenantConfigVersion.objects.create(
        organization=organization,
        version_number=next_version,
        config_payload=config_payload,
        changed_by_user_id=actor.id if actor else None,
        change_summary=change_summary,
        change_diff=change_diff,
        rollback_deadline_at=rollback_deadline,
    )

    log_audit_event(
        action=audit_action,
        organization=organization,
        actor_user=actor,
        request=request,
        resource_type="tenant_config_version",
        resource_id=str(version.id),
        metadata={
            "version_number": version.version_number,
            "change_summary": change_summary,
        },
        after_data={"config_payload": config_payload},
    )
    return version


def update_tenant_config(
    *, organization, actor, config_patch: dict, change_summary: str, request
):
    latest = get_latest_config_version(organization=organization)
    current_payload = latest.config_payload if latest else {}
    updated_payload = _deep_merge(current_payload, config_patch)
    diff = _compute_top_level_diff(current_payload, updated_payload)
    if not diff:
        raise DomainAPIException(
            code="tenant_config.no_changes",
            message="Config patch does not introduce any changes.",
        )

    return create_config_version(
        organization=organization,
        actor=actor,
        config_payload=updated_payload,
        change_summary=change_summary or "Configuration updated",
        change_diff=diff,
        request=request,
        audit_action="tenant_config.update",
    )


def rollback_tenant_config(
    *, organization, source_version, actor, change_summary: str, request
):
    if source_version.organization_id != organization.id:
        raise DomainAPIException(
            code="tenant_config.version_not_found",
            message="Config version is outside active organization.",
            status_code=404,
        )

    now = timezone.now()
    if source_version.rollback_deadline_at < now:
        raise DomainAPIException(
            code="tenant_config.rollback_window_expired",
            message="Rollback window expired for this config version.",
        )

    return create_config_version(
        organization=organization,
        actor=actor,
        config_payload=deepcopy(source_version.config_payload),
        change_summary=change_summary
        or f"Rollback from version {source_version.version_number}",
        change_diff={"rollback_from_version": source_version.version_number},
        request=request,
        audit_action="tenant_config.rollback",
    )
