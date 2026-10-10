from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import (
    CapacityListing,
    ManufacturerProfile,
    Notification,
    Order,
    OrderMessage,
    Quotation,
    QuoteRequest,
)


@override_settings(
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
