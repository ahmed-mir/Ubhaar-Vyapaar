from django import template

from marketplace.locations import canonical_india_state_ut_name


register = template.Library()

@register.filter
def state_label(value):
    """Render known State/UT values with their canonical public label."""
    return canonical_india_state_ut_name(value)
