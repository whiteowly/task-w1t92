from django.db import migrations


ROLE_SEED = [
    ("administrator", "Administrator"),
    ("club_manager", "Club Manager"),
    ("counselor_reviewer", "Counselor/Reviewer"),
    ("group_leader", "Group Leader"),
    ("member", "Member"),
]


def seed_roles(apps, schema_editor):
    Role = apps.get_model("iam", "Role")
    for code, name in ROLE_SEED:
        Role.objects.get_or_create(code=code, defaults={"name": name})


def unseed_roles(apps, schema_editor):
    Role = apps.get_model("iam", "Role")
    Role.objects.filter(code__in=[code for code, _ in ROLE_SEED]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("iam", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_roles, unseed_roles),
    ]
