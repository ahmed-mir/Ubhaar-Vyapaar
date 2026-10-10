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
