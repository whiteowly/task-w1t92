from django.utils import timezone

from common.exceptions import DomainAPIException
from observability.models import MetricsSnapshot
from scheduler.registry import register_job


@register_job("scheduler.heartbeat")
def scheduler_heartbeat(*, job, now):
    MetricsSnapshot.objects.create(
        organization=None,
        metric_key="scheduler.heartbeat",
        payload={"job_code": job.code},
        captured_at=timezone.now(),
    )


class _SchedulerSystemRequest:
    request_id = "scheduler"
    META = {"REMOTE_ADDR": ""}


@register_job("finance.settlement.monthly")
def finance_settlement_monthly(*, job, now):
    from finance.services import generate_monthly_settlement
    from tenancy.models import Organization

    scheduler_request = _SchedulerSystemRequest()
    for organization in Organization.objects.filter(is_active=True).order_by("id"):
        try:
            generate_monthly_settlement(
                organization=organization,
                actor=None,
                request=scheduler_request,
                run_at_utc=now,
            )
        except DomainAPIException as exc:
            if exc.error_code == "settlement.not_due":
                continue
            raise
