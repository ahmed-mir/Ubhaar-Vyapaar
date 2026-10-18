from django import template
from django.utils.html import json_script
from django.utils.safestring import mark_safe


register = template.Library()


@register.simple_tag
def json_ld(value, element_id):
    """Serialize structured data with Django's script-safe JSON escaping."""
    script = json_script(value, element_id)
    return mark_safe(
        str(script).replace(
            'type="application/json"',
            'type="application/ld+json"',
            1,
        )
    )
