"""Authentication signals for database-backed login throttling."""

from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.dispatch import receiver

from .rate_limits import (
    clear_login_identifier_failures,
    record_login_identifier_failure,
    record_throttle_event,
)


LOGIN_VIEW_NAMES = {"login", "admin:login"}


def _is_login_request(request):
    if request is None:
        return False
    match = getattr(request, "resolver_match", None)
    return bool(match and match.view_name in LOGIN_VIEW_NAMES)


def _submitted_identifier(request, credentials=None):
    credentials = credentials or {}
    identifier = credentials.get("username")
    if identifier is None and request is not None:
        identifier = request.POST.get("username", "")
    return identifier or ""


@receiver(user_login_failed, dispatch_uid="accounts.record_login_identifier_failure")
def record_failed_login(sender, credentials, request=None, **kwargs):
    """Count only actual failed auth attempts on the public/Admin login views."""
    if not _is_login_request(request):
        return

    decision = record_login_identifier_failure(
        _submitted_identifier(request, credentials),
    )
    if decision.throttled:
        request._auth_login_identifier_throttled = decision
        record_throttle_event("login_identifier_failure")


@receiver(user_logged_in, dispatch_uid="accounts.clear_login_identifier_failures")
def clear_successful_login_failures(sender, request, user, **kwargs):
    """Clear this identifier's failures after successful public/Admin login."""
    if not _is_login_request(request):
        return

    submitted_identifier = _submitted_identifier(request)
    clear_login_identifier_failures(submitted_identifier or user.get_username())
