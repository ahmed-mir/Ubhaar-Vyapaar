from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        BUYER = "BUYER", "Buyer"
        MANUFACTURER = "MANUFACTURER", "Manufacturer"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.BUYER,
    )

    phone = models.CharField(max_length=20, blank=True)

    terms_accepted_at = models.DateTimeField(null=True, blank=True)
    privacy_acknowledged_at = models.DateTimeField(null=True, blank=True)
    terms_version = models.CharField(max_length=40, blank=True)
    privacy_policy_version = models.CharField(max_length=40, blank=True)
