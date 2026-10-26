import logging

from django import forms
from django.conf import settings
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.forms import UserCreationForm
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone

from .models import User

logger = logging.getLogger(__name__)


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
        self.fields["phone"].help_text = "Optional. Used only for account or workflow contact if provided."

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
    state = forms.CharField(max_length=100)

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
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].help_text = (
            "Your username is your unique account name. You can also log in "
            "with your email."
        )
        self.fields["email"].required = True
        self.fields["phone"].required = False
        self.fields["phone"].help_text = "Optional. Used only for account or workflow contact if provided."

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.MANUFACTURER
        self._record_legal_acknowledgement(user)

        if commit:
            user.save()

        return user
