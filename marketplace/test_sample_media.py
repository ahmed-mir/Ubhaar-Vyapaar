from types import SimpleNamespace

from django.contrib.staticfiles import finders
from django.template.loader import render_to_string
from django.test import SimpleTestCase
from django.templatetags.static import static

from .templatetags.listing_media import listing_image_url


SAMPLE_IMAGES = (
    "cnc-machining-capacity.webp",
    "corrugated-packaging.webp",
    "cotton-garment-production.webp",
    "sheet-metal-fabrication.webp",
    "injection-moulding.webp",
    "printed-labels.webp",
    "pcb-assembly.webp",
    "stainless-steel-components.webp",
    "industrial-fasteners.webp",
    "textile-dyeing.webp",
)


class SampleMediaPresentationTests(SimpleTestCase):
    def test_sample_photos_are_first_party_static_assets(self):
        for filename in SAMPLE_IMAGES:
            with self.subTest(filename=filename):
                static_path = f"marketplace/images/demo/{filename}"
                file_path = finders.find(static_path)
                self.assertTrue(file_path)
                with open(file_path, "rb") as photo:
                    header = photo.read(12)
                self.assertEqual(header[:4], b"RIFF")
                self.assertEqual(header[8:12], b"WEBP")
                listing = SimpleNamespace(
                    manufacturer=SimpleNamespace(is_demo=True),
                    image=SimpleNamespace(name=f"demo/listings/{filename}"),
                )
                self.assertEqual(listing_image_url(listing), static(static_path))

    def test_missing_sample_photo_keeps_first_party_fallback(self):
        listing = SimpleNamespace(
            manufacturer=SimpleNamespace(is_demo=True),
            image=SimpleNamespace(name="demo/listings/missing-sample.webp"),
            machine_type="CNC milling and turning",
            materials="Aluminium and steel",
            get_category_display=lambda: "Metal",
        )

        self.assertEqual(listing_image_url(listing), "")
        rendered = render_to_string(
            "marketplace/includes/listing_visual.html",
            {
                "listing": listing,
                "resolved_image_url": listing_image_url(listing),
            },
        )

        self.assertIn(static("marketplace/images/brand/logo-mark.svg"), rendered)
        self.assertNotIn("cloudinary", rendered.lower())
        self.assertNotIn("demo/listings/missing-sample.webp", rendered)

    def test_real_listing_keeps_configured_storage_url(self):
        listing = SimpleNamespace(
            manufacturer=SimpleNamespace(is_demo=False),
            image=SimpleNamespace(
                name="listings/real-capacity.webp",
                url="/configured-media/listings/real-capacity.webp",
            ),
        )

        self.assertEqual(
            listing_image_url(listing),
            "/configured-media/listings/real-capacity.webp",
        )
