import json

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase
from django.urls import reverse

from marketplace.models import (
    CapacityListing,
    ManufacturerProfile,
    Milestone,
    Notification,
    Order,
    OrderMessage,
    PaymentTransaction,
    PaymentWebhookEvent,
    Quotation,
    QuoteRequest,
    Review,
    SavedListing,
    ContactSubmission,
    WaitlistEntry,
)
from marketplace.querysets import order_queryset_for_user

from .models import AuthRateLimitBucket
from .privacy import has_active_workflows

User = get_user_model()
PASSWORD = "Local-Test-Password-42!"


class PrivacyTestDataMixin:
    def make_user(self, username, role=User.Role.BUYER):
        return User.objects.create_user(
            username=username,
            email=f"{username}@example.test",
            password=PASSWORD,
            phone="+919876543210",
            role=role,
        )

    def make_listing(self, manufacturer, title):
        return CapacityListing.objects.create(
            manufacturer=manufacturer,
            title=title,
            description="Owned listing description",
            price_per_unit="12.50",
            minimum_quantity=10,
            production_days=8,
        )

    def make_order(self, buyer, profile, listing, status=Order.Status.COMPLETED):
        return Order.objects.create(
            source=Order.Source.BUY_NOW,
            buyer=buyer,
            manufacturer=profile,
            listing=listing,
            specifications_snapshot={
                "private_counterparty": "DO_NOT_EXPORT",
                "requirements": "Historical buyer requirements",
                "delivery_location": "Private order delivery location",
            },
            quantity=10,
            agreed_unit_price="12.50",
            total_amount="125.00",
            agreed_production_days=8,
            status=status,
        )

    def get_export(self, user):
        client = Client()
        client.force_login(user)
        response = client.get(reverse("export_account_data"))
        self.assertEqual(response.status_code, 200)
        return response, json.loads(response.content)


