import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from scheduler.services import acquire_due_jobs, run_job


class Command(BaseCommand):
    help = "Run MySQL-backed periodic jobs."

    def add_arguments(self, parser):
        parser.add_argument(
            "--once", action="store_true", help="Run only one scheduler tick."
        )
        parser.add_argument(
            "--sleep", type=int, default=5, help="Sleep duration between ticks."
        )
        parser.add_argument("--worker-id", type=str, default="scheduler-worker")

    def handle(self, *args, **options):
        run_once = options["once"]
        sleep_seconds = options["sleep"]
        worker_id = options["worker_id"]

        while True:
            now = timezone.now()
            jobs = acquire_due_jobs(now=now, worker_id=worker_id)
            for job in jobs:
                run_job(job, now=now)

            if run_once:
                break
            time.sleep(sleep_seconds)
