from decimal import Decimal
import json
from io import StringIO
import re
import tempfile
from pathlib import Path
from unittest.mock import PropertyMock, patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.management.base import CommandError
from django.test import Client
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.views.defaults import server_error

from .models import (
    CapacityListing,
    ManufacturerProfile,
    Milestone,
    Notification,
    Order,
    OrderMessage,
    Quotation,
    QuoteRequest,
    Review,
    SavedListing,
)
from .views import build_order_financial_summary, build_order_timeline


JSON_LD_PATTERN = re.compile(
    r'<script\b[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
    re.DOTALL,
)


def parse_json_ld(response):
    return [
        json.loads(payload)
        for payload in JSON_LD_PATTERN.findall(response.content.decode())
    ]


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class MarketplaceDiscoveryTrustTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.verified_user = User.objects.create_user(
            username="verified-maker",
            password="password",
            role="MANUFACTURER",
        )
        self.verified = ManufacturerProfile.objects.create(
            user=self.verified_user,
            business_name="Verified Works",
            city="Pune",
            state="Maharashtra",
            is_verified=True,
        )
        self.demo_user = User.objects.create_user(
            username="demo_mfr_sample",
            password="password",
            role="MANUFACTURER",
        )
        self.demo = ManufacturerProfile.objects.create(
            user=self.demo_user,
            business_name="Demo Works",
            city="Pune",
            state="Maharashtra",
            is_verified=True,
        )

    def create_listing(self, manufacturer, title, status="AVAILABLE"):
        return CapacityListing.objects.create(
            manufacturer=manufacturer,
            title=title,
            category=CapacityListing.Category.METAL,
            description="Manufacturing capacity.",
            price_per_unit=Decimal("10.00"),
            minimum_quantity=10,
            production_days=5,
            availability_status=status,
            is_active=True,
        )

    def test_saved_listing_shortlist_uses_named_controls_and_compact_facts(self):
        buyer = get_user_model().objects.create_user(
            username="shortlist-buyer",
            password="password",
            role="BUYER",
        )
        listing = self.create_listing(self.verified, "Shortlist packaging")
        SavedListing.objects.create(buyer=buyer, listing=listing)
        self.client.force_login(buyer)

        response = self.client.get(reverse("saved_listings"))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(content.count("<h1"), 1)
        self.assertContains(response, "Shortlist packaging")
        self.assertContains(response, "MOQ")
        self.assertContains(response, "Lead time")
        self.assertContains(
            response,
            f'aria-label="Remove {listing.title} from saved listings"',
        )
        self.assertContains(response, reverse("remove_saved_listing", args=[listing.pk]))
        self.assertNotContains(response, "listing-media-frame")

    def test_notifications_show_read_state_time_and_existing_open_action(self):
        buyer = get_user_model().objects.create_user(
            username="notification-buyer",
            password="password",
            role="BUYER",
        )
        notification = Notification.objects.create(
            recipient=buyer,
            message="A quotation is ready for review.",
            destination=Notification.Destination.BUYER_REQUESTS,
        )
        self.client.force_login(buyer)

        response = self.client.get(reverse("notifications"))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(content.count("<h1"), 1)
        self.assertContains(response, "Unread")
        self.assertContains(response, "datetime=")
        self.assertContains(response, "Mark all as read")
        self.assertContains(response, "Open update")
        self.assertContains(response, reverse("open_notification", args=[notification.pk]))

    def test_manufacturer_listing_forms_group_existing_fields_and_keep_post_behavior(self):
        self.client.force_login(self.verified_user)

        create_response = self.client.get(reverse("create_listing"))
        self.assertEqual(create_response.status_code, 200)
        create_content = create_response.content.decode()
        self.assertEqual(create_content.count("<h1"), 1)
        for heading in (
            "Listing basics",
            "Production capabilities",
            "Listing image",
            "Commercial details",
            "Capacity and location",
            "Availability",
        ):
            self.assertContains(create_response, heading)
        for field in (
            "title",
            "category",
            "description",
            "technical_capabilities",
            "image",
            "minimum_quantity",
            "price_per_unit",
            "batch_price",
            "production_days",
            "available_capacity",
            "capacity_period",
            "cluster",
            "availability_status",
        ):
            self.assertIn(f'name="{field}"', create_content)

        create_post = self.client.post(
            reverse("create_listing"),
            {
                "title": "Created through grouped form",
                "category": CapacityListing.Category.PACKAGING,
                "description": "Packaging capacity details.",
                "machine_type": "Offset press",
                "materials": "Corrugated board",
                "technical_capabilities": "Two-colour printing",
                "minimum_quantity": 100,
                "price_per_unit": "12.50",
                "batch_price": "",
                "production_days": 7,
                "available_capacity": "500",
                "capacity_period": "per week",
                "cluster": "Pimpri",
                "availability_status": CapacityListing.AvailabilityStatus.AVAILABLE,
            },
        )
        self.assertRedirects(create_post, reverse("manufacturer_dashboard"))
        created = CapacityListing.objects.get(title="Created through grouped form")
        self.assertEqual(created.manufacturer, self.verified)

        edit_response = self.client.get(reverse("edit_listing", args=[created.pk]))
        self.assertEqual(edit_response.status_code, 200)
        self.assertContains(edit_response, 'name="is_active"')
        edit_post = self.client.post(
            reverse("edit_listing", args=[created.pk]),
            {
                "title": "Updated through grouped form",
                "category": CapacityListing.Category.PACKAGING,
                "description": "Updated packaging capacity details.",
                "machine_type": "Offset press",
                "materials": "Corrugated board",
                "technical_capabilities": "Two-colour printing",
                "minimum_quantity": 100,
                "price_per_unit": "13.00",
                "batch_price": "",
                "production_days": 8,
                "available_capacity": "500",
                "capacity_period": "per week",
                "cluster": "Pimpri",
                "availability_status": CapacityListing.AvailabilityStatus.AVAILABLE,
                "is_active": "on",
            },
        )
        self.assertRedirects(edit_post, reverse("my_listings"))
        created.refresh_from_db()
        self.assertEqual(created.title, "Updated through grouped form")
        self.assertEqual(created.price_per_unit, Decimal("13.00"))

    def test_business_profile_editor_keeps_existing_fields_and_save_behavior(self):
        self.client.force_login(self.verified_user)
        response = self.client.get(reverse("edit_business_profile"))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(content.count("<h1"), 1)
        self.assertContains(response, "Business details")
        for field in ("business_name", "description", "city", "state"):
            self.assertIn(f'name="{field}"', content)

        response = self.client.post(
            reverse("edit_business_profile"),
            {
                "business_name": self.verified.business_name,
                "description": "Updated production capability summary.",
                "city": self.verified.city,
                "state": self.verified.state,
            },
        )
        self.assertRedirects(response, reverse("edit_business_profile"))
        self.verified.refresh_from_db()
        self.assertEqual(
            self.verified.description,
            "Updated production capability summary.",
        )
        self.assertTrue(self.verified.is_verified)

    def test_buyer_dashboard_renders_compact_summary_and_accessible_quote_decision(self):
        buyer = get_user_model().objects.create_user(
            username="dashboard-buyer",
            password="password",
            role="BUYER",
        )
        listing = self.create_listing(
            self.verified,
            "Dashboard packaging capacity",
        )
        quote_request = QuoteRequest.objects.create(
            buyer=buyer,
            listing=listing,
            quantity=500,
            requirements="Printed cartons",
            delivery_location="Pune",
        )
        Quotation.objects.create(
            quote_request=quote_request,
            quantity=500,
            price_per_unit=Decimal("18.75"),
            production_days=9,
        )
        QuoteRequest.objects.create(
            buyer=buyer,
            listing=listing,
            quantity=1000,
            requirements="A second size run",
            delivery_location="Mumbai",
            status=QuoteRequest.Status.PENDING,
        )
        SavedListing.objects.create(buyer=buyer, listing=listing)

        self.client.force_login(buyer)
        response = self.client.get(reverse("buyer_dashboard"))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(content.count("<h1"), 1)
        self.assertContains(response, "Needs your attention")
        self.assertContains(response, "Dashboard packaging capacity")
        self.assertContains(response, "Awaiting your decision")
        self.assertContains(response, "Pending")
        self.assertContains(response, "Saved listings")
        self.assertContains(
            response,
            'aria-label="Accept quotation for Dashboard packaging capacity"',
        )
        self.assertContains(
            response,
            'aria-label="Decline quotation for Dashboard packaging capacity"',
        )
        self.assertNotIn("trade ledger", content.lower())
        self.assertNotIn("capacity register", content.lower())

    def test_new_buyer_dashboard_has_useful_empty_states(self):
        buyer = get_user_model().objects.create_user(
            username="new-dashboard-buyer",
            password="password",
            role="BUYER",
        )
        self.client.force_login(buyer)

        response = self.client.get(reverse("buyer_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nothing waiting for your decision")
        self.assertContains(response, "No quote requests yet")
        self.assertContains(response, "No orders in progress")
        self.assertContains(response, "No accepted quotations yet")
        self.assertContains(response, "No saved listings yet")
        self.assertContains(response, "No notifications yet")

    def test_manufacturer_dashboard_prioritizes_owned_requests_and_work(self):
        buyer = get_user_model().objects.create_user(
            username="dashboard-request-buyer",
            password="password",
            role="BUYER",
        )
        pending_listing = self.create_listing(
            self.verified,
            "Dashboard packaging capacity",
        )
        pending_request = QuoteRequest.objects.create(
            buyer=buyer,
            listing=pending_listing,
            quantity=500,
            requirements="Printed cartons in two sizes.",
            delivery_location="Pune",
        )

        accepted_listing = self.create_listing(
            self.verified,
            "Dashboard metal components",
        )
        accepted_request = QuoteRequest.objects.create(
            buyer=buyer,
            listing=accepted_listing,
            quantity=300,
            requirements="Low-volume component batch.",
            delivery_location="Mumbai",
            status=QuoteRequest.Status.ACCEPTED,
        )
        accepted_quotation = Quotation.objects.create(
            quote_request=accepted_request,
            quantity=300,
            price_per_unit=Decimal("42.00"),
            production_days=12,
            status=Quotation.Status.ACCEPTED,
        )
        order = Order.objects.create(
            quotation=accepted_quotation,
            buyer=buyer,
            manufacturer=self.verified,
            listing=accepted_listing,
            quantity=300,
            agreed_unit_price=Decimal("42.00"),
            total_amount=Decimal("12600.00"),
            agreed_production_days=12,
            status=Order.Status.IN_PRODUCTION,
        )
        Milestone.objects.create(
            order=order,
            title="Begin first production batch",
            percentage=50,
            amount=Decimal("6300.00"),
            status=Milestone.Status.PENDING,
            funding_status=Milestone.FundingStatus.FUNDED,
        )
        Milestone.objects.create(
            order=order,
            title="Submit production sample",
            percentage=50,
            amount=Decimal("6300.00"),
            status=Milestone.Status.IN_PROGRESS,
            funding_status=Milestone.FundingStatus.FUNDED,
        )

        other_manufacturer_user = get_user_model().objects.create_user(
            username="other-dashboard-maker",
            password="password",
            role="MANUFACTURER",
        )
        other_manufacturer = ManufacturerProfile.objects.create(
            user=other_manufacturer_user,
            business_name="Other Dashboard Works",
            city="Jaipur",
            state="Rajasthan",
        )
        other_listing = self.create_listing(
            other_manufacturer,
            "Another maker's private request",
        )
        QuoteRequest.objects.create(
            buyer=buyer,
            listing=other_listing,
            quantity=100,
            requirements="Private to another manufacturer.",
            delivery_location="Jaipur",
        )

        self.client.force_login(self.verified_user)
        response = self.client.get(reverse("manufacturer_dashboard"))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(content.count("<h1"), 1)
        self.assertContains(response, "Verified manufacturer")
        self.assertContains(response, "Pending requests")
        self.assertContains(response, "Dashboard packaging capacity")
        self.assertContains(response, "Printed cartons in two sizes.")
        self.assertContains(
            response,
            'aria-label="Send quotation for Dashboard packaging capacity"',
        )
        self.assertContains(
            response,
            'aria-label="Accept request for Dashboard packaging capacity"',
        )
        self.assertContains(response, "Quotation sent")
        self.assertContains(response, "Quote total")
        self.assertContains(response, "12 days")
        self.assertContains(response, "Orders in progress")
        self.assertContains(response, "Milestones to update")
        self.assertContains(response, "Start milestone")
        self.assertContains(response, "Submit for approval")
        self.assertContains(response, "Your listings")
        self.assertNotContains(response, "Another maker&#x27;s private request")

        self.client.force_login(buyer)
        self.assertEqual(
            self.client.get(reverse("manufacturer_dashboard")).status_code,
            403,
        )

    def test_sparse_manufacturer_dashboard_surfaces_profile_and_first_listing(self):
        manufacturer_user = get_user_model().objects.create_user(
            username="sparse-dashboard-maker",
            password="password",
            role="MANUFACTURER",
        )
        ManufacturerProfile.objects.create(
            user=manufacturer_user,
            business_name="Sparse Dashboard Works",
            city="Indore",
            state="Madhya Pradesh",
            kyc_status=ManufacturerProfile.KycStatus.UNDER_REVIEW,
        )
        self.client.force_login(manufacturer_user)

        response = self.client.get(reverse("manufacturer_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Under review")
        self.assertContains(response, "Listings become public after verification.")
        self.assertContains(response, "You haven")
        self.assertContains(response, "listed any manufacturing capacity yet")
        self.assertContains(response, "Create your first listing")
        self.assertNotContains(response, "No production actions right now")
        self.assertNotContains(response, "No active production orders")

    def create_review(self, manufacturer, buyer_username, comment):
        buyer = get_user_model().objects.create_user(
            username=buyer_username,
            password="password",
            role="BUYER",
        )
        listing = self.create_listing(
            manufacturer,
            f"Completed capacity for {buyer_username}",
        )
        quote_request = QuoteRequest.objects.create(
            buyer=buyer,
            listing=listing,
            quantity=10,
            requirements="Completed order requirements",
            delivery_location="Mumbai",
            status=QuoteRequest.Status.ACCEPTED,
        )
        quotation = Quotation.objects.create(
            quote_request=quote_request,
            price_per_unit=Decimal("10.00"),
            quantity=10,
            production_days=5,
            status=Quotation.Status.ACCEPTED,
        )
        order = Order.objects.create(
            quotation=quotation,
            buyer=buyer,
            manufacturer=manufacturer,
            listing=listing,
            quantity=10,
            agreed_unit_price=Decimal("10.00"),
            total_amount=Decimal("100.00"),
            agreed_production_days=5,
            status=Order.Status.COMPLETED,
        )
        Review.objects.create(
            order=order,
            buyer=buyer,
            manufacturer=manufacturer,
            quality_rating=5,
            timeliness_rating=5,
            communication_rating=5,
            overall_rating=5,
            comment=comment,
        )
        return listing

    def test_sample_quote_endpoint_rejects_get_and_post_without_records(self):
        buyer = get_user_model().objects.create_user(
            username="sample-quote-buyer",
            password="password",
            role="BUYER",
        )
        listing = self.create_listing(self.demo, "Sample-only capacity")
        url = reverse("request_quote", args=[listing.pk])
        self.client.force_login(buyer)

        response = self.client.get(url, follow=True)
        self.assertContains(
            response,
            "This is a sample listing and is not accepting quote requests.",
        )
        self.assertEqual(QuoteRequest.objects.filter(listing=listing).count(), 0)
        self.assertFalse(
            Notification.objects.filter(recipient=self.demo_user).exists()
        )

        response = self.client.post(
            url,
            {
                "quantity": 10,
                "requirements": "Do not persist this sample request",
                "delivery_location": "Mumbai",
            },
            follow=True,
        )
        self.assertContains(
            response,
            "This is a sample listing and is not accepting quote requests.",
        )
        self.assertEqual(QuoteRequest.objects.filter(listing=listing).count(), 0)
        self.assertFalse(
            Notification.objects.filter(recipient=self.demo_user).exists()
        )

    def test_real_listing_quote_flow_still_creates_request_and_notification(self):
        buyer = get_user_model().objects.create_user(
            username="real-quote-buyer",
            password="password",
            role="BUYER",
        )
        listing = self.create_listing(self.verified, "Real capacity")
        self.client.force_login(buyer)

        response = self.client.post(
            reverse("request_quote", args=[listing.pk]),
            {
                "quantity": 10,
                "requirements": "Production order requirements",
                "delivery_location": "Mumbai",
            },
        )

        self.assertRedirects(
            response,
            reverse("request_quote", args=[listing.pk]),
        )
        quote = QuoteRequest.objects.get(listing=listing, buyer=buyer)
        self.assertEqual(quote.requirements, "Production order requirements")
        self.assertTrue(
            Notification.objects.filter(recipient=self.verified_user).exists()
        )

    def test_quote_request_and_quotation_pages_show_context_and_real_fields(self):
        buyer = get_user_model().objects.create_user(
            username="workflow-page-buyer",
            password="password",
            role="BUYER",
        )
        listing = self.create_listing(
            self.verified,
            "Workflow corrugated packaging",
        )
        quote_request = QuoteRequest.objects.create(
            buyer=buyer,
            listing=listing,
            quantity=500,
            requirements="Printed cartons with two colours.",
            delivery_location="Pune",
        )

        self.client.force_login(buyer)
        request_page = self.client.get(
            reverse("request_quote", args=[listing.pk]),
        )
        self.assertEqual(request_page.status_code, 200)
        self.assertEqual(request_page.content.decode().count("<h1"), 1)
        self.assertContains(request_page, "Minimum order")
        self.assertContains(request_page, "Lead time")
        self.assertContains(request_page, "Order requirement")
        self.assertContains(request_page, 'name="quantity"')
        self.assertContains(request_page, 'name="requirements"')
        self.assertContains(request_page, 'name="delivery_location"')
        self.assertContains(request_page, "Request quote")

        self.client.force_login(self.verified_user)
        quotation_page = self.client.get(
            reverse("send_quotation", args=[quote_request.pk]),
        )
        self.assertEqual(quotation_page.status_code, 200)
        self.assertEqual(quotation_page.content.decode().count("<h1"), 1)
        self.assertContains(quotation_page, "Buyer request")
        self.assertContains(quotation_page, "Printed cartons with two colours.")
        self.assertContains(quotation_page, "Pricing")
        self.assertContains(quotation_page, "Production")
        self.assertContains(quotation_page, "Message to buyer")
        self.assertContains(quotation_page, 'name="price_per_unit"')
        self.assertContains(quotation_page, 'name="production_days"')
        self.assertContains(quotation_page, 'name="message"')
        self.assertNotContains(quotation_page, 'name="quantity"')

    def test_sample_listing_card_and_detail_have_no_active_quote_cta(self):
        listing = self.create_listing(self.demo, "Sample CTA capacity")
        quote_url = reverse("request_quote", args=[listing.pk])

        home_response = self.client.get(reverse("marketplace"))
        self.assertContains(
            home_response,
            "Sample listings are shown for illustration and do not accept quote requests.",
        )
        self.assertNotContains(home_response, f'href="{quote_url}">Request quote</a>')
        self.assertNotContains(home_response, "Not accepting quote requests")

        detail_response = self.client.get(
            reverse("listing_detail", args=[listing.pk])
        )
        self.assertContains(
            detail_response,
            "Quote requests are disabled for sample data.",
        )
        self.assertNotContains(detail_response, f'href="{quote_url}"')

    def test_sample_profile_hides_reviews_and_real_profile_reviews_remain_visible(self):
        self.create_review(
            self.demo,
            "sample-review-buyer",
            "Fictional sample review text must stay private.",
        )
        real_comment = "Genuine completed order review remains visible."
        self.create_review(self.verified, "real-review-buyer", real_comment)

        sample_response = self.client.get(
            reverse("manufacturer_profile", args=[self.demo.pk])
        )
        self.assertNotContains(sample_response, "Buyer reviews")
        self.assertNotContains(sample_response, "Average rating:")
        self.assertNotContains(
            sample_response,
            "Fictional sample review text must stay private.",
        )
        self.assertNotContains(sample_response, "5.0/5")

        real_response = self.client.get(
            reverse("manufacturer_profile", args=[self.verified.pk])
        )
        self.assertContains(real_response, "Buyer reviews")
        self.assertContains(real_response, "Average rating:")
        self.assertContains(real_response, real_comment)

    @override_settings(ALLOW_INDEXING=True)
    def test_marketplace_page_two_has_page_title_and_self_canonical(self):
        for index in range(7):
            self.create_listing(self.verified, f"Capacity {index}")

        response = self.client.get(reverse("marketplace"), {"page": 2})
        content = response.content.decode()

        self.assertIn("Page 2", content.split("<title>", 1)[1].split("</title>", 1)[0])
        self.assertIn('href="https://ubhaar-vyapaar.in/marketplace/?page=2"', content)

    @override_settings(ALLOW_INDEXING=True)
    def test_search_url_is_noindex_follow_and_canonicalizes_to_marketplace(self):
        response = self.client.get(reverse("marketplace"), {"q": "steel"})
        content = response.content.decode()

        self.assertIn('<meta name="robots" content="noindex, follow">', content)
        self.assertIn('href="https://ubhaar-vyapaar.in/marketplace/"', content)

    @override_settings(ALLOW_INDEXING=True)
    def test_clean_marketplace_url_has_no_filtered_page_noindex(self):
        response = self.client.get(reverse("marketplace"))

        self.assertNotContains(response, 'name="robots" content="noindex, follow"')
        self.assertContains(response, 'href="https://ubhaar-vyapaar.in/marketplace/"')

    @override_settings(ALLOW_INDEXING=True)
    def test_plain_root_is_an_indexable_distinct_landing_page(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="https://ubhaar-vyapaar.in/"')
        self.assertContains(response, "Browse capacity")
        self.assertNotContains(response, 'name="robots" content="noindex')

    def test_root_marketplace_query_redirects_permanently_and_preserves_raw_query(self):
        category_response = self.client.get("/?category=METAL")
        self.assertEqual(category_response.status_code, 301)
        self.assertEqual(category_response["Location"], "/marketplace/?category=METAL")

        query_string = "q=packaging&location=Mumbai&page=2&empty=&source=a%20b"
        response = self.client.get(f"/?{query_string}")

        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], f"/marketplace/?{query_string}")

    def test_root_redirects_for_empty_marketplace_parameters_without_redirect_loop(self):
        response = self.client.get("/?q=&category=")

        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], "/marketplace/?q=&category=")
        marketplace_response = self.client.get(response["Location"])
        self.assertEqual(marketplace_response.status_code, 200)

    def test_marketplace_filters_remain_functional_on_new_route(self):
        matching = self.create_listing(self.verified, "Packaging filter match")
        demo_match = self.create_listing(self.demo, "Packaging demo match")

        response = self.client.get(
            reverse("marketplace"),
            {
                "q": "Packaging",
                "category": "METAL",
                "location": "Pune",
                "moq": "10",
                "max_price": "10.00",
                "lead_time": "5",
                "verification": "verified",
                "sort": "price",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["listings"].object_list), [matching])
        self.assertNotIn(demo_match, response.context["listings"].object_list)

    def test_marketplace_page_two_remains_available_and_self_canonical(self):
        for index in range(7):
            self.create_listing(self.verified, f"Paged capacity {index}")

        response = self.client.get(reverse("marketplace"), {"page": 2})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].number, 2)
        self.assertContains(response, 'href="https://ubhaar-vyapaar.in/marketplace/?page=2"')

    @override_settings(ALLOW_INDEXING=True)
    def test_pagination_drops_empty_and_default_parameters(self):
        for index in range(7):
            self.create_listing(self.verified, f"Steel capacity {index}")

        response = self.client.get(
            reverse("marketplace"),
            {"q": "steel", "sort": "newest", "category": "", "page": 1},
        )

        self.assertContains(response, 'href="?q=steel&amp;page=2"')
        content = response.content.decode()
        pagination = content.split(
            '<nav class="pagination marketplace-pagination"', 1
        )[1].split("</nav>", 1)[0]
        self.assertNotRegex(pagination, r'href="\?[^\"]*(?:sort=newest|category=)')

    @override_settings(ALLOW_INDEXING=True)
    def test_shared_social_tags_render_and_listing_image_is_used(self):
        listing = self.create_listing(self.verified, "Steel fabrication")
        listing.image = "listings/steel-fabrication.jpg"
        listing.save(update_fields=["image"])

        response = self.client.get(reverse("listing_detail", args=[listing.pk]))

        self.assertContains(response, 'property="og:title"')
        self.assertContains(response, 'property="og:description"')
        self.assertContains(response, 'property="og:url"')
        self.assertContains(response, 'property="og:type" content="website"')
        self.assertContains(response, 'name="twitter:card" content="summary_large_image"')
        self.assertContains(response, 'name="twitter:title"')
        self.assertContains(response, 'name="twitter:description"')
        self.assertContains(response, 'name="twitter:image"')
        self.assertContains(
            response,
            'property="og:image" content="https://ubhaar-vyapaar.in/media/listings/steel-fabrication.jpg"',
        )
        self.assertContains(
            response,
            'name="twitter:image" content="https://ubhaar-vyapaar.in/media/listings/steel-fabrication.jpg"',
        )
        self.assertNotContains(response, 'property="og:image:width"')
        self.assertNotContains(response, 'property="og:image:height"')

    @override_settings(ALLOW_INDEXING=True)
    def test_social_image_falls_back_to_branded_share_image_without_listing_image(self):
        listing = self.create_listing(self.verified, "Steel fabrication")

        response = self.client.get(reverse("listing_detail", args=[listing.pk]))

        self.assertContains(
            response,
            'property="og:image" content="https://ubhaar-vyapaar.in/static/marketplace/images/brand/social-share.png"',
        )
        self.assertContains(
            response,
            'name="twitter:image" content="https://ubhaar-vyapaar.in/static/marketplace/images/brand/social-share.png"',
        )
        self.assertContains(response, 'property="og:image:width" content="1200"')
        self.assertContains(response, 'property="og:image:height" content="630"')

    @override_settings(ALLOW_INDEXING=True)
    def test_default_public_page_uses_absolute_branded_share_image(self):
        response = self.client.get(reverse("home"))

        self.assertContains(
            response,
            'property="og:image" content="https://ubhaar-vyapaar.in/static/marketplace/images/brand/social-share.png"',
        )
        self.assertContains(
            response,
            'name="twitter:image" content="https://ubhaar-vyapaar.in/static/marketplace/images/brand/social-share.png"',
        )
        self.assertContains(response, 'property="og:image:width" content="1200"')
        self.assertContains(response, 'property="og:image:height" content="630"')

    @override_settings(ALLOW_INDEXING=True, LEGAL_CONTACT_EMAIL="")
    def test_homepage_emits_parseable_organization_and_website_schema(self):
        response = self.client.get(reverse("home"))
        schemas = parse_json_ld(response)

        organization = next(item for item in schemas if item["@type"] == "Organization")
        website = next(item for item in schemas if item["@type"] == "WebSite")

        self.assertEqual(organization["name"], "Ubhaar-Vyapaar")
        self.assertEqual(organization["url"], "https://ubhaar-vyapaar.in/")
        self.assertTrue(organization["logo"].startswith("https://ubhaar-vyapaar.in/"))
        self.assertNotIn("email", organization)
        self.assertEqual(website["name"], "Ubhaar-Vyapaar")
        self.assertEqual(website["alternateName"], "Ubhaar Vyapaar")
        self.assertEqual(website["url"], "https://ubhaar-vyapaar.in/")

    @override_settings(ALLOW_INDEXING=True, LEGAL_CONTACT_EMAIL="schema@ubhaar-vyapaar.in")
    def test_homepage_includes_configured_real_organization_email(self):
        schemas = parse_json_ld(self.client.get(reverse("home")))
        organization = next(item for item in schemas if item["@type"] == "Organization")

        self.assertEqual(organization["email"], "schema@ubhaar-vyapaar.in")

    @override_settings(ALLOW_INDEXING=True, LEGAL_CONTACT_EMAIL="support@example.com")
    def test_homepage_omits_placeholder_organization_email(self):
        schemas = parse_json_ld(self.client.get(reverse("home")))
        organization = next(item for item in schemas if item["@type"] == "Organization")

        self.assertNotIn("email", organization)

    @override_settings(ALLOW_INDEXING=True)
    def test_listing_schema_uses_real_values_and_safe_json_serialization(self):
        description = 'Machine makes "parts" </script><script>alert("x")</script> & more.'
        listing = self.create_listing(self.verified, "Precision parts")
        listing.description = description
        listing.image = "listings/precision-parts.jpg"
        listing.save(update_fields=["description", "image"])

        response = self.client.get(reverse("listing_detail", args=[listing.pk]))
        schemas = parse_json_ld(response)
        service = next(item for item in schemas if item["@type"] == "Service")
        breadcrumb = next(item for item in schemas if item["@type"] == "BreadcrumbList")

        self.assertEqual(service["name"], listing.title)
        self.assertEqual(service["description"], description)
        self.assertEqual(service["provider"]["name"], self.verified.business_name)
        self.assertEqual(service["image"], "https://ubhaar-vyapaar.in/media/listings/precision-parts.jpg")
        self.assertEqual(service["url"], f"https://ubhaar-vyapaar.in{reverse('listing_detail', args=[listing.pk])}")
        self.assertEqual([item["position"] for item in breadcrumb["itemListElement"]], [1, 2])
        self.assertEqual(breadcrumb["itemListElement"][0]["item"], "https://ubhaar-vyapaar.in/marketplace/")
        self.assertEqual(breadcrumb["itemListElement"][1]["item"], service["url"])
        self.assertNotIn("</script><script>alert", response.content.decode())
        self.assertNotIn("Product", str(schemas))
        self.assertNotIn("AggregateRating", str(schemas))
        self.assertNotIn("ratingValue", str(schemas))
        self.assertNotIn("reviewCount", str(schemas))

    @override_settings(ALLOW_INDEXING=True)
    def test_listing_with_nonpositive_price_has_no_offer(self):
        listing = self.create_listing(self.verified, "Price pending")
        listing.price_per_unit = Decimal("0.00")
        listing.save(update_fields=["price_per_unit"])

        schemas = parse_json_ld(self.client.get(reverse("listing_detail", args=[listing.pk])))
        service = next(item for item in schemas if item["@type"] == "Service")

        self.assertNotIn("offers", service)

    @override_settings(ALLOW_INDEXING=True)
    def test_paused_listing_has_no_offer(self):
        listing = self.create_listing(
            self.verified,
            "Temporarily paused capacity",
            CapacityListing.AvailabilityStatus.PAUSED,
        )

        schemas = parse_json_ld(self.client.get(reverse("listing_detail", args=[listing.pk])))
        service = next(item for item in schemas if item["@type"] == "Service")

        self.assertNotIn("offers", service)

    @override_settings(ALLOW_INDEXING=True)
    def test_real_active_listing_has_semantically_per_unit_inr_offer(self):
        listing = self.create_listing(self.verified, "Available fabrication")
        listing.price_per_unit = Decimal("12.50")
        listing.availability_status = CapacityListing.AvailabilityStatus.LIMITED
        listing.save(update_fields=["price_per_unit", "availability_status"])

        schemas = parse_json_ld(self.client.get(reverse("listing_detail", args=[listing.pk])))
        service = next(item for item in schemas if item["@type"] == "Service")
        offer = service["offers"]

        self.assertEqual(offer["@type"], "Offer")
        self.assertEqual(offer["price"], "12.50")
        self.assertEqual(offer["priceCurrency"], "INR")
        self.assertEqual(offer["availability"], "https://schema.org/LimitedAvailability")
        self.assertEqual(offer["priceSpecification"]["@type"], "UnitPriceSpecification")
        self.assertEqual(offer["priceSpecification"]["unitText"], "unit")

    @override_settings(ALLOW_INDEXING=True)
    def test_sample_listing_has_no_offer_or_false_verification_claim(self):
        listing = self.create_listing(self.demo, "Sample capacity")

        schemas = parse_json_ld(self.client.get(reverse("listing_detail", args=[listing.pk])))
        self.assertFalse(any(item["@type"] == "Service" for item in schemas))
        self.assertFalse(any(item["@type"] == "Product" for item in schemas))
        self.assertFalse(any(item["@type"] == "Offer" for item in schemas))
        self.assertNotIn("isVerified", str(schemas))
        self.assertNotIn("verified", str(schemas).lower())

    @override_settings(ALLOW_INDEXING=True)
    def test_manufacturer_profile_emits_parseable_organization_and_breadcrumb(self):
        response = self.client.get(reverse("manufacturer_profile", args=[self.verified.pk]))
        schemas = parse_json_ld(response)
        organization = next(item for item in schemas if item["@type"] == "Organization")
        breadcrumb = next(item for item in schemas if item["@type"] == "BreadcrumbList")

        self.assertEqual(organization["name"], self.verified.business_name)
        self.assertEqual(organization["url"], f"https://ubhaar-vyapaar.in{reverse('manufacturer_profile', args=[self.verified.pk])}")
        self.assertEqual([item["position"] for item in breadcrumb["itemListElement"]], [1, 2])
        self.assertEqual(breadcrumb["itemListElement"][1]["name"], self.verified.business_name)
        self.assertNotIn("isVerified", str(schemas))

    @override_settings(ALLOW_INDEXING=True)
    def test_sample_manufacturer_profile_does_not_claim_verification(self):
        response = self.client.get(reverse("manufacturer_profile", args=[self.demo.pk]))
        schemas = parse_json_ld(response)
        self.assertFalse(any(item["@type"] == "Organization" for item in schemas))
        self.assertTrue(any(item["@type"] == "BreadcrumbList" for item in schemas))
        self.assertContains(response, "Sample manufacturer")
        self.assertNotIn("isVerified", str(schemas))
        self.assertNotIn("verified", str(schemas).lower())

    def test_paused_listings_follow_available_listings_in_default_discovery(self):
        paused = self.create_listing(
            self.verified,
            "Paused capacity",
            CapacityListing.AvailabilityStatus.PAUSED,
        )
        available = self.create_listing(self.verified, "Available capacity")

        response = self.client.get(reverse("marketplace"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(response.context["listings"].object_list),
            [available, paused],
        )
        self.assertContains(response, "Paused")

    def test_zero_count_categories_are_hidden_and_note_is_shown(self):
        self.create_listing(self.verified, "Metal capacity")

        response = self.client.get(reverse("marketplace"))

        self.assertContains(response, "Metal")
        self.assertNotContains(response, "Plastics")
        self.assertNotContains(response, "More categories will appear")
        self.assertNotContains(response, "coming soon")

    def test_empty_marketplace_uses_present_state_copy(self):
        response = self.client.get(reverse("marketplace"))

        self.assertContains(response, "No active listings are available right now")
        self.assertNotContains(response, "coming soon")

    def test_verified_badge_requires_real_state_and_demo_content_is_marked(self):
        self.create_listing(self.verified, "Verified capacity")
        self.create_listing(self.demo, "Demo capacity")

        response = self.client.get(reverse("marketplace"))
        content = response.content.decode()

        self.assertIn('class="trust-badge">Verified</span>', content)
        self.assertIn('class="sample-badge">Sample</span>', content)

    def test_kyc_status_alone_does_not_earn_public_verified_badge(self):
        profile = ManufacturerProfile.objects.create(
            user=get_user_model().objects.create_user(
                username="kyc-only-maker",
                password="password",
                role="MANUFACTURER",
            ),
            business_name="KYC Only Works",
            city="Pune",
            state="Maharashtra",
            is_verified=False,
            kyc_status=ManufacturerProfile.KycStatus.VERIFIED,
        )

        self.assertNotIn("Verified Manufacturer", profile.earned_badges)
        self.assertFalse(profile.is_publicly_verified)

        listing = self.create_listing(profile, "KYC-only capacity")
        for route in (
            reverse("marketplace"),
            reverse("listing_detail", args=[listing.pk]),
            reverse("manufacturer_profile", args=[profile.pk]),
        ):
            with self.subTest(route=route):
                response = self.client.get(route)
                content = response.content.decode()
                self.assertNotIn('class="trust-badge">Verified', content)
                self.assertNotIn("Verified Manufacturer", content)

    def test_sample_account_never_gets_public_verified_badge_even_if_flagged(self):
        self.demo.is_verified = True
        self.demo.kyc_status = ManufacturerProfile.KycStatus.VERIFIED
        self.demo.save(update_fields=["is_verified", "kyc_status"])
        listing = self.create_listing(self.demo, "Sample verified flag capacity")

        self.assertNotIn("Verified Manufacturer", self.demo.earned_badges)
        self.assertFalse(self.demo.is_publicly_verified)
        for route in (
            reverse("marketplace"),
            reverse("listing_detail", args=[listing.pk]),
            reverse("manufacturer_profile", args=[self.demo.pk]),
        ):
            with self.subTest(route=route):
                response = self.client.get(route)
                content = response.content.decode()
                self.assertNotIn('class="trust-badge">Verified', content)
                self.assertNotIn("Verified Manufacturer", content)

        self.client.force_login(self.demo_user)
        for route in (
            reverse("manufacturer_dashboard"),
            reverse("edit_business_profile"),
        ):
            with self.subTest(route=route):
                content = self.client.get(route).content.decode()
                self.assertNotIn('class="trust-badge">Verified', content)
                self.assertNotIn("Verified business", content)

    def test_non_sample_authoritative_flag_displays_public_verified_badge(self):
        listing = self.create_listing(self.verified, "Verified flag capacity")

        for route in (
            reverse("marketplace"),
            reverse("listing_detail", args=[listing.pk]),
            reverse("manufacturer_profile", args=[self.verified.pk]),
        ):
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertContains(response, 'class="trust-badge">Verified')

    def test_top_rated_badge_logic_is_unchanged(self):
        with (
            patch.object(
                ManufacturerProfile,
                "average_rating",
                new_callable=PropertyMock,
                return_value=Decimal("4.8"),
            ),
            patch.object(
                ManufacturerProfile,
                "review_count",
                new_callable=PropertyMock,
                return_value=10,
            ),
        ):
            badges = self.verified.earned_badges

        self.assertIn("Top Rated", badges)

    def test_public_information_routes_and_trust_links_render(self):
        route_names = (
            "about",
            "contact",
            "pricing_fees",
            "trust_safety",
            "how_it_works",
            "for_manufacturers",
            "faq",
            "grievance_redressal",
        )

        for route_name in route_names:
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))
                self.assertEqual(response.status_code, 200)

        response = self.client.get(reverse("marketplace"))
        self.assertContains(response, reverse("trust_safety"))
        self.assertContains(response, reverse("about"))
        self.assertContains(response, reverse("contact"))
        self.assertContains(response, reverse("pricing_fees"))
        self.assertContains(response, reverse("faq"))


