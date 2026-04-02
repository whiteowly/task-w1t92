from __future__ import annotations

from django.db import transaction
from rest_framework import status

from clubs.models import MemberStatus, Membership
from common.constants import RoleCode
from common.exceptions import DomainAPIException
from events.models import (
    Event,
    EventAttendanceReconciliation,
    EventCheckIn,
    EventRegistration,
    EventResourceDownload,
    ReconciliationAction,
)
from observability.services import log_audit_event


MANAGER_ROLE_CODES = {RoleCode.ADMINISTRATOR.value, RoleCode.CLUB_MANAGER.value}
MEMBER_ROLE_CODE = RoleCode.MEMBER.value


def ensure_member_in_organization(*, member, organization):
    role_qs = member.organization_roles.filter(
        organization=organization, is_active=True
    )
    if not role_qs.exists():
        raise DomainAPIException(
            code="event.member_outside_organization",
            message="Member does not belong to active organization.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


def ensure_member_eligible(*, event: Event, member):
    eligible = Membership.objects.filter(
        organization=event.organization,
        member=member,
        club=event.club,
        status=MemberStatus.ACTIVE,
    ).exists()
    if not eligible:
        raise DomainAPIException(
            code="event.member_not_eligible",
            message="Member is not eligible for this event.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


def _assert_member_self_write(*, request, member):
    if request.user.id != member.id:
        raise DomainAPIException(
            code="event.member_write_forbidden",
            message="Members can only operate on their own event records.",
            status_code=status.HTTP_403_FORBIDDEN,
        )


def _get_role_codes(request) -> set[str]:
    return set(getattr(request, "role_codes", []))


def assert_manager_or_member_self(*, request, member):
    role_codes = _get_role_codes(request)
    if role_codes & MANAGER_ROLE_CODES:
        return
    if MEMBER_ROLE_CODE in role_codes:
        _assert_member_self_write(request=request, member=member)
        return
    raise DomainAPIException(
        code="event.write_forbidden",
        message="Insufficient role for event participation write action.",
        status_code=status.HTTP_403_FORBIDDEN,
    )


def assert_manager_only(*, request):
    role_codes = _get_role_codes(request)
    if role_codes & MANAGER_ROLE_CODES:
        return
    raise DomainAPIException(
        code="event.write_forbidden",
        message="Only administrators and club managers can perform this action.",
        status_code=status.HTTP_403_FORBIDDEN,
    )


@transaction.atomic
def register_for_event(*, event: Event, member, request) -> EventRegistration:
    ensure_member_in_organization(member=member, organization=event.organization)
    assert_manager_or_member_self(request=request, member=member)
    ensure_member_eligible(event=event, member=member)

    if EventRegistration.objects.filter(
        organization=event.organization,
        event=event,
        member=member,
    ).exists():
        raise DomainAPIException(
            code="event.registration_duplicate",
            message="Member is already registered for this event.",
            status_code=status.HTTP_409_CONFLICT,
        )

    registration = EventRegistration.objects.create(
        organization=event.organization,
        event=event,
        member=member,
    )

    log_audit_event(
        action="event.registration.create",
        organization=event.organization,
        actor_user=request.user,
        request=request,
        resource_type="event_registration",
        resource_id=str(registration.id),
        metadata={"event_id": event.id, "member_id": member.id},
    )
    return registration


@transaction.atomic
def capture_checkin(*, event: Event, member, request) -> EventCheckIn:
    ensure_member_in_organization(member=member, organization=event.organization)
    assert_manager_only(request=request)

    if not EventRegistration.objects.filter(
        organization=event.organization,
        event=event,
        member=member,
    ).exists():
        raise DomainAPIException(
            code="event.checkin_requires_registration",
            message="Member must be registered before check-in.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if EventCheckIn.objects.filter(
        organization=event.organization,
        event=event,
        member=member,
    ).exists():
        raise DomainAPIException(
            code="event.checkin_duplicate",
            message="Member has already checked in.",
            status_code=status.HTTP_409_CONFLICT,
        )

    checkin = EventCheckIn.objects.create(
        organization=event.organization,
        event=event,
        member=member,
    )

    log_audit_event(
        action="event.checkin.capture",
        organization=event.organization,
        actor_user=request.user,
        request=request,
        resource_type="event_checkin",
        resource_id=str(checkin.id),
        metadata={"event_id": event.id, "member_id": member.id},
    )
    return checkin


@transaction.atomic
def reconcile_attendance(
    *,
    event: Event,
    member,
    action: str,
    reason_code: str,
    notes: str,
    request,
) -> EventAttendanceReconciliation:
    ensure_member_in_organization(member=member, organization=event.organization)

    checkin_qs = EventCheckIn.objects.filter(
        organization=event.organization,
        event=event,
        member=member,
    )

    if action == ReconciliationAction.MARK_CHECKED_IN:
        if checkin_qs.exists():
            raise DomainAPIException(
                code="event.reconciliation_already_checked_in",
                message="Member is already checked in.",
                status_code=status.HTTP_409_CONFLICT,
            )
        EventCheckIn.objects.create(
            organization=event.organization,
            event=event,
            member=member,
        )
    elif action == ReconciliationAction.REMOVE_CHECK_IN:
        if not checkin_qs.exists():
            raise DomainAPIException(
                code="event.reconciliation_no_checkin",
                message="Cannot remove check-in because none exists.",
                status_code=status.HTTP_409_CONFLICT,
            )
        checkin_qs.delete()
    else:
        raise DomainAPIException(
            code="event.reconciliation_invalid_action",
            message="Invalid reconciliation action.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    reconciliation = EventAttendanceReconciliation.objects.create(
        organization=event.organization,
        event=event,
        member=member,
        action=action,
        reason_code=reason_code,
        notes=notes,
        reconciled_by=request.user,
    )

    log_audit_event(
        action="event.attendance.reconcile",
        organization=event.organization,
        actor_user=request.user,
        request=request,
        resource_type="event_reconciliation",
        resource_id=str(reconciliation.id),
        metadata={
            "event_id": event.id,
            "member_id": member.id,
            "action": action,
            "reason_code": reason_code,
        },
    )
    return reconciliation


@transaction.atomic
def track_resource_download(
    *,
    event: Event,
    member,
    resource_key: str,
    request,
) -> EventResourceDownload:
    ensure_member_in_organization(member=member, organization=event.organization)
    assert_manager_or_member_self(request=request, member=member)

    if not EventRegistration.objects.filter(
        organization=event.organization,
        event=event,
        member=member,
    ).exists():
        raise DomainAPIException(
            code="event.download_requires_registration",
            message="Member must be registered before event resource download tracking.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    download = EventResourceDownload.objects.create(
        organization=event.organization,
        event=event,
        member=member,
        resource_key=resource_key,
    )

    log_audit_event(
        action="event.resource_download.track",
        organization=event.organization,
        actor_user=request.user,
        request=request,
        resource_type="event_resource_download",
        resource_id=str(download.id),
        metadata={
            "event_id": event.id,
            "member_id": member.id,
            "resource_key": resource_key,
        },
    )
    return download
