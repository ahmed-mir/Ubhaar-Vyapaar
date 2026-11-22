from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import AuthRateLimitBucket


class Command(BaseCommand):
    help = "Remove expired authentication throttle records."

    def handle(self, *args, **options):
        now = timezone.now()
        windows = (
            settings.AUTH_LOGIN_WINDOW_SECONDS,
            settings.PASSWORD_RESET_WINDOW_SECONDS,
            settings.PASSWORD_RESET_SOURCE_WINDOW_SECONDS,
            settings.SIGNUP_WINDOW_SECONDS,
        )
        largest_window = max(windows)
        bucket_cutoff = now - timedelta(seconds=largest_window)
        bucket_count, _ = AuthRateLimitBucket.objects.filter(
            window_start__lt=bucket_cutoff,
        ).delete()

        from axes.models import AccessAttempt

        login_cutoff = now - timedelta(
            seconds=settings.AUTH_LOGIN_WINDOW_SECONDS,
        )
        attempt_count, _ = AccessAttempt.objects.filter(
            attempt_time__lt=login_cutoff,
        ).delete()

        self.stdout.write(
            self.style.SUCCESS(
                "Pruned expired authentication throttle state: "
                f"{bucket_count} rate-limit records and "
                f"{attempt_count} login-attempt records."
            )
        )
