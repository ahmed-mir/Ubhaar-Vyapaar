"""Shared, privacy-preserving authentication throttle helpers."""

import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as datetime_timezone

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core import signing
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import F
from django.shortcuts import render
from django.utils import timezone

from .models import AuthRateLimitBucket


logger = logging.getLogger("accounts.security")


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int = 0


@dataclass(frozen=True)
class LoginIdentifierDecision:
    throttled: bool
    retry_after_seconds: int = 0


def normalize_email_identifier(value):
    """Return normalized email input or ``None`` when it is not an email."""
    email = (value or "").strip()
    if not email:
        return None
    try:
        validate_email(email)
    except ValidationError:
        return None
    return email.lower()


def normalize_login_identifier(value):
    """Match the login backend's email normalization without changing usernames."""
    identifier = (value or "").strip()
    if not identifier:
        return ""
    normalized_email = normalize_email_identifier(identifier)
    return normalized_email if normalized_email else identifier


def _digest(scope, value):
    material = f"ubhaar-auth-limit:v1:{scope}:{value}".encode("utf-8")
    secret = settings.SECRET_KEY.encode("utf-8")
    return hmac.new(secret, material, hashlib.sha256).hexdigest()


SOURCE_COOKIE_NAME = "uv_auth_rate_source"
SOURCE_COOKIE_SALT = "accounts.auth-rate-source.v1"
SOURCE_COOKIE_MAX_AGE = 30 * 24 * 60 * 60
LOGIN_IDENTIFIER_FAILURE_SCOPE = "login_identifier_failure"


def ensure_source_limit_key(request):
    """Return an opaque signed browser marker; only its HMAC is persisted."""
    try:
        value = request.get_signed_cookie(
            SOURCE_COOKIE_NAME,
            salt=SOURCE_COOKIE_SALT,
            max_age=SOURCE_COOKIE_MAX_AGE,
        )
    except (signing.BadSignature, KeyError):
        value = ""

    if not value:
        value = secrets.token_urlsafe(32)
    request._auth_rate_source_cookie_value = value
    return value


def attach_source_limit_cookie(request, response):
    value = getattr(request, "_auth_rate_source_cookie_value", None)
    if value:
        response.set_signed_cookie(
            SOURCE_COOKIE_NAME,
            value,
            salt=SOURCE_COOKIE_SALT,
            max_age=SOURCE_COOKIE_MAX_AGE,
            httponly=True,
            secure=settings.SESSION_COOKIE_SECURE,
            samesite="Lax",
            path="/",
        )
    return response


def _fixed_window_start(now, window_seconds):
    timestamp = int(now.timestamp())
    start = timestamp - timestamp % window_seconds
    return datetime.fromtimestamp(start, tz=datetime_timezone.utc)


def _retry_after(window_start, window_seconds, now):
    return max(
        1,
        int(
            (
                window_start
                + timedelta(seconds=window_seconds)
                - now
            ).total_seconds()
        ),
    )


def login_identifier_digest(identifier):
    """Return the keyed digest for an identifier using login normalization."""
    normalized = normalize_login_identifier(identifier)
    return _digest(LOGIN_IDENTIFIER_FAILURE_SCOPE, normalized) if normalized else ""


def check_login_identifier_throttle(identifier, *, now=None):
    """Check the identifier's current fixed window without incrementing it."""
    normalized = normalize_login_identifier(identifier)
    if not normalized:
        return LoginIdentifierDecision(throttled=False)

    now = now or timezone.now()
    window_seconds = settings.AUTH_LOGIN_WINDOW_SECONDS
    window_start = _fixed_window_start(now, window_seconds)
    count = (
        AuthRateLimitBucket.objects.filter(
            scope=LOGIN_IDENTIFIER_FAILURE_SCOPE,
            key_digest=login_identifier_digest(normalized),
            window_start=window_start,
        )
        .values_list("count", flat=True)
        .first()
        or 0
    )
    if count < settings.AUTH_LOGIN_LIMIT:
        return LoginIdentifierDecision(throttled=False)
    return LoginIdentifierDecision(
        throttled=True,
        retry_after_seconds=_retry_after(window_start, window_seconds, now),
    )


