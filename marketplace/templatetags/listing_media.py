from pathlib import Path

from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static


register = template.Library()


@register.simple_tag
def listing_image_url(listing):
    """Use first-party static media for Sample listings, normal storage for others."""
    image = getattr(listing, "image", None)
    if not image:
        return ""

    if listing.manufacturer.is_demo:
        filename = Path(image.name).name
        static_path = f"marketplace/images/demo/{filename}"
        if finders.find(static_path):
            return static(static_path)
        return ""

    return image.url
