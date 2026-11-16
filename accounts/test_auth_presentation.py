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


class AccountMenuPresentationTests(TestCase):
    def test_buyer_account_menu_shows_identity_role_and_buyer_destinations(self):
        user = get_user_model().objects.create_user(
            username="buyer-menu-user",
            first_name="Ahmed",
            password="StrongPass123!",
            role="BUYER",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("marketplace"))

        self.assertContains(response, 'data-account-menu-trigger')
        self.assertContains(response, "Ahmed")
        self.assertContains(response, "Buyer")
        self.assertContains(response, reverse("buyer_dashboard"))
        self.assertContains(response, reverse("saved_listings"))
        self.assertContains(response, reverse("password_change"))
        self.assertContains(response, 'action="/accounts/logout/"')
        self.assertContains(response, 'method="post"')
        self.assertContains(response, 'name="csrfmiddlewaretoken"')

    def test_manufacturer_account_menu_shows_identity_role_and_listing_destination(self):
        user = get_user_model().objects.create_user(
            username="manufacturer-menu-user",
            first_name="Aarav Works",
            password="StrongPass123!",
            role="MANUFACTURER",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("marketplace"))

        self.assertContains(response, "Aarav Works")
        self.assertContains(response, "Manufacturer")
        self.assertContains(response, reverse("manufacturer_dashboard"))
        self.assertContains(response, reverse("my_listings"))
        self.assertContains(response, reverse("password_change"))

    def test_anonymous_navigation_does_not_render_account_menu(self):
        response = self.client.get(reverse("marketplace"))

        self.assertNotContains(response, 'class="account-menu"')
        self.assertContains(response, reverse("login"))

    def test_logout_remains_post_only(self):
        user = get_user_model().objects.create_user(
            username="secure-logout-menu-user",
            password="StrongPass123!",
            role="BUYER",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("logout"))

        self.assertEqual(response.status_code, 405)
        self.assertEqual(self.client.session.get("_auth_user_id"), str(user.pk))
