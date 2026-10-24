from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .forms import WaitlistEntryForm
from .models import WaitlistEntry


class WaitlistFormTests(TestCase):
    def payload(self, **overrides):
        values = {
            "email": "Asha@Example.test",
            "role": WaitlistEntry.Role.BUYER,
            "note": "Looking for packaging capacity.",
        }
        values.update(overrides)
        return values

    def test_form_renders_with_two_roles_optional_note_and_accessible_labels(self):
        response = self.client.get(reverse("home"))
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(html.count("<h1"), 1)
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertContains(response, 'autocomplete="email"')
        self.assertContains(response, "Buyer")
        self.assertContains(response, "Manufacturer")
        self.assertNotContains(response, ">Other</option>")
        self.assertContains(response, 'name="note"')
        self.assertContains(response, 'maxlength="1000"')
        self.assertContains(response, 'aria-hidden="true"')
        self.assertNotContains(response, 'name="marketing_consent"')
        self.assertNotContains(response, 'name="newsletter"')
        self.assertContains(response, 'data-analytics-event="waitlist_submit"')
        self.assertContains(response, "Interested in using Ubhaar-Vyapaar?")
        self.assertContains(response, "Join early access")
        self.assertLess(html.index("Current platform state"), html.index('id="early-access"'))
        for misleading_claim in ("limited spots", "invite only", "join thousands", "launching soon", "guaranteed access"):
            self.assertNotIn(misleading_claim, html.lower())

    def test_form_accepts_valid_email_and_optional_note(self):
        self.assertTrue(WaitlistEntryForm(self.payload(note="")).is_valid())
        self.assertFalse(WaitlistEntryForm(self.payload(email="bad-email")).is_valid())
        self.assertFalse(WaitlistEntryForm(self.payload(role="ADMIN")).is_valid())
        self.assertFalse(WaitlistEntryForm(self.payload(note="x" * 1001)).is_valid())


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class WaitlistSubmissionTests(TestCase):
    def payload(self, **overrides):
        values = {
            "email": "Asha@Example.test",
            "role": WaitlistEntry.Role.BUYER,
            "note": "Interested in packaging.",
        }
        values.update(overrides)
        return values

    def test_valid_post_saves_normalized_entry_and_uses_prg_success(self):
        response = self.client.post(reverse("home"), self.payload())

        self.assertRedirects(response, f"{reverse('home')}#early-access", fetch_redirect_response=False)
        entry = WaitlistEntry.objects.get()
        self.assertEqual(entry.email, "asha@example.test")
        self.assertEqual(entry.role, WaitlistEntry.Role.BUYER)
        self.assertEqual(len(mail.outbox), 0)
        success = self.client.get(reverse("home"))
        self.assertContains(success, "Thanks — your interest has been recorded.")

    def test_invalid_post_creates_no_entry_and_shows_associated_error(self):
        response = self.client.post(reverse("home"), self.payload(email="invalid"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(WaitlistEntry.objects.count(), 0)
        self.assertContains(response, 'aria-invalid="true"')
        self.assertContains(response, 'aria-describedby="id_email_error"')
        self.assertContains(response, 'id="id_email_error"')

    def test_same_normalized_email_and_role_is_neutral_and_not_duplicated(self):
        first = self.client.post(reverse("home"), self.payload())
        second = self.client.post(
            reverse("home"), self.payload(email="asha@example.test")
        )

        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        self.assertEqual(WaitlistEntry.objects.count(), 1)
        self.assertContains(
            self.client.get(reverse("home")),
            "Thanks — your interest has been recorded.",
        )

    def test_same_email_can_join_for_a_different_role(self):
        self.client.post(reverse("home"), self.payload())
        self.client.post(
            reverse("home"), self.payload(role=WaitlistEntry.Role.MANUFACTURER)
        )
        self.assertEqual(WaitlistEntry.objects.count(), 2)

    def test_filled_honeypot_redirects_neutrally_without_saving(self):
        response = self.client.post(
            reverse("home"), self.payload(website="spam.example")
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(WaitlistEntry.objects.count(), 0)
        self.assertContains(
            self.client.get(reverse("home")),
            "Thanks — your interest has been recorded.",
        )

    def test_session_throttle_allows_five_and_blocks_the_sixth(self):
        for index in range(5):
            response = self.client.post(
                reverse("home"),
                self.payload(email=f"buyer{index}@example.test"),
            )
            self.assertEqual(response.status_code, 302)

        limited = self.client.post(
            reverse("home"), self.payload(email="sixth@example.test")
        )
        self.assertEqual(limited.status_code, 429)
        self.assertContains(limited, "Please try again later", status_code=429)
        self.assertEqual(WaitlistEntry.objects.count(), 5)

    def test_post_requires_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        page = client.get(reverse("home"))
        self.assertEqual(page.status_code, 200)
        token = client.cookies["csrftoken"].value
        denied = client.post(reverse("home"), self.payload())
        self.assertEqual(denied.status_code, 403)
        accepted = client.post(
            reverse("home"), self.payload(), HTTP_X_CSRFTOKEN=token
        )
        self.assertEqual(accepted.status_code, 302)
        self.assertEqual(WaitlistEntry.objects.count(), 1)

    def test_admin_supports_email_search_role_filter_and_contact_status(self):
        entry = WaitlistEntry.objects.create(
            email="admin@example.test", role=WaitlistEntry.Role.MANUFACTURER
        )
        from django.contrib.auth import get_user_model

        admin_user = get_user_model().objects.create_superuser(
            username="waitlist-admin",
            email="admin-user@example.test",
            password="strong-password",
        )
        self.client.force_login(admin_user)
        page = self.client.get(
            reverse("admin:marketplace_waitlistentry_change", args=[entry.pk])
        )
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "admin@example.test")
        self.assertContains(page, "is_contacted")


class WaitlistPrivacyTests(TestCase):
    def test_privacy_page_covers_waitlist_use_and_no_retention_period(self):
        response = self.client.get(reverse("privacy_policy"))
        self.assertContains(response, "Early-access interest")
        self.assertContains(response, "not added to a marketing list automatically")
        self.assertContains(response, "Early-access interest records may be retained")
        self.assertContains(response, "does not set a specific retention period")

    def test_waitlist_model_has_no_ip_user_agent_or_marketing_metadata(self):
        field_names = {field.name for field in WaitlistEntry._meta.fields}
        self.assertEqual(
            field_names,
            {"id", "email", "role", "note", "created_at", "is_contacted"},
        )
