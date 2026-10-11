from django import forms
from django.conf import settings
from django.contrib.auth.forms import UserCreationForm
from django.utils import timezone

from .models import User


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
