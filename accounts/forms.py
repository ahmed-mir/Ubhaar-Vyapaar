from django.contrib.auth.forms import UserCreationForm

from .models import User
from django import forms

class BuyerRegistrationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("username", "email", "phone")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.BUYER

        if commit:
            user.save()

        return user
class ManufacturerRegistrationForm(UserCreationForm):
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

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.MANUFACTURER

        if commit:
            user.save()

        return user    