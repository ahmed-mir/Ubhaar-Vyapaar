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
    def test_password_reset_post_uses_django_send_mail_for_active_user(self):
        user_model = get_user_model()
        user_model.objects.create_user(
            username="reset-user",
            email="reset-user@example.test",
            password="StrongPass123!",
        )

        with mock.patch("accounts.forms.send_mail", return_value=1) as send:
            response = self.client.post(
                reverse("password_reset"),
                {"email": "reset-user@example.test"},
            )

        self.assertRedirects(response, reverse("password_reset_done"))
        send.assert_called_once()
        self.assertEqual(
            send.call_args.kwargs["recipient_list"],
            ["reset-user@example.test"],
        )
        self.assertEqual(
            send.call_args.kwargs["from_email"],
            "sender@example.test",
        )
        self.assertFalse(send.call_args.kwargs["fail_silently"])

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

        with mock.patch("accounts.forms.logger.exception") as logger_exception:
            with mock.patch(
                "accounts.forms.send_mail",
                side_effect=RuntimeError("SMTP send failed"),
            ) as send_mock:
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

        send_mock.assert_called_once()
        self.assertFalse(send_mock.call_args.kwargs["fail_silently"])
        logger_exception.assert_called_once_with(
            "Password reset email delivery failed."
        )

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
    @override_settings(ALLOW_INDEXING=True)
    def test_get_started_chooser_links_to_existing_registration_routes(self):
        response = self.client.get(reverse("get_started"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("register"))
        self.assertContains(response, reverse("register_manufacturer"))
        self.assertContains(response, 'name="robots" content="noindex,follow"')
        self.assertEqual(response.content.count(b"<h1"), 1)

    def test_buyer_registration_fields_and_username_sign_in_remain_unchanged(self):
        response = self.client.get(reverse("register"))
        for field_name in (
            "username", "email", "phone", "password1", "password2",
            "legal_acknowledgement",
        ):
            self.assertContains(response, f'name="{field_name}"')
        self.assertContains(response, "Your username is used to sign in")

        response = self.client.post(
            reverse("register"),
            {
                "username": "buyer-login-check",
                "email": "buyer-login-check@example.test",
                "phone": "",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
                "legal_acknowledgement": "on",
            },
            follow=True,
        )

        self.assertEqual(response.redirect_chain[-1][0], reverse("home"))
        user = get_user_model().objects.get(username="buyer-login-check")
        self.assertEqual(user.role, get_user_model().Role.BUYER)
        self.assertTrue(user.check_password("StrongPass123!"))
        self.assertEqual(str(self.client.session.get("_auth_user_id")), str(user.pk))
        self.assertContains(response, "Your buyer account is ready")
        self.client.logout()
        login_response = self.client.post(
            reverse("login"),
            {"username": "buyer-login-check", "password": "StrongPass123!"},
        )
        self.assertRedirects(login_response, reverse("home"))

    def test_manufacturer_registration_keeps_profile_state_and_redirect(self):
        response = self.client.get(reverse("register_manufacturer"))
        self.assertEqual(response.status_code, 200)
        for field_name in (
            "username", "email", "phone", "business_name", "description",
            "city", "state", "password1", "password2", "legal_acknowledgement",
        ):
            self.assertContains(response, f'name="{field_name}"')

        response = self.client.post(
            reverse("register_manufacturer"),
            {
                "username": "manufacturer-onboarding-check",
                "email": "manufacturer-check@example.test",
                "phone": "",
                "business_name": "Check Works",
                "description": "Capacity for small batches.",
                "city": "Pune",
                "state": "Maharashtra",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
                "legal_acknowledgement": "on",
            },
            follow=True,
        )

        self.assertEqual(
            response.redirect_chain[-1][0], reverse("manufacturer_dashboard")
        )
        user = get_user_model().objects.get(username="manufacturer-onboarding-check")
        profile = user.manufacturer_profile
        self.assertEqual(user.role, get_user_model().Role.MANUFACTURER)
        self.assertFalse(profile.is_verified)
        self.assertEqual(profile.kyc_status, "UNDER_REVIEW")
        self.assertContains(response, "Your manufacturer account is ready")

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


class EmailOrUsernameAuthenticationTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()

    def create_user(self, username, email, **kwargs):
        return self.user_model.objects.create_user(
            username=username,
            email=email,
            password="StrongPass123!",
            **kwargs,
        )

    def test_buyer_and_manufacturer_username_login_are_preserved(self):
        buyer = self.create_user(
            "buyer-username-login",
            "buyer-username-login@example.test",
            role=self.user_model.Role.BUYER,
        )
        manufacturer = self.create_user(
            "manufacturer-username-login",
            "manufacturer-username-login@example.test",
            role=self.user_model.Role.MANUFACTURER,
        )

        self.assertTrue(
            self.client.login(
                username=buyer.username,
                password="StrongPass123!",
            )
        )
        self.assertEqual(str(self.client.session["_auth_user_id"]), str(buyer.pk))
        self.client.logout()

        self.assertTrue(
            self.client.login(
                username=manufacturer.username,
                password="StrongPass123!",
            )
        )
        self.assertEqual(
            str(self.client.session["_auth_user_id"]),
            str(manufacturer.pk),
        )

    def test_email_login_is_case_insensitive_and_requires_correct_password(self):
        user = self.create_user("email-login-user", "Case@Test.Example")

        self.assertTrue(
            self.client.login(
                username="  CASE@test.example  ",
                password="StrongPass123!",
            )
        )
        self.assertEqual(str(self.client.session["_auth_user_id"]), str(user.pk))
        self.client.logout()

        self.assertFalse(
            self.client.login(
                username="case@test.example",
                password="WrongPassword123!",
            )
        )

    def test_inactive_user_and_blank_identifier_fail_safely(self):
        self.create_user(
            "inactive-email-user",
            "inactive@example.test",
            is_active=False,
        )

        for identifier in ("inactive-email-user", "inactive@example.test", ""):
            self.assertFalse(
                self.client.login(
                    username=identifier,
                    password="StrongPass123!",
                )
            )

    def test_duplicate_email_fails_generically_but_each_username_still_works(self):
        first = self.create_user("duplicate-email-one", "shared@example.test")
        second = self.create_user("duplicate-email-two", "SHARED@example.test")

        duplicate_response = self.client.post(
            reverse("login"),
            {"username": "shared@example.test", "password": "StrongPass123!"},
        )
        self.assertEqual(duplicate_response.status_code, 200)
        self.assertContains(
            duplicate_response,
            "Please enter a correct email or username and password.",
        )
        self.assertNotIn("_auth_user_id", self.client.session)

        wrong_response = self.client.post(
            reverse("login"),
            {"username": "unknown@example.test", "password": "WrongPassword123!"},
        )
        self.assertContains(
            wrong_response,
            "Please enter a correct email or username and password.",
        )

        for user in (first, second):
            self.assertTrue(
                self.client.login(
                    username=user.username,
                    password="StrongPass123!",
                )
            )
            self.assertEqual(
                str(self.client.session["_auth_user_id"]),
                str(user.pk),
            )
            self.client.logout()

    def test_staff_and_superuser_can_authenticate_with_username_in_admin(self):
        staff = self.create_user(
            "staff-username-login",
            "staff@example.test",
            is_staff=True,
        )
        superuser = self.user_model.objects.create_superuser(
            username="superuser-username-login",
            email="superuser@example.test",
            password="StrongPass123!",
        )

        for user in (staff, superuser):
            self.assertTrue(
                self.client.login(
                    username=user.username,
                    password="StrongPass123!",
                )
            )
            response = self.client.get("/admin/")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                str(self.client.session["_auth_user_id"]),
                str(user.pk),
            )
            self.client.logout()

    def test_login_form_keeps_post_name_and_has_neutral_email_or_username_label(self):
        response = self.client.get(reverse("login"))

        self.assertContains(response, 'name="username"')
        self.assertContains(response, "Email or username")
        self.assertNotContains(response, 'name="email"')

    def test_login_keeps_safe_next_redirect_and_rejects_external_destination(self):
        self.create_user("safe-next-login", "safe-next-login@example.test")

        safe_response = self.client.post(
            reverse("login"),
            {
                "username": "safe-next-login",
                "password": "StrongPass123!",
                "next": reverse("buyer_dashboard"),
            },
        )
        self.assertRedirects(
            safe_response,
            reverse("buyer_dashboard"),
            fetch_redirect_response=False,
        )

        self.client.logout()
        unsafe_response = self.client.post(
            reverse("login"),
            {
                "username": "safe-next-login",
                "password": "StrongPass123!",
                "next": "https://example.invalid/",
            },
        )
        self.assertRedirects(
            unsafe_response,
            reverse("home"),
            fetch_redirect_response=False,
        )
