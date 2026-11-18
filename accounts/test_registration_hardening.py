from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.conf import settings
from django.contrib.auth.password_validation import (
    CommonPasswordValidator,
    MinimumLengthValidator,
    NumericPasswordValidator,
    UserAttributeSimilarityValidator,
    get_password_validators,
)
from django.db import IntegrityError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from marketplace.models import ManufacturerProfile

from .forms import (
    BuyerRegistrationForm,
    ManufacturerRegistrationForm,
    configured_password_requirements,
)


FAST_HASHER = "django.contrib.auth.hashers.MD5PasswordHasher"
VALID_PASSWORD = "Cobalt-Orbit-752!"
PHONE_ERROR = "Enter a valid phone number containing 8–15 digits."


def registration_data(form_class, suffix, phone=""):
    data = {
        "username": f"signup-{suffix}",
        "email": f"signup-{suffix}@example.test",
        "phone": phone,
        "password1": VALID_PASSWORD,
        "password2": VALID_PASSWORD,
        "legal_acknowledgement": "on",
    }
    if form_class is ManufacturerRegistrationForm:
        data.update(
            {
                "business_name": f"{suffix} Works",
                "description": "Small batch manufacturing capacity.",
                "city": "Pune",
                "state": "Maharashtra",
            }
        )
    return data


