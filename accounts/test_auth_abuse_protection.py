from datetime import timedelta

from django.conf import settings as project_settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.core import signing
from django.core.management import call_command
from django.http import HttpResponse, QueryDict
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from axes.helpers import get_query_str
from axes.models import AccessAttempt, AccessAttemptExpiration

from .models import AuthRateLimitBucket
from .rate_limits import (
    SOURCE_COOKIE_NAME,
    SOURCE_COOKIE_SALT,
    _digest,
    _fixed_window_start,
    axes_username_digest,
    consume_rate_limits,
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

    def test_login_failures_share_identifier_limit_across_clients(self):
        user = self.create_user("limited-buyer", "limited@example.test")
        clients = (Client(), Client())

        for index in range(project_settings.AUTH_LOGIN_LIMIT - 1):
            response = self.login_post(
                clients[index % 2],
                "LIMITED@EXAMPLE.TEST",
                password="Wrong-Password@4821",
            )
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Please enter a correct email or username")

        response = self.login_post(
            clients[1],
            "limited@example.test",
            password="Wrong-Password@4821",
        )
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response["Retry-After"], str(project_settings.AUTH_LOGIN_WINDOW_SECONDS))
        self.assertContains(response, "Too many sign-in attempts", status_code=429)
        user.refresh_from_db()
        self.assertTrue(user.is_active)

        attempt = AccessAttempt.objects.get()
        self.assertNotIn(user.email, attempt.username)
        self.assertNotIn(self.password, attempt.post_data)
        self.assertNotIn("limited@example.test", attempt.post_data)

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

    def test_login_errors_are_generic_and_success_clears_email_identifier(self):
        user = self.create_user("generic-login", "generic@example.test")
        known = self.login_post(
            self.client,
            user.username,
            password="Incorrect-Password@4821",
        )
        unknown = self.login_post(
            Client(),
            "not-a-real-account@example.test",
            password="Incorrect-Password@4821",
        )
        self.assertContains(known, "Please enter a correct email or username")
        self.assertContains(unknown, "Please enter a correct email or username")

        email_client = Client()
        for _ in range(project_settings.AUTH_LOGIN_LIMIT - 1):
            self.login_post(
                email_client,
                "GENERIC@EXAMPLE.TEST",
                password="Incorrect-Password@4821",
            )
        success = self.login_post(email_client, "generic@example.test")
        self.assertEqual(success.status_code, 302)
        digest = axes_username_digest(None, {"username": user.email})
        self.assertFalse(AccessAttempt.objects.filter(username=digest).exists())

    def test_unknown_identifier_gets_same_temporary_lockout_response(self):
        user = self.create_user("known-lockout", "known-lockout@example.test")
        known_client, unknown_client = Client(), Client()
        responses = []
        for client, identifier in (
            (known_client, user.username),
            (unknown_client, "unknown-lockout@example.test"),
        ):
            for _ in range(project_settings.AUTH_LOGIN_LIMIT):
                response = self.login_post(
                    client,
                    identifier,
                    password="Incorrect-Password@4821",
                )
            responses.append(response)

        self.assertEqual([response.status_code for response in responses], [429, 429])
        self.assertContains(responses[0], "Too many sign-in attempts", status_code=429)
        self.assertContains(responses[1], "Too many sign-in attempts", status_code=429)
        self.assertEqual(responses[0].content, responses[1].content)

    def test_login_throttle_expires_and_does_not_disable_user(self):
        user = self.create_user("expiring-login", "expiring@example.test")
        for _ in range(project_settings.AUTH_LOGIN_LIMIT):
            response = self.login_post(
                self.client,
                user.username,
                password="Incorrect-Password@4821",
            )
        self.assertEqual(response.status_code, 429)

        old_time = timezone.now() - timedelta(
            seconds=project_settings.AUTH_LOGIN_WINDOW_SECONDS + 2,
        )
        attempt = AccessAttempt.objects.get()
        attempt.attempt_time = old_time
        attempt.save(update_fields=["attempt_time"])
        AccessAttemptExpiration.objects.filter(
            access_attempt=attempt,
        ).update(expires_at=old_time)

        success = self.login_post(self.client, user.username)
        self.assertEqual(success.status_code, 302)
        user.refresh_from_db()
        self.assertTrue(user.is_active)

    def test_unrelated_login_identifier_remains_available(self):
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

    def test_admin_login_is_throttled_and_valid_admin_can_sign_in(self):
        admin = self.create_user(
            "admin-login-fixture",
            "admin-login@example.test",
            is_staff=True,
            is_superuser=True,
        )
        response = self.login_post(
            self.client,
            admin.username,
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
        for _ in range(project_settings.AUTH_LOGIN_LIMIT):
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

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_password_reset_is_generic_and_shared_limit_stops_email_sends(self):
        mail.outbox = []
        user = self.create_user("reset-fixture", "Reset@Example.Test")
        first_client = Client()
        second_client = Client()

        for client, email in (
            (first_client, "RESET@example.test"),
            (second_client, "reset@EXAMPLE.TEST"),
            (first_client, "reset@example.test"),
        ):
            response = self.reset_post(client, email)
            self.assertRedirects(response, reverse("password_reset_done"))

        sent_count = len(mail.outbox)
        self.assertEqual(sent_count, project_settings.PASSWORD_RESET_LIMIT)

        throttled = self.reset_post(second_client, "RESET@example.test")
        self.assertRedirects(throttled, reverse("password_reset_done"))
        self.assertEqual(
            len(mail.outbox),
            sent_count,
        )

        unknown = self.reset_post(Client(), "unknown@example.test")
        self.assertRedirects(unknown, reverse("password_reset_done"))
        self.assertEqual(unknown.status_code, throttled.status_code)
        self.assertEqual(unknown["Location"], throttled["Location"])
        user.refresh_from_db()
        self.assertTrue(user.is_active)

        buckets = AuthRateLimitBucket.objects.filter(
            scope="password_reset_email",
        )
        self.assertEqual(buckets.count(), 2)
        for bucket in buckets:
            self.assertNotIn(user.email, bucket.key_digest)

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

    def test_database_window_expiry_and_cross_client_persistence(self):
        now = timezone.now().replace(second=0, microsecond=0)
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

    def test_source_limit_cookie_is_signed_and_record_is_only_digest(self):
        marker = "deterministic-browser-source"
        signed_response = HttpResponse()
        signed_response.set_signed_cookie(
            SOURCE_COOKIE_NAME,
            marker,
            salt=SOURCE_COOKIE_SALT,
        )
        cookie_value = signed_response.cookies[SOURCE_COOKIE_NAME].value
        client_a, client_b = Client(), Client()
        client_a.cookies[SOURCE_COOKIE_NAME] = cookie_value
        client_b.cookies[SOURCE_COOKIE_NAME] = cookie_value

        data = self.buyer_registration_data("cookie-source")
        # The same browser marker is recognized across independent clients.
        client_a.get(reverse("register"))
        client_b.get(reverse("register"))
        bucket = AuthRateLimitBucket.objects.create(
            scope="signup_source",
            key_digest=_digest("signup_source", marker),
            window_start=_fixed_window_start(
                timezone.now(),
                project_settings.SIGNUP_WINDOW_SECONDS,
            ),
            count=project_settings.SIGNUP_LIMIT,
        )
        response = client_b.post(reverse("register"), data)
        self.assertEqual(response.status_code, 429)
        self.assertNotIn(marker, bucket.key_digest)

    def test_axes_request_diagnostics_mask_credentials_and_tokens(self):
        query = QueryDict(
            "username=private%40example.test"
            "&email=private%40example.test"
            "&password=fixture-password"
            "&csrfmiddlewaretoken=fixture-csrf-token"
            "&reset_token=fixture-reset-token"
            "&session_key=fixture-session-key"
        )
        diagnostic = get_query_str(query)
        for secret_value in (
            "private@example.test",
            "fixture-password",
            "fixture-csrf-token",
            "fixture-reset-token",
            "fixture-session-key",
        ):
            self.assertNotIn(secret_value, diagnostic)

    def test_prune_command_removes_expired_rate_windows(self):
        old_window = timezone.now() - timedelta(days=2)
        AuthRateLimitBucket.objects.create(
            scope="expired",
            key_digest="f" * 64,
            window_start=old_window,
            count=1,
        )
        call_command("prune_auth_throttles", verbosity=0)
        self.assertFalse(
            AuthRateLimitBucket.objects.filter(scope="expired").exists()
        )
