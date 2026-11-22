from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import AuthRateLimitBucket
from accounts.rate_limits import LOGIN_IDENTIFIER_FAILURE_SCOPE, _fixed_window_start


class Command(BaseCommand):
    help = "Remove expired authentication throttle records."

    def handle(self, *args, **options):
        now = timezone.now()
        windows_by_scope = {
            LOGIN_IDENTIFIER_FAILURE_SCOPE: settings.AUTH_LOGIN_WINDOW_SECONDS,
            "login_source": settings.AUTH_LOGIN_WINDOW_SECONDS,
            "password_reset_source": settings.PASSWORD_RESET_SOURCE_WINDOW_SECONDS,
            "password_reset_email": settings.PASSWORD_RESET_WINDOW_SECONDS,
            "signup_source": settings.SIGNUP_WINDOW_SECONDS,
        }
        bucket_count = 0
        for scope, window_seconds in windows_by_scope.items():
            current_window_start = _fixed_window_start(now, window_seconds)
            deleted, _ = AuthRateLimitBucket.objects.filter(
                scope=scope,
                window_start__lt=current_window_start,
            ).delete()
            bucket_count += deleted

        self.stdout.write(
            self.style.SUCCESS(
                "Pruned expired authentication throttle state: "
                f"{bucket_count} rate-limit records."
            )
        )