class PublicWorkflowEducationPageTests(TestCase):
    def assertSingleH1(self, response):
        html = response.content.decode()
        self.assertEqual(len(re.findall(r"<h1\b", html, re.IGNORECASE)), 1)

    def test_how_it_works_explains_buyer_and_manufacturer_flows(self):
        response = self.client.get(reverse("how_it_works"))

        self.assertEqual(response.status_code, 200)
        self.assertSingleH1(response)
        self.assertContains(response, 'rel="canonical"')
        self.assertContains(response, 'property="og:title" content="How it works | Ubhaar-Vyapaar"')
        self.assertContains(response, "From manufacturing need to order updates")
        for label in (
            "Browse capacity",
            "Review the listing",
            "Request a quotation",
            "Review the quotation",
            "Manage accepted orders",
            "Quote request",
            "Manufacturer quotation",
            "Buyer decision",
            "Early-access pilot",
            "Sample listings",
            "simulated",
            "real payment processing or escrow",
        ):
            with self.subTest(label=label):
                self.assertContains(response, label)
        self.assertContains(response, reverse("marketplace"))
        self.assertContains(response, reverse("register_manufacturer"))
        self.assertNotContains(response, "On this page")
        self.assertNotContains(response, "Free during the pilot")

    def test_manufacturer_page_uses_existing_routes_and_careful_verification_copy(self):
        response = self.client.get(reverse("for_manufacturers"))

        self.assertEqual(response.status_code, 200)
        self.assertSingleH1(response)
        self.assertContains(response, 'rel="canonical"')
        self.assertContains(response, 'property="og:title" content="For manufacturers | Ubhaar-Vyapaar"')
        for label in (
            "List spare capacity",
            "Set practical terms upfront",
            "Respond with a quotation",
            "Follow accepted orders",
            "Create a manufacturer account",
            "How verification is shown",
            "A KYC status alone does not display the badge",
            "not a certification, product inspection, or guarantee",
            "Early-access pilot",
            "Sample listings",
        ):
            with self.subTest(label=label):
                self.assertContains(response, label)
        self.assertContains(response, reverse("trust_safety"))
        self.assertContains(response, reverse("register_manufacturer"))
        self.assertNotContains(response, "On this page")
        self.assertNotContains(response, "Approved within")
        self.assertNotContains(response, "guaranteed approval")

    @override_settings(
        MANUFACTURER_REQUIRED_DOCUMENTS=[],
        MANUFACTURER_REVIEW_TIME="",
    )
    def test_unconfigured_manufacturer_requirements_and_review_time_are_hidden(self):
        response = self.client.get(reverse("for_manufacturers"))

        self.assertNotContains(response, "Configured document requirements")
        self.assertNotContains(response, "Expected review time")

    @override_settings(
        MANUFACTURER_REQUIRED_DOCUMENTS=["Business registration"],
        MANUFACTURER_REVIEW_TIME="5 working days",
    )
    def test_configured_manufacturer_requirements_and_review_time_are_shown(self):
        response = self.client.get(reverse("for_manufacturers"))

        self.assertContains(response, "Configured document requirements")
        self.assertContains(response, "Business registration")
        self.assertContains(response, "Expected review time: 5 working days")


class SeededSampleNameTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.TemporaryDirectory()
        self.override = override_settings(
            MEDIA_ROOT=self.media_root.name,
            ALLOW_DEMO_SEEDING=True,
            STORAGES={
                "default": {
                    "BACKEND": "django.core.files.storage.FileSystemStorage",
                },
                "staticfiles": {
                    "BACKEND": (
                        "django.contrib.staticfiles.storage.StaticFilesStorage"
                    ),
                },
            },
            PASSWORD_HASHERS=[
                "django.contrib.auth.hashers.MD5PasswordHasher",
            ],
        )
        self.override.enable()

    def tearDown(self):
        self.override.disable()
        self.media_root.cleanup()

    def test_seeded_names_stay_sample_classified_and_cleanup_is_idempotent(self):
        call_command("seed_demo_data", stdout=StringIO())
        self.assertEqual(list(Path(self.media_root.name).iterdir()), [])

        profiles = ManufacturerProfile.objects.filter(
            user__username__startswith="demo_mfr_"
        ).order_by("user__username")
        names = list(profiles.values_list("business_name", flat=True))

        self.assertEqual(profiles.count(), 5)
        self.assertTrue(all(profile.is_demo for profile in profiles))
        self.assertTrue(all(not name.startswith("Demo ") for name in names))
        self.assertTrue(all(not profile.is_verified for profile in profiles))

        legacy_profile = profiles.first()
        legacy_profile.business_name = f"Demo {legacy_profile.business_name}"
        legacy_profile.save(update_fields=["business_name"])

        call_command("seed_demo_data", stdout=StringIO())

        refreshed = ManufacturerProfile.objects.get(pk=legacy_profile.pk)
        self.assertFalse(refreshed.business_name.startswith("Demo "))
        self.assertEqual(
            ManufacturerProfile.objects.filter(
                user__username__startswith="demo_mfr_"
            ).count(),
            5,
        )

        response = self.client.get(reverse("marketplace"))
        self.assertContains(response, "Sample listing")
        self.assertNotContains(response, "Verified business")
        self.assertNotContains(response, "Demo ")

    def test_non_seed_manufacturer_name_is_untouched_by_seed_cleanup(self):
        User = get_user_model()
        user = User.objects.create_user(
            username="production-maker",
            password="password",
            role="MANUFACTURER",
        )
        profile = ManufacturerProfile.objects.create(
            user=user,
            business_name="Demo Genuine Works",
            city="Pune",
            state="Maharashtra",
            is_verified=True,
        )

        call_command("seed_demo_data", stdout=StringIO())

        profile.refresh_from_db()
        self.assertEqual(profile.business_name, "Demo Genuine Works")


