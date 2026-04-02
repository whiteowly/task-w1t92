from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from scheduler.models import ScheduledJob
from scheduler.registry import JOB_HANDLERS


def acquire_due_jobs(*, now=None, limit=10, worker_id="scheduler"):
    now = now or timezone.now()
    acquired_jobs = []

    with transaction.atomic():
        due = (
            ScheduledJob.objects.select_for_update(skip_locked=True)
            .filter(is_enabled=True, next_run_at__lte=now)
            .order_by("next_run_at")[:limit]
        )
        for job in due:
            job.locked_at = now
            job.locked_by = worker_id
            job.save(update_fields=["locked_at", "locked_by", "updated_at"])
            acquired_jobs.append(job)

    return acquired_jobs


def run_job(job: ScheduledJob, *, now=None):
    now = now or timezone.now()
    handler = JOB_HANDLERS.get(job.handler)
    if handler is None:
        job.last_error = f"No handler registered for '{job.handler}'"
        job.last_run_at = now
        job.next_run_at = now + timedelta(seconds=job.interval_seconds)
        job.locked_at = None
        job.locked_by = ""
        job.save(
            update_fields=[
                "last_error",
                "last_run_at",
                "next_run_at",
                "locked_at",
                "locked_by",
                "updated_at",
            ]
        )
        return

    try:
        handler(job=job, now=now)
        job.last_success_at = now
        job.last_error = ""
    except Exception as exc:  # noqa: BLE001
        job.last_error = str(exc)

    job.last_run_at = now
    job.next_run_at = now + timedelta(seconds=job.interval_seconds)
    job.locked_at = None
    job.locked_by = ""
    job.save(
        update_fields=[
            "last_success_at",
            "last_error",
            "last_run_at",
            "next_run_at",
            "locked_at",
            "locked_by",
            "updated_at",
        ]
    )
