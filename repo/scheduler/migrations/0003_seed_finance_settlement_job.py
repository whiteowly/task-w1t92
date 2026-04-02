from django.db import migrations
from django.utils import timezone


def seed_finance_settlement_job(apps, schema_editor):
    ScheduledJob = apps.get_model("scheduler", "ScheduledJob")
    ScheduledJob.objects.get_or_create(
        code="finance-monthly-settlement",
        defaults={
            "description": "Automatic monthly settlement generation across active organizations",
            "handler": "finance.settlement.monthly",
            "interval_seconds": 900,
            "next_run_at": timezone.now(),
            "is_enabled": True,
        },
    )


def unseed_finance_settlement_job(apps, schema_editor):
    ScheduledJob = apps.get_model("scheduler", "ScheduledJob")
    ScheduledJob.objects.filter(code="finance-monthly-settlement").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("scheduler", "0002_seed_jobs"),
    ]

    operations = [
        migrations.RunPython(
            seed_finance_settlement_job,
            unseed_finance_settlement_job,
        ),
    ]