class ProductionReadinessTests(TestCase):
    @override_settings(GOOGLE_SITE_VERIFICATION="", BING_SITE_VERIFICATION="")
    def test_search_engine_verification_tags_are_omitted_when_unset(self):
        response = self.client.get(reverse("home"))

        self.assertNotContains(response, 'name="google-site-verification"')
        self.assertNotContains(response, 'name="msvalidate.01"')

    @override_settings(GOOGLE_SITE_VERIFICATION="google-site-token")
    def test_google_site_verification_tag_renders_when_configured(self):
        response = self.client.get(reverse("home"))

        self.assertContains(
            response,
            '<meta name="google-site-verification" content="google-site-token">',
        )

    @override_settings(BING_SITE_VERIFICATION="bing-site-token")
    def test_bing_site_verification_tag_renders_when_configured(self):
        response = self.client.get(reverse("home"))

        self.assertContains(
            response,
            '<meta name="msvalidate.01" content="bing-site-token">',
        )

    @override_settings(GOOGLE_SITE_VERIFICATION='g&"<tag>')
    def test_search_engine_verification_values_are_html_escaped(self):
        response = self.client.get(reverse("home"))

        self.assertContains(
            response,
            '<meta name="google-site-verification" content="g&amp;&quot;&lt;tag&gt;">',
        )

    def test_sentry_is_disabled_without_dsn_and_privacy_defaults_are_safe(self):
        from django.conf import settings

        self.assertFalse(settings.SENTRY_DSN)
        self.assertFalse(settings.SENTRY_ENABLED)
        self.assertFalse(settings.SENTRY_SEND_DEFAULT_PII)
        self.assertEqual(settings.SENTRY_TRACES_SAMPLE_RATE, 0.0)

    @override_settings(LEGAL_CONTACT_EMAIL="")
    def test_contact_page_omits_missing_contact_details(self):
        response = self.client.get(reverse("contact"))
        content = response.content.decode().lower()

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("not configured", content)
        self.assertNotContains(response, "LEGAL_CONTACT_EMAIL")
        self.assertNotContains(response, "mailto:")

    @override_settings(
        LEGAL_CONTACT_EMAIL="",
        LEGAL_ENTITY_NAME="",
    )
    def test_public_legal_pages_omit_missing_details_and_configuration_text(self):
        routes = (
            "contact",
            "grievance_redressal",
            "privacy_policy",
            "terms",
            "pricing_fees",
            "refund_policy",
            "trust_safety",
        )

        for route_name in routes:
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))
                content = response.content.decode()
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("LEGAL_CONTACT_EMAIL", content)
                self.assertNotIn("not configured", content.lower())
                self.assertNotIn("prototype", content.lower())

        self.assertNotContains(self.client.get(reverse("contact")), "mailto:")
        self.assertNotContains(
            self.client.get(reverse("grievance_redressal")), "mailto:"
        )

    @override_settings(
        LEGAL_ENTITY_NAME="Configured Marketplace Entity",
        LEGAL_CONTACT_EMAIL="legal@ubhaar-vyapaar.in",
        LEGAL_CONTACT_LABEL="Legal contact",
    )
    def test_configured_legal_contact_renders_on_applicable_pages(self):
        for route_name in (
            "contact",
            "privacy_policy",
            "terms",
        ):
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))
                self.assertContains(response, "legal@ubhaar-vyapaar.in")
                self.assertNotContains(response, "LEGAL_CONTACT_EMAIL")

        privacy = self.client.get(reverse("privacy_policy"))
        self.assertContains(privacy, "Configured Marketplace Entity")

    @override_settings(LEGAL_CONTACT_EMAIL="support@ubhaar-vyapaar.in")
    def test_default_contact_label_does_not_expose_prototype_wording(self):
        response = self.client.get(reverse("home"))

        self.assertContains(response, "support@ubhaar-vyapaar.in")
        self.assertNotContains(response, "prototype")

    @override_settings(
        LEGAL_ENTITY_NAME="Configured Marketplace Entity",
        LEGAL_CONTACT_EMAIL="support@ubhaar-vyapaar.in",
        LEGAL_CONTACT_LABEL="Support email",
    )
    def test_configured_contact_values_are_shared_with_footer(self):
        contact_response = self.client.get(reverse("contact"))
        home_response = self.client.get(reverse("home"))

        self.assertContains(contact_response, "support@ubhaar-vyapaar.in")
        self.assertContains(home_response, "Configured Marketplace Entity")
        self.assertContains(home_response, "support@ubhaar-vyapaar.in")
        self.assertContains(home_response, "Support email")

    @override_settings(DEBUG=False)
    def test_production_response_has_referrer_policy(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response["Referrer-Policy"], "same-origin")

    def test_health_endpoint_returns_minimal_ok_response(self):
        response = self.client.get(reverse("health"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertEqual(
            set(response.json()),
            {"status"},
        )

    def test_pages_use_configured_canonical_origin(self):
        response = self.client.get(reverse("home"))

        self.assertContains(
            response,
            "https://ubhaar-vyapaar.in/",
        )


@override_settings(
    PASSWORD_HASHERS=[
        "django.contrib.auth.hashers.MD5PasswordHasher",
    ],
    STORAGES={
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": (
                "django.contrib.staticfiles.storage.StaticFilesStorage"
            ),
        },
    }
)
class OrderMessagingTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.buyer = User.objects.create_user(
            username="buyer",
            password="password",
            role="BUYER",
        )
        self.other_buyer = User.objects.create_user(
            username="otherbuyer",
            password="password",
            role="BUYER",
        )
        self.manufacturer_user = User.objects.create_user(
            username="maker",
            password="password",
            role="MANUFACTURER",
        )
        self.other_manufacturer_user = User.objects.create_user(
            username="othermaker",
            password="password",
            role="MANUFACTURER",
        )
        self.other_manufacturer = ManufacturerProfile.objects.create(
            user=self.other_manufacturer_user,
            business_name="Other Works",
            city="Nashik",
            state="Maharashtra",
            is_verified=True,
        )
        self.manufacturer = ManufacturerProfile.objects.create(
            user=self.manufacturer_user,
            business_name="Maker Works",
            city="Pune",
            state="Maharashtra",
            is_verified=True,
        )
        self.listing = CapacityListing.objects.create(
            manufacturer=self.manufacturer,
            title="Box production",
            description="Corrugated packaging",
            minimum_quantity=100,
            price_per_unit=Decimal("10.00"),
            production_days=7,
        )
        self.quote_request = QuoteRequest.objects.create(
            buyer=self.buyer,
            listing=self.listing,
            quantity=100,
            requirements="Printed boxes",
            delivery_location="Mumbai",
            status=QuoteRequest.Status.ACCEPTED,
        )
        self.quotation = Quotation.objects.create(
            quote_request=self.quote_request,
            price_per_unit=Decimal("12.00"),
            quantity=100,
            production_days=8,
            status=Quotation.Status.ACCEPTED,
        )
        self.order = Order.objects.create(
            quotation=self.quotation,
            buyer=self.buyer,
            manufacturer=self.manufacturer,
            listing=self.listing,
            specifications_snapshot={
                "requirements": "Printed boxes",
                "delivery_location": "Mumbai",
            },
            quantity=100,
            agreed_unit_price=Decimal("12.00"),
            total_amount=Decimal("1200.00"),
            agreed_production_days=8,
        )
        self.milestone = Milestone.objects.create(
            order=self.order,
            title="Production complete",
            percentage=100,
            amount=Decimal("1200.00"),
        )

    def test_order_detail_is_limited_to_order_participants(self):
        url = reverse("order_detail", args=[self.order.pk])

        self.client.force_login(self.buyer)
        self.assertEqual(self.client.get(url).status_code, 200)

        self.client.force_login(self.manufacturer_user)
        self.assertEqual(self.client.get(url).status_code, 200)

        self.client.force_login(self.other_buyer)
        self.assertEqual(self.client.get(url).status_code, 404)

        self.client.force_login(self.other_manufacturer_user)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_order_detail_prioritizes_terms_milestones_and_role_specific_actions(self):
        self.client.force_login(self.buyer)
        buyer_response = self.client.get(
            reverse("order_detail", args=[self.order.pk]),
        )
        self.assertEqual(buyer_response.status_code, 200)
        buyer_content = buyer_response.content.decode()
        self.assertEqual(buyer_content.count("<h1"), 1)
        self.assertContains(buyer_response, "Commercial terms")
        self.assertContains(buyer_response, "Simulated payment state")
        self.assertContains(buyer_response, "Milestone 1")
        self.assertContains(buyer_response, "No messages yet")
        self.assertContains(buyer_response, "Fund milestone (demo)")
        self.assertNotContains(buyer_response, "Start milestone")
        self.assertContains(buyer_response, 'for="id_body"')

        self.milestone.status = Milestone.Status.IN_PROGRESS
        self.milestone.funding_status = Milestone.FundingStatus.FUNDED
        self.milestone.save(
            update_fields=["status", "funding_status", "updated_at"],
        )
        self.client.force_login(self.manufacturer_user)
        manufacturer_response = self.client.get(
            reverse("order_detail", args=[self.order.pk]),
        )
        self.assertEqual(manufacturer_response.status_code, 200)
        self.assertContains(manufacturer_response, "Submit for approval")
        self.assertNotContains(manufacturer_response, "Fund milestone (demo)")

    def test_buyer_message_notifies_order_manufacturer(self):
        self.client.force_login(self.buyer)

        response = self.client.post(
            reverse("send_order_message", args=[self.order.pk]),
            {"body": "Can you share a production update?"},
        )

        self.assertRedirects(
            response,
            reverse("order_detail", args=[self.order.pk]),
        )
        message = OrderMessage.objects.get(order=self.order)
        self.assertEqual(message.sender, self.buyer)
        self.assertEqual(
            Notification.objects.get().recipient,
            self.manufacturer_user,
        )
        self.assertEqual(
            Notification.objects.get().destination,
            Notification.Destination.ORDER_DETAIL,
        )
        self.assertEqual(Notification.objects.get().order, self.order)

    def test_non_participant_cannot_send_order_message(self):
        self.client.force_login(self.other_buyer)

        response = self.client.post(
            reverse("send_order_message", args=[self.order.pk]),
            {"body": "I should not be here."},
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(OrderMessage.objects.exists())
        self.assertFalse(Notification.objects.exists())

    def test_role_and_ownership_guards_block_id_guessing(self):
        self.client.force_login(self.buyer)
        self.assertEqual(
            self.client.get(reverse("create_listing")).status_code,
            403,
        )

        self.client.force_login(self.manufacturer_user)
        self.assertEqual(
            self.client.post(reverse("save_listing", args=[self.listing.pk]))
            .status_code,
            403,
        )

        self.client.force_login(self.other_manufacturer_user)
        self.assertEqual(
            self.client.get(reverse("edit_listing", args=[self.listing.pk]))
            .status_code,
            404,
        )

    def test_order_notification_opens_scoped_order(self):
        notification = Notification.objects.create(
            recipient=self.buyer,
            message="Order update",
            destination=Notification.Destination.ORDER_DETAIL,
            order=self.order,
        )
        self.client.force_login(self.buyer)

        response = self.client.post(
            reverse("open_notification", args=[notification.pk])
        )

        self.assertRedirects(
            response,
            reverse("order_detail", args=[self.order.pk]),
            fetch_redirect_response=False,
        )
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

    def test_notification_access_is_scoped_to_recipient(self):
        notification = Notification.objects.create(
            recipient=self.buyer,
            message="Private update",
            destination=Notification.Destination.BUYER_REQUESTS,
        )
        self.client.force_login(self.other_buyer)

        response = self.client.post(
            reverse("open_notification", args=[notification.pk])
        )

        self.assertEqual(response.status_code, 404)
        notification.refresh_from_db()
        self.assertFalse(notification.is_read)

    def test_order_notification_does_not_redirect_to_inaccessible_order(self):
        notification = Notification.objects.create(
            recipient=self.other_buyer,
            message="Mismatched order update",
            destination=Notification.Destination.ORDER_DETAIL,
            order=self.order,
        )
        self.client.force_login(self.other_buyer)

        response = self.client.post(
            reverse("open_notification", args=[notification.pk])
        )

        self.assertRedirects(response, reverse("notifications"))
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

    def test_quotation_acceptance_creates_order_once(self):
        pending_request = QuoteRequest.objects.create(
            buyer=self.other_buyer,
            listing=self.listing,
            quantity=150,
            requirements="Mailer boxes",
            delivery_location="Delhi",
            status=QuoteRequest.Status.ACCEPTED,
        )
        quotation = Quotation.objects.create(
            quote_request=pending_request,
            price_per_unit=Decimal("15.00"),
            quantity=150,
            production_days=10,
        )
        self.client.force_login(self.other_buyer)

        response = self.client.post(
            reverse("respond_to_quotation", args=[quotation.pk]),
            {"status": Quotation.Status.ACCEPTED},
        )

        self.assertRedirects(response, reverse("my_quote_requests"))
        order = Order.objects.get(quotation=quotation)
        self.assertEqual(order.buyer, self.other_buyer)
        self.assertEqual(order.total_amount, Decimal("2250.00"))
        self.assertEqual(order.milestones.count(), 2)

        response = self.client.post(
            reverse("respond_to_quotation", args=[quotation.pk]),
            {"status": Quotation.Status.DECLINED},
        )

        self.assertRedirects(response, reverse("my_quote_requests"))
        self.assertEqual(Order.objects.filter(quotation=quotation).count(), 1)
        quotation.refresh_from_db()
        self.assertEqual(quotation.status, Quotation.Status.ACCEPTED)

    def test_manufacturer_can_send_quotation_and_buyer_can_decline(self):
        quote_request = QuoteRequest.objects.create(
            buyer=self.other_buyer,
            listing=self.listing,
            quantity=150,
            requirements="Mailer boxes with a printed insert.",
            delivery_location="Delhi",
        )
        self.client.force_login(self.manufacturer_user)

        response = self.client.post(
            reverse("send_quotation", args=[quote_request.pk]),
            {
                "price_per_unit": "15.50",
                "production_days": "12",
                "message": "Includes the printed insert.",
            },
        )

        self.assertRedirects(response, reverse("manufacturer_dashboard"))
        quotation = Quotation.objects.get(quote_request=quote_request)
        self.assertEqual(quotation.quantity, 150)
        self.assertEqual(quotation.subtotal, Decimal("2325.00"))
        quote_request.refresh_from_db()
        self.assertEqual(quote_request.status, QuoteRequest.Status.ACCEPTED)

        self.client.force_login(self.other_buyer)
        review_page = self.client.get(reverse("my_quote_requests"))
        self.assertContains(review_page, "Quotation · Awaiting your decision")
        self.assertContains(review_page, "2,325")
        self.assertContains(review_page, "Includes the printed insert.")
        self.assertContains(review_page, "Accept quotation")
        self.assertContains(review_page, "Decline")

        response = self.client.post(
            reverse("respond_to_quotation", args=[quotation.pk]),
            {"status": Quotation.Status.DECLINED},
        )
        self.assertRedirects(response, reverse("my_quote_requests"))
        quotation.refresh_from_db()
        self.assertEqual(quotation.status, Quotation.Status.DECLINED)
        self.assertFalse(Order.objects.filter(quotation=quotation).exists())

    def test_buyer_cannot_respond_to_another_buyers_quotation(self):
        self.client.force_login(self.other_buyer)

        response = self.client.post(
            reverse("respond_to_quotation", args=[self.quotation.pk]),
            {"status": Quotation.Status.DECLINED},
        )

        self.assertEqual(response.status_code, 404)
        self.quotation.refresh_from_db()
        self.assertEqual(self.quotation.status, Quotation.Status.ACCEPTED)

    def test_milestone_actions_are_limited_to_order_participants(self):
        self.client.force_login(self.other_manufacturer_user)
        response = self.client.post(
            reverse("mark_milestone_complete", args=[self.milestone.pk])
        )
        self.assertEqual(response.status_code, 404)

        self.client.force_login(self.manufacturer_user)
        response = self.client.post(
            reverse("mark_milestone_complete", args=[self.milestone.pk])
        )
        self.assertRedirects(
            response,
            reverse("order_detail", args=[self.order.pk]),
        )
        self.milestone.refresh_from_db()
        self.assertEqual(self.milestone.status, Milestone.Status.PENDING)

        self.client.force_login(self.buyer)
        response = self.client.post(
            reverse("fund_milestone", args=[self.milestone.pk])
        )
        self.assertRedirects(
            response,
            reverse("order_detail", args=[self.order.pk]),
        )
        self.milestone.refresh_from_db()
        self.assertEqual(
            self.milestone.funding_status,
            Milestone.FundingStatus.FUNDED,
        )

        self.client.force_login(self.manufacturer_user)
        response = self.client.post(
            reverse("start_milestone", args=[self.milestone.pk])
        )
        self.assertRedirects(
            response,
            reverse("order_detail", args=[self.order.pk]),
        )
        self.milestone.refresh_from_db()
        self.assertEqual(self.milestone.status, Milestone.Status.IN_PROGRESS)

        response = self.client.post(
            reverse("mark_milestone_complete", args=[self.milestone.pk])
        )
        self.assertRedirects(
            response,
            reverse("order_detail", args=[self.order.pk]),
        )
        self.milestone.refresh_from_db()
        self.assertEqual(self.milestone.status, Milestone.Status.COMPLETED)

        self.client.force_login(self.other_buyer)
        response = self.client.post(
            reverse("respond_to_milestone", args=[self.milestone.pk]),
            {"status": Milestone.Status.APPROVED},
        )
        self.assertEqual(response.status_code, 404)

        self.client.force_login(self.buyer)
        response = self.client.post(
            reverse("respond_to_milestone", args=[self.milestone.pk]),
            {"status": Milestone.Status.APPROVED},
        )
        self.assertRedirects(
            response,
            reverse("order_detail", args=[self.order.pk]),
        )
        self.milestone.refresh_from_db()
        self.assertEqual(self.milestone.status, Milestone.Status.APPROVED)
        self.assertEqual(
            self.milestone.funding_status,
            Milestone.FundingStatus.FUNDED,
        )

    def test_demo_funding_release_and_completion_flow(self):
        self.client.force_login(self.buyer)

        response = self.client.post(
            reverse("fund_milestone", args=[self.milestone.pk])
        )

        self.assertRedirects(
            response,
            reverse("order_detail", args=[self.order.pk]),
        )
        self.milestone.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(
            self.milestone.funding_status,
            Milestone.FundingStatus.FUNDED,
        )
        self.assertIsNotNone(self.milestone.funded_at)
        self.assertEqual(self.order.status, Order.Status.FUNDED)
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.manufacturer_user,
                message__icontains="demo funding",
                order=self.order,
            ).exists()
        )

        response = self.client.post(
            reverse("fund_milestone", args=[self.milestone.pk])
        )
        self.assertRedirects(
            response,
            reverse("order_detail", args=[self.order.pk]),
        )
        self.assertEqual(
            Milestone.objects.get(pk=self.milestone.pk).funding_status,
            Milestone.FundingStatus.FUNDED,
        )

        self.client.force_login(self.other_buyer)
        response = self.client.post(
            reverse("fund_milestone", args=[self.milestone.pk])
        )
        self.assertEqual(response.status_code, 404)

        self.client.force_login(self.manufacturer_user)
        response = self.client.post(
            reverse("start_milestone", args=[self.milestone.pk])
        )
        self.assertRedirects(
            response,
            reverse("order_detail", args=[self.order.pk]),
        )
        self.milestone.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.milestone.status, Milestone.Status.IN_PROGRESS)
        self.assertEqual(self.order.status, Order.Status.IN_PRODUCTION)

        response = self.client.post(
            reverse("mark_milestone_complete", args=[self.milestone.pk])
        )
        self.assertRedirects(
            response,
            reverse("order_detail", args=[self.order.pk]),
        )
        self.milestone.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.milestone.status, Milestone.Status.COMPLETED)
        self.assertEqual(self.order.status, Order.Status.MILESTONE_PENDING)

        self.client.force_login(self.manufacturer_user)
        response = self.client.post(
            reverse("respond_to_milestone", args=[self.milestone.pk]),
            {"status": Milestone.Status.APPROVED},
        )
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.buyer)
        response = self.client.post(
            reverse("respond_to_milestone", args=[self.milestone.pk]),
            {
                "status": Milestone.Status.APPROVED,
                "buyer_feedback": "Looks good.",
            },
        )
        self.assertRedirects(
            response,
            reverse("order_detail", args=[self.order.pk]),
        )
        self.milestone.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.milestone.status, Milestone.Status.APPROVED)
        self.assertEqual(self.order.status, Order.Status.IN_PRODUCTION)

        response = self.client.post(
            reverse("release_milestone_payment", args=[self.milestone.pk])
        )
        self.assertRedirects(
            response,
            reverse("order_detail", args=[self.order.pk]),
        )
        self.milestone.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(
            self.milestone.funding_status,
            Milestone.FundingStatus.RELEASED,
        )
        self.assertIsNotNone(self.milestone.released_at)
        self.assertEqual(self.order.status, Order.Status.COMPLETED)
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.manufacturer_user,
                message__icontains="released demo payment",
                order=self.order,
            ).exists()
        )

        response = self.client.post(
            reverse("release_milestone_payment", args=[self.milestone.pk])
        )
        self.assertRedirects(
            response,
            reverse("order_detail", args=[self.order.pk]),
        )
        self.assertEqual(
            Milestone.objects.get(pk=self.milestone.pk).funding_status,
            Milestone.FundingStatus.RELEASED,
        )

    def test_completed_order_blocks_funding_and_milestone_updates(self):
        self.milestone.funding_status = Milestone.FundingStatus.RELEASED
        self.milestone.status = Milestone.Status.APPROVED
        self.milestone.save(update_fields=["funding_status", "status"])
        self.order.status = Order.Status.COMPLETED
        self.order.save(update_fields=["status"])

        self.client.force_login(self.buyer)
        response = self.client.post(
            reverse("fund_milestone", args=[self.milestone.pk])
        )
        self.assertRedirects(
            response,
            reverse("order_detail", args=[self.order.pk]),
        )

        self.client.force_login(self.manufacturer_user)
        response = self.client.post(
            reverse("start_milestone", args=[self.milestone.pk])
        )
        self.assertRedirects(
            response,
            reverse("order_detail", args=[self.order.pk]),
        )
        self.milestone.refresh_from_db()
        self.assertEqual(self.milestone.status, Milestone.Status.APPROVED)

    def test_financial_summary_uses_milestone_funding_states(self):
        second = Milestone.objects.create(
            order=self.order,
            title="Final dispatch",
            percentage=25,
            amount=Decimal("300.00"),
            funding_status=Milestone.FundingStatus.RELEASED,
        )
        self.milestone.funding_status = Milestone.FundingStatus.FUNDED
        self.milestone.amount = Decimal("900.00")
        self.milestone.save(update_fields=["funding_status", "amount"])

        summary = build_order_financial_summary(
            self.order,
            [self.milestone, second],
        )

        self.assertEqual(summary["order_value"], Decimal("1200.00"))
        self.assertEqual(summary["milestone_total"], Decimal("1200.00"))
        self.assertEqual(summary["funded"], Decimal("1200.00"))
        self.assertEqual(summary["released"], Decimal("300.00"))
        self.assertEqual(summary["remaining"], Decimal("0.00"))

    def test_order_timeline_reflects_real_milestone_progress(self):
        self.milestone.funding_status = Milestone.FundingStatus.RELEASED
        self.milestone.status = Milestone.Status.APPROVED
        self.milestone.save(update_fields=["funding_status", "status"])
        self.order.status = Order.Status.COMPLETED
        self.order.save(update_fields=["status"])

        steps = build_order_timeline(self.order, [self.milestone])
        completed_steps = {
            step["title"]
            for step in steps
            if step["complete"]
        }

        self.assertEqual(len(steps), 10)
        self.assertIn("Quotation accepted", completed_steps)
        self.assertIn("Demo funding", completed_steps)
        self.assertIn("Approval", completed_steps)
        self.assertIn("Demo release", completed_steps)
        self.assertIn("Completion", completed_steps)
        self.assertNotIn("Review", completed_steps)

    def test_review_requires_completed_owned_order_and_is_unique(self):
        self.client.force_login(self.buyer)
        response = self.client.get(reverse("review_order", args=[self.order.pk]))
        self.assertEqual(response.status_code, 404)

        self.order.status = Order.Status.COMPLETED
        self.order.save(update_fields=["status"])

        response = self.client.post(
            reverse("review_order", args=[self.order.pk]),
            {
                "quality_rating": 5,
                "timeliness_rating": 4,
                "communication_rating": 5,
                "overall_rating": 5,
                "comment": "Clear updates and good finish.",
            },
        )

        self.assertRedirects(
            response,
            reverse("order_detail", args=[self.order.pk]),
        )
        self.assertEqual(Review.objects.filter(order=self.order).count(), 1)

        response = self.client.post(
            reverse("review_order", args=[self.order.pk]),
            {
                "quality_rating": 1,
                "timeliness_rating": 1,
                "communication_rating": 1,
                "overall_rating": 1,
            },
        )

        self.assertRedirects(
            response,
            reverse("order_detail", args=[self.order.pk]),
        )
        self.assertEqual(Review.objects.filter(order=self.order).count(), 1)

        self.client.force_login(self.other_buyer)
        self.assertEqual(
            self.client.get(reverse("review_order", args=[self.order.pk]))
            .status_code,
            404,
        )

        self.client.force_login(self.manufacturer_user)
        self.assertEqual(
            self.client.get(reverse("review_order", args=[self.order.pk]))
            .status_code,
            403,
        )


