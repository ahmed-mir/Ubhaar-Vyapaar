import logging

from django import forms
from django.conf import settings
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.password_validation import (
    MinimumLengthValidator,
    NumericPasswordValidator,
    UserAttributeSimilarityValidator,
    get_password_validators,
)
from django.core.exceptions import ValidationError
from django.db.models.functions import Lower, Trim
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

from .password_validators import SymbolPasswordValidator
from .models import User
from marketplace.locations import (
    INDIA_PINCODE_HTML_PATTERN,
    INDIA_STATE_UT_CHOICES,
    INDIA_STATE_UT_PLACEHOLDER,
    validate_indian_pincode,
)

logger = logging.getLogger(__name__)

def validate_phone_number(value):
    """Validate an optional Indian national mobile number and add +91."""
    phone = value or ""
    if not phone:
        return ""

    if len(phone) != 10 or not phone.isascii() or not phone.isdigit():
        raise ValidationError(
            "Enter a valid 10-digit mobile number.",
            code="invalid_phone",
        )

    return f"+91{phone}"


def configured_password_requirements():
    """Describe the active Django password validators for signup UX."""
    requirements = []
    priority = {
        "minimum_length": 0,
        "symbol": 1,
        "not_numeric": 2,
        "similarity": 3,
    }

    for index, validator in enumerate(
        get_password_validators(settings.AUTH_PASSWORD_VALIDATORS)
    ):
        if isinstance(validator, MinimumLengthValidator):
            requirement = {
                "key": "minimum_length",
                "text": f"At least {validator.min_length} characters",
                "live": True,
                "minimum": validator.min_length,
            }
        elif isinstance(validator, SymbolPasswordValidator):
            requirement = {
                "key": "symbol",
                "text": "At least 1 symbol (e.g. @ # $ & !)",
                "live": True,
            }
        elif isinstance(validator, NumericPasswordValidator):
            requirement = {
                "key": "not_numeric",
                "text": "Not entirely numeric",
                "live": True,
            }
        elif isinstance(validator, UserAttributeSimilarityValidator):
            attributes = tuple(validator.user_attributes)
            requirement = {
                "key": "similarity",
                "text": (
                    "Must not be similar to your email address or username"
                    if set(attributes) == {"username", "email"}
                    else strip_tags(str(validator.get_help_text())).strip()
                ),
                "live": set(attributes) == {"username", "email"},
                "attributes": ",".join(attributes),
                "max_similarity": validator.max_similarity,
            }
        else:
            help_text = strip_tags(str(validator.get_help_text())).strip()
            requirement = {
                "key": f"configured_rule_{index}",
                "text": help_text or "Must meet the configured password rule",
                "live": False,
            }

        requirement["priority"] = priority.get(requirement["key"], 10 + index)
        requirements.append(requirement)

    return sorted(requirements, key=lambda requirement: requirement["priority"])


class ReliablePasswordResetForm(PasswordResetForm):
    def send_mail(
        self,
        subject_template_name,
        email_template_name,
        context,
        from_email,
        to_email,
        html_email_template_name=None,
    ):
        subject = render_to_string(subject_template_name, context)
        subject = "".join(subject.splitlines())
        body = render_to_string(email_template_name, context)

        html_body = None
        if html_email_template_name:
            html_body = render_to_string(html_email_template_name, context)

        try:
            result = send_mail(
                subject=subject,
                message=body,
                from_email=from_email or settings.DEFAULT_FROM_EMAIL,
                recipient_list=[to_email],
                fail_silently=False,
                html_message=html_body,
            )

            logger.info(
                "Password reset email handed to email backend successfully: "
                "result=%s",
                result,
            )
            return result

        except Exception:
            logger.exception("Password reset email delivery failed.")
            raise


