from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
from rest_framework import status

from clubs.models import (
    Club,
    Department,
    MemberStatus,
    Membership,
    MembershipStatusLog,
    MembershipTransferLog,
)
from common.exceptions import DomainAPIException
from observability.services import log_audit_event


ALLOWED_TRANSITIONS = {
    MemberStatus.PENDING: {
        MemberStatus.ACTIVE,
        MemberStatus.SUSPENDED,
        MemberStatus.BANNED,
    },
    MemberStatus.ACTIVE: {
        MemberStatus.SUSPENDED,
        MemberStatus.ALUMNI,
        MemberStatus.BANNED,
    },
    MemberStatus.SUSPENDED: {
        MemberStatus.ACTIVE,
        MemberStatus.ALUMNI,
        MemberStatus.BANNED,
    },
    MemberStatus.ALUMNI: {MemberStatus.ACTIVE},
    MemberStatus.BANNED: set(),
}


@dataclass
class JoinResult:
    membership: Membership
    created: bool


def _raise_invalid_transition(from_status: str, to_status: str):
    raise DomainAPIException(
        code="membership.invalid_transition",
        message=f"Cannot transition membership from '{from_status}' to '{to_status}'.",
        details=[
            {
                "field": "to_status",
                "code": "invalid_transition",
                "message": f"Transition from {from_status} to {to_status} is not allowed.",
            }
        ],
    )


def _validate_transition(from_status: str, to_status: str):
    if from_status == to_status:
        raise DomainAPIException(
            code="membership.noop_transition",
            message="Requested status is already the current status.",
            details=[
                {
                    "field": "to_status",
                    "code": "noop",
                    "message": "Provide a different target status.",
                }
            ],
        )

    if to_status not in ALLOWED_TRANSITIONS.get(from_status, set()):
        _raise_invalid_transition(from_status=from_status, to_status=to_status)


@transaction.atomic
def transition_membership_status(
    *,
    membership: Membership,
    to_status: str,
    reason_code: str,
    effective_date,
    actor,
    request,
    action_name: str,
) -> Membership:
    membership = (
        Membership.objects.select_for_update()
        .select_related("club", "department")
        .get(pk=membership.pk)
    )

    from_status = membership.status
    _validate_transition(from_status=from_status, to_status=to_status)

    membership.status = to_status
    membership.status_effective_date = effective_date
    membership.save(update_fields=["status", "status_effective_date", "updated_at"])

    MembershipStatusLog.objects.create(
        organization=membership.organization,
        membership=membership,
        from_status=from_status,
        to_status=to_status,
        reason_code=reason_code,
        effective_date=effective_date,
        changed_by=actor,
    )

    log_audit_event(
        action=action_name,
        organization=membership.organization,
        actor_user=actor,
        request=request,
        resource_type="membership",
        resource_id=str(membership.id),
        metadata={
            "membership_id": membership.id,
            "reason_code": reason_code,
            "effective_date": str(effective_date),
        },
        before_data={"status": from_status},
        after_data={"status": to_status},
    )
    return membership


@transaction.atomic
def join_membership(
    *,
    organization,
    member,
    club: Club,
    department: Department | None,
    reason_code: str,
    effective_date,
    actor,
    request,
) -> JoinResult:
    if not member.is_active:
        raise DomainAPIException(
            code="membership.member_inactive",
            message="Member account must be active.",
        )

    if not member.organization_roles.filter(
        organization=organization,
        is_active=True,
    ).exists():
        raise DomainAPIException(
            code="membership.member_outside_organization",
            message="Member does not belong to active organization.",
        )

    membership, created = Membership.objects.select_for_update().get_or_create(
        organization=organization,
        member=member,
        club=club,
        defaults={
            "department": department,
            "status": MemberStatus.PENDING,
        },
    )

    if department is not None and membership.department_id != department.id:
        membership.department = department
        membership.save(update_fields=["department", "updated_at"])

    membership = transition_membership_status(
        membership=membership,
        to_status=MemberStatus.ACTIVE,
        reason_code=reason_code,
        effective_date=effective_date,
        actor=actor,
        request=request,
        action_name="membership.join",
    )

    return JoinResult(membership=membership, created=created)


def leave_membership(
    *,
    membership: Membership,
    reason_code: str,
    effective_date,
    actor,
    request,
) -> Membership:
    return transition_membership_status(
        membership=membership,
        to_status=MemberStatus.ALUMNI,
        reason_code=reason_code,
        effective_date=effective_date,
        actor=actor,
        request=request,
        action_name="membership.leave",
    )


@transaction.atomic
def transfer_membership(
    *,
    membership: Membership,
    to_club: Club,
    to_department: Department | None,
    reason_code: str,
    effective_date,
    actor,
    request,
) -> Membership:
    membership = (
        Membership.objects.select_for_update()
        .select_related("club", "department")
        .get(pk=membership.pk)
    )

    if membership.status == MemberStatus.BANNED:
        raise DomainAPIException(
            code="membership.transfer_blocked",
            message="Banned memberships cannot be transferred.",
        )

    if membership.club_id == to_club.id and membership.department_id == (
        to_department.id if to_department else None
    ):
        raise DomainAPIException(
            code="membership.transfer_noop",
            message="Transfer target matches current club and department.",
        )

    duplicate_exists = Membership.objects.filter(
        organization=membership.organization,
        member=membership.member,
        club=to_club,
    ).exclude(pk=membership.pk)
    if duplicate_exists.exists():
        raise DomainAPIException(
            code="membership.transfer_duplicate",
            message="Member already has a membership in the target club.",
            status_code=status.HTTP_409_CONFLICT,
        )

    from_club = membership.club
    from_department = membership.department

    membership.club = to_club
    membership.department = to_department
    membership.save(update_fields=["club", "department", "updated_at"])

    MembershipTransferLog.objects.create(
        organization=membership.organization,
        membership=membership,
        from_club=from_club,
        from_department=from_department,
        to_club=to_club,
        to_department=to_department,
        reason_code=reason_code,
        effective_date=effective_date,
        changed_by=actor,
    )

    log_audit_event(
        action="membership.transfer",
        organization=membership.organization,
        actor_user=actor,
        request=request,
        resource_type="membership",
        resource_id=str(membership.id),
        metadata={
            "membership_id": membership.id,
            "reason_code": reason_code,
            "effective_date": str(effective_date),
        },
        before_data={
            "club_id": from_club.id,
            "department_id": from_department.id if from_department else None,
        },
        after_data={
            "club_id": to_club.id,
            "department_id": to_department.id if to_department else None,
        },
    )

    return membership


def change_membership_status(
    *,
    membership: Membership,
    to_status: str,
    reason_code: str,
    effective_date,
    actor,
    request,
) -> Membership:
    return transition_membership_status(
        membership=membership,
        to_status=to_status,
        reason_code=reason_code,
        effective_date=effective_date,
        actor=actor,
        request=request,
        action_name="membership.status_change",
    )
