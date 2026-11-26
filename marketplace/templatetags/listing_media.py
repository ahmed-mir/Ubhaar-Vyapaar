from pathlib import Path
from urllib.parse import urlsplit

from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static


register = template.Library()

RESPONSIVE_LISTING_WIDTHS = (320, 480, 640, 960, 1280)


def _cloudinary_cloud_name(image_url):
    parsed = urlsplit(image_url)
    if parsed.scheme != "https" or parsed.hostname != "res.cloudinary.com":
        return ""

    segments = parsed.path.split("/")
    if len(segments) < 4 or segments[2:4] != ["image", "upload"]:
        return ""

    return segments[1]


def _cloudinary_variant(public_id, cloud_name, width, height, crop):
    from cloudinary.utils import cloudinary_url

    transformation = {
        "fetch_format": "auto",
        "quality": "auto",
        "width": width,
        "crop": crop,
    }
    if height:
        transformation["height"] = height
    if crop == "fill":
        transformation["gravity"] = "auto"

    url, _options = cloudinary_url(
        public_id,
        cloud_name=cloud_name,
        resource_type="image",
        secure=True,
        transformation=[transformation],
    )
    return url


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


@register.simple_tag
def listing_image_sources(listing, width=800, height=600, crop="fill"):
    """Return a storage-safe image URL and responsive Cloudinary variants."""
    image = getattr(listing, "image", None)
    if not image:
        return {"src": "", "srcset": ""}

    try:
        original_url = listing_image_url(listing)
    except (OSError, TypeError, ValueError):
        return {"src": "", "srcset": ""}

    if not original_url:
        return {"src": "", "srcset": ""}

    try:
        parsed_url = urlsplit(original_url)
    except ValueError:
        return {"src": "", "srcset": ""}
    if parsed_url.scheme and parsed_url.scheme not in {"http", "https"}:
        return {"src": "", "srcset": ""}
    if parsed_url.scheme in {"http", "https"} and not parsed_url.hostname:
        return {"src": "", "srcset": ""}
    if original_url.startswith("//"):
        return {"src": "", "srcset": ""}

    cloud_name = _cloudinary_cloud_name(original_url)
    if not cloud_name or getattr(listing.manufacturer, "is_demo", False):
        return {"src": original_url, "srcset": ""}

    try:
        target_width = max(1, int(width))
    except (TypeError, ValueError):
        target_width = 800
    try:
        target_height = max(0, int(height))
    except (TypeError, ValueError):
        target_height = 600

    if crop in (None, ""):
        crop = "fill"
    elif crop not in {"fill", "limit"}:
        crop = "limit"
    variants = []
    public_id = getattr(image, "name", "")
    if not public_id:
        return {"src": original_url, "srcset": ""}
    try:
        for variant_width in RESPONSIVE_LISTING_WIDTHS:
            variant_height = (
                round(target_height * variant_width / target_width)
                if crop == "fill" and target_height
                else 0
            )
            variant_url = _cloudinary_variant(
                public_id,
                cloud_name,
                variant_width,
                variant_height,
                crop,
            )
            variants.append((variant_width, variant_url))
    except (ImportError, OSError, TypeError, ValueError):
        return {"src": original_url, "srcset": ""}

    fallback_variant = min(
        variants,
        key=lambda variant: abs(variant[0] - min(target_width, 640)),
    )
    return {
        "src": fallback_variant[1],
        "srcset": ", ".join(
            f"{url} {variant_width}w" for variant_width, url in variants
        ),
    }