class PrivacyDataExportTests(PrivacyTestDataMixin, TestCase):

    def test_anonymous_export_requires_authentication(self):
        response = self.client.get(reverse("export_account_data"))
        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('export_account_data')}",
        )

    def test_buyer_export_is_scoped_and_redacts_counterparty_and_secrets(self):
        buyer = self.make_user("export-buyer")
        other_buyer = self.make_user("unrelated-buyer")
        manufacturer = self.make_user("export-manufacturer", User.Role.MANUFACTURER)
        manufacturer.phone = "+911111111111"
        manufacturer.save(update_fields=["phone"])
        profile = ManufacturerProfile.objects.create(
            user=manufacturer,
            business_name="Public Business",
            description="Public business description",
            city="Pune",
            state="Maharashtra",
            pincode="411001",
        )
        listing = self.make_listing(profile, "Buyer-owned request listing")
        own_order = self.make_order(buyer, profile, listing)
        own_milestone = Milestone.objects.create(
            order=own_order,
            title="Production",
            percentage=80,
            amount="100.00",
            status=Milestone.Status.APPROVED,
            funding_status=Milestone.FundingStatus.FUNDED,
        )
        request = QuoteRequest.objects.create(
            buyer=buyer,
            listing=listing,
            quantity=15,
            requirements="Buyer submitted requirement",
            delivery_location="Buyer provided delivery location",
            status=QuoteRequest.Status.ACCEPTED,
        )
        quotation = Quotation.objects.create(
            quote_request=request,
            price_per_unit="12.00",
            quantity=15,
            production_days=7,
            message="Counterparty private contact should not be exported",
            status=Quotation.Status.ACCEPTED,
        )
        own_order.quotation = quotation
        own_order.save(update_fields=["quotation"])
        payment = PaymentTransaction.objects.create(
            buyer=buyer,
            milestone=own_milestone,
            amount="100.00",
            currency="INR",
            status=PaymentTransaction.Status.CAPTURED,
            provider_order_id="PROVIDER_ORDER_SECRET_SENTINEL",
            provider_payment_id="PROVIDER_PAYMENT_SECRET_SENTINEL",
        )
        PaymentWebhookEvent.objects.create(
            event_id="WEBHOOK_SECRET_SENTINEL",
            event_type="payment.captured",
            status=PaymentWebhookEvent.ProcessingStatus.PROCESSED,
            payment_transaction=payment,
            processing_note="PRIVATE_WEBHOOK_NOTE_SENTINEL",
        )
        OrderMessage.objects.create(
            order=own_order,
            sender=buyer,
            body="Buyer-authored message",
        )
        OrderMessage.objects.create(
            order=own_order,
            sender=manufacturer,
            body="Manufacturer reply visible to Buyer",
        )
        Review.objects.create(
            order=own_order,
            buyer=buyer,
            manufacturer=profile,
            quality_rating=5,
            timeliness_rating=4,
            communication_rating=5,
            overall_rating=5,
            comment="Buyer-authored review",
        )

        other_listing = self.make_listing(profile, "Other buyer listing")
        other_order = self.make_order(other_buyer, profile, other_listing)
        OrderMessage.objects.create(
            order=other_order,
            sender=manufacturer,
            body="Unrelated Buyer order message",
        )
        SavedListing.objects.create(buyer=buyer, listing=other_listing)
        Notification.objects.create(
            recipient=buyer,
            message="Private notification text",
            destination=Notification.Destination.BUYER_DASHBOARD,
            order=own_order,
        )
        AuthRateLimitBucket.objects.create(
            scope="login_identifier_failure",
            key_digest="f" * 64,
            window_start="2026-11-23T00:00:00Z",
            count=3,
        )
        ContactSubmission.objects.create(
            name="Unlinked contact",
            email=buyer.email,
            role=ContactSubmission.Role.BUYER,
            message="Unlinked contact message",
        )
        WaitlistEntry.objects.create(
            email=buyer.email,
            role=WaitlistEntry.Role.BUYER,
            note="Unlinked pilot note",
        )

        response, payload = self.get_export(buyer)
        body = response.content.decode()
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(
            response["Content-Disposition"],
            'attachment; filename="account-data-export.json"',
        )
        self.assertEqual(response["Cache-Control"], "private, no-store, max-age=0")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertEqual([item["order_id"] for item in payload["orders"]], [own_order.pk])
        self.assertEqual(
            {item["order_id"] for item in payload["orders"]},
            set(order_queryset_for_user(buyer).values_list("pk", flat=True)),
        )
        self.assertEqual([item["order_id"] for item in payload["milestones"]], [own_order.pk])
        self.assertEqual(payload["payments"][0]["status"], PaymentTransaction.Status.CAPTURED)
        self.assertEqual(payload["payments"][0]["amount"], "100.00")
        self.assertEqual(
            payload["orders"][0]["buyer_supplied_details"]["delivery_location"],
            "Private order delivery location",
        )
        self.assertEqual(
            payload["orders"][0]["buyer_supplied_details"]["requirements"],
            "Historical buyer requirements",
        )
        self.assertIsNone(payload["quotations"][0]["message"])
        self.assertIn("Buyer submitted requirement", body)
        self.assertIn("Buyer-authored message", body)
        self.assertEqual(
            [message["body"] for message in payload["order_messages"]],
            ["Buyer-authored message", "Manufacturer reply visible to Buyer"],
        )
        self.assertTrue(
            all(
                set(message) == {"order_id", "body", "created_at"}
                and message["order_id"] == own_order.pk
                for message in payload["order_messages"]
            )
        )
        self.assertNotIn("Unrelated Buyer order message", body)
        self.assertEqual(len(payload["orders"]), 1)
        self.assertEqual(payload["orders"][0]["order_id"], own_order.pk)
        self.assertEqual(
            {item["order_id"] for item in payload["orders"]},
            set(order_queryset_for_user(buyer).values_list("pk", flat=True)),
        )
        for private_value in (
            manufacturer.email,
            manufacturer.phone,
            other_buyer.email,
            "Counterparty private contact",
            "PROVIDER_ORDER_SECRET_SENTINEL",
            "PROVIDER_PAYMENT_SECRET_SENTINEL",
            "WEBHOOK_SECRET_SENTINEL",
            "PRIVATE_WEBHOOK_NOTE_SENTINEL",
            "f" * 64,
            "Unlinked contact message",
            "Unlinked pilot note",
            "Private notification text",
            "DO_NOT_EXPORT",
            buyer.password,
        ):
            self.assertNotIn(private_value, body)
        self.assertNotIn("password", payload["account"])
        self.assertEqual(payload["notifications"][0]["destination"], Notification.Destination.BUYER_DASHBOARD)

    def test_manufacturer_export_includes_only_owned_listings_and_safe_transactions(self):
        manufacturer_user = self.make_user("export-mfr", User.Role.MANUFACTURER)
        profile = ManufacturerProfile.objects.create(
            user=manufacturer_user,
            business_name="Exporter Works",
            description="Profile description",
            city="Surat",
            state="Gujarat",
            pincode="395003",
        )
        own_listing = self.make_listing(profile, "Own listing")
        other_user = self.make_user("other-export-mfr", User.Role.MANUFACTURER)
        other_profile = ManufacturerProfile.objects.create(
            user=other_user,
            business_name="Other private manufacturer business",
            description="Other profile private description",
            city="Delhi",
            state="Delhi",
        )
        other_listing = self.make_listing(other_profile, "Other listing title")
        buyer = self.make_user("mfr-export-buyer")
        buyer.phone = "+912222222222"
        buyer.save(update_fields=["phone"])
        quote_request = QuoteRequest.objects.create(
            buyer=buyer,
            listing=own_listing,
            quantity=25,
            requirements="Third party private requirements",
            delivery_location="Third party private address",
            status=QuoteRequest.Status.ACCEPTED,
        )
        Quotation.objects.create(
            quote_request=quote_request,
            price_per_unit="10.00",
            quantity=25,
            production_days=9,
            message="Manufacturer authored terms",
            status=Quotation.Status.ACCEPTED,
        )
        own_order = self.make_order(buyer, profile, own_listing)
        OrderMessage.objects.create(
            order=own_order,
            sender=manufacturer_user,
            body="Manufacturer order message",
        )
        OrderMessage.objects.create(
            order=own_order,
            sender=buyer,
            body="Buyer reply visible to Manufacturer",
        )
        unrelated_buyer = self.make_user("unrelated-order-buyer")
        unrelated_order = self.make_order(unrelated_buyer, other_profile, other_listing)
        OrderMessage.objects.create(
            order=unrelated_order,
            sender=other_user,
            body="Unrelated Manufacturer order message",
        )

        response, payload = self.get_export(manufacturer_user)
        body = response.content.decode()
        self.assertEqual([item["title"] for item in payload["listings"]], ["Own listing"])
        self.assertEqual(len(payload["quotations"]), 1)
        self.assertEqual(payload["quotations"][0]["message"], "Manufacturer authored terms")
        self.assertEqual(payload["orders"][0]["order_id"], own_order.pk)
        self.assertEqual(
            {item["order_id"] for item in payload["orders"]},
            set(order_queryset_for_user(manufacturer_user).values_list("pk", flat=True)),
        )
        self.assertIsNone(payload["orders"][0]["buyer_supplied_details"])
        self.assertEqual(
            [message["body"] for message in payload["order_messages"]],
            ["Manufacturer order message", "Buyer reply visible to Manufacturer"],
        )
        self.assertTrue(
            all(
                set(message) == {"order_id", "body", "created_at"}
                and message["order_id"] == own_order.pk
                for message in payload["order_messages"]
            )
        )
        self.assertNotIn("Unrelated Manufacturer order message", body)
        for private_value in (
            buyer.email,
            buyer.phone,
            "Third party private requirements",
            "Third party private address",
            "Other private manufacturer business",
            "Other profile private description",
            "Other listing title",
        ):
            self.assertNotIn(private_value, body)

    def test_manufacturer_to_buyer_change_removes_stale_profile_records_from_export(self):
        manufacturer = self.make_user("stale-profile-mfr", User.Role.MANUFACTURER)
        profile = ManufacturerProfile.objects.create(
            user=manufacturer,
            business_name="Former Manufacturer",
            city="Pune",
            state="Maharashtra",
        )
        listing = self.make_listing(profile, "Former manufacturer listing")
        buyer = self.make_user("stale-profile-buyer")
        order = self.make_order(buyer, profile, listing)
        milestone = Milestone.objects.create(
            order=order,
            title="Former manufacturer milestone",
            percentage=80,
            amount="100.00",
        )
        PaymentTransaction.objects.create(
            buyer=buyer,
            milestone=milestone,
            amount="100.00",
            currency="INR",
            status=PaymentTransaction.Status.CAPTURED,
        )
        OrderMessage.objects.create(
            order=order,
            sender=manufacturer,
            body="Former manufacturer order message",
        )
        quote_request = QuoteRequest.objects.create(
            buyer=buyer,
            listing=listing,
            quantity=10,
            requirements="Former manufacturer RFQ context",
            delivery_location="Private buyer location",
            status=QuoteRequest.Status.REJECTED,
        )
        Quotation.objects.create(
            quote_request=quote_request,
            price_per_unit="12.00",
            quantity=10,
            production_days=8,
            message="Former manufacturer quotation",
            status=Quotation.Status.DECLINED,
        )

        manufacturer.role = User.Role.BUYER
        manufacturer.save(update_fields=["role"])

        self.assertTrue(ManufacturerProfile.objects.filter(pk=profile.pk).exists())
        self.assertFalse(order_queryset_for_user(manufacturer).filter(pk=order.pk).exists())
        ui_client = Client()
        ui_client.force_login(manufacturer)
        self.assertEqual(
            ui_client.get(reverse("order_detail", args=[order.pk])).status_code,
            404,
        )
        _response, payload = self.get_export(manufacturer)
        ui_order_ids = set(
            order_queryset_for_user(manufacturer).values_list("pk", flat=True)
        )
        self.assertEqual(
            {item["order_id"] for item in payload["orders"]},
            ui_order_ids,
        )
        self.assertNotIn(order.pk, ui_order_ids)
        self.assertNotIn(order.pk, [item["order_id"] for item in payload["milestones"]])
        self.assertNotIn(order.pk, [item["order_id"] for item in payload["payments"]])
        self.assertNotIn(order.pk, [item["order_id"] for item in payload["order_messages"]])
        self.assertNotIn("Former manufacturer order message", json.dumps(payload))
        self.assertNotIn("Former manufacturer quotation", json.dumps(payload))
        self.assertNotIn("Former manufacturer listing", json.dumps(payload))
        self.assertEqual(payload["orders"], [])
        self.assertEqual(payload["milestones"], [])
        self.assertEqual(payload["payments"], [])
        self.assertEqual(payload["order_messages"], [])
        self.assertEqual(payload["quotations"], [])
        self.assertEqual(payload["listings"], [])

    def test_buyer_to_manufacturer_change_matches_current_role_order_scope(self):
        user = self.make_user("role-change-user", User.Role.BUYER)
        former_manufacturer = self.make_user(
            "role-change-old-mfr", User.Role.MANUFACTURER
        )
        former_profile = ManufacturerProfile.objects.create(
            user=former_manufacturer,
            business_name="Old manufacturer",
            city="Pune",
            state="Maharashtra",
        )
        former_listing = self.make_listing(former_profile, "Former buyer listing")
        former_buyer_order = self.make_order(user, former_profile, former_listing)
        former_buyer_milestone = Milestone.objects.create(
            order=former_buyer_order,
            title="Former buyer milestone",
            percentage=80,
            amount="100.00",
        )
        PaymentTransaction.objects.create(
            buyer=user,
            milestone=former_buyer_milestone,
            amount="100.00",
            currency="INR",
            status=PaymentTransaction.Status.CAPTURED,
        )
        former_request = QuoteRequest.objects.create(
            buyer=user,
            listing=former_listing,
            quantity=10,
            requirements="Former buyer RFQ requirements",
            delivery_location="Former buyer location",
            status=QuoteRequest.Status.REJECTED,
        )
        Quotation.objects.create(
            quote_request=former_request,
            price_per_unit="12.00",
            quantity=10,
            production_days=8,
            status=Quotation.Status.DECLINED,
        )
        OrderMessage.objects.create(
            order=former_buyer_order,
            sender=user,
            body="Former buyer order message",
        )
        Review.objects.create(
            order=former_buyer_order,
            buyer=user,
            manufacturer=former_profile,
            quality_rating=5,
            timeliness_rating=5,
            communication_rating=5,
            overall_rating=5,
            comment="Former buyer review",
        )

        user.role = User.Role.MANUFACTURER
        user.save(update_fields=["role"])
        profile = ManufacturerProfile.objects.create(
            user=user,
            business_name="Current manufacturer",
            city="Surat",
            state="Gujarat",
        )
        listing = self.make_listing(profile, "Current manufacturer listing")
        buyer = self.make_user("role-change-new-buyer")
        manufacturer_order = self.make_order(buyer, profile, listing)
        milestone = Milestone.objects.create(
            order=manufacturer_order,
            title="Current manufacturer milestone",
            percentage=80,
            amount="100.00",
        )
        PaymentTransaction.objects.create(
            buyer=buyer,
            milestone=milestone,
            amount="100.00",
            currency="INR",
            status=PaymentTransaction.Status.CAPTURED,
        )
        OrderMessage.objects.create(
            order=manufacturer_order,
            sender=user,
            body="Current manufacturer order message",
        )
        OrderMessage.objects.create(
            order=manufacturer_order,
            sender=buyer,
            body="Current buyer reply",
        )
        manufacturer_request = QuoteRequest.objects.create(
            buyer=buyer,
            listing=listing,
            quantity=10,
            requirements="Counterparty request excluded from manufacturer export",
            delivery_location="Counterparty location excluded",
            status=QuoteRequest.Status.REJECTED,
        )
        Quotation.objects.create(
            quote_request=manufacturer_request,
            price_per_unit="12.00",
            quantity=10,
            production_days=8,
            message="Current manufacturer quotation",
            status=Quotation.Status.DECLINED,
        )

        self.assertFalse(
            order_queryset_for_user(user).filter(pk=former_buyer_order.pk).exists()
        )
        self.assertTrue(
            order_queryset_for_user(user).filter(pk=manufacturer_order.pk).exists()
        )
        _response, payload = self.get_export(user)
        ui_order_ids = set(order_queryset_for_user(user).values_list("pk", flat=True))
        export_order_ids = {item["order_id"] for item in payload["orders"]}
        self.assertEqual(export_order_ids, ui_order_ids)
        self.assertEqual(export_order_ids, {manufacturer_order.pk})
        self.assertEqual(
            [item["order_id"] for item in payload["milestones"]],
            [milestone.order_id],
        )
        self.assertEqual(
            [item["order_id"] for item in payload["payments"]],
            [milestone.order_id],
        )
        self.assertEqual(
            [item["body"] for item in payload["order_messages"]],
            ["Current manufacturer order message", "Current buyer reply"],
        )
        self.assertEqual(payload["quote_requests"], [])
        self.assertEqual(len(payload["quotations"]), 1)
        self.assertEqual(
            payload["quotations"][0]["message"], "Current manufacturer quotation"
        )
        serialized = json.dumps(payload)
        self.assertNotIn("Former buyer order message", serialized)
        self.assertNotIn("Former buyer review", serialized)
        self.assertNotIn("Former buyer RFQ requirements", serialized)
        self.assertNotIn("Former buyer location", serialized)
        self.assertNotIn("Counterparty request excluded", serialized)
        self.assertNotIn("Counterparty location excluded", serialized)

    def test_empty_export_is_valid_json_and_does_not_require_related_rows(self):
        buyer = self.make_user("empty-export")
        response, payload = self.get_export(buyer)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["orders"], [])
        self.assertEqual(payload["milestones"], [])
        self.assertEqual(payload["payments"], [])
        self.assertEqual(payload["manufacturer_profile"], None)