@override_settings(PASSWORD_HASHERS=[FAST_HASHER])
class SignupPhoneValidationTests(TestCase):
    def test_phone_is_optional_and_accepts_common_international_formats(self):
        examples = (
            "",
            "9876543210",
            "+919876543210",
            "+91 98765 43210",
            "022 1234 5678",
            "020-12345678",
            "+1 (415) 555-2671",
        )
        for form_class in (BuyerRegistrationForm, ManufacturerRegistrationForm):
            for index, phone in enumerate(examples):
                with self.subTest(form=form_class.__name__, phone=phone):
                    form = form_class(
                        data=registration_data(form_class, f"valid-{index}", phone)
                    )
                    self.assertTrue(form.is_valid(), form.errors)
                    self.assertEqual(form.cleaned_data["phone"], phone.strip())

    def test_both_signup_forms_reject_malformed_phone_server_side(self):
        invalid_numbers = (
            "abcdef",
            "phone123",
            "dsadsaqeqewqwas",
            "abc123",
            "123abc456",
            "12",
            "1234567",
            "1234567890123456",
            "++++++",
        )
        for form_class in (BuyerRegistrationForm, ManufacturerRegistrationForm):
            for index, phone in enumerate(invalid_numbers):
                with self.subTest(form=form_class.__name__, phone=phone):
                    form = form_class(
                        data=registration_data(form_class, f"invalid-{index}", phone)
                    )
                    self.assertFalse(form.is_valid())
                    self.assertEqual(form.errors["phone"], [PHONE_ERROR])

    def test_direct_buyer_post_rejects_arbitrary_phone_and_ignores_role_tampering(self):
        data = registration_data(BuyerRegistrationForm, "direct-buyer-post", "letters")
        data["role"] = "MANUFACTURER"

        response = self.client.post(reverse("register"), data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form"].errors["phone"], [PHONE_ERROR])
        self.assertFalse(
            get_user_model().objects.filter(username=data["username"]).exists()
        )

    def test_direct_manufacturer_post_rejects_arbitrary_phone(self):
        data = registration_data(
            ManufacturerRegistrationForm,
            "direct-manufacturer-post",
            "dsadsaqeqewqwas",
        )
        data["role"] = "BUYER"

        response = self.client.post(reverse("register_manufacturer"), data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form"].errors["phone"], [PHONE_ERROR])
        self.assertFalse(
            get_user_model().objects.filter(username=data["username"]).exists()
        )
        self.assertFalse(
            ManufacturerProfile.objects.filter(user__username=data["username"]).exists()
        )

    def test_phone_is_trimmed_before_storage(self):
        data = registration_data(BuyerRegistrationForm, "trim-phone", "  +91 98765 43210  ")

        response = self.client.post(reverse("register"), data)

        self.assertRedirects(response, reverse("home"))
        user = get_user_model().objects.get(username=data["username"])
        self.assertEqual(user.phone, "+91 98765 43210")


@override_settings(PASSWORD_HASHERS=[FAST_HASHER])
class SignupValidationAndRoleTests(TestCase):
    def test_buyer_signup_sets_buyer_role_and_hashes_password_despite_role_post(self):
        data = registration_data(BuyerRegistrationForm, "trusted-buyer-role")
        data["role"] = "MANUFACTURER"

        response = self.client.post(reverse("register"), data)

        self.assertRedirects(response, reverse("home"))
        user = get_user_model().objects.get(username=data["username"])
        self.assertEqual(user.role, get_user_model().Role.BUYER)
        self.assertTrue(user.check_password(VALID_PASSWORD))
        self.assertNotEqual(user.password, VALID_PASSWORD)
        self.assertEqual(str(self.client.session.get("_auth_user_id")), str(user.pk))

    def test_manufacturer_signup_is_atomic_and_stays_unverified(self):
        data = registration_data(ManufacturerRegistrationForm, "trusted-manufacturer-role")
        data["role"] = "ADMIN"

        response = self.client.post(reverse("register_manufacturer"), data)

        self.assertRedirects(response, reverse("manufacturer_dashboard"))
        user = get_user_model().objects.get(username=data["username"])
        profile = ManufacturerProfile.objects.get(user=user)
        self.assertEqual(user.role, get_user_model().Role.MANUFACTURER)
        self.assertTrue(user.check_password(VALID_PASSWORD))
        self.assertFalse(profile.is_verified)
        self.assertEqual(profile.kyc_status, ManufacturerProfile.KycStatus.UNDER_REVIEW)

    def test_failed_manufacturer_profile_creation_rolls_back_user_creation(self):
        data = registration_data(ManufacturerRegistrationForm, "atomic-manufacturer")
        with patch(
            "accounts.views.ManufacturerProfile.objects.create",
            side_effect=IntegrityError("profile constraint"),
        ):
            with self.assertRaises(IntegrityError):
                self.client.post(reverse("register_manufacturer"), data)

        self.assertFalse(
            get_user_model().objects.filter(username=data["username"]).exists()
        )

    def test_malformed_emails_are_rejected_by_buyer_and_manufacturer_forms(self):
        for form_class in (BuyerRegistrationForm, ManufacturerRegistrationForm):
            for index, email in enumerate(("abc", "abc@", "@domain.com")):
                with self.subTest(form=form_class.__name__, email=email):
                    data = registration_data(form_class, f"email-{index}")
                    data["email"] = email
                    form = form_class(data=data)
                    self.assertFalse(form.is_valid())
                    self.assertIn("email", form.errors)

    def test_password_mismatch_and_configured_weak_password_rules_fail_both_roles(self):
        for form_class in (BuyerRegistrationForm, ManufacturerRegistrationForm):
            mismatch = registration_data(form_class, "password-mismatch")
            mismatch["password2"] = "Different-Cobalt-752!"
            form = form_class(data=mismatch)
            self.assertFalse(form.is_valid())
            self.assertIn("password2", form.errors)

            weak = registration_data(form_class, "password-weak")
            weak["password1"] = "12345678"
            weak["password2"] = "12345678"
            form = form_class(data=weak)
            self.assertFalse(form.is_valid())
            self.assertTrue(form.errors.get("password2") or form.non_field_errors())

    def test_unchecked_agreement_blocks_buyer_and_manufacturer_signup(self):
        for form_class, route_name in (
            (BuyerRegistrationForm, "register"),
            (ManufacturerRegistrationForm, "register_manufacturer"),
        ):
            data = registration_data(form_class, f"consent-{route_name}")
            data.pop("legal_acknowledgement")

            response = self.client.post(reverse(route_name), data)

            self.assertEqual(response.status_code, 200)
            self.assertIn("legal_acknowledgement", response.context["form"].errors)
            self.assertFalse(
                get_user_model().objects.filter(username=data["username"]).exists()
            )

    def test_duplicate_username_is_a_field_error_not_a_database_exception(self):
        get_user_model().objects.create_user(
            username="existing-registration-name",
            email="first@example.test",
            password=VALID_PASSWORD,
        )

        for form_class, route_name in (
            (BuyerRegistrationForm, "register"),
            (ManufacturerRegistrationForm, "register_manufacturer"),
        ):
            data = registration_data(form_class, route_name)
            data["username"] = "existing-registration-name"

            response = self.client.post(reverse(route_name), data)

            self.assertEqual(response.status_code, 200)
            self.assertIn("username", response.context["form"].errors)

    def test_signup_password_requirements_mirror_configured_django_validators(self):
        configured = get_password_validators(settings.AUTH_PASSWORD_VALIDATORS)
        self.assertEqual(
            {type(validator) for validator in configured},
            {
                UserAttributeSimilarityValidator,
                MinimumLengthValidator,
                CommonPasswordValidator,
                NumericPasswordValidator,
            },
        )

        requirements = configured_password_requirements()
        self.assertEqual(
            [requirement["key"] for requirement in requirements],
            ["minimum_length", "not_numeric", "common_password", "similarity"],
        )
        self.assertEqual(requirements[0]["minimum"], 8)
        self.assertEqual([item["live"] for item in requirements], [True, True, False, False])

    def test_csrf_is_required_for_buyer_and_manufacturer_signup_posts(self):
        csrf_client = Client(enforce_csrf_checks=True)
        for route_name, form_class in (
            ("register", BuyerRegistrationForm),
            ("register_manufacturer", ManufacturerRegistrationForm),
        ):
            csrf_client.get(reverse(route_name))
            response = csrf_client.post(
                reverse(route_name),
                registration_data(form_class, f"csrf-{route_name}"),
            )
            self.assertEqual(response.status_code, 403)


@override_settings(PASSWORD_HASHERS=[FAST_HASHER])
class LoginHardeningTests(TestCase):
    def test_authenticated_user_is_redirected_away_from_login_form(self):
        user = get_user_model().objects.create_user(
            username="already-authenticated",
            password=VALID_PASSWORD,
            role=get_user_model().Role.BUYER,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("login"))

        self.assertRedirects(response, reverse("home"))

    def test_login_password_errors_are_generic_for_wrong_and_unknown_accounts(self):
        get_user_model().objects.create_user(
            username="generic-login-error",
            email="generic-login-error@example.test",
            password=VALID_PASSWORD,
        )

        wrong_password = self.client.post(
            reverse("login"),
            {"username": "generic-login-error", "password": "Wrong-Password-1!"},
        )
        unknown_user = self.client.post(
            reverse("login"),
            {"username": "unknown-login-name", "password": "Wrong-Password-1!"},
        )
        message = "Please enter a correct email or username and password."

        self.assertContains(wrong_password, message)
        self.assertContains(unknown_user, message)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_csrf_remains_required(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.get(reverse("login"))

        response = csrf_client.post(
            reverse("login"),
            {"username": "any-user", "password": "AnyPassword123!"},
        )

        self.assertEqual(response.status_code, 403)
