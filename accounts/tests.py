import importlib
import os
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings
from django.urls import reverse

import config.settings as project_settings


class EmailSettingsTests(TestCase):
    def reload_settings(self, env):
        with mock.patch.dict(os.environ, env, clear=False):
            return importlib.reload(project_settings)

    def tearDown(self):
        importlib.reload(project_settings)
        super().tearDown()

    def test_console_backend_is_default_for_local_safety(self):
        settings = self.reload_settings(
            {
                "DJANGO_DEBUG": "True",
                "DJANGO_EMAIL_BACKEND": "",
                "EMAIL_HOST": "",
                "EMAIL_PORT": "",
                "EMAIL_USE_TLS": "",
            }
        )

        self.assertEqual(
            settings.EMAIL_BACKEND,
            "django.core.mail.backends.console.EmailBackend",
        )

    def test_smtp_email_settings_are_loaded_from_environment(self):
        settings = self.reload_settings(
            {
                "DJANGO_DEBUG": "False",
                "DJANGO_USE_CLOUDINARY_MEDIA": "False",
                "DJANGO_EMAIL_BACKEND": (
                    "django.core.mail.backends.smtp.EmailBackend"
                ),
                "EMAIL_HOST": "smtp-host-from-env",
                "EMAIL_PORT": "587",
                "EMAIL_HOST_USER": "smtp-login-from-env",
                "EMAIL_HOST_PASSWORD": "smtp-secret-from-env",
                "EMAIL_USE_TLS": "True",
                "DEFAULT_FROM_EMAIL": "sender@example.test",
                "SERVER_EMAIL": "server@example.test",
            }
        )

        self.assertEqual(
            settings.EMAIL_BACKEND,
            "django.core.mail.backends.smtp.EmailBackend",
        )
        self.assertEqual(settings.EMAIL_HOST, "smtp-host-from-env")
        self.assertEqual(settings.EMAIL_PORT, 587)
        self.assertEqual(settings.EMAIL_HOST_USER, "smtp-login-from-env")
        self.assertEqual(settings.EMAIL_HOST_PASSWORD, "smtp-secret-from-env")
        self.assertIs(settings.EMAIL_USE_TLS, True)
        self.assertEqual(settings.DEFAULT_FROM_EMAIL, "sender@example.test")
        self.assertEqual(settings.SERVER_EMAIL, "server@example.test")

    def test_invalid_email_port_is_rejected(self):
        with self.assertRaises(ImproperlyConfigured):
            self.reload_settings(
                {
                    "DJANGO_DEBUG": "True",
                    "EMAIL_PORT": "not-a-port",
                }
            )

    def test_invalid_email_tls_boolean_is_rejected(self):
        with self.assertRaises(ImproperlyConfigured):
            self.reload_settings(
                {
                    "DJANGO_DEBUG": "True",
                    "EMAIL_USE_TLS": "sometimes",
                }
            )


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="sender@example.test",
)
class PasswordResetEmailTests(TestCase):
    def test_password_reset_view_renders_and_queues_local_email(self):
        user_model = get_user_model()
        user_model.objects.create_user(
            username="reset-user",
            email="reset-user@example.test",
            password="StrongPass123!",
        )

        response = self.client.post(
            reverse("password_reset"),
            {"email": "reset-user@example.test"},
        )

        self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            "Reset your Ubhaar-Vyapaar password",
        )
        self.assertIn("/accounts/password/reset/", mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].from_email, "sender@example.test")


class RegistrationConsentTests(TestCase):
    def test_buyer_registration_requires_legal_acknowledgement(self):
        response = self.client.post(
            reverse("register"),
            {
                "username": "buyer-one",
                "email": "buyer@example.test",
                "phone": "",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Please agree to the Terms &amp; Conditions",
        )
        self.assertFalse(
            get_user_model().objects.filter(username="buyer-one").exists()
        )

    def test_buyer_registration_records_policy_versions(self):
        response = self.client.post(
            reverse("register"),
            {
                "username": "buyer-two",
                "email": "buyer-two@example.test",
                "phone": "",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
                "legal_acknowledgement": "on",
            },
        )

        self.assertRedirects(response, reverse("home"))
        user = get_user_model().objects.get(username="buyer-two")
        self.assertIsNotNone(user.terms_accepted_at)
        self.assertIsNotNone(user.privacy_acknowledged_at)
        self.assertEqual(user.terms_version, project_settings.TERMS_VERSION)
        self.assertEqual(
            user.privacy_policy_version,
            project_settings.PRIVACY_POLICY_VERSION,
        )

    def test_registration_page_links_policies_and_has_no_marketing_consent(self):
        response = self.client.get(reverse("register"))

        self.assertContains(response, reverse("terms"))
        self.assertContains(response, reverse("privacy_policy"))
        self.assertContains(response, 'name="legal_acknowledgement"')
        self.assertNotContains(response, 'name="marketing_consent"')
        self.assertNotContains(response, 'checked="checked"')
