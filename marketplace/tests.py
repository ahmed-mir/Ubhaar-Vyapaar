from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

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
