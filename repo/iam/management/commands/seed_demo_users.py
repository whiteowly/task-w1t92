"""
Create demo users for all five roles within the first organization.

Idempotent — skips users that already exist.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from iam.models import Role, UserOrganizationRole
from tenancy.models import Organization

User = get_user_model()

DEMO_USERS = [
    {
        "username": "admin",
        "email": "admin@example.com",
        "full_name": "Platform Admin",
        "password": "StrongPassword123!",
        "role": "administrator",
    },
    {
        "username": "club.manager",
        "email": "club.manager@example.com",
        "full_name": "Club Manager",
        "password": "StrongPassword123!",
        "role": "club_manager",
    },
    {
        "username": "counselor.reviewer",
        "email": "counselor.reviewer@example.com",
        "full_name": "Counselor Reviewer",
        "password": "StrongPassword123!",
        "role": "counselor_reviewer",
    },
    {
        "username": "group.leader",
        "email": "group.leader@example.com",
        "full_name": "Group Leader",
        "password": "StrongPassword123!",
        "role": "group_leader",
    },
    {
        "username": "member.user",
        "email": "member.user@example.com",
        "full_name": "Member User",
        "password": "StrongPassword123!",
        "role": "member",
    },
]


class Command(BaseCommand):
    help = "Seed demo users for all roles in the first organization."

    def add_arguments(self, parser):
        parser.add_argument(
            "--org-slug",
            default="heritage-org",
            help="Organization slug (default: heritage-org)",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        org_slug = options["org_slug"]
        try:
            org = Organization.objects.get(slug=org_slug)
        except Organization.DoesNotExist:
            self.stderr.write(
                f"Organization '{org_slug}' not found. "
                "Run bootstrap_tenant first."
            )
            return

        for entry in DEMO_USERS:
            user, created = User.objects.get_or_create(
                username=entry["username"],
                defaults={
                    "email": entry["email"],
                    "full_name": entry["full_name"],
                },
            )
            if created:
                user.set_password(entry["password"])
                user.save(update_fields=["password"])
                self.stdout.write(f"Created user: {user.username}")
            else:
                self.stdout.write(f"User already exists: {user.username}")

            role = Role.objects.get(code=entry["role"])
            _, role_created = UserOrganizationRole.objects.get_or_create(
                user=user,
                organization=org,
                role=role,
                defaults={"is_active": True},
            )
            if role_created:
                self.stdout.write(
                    f"  Assigned role '{entry['role']}' to {user.username}"
                )

        self.stdout.write(self.style.SUCCESS("Demo users seeded successfully."))
