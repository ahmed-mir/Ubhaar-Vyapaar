import importlib
import os
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

import config.settings as project_settings
from accounts.forms import ReliablePasswordResetForm


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
    def test_password_reset_post_invokes_custom_sender_for_active_user(self):
        user_model = get_user_model()
        user_model.objects.create_user(
            username="reset-user",
            email="reset-user@example.test",
            password="StrongPass123!",
        )
        original_send_mail = ReliablePasswordResetForm.send_mail

        def send_mail_spy(form, *args, **kwargs):
            return original_send_mail(form, *args, **kwargs)

        with mock.patch.object(
            ReliablePasswordResetForm,
            "send_mail",
            autospec=True,
            side_effect=send_mail_spy,
        ) as send_mail:
            response = self.client.post(
                reverse("password_reset"),
                {"email": "reset-user@example.test"},
            )

        self.assertRedirects(response, reverse("password_reset_done"))
        send_mail.assert_called_once()
        self.assertEqual(len(mail.outbox), 1)

    def test_password_reset_email_contains_reset_url(self):
        user_model = get_user_model()
        user_model.objects.create_user(
            username="reset-url-user",
            email="reset-url-user@example.test",
            password="StrongPass123!",
        )

        response = self.client.post(
            reverse("password_reset"),
            {"email": "reset-url-user@example.test"},
        )

        self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            "Reset your Ubhaar-Vyapaar password",
        )
        self.assertIn("/accounts/password/reset/", mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].from_email, "sender@example.test")

    def test_inactive_users_do_not_receive_password_reset_email(self):
        user_model = get_user_model()
        user_model.objects.create_user(
            username="inactive-reset-user",
            email="inactive-reset-user@example.test",
            password="StrongPass123!",
            is_active=False,
        )

        with mock.patch.object(
            ReliablePasswordResetForm,
            "send_mail",
            autospec=True,
        ) as send_mail:
            response = self.client.post(
                reverse("password_reset"),
                {"email": "inactive-reset-user@example.test"},
            )

        self.assertRedirects(response, reverse("password_reset_done"))
        send_mail.assert_not_called()
        self.assertEqual(len(mail.outbox), 0)

    def test_unknown_email_redirects_without_revealing_account_existence(self):
        with mock.patch.object(
            ReliablePasswordResetForm,
            "send_mail",
            autospec=True,
        ) as send_mail:
            response = self.client.post(
                reverse("password_reset"),
                {"email": "unknown@example.test"},
            )

        self.assertRedirects(response, reverse("password_reset_done"))
        send_mail.assert_not_called()
        self.assertEqual(len(mail.outbox), 0)

    def test_reliable_password_reset_form_does_not_swallow_send_failure(self):
        form = ReliablePasswordResetForm()

        with mock.patch(
            "accounts.forms.EmailMultiAlternatives.send",
            side_effect=RuntimeError("SMTP send failed"),
        ) as send:
            with self.assertRaisesMessage(RuntimeError, "SMTP send failed"):
                form.send_mail(
                    "accounts/password_reset_subject.txt",
                    "accounts/password_reset_email.txt",
                    {
                        "domain": "example.test",
                        "protocol": "https",
                        "uid": "uid",
                        "token": "token",
                    },
                    None,
                    "reset-user@example.test",
                )

        send.assert_called_once_with(fail_silently=False)

    def test_password_reset_confirm_and_complete_flow_still_works(self):
        user_model = get_user_model()
        user = user_model.objects.create_user(
            username="confirm-reset-user",
            email="confirm-reset-user@example.test",
            password="StrongPass123!",
        )
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        response = self.client.get(
            reverse(
                "password_reset_confirm",
                kwargs={"uidb64": uid, "token": token},
            )
        )
        self.assertEqual(response.status_code, 302)

        response = self.client.post(
            response["Location"],
            {
                "new_password1": "NewStrongPass123!",
                "new_password2": "NewStrongPass123!",
            },
        )

        self.assertRedirects(response, reverse("password_reset_complete"))
        user.refresh_from_db()
        self.assertTrue(user.check_password("NewStrongPass123!"))

        response = self.client.get(reverse("password_reset_complete"))

        self.assertEqual(response.status_code, 200)


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
        self.assertContains(response, 'aria-invalid="true"')
        self.assertContains(response, 'id_legal_acknowledgement_error')
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
        self.assertContains(response, 'aria-required="true"')
        self.assertNotContains(response, 'name="marketing_consent"')
        self.assertNotContains(response, 'checked="checked"')
