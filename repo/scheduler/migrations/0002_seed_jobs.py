from django.db import migrations
from django.utils import timezone


def seed_scheduler_jobs(apps, schema_editor):
    ScheduledJob = apps.get_model("scheduler", "ScheduledJob")
    ScheduledJob.objects.get_or_create(
        code="scheduler-heartbeat",
        defaults={
            "description": "Baseline scheduler heartbeat snapshot job",
            "handler": "scheduler.heartbeat",
            "interval_seconds": 300,
            "next_run_at": timezone.now(),
            "is_enabled": True,
        },
    )


def unseed_scheduler_jobs(apps, schema_editor):
    ScheduledJob = apps.get_model("scheduler", "ScheduledJob")
    ScheduledJob.objects.filter(code="scheduler-heartbeat").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("scheduler", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_scheduler_jobs, unseed_scheduler_jobs),
    ]
