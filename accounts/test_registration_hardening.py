from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.conf import settings
from django.contrib.auth.password_validation import (
    MinimumLengthValidator,
    NumericPasswordValidator,
    UserAttributeSimilarityValidator,
    get_password_validators,
)
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.functions import Lower, Trim
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from marketplace.models import ManufacturerProfile

from .password_validators import SymbolPasswordValidator
from .forms import (
    BuyerRegistrationForm,
    ManufacturerRegistrationForm,
    configured_password_requirements,
)


FAST_HASHER = "django.contrib.auth.hashers.MD5PasswordHasher"
VALID_PASSWORD = "Cobalt-Orbit-752!"
PHONE_ERROR = "Enter a valid 10-digit mobile number."


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
    def test_phone_is_optional_and_accepts_exactly_ten_ascii_digits(self):
        examples = ("", "9876543210", "8123456789")
        for form_class in (BuyerRegistrationForm, ManufacturerRegistrationForm):
            for index, phone in enumerate(examples):
                with self.subTest(form=form_class.__name__, phone=phone):
                    form = form_class(
                        data=registration_data(form_class, f"valid-{index}", phone)
                    )
                    self.assertTrue(form.is_valid(), form.errors)
                    self.assertEqual(
                        form.cleaned_data["phone"],
                        f"+91{phone}" if phone else "",
                    )

    def test_both_signup_forms_reject_malformed_phone_server_side(self):
        invalid_numbers = (
            "98765",
            "987654321",
            "98765432101",
            "abcdef",
            "98765abc12",
            "+919876543210",
            "98765 43210",
            "98765-43210",
            "(98765)43210",
            " 9876543210 ",
            "１２３４５６７８９０",
        )
        for form_class in (BuyerRegistrationForm, ManufacturerRegistrationForm):
            for index, phone in enumerate(invalid_numbers):
                with self.subTest(form=form_class.__name__, phone=phone):
                    form = form_class(
                        data=registration_data(form_class, f"invalid-{index}", phone)
                    )
                    self.assertFalse(form.is_valid())
                    self.assertEqual(form.errors["phone"], [PHONE_ERROR])

    def test_direct_signup_posts_reject_invalid_phone_without_javascript(self):
        invalid_values = ("abcdefghij", "12345abc90", "98765432101", "+919876543210")
        for form_class, route_name in (
            (BuyerRegistrationForm, "register"),
            (ManufacturerRegistrationForm, "register_manufacturer"),
        ):
            for index, phone in enumerate(invalid_values):
                data = registration_data(
                    form_class,
                    f"direct-{route_name}-{index}",
                    phone,
                )
                if index == 0:
                    data["role"] = (
                        "MANUFACTURER"
                        if form_class is BuyerRegistrationForm
                        else "BUYER"
                    )

                response = self.client.post(reverse(route_name), data)

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["form"].errors["phone"], [PHONE_ERROR])
                self.assertFalse(
                    get_user_model().objects.filter(username=data["username"]).exists()
                )
                self.assertFalse(
                    ManufacturerProfile.objects.filter(
                        user__username=data["username"]
                    ).exists()
                )

    def test_phone_is_stored_with_fixed_india_country_code(self):
        data = registration_data(BuyerRegistrationForm, "national-phone", "9876543210")

        response = self.client.post(reverse("register"), data)

        self.assertRedirects(response, reverse("home"))
        user = get_user_model().objects.get(username=data["username"])
        self.assertEqual(user.phone, "+919876543210")

    def test_form_phone_attributes_match_the_national_number_rule_without_helper_text(self):
        for form_class in (BuyerRegistrationForm, ManufacturerRegistrationForm):
            with self.subTest(form=form_class.__name__):
                form = form_class()
                phone = form["phone"]
                self.assertFalse(phone.field.required)
                self.assertEqual(phone.field.widget.input_type, "tel")
                self.assertEqual(phone.field.widget.attrs["inputmode"], "numeric")
                self.assertEqual(phone.field.widget.attrs["autocomplete"], "tel-national")
                self.assertEqual(phone.field.widget.attrs["maxlength"], "10")
                self.assertEqual(phone.field.widget.attrs["pattern"], "[0-9]{10}")
                self.assertEqual(phone.help_text, "")


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

    def test_password_mismatch_and_missing_symbol_fail_both_roles(self):
        for form_class in (BuyerRegistrationForm, ManufacturerRegistrationForm):
            mismatch = registration_data(form_class, "password-mismatch")
            mismatch["password2"] = "Different-Cobalt-752!"
            form = form_class(data=mismatch)
            self.assertFalse(form.is_valid())
            self.assertIn("password2", form.errors)

            for password in ("abcdefgh", "12345678", "Ahmed123"):
                weak = registration_data(form_class, f"password-weak-{password}")
                weak["username"] = "unrelated-account"
                weak["email"] = "separate@example.test"
                weak["password1"] = password
                weak["password2"] = password
                form = form_class(data=weak)
                self.assertFalse(form.is_valid())
                self.assertTrue(
                    any(
                        "symbol" in error.lower()
                        for error in form.errors.get("password2", [])
                    ),
                    form.errors,
                )

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
            self.assertEqual(
                response.context["form"].errors["username"],
                ["A user with that username already exists."],
            )

    def test_buyer_duplicate_emails_are_rejected_case_insensitively(self):
        data = registration_data(BuyerRegistrationForm, "buyer-email-first")
        data["email"] = "Ahmed@example.com"
        self.assertRedirects(self.client.post(reverse("register"), data), reverse("home"))

        self.client.logout()
        for index, email in enumerate(("ahmed@example.com", "AHMED@EXAMPLE.COM")):
            duplicate = registration_data(BuyerRegistrationForm, f"buyer-email-dup-{index}")
            duplicate["email"] = email
            response = self.client.post(reverse("register"), duplicate)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.context["form"].errors["email"],
                ["An account with this email address already exists."],
            )
            self.assertFalse(
                get_user_model().objects.filter(username=duplicate["username"]).exists()
            )

    def test_manufacturer_duplicate_emails_are_rejected_case_insensitively(self):
        first = registration_data(ManufacturerRegistrationForm, "manufacturer-email-first")
        first["email"] = "builder@example.com"
        self.assertRedirects(
            self.client.post(reverse("register_manufacturer"), first),
            reverse("manufacturer_dashboard"),
        )

        self.client.logout()
        duplicate = registration_data(
            ManufacturerRegistrationForm,
            "manufacturer-email-duplicate",
        )
        duplicate["email"] = "BUILDER@EXAMPLE.COM"
        response = self.client.post(reverse("register_manufacturer"), duplicate)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["form"].errors["email"],
            ["An account with this email address already exists."],
        )
        self.assertFalse(
            get_user_model().objects.filter(username=duplicate["username"]).exists()
        )

    def test_email_uniqueness_applies_across_buyer_and_manufacturer_roles(self):
        buyer = registration_data(BuyerRegistrationForm, "cross-role-buyer")
        buyer["email"] = "shared@example.com"
        self.client.post(reverse("register"), buyer)
        self.client.logout()

        manufacturer = registration_data(
            ManufacturerRegistrationForm,
            "cross-role-manufacturer",
        )
        manufacturer["email"] = "SHARED@EXAMPLE.COM"
        response = self.client.post(reverse("register_manufacturer"), manufacturer)
        self.assertEqual(response.status_code, 200)
        self.assertIn("email", response.context["form"].errors)
        self.assertFalse(
            get_user_model().objects.filter(username=manufacturer["username"]).exists()
        )

    def test_email_is_stripped_and_lowercased_before_storage(self):
        data = registration_data(BuyerRegistrationForm, "normalized-email")
        data["email"] = "  Ahmed@Example.com  "

        self.assertRedirects(self.client.post(reverse("register"), data), reverse("home"))
        user = get_user_model().objects.get(username=data["username"])
        self.assertEqual(user.email, "ahmed@example.com")

    def test_user_model_normalizes_email_when_saved_outside_signup_forms(self):
        user = get_user_model().objects.create_user(
            username="model-email-normalization",
            email="  Ahmed@Example.com  ",
            password=VALID_PASSWORD,
        )

        self.assertEqual(user.email, "ahmed@example.com")

    def test_case_insensitive_email_constraint_is_enforced_by_the_database(self):
        user_model = get_user_model()
        first = user_model.objects.create_user(
            username="database-email-first",
            email="db-unique@example.test",
            password=VALID_PASSWORD,
        )
        second = user_model.objects.create_user(
            username="database-email-second",
            email="other@example.test",
            password=VALID_PASSWORD,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                user_model.objects.filter(pk=second.pk).update(
                    email=first.email.upper(),
                )

    def test_signup_password_validators_and_visible_requirements_match(self):
        configured = get_password_validators(settings.AUTH_PASSWORD_VALIDATORS)
        self.assertEqual(
            [type(validator) for validator in configured],
            [
                MinimumLengthValidator,
                SymbolPasswordValidator,
                NumericPasswordValidator,
                UserAttributeSimilarityValidator,
            ],
        )
        self.assertEqual(configured[0].min_length, 8)
        self.assertEqual(configured[3].user_attributes, ("username", "email"))

        requirements = configured_password_requirements()
        self.assertEqual(
            [requirement["key"] for requirement in requirements],
            ["minimum_length", "symbol", "not_numeric", "similarity"],
        )
        self.assertEqual(requirements[0]["minimum"], 8)
        self.assertTrue(all(item["live"] for item in requirements))
        self.assertEqual(
            requirements[-1]["text"],
            "Must not be similar to your email address or username",
        )
        self.assertNotIn("common_password", [item["key"] for item in requirements])

    def test_symbol_password_validator_accepts_non_alphanumeric_and_rejects_plain_text(self):
        validator = SymbolPasswordValidator()
        validator.validate("Ahmed@123")
        with self.assertRaises(ValidationError):
            validator.validate("Ahmed123")

    def test_similarity_validator_checks_username_and_email_only(self):
        similarity = get_password_validators(settings.AUTH_PASSWORD_VALIDATORS)[-1]
        self.assertEqual(similarity.user_attributes, ("username", "email"))

        for form_class in (BuyerRegistrationForm, ManufacturerRegistrationForm):
            for identifier, username, email, password in (
                ("username", "AhmedUser", "distinct@acme.com", "AhmedUser!"),
                ("email", "UnrelatedUser", "ahmed@acme.com", "ahmed@acme.com"),
            ):
                data = registration_data(form_class, f"similarity-{identifier}")
                data["username"] = username
                data["email"] = email
                data["password1"] = password
                data["password2"] = password
                form = form_class(data=data)
                self.assertFalse(form.is_valid())
                self.assertTrue(
                    any(
                        "too similar" in error.lower()
                        for error in form.errors.get("password2", [])
                    ),
                    form.errors,
                )

    def test_common_password_validator_is_not_enabled_or_displayed(self):
        data = registration_data(BuyerRegistrationForm, "common-password")
        data["username"] = "an-unrelated-username"
        data["email"] = "unrelated@example.test"
        data["password1"] = "password!"
        data["password2"] = "password!"
        form = BuyerRegistrationForm(data=data)
        self.assertTrue(form.is_valid(), form.errors)

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
