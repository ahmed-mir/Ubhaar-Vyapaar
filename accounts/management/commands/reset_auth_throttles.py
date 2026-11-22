from django.core.management.base import BaseCommand, CommandError

from accounts.models import AuthRateLimitBucket


class Command(BaseCommand):
    help = "Clear authentication throttle state after explicit confirmation."

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Confirm clearing application rate-limit buckets.",
        )

    def handle(self, *args, **options):
        if not options["confirm"]:
            raise CommandError("Pass --confirm to clear authentication throttle state.")

        bucket_count, _ = AuthRateLimitBucket.objects.all().delete()
        self.stdout.write(
            self.style.SUCCESS(
                "Cleared authentication throttle state: "
                f"{bucket_count} rate-limit records."
            )
        )
