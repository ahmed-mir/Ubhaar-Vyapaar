from decimal import Decimal, InvalidOperation

from django import template
from django.utils.html import format_html


register = template.Library()


def _indian_grouped(value):
    text = str(value)
    sign = ""
    if text.startswith(("-", "+")):
        sign, text = text[0], text[1:]
    integer, separator, fraction = text.partition(".")
    if len(integer) > 3:
        tail = integer[-3:]
        head = integer[:-3]
        groups = []
        while head:
            groups.append(head[-2:])
            head = head[:-2]
        integer = ",".join(reversed(groups)) + "," + tail
    return sign + integer + (separator + fraction if separator else "")


@register.filter
def inr(value):
    if value in (None, ""):
        return "Not specified"

    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return value

    rendered = f"{amount:.2f}" if amount % 1 else f"{amount:.0f}"
    return format_html("&#8377;{}", _indian_grouped(rendered))


@register.filter
def indian_number(value):
    if value in (None, ""):
        return ""
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return value
    rendered = f"{amount:.2f}" if amount % 1 else f"{amount:.0f}"
    return _indian_grouped(rendered)
