from django import template

from marketplace.templatetags.accessibility import render_accessible_field

register = template.Library()


@register.filter
def render_auth_field(field):
    """Add browser hints without changing form binding or validation."""
    autocomplete = {
        "username": "username",
        "email": "email",
        "phone": "tel-national",
        "business_name": "organization",
        "city": "address-level2",
        "state": "address-level1",
        "old_password": "current-password",
        "password1": "new-password",
        "password2": "new-password",
        "new_password1": "new-password",
        "new_password2": "new-password",
    }.get(field.name)
    if autocomplete and "autocomplete" not in field.field.widget.attrs:
        field.field.widget.attrs["autocomplete"] = autocomplete
    return render_accessible_field(field)
