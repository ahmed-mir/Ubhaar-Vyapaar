from decimal import Decimal, InvalidOperation

from django import template
from django.utils.html import format_html


register = template.Library()


@register.filter
def inr(value):
    if value in (None, ""):
        return "Not specified"

    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return value

    return format_html("&#8377;{}", f"{amount:,.2f}")
