from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model


class AuthPresentationTests(TestCase):
    def test_registration_autocomplete_hints_and_consent_are_present(self):
        for route in ("register", "register_manufacturer"):
            with self.subTest(route=route):
                response = self.client.get(reverse(route))
                self.assertContains(response, 'autocomplete="username"')
                self.assertContains(response, 'autocomplete="email"')
                self.assertContains(response, 'autocomplete="tel"')
                self.assertContains(response, 'autocomplete="new-password"')
                self.assertContains(response, 'name="legal_acknowledgement"')
                self.assertNotContains(response, 'name="legal_acknowledgement" checked')

    def test_password_change_requires_login(self):
        response = self.client.get(reverse("password_change"))
        self.assertRedirects(response, reverse("login") + "?next=" + reverse("password_change"))

    def test_password_change_preserves_authenticated_session(self):
        user = get_user_model().objects.create_user(username="change-test", password="OldPass-strong-42!")
        self.client.force_login(user)
        response = self.client.post(reverse("password_change"), {
            "old_password": "OldPass-strong-42!",
            "new_password1": "NewPass-strong-73!",
            "new_password2": "NewPass-strong-73!",
        })
        self.assertRedirects(response, reverse("password_change_done"))
        user.refresh_from_db()
        self.assertTrue(user.check_password("NewPass-strong-73!"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)
