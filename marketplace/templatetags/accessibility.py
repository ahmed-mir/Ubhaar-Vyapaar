from django import template
from django.utils.safestring import mark_safe

register = template.Library()


def _describedby_ids(bound_field):
    ids = []

    if bound_field.errors:
        ids.append(f"{bound_field.auto_id}_error")

    if bound_field.help_text:
        ids.append(f"{bound_field.auto_id}_helptext")

    return " ".join(ids)


@register.filter
def render_accessible_field(bound_field):
    attrs = {}
    describedby = _describedby_ids(bound_field)

    if describedby:
        attrs["aria-describedby"] = describedby

    if bound_field.errors:
        attrs["aria-invalid"] = "true"

    if bound_field.field.required:
        attrs["aria-required"] = "true"

    return mark_safe(bound_field.as_widget(attrs=attrs))
