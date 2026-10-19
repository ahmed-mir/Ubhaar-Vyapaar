from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class StyleguideAccessTests(TestCase):
    def test_styleguide_is_staff_only_and_noindex(self):
        url = reverse("styleguide")
        self.assertEqual(self.client.get(url).status_code, 302)

        User = get_user_model()
        user = User.objects.create_user(username="styleguide-user", password="test-pass")
        self.client.force_login(user)
        self.assertEqual(self.client.get(url).status_code, 302)

        user.is_staff = True
        user.save(update_fields=["is_staff"])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="robots" content="noindex,nofollow"')
        self.assertContains(response, "Machine specification")
