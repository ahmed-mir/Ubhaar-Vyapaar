from django import forms
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from .rate_limits import (
    check_login_identifier_throttle,
    record_login_identifier_failure,
    record_throttle_event,
)


class LoginIdentifierThrottleMixin:
    throttled_error = _("Too many sign-in attempts. Please try again later.")

    def _mark_identifier_throttled(self, decision, *, log_event=False):
        self.request._auth_login_identifier_throttled = decision
        if log_event:
            record_throttle_event("login_identifier_failure")

    def clean(self):
        identifier = self.cleaned_data.get("username", "")
        decision = check_login_identifier_throttle(identifier)
        if decision.throttled:
            self._mark_identifier_throttled(decision, log_event=True)
            raise ValidationError(self.throttled_error, code="throttled")

        try:
            return super().clean()
        except ValidationError:
            if getattr(self.request, "_auth_login_identifier_throttled", None):
                raise ValidationError(
                    self.throttled_error,
                    code="throttled",
                )
            raise

class EmailOrUsernameAuthenticationForm(
    LoginIdentifierThrottleMixin,
    AuthenticationForm,
):
    username = forms.CharField(
        label=_("Email or username"),
        max_length=254,
        strip=True,
        widget=forms.TextInput(
            attrs={
                "autocapitalize": "none",
                "autocomplete": "username",
                "autofocus": True,
            }
        ),
    )

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": _(
            "Please enter a correct email or username and password."
        ),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].help_text = (
            "Use your email address or username. Phone sign-in is not available."
        )
        self.fields["password"].widget.attrs["autocomplete"] = "current-password"


class RateLimitedAdminAuthenticationForm(
    LoginIdentifierThrottleMixin,
    AdminAuthenticationForm,
):
    """Keep Django Admin auth intact while sharing identifier throttling."""

    def confirm_login_allowed(self, user):
        try:
            return super().confirm_login_allowed(user)
        except ValidationError:
            # Django Admin rejects authenticated non-staff users here rather
            # than emitting user_login_failed, so count that failed Admin auth.
            decision = record_login_identifier_failure(
                self.cleaned_data.get("username", ""),
            )
            if decision.throttled:
                self._mark_identifier_throttled(decision, log_event=True)
            raise
