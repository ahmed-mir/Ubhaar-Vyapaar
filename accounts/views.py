from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.views import LoginView, PasswordResetView
from django.db import IntegrityError, transaction
from django.db.models.functions import Lower, Trim
from django.shortcuts import redirect, render
from django.conf import settings

from marketplace.models import ManufacturerProfile

from .forms import (
    BuyerRegistrationForm,
    ManufacturerRegistrationForm,
)
from .rate_limits import (
    attach_source_limit_cookie,
    consume_rate_limits,
    ensure_source_limit_key,
    login_source_throttle_response,
    normalize_email_identifier,
    record_throttle_event,
    registration_throttle_response,
)


def _add_registration_constraint_error(form):
    email = form.cleaned_data.get("email", "").strip().lower()
    if email:
        duplicate_email = get_user_model().objects.annotate(
            _normalized_email=Lower(Trim("email")),
        ).filter(_normalized_email=email)
        if duplicate_email.exists():
            form.add_error(
                "email",
                "An account with this email address already exists.",
            )
            return True

    username = form.cleaned_data.get("username")
    if username and get_user_model().objects.filter(username=username).exists():
        form.add_error("username", "A user with that username already exists.")
        return True
    return False


def get_started(request):
    if request.user.is_authenticated:
        return redirect("home")
    return render(request, "accounts/get_started.html")


def register(request):
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        form = BuyerRegistrationForm(request.POST)

        if form.is_valid():
            decision = consume_rate_limits(
                [
                    (
                        "signup_source",
                        ensure_source_limit_key(request),
                        settings.SIGNUP_LIMIT,
                        settings.SIGNUP_WINDOW_SECONDS,
                    ),
                ]
            )
            if not decision.allowed:
                return registration_throttle_response(
                    request,
                    form,
                    "accounts/register.html",
                    decision.retry_after_seconds,
                )

            try:
                with transaction.atomic():
                    user = form.save()
            except IntegrityError:
                if not _add_registration_constraint_error(form):
                    raise
            else:
                login(
                    request,
                    user,
                    backend="accounts.backends.EmailOrUsernameBackend",
                )
                messages.success(
                    request,
                    "Your buyer account is ready. You can now browse capacity "
                    "and request quotations from eligible listings.",
                )
                return attach_source_limit_cookie(request, redirect("home"))
    else:
        form = BuyerRegistrationForm()

    response = render(
        request,
        "accounts/register.html",
        {"form": form},
    )
    return attach_source_limit_cookie(request, response)
def register_manufacturer(request):
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        form = ManufacturerRegistrationForm(request.POST)

        if form.is_valid():
            decision = consume_rate_limits(
                [
                    (
                        "signup_source",
                        ensure_source_limit_key(request),
                        settings.SIGNUP_LIMIT,
                        settings.SIGNUP_WINDOW_SECONDS,
                    ),
                ]
            )
            if not decision.allowed:
                return registration_throttle_response(
                    request,
                    form,
                    "accounts/register_manufacturer.html",
                    decision.retry_after_seconds,
                )

            try:
                with transaction.atomic():
                    user = form.save()

                    ManufacturerProfile.objects.create(
                        user=user,
                        business_name=form.cleaned_data["business_name"],
                        description=form.cleaned_data["description"],
                        city=form.cleaned_data["city"],
                        state=form.cleaned_data["state"],
                        pincode=form.cleaned_data["pincode"],
                        is_verified=False,
                        kyc_status=ManufacturerProfile.KycStatus.UNDER_REVIEW,
                    )
            except IntegrityError:
                if not _add_registration_constraint_error(form):
                    raise
            else:
                login(
                    request,
                    user,
                    backend="accounts.backends.EmailOrUsernameBackend",
                )

                messages.success(
                    request,
                    "Your manufacturer account is ready. "
                    "Complete your business profile and manage your listings "
                    "from the dashboard. Listings become public only after "
                    "your business is verified.",
                )

                return attach_source_limit_cookie(
                    request,
                    redirect("manufacturer_dashboard"),
                )
    else:
        form = ManufacturerRegistrationForm()

    response = render(
        request,
        "accounts/register_manufacturer.html",
        {"form": form},
    )
    return attach_source_limit_cookie(request, response)


class RateLimitedPasswordResetView(PasswordResetView):
    """Keep reset responses generic while limiting email and session abuse."""

    def post(self, request, *args, **kwargs):
        submitted_email = normalize_email_identifier(
            request.POST.get("email", "")
        )
        specifications = [
            (
                "password_reset_source",
                ensure_source_limit_key(request),
                settings.PASSWORD_RESET_SOURCE_LIMIT,
                settings.PASSWORD_RESET_SOURCE_WINDOW_SECONDS,
            ),
        ]
        if submitted_email:
            specifications.append(
                (
                    "password_reset_email",
                    submitted_email,
                    settings.PASSWORD_RESET_LIMIT,
                    settings.PASSWORD_RESET_WINDOW_SECONDS,
                )
            )

        decision = consume_rate_limits(specifications)
        if not decision.allowed:
            record_throttle_event("password_reset")
            # Same redirect and completion page as an ordinary valid request;
            # do not reveal whether an account exists or a message was sent.
            return attach_source_limit_cookie(
                request,
                redirect(self.get_success_url()),
            )

        return attach_source_limit_cookie(
            request,
            super().post(request, *args, **kwargs),
        )


class RateLimitedLoginView(LoginView):
    """Add a modest session-source ceiling alongside Axes identifier limits."""

    def post(self, request, *args, **kwargs):
        decision = consume_rate_limits(
            [
                (
                    "login_source",
                    ensure_source_limit_key(request),
                    settings.AUTH_LOGIN_SOURCE_LIMIT,
                    settings.AUTH_LOGIN_WINDOW_SECONDS,
                ),
            ]
        )
        if not decision.allowed:
            return login_source_throttle_response(
                request,
                decision,
                self.get_form(),
            )

        return attach_source_limit_cookie(
            request,
            super().post(request, *args, **kwargs),
        )
