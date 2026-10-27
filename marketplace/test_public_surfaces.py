import json
import re
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import CapacityListing, ManufacturerProfile


class PublicTradeSurfaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.sample_user = user_model.objects.create_user(
            username="demo_mfr_public_surface",
            password="password",
            role="MANUFACTURER",
        )
        cls.sample_manufacturer = ManufacturerProfile.objects.create(
            user=cls.sample_user,
            business_name="Sample Works",
            description="Illustrative manufacturing profile.",
            city="Pune",
            state="Maharashtra",
            is_verified=True,
        )
        cls.sample_listing = CapacityListing.objects.create(
            manufacturer=cls.sample_manufacturer,
            title="Sample CNC Capacity",
            category=CapacityListing.Category.METAL,
            description="Illustrative machining capacity.",
            price_per_unit=Decimal("185.00"),
            minimum_quantity=75,
            production_days=11,
            availability_status=CapacityListing.AvailabilityStatus.AVAILABLE,
        )

        cls.real_user = user_model.objects.create_user(
            username="public_surface_maker",
            password="password",
            role="MANUFACTURER",
        )
        cls.real_manufacturer = ManufacturerProfile.objects.create(
            user=cls.real_user,
            business_name="Public Works",
            description="Metal parts production.",
            city="Ahmedabad",
            state="Gujarat",
            is_verified=True,
            kyc_status=ManufacturerProfile.KycStatus.APPLIED,
        )
        cls.real_listing = CapacityListing.objects.create(
            manufacturer=cls.real_manufacturer,
            title="Real Metal Capacity",
            category=CapacityListing.Category.METAL,
            description="Available production capacity.",
            price_per_unit=Decimal("125000.00"),
            minimum_quantity=1000,
            production_days=14,
            available_capacity=60000,
            capacity_period="month",
            availability_status=CapacityListing.AvailabilityStatus.AVAILABLE,
        )

    def test_marketplace_uses_real_filtered_count_and_sample_notice(self):
        response = self.client.get(reverse("marketplace"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].paginator.count, 2)
        self.assertContains(
            response,
            "Sample listings are shown for illustration and do not accept quote requests.",
        )
        self.assertContains(response, "Sample")
        self.assertNotContains(response, "Not accepting quote requests")
        self.assertContains(response, "1,25,000")
        self.assertContains(response, "60,000 units/month")

    def test_marketplace_filters_and_query_values_survive_pagination(self):
        for index in range(6):
            CapacityListing.objects.create(
                manufacturer=self.real_manufacturer,
                title=f"Capacity row {index}",
                category=CapacityListing.Category.METAL,
                description="Pune metal production.",
                minimum_quantity=1000,
                price_per_unit=Decimal("20.00"),
                production_days=5,
            )

        params = "?q=Capacity&category=METAL&location=Ahmedabad&moq=1000&max_price=200000&lead_time=20&verification=verified&sort=price&page=2"
        response = self.client.get(f"{reverse('marketplace')}{params}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].paginator.count, 7)
        self.assertEqual(response.context["page_obj"].number, 2)
        self.assertContains(response, "page=1")
        self.assertContains(response, "q=Capacity&amp;category=METAL")
        self.assertContains(response, "aria-label=\"Active filters\"")

    def test_marketplace_sample_row_has_no_quote_action_and_title_is_primary_link(self):
        response = self.client.get(reverse("marketplace"))
        content = response.content.decode()
        sample_start = content.index('data-sample-listing="true"')
        sample_end = content.index("</article>", sample_start)
        row = content[sample_start:sample_end]

        self.assertIn("Sample</span>", row)
        self.assertNotIn("request_quote", row)
        self.assertNotIn("Request a quote", row)
        self.assertIn('class="listing-image-placeholder" aria-hidden="true"', row)
        self.assertEqual(
            row.count(f'href="{reverse("listing_detail", args=[self.sample_listing.pk])}"'),
            1,
        )
        self.assertIn("View details", row)

    def test_sample_images_use_first_party_assets_on_public_surfaces(self):
        self.sample_listing.image = "demo/listings/printed-labels.webp"
        self.sample_listing.availability_status = (
            CapacityListing.AvailabilityStatus.AVAILABLE
        )
        self.sample_listing.save(update_fields=["image", "availability_status"])
        for index in range(2):
            CapacityListing.objects.create(
                manufacturer=self.real_manufacturer,
                title=f"Homepage real capacity {index}",
                category=CapacityListing.Category.METAL,
                description="Available production capacity.",
                price_per_unit=Decimal("25.00"),
                minimum_quantity=50,
                production_days=5,
                availability_status=CapacityListing.AvailabilityStatus.AVAILABLE,
            )
        CapacityListing.objects.create(
            manufacturer=self.sample_manufacturer,
            title="Homepage Sample Media",
            category=CapacityListing.Category.METAL,
            description="Illustrative sample capacity.",
            image="demo/listings/printed-labels.webp",
            price_per_unit=Decimal("18.00"),
            minimum_quantity=40,
            production_days=7,
            availability_status=CapacityListing.AvailabilityStatus.AVAILABLE,
        )
        expected_image = "/static/marketplace/images/demo/printed-labels.webp"

        for url in (
            reverse("home"),
            reverse("marketplace"),
            reverse("listing_detail", args=[self.sample_listing.pk]),
            reverse("manufacturer_profile", args=[self.sample_manufacturer.pk]),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, expected_image)
                self.assertNotContains(response, "res.cloudinary.com")

        detail = self.client.get(
            reverse("listing_detail", args=[self.sample_listing.pk]),
        )
        self.assertContains(detail, "Sample")
        self.assertNotContains(detail, "Request a quote")
        self.assertNotContains(detail, "listing-service-jsonld")

    def test_unknown_sample_image_reference_uses_immediate_fallback(self):
        self.sample_listing.image = "demo/listings/retired-sample.webp"
        self.sample_listing.save(update_fields=["image"])

        response = self.client.get(
            reverse("listing_detail", args=[self.sample_listing.pk]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "res.cloudinary.com")
        self.assertNotContains(response, "retired-sample.webp")
        self.assertContains(response, "media-no-image")
        self.assertContains(response, "detail-image-placeholder")

    def test_real_listing_image_continues_to_use_its_storage_url(self):
        self.real_listing.image = "listings/real-capacity.webp"
        self.real_listing.save(update_fields=["image"])
        expected_image = self.real_listing.image.url

        response = self.client.get(
            reverse("listing_detail", args=[self.real_listing.pk]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, expected_image)
        self.assertNotContains(response, "marketplace/images/demo/")

    def test_listing_image_alt_is_meaningful_without_repeating_the_title(self):
        self.sample_listing.machine_type = "CNC turning"
        self.sample_listing.image = "demo/listings/printed-labels.webp"
        self.sample_listing.save(update_fields=["machine_type", "image"])

        response = self.client.get(
            reverse("listing_detail", args=[self.sample_listing.pk]),
        )
        self.assertContains(response, 'alt="CNC turning manufacturing capacity image"')
        self.assertNotContains(response, 'alt="Sample CNC Capacity')

    def test_sample_listing_detail_has_no_quote_action_or_commercial_schema(self):
        response = self.client.get(
            reverse("listing_detail", args=[self.sample_listing.pk]),
        )
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Quote requests are disabled for sample data.")
        self.assertNotContains(response, "Request a quote")
        self.assertNotContains(response, "Log in to request a quote")
        self.assertContains(response, "Sample manufacturer")
        self.assertContains(response, reverse("manufacturer_profile", args=[self.sample_manufacturer.pk]))
        self.assertNotContains(response, "listing-service-jsonld")
        self.assertNotIn('"@type":"Offer"', content)

    def test_real_listing_detail_keeps_quote_action_and_omits_missing_specs(self):
        response = self.client.get(
            reverse("listing_detail", args=[self.real_listing.pk]),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Log in to request a quote")
        self.assertContains(response, "listing-service-jsonld")
        self.assertNotContains(response, "Batch price")
        self.assertContains(response, "Capacity</dt>")
        self.assertContains(response, "1,000 units")
        self.assertContains(response, "60,000 units/month")

    def test_similar_listings_are_hidden_when_no_category_match(self):
        self.sample_listing.category = CapacityListing.Category.WOOD
        self.sample_listing.save(update_fields=["category"])
        response = self.client.get(
            reverse("listing_detail", args=[self.sample_listing.pk]),
        )
        self.assertNotContains(response, "similar-listings-title")

    @override_settings(ALLOW_INDEXING=True)
    def test_sample_manufacturer_profile_is_public_noindex_and_has_no_org_schema(self):
        response = self.client.get(
            reverse("manufacturer_profile", args=[self.sample_manufacturer.pk]),
        )
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'content="noindex,follow"')
        self.assertContains(response, "Sample manufacturer")
        self.assertNotContains(response, "Verified manufacturer")
        self.assertNotContains(response, "Buyer reviews")
        self.assertNotContains(response, "Average rating")
        self.assertNotContains(response, "manufacturer-organization-jsonld")
        scripts = re.findall(
            r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
            content,
            re.DOTALL,
        )
        schemas = [json.loads(script) for script in scripts]
        self.assertFalse(any(schema.get("@type") == "Organization" for schema in schemas))

    def test_real_profile_verification_uses_public_authoritative_state(self):
        self.real_manufacturer.kyc_status = ManufacturerProfile.KycStatus.VERIFIED
        self.real_manufacturer.is_verified = False
        self.real_manufacturer.save(update_fields=["kyc_status", "is_verified"])
        response = self.client.get(
            reverse("manufacturer_profile", args=[self.real_manufacturer.pk]),
        )
        self.assertEqual(response.status_code, 404)

    def test_sample_profile_referenced_by_listing_resolves(self):
        response = self.client.get(
            reverse("manufacturer_profile", args=[self.sample_manufacturer.pk]),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("listing_detail", args=[self.sample_listing.pk]))

    def test_sample_manufacturer_is_omitted_from_sitemap(self):
        response = self.client.get(reverse("sitemap_xml"))
        sitemap = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(
            reverse("manufacturer_profile", args=[self.sample_manufacturer.pk]),
            sitemap,
        )
        self.assertIn(
            reverse("manufacturer_profile", args=[self.real_manufacturer.pk]),
            sitemap,
        )

    def test_listing_and_manufacturer_templates_emit_one_breadcrumb_schema_each(self):
        listing_response = self.client.get(
            reverse("listing_detail", args=[self.real_listing.pk]),
        )
        profile_response = self.client.get(
            reverse("manufacturer_profile", args=[self.real_manufacturer.pk]),
        )
        self.assertEqual(listing_response.content.decode().count('"@type": "BreadcrumbList"'), 1)
        self.assertEqual(profile_response.content.decode().count('"@type": "BreadcrumbList"'), 1)