class PolicyPageTests(TestCase):
    @override_settings(DEBUG=False)
    def test_error_pages_offer_marketplace_route(self):
        missing = self.client.get("/missing-page/")
        self.assertEqual(missing.status_code, 404)
        self.assertContains(missing, "Back to marketplace", status_code=404)
        self.assertContains(missing, 'name="robots" content="noindex"', status_code=404)

        unavailable = server_error(RequestFactory().get("/"))
        self.assertEqual(unavailable.status_code, 500)
        self.assertIn(b"Back to marketplace", unavailable.content)
        self.assertIn(b'name="robots" content="noindex"', unavailable.content)

    def test_information_pages_are_public_and_disclose_simulated_funding(self):
        for name in ("about", "how_it_works", "help_page"):
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "simulated")

    @override_settings(LEGAL_CONTACT_EMAIL="")
    def test_help_omits_unconfigured_contact(self):
        response = self.client.get(reverse("help_page"))
        self.assertNotContains(response, "mailto:")

    def test_policy_pages_return_success(self):
        for name in (
            "privacy_policy",
            "terms",
            "cookie_policy",
            "refund_policy",
        ):
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)

    def test_cookie_policy_does_not_list_unused_cookie_categories(self):
        response = self.client.get(reverse("cookie_policy"))

        self.assertNotContains(response, "<dt>Marketing</dt>")
        self.assertNotContains(response, "Accept All")

    def test_terms_disclose_simulated_payments(self):
        response = self.client.get(reverse("terms"))

        self.assertContains(response, "does not process real payments")
        self.assertContains(response, "real escrow account")


