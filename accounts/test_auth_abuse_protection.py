from datetime import datetime, timedelta, timezone as datetime_timezone
from unittest.mock import patch

from django.conf import settings as project_settings
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import AuthRateLimitBucket
from .rate_limits import (
    LOGIN_IDENTIFIER_FAILURE_SCOPE,
    SOURCE_COOKIE_NAME,
    _fixed_window_start,
    consume_rate_limits,
    login_identifier_digest,
)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AuthenticationAbuseProtectionTests(TestCase):
    password = "Fixture-Only-Strong@4821"

    def create_user(self, username, email, **kwargs):
        return get_user_model().objects.create_user(
            username=username,
            email=email,
            password=self.password,
            **kwargs,
        )

    def login_post(self, client, identifier, password=None, path=None):
        return client.post(
            path or reverse("login"),
            {
                "username": identifier,
                "password": password or self.password,
            },
        )

    def login_post_at(self, client, identifier, when, password=None, path=None):
        with patch("accounts.rate_limits.timezone.now", return_value=when):
            return self.login_post(client, identifier, password, path)

    def reset_post(self, client, email):
        return client.post(reverse("password_reset"), {"email": email})

    def buyer_registration_data(self, suffix):
        return {
            "username": f"buyer-limit-{suffix}",
            "email": f"buyer-limit-{suffix}@example.test",
            "phone": "",
            "password1": self.password,
            "password2": self.password,
            "legal_acknowledgement": "on",
        }

    def manufacturer_registration_data(self, suffix):
        return {
            "username": f"manufacturer-limit-{suffix}",
            "email": f"manufacturer-limit-{suffix}@example.test",
            "phone": "",
            "business_name": "Limit Test Works",
            "description": "Test-only manufacturer profile.",
            "city": "Pune",
            "state": "Maharashtra",
            "pincode": "400001",
            "password1": self.password,
            "password2": self.password,
            "legal_acknowledgement": "on",
        }

    def current_identifier_bucket(self, identifier, now=None):
        now = now or timezone.now()
        return AuthRateLimitBucket.objects.filter(
            scope=LOGIN_IDENTIFIER_FAILURE_SCOPE,
            key_digest=login_identifier_digest(identifier),
            window_start=_fixed_window_start(
                now,
                project_settings.AUTH_LOGIN_WINDOW_SECONDS,
            ),
        )

    def test_failures_one_to_four_are_generic_and_failure_five_throttles(self):
        user = self.create_user("limited-buyer", "limited@example.test")
        clients = (Client(), Client())

        for index in range(project_settings.AUTH_LOGIN_LIMIT - 1):
            response = self.login_post(
                clients[index % 2],
                "LIMITED@EXAMPLE.TEST",
                password="Wrong-Password@4821",
            )
            self.assertEqual(response.status_code, 200)
            self.assertContains(
                response,
                "Please enter a correct email or username and password",
            )

        with self.assertLogs("accounts.security", level="WARNING") as logs:
            response = self.login_post(
                clients[1],
                "limited@example.test",
                password="Wrong-Password@4821",
            )
        self.assertEqual(response.status_code, 429)
        self.assertGreaterEqual(int(response["Retry-After"]), 1)
        self.assertContains(response, "Too many sign-in attempts", status_code=429)
        self.assertNotIn(user.email, " ".join(logs.output))
        self.assertNotIn("Wrong-Password@4821", " ".join(logs.output))

        # Attempts beyond the threshold stay blocked and do not extend/count it.
        response = self.login_post(
            clients[0],
            "LIMITED@example.test",
            password="Wrong-Password@4821",
        )
        self.assertEqual(response.status_code, 429)
        self.assertEqual(self.current_identifier_bucket(user.email).get().count, 5)
        user.refresh_from_db()
        self.assertTrue(user.is_active)

    @override_settings(AUTH_LOGIN_SOURCE_LIMIT=2)
    def test_login_browser_source_limit_reduces_identifier_spraying(self):
        for identifier in (
            "first-unknown@example.test",
            "second-unknown@example.test",
        ):
            response = self.login_post(
                self.client,
                identifier,
                password="Wrong-Password@4821",
            )
            self.assertEqual(response.status_code, 200)

        response = self.login_post(
            self.client,
            "third-unknown@example.test",
            password="Wrong-Password@4821",
        )
        self.assertEqual(response.status_code, 429)
        self.assertContains(response, "Too many sign-in attempts", status_code=429)

    def test_known_and_unknown_username_and_email_errors_are_generic(self):
        user = self.create_user("generic-login", "generic@example.test")
        pairs = (
            (user.username, "not-a-real-username"),
            (user.email.upper(), "not-a-real-account@example.test"),
        )
        for known_identifier, unknown_identifier in pairs:
            known = self.login_post(
                Client(),
                known_identifier,
                password="Incorrect-Password@4821",
            )
            unknown = self.login_post(
                Client(),
                unknown_identifier,
                password="Incorrect-Password@4821",
            )
            self.assertEqual((known.status_code, unknown.status_code), (200, 200))
            generic_message = "Please enter a correct email or username and password"
            self.assertContains(known, generic_message)
            self.assertContains(unknown, generic_message)

        throttled_responses = []
        for identifier in (user.username, "unknown-throttled@example.test"):
            client = Client()
            for _ in range(project_settings.AUTH_LOGIN_LIMIT):
                response = self.login_post(
                    client,
                    identifier,
                    password="Incorrect-Password@4821",
                )
            throttled_responses.append(response)

        for response in throttled_responses:
            self.assertEqual(response.status_code, 429)
            self.assertContains(response, "Too many sign-in attempts", status_code=429)

    def test_expired_fixed_window_failures_do_not_carry_forward(self):
        user = self.create_user("fixed-window-user", "fixed-window@example.test")
        client = Client()
        window_one = datetime(2026, 1, 1, 14, 0, tzinfo=datetime_timezone.utc)

        for second in range(4):
            response = self.login_post_at(
                client,
                user.email,
                window_one + timedelta(seconds=second),
                password="Wrong-Password@4821",
            )
            self.assertEqual(response.status_code, 200)

        window_two = window_one + timedelta(
            seconds=project_settings.AUTH_LOGIN_WINDOW_SECONDS,
        )
        response = self.login_post_at(
            client,
            user.email,
            window_two,
            password="Wrong-Password@4821",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.current_identifier_bucket(user.email, window_two).get().count, 1)

        for offset in range(1, project_settings.AUTH_LOGIN_LIMIT - 1):
            response = self.login_post_at(
                client,
                user.email,
                window_two + timedelta(seconds=offset),
                password="Wrong-Password@4821",
            )
            self.assertEqual(response.status_code, 200)

        response = self.login_post_at(
            client,
            user.email,
            window_two + timedelta(seconds=project_settings.AUTH_LOGIN_LIMIT),
            password="Wrong-Password@4821",
        )
        self.assertEqual(response.status_code, 429)
        self.assertEqual(self.current_identifier_bucket(user.email, window_two).get().count, 5)
        self.assertEqual(self.current_identifier_bucket(user.email, window_one).get().count, 4)

    def test_successful_login_clears_only_identifier_failures(self):
        user = self.create_user("success-reset", "success-reset@example.test")
        client = Client()
        for _ in range(3):
            response = self.login_post(
                client,
                "SUCCESS-RESET@example.test",
                password="Incorrect-Password@4821",
            )
            self.assertEqual(response.status_code, 200)

        self.assertEqual(self.current_identifier_bucket(user.email).get().count, 3)
        response = self.login_post(client, user.email)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self.current_identifier_bucket(user.email).exists())

        client.post(reverse("logout"))
        response = self.login_post(
            client,
            user.email,
            password="Incorrect-Password@4821",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.current_identifier_bucket(user.email).get().count, 1)

    def test_unrelated_identifier_remains_available(self):
        locked = self.create_user("locked-fixture", "locked@example.test")
        available = self.create_user("available-fixture", "available@example.test")
        for _ in range(project_settings.AUTH_LOGIN_LIMIT):
            self.login_post(
                self.client,
                locked.username,
                password="Incorrect-Password@4821",
            )

        response = self.login_post(Client(), available.username)
        self.assertEqual(response.status_code, 302)
        locked.refresh_from_db()
        self.assertTrue(locked.is_active)

    def test_admin_login_uses_shared_limiter_and_preserves_staff_checks(self):
        admin_user = self.create_user(
            "admin-login-fixture",
            "admin-login@example.test",
            is_staff=True,
            is_superuser=True,
        )
        self.assertEqual(admin.site.login_form.__name__, "RateLimitedAdminAuthenticationForm")
        response = self.login_post(
            self.client,
            admin_user.username,
            path="/admin/login/",
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get("/admin/").status_code, 200)

        second_admin = self.create_user(
            "admin-throttle-fixture",
            "admin-throttle@example.test",
            is_staff=True,
            is_superuser=True,
        )
        throttle_client = Client()
        for _ in range(project_settings.AUTH_LOGIN_LIMIT - 1):
            response = self.login_post(
                throttle_client,
                second_admin.username,
                password="Incorrect-Password@4821",
                path="/admin/login/",
            )
            self.assertEqual(response.status_code, 200)
        response = self.login_post(
            throttle_client,
            second_admin.username,
            password="Incorrect-Password@4821",
            path="/admin/login/",
        )
        self.assertEqual(response.status_code, 429)
        self.assertContains(response, "Too many sign-in attempts", status_code=429)
        second_admin.refresh_from_db()
        self.assertTrue(second_admin.is_active)

    def test_public_and_admin_login_share_identifier_failure_history(self):
        admin_user = self.create_user(
            "shared-admin-login",
            "shared-admin@example.test",
            is_staff=True,
            is_superuser=True,
        )
        client = Client()
        for _ in range(project_settings.AUTH_LOGIN_LIMIT - 1):
            response = self.login_post(
                client,
                admin_user.username,
                password="Incorrect-Password@4821",
            )
            self.assertEqual(response.status_code, 200)
        response = self.login_post(
            client,
            admin_user.username,
            password="Incorrect-Password@4821",
            path="/admin/login/",
        )
        self.assertEqual(response.status_code, 429)
        self.assertContains(response, "Too many sign-in attempts", status_code=429)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        PASSWORD_RESET_LIMIT=2,
    )
    def test_password_reset_known_unknown_and_throttled_responses_match(self):
        mail.outbox = []
        user = self.create_user("reset-fixture", "Reset@Example.Test")

        existing_responses = [
            self.reset_post(Client(), " RESET@example.test "),
            self.reset_post(Client(), "reset@EXAMPLE.test"),
            self.reset_post(Client(), "reset@example.test"),
        ]
        unknown_responses = [
            self.reset_post(Client(), "unknown@example.test"),
            self.reset_post(Client(), "UNKNOWN@example.test"),
            self.reset_post(Client(), "unknown@example.test"),
        ]
        for response in existing_responses + unknown_responses:
            self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(
            [response.status_code for response in existing_responses],
            [response.status_code for response in unknown_responses],
        )
        self.assertEqual(
            [response["Location"] for response in existing_responses],
            [response["Location"] for response in unknown_responses],
        )
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        for bucket in AuthRateLimitBucket.objects.filter(scope="password_reset_email"):
            self.assertNotIn(user.email, bucket.key_digest)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        PASSWORD_RESET_SOURCE_LIMIT=8,
    )
    def test_password_reset_source_limit_allows_eight_then_generic_redirects(self):
        mail.outbox = []
        responses = [
            self.reset_post(self.client, f"unknown-{index}@example.test")
            for index in range(8)
        ]
        for response in responses:
            self.assertRedirects(response, reverse("password_reset_done"))

        ninth = self.reset_post(self.client, "unknown-ninth@example.test")
        self.assertRedirects(ninth, reverse("password_reset_done"))
        self.assertEqual(ninth.status_code, 302)
        self.assertEqual(mail.outbox, [])

    @override_settings(SIGNUP_LIMIT=1)
    def test_buyer_signup_source_limit_survives_login_and_logout(self):
        first = self.client.post(
            reverse("register"),
            self.buyer_registration_data("first"),
        )
        self.assertEqual(first.status_code, 302)
        self.assertIn(SOURCE_COOKIE_NAME, self.client.cookies)
        self.client.post(reverse("logout"))

        response = self.client.post(
            reverse("register"),
            self.buyer_registration_data("second"),
        )
        self.assertEqual(response.status_code, 429)
        self.assertContains(response, "Too many registration attempts", status_code=429)
        self.assertTrue(
            get_user_model().objects.filter(username="buyer-limit-first").exists()
        )
        self.assertFalse(
            get_user_model().objects.filter(username="buyer-limit-second").exists()
        )

    @override_settings(SIGNUP_LIMIT=1)
    def test_manufacturer_signup_limit_keeps_profile_policy(self):
        first = self.client.post(
            reverse("register_manufacturer"),
            self.manufacturer_registration_data("first"),
        )
        self.assertEqual(first.status_code, 302)
        self.assertFalse(
            get_user_model().objects.get(username="manufacturer-limit-first")
            .manufacturer_profile.is_verified
        )
        self.client.post(reverse("logout"))

        response = self.client.post(
            reverse("register_manufacturer"),
            self.manufacturer_registration_data("second"),
        )
        self.assertEqual(response.status_code, 429)
        self.assertFalse(
            get_user_model().objects.filter(
                username="manufacturer-limit-second",
            ).exists()
        )

    def test_database_fixed_windows_are_shared_across_clients(self):
        now = datetime(2026, 1, 1, 14, 0, tzinfo=datetime_timezone.utc)
        specification = [("cross_client", "opaque-source", 2, 60)]
        self.assertTrue(consume_rate_limits(specification, now=now).allowed)
        self.assertTrue(
            consume_rate_limits(
                specification,
                now=now + timedelta(seconds=1),
            ).allowed
        )
        self.assertFalse(
            consume_rate_limits(
                specification,
                now=now + timedelta(seconds=2),
            ).allowed
        )
        self.assertTrue(
            consume_rate_limits(
                specification,
                now=now + timedelta(seconds=60),
            ).allowed
        )

    @override_settings(SESSION_COOKIE_SECURE=True)
    def test_source_cookie_is_signed_secure_http_only_and_browser_scoped(self):
        first, second = Client(), Client()
        self.login_post(first, "first@example.test", password="Wrong-Password@4821")
        self.login_post(second, "second@example.test", password="Wrong-Password@4821")
        first_cookie = first.cookies[SOURCE_COOKIE_NAME]
        second_cookie = second.cookies[SOURCE_COOKIE_NAME]

        self.assertNotEqual(first_cookie.value, second_cookie.value)
        self.assertTrue(first_cookie["httponly"])
        self.assertTrue(first_cookie["secure"])
        self.assertEqual(first_cookie["samesite"], "Lax")

    def test_login_identifiers_are_pseudonymized_and_normalized_consistently(self):
        self.assertEqual(
            login_identifier_digest("  PERSON@EXAMPLE.TEST "),
            login_identifier_digest("person@example.test"),
        )
        self.assertNotEqual(
            login_identifier_digest("CaseSensitiveUser"),
            login_identifier_digest("casesensitiveuser"),
        )

        user = self.create_user("private-user", "private@example.test")
        self.login_post(
            Client(),
            user.email,
            password="Wrong-Password@4821",
        )
        bucket = self.current_identifier_bucket(user.email).get()
        self.assertEqual(len(bucket.key_digest), 64)
        self.assertNotIn(user.email, bucket.key_digest)
        self.assertNotIn("Wrong-Password@4821", repr(bucket))

    def test_prune_command_is_idempotent_and_preserves_current_windows(self):
        now = datetime(2026, 1, 1, 14, 20, tzinfo=datetime_timezone.utc)
        current_window = _fixed_window_start(now, project_settings.SIGNUP_WINDOW_SECONDS)
        old_window = current_window - timedelta(
            seconds=project_settings.SIGNUP_WINDOW_SECONDS,
        )
        old = AuthRateLimitBucket.objects.create(
            scope="signup_source",
            key_digest="f" * 64,
            window_start=old_window,
            count=1,
        )
        current = AuthRateLimitBucket.objects.create(
            scope="signup_source",
            key_digest="e" * 64,
            window_start=current_window,
            count=1,
        )
        with patch("accounts.management.commands.prune_auth_throttles.timezone.now", return_value=now):
            call_command("prune_auth_throttles", verbosity=0)
            call_command("prune_auth_throttles", verbosity=0)

        self.assertFalse(AuthRateLimitBucket.objects.filter(pk=old.pk).exists())
        self.assertTrue(AuthRateLimitBucket.objects.filter(pk=current.pk).exists())
