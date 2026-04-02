import time

from django.core.management.base import BaseCommand
from django.db import connections
from django.db.utils import OperationalError


class Command(BaseCommand):
    help = "Wait for the default database to become available."

    def handle(self, *args, **options):
        self.stdout.write("Waiting for database...")
        for attempt in range(60):
            try:
                connection = connections["default"]
                connection.cursor()
                self.stdout.write(self.style.SUCCESS("Database is available."))
                return
            except OperationalError:
                time.sleep(1)
                self.stdout.write(
                    f"Database unavailable, retrying ({attempt + 1}/60)..."
                )

        raise OperationalError("Database did not become available in time.")
