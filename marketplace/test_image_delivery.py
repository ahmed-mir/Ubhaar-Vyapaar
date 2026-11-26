from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.staticfiles.finders import find
from django.template.loader import render_to_string
from django.test import SimpleTestCase
from django.templatetags.static import static

from .templatetags.listing_media import listing_image_sources


def make_listing(image_url, name="listings/public-capacity.webp", is_demo=False):
    return SimpleNamespace(
        manufacturer=SimpleNamespace(is_demo=is_demo),
        image=SimpleNamespace(name=name, url=image_url),
        machine_type="CNC machining",
        materials="Aluminium",
        get_category_display=lambda: "Metal",
    )


class ListingImageDeliveryTests(SimpleTestCase):
    def cloudinary_listing(self):
        return make_listing(
            "https://res.cloudinary.com/project-cloud/image/upload/listings/public-capacity.webp"
        )

    @patch("cloudinary.utils.cloudinary_url")
    def test_cloudinary_srcset_uses_auto_format_quality_and_width_variants(self, url_builder):
        url_builder.side_effect = lambda public_id, **options: (
            "https://res.cloudinary.com/project-cloud/image/upload/"
            f"w_{options['transformation'][0]['width']}/{public_id}",
            {},
        )

        sources = listing_image_sources(
            self.cloudinary_listing(), width=800, height=600, crop="fill"
        )

        self.assertEqual(url_builder.call_count, 5)
        self.assertIn("w_320", sources["srcset"])
        self.assertIn("w_480", sources["srcset"])
        self.assertIn("w_640", sources["srcset"])
        self.assertIn("w_960", sources["srcset"])
        self.assertIn("w_1280", sources["srcset"])
        self.assertTrue(sources["src"].endswith("w_640/listings/public-capacity.webp"))

        transformations = [call.kwargs["transformation"][0] for call in url_builder.call_args_list]
        self.assertEqual([item["width"] for item in transformations], [320, 480, 640, 960, 1280])
        self.assertEqual([item["height"] for item in transformations], [240, 360, 480, 720, 960])
        for transformation in transformations:
            self.assertEqual(transformation["fetch_format"], "auto")
            self.assertEqual(transformation["quality"], "auto")
            self.assertEqual(transformation["crop"], "fill")
            self.assertEqual(transformation["gravity"], "auto")

    @patch("cloudinary.utils.cloudinary_url")
    def test_detail_limit_variants_keep_source_ratio_and_only_limit_width(self, url_builder):
        url_builder.return_value = ("https://res.cloudinary.com/project-cloud/image/upload/variant", {})

        listing_image_sources(
            self.cloudinary_listing(), width=800, height=0, crop="limit"
        )

        transformations = [call.kwargs["transformation"][0] for call in url_builder.call_args_list]
        self.assertTrue(all("height" not in item for item in transformations))
        self.assertTrue(all(item["crop"] == "limit" for item in transformations))
        self.assertTrue(all("gravity" not in item for item in transformations))

    @patch("cloudinary.utils.cloudinary_url")
    def test_local_and_non_cloudinary_urls_pass_through_without_transformations(self, url_builder):
        local = make_listing("/media/listings/local.webp")
        external = make_listing("https://images.example.test/listing.webp")

        self.assertEqual(listing_image_sources(local)["src"], "/media/listings/local.webp")
        self.assertEqual(listing_image_sources(external)["src"], "https://images.example.test/listing.webp")
        self.assertEqual(listing_image_sources(local)["srcset"], "")
        self.assertEqual(listing_image_sources(external)["srcset"], "")
        url_builder.assert_not_called()

    @patch("cloudinary.utils.cloudinary_url")
    def test_sample_images_stay_first_party_static_and_missing_images_stay_empty(self, url_builder):
        sample = make_listing(
            "/media/demo/listings/printed-labels.webp",
            name="demo/listings/printed-labels.webp",
            is_demo=True,
        )
        missing = make_listing("", name="", is_demo=False)

        self.assertEqual(
            listing_image_sources(sample)["src"],
            static("marketplace/images/demo/printed-labels.webp"),
        )
        self.assertTrue(find("marketplace/images/demo/printed-labels.webp"))
        self.assertEqual(listing_image_sources(missing), {"src": "", "srcset": ""})
        url_builder.assert_not_called()

    @patch("cloudinary.utils.cloudinary_url")
    def test_unsafe_or_malformed_url_uses_existing_visual_fallback(self, url_builder):
        listing = make_listing("javascript:alert(1)")

        sources = listing_image_sources(listing)
        rendered = render_to_string(
            "marketplace/includes/listing_visual.html",
            {"listing": listing, "image_sources": sources},
        )

        self.assertEqual(sources, {"src": "", "srcset": ""})
        self.assertIn('class="listing-image-placeholder"', rendered)
        self.assertNotIn("javascript:", rendered)
        url_builder.assert_not_called()

    @patch("cloudinary.utils.cloudinary_url")
    def test_malformed_absolute_url_renders_placeholder_without_raising(self, url_builder):
        listing = make_listing("https://[invalid-host/image.jpg")

        sources = listing_image_sources(listing)
        rendered = render_to_string(
            "marketplace/includes/listing_visual.html",
            {"listing": listing},
        )

        self.assertEqual(sources, {"src": "", "srcset": ""})
        self.assertIn('class="listing-image-placeholder"', rendered)
        self.assertNotIn('class="listing-image"', rendered)
        url_builder.assert_not_called()

    @patch("cloudinary.utils.cloudinary_url")
    def test_template_emits_responsive_attributes_and_reserved_dimensions(self, url_builder):
        url_builder.side_effect = lambda public_id, **options: (
            "https://res.cloudinary.com/project-cloud/image/upload/"
            f"w_{options['transformation'][0]['width']}/{public_id}",
            {},
        )

        rendered = render_to_string(
            "marketplace/includes/listing_visual.html",
            {
                "listing": self.cloudinary_listing(),
                "image_sizes": "(max-width: 640px) 100vw, 340px",
                "image_loading": "lazy",
            },
        )

        self.assertIn('srcset="', rendered)
        self.assertIn('sizes="(max-width: 640px) 100vw, 340px"', rendered)
        self.assertIn('width="800"', rendered)
        self.assertIn('height="600"', rendered)
        self.assertIn('loading="lazy"', rendered)
        self.assertIn('decoding="async"', rendered)
        self.assertIn('alt="CNC machining manufacturing capacity"', rendered)
