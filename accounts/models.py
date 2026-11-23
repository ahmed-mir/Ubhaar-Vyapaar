from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower, Trim


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

    class Meta(AbstractUser.Meta):
        abstract = False
        constraints = [
            models.UniqueConstraint(
                Lower(Trim("email")),
                condition=~Q(email=""),
                name="accounts_user_email_ci_uniq",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.email is not None:
            self.email = self.email.strip().lower()
        return super().save(*args, **kwargs)

    @property
    def account_display_name(self):
        if not self.is_active:
            return "Deleted account"
        return self.first_name or self.username or self.email


class AuthRateLimitBucket(models.Model):
    """A fixed-window counter keyed only by a keyed digest, never raw input."""

    scope = models.CharField(max_length=32)
    key_digest = models.CharField(max_length=64)
    window_start = models.DateTimeField()
    count = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("scope", "key_digest", "window_start"),
                name="auth_rate_bucket_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=("window_start",),
                name="auth_rate_bucket_window_idx",
            ),
        ]