class AccountClosureTests(PrivacyTestDataMixin, TestCase):
    def make_active_order(self, buyer, profile, listing):
        return self.make_order(buyer, profile, listing, status=Order.Status.IN_PRODUCTION)

    def closure_client(self, user, csrf=True):
        client = Client(enforce_csrf_checks=csrf)
        client.force_login(user)
        return client

    def test_buyer_closure_anonymizes_pii_preserves_completed_history_and_sessions(self):
        buyer = self.make_user("close-buyer")
        original_email = buyer.email
        original_username = buyer.username
        original_phone = buyer.phone
        manufacturer = self.make_user("history-mfr", User.Role.MANUFACTURER)
        profile = ManufacturerProfile.objects.create(
            user=manufacturer,
            business_name="History Works",
            description="Mfr profile",
            city="Mumbai",
            state="Maharashtra",
        )
        listing = self.make_listing(profile, "History listing")
        order = self.make_order(buyer, profile, listing)
        cancelled_order = self.make_order(
            buyer,
            profile,
            listing,
            status=Order.Status.CANCELLED,
        )
        milestone = Milestone.objects.create(
            order=order,
            title="Production",
            percentage=80,
            amount="100.00",
            status=Milestone.Status.APPROVED,
            funding_status=Milestone.FundingStatus.RELEASED,
        )
        quote_request = QuoteRequest.objects.create(
            buyer=buyer,
            listing=listing,
            quantity=10,
            requirements="Private RFQ text",
            delivery_location="Private delivery location",
            status=QuoteRequest.Status.ACCEPTED,
        )
        quotation = Quotation.objects.create(
            quote_request=quote_request,
            price_per_unit="12.50",
            quantity=10,
            production_days=8,
            status=Quotation.Status.ACCEPTED,
        )
        order.quotation = quotation
        order.save(update_fields=["quotation"])
        payment = PaymentTransaction.objects.create(
            buyer=buyer,
            milestone=milestone,
            amount="100.00",
            currency="INR",
            status=PaymentTransaction.Status.CAPTURED,
            provider_order_id="unchanged-order-ref",
            provider_payment_id="unchanged-payment-ref",
        )
        message = OrderMessage.objects.create(
            order=order,
            sender=buyer,
            body="Buyer private message text",
        )
        review = Review.objects.create(
            order=order,
            buyer=buyer,
            manufacturer=profile,
            quality_rating=5,
            timeliness_rating=5,
            communication_rating=4,
            overall_rating=5,
            comment="Review with personal detail",
        )
        second_client = Client()
        second_client.force_login(buyer)
        client = self.closure_client(buyer)
        privacy_response = client.get(reverse("privacy_settings"))
        self.assertEqual(privacy_response.status_code, 200)
        csrf_token = client.cookies["csrftoken"].value
        response = client.post(
            reverse("close_account"),
            {"password": PASSWORD, "confirmation": "CLOSE", "csrfmiddlewaretoken": csrf_token},
        )

        self.assertRedirects(response, reverse("account_closed"))
        buyer.refresh_from_db()
        self.assertFalse(buyer.is_active)
        self.assertFalse(buyer.has_usable_password())
        self.assertEqual((buyer.first_name, buyer.last_name, buyer.phone), ("", "", ""))
        self.assertNotEqual(buyer.email, original_email)
        self.assertNotIn(original_email, buyer.email)
        self.assertNotIn(original_email, buyer.username)
        self.assertNotIn(original_username, buyer.username)
        self.assertTrue(buyer.email.endswith("@invalid.local"))
        self.assertIsNone(buyer.terms_accepted_at)
        self.assertFalse(client.session.get("_auth_user_id"))
        self.assertEqual(second_client.get(reverse("privacy_settings")).status_code, 302)

        order.refresh_from_db()
        quote_request.refresh_from_db()
        quotation.refresh_from_db()
        milestone.refresh_from_db()
        payment.refresh_from_db()
        message.refresh_from_db()
        review.refresh_from_db()
        self.assertEqual(order.buyer_id, buyer.pk)
        self.assertEqual(order.status, Order.Status.COMPLETED)
        self.assertNotIn("delivery_location", order.specifications_snapshot)
        self.assertEqual(
            order.specifications_snapshot["requirements"],
            "Historical buyer requirements",
        )
        self.assertEqual(
            order.specifications_snapshot["private_counterparty"],
            "DO_NOT_EXPORT",
        )
        self.assertEqual(quote_request.status, QuoteRequest.Status.ACCEPTED)
        self.assertEqual((quote_request.requirements, quote_request.delivery_location), ("", ""))
        cancelled_order.refresh_from_db()
        self.assertTrue(Order.objects.filter(pk=cancelled_order.pk).exists())
        self.assertEqual(cancelled_order.status, Order.Status.CANCELLED)
        self.assertEqual(
            cancelled_order.specifications_snapshot["requirements"],
            "Historical buyer requirements",
        )
        self.assertNotIn("delivery_location", cancelled_order.specifications_snapshot)
        self.assertEqual(quotation.status, Quotation.Status.ACCEPTED)
        self.assertEqual(milestone.status, Milestone.Status.APPROVED)
        self.assertEqual(payment.status, PaymentTransaction.Status.CAPTURED)
        self.assertEqual(payment.provider_order_id, "unchanged-order-ref")
        self.assertEqual(payment.provider_payment_id, "unchanged-payment-ref")
        self.assertEqual(message.body, "[Message content removed at account closure]")
        self.assertEqual(review.comment, "")

        login_client = Client()
        login_response = login_client.post(
            reverse("login"),
            {"username": original_email, "password": PASSWORD},
        )
        self.assertEqual(login_response.status_code, 200)
        self.assertNotIn("_auth_user_id", login_client.session)
        username_login_client = Client()
        username_login_response = username_login_client.post(
            reverse("login"),
            {"username": original_username, "password": PASSWORD},
        )
        self.assertEqual(username_login_response.status_code, 200)
        self.assertNotIn("_auth_user_id", username_login_client.session)
        reset_response = Client().post(
            reverse("password_reset"),
            {"email": original_email},
        )
        self.assertRedirects(reset_response, reverse("password_reset_done"))
        self.assertEqual(mail.outbox, [])

    def test_manufacturer_closure_unpublishes_profile_and_preserves_history(self):
        manufacturer = self.make_user("close-manufacturer", User.Role.MANUFACTURER)
        original_email = manufacturer.email
        profile = ManufacturerProfile.objects.create(
            user=manufacturer,
            business_name="Personal Manufacturer Name",
            description="Private profile text",
            city="Jaipur",
            state="Rajasthan",
            pincode="302001",
            is_verified=True,
            kyc_status=ManufacturerProfile.KycStatus.VERIFIED,
        )
        listing = self.make_listing(profile, "Historical capability")
        buyer = self.make_user("historical-buyer")
        order = self.make_order(buyer, profile, listing)
        quote_request = QuoteRequest.objects.create(
            buyer=buyer,
            listing=listing,
            quantity=10,
            requirements="Completed commercial request",
            delivery_location="Pune",
            status=QuoteRequest.Status.REJECTED,
        )
        quotation = Quotation.objects.create(
            quote_request=quote_request,
            price_per_unit="12.50",
            quantity=10,
            production_days=8,
            message="Commercial offer terms retained",
            status=Quotation.Status.DECLINED,
        )
        client = self.closure_client(manufacturer)
        csrf_token = client.get(reverse("privacy_settings")).cookies["csrftoken"].value
        response = client.post(
            reverse("close_account"),
            {"password": PASSWORD, "confirmation": "CLOSE", "csrfmiddlewaretoken": csrf_token},
        )
        self.assertRedirects(response, reverse("account_closed"))

        manufacturer.refresh_from_db()
        profile.refresh_from_db()
        listing.refresh_from_db()
        order.refresh_from_db()
        quotation.refresh_from_db()
        self.assertFalse(manufacturer.is_active)
        self.assertNotEqual(manufacturer.email, original_email)
        self.assertEqual(profile.business_name, "Closed manufacturer account")
        self.assertEqual((profile.description, profile.city, profile.state, profile.pincode), ("", "", "", ""))
        self.assertFalse(profile.is_verified)
        self.assertEqual(profile.kyc_status, ManufacturerProfile.KycStatus.VERIFIED)
        self.assertFalse(listing.is_active)
        self.assertEqual(listing.availability_status, CapacityListing.AvailabilityStatus.PAUSED)
        self.assertEqual(listing.title, "Historical capability")
        self.assertEqual(order.manufacturer_id, profile.pk)
        self.assertEqual(Order.objects.filter(pk=order.pk).count(), 1)
        self.assertEqual(quotation.message, "Commercial offer terms retained")
        public_profile = Client().get(reverse("manufacturer_profile", args=[profile.pk]))
        self.assertEqual(public_profile.status_code, 404)

    def test_active_order_blocks_closure_without_partial_changes(self):
        buyer = self.make_user("blocked-closure")
        original_email = buyer.email
        manufacturer = self.make_user("blocked-mfr", User.Role.MANUFACTURER)
        profile = ManufacturerProfile.objects.create(
            user=manufacturer,
            business_name="Blocked Profile",
            city="Pune",
            state="Maharashtra",
        )
        listing = self.make_listing(profile, "Active-work listing")
        order = self.make_active_order(buyer, profile, listing)
        client = self.closure_client(buyer)
        csrf_token = client.get(reverse("privacy_settings")).cookies["csrftoken"].value
        response = client.post(
            reverse("close_account"),
            {"password": PASSWORD, "confirmation": "CLOSE", "csrfmiddlewaretoken": csrf_token},
        )
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Resolve active orders", status_code=400)
        buyer.refresh_from_db()
        order.refresh_from_db()
        self.assertTrue(buyer.is_active)
        self.assertEqual(buyer.email, original_email)
        self.assertEqual(order.status, Order.Status.IN_PRODUCTION)
        self.assertEqual(
            order.specifications_snapshot["requirements"],
            "Historical buyer requirements",
        )

    def test_manufacturer_with_active_order_is_not_anonymized(self):
        buyer = self.make_user("active-order-buyer")
        manufacturer = self.make_user("active-order-mfr", User.Role.MANUFACTURER)
        original_email = manufacturer.email
        profile = ManufacturerProfile.objects.create(
            user=manufacturer,
            business_name="Active Manufacturer Profile",
            city="Pune",
            state="Maharashtra",
        )
        listing = self.make_listing(profile, "Active manufacturer listing")
        order = self.make_active_order(buyer, profile, listing)
        client = self.closure_client(manufacturer)
        csrf_token = client.get(reverse("privacy_settings")).cookies["csrftoken"].value

        response = client.post(
            reverse("close_account"),
            {
                "password": PASSWORD,
                "confirmation": "CLOSE",
                "csrfmiddlewaretoken": csrf_token,
            },
        )

        self.assertEqual(response.status_code, 400)
        manufacturer.refresh_from_db()
        profile.refresh_from_db()
        order.refresh_from_db()
        self.assertTrue(manufacturer.is_active)
        self.assertEqual(manufacturer.email, original_email)
        self.assertEqual(profile.business_name, "Active Manufacturer Profile")
        self.assertEqual(order.status, Order.Status.IN_PRODUCTION)

    def test_pending_quote_and_created_payment_also_block_closure(self):
        buyer = self.make_user("pending-close-buyer")
        manufacturer = self.make_user("pending-close-mfr", User.Role.MANUFACTURER)
        profile = ManufacturerProfile.objects.create(
            user=manufacturer,
            business_name="Pending Profile",
            city="Pune",
            state="Maharashtra",
        )
        listing = self.make_listing(profile, "Pending quote listing")
        quote = QuoteRequest.objects.create(
            buyer=buyer,
            listing=listing,
            quantity=10,
            requirements="Pending quote",
            delivery_location="Location",
        )
        self.assertTrue(has_active_workflows(buyer))
        quote.status = QuoteRequest.Status.REJECTED
        quote.save(update_fields=["status"])
        accepted_request = QuoteRequest.objects.create(
            buyer=buyer,
            listing=listing,
            quantity=10,
            requirements="Accepted quote awaiting its order",
            delivery_location="Location",
            status=QuoteRequest.Status.ACCEPTED,
        )
        Quotation.objects.create(
            quote_request=accepted_request,
            price_per_unit="11.00",
            quantity=10,
            production_days=7,
            status=Quotation.Status.ACCEPTED,
        )
        self.assertTrue(has_active_workflows(buyer))
        Quotation.objects.filter(quote_request=accepted_request).update(
            status=Quotation.Status.DECLINED
        )
        order = self.make_order(buyer, profile, listing)
        milestone = Milestone.objects.create(
            order=order,
            title="Payment pending",
            percentage=80,
            amount="100.00",
        )
        PaymentTransaction.objects.create(
            buyer=buyer,
            milestone=milestone,
            amount="100.00",
            currency="INR",
            status=PaymentTransaction.Status.CREATED,
        )
        self.assertTrue(has_active_workflows(buyer))

    def test_get_and_missing_csrf_do_not_close_account(self):
        buyer = self.make_user("csrf-close")
        client = self.closure_client(buyer)
        response = client.get(reverse("close_account"))
        self.assertEqual(response.status_code, 405)
        self.assertEqual(
            Client(enforce_csrf_checks=True).post(
                reverse("close_account"),
                {"password": PASSWORD, "confirmation": "CLOSE"},
            ).status_code,
            403,
        )
        buyer.refresh_from_db()
        self.assertTrue(buyer.is_active)

    def test_wrong_password_and_bad_confirmation_do_not_close(self):
        buyer = self.make_user("reauth-close")
        client = self.closure_client(buyer)
        csrf_token = client.get(reverse("privacy_settings")).cookies["csrftoken"].value
        response = client.post(
            reverse("close_account"),
            {"password": "wrong", "confirmation": "CLOSE", "csrfmiddlewaretoken": csrf_token},
        )
        self.assertEqual(response.status_code, 400)
        response = client.post(
            reverse("close_account"),
            {"password": PASSWORD, "confirmation": "DELETE", "csrfmiddlewaretoken": csrf_token},
        )
        self.assertEqual(response.status_code, 400)
        buyer.refresh_from_db()
        self.assertTrue(buyer.is_active)

    def test_duplicate_closure_is_safe_and_event_log_has_no_account_pii(self):
        buyer = self.make_user("event-close")
        old_email = buyer.email
        client = Client()
        client.force_login(buyer)
        with self.assertLogs("accounts.privacy", level="INFO") as captured:
            with self.captureOnCommitCallbacks(execute=True):
                response = client.post(
                    reverse("close_account"),
                    {"password": PASSWORD, "confirmation": "CLOSE"},
                )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(all(old_email not in line for line in captured.output))
        user_count = User.objects.count()
        self.assertEqual(
            client.post(
                reverse("close_account"),
                {"password": PASSWORD, "confirmation": "CLOSE"},
            ).status_code,
            302,
        )
        self.assertEqual(User.objects.count(), user_count)

    def test_contact_and_waitlist_records_are_not_exported_or_deleted_automatically(self):
        buyer = self.make_user("manual-request")
        ContactSubmission.objects.create(
            name="Manual contact",
            email=buyer.email,
            role=ContactSubmission.Role.BUYER,
            message="Contact retained pending review",
        )
        WaitlistEntry.objects.create(
            email=buyer.email,
            role=WaitlistEntry.Role.BUYER,
        )
        _, payload = self.get_export(buyer)
        self.assertNotIn("contact_submissions", payload)
        self.assertNotIn("waitlist", payload)
        self.assertTrue(ContactSubmission.objects.filter(email=buyer.email).exists())
        self.assertTrue(WaitlistEntry.objects.filter(email=buyer.email).exists())

    def test_admin_cannot_hard_delete_users_or_manufacturer_profiles(self):
        buyer = self.make_user("admin-delete-buyer")
        manufacturer = self.make_user("admin-delete-mfr", User.Role.MANUFACTURER)
        profile = ManufacturerProfile.objects.create(
            user=manufacturer,
            business_name="Admin protected profile",
            city="Pune",
            state="Maharashtra",
        )
        staff = User.objects.create_superuser(
            username="privacy-admin",
            email="privacy-admin@example.test",
            password=PASSWORD,
        )
        client = Client()
        client.force_login(staff)
        user_admin = admin.site._registry[User]
        profile_admin = admin.site._registry[ManufacturerProfile]
        request = type("AdminRequest", (), {"user": staff})()
        self.assertFalse(user_admin.has_delete_permission(request, buyer))
        self.assertIsNone(user_admin.actions)
        self.assertFalse(profile_admin.has_delete_permission(request, profile))
        user_delete = client.post(reverse("admin:accounts_user_delete", args=[buyer.pk]), {"post": "yes"})
        profile_delete = client.post(
            reverse("admin:marketplace_manufacturerprofile_delete", args=[profile.pk]),
            {"post": "yes"},
        )
        self.assertEqual(user_delete.status_code, 403)
        self.assertEqual(profile_delete.status_code, 403)
        self.assertTrue(User.objects.filter(pk=buyer.pk).exists())
        self.assertTrue(ManufacturerProfile.objects.filter(pk=profile.pk).exists())
        self.assertTrue(User.objects.filter(pk=manufacturer.pk).exists())


