from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from common.constants import RoleCode
from common.exceptions import DomainAPIException
from logistics.models import GroupLeaderOnboarding, OnboardingStatus
from observability.services import log_audit_event


@transaction.atomic
def submit_onboarding_application(
    *,
    organization,
    applicant,
    pickup_point,
    document_title: str,
    document_type: str,
    document_reference: str,
    document_metadata: dict,
    request,
) -> GroupLeaderOnboarding:
    application = GroupLeaderOnboarding.objects.create(
        organization=organization,
        applicant=applicant,
        pickup_point=pickup_point,
        status=OnboardingStatus.SUBMITTED,
        document_title=document_title,
        document_type=document_type,
        document_reference=document_reference,
        document_metadata=document_metadata,
    )

    log_audit_event(
        action="leader_onboarding.submit",
        organization=organization,
        actor_user=applicant,
        request=request,
        resource_type="leader_onboarding",
        resource_id=str(application.id),
        metadata={
            "pickup_point_id": pickup_point.id if pickup_point else None,
            "document_type": document_type,
        },
    )
    return application


@transaction.atomic
def review_onboarding_application(
    *,
    application: GroupLeaderOnboarding,
    decision: str,
    review_notes: str,
    reviewer,
    request,
) -> GroupLeaderOnboarding:
    application = GroupLeaderOnboarding.objects.select_for_update().get(
        pk=application.pk
    )

    if application.status != OnboardingStatus.SUBMITTED:
        raise DomainAPIException(
            code="leader_onboarding.invalid_transition",
            message="Only submitted applications can be reviewed.",
            details=[
                {
                    "field": "status",
                    "code": "invalid_transition",
                    "message": f"Current status is '{application.status}'.",
                }
            ],
        )

    if decision not in {OnboardingStatus.APPROVED, OnboardingStatus.REJECTED}:
        raise DomainAPIException(
            code="leader_onboarding.invalid_decision",
            message="Review decision must be 'approved' or 'rejected'.",
        )

    before_status = application.status
    application.status = decision
    application.reviewed_by = reviewer
    application.reviewed_at = timezone.now()
    application.review_notes = review_notes
    application.save(
        update_fields=[
            "status",
            "reviewed_by",
            "reviewed_at",
            "review_notes",
            "updated_at",
        ]
    )

    if decision == OnboardingStatus.APPROVED:
        from iam.models import Role, UserOrganizationRole

        group_leader_role, _ = Role.objects.get_or_create(
            code=RoleCode.GROUP_LEADER.value,
            defaults={"name": "Group Leader"},
        )
        assignment, created = UserOrganizationRole.objects.get_or_create(
            user=application.applicant,
            organization=application.organization,
            role=group_leader_role,
            defaults={"is_active": True},
        )
        if not created and not assignment.is_active:
            assignment.is_active = True
            assignment.save(update_fields=["is_active", "updated_at"])

    log_audit_event(
        action=f"leader_onboarding.review.{decision}",
        organization=application.organization,
        actor_user=reviewer,
        request=request,
        resource_type="leader_onboarding",
        resource_id=str(application.id),
        metadata={"decision": decision},
        before_data={"status": before_status},
        after_data={"status": application.status},
    )
    return application
