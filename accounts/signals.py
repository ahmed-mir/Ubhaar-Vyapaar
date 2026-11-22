"""Authentication signals used for shared login throttle cleanup."""

from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver


@receiver(user_logged_in, dispatch_uid="accounts.clear_email_login_attempts")
def clear_email_login_attempts(sender, request, user, **kwargs):
    """Clear an email-form login's pseudonymous Axes key after success."""
    if request is None:
        return

    submitted_identifier = request.POST.get("username", "").strip()
    if "@" not in submitted_identifier:
        return

    from axes.models import AccessAttempt

    from .rate_limits import axes_username_digest

    digest = axes_username_digest(
        request,
        {"username": submitted_identifier},
    )
    AccessAttempt.objects.filter(
        username=digest,
        ip_address__isnull=True,
    ).delete()
