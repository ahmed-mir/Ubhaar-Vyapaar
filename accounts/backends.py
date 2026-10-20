from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db.models.functions import Lower, Trim


class EmailOrUsernameBackend(ModelBackend):
    """Keep Django username auth and allow unambiguous email login."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        user_model = get_user_model()
        if username is None:
            username = kwargs.get(user_model.USERNAME_FIELD)

        if username is None or password is None:
            return None

        # Preserve ModelBackend's exact USERNAME_FIELD lookup and inactive
        # account handling before trying the email address.
        user = super().authenticate(
            request,
            username=username,
            password=password,
        )
        if user is not None:
            return user

        email_candidate = username.strip()
        try:
            validate_email(email_candidate)
        except ValidationError:
            return None

        normalized_email = email_candidate.lower()
        matches = list(
            user_model._default_manager.annotate(
                _normalized_email=Lower(Trim("email")),
            )
            .filter(
                _normalized_email=normalized_email,
                is_active=True,
            )[:2]
        )

        if len(matches) != 1:
            return None

        email_user = matches[0]
        if email_user.check_password(password) and self.user_can_authenticate(
            email_user
        ):
            return email_user

        return None