def record_login_identifier_failure(identifier, *, now=None):
    """Atomically record one failed auth in a deterministic fixed window.

    The request that records failure number ``AUTH_LOGIN_LIMIT`` is itself
    throttled. A saturated bucket is never incremented or extended.
    """
    normalized = normalize_login_identifier(identifier)
    if not normalized:
        return LoginIdentifierDecision(throttled=False)

    now = now or timezone.now()
    window_seconds = settings.AUTH_LOGIN_WINDOW_SECONDS
    window_start = _fixed_window_start(now, window_seconds)
    digest = login_identifier_digest(normalized)
    with transaction.atomic():
        bucket, _ = AuthRateLimitBucket.objects.get_or_create(
            scope=LOGIN_IDENTIFIER_FAILURE_SCOPE,
            key_digest=digest,
            window_start=window_start,
            defaults={"count": 0},
        )
        bucket = AuthRateLimitBucket.objects.select_for_update().get(pk=bucket.pk)

        if bucket.count >= settings.AUTH_LOGIN_LIMIT:
            return LoginIdentifierDecision(
                throttled=True,
                retry_after_seconds=_retry_after(
                    window_start,
                    window_seconds,
                    now,
                ),
            )

        next_count = bucket.count + 1
        AuthRateLimitBucket.objects.filter(pk=bucket.pk).update(
            count=F("count") + 1,
            updated_at=now,
        )

    if next_count < settings.AUTH_LOGIN_LIMIT:
        return LoginIdentifierDecision(throttled=False)
    return LoginIdentifierDecision(
        throttled=True,
        retry_after_seconds=_retry_after(window_start, window_seconds, now),
    )


def clear_login_identifier_failures(identifier):
    """Clear only this normalized login identifier's failure buckets."""
    digest = login_identifier_digest(identifier)
    if not digest:
        return 0
    deleted, _ = AuthRateLimitBucket.objects.filter(
        scope=LOGIN_IDENTIFIER_FAILURE_SCOPE,
        key_digest=digest,
    ).delete()
    return deleted


def consume_rate_limits(specifications, *, now=None):
    """Atomically consume all fixed-window counters in one shared database."""
    now = now or timezone.now()
    prepared = []
    for scope, raw_value, limit, window_seconds in specifications:
        if not raw_value:
            continue
        if limit < 1 or window_seconds < 1:
            raise ValueError("Rate-limit values must be positive integers.")
        digest = _digest(scope, str(raw_value))
        window_start = _fixed_window_start(now, window_seconds)
        prepared.append(
            (scope, digest, window_start, limit, window_seconds)
        )

    if not prepared:
        return RateLimitDecision(allowed=True)

    prepared.sort(key=lambda item: (item[0], item[1], item[2]))
    with transaction.atomic():
        # Avoid leaving empty rows for unrelated keys when one existing
        # dimension is already blocked (for example, reset-email throttles).
        existing = []
        for scope, digest, window_start, limit, window_seconds in prepared:
            bucket = (
                AuthRateLimitBucket.objects.select_for_update()
                .filter(
                    scope=scope,
                    key_digest=digest,
                    window_start=window_start,
                )
                .first()
            )
            if bucket is not None and bucket.count >= limit:
                retry_after = _retry_after(window_start, window_seconds, now)
                return RateLimitDecision(
                    allowed=False,
                    retry_after_seconds=retry_after,
                )
            existing.append(bucket)

        locked_buckets = []
        for scope, digest, window_start, limit, window_seconds in prepared:
            bucket, _ = AuthRateLimitBucket.objects.get_or_create(
                scope=scope,
                key_digest=digest,
                window_start=window_start,
                defaults={"count": 0},
            )
            bucket = AuthRateLimitBucket.objects.select_for_update().get(
                pk=bucket.pk,
            )
            locked_buckets.append(
                (bucket, limit, window_seconds, window_start)
            )

        blocked = [
            item
            for item in locked_buckets
            if item[0].count >= item[1]
        ]
        if blocked:
            retry_after = max(
                _retry_after(window_start, window_seconds, now)
                for _, _, window_seconds, window_start in blocked
            )
            return RateLimitDecision(
                allowed=False,
                retry_after_seconds=retry_after,
            )

        for bucket, _, _, _ in locked_buckets:
            AuthRateLimitBucket.objects.filter(pk=bucket.pk).update(
                count=F("count") + 1,
                updated_at=now,
            )

    return RateLimitDecision(allowed=True)


def record_throttle_event(scope):
    """Log a throttle event without identifiers, IPs, or submitted values."""
    logger.warning("Authentication request throttled", extra={"scope": scope})


def registration_throttle_response(
    request,
    form,
    template_name,
    retry_after_seconds,
    scope="signup",
):
    form.add_error(None, "Too many registration attempts. Please try again later.")
    response = render(
        request,
        template_name,
        {"form": form},
        status=429,
    )
    response["Retry-After"] = str(retry_after_seconds)
    record_throttle_event(scope)
    return attach_source_limit_cookie(request, response)

def login_source_throttle_response(request, decision, form):
    form.add_error(None, "Too many sign-in attempts. Please try again later.")
    response = render(
        request,
        "accounts/login.html",
        {"form": form, "next": request.POST.get("next", "")},
        status=429,
    )
    response["Retry-After"] = str(decision.retry_after_seconds)
    record_throttle_event("login_source")
    return attach_source_limit_cookie(request, response)
