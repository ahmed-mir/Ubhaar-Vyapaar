from django import template

from marketplace.locations import INDIA_STATE_UT_NAMES


register = template.Library()

_CANONICAL_STATE_LABELS = {
    name.casefold(): name for name in INDIA_STATE_UT_NAMES
}


@register.filter
def state_label(value):
    """Render known State/UT values with their canonical public label."""
    if value in (None, ""):
        return ""

    value = str(value).strip()
    return _CANONICAL_STATE_LABELS.get(value.casefold(), value)
