from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from iam.models import Role, UserOrganizationRole
from tenancy.models import Organization

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Bootstrap the first tenant organization and administrator user. "
        "Use this once for initial platform setup when no API session exists yet."
    )

    def add_arguments(self, parser):
        parser.add_argument("--org-name", required=True, help="Organization name")
        parser.add_argument("--org-slug", required=True, help="Organization slug")
        parser.add_argument("--org-timezone", default="UTC", help="Timezone (default: UTC)")
        parser.add_argument("--admin-username", required=True, help="Admin username")
        parser.add_argument("--admin-password", required=True, help="Admin password")
        parser.add_argument("--admin-email", default="", help="Admin email (optional)")
        parser.add_argument("--admin-full-name", default="", help="Admin full name (optional)")

    @transaction.atomic
    def handle(self, *args, **options):
        slug = options["org_slug"]
        if Organization.objects.filter(slug=slug).exists():
            raise CommandError(f"Organization with slug '{slug}' already exists.")

        org = Organization.objects.create(
            name=options["org_name"],
            slug=slug,
            timezone=options["org_timezone"],
        )
        self.stdout.write(f"Created organization: {org.name} ({org.slug})")

        username = options["admin_username"]
        if User.objects.filter(username=username).exists():
            raise CommandError(f"User with username '{username}' already exists.")

        user = User.objects.create_user(
            username=username,
            password=options["admin_password"],
            email=options["admin_email"],
            full_name=options["admin_full_name"],
        )
        self.stdout.write(f"Created user: {user.username}")

        admin_role = Role.objects.get(code="administrator")
        UserOrganizationRole.objects.create(
            user=user, organization=org, role=admin_role
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Assigned administrator role to {user.username} in {org.slug}. "
                "Bootstrap complete."
            )
        )
