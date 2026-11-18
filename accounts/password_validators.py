from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class SymbolPasswordValidator:
    """Require at least one non-alphanumeric password character."""

    def validate(self, password, user=None):
        if not any(not character.isalnum() for character in password):
            raise ValidationError(
                _("Your password must contain at least one symbol."),
                code="password_no_symbol",
            )

    def get_help_text(self):
        return _("Your password must contain at least one symbol.")
