from collections import OrderedDict

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from marketplace.models import (
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


E2E_USER_PREFIXES = (
    "uv-e2e-buyer-",
    "uv-e2e-manufacturer-",
    "uv-e2e-buyeraccess-",
    "uv-e2e-manufactureraccess-",
    "uv-e2e-commercebuyer-",
    "uv-e2e-otherbuyer-",
    "uv-e2e-commercemfr-",
)

E2E_BUSINESS_PREFIXES = (
    "UV E2E Verified Works ",
    "UV E2E Works ",
    "UV E2E Access Works ",
)

E2E_LISTING_PREFIXES = (
    "UV E2E Verified Capacity ",
    "UV E2E Unverified Capacity ",
)


class Command(BaseCommand):
    help = (
        "Remove only obvious automated E2E test records created by the "
        "Playwright production smoke tests."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print matching records and counts without deleting anything.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        plan = self._build_cleanup_plan()

        self.stdout.write(
            self.style.WARNING(
                "DRY RUN: no records will be deleted."
                if dry_run
                else "Deleting matched E2E records."
            )
        )
        self.stdout.write(
            "Selectors: exact uv-e2e production-test account prefixes, "
            "UV E2E business prefixes, and UV E2E listing prefixes."
        )

        for label, records in plan.items():
            self.stdout.write(f"\n{label}: {len(records)}")
            for record in records:
                self.stdout.write(f"  - {record['text']}")

        self.stdout.write("\nCounts by model:")
        for label, records in plan.items():
            self.stdout.write(f"  {label}: {len(records)}")

        if dry_run:
            return

        with transaction.atomic():
            self._delete_plan(plan)

        self.stdout.write(self.style.SUCCESS("E2E cleanup complete."))

    def _build_cleanup_plan(self):
        User = get_user_model()

        user_selector = Q()
        for prefix in E2E_USER_PREFIXES:
            user_selector |= Q(username__startswith=prefix)

        business_selector = Q()
        for prefix in E2E_BUSINESS_PREFIXES:
            business_selector |= Q(business_name__startswith=prefix)

        listing_selector = Q()
        for prefix in E2E_LISTING_PREFIXES:
            listing_selector |= Q(title__startswith=prefix)

        profile_user_ids = ManufacturerProfile.objects.filter(
            business_selector
        ).values_list("user_id", flat=True)

        users = User.objects.filter(
            (
                user_selector
                & Q(email__startswith="uv-e2e-")
                & Q(email__endswith="@example.com")
            )
            | Q(pk__in=profile_user_ids)
        ).distinct()
        user_ids = list(users.values_list("pk", flat=True))

        manufacturers = ManufacturerProfile.objects.filter(
            Q(user_id__in=user_ids) | business_selector
        ).distinct()
        manufacturer_ids = list(manufacturers.values_list("pk", flat=True))

        listings = CapacityListing.objects.filter(
            Q(manufacturer_id__in=manufacturer_ids) | listing_selector
        ).distinct()
        listing_ids = list(listings.values_list("pk", flat=True))

        quote_requests = QuoteRequest.objects.filter(
            Q(buyer_id__in=user_ids) | Q(listing_id__in=listing_ids)
        ).distinct()
        quote_request_ids = set(quote_requests.values_list("pk", flat=True))

        quotations = Quotation.objects.filter(
            quote_request_id__in=quote_request_ids
        ).distinct()
        quotation_ids = set(quotations.values_list("pk", flat=True))

        orders = Order.objects.filter(
            Q(buyer_id__in=user_ids)
            | Q(manufacturer_id__in=manufacturer_ids)
            | Q(listing_id__in=listing_ids)
            | Q(quotation_id__in=quotation_ids)
        ).distinct()
        order_ids = list(orders.values_list("pk", flat=True))

        quotation_ids.update(
            Order.objects.filter(pk__in=order_ids).values_list(
                "quotation_id", flat=True
            )
        )
        quotations = Quotation.objects.filter(pk__in=quotation_ids)

        quote_request_ids.update(
            quotations.values_list("quote_request_id", flat=True)
        )
        quote_requests = QuoteRequest.objects.filter(pk__in=quote_request_ids)

        return OrderedDict(
            (
                (
                    "Notifications",
                    self._describe_queryset(
                        Notification.objects.filter(
                            Q(recipient_id__in=user_ids)
                            | Q(order_id__in=order_ids)
                        ).distinct(),
                        self._describe_notification,
                    ),
                ),
                (
                    "Saved listings",
                    self._describe_queryset(
                        SavedListing.objects.filter(
                            Q(buyer_id__in=user_ids)
                            | Q(listing_id__in=listing_ids)
                        ).distinct(),
                        self._describe_saved_listing,
                    ),
                ),
                (
                    "Order messages",
                    self._describe_queryset(
                        OrderMessage.objects.filter(
                            Q(order_id__in=order_ids)
                            | Q(sender_id__in=user_ids)
                        ).distinct(),
                        self._describe_order_message,
                    ),
                ),
                (
                    "Reviews",
                    self._describe_queryset(
                        Review.objects.filter(
                            Q(order_id__in=order_ids)
                            | Q(buyer_id__in=user_ids)
                            | Q(manufacturer_id__in=manufacturer_ids)
                        ).distinct(),
                        self._describe_review,
                    ),
                ),
                (
                    "Milestones",
                    self._describe_queryset(
                        Milestone.objects.filter(order_id__in=order_ids),
                        self._describe_milestone,
                    ),
                ),
                (
                    "Orders",
                    self._describe_queryset(orders, self._describe_order),
                ),
                (
                    "Quotations",
                    self._describe_queryset(
                        quotations, self._describe_quotation
                    ),
                ),
                (
                    "Quote requests",
                    self._describe_queryset(
                        quote_requests, self._describe_quote_request
                    ),
                ),
                (
                    "Listings",
                    self._describe_queryset(listings, self._describe_listing),
                ),
                (
                    "Manufacturers",
                    self._describe_queryset(
                        manufacturers, self._describe_manufacturer
                    ),
                ),
                ("Users", self._describe_queryset(users, self._describe_user)),
            )
        )

    def _delete_plan(self, plan):
        model_by_label = OrderedDict(
            (
                ("Notifications", Notification),
                ("Saved listings", SavedListing),
                ("Order messages", OrderMessage),
                ("Reviews", Review),
                ("Milestones", Milestone),
                ("Orders", Order),
                ("Quotations", Quotation),
                ("Quote requests", QuoteRequest),
                ("Listings", CapacityListing),
                ("Manufacturers", ManufacturerProfile),
                ("Users", get_user_model()),
            )
        )

        for label, model in model_by_label.items():
            ids = [record["pk"] for record in plan[label]]
            if ids:
                model.objects.filter(pk__in=ids).delete()

    def _describe_queryset(self, queryset, describe):
        return [
            {"pk": obj.pk, "text": describe(obj)}
            for obj in queryset.order_by("pk")
        ]

    def _describe_user(self, user):
        return (
            f"User #{user.pk}: username={user.username}, "
            f"email={user.email}, role={user.role}"
        )

    def _describe_manufacturer(self, manufacturer):
        return (
            f"Manufacturer #{manufacturer.pk}: "
            f"{manufacturer.business_name} "
            f"(user={manufacturer.user_id})"
        )

    def _describe_listing(self, listing):
        return (
            f"Listing #{listing.pk}: {listing.title} "
            f"(manufacturer={listing.manufacturer_id})"
        )

    def _describe_quote_request(self, quote_request):
        return (
            f"QuoteRequest #{quote_request.pk}: "
            f"buyer={quote_request.buyer_id}, "
            f"listing={quote_request.listing_id}"
        )

    def _describe_quotation(self, quotation):
        return (
            f"Quotation #{quotation.pk}: "
            f"quote_request={quotation.quote_request_id}, "
            f"status={quotation.status}"
        )

    def _describe_order(self, order):
        return (
            f"Order #{order.pk}: buyer={order.buyer_id}, "
            f"manufacturer={order.manufacturer_id}, "
            f"listing={order.listing_id}"
        )

    def _describe_milestone(self, milestone):
        return f"Milestone #{milestone.pk}: order={milestone.order_id}"

    def _describe_review(self, review):
        return (
            f"Review #{review.pk}: order={review.order_id}, "
            f"buyer={review.buyer_id}, "
            f"manufacturer={review.manufacturer_id}"
        )

    def _describe_order_message(self, message):
        return (
            f"OrderMessage #{message.pk}: order={message.order_id}, "
            f"sender={message.sender_id}"
        )

    def _describe_saved_listing(self, saved_listing):
        return (
            f"SavedListing #{saved_listing.pk}: "
            f"buyer={saved_listing.buyer_id}, "
            f"listing={saved_listing.listing_id}"
        )

    def _describe_notification(self, notification):
        return (
            f"Notification #{notification.pk}: "
            f"recipient={notification.recipient_id}, "
            f"order={notification.order_id}"
        )