class AccountClosureForm(forms.Form):
    """Require password reauthentication and a deliberate closure phrase."""

    password = forms.CharField(
        label="Current password",
        strip=False,
        widget=forms.PasswordInput(
            attrs={"autocomplete": "current-password"}
        ),
    )
    confirmation = forms.CharField(
        label='Type "CLOSE" to confirm',
        strip=True,
        max_length=5,
    )

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_password(self):
        password = self.cleaned_data["password"]
        if not self.user.check_password(password):
            raise ValidationError("Enter your current password to continue.")
        return password

    def clean_confirmation(self):
        value = self.cleaned_data["confirmation"]
        if value != "CLOSE":
            raise ValidationError('Type "CLOSE" to confirm account closure.')
        return value


class RegistrationConsentMixin(forms.Form):
    legal_acknowledgement = forms.BooleanField(
        required=True,
        label=(
            "I agree to the Terms & Conditions and acknowledge "
            "the Privacy Policy."
        ),
        error_messages={
            "required": (
                "Please agree to the Terms & Conditions and acknowledge "
                "the Privacy Policy to create an account."
            ),
        },
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        phone = self.fields.get("phone")
        if phone:
            phone.label = "Mobile number"
            phone.strip = False
            phone.widget.input_type = "tel"
            phone.widget.attrs.update(
                {
                    "inputmode": "numeric",
                    "autocomplete": "tel-national",
                    "maxlength": "10",
                    "pattern": "[0-9]{10}",
                    "placeholder": "9876543210",
                }
            )
            phone.help_text = ""

        if "password1" in self.fields:
            self.password_requirements = configured_password_requirements()
            self.fields["password1"].help_text = (
                "Your password is checked against the requirements below."
            )
            self.fields["password2"].help_text = (
                "Re-enter the same password to confirm it."
            )

    def clean_phone(self):
        return validate_phone_number(self.cleaned_data.get("phone", ""))

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        duplicates = User.objects.annotate(
            _normalized_email=Lower(Trim("email")),
        ).filter(_normalized_email=email)
        if self.instance.pk:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise ValidationError(
                "An account with this email address already exists.",
                code="duplicate_email",
            )
        return email

    def _record_legal_acknowledgement(self, user):
        accepted_at = timezone.now()
        user.terms_accepted_at = accepted_at
        user.privacy_acknowledged_at = accepted_at
        user.terms_version = settings.TERMS_VERSION
        user.privacy_policy_version = settings.PRIVACY_POLICY_VERSION
        return user


class BuyerRegistrationForm(RegistrationConsentMixin, UserCreationForm):
    class Meta:
        model = User
        fields = ("username", "email", "phone")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].help_text = (
            "Your username is your unique account name. You can also log in "
            "with your email."
        )
        self.fields["email"].required = True
        self.fields["phone"].required = False

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.BUYER
        self._record_legal_acknowledgement(user)

        if commit:
            user.save()

        return user
class ManufacturerRegistrationForm(RegistrationConsentMixin, UserCreationForm):
    business_name = forms.CharField(max_length=200)
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
    )
    city = forms.CharField(max_length=100)
    state = forms.ChoiceField(
        label="State",
        choices=(
            ("", INDIA_STATE_UT_PLACEHOLDER),
            *INDIA_STATE_UT_CHOICES,
        ),
    )
    pincode = forms.CharField(
        label="PIN code",
        strip=False,
        validators=[validate_indian_pincode],
        widget=forms.TextInput(
            attrs={
                "type": "text",
                "inputmode": "numeric",
                "maxlength": "6",
                "autocomplete": "postal-code",
                "pattern": INDIA_PINCODE_HTML_PATTERN,
            }
        ),
    )

    class Meta:
        model = User
        fields = (
            "username",
            "email",
            "phone",
            "business_name",
            "description",
            "city",
            "state",
            "pincode",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].help_text = (
            "Your username is your unique account name. You can also log in "
            "with your email."
        )
        self.fields["email"].required = True
        self.fields["phone"].required = False

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.MANUFACTURER
        self._record_legal_acknowledgement(user)

        if commit:
            user.save()

        return user