class WorkflowClosureCoordinationTests(PrivacyTestDataMixin, TestCase):
    def test_inactive_participant_blocks_new_buy_now_and_quote_request(self):
        buyer = self.make_user("workflow-buyer")
        manufacturer = self.make_user("workflow-mfr", User.Role.MANUFACTURER)
        profile = ManufacturerProfile.objects.create(
            user=manufacturer,
            business_name="Workflow Profile",
            city="Pune",
            state="Maharashtra",
            is_verified=True,
        )
        listing = self.make_listing(profile, "Workflow listing")
        manufacturer.is_active = False
        manufacturer.save(update_fields=["is_active"])

        client = Client()
        client.force_login(buyer)

        buy_now_url = reverse("buy_now", args=[listing.pk])
        buy_now_token = client.get(buy_now_url).context["action_token"]
        buy_response = client.post(
            buy_now_url,
            {
                "quantity": listing.minimum_quantity,
                "delivery_location": "Pune",
                "action_token": buy_now_token,
            },
        )
        self.assertEqual(buy_response.status_code, 200)
        self.assertContains(buy_response, "account involved in this purchase is no longer active")
        self.assertFalse(Order.objects.filter(listing=listing).exists())

        quote_url = reverse("request_quote", args=[listing.pk])
        quote_token = client.get(quote_url).context["action_token"]
        quote_response = client.post(
            quote_url,
            {
                "quantity": listing.minimum_quantity,
                "requirements": "New request",
                "delivery_location": "Pune",
                "action_token": quote_token,
            },
        )
        self.assertEqual(quote_response.status_code, 200)
        self.assertContains(quote_response, "account involved in this request is no longer active")
        self.assertFalse(QuoteRequest.objects.filter(listing=listing).exists())
        self.assertFalse(Notification.objects.filter(recipient=manufacturer).exists())
