from decimal import Decimal
from io import StringIO
import tempfile

from django.contrib.auth import get_user_model
from django.core.management import call_command
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

    def test_paused_listings_follow_available_listings_in_default_discovery(self):
        paused = self.create_listing(
            self.verified,
            "Paused capacity",
            CapacityListing.AvailabilityStatus.PAUSED,
        )
        available = self.create_listing(self.verified, "Available capacity")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(response.context["listings"].object_list),
            [available, paused],
        )
        self.assertContains(response, "Paused")

    def test_zero_count_categories_are_hidden_and_note_is_shown(self):
        self.create_listing(self.verified, "Metal capacity")

        response = self.client.get(reverse("home"))

        self.assertContains(response, "Metal")
        self.assertNotContains(response, "Plastics")
        self.assertContains(response, "More categories coming soon.")

    def test_verified_badge_requires_real_state_and_demo_content_is_marked(self):
        self.create_listing(self.verified, "Verified capacity")
        self.create_listing(self.demo, "Demo capacity")

        response = self.client.get(reverse("home"))
        content = response.content.decode()

        self.assertIn("Verified business", content)
        self.assertIn("Sample listing", content)

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

        response = self.client.get(reverse("home"))
        self.assertContains(response, reverse("trust_safety"))
        self.assertContains(response, reverse("about"))
        self.assertContains(response, reverse("contact"))
        self.assertContains(response, reverse("pricing_fees"))
        self.assertContains(response, reverse("faq"))


class SeededSampleNameTests(TestCase):
    def test_seeded_names_stay_sample_classified_and_cleanup_is_idempotent(self):
        call_command("seed_demo_data", stdout=StringIO())

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

        response = self.client.get(reverse("home"))
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
    def test_sentry_is_disabled_without_dsn_and_privacy_defaults_are_safe(self):
        from django.conf import settings

        self.assertFalse(settings.SENTRY_DSN)
        self.assertFalse(settings.SENTRY_ENABLED)
        self.assertFalse(settings.SENTRY_SEND_DEFAULT_PII)
        self.assertEqual(settings.SENTRY_TRACES_SAMPLE_RATE, 0.0)

    @override_settings(LEGAL_CONTACT_EMAIL="")
    def test_contact_page_omits_missing_contact_details(self):
        response = self.client.get(reverse("contact"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "not configured yet")
        self.assertNotContains(response, "mailto:")

    @override_settings(
        LEGAL_ENTITY_NAME="Configured Marketplace Entity",
        LEGAL_CONTACT_EMAIL="support@example.com",
        LEGAL_CONTACT_LABEL="Support email",
    )
    def test_configured_contact_values_are_shared_with_footer(self):
        contact_response = self.client.get(reverse("contact"))
        home_response = self.client.get(reverse("home"))

        self.assertContains(contact_response, "support@example.com")
        self.assertContains(home_response, "Configured Marketplace Entity")
        self.assertContains(home_response, "support@example.com")
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

    def test_cookie_policy_does_not_claim_optional_tracking(self):
        response = self.client.get(reverse("cookie_policy"))

        self.assertContains(response, "None found in the current code audit")
        self.assertNotContains(response, "Accept All")

    def test_terms_disclose_simulated_payments(self):
        response = self.client.get(reverse("terms"))

        self.assertContains(response, "does not currently process real payments")
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
        self.assertContains(response, reverse("home"))
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

    def test_robots_txt_guides_private_area_exclusion(self):
        response = self.client.get(reverse("robots_txt"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/plain; charset=utf-8")
        self.assertContains(response, "Disallow: /admin/")
        self.assertContains(response, "Disallow: /accounts/")
        self.assertContains(response, "Disallow: /orders/")
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
        home_response = self.client.get(reverse("home"))

        self.assertContains(home_response, "listing-media-frame")
        self.assertContains(home_response, "media-no-image")
        self.assertContains(home_response, "fallback-brand-mark")
        self.assertContains(home_response, "Manufacturing capacity")
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

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["listings"]), 6)
        self.assertGreater(response.context["page_obj"].paginator.count, 6)


class CleanupE2EDataCommandTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.TemporaryDirectory()
        self.override = override_settings(
            MEDIA_ROOT=self.media_root.name,
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