class AccessibilityContrastTests(TestCase):
    def contrast_ratio(self, foreground, background):
        def luminance(hex_color):
            value = hex_color.lstrip("#")
            channels = [
                int(value[index:index + 2], 16) / 255
                for index in (0, 2, 4)
            ]
            linear = [
                channel / 12.92
                if channel <= 0.03928
                else ((channel + 0.055) / 1.055) ** 2.4
                for channel in channels
            ]
            return (
                0.2126 * linear[0]
                + 0.7152 * linear[1]
                + 0.0722 * linear[2]
            )

        lighter = max(luminance(foreground), luminance(background))
        darker = min(luminance(foreground), luminance(background))
        return (lighter + 0.05) / (darker + 0.05)

    def assert_contrast_at_least(self, foreground, background, minimum):
        self.assertGreaterEqual(
            self.contrast_ratio(foreground, background),
            minimum,
            f"{foreground} on {background} should meet {minimum}:1 contrast",
        )

    def test_core_palette_meets_wcag_aa_text_contrast(self):
        pairs = (
            ("#18212b", "#ffffff"),
            ("#647280", "#ffffff"),
            ("#185f5b", "#ffffff"),
            ("#ffffff", "#185f5b"),
            ("#1f6844", "#eaf6ef"),
            ("#814c14", "#fff4df"),
            ("#9c2c25", "#fff0ee"),
            ("#245d90", "#eaf3fb"),
            ("#52636e", "#edf2f4"),
            ("#aec0cb", "#102f3c"),
        )

        for foreground, background in pairs:
            with self.subTest(foreground=foreground, background=background):
                self.assert_contrast_at_least(foreground, background, 4.5)

    def test_focus_ring_meets_non_text_contrast(self):
        self.assert_contrast_at_least("#8a560f", "#ffffff", 3)


class PlatformReadinessTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.buyer = User.objects.create_user(
            username="seo-buyer",
            email="seo-buyer@example.test",
            password="StrongPass123!",
            role="BUYER",
        )
        manufacturer_user = User.objects.create_user(
            username="seo-maker",
            password="password",
            role="MANUFACTURER",
        )
        self.manufacturer = ManufacturerProfile.objects.create(
            user=manufacturer_user,
            business_name="SEO Works",
            city="Pune",
            state="Maharashtra",
            is_verified=True,
        )
        self.listing = CapacityListing.objects.create(
            manufacturer=self.manufacturer,
            title="Public packaging capacity",
            description="Public listing for sitemap tests.",
            minimum_quantity=25,
            price_per_unit=Decimal("22.00"),
            production_days=5,
        )

    def test_sitemap_includes_public_urls_and_excludes_private_urls(self):
        response = self.client.get(reverse("sitemap_xml"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/xml; charset=utf-8")
        self.assertContains(response, "https://ubhaar-vyapaar.in/")
        self.assertContains(response, "https://ubhaar-vyapaar.in/marketplace/")
        self.assertContains(
            response,
            reverse("listing_detail", args=[self.listing.pk]),
        )
        self.assertContains(
            response,
            reverse("manufacturer_profile", args=[self.manufacturer.pk]),
        )
        self.assertContains(response, reverse("privacy_policy"))
        self.assertNotContains(response, reverse("buyer_dashboard"))
        self.assertNotContains(response, "/orders/")
        self.assertNotContains(response, "/notifications/")
        self.assertNotContains(response, "/admin/")
        self.assertIn(
            "https://ubhaar-vyapaar.in/listings/",
            response.content.decode(),
        )

    def test_sitemap_excludes_paused_and_inactive_listings(self):
        paused = CapacityListing.objects.create(
            manufacturer=self.manufacturer,
            title="Paused packaging capacity",
            description="Paused listing.",
            minimum_quantity=25,
            price_per_unit=Decimal("22.00"),
            production_days=5,
            availability_status=CapacityListing.AvailabilityStatus.PAUSED,
        )
        inactive = CapacityListing.objects.create(
            manufacturer=self.manufacturer,
            title="Removed packaging capacity",
            description="Inactive listing.",
            minimum_quantity=25,
            price_per_unit=Decimal("22.00"),
            production_days=5,
            is_active=False,
        )

        response = self.client.get(reverse("sitemap_xml"))
        content = response.content.decode()

        self.assertIn(
            reverse("listing_detail", args=[self.listing.pk]),
            content,
        )
        self.assertNotIn(
            reverse("listing_detail", args=[paused.pk]),
            content,
        )
        self.assertNotIn(
            reverse("listing_detail", args=[inactive.pk]),
            content,
        )

    @override_settings(ALLOW_INDEXING=True)
    def test_paused_detail_is_noindex_but_active_detail_is_indexable(self):
        paused = CapacityListing.objects.create(
            manufacturer=self.manufacturer,
            title="Paused detail capacity",
            description="Paused listing.",
            minimum_quantity=25,
            price_per_unit=Decimal("22.00"),
            production_days=5,
            availability_status=CapacityListing.AvailabilityStatus.PAUSED,
        )

        paused_response = self.client.get(
            reverse("listing_detail", args=[paused.pk]),
        )
        active_response = self.client.get(
            reverse("listing_detail", args=[self.listing.pk]),
        )

        self.assertContains(
            paused_response,
            '<meta name="robots" content="noindex,follow">',
            html=True,
        )
        self.assertNotContains(active_response, 'name="robots"')

    @override_settings(ALLOW_INDEXING=True)
    def test_public_pages_are_indexable_when_allowed(self):
        response = self.client.get(reverse("home"))

        self.assertNotContains(response, 'content="noindex,nofollow"')

    @override_settings(ALLOW_INDEXING=True)
    def test_account_and_private_pages_are_noindex_when_public_indexing_is_enabled(self):
        for url_name in (
            "login",
            "register",
            "password_reset",
        ):
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertContains(
                    response,
                    '<meta name="robots" content="noindex,follow">',
                    html=True,
                )

        self.client.force_login(self.buyer)
        dashboard = self.client.get(reverse("buyer_dashboard"))
        self.assertContains(
            dashboard,
            '<meta name="robots" content="noindex,follow">',
            html=True,
        )

    @override_settings(ALLOW_INDEXING=False)
    def test_public_pages_are_noindex_nofollow_when_indexing_disabled(self):
        response = self.client.get(reverse("home"))

        self.assertContains(
            response,
            '<meta name="robots" content="noindex,nofollow">',
            html=True,
        )

    @override_settings(ALLOW_GPTBOT=False)
    def test_robots_disallows_gptbot_when_disabled_and_allows_oai_searchbot(self):
        response = self.client.get(reverse("robots_txt"))
        content = response.content.decode()

        self.assertIn("User-agent: OAI-SearchBot", content)
        self.assertIn("User-agent: GPTBot\nDisallow: /", content)

    @override_settings(ALLOW_INDEXING=True, ALLOW_GPTBOT=True)
    def test_robots_allows_gptbot_without_overriding_private_disallows(self):
        response = self.client.get(reverse("robots_txt"))
        content = response.content.decode()

        self.assertIn("User-agent: GPTBot", content)
        self.assertIn("Disallow: /admin/", content)
        self.assertIn("Allow: /", content)

    @override_settings(ALLOW_INDEXING=True)
    def test_robots_txt_guides_private_area_exclusion(self):
        response = self.client.get(reverse("robots_txt"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/plain; charset=utf-8")
        self.assertContains(response, "Disallow: /admin/")
        self.assertContains(response, "Disallow: /accounts/password/change/")
        self.assertNotContains(response, "Disallow: /accounts/\n")
        self.assertContains(response, "Disallow: /orders/")
        self.assertContains(response, "User-agent: OAI-SearchBot")
        self.assertContains(response, "Allow: /")
        self.assertContains(response, "Sitemap:")

    def test_analytics_absent_without_configured_id(self):
        response = self.client.get(reverse("home"))

        self.assertContains(response, 'data-google-analytics-id=""')
        self.assertContains(response, 'data-google-analytics-src=""')
        self.assertNotContains(response, "www.googletagmanager.com/gtag/js")

    @override_settings(GOOGLE_ANALYTICS_ID="G-TEST123")
    def test_analytics_configured_but_not_loaded_before_consent(self):
        response = self.client.get(reverse("home"))

        self.assertContains(response, 'data-google-analytics-id="G-TEST123"')
        self.assertContains(response, "www.googletagmanager.com/gtag/js")
        self.assertNotContains(response, '<script async src="https://www.googletagmanager.com/gtag/js')
        self.assertContains(response, "loadAnalytics")
        self.assertContains(response, "preferences.analytics")

    def test_cookie_preferences_can_be_changed_from_footer(self):
        response = self.client.get(reverse("home"))

        self.assertContains(response, "Cookie settings")
        self.assertContains(response, "data-cookie-settings")
        self.assertContains(response, "data-cookie-accept")
        self.assertContains(response, "data-cookie-reject")
        self.assertContains(response, "data-cookie-preferences")

    def test_necessary_csrf_cookie_remains_functional(self):
        client = Client(enforce_csrf_checks=True)
        response = client.get(reverse("register"))
        csrf_token = response.cookies["csrftoken"].value

        response = client.post(
            reverse("register"),
            {
                "username": "csrf-buyer",
                "email": "csrf-buyer@example.test",
                "phone": "",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
                "legal_acknowledgement": "on",
                "csrfmiddlewaretoken": csrf_token,
            },
            HTTP_REFERER="http://testserver/accounts/register/",
        )

        self.assertRedirects(response, reverse("home"))
        self.assertTrue(
            get_user_model().objects.filter(username="csrf-buyer").exists()
        )

    def test_public_listing_without_image_uses_designed_fallback(self):
        home_response = self.client.get(reverse("marketplace"))

        self.assertContains(home_response, "listing-media-frame")
        self.assertContains(home_response, "media-no-image")
        self.assertContains(home_response, "fallback-brand-mark")
        self.assertContains(home_response, "Browse manufacturing capacity")
        self.assertNotContains(home_response, "Product photo coming soon")
        self.assertNotContains(home_response, "Image for ")

        detail_response = self.client.get(
            reverse("listing_detail", args=[self.listing.pk])
        )

        self.assertContains(detail_response, "detail-image-placeholder")
        self.assertContains(detail_response, "media-no-image")
        self.assertContains(detail_response, "fallback-geometry")
        self.assertNotContains(detail_response, "Product photo coming soon")
        self.assertNotContains(detail_response, "Image for ")

    def test_public_listing_with_missing_image_has_client_side_fallback(self):
        self.listing.image = "listings/missing-demo-image.webp"
        self.listing.save(update_fields=["image"])

        response = self.client.get(reverse("listing_detail", args=[self.listing.pk]))

        self.assertContains(response, "listings/missing-demo-image.webp")
        self.assertContains(response, "media-failed")
        self.assertContains(response, "detail-image-placeholder")
        self.assertContains(response, "fallback-brand-mark")


class DemoSeedCommandTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.TemporaryDirectory()
        self.override = override_settings(
            MEDIA_ROOT=self.media_root.name,
            ALLOW_DEMO_SEEDING=True,
            STORAGES={
                "default": {
                    "BACKEND": "django.core.files.storage.FileSystemStorage",
                },
                "staticfiles": {
                    "BACKEND": (
                        "django.contrib.staticfiles.storage.StaticFilesStorage"
                    ),
                },
            },
            PASSWORD_HASHERS=[
                "django.contrib.auth.hashers.MD5PasswordHasher",
            ],
        )
        self.override.enable()

    def tearDown(self):
        self.override.disable()
        self.media_root.cleanup()

    def test_demo_seed_is_blocked_when_production_flag_is_disabled(self):
        with override_settings(DEBUG=False, ALLOW_DEMO_SEEDING=False):
            with self.assertRaisesMessage(
                CommandError,
                "Demo data seeding is disabled.",
            ):
                call_command("seed_demo_data", stdout=StringIO())

        self.assertEqual(ManufacturerProfile.objects.count(), 0)
        self.assertEqual(CapacityListing.objects.count(), 0)

    def test_demo_seed_runs_when_explicitly_allowed(self):
        with override_settings(ALLOW_DEMO_SEEDING=True):
            call_command("seed_demo_data", stdout=StringIO())

        self.assertEqual(
            ManufacturerProfile.objects.filter(
                user__username__startswith="demo_mfr_",
            ).count(),
            5,
        )

    def test_seed_demo_data_creates_fictional_demo_marketplace_content(self):
        call_command("seed_demo_data", verbosity=0)

        self.assertEqual(
            ManufacturerProfile.objects.filter(
                user__username__startswith="demo_mfr_",
            ).count(),
            5,
        )
        self.assertEqual(
            CapacityListing.objects.filter(
                manufacturer__user__username__startswith="demo_mfr_",
            ).count(),
            10,
        )
        self.assertEqual(
            CapacityListing.objects.filter(
                manufacturer__user__username__startswith="demo_mfr_",
                image="",
            ).count(),
            0,
        )
        self.assertEqual(
            CapacityListing.objects.filter(
                manufacturer__user__username__startswith="demo_mfr_",
                image__startswith="demo/listings/",
            ).count(),
            10,
        )
        self.assertEqual(Review.objects.count(), 2)

    def test_public_sample_profile_hides_seeded_reviews_and_ratings(self):
        call_command("seed_demo_data", verbosity=0)
        manufacturer = ManufacturerProfile.objects.get(
            user__username="demo_mfr_nila_pack",
        )
        manufacturer.is_verified = True
        manufacturer.save(update_fields=["is_verified"])
        listing = CapacityListing.objects.get(
            title="Custom Corrugated Packaging for D2C Shipments",
        )

        profile_response = self.client.get(
            reverse("manufacturer_profile", args=[manufacturer.pk]),
        )
        self.assertNotContains(profile_response, "Buyer reviews")
        self.assertNotContains(profile_response, "Average rating:")
        self.assertNotContains(profile_response, "Cartons matched the approved sample")
        self.assertNotContains(profile_response, "5.0/5")

        detail_response = self.client.get(
            reverse("listing_detail", args=[listing.pk]),
        )
        self.assertNotContains(detail_response, "Average rating:")
        self.assertNotContains(detail_response, "5.0/5")
        self.assertEqual(Review.objects.filter(manufacturer=manufacturer).count(), 1)
        self.assertTrue(
            CapacityListing.objects.filter(
                title="Custom Corrugated Packaging for D2C Shipments",
                image__startswith="demo/listings/",
                manufacturer__business_name="Nila Packworks",
                manufacturer__user__email__endswith="@example.com",
            ).exists()
        )

    def test_seed_demo_data_is_idempotent(self):
        call_command("seed_demo_data", verbosity=0)
        call_command("seed_demo_data", verbosity=0)

        self.assertEqual(
            CapacityListing.objects.filter(
                manufacturer__user__username__startswith="demo_mfr_",
            ).count(),
            10,
        )
        self.assertEqual(Review.objects.count(), 2)

    def test_homepage_limits_demo_listing_density(self):
        call_command("seed_demo_data", verbosity=0)

        response = self.client.get(reverse("marketplace"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["listings"]), 6)
        self.assertGreater(response.context["page_obj"].paginator.count, 6)


class CleanupE2EDataCommandTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.TemporaryDirectory()
        self.override = override_settings(
            MEDIA_ROOT=self.media_root.name,
            ALLOW_DEMO_SEEDING=True,
            STORAGES={
                "default": {
                    "BACKEND": "django.core.files.storage.FileSystemStorage",
                },
                "staticfiles": {
                    "BACKEND": (
                        "django.contrib.staticfiles.storage.StaticFilesStorage"
                    ),
                },
            },
            PASSWORD_HASHERS=[
                "django.contrib.auth.hashers.MD5PasswordHasher",
            ],
        )
        self.override.enable()

    def tearDown(self):
        self.override.disable()
        self.media_root.cleanup()

    def create_commerce_graph(
        self,
        *,
        buyer_username,
        manufacturer_username,
        buyer_email,
        manufacturer_email,
        business_name,
        listing_title,
    ):
        User = get_user_model()

        buyer = User.objects.create_user(
            username=buyer_username,
            email=buyer_email,
            password="password",
            role="BUYER",
        )
        manufacturer_user = User.objects.create_user(
            username=manufacturer_username,
            email=manufacturer_email,
            password="password",
            role="MANUFACTURER",
        )
        manufacturer = ManufacturerProfile.objects.create(
            user=manufacturer_user,
            business_name=business_name,
            description="Production smoke-test fixture.",
            city="Ahmedabad",
            state="Gujarat",
            is_verified=True,
            kyc_status=ManufacturerProfile.KycStatus.VERIFIED,
        )
        listing = CapacityListing.objects.create(
            manufacturer=manufacturer,
            title=listing_title,
            description="Disposable listing for cleanup coverage.",
            minimum_quantity=20,
            price_per_unit=Decimal("18.75"),
            production_days=5,
        )
        saved_listing = SavedListing.objects.create(
            buyer=buyer,
            listing=listing,
        )
        quote_request = QuoteRequest.objects.create(
            buyer=buyer,
            listing=listing,
            quantity=30,
            requirements="Smoke-test package requirements",
            delivery_location="Mumbai, Maharashtra",
            status=QuoteRequest.Status.ACCEPTED,
        )
        quotation = Quotation.objects.create(
            quote_request=quote_request,
            price_per_unit=Decimal("21.25"),
            quantity=30,
            production_days=6,
            message="Quotation generated by production smoke test.",
            status=Quotation.Status.ACCEPTED,
        )
        order = Order.objects.create(
            quotation=quotation,
            buyer=buyer,
            manufacturer=manufacturer,
            listing=listing,
            specifications_snapshot={
                "requirements": quote_request.requirements,
                "delivery_location": quote_request.delivery_location,
            },
            quantity=30,
            agreed_unit_price=Decimal("21.25"),
            total_amount=Decimal("637.50"),
            agreed_production_days=6,
            status=Order.Status.COMPLETED,
        )
        milestone = Milestone.objects.create(
            order=order,
            title="Production complete",
            percentage=100,
            amount=Decimal("637.50"),
        )
        order_message = OrderMessage.objects.create(
            order=order,
            sender=buyer,
            body="Buyer scoped message",
        )
        review = Review.objects.create(
            order=order,
            buyer=buyer,
            manufacturer=manufacturer,
            quality_rating=5,
            timeliness_rating=5,
            communication_rating=5,
            overall_rating=5,
            comment="Completed order review from production smoke test.",
        )
        notification = Notification.objects.create(
            recipient=manufacturer_user,
            message=f"New message on order #{order.pk}",
            destination=Notification.Destination.ORDER_DETAIL,
            order=order,
        )

        return {
            "buyer": buyer,
            "manufacturer_user": manufacturer_user,
            "manufacturer": manufacturer,
            "listing": listing,
            "saved_listing": saved_listing,
            "quote_request": quote_request,
            "quotation": quotation,
            "order": order,
            "milestone": milestone,
            "order_message": order_message,
            "review": review,
            "notification": notification,
        }

    def create_e2e_graph(self):
        run_id = "1700000000000-abc123"

        return self.create_commerce_graph(
            buyer_username=f"uv-e2e-commercebuyer-{run_id}",
            manufacturer_username=f"uv-e2e-commercemfr-{run_id}",
            buyer_email=f"uv-e2e-commercebuyer-{run_id}@example.com",
            manufacturer_email=f"uv-e2e-commercemfr-{run_id}@example.com",
            business_name=f"UV E2E Verified Works {run_id}",
            listing_title=f"UV E2E Verified Capacity {run_id}",
        )

    def create_normal_graph(self):
        return self.create_commerce_graph(
            buyer_username="real-buyer",
            manufacturer_username="real-manufacturer",
            buyer_email="real-buyer@example.test",
            manufacturer_email="real-manufacturer@example.test",
            business_name="Verified Works Real Supplier",
            listing_title="Verified Capacity for Real Packaging",
        )

    def model_counts(self):
        User = get_user_model()

        return {
            "users": User.objects.count(),
            "manufacturers": ManufacturerProfile.objects.count(),
            "listings": CapacityListing.objects.count(),
            "saved_listings": SavedListing.objects.count(),
            "quote_requests": QuoteRequest.objects.count(),
            "quotations": Quotation.objects.count(),
            "orders": Order.objects.count(),
            "milestones": Milestone.objects.count(),
            "order_messages": OrderMessage.objects.count(),
            "reviews": Review.objects.count(),
            "notifications": Notification.objects.count(),
        }

    def test_dry_run_deletes_nothing(self):
        e2e = self.create_e2e_graph()
        before = self.model_counts()
        output = StringIO()

        call_command("cleanup_e2e_data", dry_run=True, stdout=output)

        self.assertEqual(self.model_counts(), before)
        self.assertTrue(
            CapacityListing.objects.filter(pk=e2e["listing"].pk).exists()
        )
        self.assertIn("DRY RUN", output.getvalue())

    def test_e2e_records_are_detected_in_dry_run(self):
        e2e = self.create_e2e_graph()
        output = StringIO()

        call_command("cleanup_e2e_data", dry_run=True, stdout=output)

        text = output.getvalue()
        self.assertIn(e2e["buyer"].username, text)
        self.assertIn(e2e["manufacturer"].business_name, text)
        self.assertIn(e2e["listing"].title, text)
        self.assertIn(f"Order #{e2e['order'].pk}", text)
        self.assertIn("Users: 2", text)
        self.assertIn("Listings: 1", text)
        self.assertIn("Orders: 1", text)

    def test_real_execution_deletes_only_e2e_records(self):
        e2e = self.create_e2e_graph()
        normal = self.create_normal_graph()

        call_command("cleanup_e2e_data", stdout=StringIO())

        self.assertFalse(
            get_user_model().objects.filter(pk=e2e["buyer"].pk).exists()
        )
        self.assertFalse(
            ManufacturerProfile.objects.filter(
                pk=e2e["manufacturer"].pk
            ).exists()
        )
        self.assertFalse(
            CapacityListing.objects.filter(pk=e2e["listing"].pk).exists()
        )
        self.assertFalse(
            Order.objects.filter(pk=e2e["order"].pk).exists()
        )
        self.assertFalse(
            QuoteRequest.objects.filter(
                pk=e2e["quote_request"].pk
            ).exists()
        )

        self.assertTrue(
            get_user_model().objects.filter(pk=normal["buyer"].pk).exists()
        )
        self.assertTrue(
            ManufacturerProfile.objects.filter(
                pk=normal["manufacturer"].pk
            ).exists()
        )
        self.assertTrue(
            CapacityListing.objects.filter(pk=normal["listing"].pk).exists()
        )
        self.assertTrue(Order.objects.filter(pk=normal["order"].pk).exists())

    def test_seeded_demo_records_survive_cleanup(self):
        self.create_e2e_graph()
        call_command("seed_demo_data", verbosity=0)

        call_command("cleanup_e2e_data", stdout=StringIO())

        self.assertEqual(
            ManufacturerProfile.objects.filter(
                user__username__startswith="demo_mfr_",
            ).count(),
            5,
        )
        self.assertEqual(
            CapacityListing.objects.filter(
                manufacturer__user__username__startswith="demo_mfr_",
            ).count(),
            10,
        )
        self.assertTrue(
            CapacityListing.objects.filter(
                title="Custom Corrugated Packaging for D2C Shipments",
                manufacturer__business_name="Nila Packworks",
            ).exists()
        )


class LandingPageTests(TestCase):
    def test_root_renders_landing_while_marketplace_keeps_search_ui(self):
        root_response = self.client.get(reverse("home"))
        self.assertEqual(root_response.status_code, 200)
        self.assertContains(
            root_response,
            "Find manufacturers with spare capacity for small-batch orders",
        )
        self.assertNotContains(root_response, "Source manufacturing. Faster.")

        marketplace_response = self.client.get(reverse("marketplace"))
        self.assertEqual(marketplace_response.status_code, 200)
        self.assertContains(marketplace_response, "Browse manufacturing capacity")
        self.assertContains(marketplace_response, 'class="marketplace-discovery"')
        self.assertNotContains(marketplace_response, "Source manufacturing. Faster.")

    def make_listing(self, index, *, sample=False, active=True, category=CapacityListing.Category.METAL):
        User = get_user_model()
        username = f"{'demo_mfr_' if sample else 'landing_maker_'}{index}"
        user = User.objects.create_user(username=username, password="password", role="MANUFACTURER")
        profile = ManufacturerProfile.objects.create(
            user=user,
            business_name=f"Capacity Maker {index}",
            city="Pune",
            state="Maharashtra",
            is_verified=not sample,
        )
        return CapacityListing.objects.create(
            manufacturer=profile,
            title=f"Capacity listing {index}",
            category=category,
            description="Production capacity details.",
            price_per_unit=Decimal("12.50"),
            minimum_quantity=25,
            production_days=7,
            availability_status=CapacityListing.AvailabilityStatus.AVAILABLE,
            is_active=active,
        )

    def test_homepage_has_one_h1_search_and_marketplace_ctas(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertEqual(len(re.findall(r"<h1\b", content)), 1)
        self.assertRegex(content, r'<form[^>]+method="get"[^>]+action="/marketplace/"')
        self.assertRegex(content, r'<input[^>]+name="q"')
        self.assertContains(response, 'href="/marketplace/" data-analytics="hero_browse"')
        self.assertContains(response, 'href="/accounts/register/manufacturer/" data-analytics="hero_list"')

    def test_categories_only_show_real_active_listing_counts_and_routes(self):
        self.make_listing(1, category=CapacityListing.Category.METAL)
        self.make_listing(2, category=CapacityListing.Category.METAL, active=False)
        response = self.client.get(reverse("home"))
        self.assertContains(response, 'href="/marketplace/?category=METAL"')
        self.assertContains(response, "1 listing")
        self.assertNotContains(response, "0 listings")
        self.assertNotContains(response, "+ manufacturers")

    def test_featured_capacity_is_hidden_below_three_qualifying_listings(self):
        self.make_listing(1)
        self.make_listing(2)
        response = self.client.get(reverse("home"))
        self.assertNotContains(response, 'id="featured-title"')

    def test_featured_capacity_shows_three_and_sample_has_no_quote_cta(self):
        self.make_listing(1)
        self.make_listing(2)
        sample = self.make_listing(3, sample=True)
        response = self.client.get(reverse("home"))
        content = response.content.decode()
        self.assertContains(response, 'id="featured-title"')
        sample_start = content.index(f'data-sample-listing="true"')
        sample_end = content.index("</article>", sample_start)
        sample_card = content[sample_start:sample_end]
        self.assertNotIn("Request a quote", sample_card)
        self.assertNotIn("request-quote", sample_card)
        self.assertIn(str(sample.title), sample_card)

    def test_no_listings_means_no_empty_optional_sections_or_fake_counts(self):
        response = self.client.get(reverse("home"))
        content = response.content.decode()
        self.assertNotIn('id="featured-title"', content)
        self.assertNotIn('id="categories-title"', content)
        self.assertNotIn("0 manufacturers", content)
        self.assertNotIn("0 listings", content)
        self.assertNotIn("500+", content)
        self.assertNotIn("2,000+", content)

    def test_landing_faq_and_schema_are_not_duplicated(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(len(parse_json_ld(response)), 2)
        self.assertContains(response, "Does the platform process payments or escrow?")
        self.assertContains(response, "Sample listings are shown for illustration.")
