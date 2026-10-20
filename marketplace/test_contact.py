from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .forms import ContactSubmissionForm
from .models import ContactSubmission


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class ContactSubmissionTests(TestCase):
    def assert_contact_redirect(self, response):
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("contact"))

    def payload(self, **overrides):
        values = {
            "name": "Asha Buyer",
            "email": "asha@example.test",
            "role": "BUYER",
            "message": "I have a question about the marketplace.",
        }
        values.update(overrides)
        return values

    def test_contact_page_renders_accessible_post_form(self):
        response = self.client.get(reverse("contact"))
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(html.count("<h1"), 1)
        self.assertContains(response, '<form method="post"')
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertContains(response, 'autocomplete="name"')
        self.assertContains(response, 'autocomplete="email"')
        self.assertContains(response, 'aria-hidden="true"')
        self.assertContains(response, "We use the information you submit")
        self.assertContains(response, reverse("privacy_policy"))
        self.assertNotContains(response, 'name="marketing_consent"')
        self.assertNotContains(response, 'name="newsletter"')

    def test_form_validates_email_required_fields_role_and_message_length(self):
        valid = ContactSubmissionForm(self.payload())
        self.assertTrue(valid.is_valid(), valid.errors)

        invalid_cases = (
            {"email": "not-an-email"},
            {"name": ""},
            {"message": ""},
            {"role": "ADMIN"},
            {"message": "x" * 5001},
        )
        for changes in invalid_cases:
            with self.subTest(changes=tuple(changes)):
                form = ContactSubmissionForm(self.payload(**changes))
                self.assertFalse(form.is_valid())

    @override_settings(LEGAL_CONTACT_EMAIL="")
    def test_valid_post_saves_once_redirects_and_does_not_need_email_recipient(self):
        response = self.client.post(reverse("contact"), self.payload())

        self.assert_contact_redirect(response)
        self.assertEqual(ContactSubmission.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 0)

        success = self.client.get(response.url)
        self.assertContains(success, "Your message has been received.")
        self.client.get(response.url)
        self.assertEqual(ContactSubmission.objects.count(), 1)

    def test_invalid_post_shows_associated_errors_without_saving(self):
        response = self.client.post(
            reverse("contact"),
            self.payload(email="bad-address"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ContactSubmission.objects.count(), 0)
        self.assertContains(response, 'aria-invalid="true"')
        self.assertContains(response, 'aria-describedby="id_email_error')
        self.assertContains(response, 'id="id_email_error"')

    @override_settings(LEGAL_CONTACT_EMAIL="")
    def test_post_requires_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        page = client.get(reverse("contact"))
        self.assertEqual(page.status_code, 200)
        csrf_token = client.cookies["csrftoken"].value

        missing_token = client.post(reverse("contact"), self.payload())
        self.assertEqual(missing_token.status_code, 403)
        self.assertEqual(ContactSubmission.objects.count(), 0)

        valid_post = client.post(
            reverse("contact"),
            self.payload(),
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(valid_post.status_code, 302)
        self.assertEqual(ContactSubmission.objects.count(), 1)

    @override_settings(LEGAL_CONTACT_EMAIL="support@contact.example.com")
    def test_notification_uses_configured_recipient_and_contains_submission(self):
        response = self.client.post(reverse("contact"), self.payload())

        self.assert_contact_redirect(response)
        self.assertEqual(ContactSubmission.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        notification = mail.outbox[0]
        self.assertEqual(notification.to, ["support@contact.example.com"])
        self.assertEqual(notification.reply_to, ["asha@example.test"])
        self.assertIn("Asha Buyer", notification.body)
        self.assertIn("asha@example.test", notification.body)
        self.assertIn("Buyer", notification.body)
        self.assertIn("I have a question about the marketplace.", notification.body)
        self.assertIn("Submitted:", notification.body)
        self.assertIn("/admin/marketplace/contactsubmission/1/change/", notification.body)

    @override_settings(
        LEGAL_CONTACT_EMAIL="support@contact.example.com",
        SENTRY_ENABLED=False,
    )
    def test_notification_failure_keeps_submission_and_shows_neutral_success(self):
        with self.assertLogs("marketplace.views", level="ERROR") as captured:
            with patch(
                "marketplace.views.EmailMessage.send",
                side_effect=OSError("SMTP credentials must not reach the user"),
            ):
                response = self.client.post(reverse("contact"), self.payload())

        self.assert_contact_redirect(response)
        self.assertEqual(ContactSubmission.objects.count(), 1)
        logged = "\n".join(captured.output)
        self.assertIn("submission id=1", logged)
        self.assertNotIn("asha@example.test", logged)
        self.assertNotIn("I have a question about the marketplace", logged)
        success = self.client.get(response.url)
        self.assertContains(success, "Your message has been received.")
        self.assertNotContains(success, "SMTP credentials")

    def test_filled_honeypot_does_not_save_or_send_notification(self):
        response = self.client.post(
            reverse("contact"),
            self.payload(company_website="https://spam.example"),
        )

        self.assert_contact_redirect(response)
        self.assertEqual(ContactSubmission.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)
        self.assertContains(self.client.get(response.url), "Your message has been received.")

    @override_settings(LEGAL_CONTACT_EMAIL="")
    def test_session_throttle_allows_five_and_blocks_the_sixth_submission(self):
        for _ in range(5):
            response = self.client.post(reverse("contact"), self.payload())
            self.assert_contact_redirect(response)

        limited = self.client.post(reverse("contact"), self.payload())
        self.assertEqual(limited.status_code, 429)
        self.assertContains(
            limited,
            "Please try again later before sending another message.",
            status_code=429,
        )
        self.assertEqual(ContactSubmission.objects.count(), 5)

    @override_settings(
        LEGAL_ENTITY_NAME="Ubhaar Trade Services",
        LEGAL_CONTACT_EMAIL="support@contact.example.com",
        LEGAL_CONTACT_LABEL="Support email",
    )
    def test_configured_contact_details_render_and_admin_can_triage_submission(self):
        page = self.client.get(reverse("contact"))
        self.assertContains(page, "Ubhaar Trade Services")
        self.assertContains(page, "support@contact.example.com")

        submission = ContactSubmission.objects.create(
            **{
                **self.payload(),
                "message": "<script>alert(1)</script>",
            }
        )
        User = get_user_model()
        admin_user = User.objects.create_superuser(
            username="contact-admin",
            email="contact-admin@example.test",
            password="strong-password",
            role="BUYER",
        )
        self.client.force_login(admin_user)
        admin_page = self.client.get(
            reverse("admin:marketplace_contactsubmission_change", args=[submission.pk])
        )
        self.assertEqual(admin_page.status_code, 200)
        self.assertContains(admin_page, "&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertNotIn("<script>alert(1)</script>", admin_page.content.decode())


class ContactSubmissionPrivacyTests(TestCase):
    def test_privacy_policy_covers_contact_data_and_no_specific_retention_period(self):
        response = self.client.get(reverse("privacy_policy"))
        self.assertContains(response, "Contact enquiries: name, email address, role, and message")
        self.assertContains(response, "contact-submission records may be retained")
        self.assertContains(response, "does not set a specific retention period")
