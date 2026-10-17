from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.core.paginator import Paginator
from django.db import transaction
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from decimal import Decimal, InvalidOperation
from xml.sax.saxutils import escape

from django.conf import settings
from django.http import HttpResponse
from django.urls import reverse

from .forms import (
    CapacityListingEditForm,
    CapacityListingForm,
    OrderMessageForm,
    QuoteRequestForm,
    QuotationForm,
    ManufacturerProfileForm,
    ReviewForm,
)
from .models import (
    CapacityListing,
    ManufacturerProfile,
    Milestone,
    Notification,
    Order,
    QuoteRequest,
    Quotation,
    Review,
    SavedListing,
)
from django.db.models import Case, Count, IntegerField, Q, When
from django.views.decorators.http import require_POST


def legal_page_context():
    return {
        "legal_entity_name": settings.LEGAL_ENTITY_NAME,
        "legal_contact_email": settings.LEGAL_CONTACT_EMAIL,
        "legal_contact_label": settings.LEGAL_CONTACT_LABEL,
        "terms_version": settings.TERMS_VERSION,
        "privacy_policy_version": settings.PRIVACY_POLICY_VERSION,
    }


def privacy_policy(request):
    return render(
        request,
        "marketplace/privacy_policy.html",
        legal_page_context(),
    )


def terms(request):
    return render(
        request,
        "marketplace/terms.html",
        legal_page_context(),
    )


def cookie_policy(request):
    return render(
        request,
        "marketplace/cookie_policy.html",
        legal_page_context(),
    )


def refund_policy(request):
    return render(
        request,
        "marketplace/refund_policy.html",
        legal_page_context(),
    )


def about(request):
    return render(request, "marketplace/about.html")


def how_it_works(request):
    return render(request, "marketplace/how_it_works.html")


def for_manufacturers(request):
    return render(request, "marketplace/for_manufacturers.html")


def contact(request):
    return render(request, "marketplace/contact.html", legal_page_context())


def pricing_fees(request):
    return render(request, "marketplace/pricing_fees.html")


def trust_safety(request):
    return render(request, "marketplace/trust_safety.html")


def faq(request):
    return render(request, "marketplace/faq.html")


def grievance_redressal(request):
    return render(request, "marketplace/grievance_redressal.html", legal_page_context())


def help_page(request):
    return render(request, "marketplace/help.html", legal_page_context())


def absolute_url(request, path):
    return request.build_absolute_uri(path)


def sitemap_xml(request):
    public_urls = [
        (absolute_url(request, reverse("home")), "daily", "0.9"),
        (absolute_url(request, reverse("about")), "monthly", "0.4"),
        (absolute_url(request, reverse("how_it_works")), "monthly", "0.4"),
        (absolute_url(request, reverse("for_manufacturers")), "monthly", "0.4"),
        (absolute_url(request, reverse("contact")), "monthly", "0.3"),
        (absolute_url(request, reverse("pricing_fees")), "monthly", "0.3"),
        (absolute_url(request, reverse("trust_safety")), "monthly", "0.4"),
        (absolute_url(request, reverse("faq")), "monthly", "0.3"),
        (absolute_url(request, reverse("grievance_redressal")), "monthly", "0.3"),
        (absolute_url(request, reverse("help_page")), "monthly", "0.4"),
        (absolute_url(request, reverse("privacy_policy")), "monthly", "0.3"),
        (absolute_url(request, reverse("terms")), "monthly", "0.3"),
        (absolute_url(request, reverse("cookie_policy")), "monthly", "0.3"),
        (absolute_url(request, reverse("refund_policy")), "monthly", "0.3"),
    ]

    listings = CapacityListing.objects.filter(
        Q(is_active=True)
        & (
            Q(manufacturer__is_verified=True)
            | Q(manufacturer__user__username__startswith="demo_mfr_")
        ),
    ).order_by("pk")

    for listing in listings:
        public_urls.append((
            absolute_url(request, reverse("listing_detail", args=[listing.pk])),
            "weekly",
            "0.8",
        ))

    manufacturers = ManufacturerProfile.objects.filter(
        is_verified=True,
    ).order_by("pk")

    for manufacturer in manufacturers:
        public_urls.append((
            absolute_url(
                request,
                reverse("manufacturer_profile", args=[manufacturer.pk]),
            ),
            "weekly",
            "0.7",
        ))

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]

    for location, changefreq, priority in public_urls:
        lines.extend([
            "  <url>",
            f"    <loc>{escape(location)}</loc>",
            f"    <changefreq>{changefreq}</changefreq>",
            f"    <priority>{priority}</priority>",
            "  </url>",
        ])

    lines.append("</urlset>")

    return HttpResponse(
        "\n".join(lines),
        content_type="application/xml; charset=utf-8",
    )


def robots_txt(request):
    sitemap_url = absolute_url(request, reverse("sitemap_xml"))
    lines = [
        "User-agent: *",
        "Disallow: /admin/",
        "Disallow: /accounts/",
        "Disallow: /buyer/",
        "Disallow: /manufacturer/dashboard/",
        "Disallow: /manufacturer/orders/",
        "Disallow: /manufacturer/listings/",
        "Disallow: /my-quote-requests/",
        "Disallow: /saved-listings/",
        "Disallow: /orders/",
        "Disallow: /milestones/",
        "Disallow: /notifications/",
        "Allow: /",
        f"Sitemap: {sitemap_url}",
    ]

    return HttpResponse(
        "\n".join(lines) + "\n",
        content_type="text/plain; charset=utf-8",
    )


def create_order_from_quotation(quotation):
    quote_request = quotation.quote_request
    listing = quote_request.listing

    order, created = Order.objects.get_or_create(
        quotation=quotation,
        defaults={
            "buyer": quote_request.buyer,
            "manufacturer": listing.manufacturer,
            "listing": listing,
            "specifications_snapshot": {
                "listing_title": listing.title,
                "listing_category": listing.get_category_display(),
                "requirements": quote_request.requirements,
                "delivery_location": quote_request.delivery_location,
                "machine_type": listing.machine_type,
                "materials": listing.materials,
                "technical_capabilities": listing.technical_capabilities,
            },
            "quantity": quotation.quantity,
            "agreed_unit_price": quotation.price_per_unit,
            "total_amount": quotation.subtotal,
            "agreed_production_days": quotation.production_days,
            "status": Order.Status.AWAITING_FUNDING,
        },
    )

    if created:
        Milestone.objects.bulk_create(
            [
                Milestone(
                    order=order,
                    title="Production complete",
                    description=(
                        "Manufacturer marks this complete when production "
                        "is ready for buyer review."
                    ),
                    percentage=80,
                    amount=quotation.subtotal * Decimal("0.80"),
                ),
                Milestone(
                    order=order,
                    title="Ready to ship",
                    description=(
                        "Final packing or dispatch readiness checkpoint."
                    ),
                    percentage=20,
                    amount=quotation.subtotal * Decimal("0.20"),
                ),
            ]
        )

    return order, created


def order_queryset_for_user(user):
    orders = Order.objects.select_related(
        "buyer",
        "manufacturer",
        "manufacturer__user",
        "listing",
        "quotation",
    ).prefetch_related(
        "milestones",
        "messages",
        "messages__sender",
    )

    if user.role == "BUYER":
        return orders.filter(buyer=user)

    if user.role == "MANUFACTURER":
        return orders.filter(manufacturer__user=user)

    return Order.objects.none()


def get_order_for_user(user, pk):
    return get_object_or_404(order_queryset_for_user(user), pk=pk)


def get_order_message_recipient(order, sender):
    if sender == order.buyer:
        return order.manufacturer.user

    if sender == order.manufacturer.user:
        return order.buyer

    raise PermissionDenied("You do not have access to this order.")


def create_order_notification(recipient, message, order):
    return Notification.objects.create(
        recipient=recipient,
        message=message,
        destination=Notification.Destination.ORDER_DETAIL,
        order=order,
    )


def concise_label(value, limit=72):
    text = str(value or "").strip()

    if len(text) <= limit:
        return text

    return f"{text[:limit - 3]}..."


def notify_order_status_change(order, previous_status):
    if previous_status == order.status:
        return

    status_label = order.get_status_display()
    message = (
        f"Order #{order.pk} is now {status_label}. "
        "Open the order to review the next workflow action."
    )

    create_order_notification(order.buyer, message, order)
    create_order_notification(order.manufacturer.user, message, order)


def refresh_order_status(order):
    previous_status = order.status
    milestones = list(order.milestones.all())

    if not milestones:
        return previous_status, order.status

    if all(
        milestone.status == Milestone.Status.APPROVED
        and milestone.funding_status == Milestone.FundingStatus.RELEASED
        for milestone in milestones
    ):
        order.status = Order.Status.COMPLETED
    elif any(
        milestone.status == Milestone.Status.COMPLETED
        for milestone in milestones
    ):
        order.status = Order.Status.MILESTONE_PENDING
    elif any(
        milestone.status in {
            Milestone.Status.IN_PROGRESS,
            Milestone.Status.APPROVED,
            Milestone.Status.REJECTED,
        }
        for milestone in milestones
    ):
        order.status = Order.Status.IN_PRODUCTION
    elif any(
        milestone.funding_status
        in {
            Milestone.FundingStatus.FUNDED,
            Milestone.FundingStatus.RELEASED,
        }
        for milestone in milestones
    ):
        order.status = Order.Status.FUNDED
    else:
        order.status = Order.Status.AWAITING_FUNDING

    if previous_status != order.status:
        order.save(update_fields=["status", "updated_at"])

    return previous_status, order.status


def milestone_amount(milestone):
    return milestone.amount or Decimal("0.00")


def build_order_financial_summary(order, milestones):
    order_value = order.total_amount or Decimal("0.00")
    funded = sum(
        milestone_amount(milestone)
        for milestone in milestones
        if milestone.funding_status
        in {
            Milestone.FundingStatus.FUNDED,
            Milestone.FundingStatus.RELEASED,
        }
    )
    released = sum(
        milestone_amount(milestone)
        for milestone in milestones
        if milestone.funding_status == Milestone.FundingStatus.RELEASED
    )
    milestone_total = sum(milestone_amount(milestone) for milestone in milestones)
    remaining = max(order_value - funded, Decimal("0.00"))

    return {
        "order_value": order_value,
        "milestone_total": milestone_total,
        "funded": funded,
        "released": released,
        "remaining": remaining,
    }


def order_is_closed(order):
    return order.status in {
        Order.Status.COMPLETED,
        Order.Status.CANCELLED,
        Order.Status.DISPUTED,
    }


def add_milestone_action_flags(milestone, user):
    closed = order_is_closed(milestone.order)

    milestone.can_fund = (
        user.role == "BUYER"
        and not closed
        and milestone.status == Milestone.Status.PENDING
        and milestone.funding_status == Milestone.FundingStatus.NOT_FUNDED
    )
    milestone.can_start = (
        user.role == "MANUFACTURER"
        and not closed
        and milestone.status in {
            Milestone.Status.PENDING,
            Milestone.Status.REJECTED,
        }
        and milestone.funding_status == Milestone.FundingStatus.FUNDED
    )
    milestone.can_submit = (
        user.role == "MANUFACTURER"
        and not closed
        and milestone.status == Milestone.Status.IN_PROGRESS
        and milestone.funding_status == Milestone.FundingStatus.FUNDED
    )
    milestone.can_review = (
        user.role == "BUYER"
        and not closed
        and milestone.status == Milestone.Status.COMPLETED
    )
    milestone.can_release = (
        user.role == "BUYER"
        and not closed
        and milestone.status == Milestone.Status.APPROVED
        and milestone.funding_status == Milestone.FundingStatus.FUNDED
    )

    if milestone.status == Milestone.Status.PENDING:
        if milestone.funding_status == Milestone.FundingStatus.NOT_FUNDED:
            milestone.workflow_hint = "Awaiting buyer demo funding."
        else:
            milestone.workflow_hint = "Ready for manufacturer to start."
    elif milestone.status == Milestone.Status.IN_PROGRESS:
        milestone.workflow_hint = "Manufacturer is working on this milestone."
    elif milestone.status == Milestone.Status.COMPLETED:
        milestone.workflow_hint = "Awaiting buyer review."
    elif milestone.status == Milestone.Status.APPROVED:
        if milestone.funding_status == Milestone.FundingStatus.RELEASED:
            milestone.workflow_hint = "Approved and demo payment released."
        else:
            milestone.workflow_hint = "Approved; awaiting demo release."
    elif milestone.status == Milestone.Status.REJECTED:
        milestone.workflow_hint = "Changes requested by buyer."
    else:
        milestone.workflow_hint = milestone.get_status_display()

    return milestone


def build_next_action(order, user, milestones):
    if order_is_closed(order):
        if order.status == Order.Status.COMPLETED and user.role == "BUYER":
            if not Review.objects.filter(order=order, buyer=user).exists():
                return {
                    "title": "Review the manufacturer",
                    "body": "This order is complete. Share feedback from the completed production workflow.",
                    "url_name": "review_order",
                    "url_arg": order.pk,
                    "button": "Write review",
                }

        return {
            "title": "No action required",
            "body": f"Order #{order.pk} is {order.get_status_display().lower()}.",
        }

    for milestone in milestones:
        if user.role == "BUYER":
            if milestone.can_fund:
                return {
                    "title": f"Confirm demo funding for {milestone.title}",
                    "body": "This is a simulated funding step. No real payment will be processed.",
                    "url_name": "fund_milestone",
                    "url_arg": milestone.pk,
                    "button": "Fund milestone (demo)",
                }
            if milestone.can_review:
                return {
                    "title": f"Review {milestone.title}",
                    "body": "The manufacturer submitted this milestone for buyer approval.",
                    "anchor": f"milestone-{milestone.pk}",
                    "button": "Review milestone",
                }
            if milestone.can_release:
                return {
                    "title": f"Release demo payment for {milestone.title}",
                    "body": "The milestone is approved. Release the simulated milestone amount to complete this step.",
                    "anchor": f"milestone-{milestone.pk}",
                    "button": "Release demo payment",
                }

        if user.role == "MANUFACTURER":
            if milestone.can_start:
                return {
                    "title": f"Start {milestone.title}",
                    "body": "The buyer has demo-funded this milestone. Start work when production is ready.",
                    "anchor": f"milestone-{milestone.pk}",
                    "button": "Start milestone",
                }
            if milestone.can_submit:
                return {
                    "title": f"Submit {milestone.title}",
                    "body": "Mark this milestone ready when the buyer should review it.",
                    "anchor": f"milestone-{milestone.pk}",
                    "button": "Submit for approval",
                }

    return {
        "title": "No immediate action",
        "body": "The order is moving through the current workflow. Use messages for order-specific updates.",
    }


def build_order_timeline(order, milestones):
    has_milestones = bool(milestones)
    all_funded = has_milestones and all(
        milestone.funding_status
        in {
            Milestone.FundingStatus.FUNDED,
            Milestone.FundingStatus.RELEASED,
        }
        for milestone in milestones
    )
    has_production = any(
        milestone.status
        in {
            Milestone.Status.IN_PROGRESS,
            Milestone.Status.COMPLETED,
            Milestone.Status.APPROVED,
        }
        for milestone in milestones
    )
    has_submission = any(
        milestone.status
        in {
            Milestone.Status.COMPLETED,
            Milestone.Status.APPROVED,
        }
        for milestone in milestones
    )
    all_approved = has_milestones and all(
        milestone.status == Milestone.Status.APPROVED
        for milestone in milestones
    )
    all_released = has_milestones and all(
        milestone.funding_status == Milestone.FundingStatus.RELEASED
        for milestone in milestones
    )
    has_order_review = Review.objects.filter(order=order).exists()

    return [
        {
            "title": "Quotation accepted",
            "body": "Buyer accepted the quotation.",
            "complete": order.quotation.status == Quotation.Status.ACCEPTED,
            "date": order.quotation.responded_at,
        },
        {
            "title": "Order created",
            "body": "Commercial terms were locked into a demo order.",
            "complete": True,
            "date": order.created_at,
        },
        {
            "title": "Milestones",
            "body": "Production checkpoints were created for this order.",
            "complete": has_milestones,
        },
        {
            "title": "Demo funding",
            "body": "All milestone funding is simulated; no real money is held.",
            "complete": all_funded,
        },
        {
            "title": "Production",
            "body": "Manufacturer works through funded milestones.",
            "complete": has_production,
        },
        {
            "title": "Submission",
            "body": "Manufacturer submits milestone work for buyer review.",
            "complete": has_submission,
        },
        {
            "title": "Approval",
            "body": "Buyer approves submitted milestones.",
            "complete": all_approved,
        },
        {
            "title": "Demo release",
            "body": "Approved milestone amounts are marked released in demo mode.",
            "complete": all_released,
        },
        {
            "title": "Completion",
            "body": "All milestones approved and demo releases completed.",
            "complete": order.status == Order.Status.COMPLETED,
            "date": order.updated_at if order.status == Order.Status.COMPLETED else None,
        },
        {
            "title": "Review",
            "body": "Buyer can leave a completed-order review.",
            "complete": has_order_review,
        },
    ]

def home(request):
    query = request.GET.get("q", "").strip()
    selected_category = request.GET.get("category", "").strip()
    location = request.GET.get("location", "").strip()
    moq = request.GET.get("moq", "").strip()
    max_price = request.GET.get("max_price", "").strip()
    lead_time = request.GET.get("lead_time", "").strip()
    verification = request.GET.get("verification", "").strip()
    sort = request.GET.get("sort", "newest").strip()

    valid_categories = {
        value for value, label in CapacityListing.Category.choices
    }

    if selected_category not in valid_categories:
        selected_category = ""

    valid_sorts = {"newest", "price", "lead_time"}

    if sort not in valid_sorts:
        sort = "newest"

    public_listings = CapacityListing.objects.filter(
        is_active=True,
    ).filter(
        Q(manufacturer__is_verified=True)
        | Q(manufacturer__user__username__startswith="demo_mfr_")
    )

    category_counts = {
        item["category"]: item["total"]
        for item in public_listings.values("category").annotate(total=Count("pk"))
    }

    category_summaries = [
        {
            "value": value,
            "label": label,
            "count": category_counts.get(value, 0),
        }
        for value, label in CapacityListing.Category.choices
        if category_counts.get(value, 0)
    ]

    available_categories = tuple(
        (item["value"], item["label"])
        for item in category_summaries
    )

    listings = public_listings.select_related("manufacturer")

    if query:
        listings = listings.filter(
            Q(title__icontains=query)
            | Q(manufacturer__business_name__icontains=query)
            | Q(manufacturer__city__icontains=query)
            | Q(manufacturer__state__icontains=query)
            | Q(description__icontains=query)
            | Q(machine_type__icontains=query)
            | Q(materials__icontains=query)
            | Q(technical_capabilities__icontains=query)
            | Q(cluster__icontains=query)
        )

    if selected_category:
        listings = listings.filter(category=selected_category)

    if location:
        listings = listings.filter(
            Q(manufacturer__city__icontains=location)
            | Q(manufacturer__state__icontains=location)
            | Q(cluster__icontains=location)
        )

    if moq.isdigit():
        listings = listings.filter(minimum_quantity__lte=int(moq))

    try:
        if max_price:
            listings = listings.filter(
                price_per_unit__lte=Decimal(max_price)
            )
    except (InvalidOperation, ValueError):
        max_price = ""

    if lead_time.isdigit():
        listings = listings.filter(production_days__lte=int(lead_time))

    if verification and verification != "verified":
        verification = ""

    listings = listings.annotate(
        paused_rank=Case(
            When(
                availability_status=CapacityListing.AvailabilityStatus.PAUSED,
                then=1,
            ),
            default=0,
            output_field=IntegerField(),
        )
    )

    if sort == "price":
        listings = listings.order_by("paused_rank", "price_per_unit", "-pk")
    elif sort == "lead_time":
        listings = listings.order_by("paused_rank", "production_days", "-pk")
    else:
        listings = listings.order_by("paused_rank", "-pk")

    paginator = Paginator(listings, 6)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "marketplace/home.html",
        {
            "listings": page_obj,
            "page_obj": page_obj,
            "query": query,
            "categories": available_categories,
            "category_summaries": category_summaries,
            "has_more_categories": len(available_categories) < len(CapacityListing.Category.choices),
            "selected_category": selected_category,
            "location": location,
            "moq": moq,
            "max_price": max_price,
            "lead_time": lead_time,
            "verification": verification,
            "sort": sort,
        },
    )
def listing_detail(request, pk):
    listing = get_object_or_404(
        CapacityListing.objects.select_related("manufacturer"),
        Q(manufacturer__is_verified=True)
        | Q(manufacturer__user__username__startswith="demo_mfr_"),
        pk=pk,
        is_active=True,
    )

    is_saved = False

    if request.user.is_authenticated and request.user.role == "BUYER":
        is_saved = SavedListing.objects.filter(
            buyer=request.user,
            listing=listing,
        ).exists()

    return render(
        request,
        "marketplace/listing_detail.html",
        {
            "listing": listing,
            "is_saved": is_saved,
        },
    )
@login_required
def request_quote(request, pk):
    if request.user.role != "BUYER":
        raise PermissionDenied(
            "Only buyer accounts can request quotes."
        )

    listing = get_object_or_404(
        CapacityListing.objects.select_related("manufacturer"),
        Q(manufacturer__is_verified=True)
        | Q(manufacturer__user__username__startswith="demo_mfr_"),
        pk=pk,
        is_active=True,
        availability_status__in=[
            CapacityListing.AvailabilityStatus.AVAILABLE,
            CapacityListing.AvailabilityStatus.LIMITED,
        ],
    )

    if request.method == "POST":
        form = QuoteRequestForm(request.POST, listing=listing)

        if form.is_valid():
            with transaction.atomic():
                quote = form.save(commit=False)
                quote.buyer = request.user
                quote.listing = listing
                quote.save()

                Notification.objects.create(
                    recipient_id=listing.manufacturer.user_id,
                    message=(
                        f"New quote request #{quote.pk} for {concise_label(listing.title)}: "
                        f"{quote.quantity} units requested. Review and respond."
                    ),
                    destination=(
                        Notification.Destination.MANUFACTURER_DASHBOARD
                    ),
                )

            messages.success(
                request,
                "Your quote request was submitted.",
            )

            return redirect("request_quote", pk=listing.pk)
    else:
        form = QuoteRequestForm(listing=listing)

    recent_quote = listing.quote_requests.filter(
        buyer=request.user,
    ).order_by("-created_at", "-pk").first()

    return render(
        request,
        "marketplace/request_quote.html",
        {
            "form": form,
            "listing": listing,
            "recent_quote": recent_quote,
        },
    )
@login_required
def my_quote_requests(request):
    if request.user.role != "BUYER":
        raise PermissionDenied(
            "Only buyer accounts can view this page."
        )

    quotes = QuoteRequest.objects.filter(
        buyer=request.user,
    ).select_related(
        "listing",
        "listing__manufacturer",
        "quotation",
        "quotation__order",
    ).order_by("-created_at", "-pk")

    buyer_quotations = Quotation.objects.filter(
        quote_request__buyer=request.user,
    )

    stats = {
        "total_requests": quotes.count(),
        "pending_requests": quotes.filter(
            status=QuoteRequest.Status.PENDING,
        ).count(),
        "awaiting_response": buyer_quotations.filter(
            status=Quotation.Status.SENT,
        ).count(),
        "accepted_quotations": buyer_quotations.filter(
            status=Quotation.Status.ACCEPTED,
        ).count(),
    }

    return render(
        request,
        "marketplace/my_quote_requests.html",
        {
            "quotes": quotes,
            "stats": stats,
        },
    )


@login_required
def buyer_dashboard(request):
    if request.user.role != "BUYER":
        raise PermissionDenied(
            "Only buyer accounts can view this page."
        )

    quote_requests = QuoteRequest.objects.filter(
        buyer=request.user,
    ).select_related(
        "listing",
        "listing__manufacturer",
        "quotation",
    ).order_by("-created_at", "-pk")

    quotations = Quotation.objects.filter(
        quote_request__buyer=request.user,
    ).select_related(
        "quote_request",
        "quote_request__listing",
        "quote_request__listing__manufacturer",
        "order",
    )

    pending_quotations = quotations.filter(
        status=Quotation.Status.SENT,
    ).order_by("-created_at", "-pk")

    accepted_quotations = quotations.filter(
        status=Quotation.Status.ACCEPTED,
    ).order_by("-responded_at", "-pk")

    active_requests = quote_requests.filter(
        status__in=[
            QuoteRequest.Status.PENDING,
            QuoteRequest.Status.ACCEPTED,
        ],
    )[:6]

    saved_items = SavedListing.objects.filter(
        buyer=request.user,
    ).select_related(
        "listing",
        "listing__manufacturer",
    ).order_by("-created_at", "-pk")[:4]

    notifications = Notification.objects.filter(
        recipient=request.user,
    ).order_by("-created_at", "-pk")[:5]

    active_order_queryset = Order.objects.filter(
        buyer=request.user,
    ).exclude(
        status__in=[
            Order.Status.COMPLETED,
            Order.Status.CANCELLED,
        ],
    )

    active_orders = active_order_queryset.select_related(
        "listing",
        "manufacturer",
    )[:4]

    funding_milestones = Milestone.objects.filter(
        order__buyer=request.user,
        order__status__in=[
            Order.Status.AWAITING_FUNDING,
            Order.Status.FUNDED,
            Order.Status.IN_PRODUCTION,
            Order.Status.MILESTONE_PENDING,
        ],
        status=Milestone.Status.PENDING,
        funding_status=Milestone.FundingStatus.NOT_FUNDED,
    ).select_related("order", "order__manufacturer", "order__listing")

    review_milestones = Milestone.objects.filter(
        order__buyer=request.user,
        order__status__in=[
            Order.Status.IN_PRODUCTION,
            Order.Status.MILESTONE_PENDING,
        ],
        status=Milestone.Status.COMPLETED,
    ).select_related("order", "order__manufacturer", "order__listing")

    release_milestones = Milestone.objects.filter(
        order__buyer=request.user,
        order__status__in=[
            Order.Status.IN_PRODUCTION,
            Order.Status.MILESTONE_PENDING,
            Order.Status.FUNDED,
        ],
        status=Milestone.Status.APPROVED,
        funding_status=Milestone.FundingStatus.FUNDED,
    ).select_related("order", "order__manufacturer", "order__listing")

    stats = {
        "active_requests": quote_requests.filter(
            status__in=[
                QuoteRequest.Status.PENDING,
                QuoteRequest.Status.ACCEPTED,
            ],
        ).count(),
        "quotations_received": quotations.count(),
        "pending_actions": pending_quotations.count(),
        "accepted_quotations": quotations.filter(
            status=Quotation.Status.ACCEPTED,
        ).count(),
        "saved_listings": SavedListing.objects.filter(
            buyer=request.user,
        ).count(),
        "unread_notifications": Notification.objects.filter(
            recipient=request.user,
            is_read=False,
        ).count(),
        "active_orders": active_order_queryset.count(),
        "milestones_to_fund": funding_milestones.count(),
        "milestones_to_review": review_milestones.count(),
        "demo_releases_due": release_milestones.count(),
    }

    return render(
        request,
        "marketplace/buyer_dashboard.html",
        {
            "stats": stats,
            "active_requests": active_requests,
            "pending_quotations": pending_quotations[:6],
            "accepted_quotations": accepted_quotations[:4],
            "active_orders": active_orders,
            "funding_milestones": funding_milestones[:4],
            "review_milestones": review_milestones[:4],
            "release_milestones": release_milestones[:4],
            "saved_items": saved_items,
            "notifications": notifications,
        },
    )


@login_required
def buyer_orders(request):
    if request.user.role != "BUYER":
        raise PermissionDenied("Only buyer accounts can view orders.")

    orders = Order.objects.filter(
        buyer=request.user,
    ).select_related("listing", "manufacturer").prefetch_related(
        "milestones",
    )

    return render(
        request,
        "marketplace/buyer_orders.html",
        {"orders": orders},
    )


@login_required
def manufacturer_orders(request):
    if request.user.role != "MANUFACTURER":
        raise PermissionDenied("Only manufacturers can view orders.")

    orders = Order.objects.filter(
        manufacturer__user=request.user,
    ).select_related("buyer", "listing").prefetch_related(
        "milestones",
    )

    return render(
        request,
        "marketplace/manufacturer_orders.html",
        {"orders": orders},
    )


@login_required
def order_detail(request, pk):
    order = get_order_for_user(request.user, pk)
    milestones = [
        add_milestone_action_flags(milestone, request.user)
        for milestone in order.milestones.all()
    ]
    financial_summary = build_order_financial_summary(order, milestones)
    next_action = build_next_action(order, request.user, milestones)
    timeline_steps = build_order_timeline(order, milestones)
    activity_items = Notification.objects.filter(
        recipient=request.user,
        order=order,
    ).order_by("-created_at", "-pk")[:8]

    return render(
        request,
        "marketplace/order_detail.html",
        {
            "order": order,
            "milestones": milestones,
            "financial_summary": financial_summary,
            "next_action": next_action,
            "timeline_steps": timeline_steps,
            "activity_items": activity_items,
            "message_form": OrderMessageForm(),
            "review_form": ReviewForm(),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def fund_milestone(request, pk):
    if request.user.role != "BUYER":
        raise PermissionDenied("Only buyers can demo-fund milestones.")

    milestone = get_object_or_404(
        Milestone.objects.select_related(
            "order",
            "order__buyer",
            "order__manufacturer",
            "order__manufacturer__user",
            "order__listing",
        ),
        pk=pk,
        order__buyer=request.user,
    )
    add_milestone_action_flags(milestone, request.user)

    if request.method == "GET":
        return render(
            request,
            "marketplace/fund_milestone.html",
            {
                "milestone": milestone,
                "order": milestone.order,
            },
        )

    if not milestone.can_fund:
        messages.info(
            request,
            "This milestone cannot be demo-funded in its current state.",
        )
        return redirect("order_detail", pk=milestone.order_id)

    with transaction.atomic():
        updated = Milestone.objects.filter(
            pk=milestone.pk,
            order__buyer=request.user,
            status=Milestone.Status.PENDING,
            funding_status=Milestone.FundingStatus.NOT_FUNDED,
        ).update(
            funding_status=Milestone.FundingStatus.FUNDED,
            funded_at=timezone.now(),
        )

        if updated:
            milestone.refresh_from_db()
            previous_order_status, _ = refresh_order_status(milestone.order)
            milestone_title = concise_label(milestone.title)

            create_order_notification(
                milestone.order.manufacturer.user,
                (
                    f"Buyer funded the {milestone_title} milestone for "
                    f"Order #{milestone.order_id} (demo funding). Start it "
                    "when production is ready."
                ),
                milestone.order,
            )
            create_order_notification(
                request.user,
                (
                    f"Demo funding confirmed for {milestone_title} on "
                    f"Order #{milestone.order_id}. No real money was processed."
                ),
                milestone.order,
            )
            notify_order_status_change(milestone.order, previous_order_status)

    if updated:
        messages.success(
            request,
            "Demo funding confirmed. No real payment was processed.",
        )
    else:
        messages.info(request, "This milestone was already funded or changed.")

    return redirect("order_detail", pk=milestone.order_id)


@login_required
@require_POST
def start_milestone(request, pk):
    if request.user.role != "MANUFACTURER":
        raise PermissionDenied("Only manufacturers can start milestones.")

    milestone = get_object_or_404(
        Milestone.objects.select_related(
            "order",
            "order__buyer",
            "order__manufacturer",
            "order__manufacturer__user",
        ),
        pk=pk,
        order__manufacturer__user=request.user,
    )
    add_milestone_action_flags(milestone, request.user)

    if not milestone.can_start:
        messages.info(
            request,
            "This milestone cannot be started until it is demo-funded.",
        )
        return redirect("order_detail", pk=milestone.order_id)

    with transaction.atomic():
        updated = Milestone.objects.filter(
            pk=milestone.pk,
            order__manufacturer__user=request.user,
            status__in=[
                Milestone.Status.PENDING,
                Milestone.Status.REJECTED,
            ],
            funding_status=Milestone.FundingStatus.FUNDED,
        ).update(
            status=Milestone.Status.IN_PROGRESS,
            started_at=timezone.now(),
        )

        if updated:
            milestone.refresh_from_db()
            previous_order_status, _ = refresh_order_status(milestone.order)
            milestone_title = concise_label(milestone.title)
            create_order_notification(
                milestone.order.buyer,
                (
                    f"Manufacturer started the {milestone_title} milestone "
                    f"for Order #{milestone.order_id}."
                ),
                milestone.order,
            )
            notify_order_status_change(milestone.order, previous_order_status)

    if updated:
        messages.success(request, "Milestone marked in progress.")
    else:
        messages.info(request, "This milestone has already changed.")

    return redirect("order_detail", pk=milestone.order_id)


@login_required
@require_POST
def send_order_message(request, pk):
    order = get_order_for_user(request.user, pk)
    form = OrderMessageForm(request.POST)

    if form.is_valid():
        with transaction.atomic():
            order_message = form.save(commit=False)
            order_message.order = order
            order_message.sender = request.user
            order_message.save()

            recipient = get_order_message_recipient(order, request.user)
            create_order_notification(
                recipient,
                f"New message on Order #{order.pk}. Open the order to reply.",
                order,
            )

        messages.success(request, "Message sent.")
    else:
        messages.error(request, "Please enter a message before sending.")

    return redirect("order_detail", pk=order.pk)


@login_required
@require_http_methods(["GET", "POST"])
def review_order(request, pk):
    if request.user.role != "BUYER":
        raise PermissionDenied("Only buyers can review completed orders.")

    order = get_object_or_404(
        Order.objects.select_related("manufacturer", "listing"),
        pk=pk,
        buyer=request.user,
        status=Order.Status.COMPLETED,
    )

    if Review.objects.filter(order=order, buyer=request.user).exists():
        messages.info(request, "You already reviewed this order.")
        return redirect("order_detail", pk=order.pk)

    if request.method == "POST":
        form = ReviewForm(request.POST)

        if form.is_valid():
            review = form.save(commit=False)
            review.order = order
            review.buyer = request.user
            review.manufacturer = order.manufacturer
            review.save()

            create_order_notification(
                order.manufacturer.user,
                f"The buyer reviewed Order #{order.pk}. View the completed-order feedback.",
                order,
            )

            messages.success(request, "Thank you for reviewing this order.")
            return redirect("order_detail", pk=order.pk)
    else:
        form = ReviewForm()

    return render(
        request,
        "marketplace/review_order.html",
        {
            "form": form,
            "order": order,
        },
    )


@login_required
@require_POST
def mark_milestone_complete(request, pk):
    if request.user.role != "MANUFACTURER":
        raise PermissionDenied("Only manufacturers can update milestones.")

    milestone = get_object_or_404(
        Milestone.objects.select_related("order", "order__buyer"),
        pk=pk,
        order__manufacturer__user=request.user,
    )

    add_milestone_action_flags(milestone, request.user)

    if milestone.can_submit:
        milestone.status = Milestone.Status.COMPLETED
        milestone.completed_at = timezone.now()
        milestone.save(update_fields=["status", "completed_at", "updated_at"])
        previous_order_status, _ = refresh_order_status(milestone.order)
        milestone_title = concise_label(milestone.title)

        create_order_notification(
            milestone.order.buyer,
            message=(
                f"{milestone_title} milestone is ready for your approval "
                f"on Order #{milestone.order_id}. Review the work and approve "
                "or request changes."
            ),
            order=milestone.order,
        )
        notify_order_status_change(milestone.order, previous_order_status)

        messages.success(
            request,
            "Milestone submitted for buyer approval.",
        )
    else:
        messages.info(
            request,
            "This milestone must be demo-funded and in progress before submission.",
        )

    return redirect("order_detail", pk=milestone.order_id)


@login_required
@require_POST
def respond_to_milestone(request, pk):
    if request.user.role != "BUYER":
        raise PermissionDenied("Only buyers can review milestones.")

    milestone = get_object_or_404(
        Milestone.objects.select_related(
            "order",
            "order__manufacturer",
            "order__manufacturer__user",
        ),
        pk=pk,
        order__buyer=request.user,
    )

    decision = request.POST.get("status")
    feedback = request.POST.get("buyer_feedback", "").strip()

    if decision not in {
        Milestone.Status.APPROVED,
        Milestone.Status.REJECTED,
    }:
        raise PermissionDenied("Invalid milestone response.")

    if milestone.status != Milestone.Status.COMPLETED:
        messages.info(request, "This milestone is not awaiting review.")
        return redirect("order_detail", pk=milestone.order_id)

    milestone.status = decision
    milestone.buyer_feedback = feedback

    if decision == Milestone.Status.APPROVED:
        milestone.approved_at = timezone.now()
    else:
        milestone.approved_at = None
        milestone.completed_at = None

    milestone.save(
        update_fields=[
            "status",
            "buyer_feedback",
            "approved_at",
            "completed_at",
            "updated_at",
        ]
    )
    previous_order_status, _ = refresh_order_status(milestone.order)
    milestone.order.refresh_from_db(fields=["status"])

    response_label = (
        "approved"
        if decision == Milestone.Status.APPROVED
        else "requested changes for"
    )
    milestone_title = concise_label(milestone.title)

    create_order_notification(
        milestone.order.manufacturer.user,
        message=(
            f"The buyer {response_label} the {milestone_title} milestone "
            f"on Order #{milestone.order_id}."
        ),
        order=milestone.order,
    )
    notify_order_status_change(milestone.order, previous_order_status)

    messages.success(request, "Milestone response saved.")
    return redirect("order_detail", pk=milestone.order_id)


@login_required
@require_POST
def release_milestone_payment(request, pk):
    if request.user.role != "BUYER":
        raise PermissionDenied("Only buyers can release demo milestone payments.")

    milestone = get_object_or_404(
        Milestone.objects.select_related(
            "order",
            "order__buyer",
            "order__manufacturer",
            "order__manufacturer__user",
        ),
        pk=pk,
        order__buyer=request.user,
    )
    add_milestone_action_flags(milestone, request.user)

    if not milestone.can_release:
        messages.info(
            request,
            "This milestone is not ready for demo payment release.",
        )
        return redirect("order_detail", pk=milestone.order_id)

    with transaction.atomic():
        updated = Milestone.objects.filter(
            pk=milestone.pk,
            order__buyer=request.user,
            status=Milestone.Status.APPROVED,
            funding_status=Milestone.FundingStatus.FUNDED,
        ).update(
            funding_status=Milestone.FundingStatus.RELEASED,
            released_at=timezone.now(),
        )

        if updated:
            milestone.refresh_from_db()
            previous_order_status, _ = refresh_order_status(milestone.order)
            milestone.order.refresh_from_db(fields=["status"])
            milestone_title = concise_label(milestone.title)

            create_order_notification(
                milestone.order.manufacturer.user,
                (
                    f"Buyer released demo payment for milestone "
                    f"{milestone_title} on Order #{milestone.order_id}. "
                    "No real money was transferred."
                ),
                milestone.order,
            )
            create_order_notification(
                request.user,
                (
                    f"Demo payment released for milestone "
                    f"{milestone_title} on Order #{milestone.order_id}. "
                    "No real money was transferred."
                ),
                milestone.order,
            )
            notify_order_status_change(milestone.order, previous_order_status)

            if (
                previous_order_status != Order.Status.COMPLETED
                and milestone.order.status == Order.Status.COMPLETED
            ):
                create_order_notification(
                    request.user,
                    message=(
                        f"Order #{milestone.order_id} is complete. "
                        "You can now leave a review."
                    ),
                    order=milestone.order,
                )

    if updated:
        messages.success(
            request,
            "Demo payment released. No real money was transferred.",
        )
    else:
        messages.info(request, "This milestone was already released or changed.")

    return redirect("order_detail", pk=milestone.order_id)


@login_required
def manufacturer_dashboard(request):
    if request.user.role != "MANUFACTURER":
        raise PermissionDenied(
            "Only manufacturer accounts can access this page."
        )

    listings = CapacityListing.objects.filter(
        manufacturer__user=request.user,
    )

    quotes = QuoteRequest.objects.filter(
        listing__manufacturer__user=request.user,
    ).select_related(
        "listing",
        "buyer",
        "quotation",
    ).order_by("-created_at", "-pk")

    active_orders = Order.objects.filter(
        manufacturer__user=request.user,
    ).exclude(
        status__in=[
            Order.Status.COMPLETED,
            Order.Status.CANCELLED,
        ],
    ).select_related("buyer", "listing")

    milestones_ready_to_start = Milestone.objects.filter(
        order__manufacturer__user=request.user,
        order__status__in=[
            Order.Status.FUNDED,
            Order.Status.IN_PRODUCTION,
            Order.Status.MILESTONE_PENDING,
        ],
        status__in=[
            Milestone.Status.PENDING,
            Milestone.Status.REJECTED,
        ],
        funding_status=Milestone.FundingStatus.FUNDED,
    ).select_related("order", "order__buyer", "order__listing")

    milestones_ready_to_submit = Milestone.objects.filter(
        order__manufacturer__user=request.user,
        order__status__in=[
            Order.Status.IN_PRODUCTION,
            Order.Status.FUNDED,
        ],
        status=Milestone.Status.IN_PROGRESS,
        funding_status=Milestone.FundingStatus.FUNDED,
    ).select_related("order", "order__buyer", "order__listing")

    quotations_waiting = Quotation.objects.filter(
        quote_request__listing__manufacturer__user=request.user,
        status=Quotation.Status.SENT,
    )

    stats = {
        "total_listings": listings.count(),
        "public_listings": listings.filter(
            is_active=True,
            manufacturer__is_verified=True,
        ).count(),
        "active_listings": listings.filter(
            is_active=True,
        ).count(),
        "pending_requests": quotes.filter(
            status=QuoteRequest.Status.PENDING,
        ).count(),
        "quotations_sent": Quotation.objects.filter(
            quote_request__listing__manufacturer__user=request.user,
        ).count(),
        "quotations_waiting": quotations_waiting.count(),
        "quotations_accepted": Quotation.objects.filter(
            quote_request__listing__manufacturer__user=request.user,
            status=Quotation.Status.ACCEPTED,
        ).count(),
        "unread_notifications": Notification.objects.filter(
            recipient=request.user,
            is_read=False,
        ).count(),
        "active_orders": active_orders.count(),
        "milestones_to_start": milestones_ready_to_start.count(),
        "milestones_to_submit": milestones_ready_to_submit.count(),
    }

    manufacturer = get_object_or_404(
        ManufacturerProfile,
        user=request.user,
    )

    return render(
        request,
        "marketplace/manufacturer_dashboard.html",
        {
            "quotes": quotes,
            "stats": stats,
            "manufacturer": manufacturer,
            "active_orders": active_orders[:4],
            "milestones_ready_to_start": milestones_ready_to_start[:4],
            "milestones_ready_to_submit": milestones_ready_to_submit[:4],
            "recent_reviews": Review.objects.filter(
                manufacturer=manufacturer,
            ).select_related("order", "buyer")[:3],
        },
    )
@login_required
@require_POST
def update_quote_status(request, pk):
    if request.user.role != "MANUFACTURER":
        raise PermissionDenied(
            "Only manufacturers can update quote requests."
        )

    quote = get_object_or_404(
        QuoteRequest,
        pk=pk,
        listing__manufacturer__user=request.user,
    )

    new_status = request.POST.get("status")

    allowed_statuses = {
        QuoteRequest.Status.ACCEPTED,
        QuoteRequest.Status.REJECTED,
    }

    if new_status not in allowed_statuses:
        raise PermissionDenied("Invalid status.")

    QuoteRequest.objects.filter(
        pk=quote.pk,
        listing__manufacturer__user=request.user,
        status=QuoteRequest.Status.PENDING,
    ).update(status=new_status)

    return redirect("my_listings")
@login_required
def create_listing(request):
    if request.user.role != "MANUFACTURER":
        raise PermissionDenied(
            "Only manufacturers can create listings."
        )

    manufacturer = get_object_or_404(
        ManufacturerProfile,
        user=request.user,
    )

    if request.method == "POST":
        form = CapacityListingForm(request.POST, request.FILES)

        if form.is_valid():
            listing = form.save(commit=False)
            listing.manufacturer = manufacturer
            listing.is_active = True
            listing.save()

            if manufacturer.is_verified:
                messages.success(
                    request,
                    "Your listing was created and is now visible to buyers.",
                )
            else:
                messages.success(
                    request,
                    "Your listing was saved. It will become visible "
                    "to buyers after your business is verified.",
                )

            return redirect("manufacturer_dashboard")
    else:
        form = CapacityListingForm()

    return render(
        request,
        "marketplace/create_listing.html",
        {"form": form},
    )
@login_required
def my_listings(request):
    if request.user.role != "MANUFACTURER":
        raise PermissionDenied(
            "Only manufacturers can access this page."
        )

    listings = CapacityListing.objects.filter(
        manufacturer__user=request.user,
    ).select_related("manufacturer").order_by("-pk")

    return render(
        request,
        "marketplace/my_listings.html",
        {"listings": listings},
    )


@login_required
def edit_listing(request, pk):
    if request.user.role != "MANUFACTURER":
        raise PermissionDenied(
            "Only manufacturers can edit listings."
        )

    listing = get_object_or_404(
        CapacityListing,
        pk=pk,
        manufacturer__user=request.user,
    )

    if request.method == "POST":
        form = CapacityListingEditForm(
            request.POST,
            request.FILES,
            instance=listing,
        )

        if form.is_valid():
            form.save()
            messages.success(
                request,
                "Your listing was updated.",
            )
            return redirect("my_listings")
    else:
        form = CapacityListingEditForm(instance=listing)

    return render(
        request,
        "marketplace/edit_listing.html",
        {
            "form": form,
            "listing": listing,
        },
    )

@login_required
@require_http_methods(["GET", "POST"])
def send_quotation(request, pk):
    if request.user.role != "MANUFACTURER":
        raise PermissionDenied(
            "Only manufacturers can send quotations."
        )

    quote_request = get_object_or_404(
        QuoteRequest.objects.select_related("listing", "buyer"),
        pk=pk,
        listing__manufacturer__user=request.user,
    )

    if quote_request.status == QuoteRequest.Status.REJECTED:
        messages.error(
            request,
            "You cannot send a quotation for a rejected request.",
        )
        return redirect("manufacturer_dashboard")

    if Quotation.objects.filter(
        quote_request=quote_request,
    ).exists():
        messages.info(
            request,
            "A quotation has already been sent for this request.",
        )
        return redirect("manufacturer_dashboard")

    if request.method == "POST":
        form = QuotationForm(request.POST)

        if form.is_valid():
            with transaction.atomic():
                # Claim a pending or previously accepted request.
                # This also coordinates with the existing reject action.
                updated = QuoteRequest.objects.filter(
                    pk=quote_request.pk,
                    listing__manufacturer__user=request.user,
                    status__in=[
                        QuoteRequest.Status.PENDING,
                        QuoteRequest.Status.ACCEPTED,
                    ],
                ).update(status=QuoteRequest.Status.ACCEPTED)

                if not updated:
                    messages.error(
                        request,
                        "This request is no longer available for quotation.",
                    )
                    return redirect("manufacturer_dashboard")

                quotation, created = Quotation.objects.get_or_create(
                    quote_request=quote_request,
                    defaults={
                        "quantity": quote_request.quantity,
                        "price_per_unit": form.cleaned_data["price_per_unit"],
                        "production_days": form.cleaned_data["production_days"],
                        "message": form.cleaned_data["message"],
                    },
                )

                if created:
                    listing_title = concise_label(quote_request.listing.title)
                    Notification.objects.create(
                        recipient_id=quote_request.buyer_id,
                        message=(
                            f"Quotation received for {listing_title} "
                            f"request #{quote_request.pk}. Review and respond."
                        ),
                        destination=(
                            Notification.Destination.BUYER_REQUESTS
                        ),
                    )

            if created:
                messages.success(
                    request,
                    "Your quotation was sent to the buyer.",
                )
            else:
                messages.info(
                    request,
                    "A quotation has already been sent for this request.",
                )

            return redirect("manufacturer_dashboard")
    else:
        form = QuotationForm()

    return render(
        request,
        "marketplace/send_quotation.html",
        {
            "form": form,
            "quote_request": quote_request,
        },
    )
@login_required
@require_POST
def respond_to_quotation(request, pk):
    if request.user.role != "BUYER":
        raise PermissionDenied(
            "Only buyers can respond to quotations."
        )

    quotation = get_object_or_404(
        Quotation.objects.select_related(
            "quote_request__listing__manufacturer",
        ),
        pk=pk,
        quote_request__buyer=request.user,
    )

    new_status = request.POST.get("status")

    allowed_statuses = {
        Quotation.Status.ACCEPTED,
        Quotation.Status.DECLINED,
    }

    if new_status not in allowed_statuses:
        raise PermissionDenied("Invalid quotation response.")

    with transaction.atomic():
        updated = Quotation.objects.filter(
            pk=quotation.pk,
            quote_request__buyer=request.user,
            status=Quotation.Status.SENT,
        ).update(
            status=new_status,
            responded_at=timezone.now(),
        )

        if updated:
            order = None
            order_created = False

            if new_status == Quotation.Status.ACCEPTED:
                quotation.status = Quotation.Status.ACCEPTED
                quotation.responded_at = timezone.now()
                order, order_created = create_order_from_quotation(quotation)

            listing_title = concise_label(quotation.quote_request.listing.title)
            manufacturer_user = quotation.quote_request.listing.manufacturer.user

            if new_status == Quotation.Status.ACCEPTED:
                response_message = (
                    f"Your quotation for {listing_title} was accepted. "
                    "Open the order to review next steps."
                )
            else:
                response_message = (
                    f"Your quotation for {listing_title} was declined by the buyer."
                )

            if order is not None:
                create_order_notification(
                    manufacturer_user,
                    response_message,
                    order,
                )
            else:
                Notification.objects.create(
                    recipient=manufacturer_user,
                    message=response_message,
                    destination=(
                        Notification.Destination.MANUFACTURER_DASHBOARD
                    ),
                )

            if order_created:
                create_order_notification(
                    request.user,
                    message=(
                        f"Order #{order.pk} was created from your accepted "
                        f"quotation for {listing_title}. Confirm demo milestone "
                        "funding to start production."
                    ),
                    order=order,
                )

    if updated:
        if new_status == Quotation.Status.ACCEPTED:
            messages.success(
                request,
                "You accepted the quotation. A demo order was created. "
                "No real payment or escrow has been started.",
            )
        else:
            messages.success(
                request,
                "You declined the quotation.",
            )
    else:
        messages.info(
            request,
            "This quotation has already been answered.",
        )

    return redirect("my_quote_requests")

@login_required
def saved_listings(request):
    if request.user.role != "BUYER":
        raise PermissionDenied(
            "Only buyers can view saved listings."
        )

    saved_items = SavedListing.objects.filter(
        buyer=request.user,
    ).select_related(
        "listing",
        "listing__manufacturer",
    ).order_by("-created_at", "-pk")

    return render(
        request,
        "marketplace/saved_listings.html",
        {"saved_items": saved_items},
    )


@login_required
@require_POST
def save_listing(request, pk):
    if request.user.role != "BUYER":
        raise PermissionDenied(
            "Only buyers can save listings."
        )

    listing = get_object_or_404(
        CapacityListing,
        pk=pk,
        is_active=True,
        manufacturer__is_verified=True,
    )

    saved_item, created = SavedListing.objects.get_or_create(
        buyer=request.user,
        listing=listing,
    )

    if created:
        messages.success(request, "Listing saved.")
    else:
        messages.info(request, "This listing is already saved.")

    return redirect("listing_detail", pk=listing.pk)


@login_required
@require_POST
def remove_saved_listing(request, pk):
    if request.user.role != "BUYER":
        raise PermissionDenied(
            "Only buyers can manage saved listings."
        )

    SavedListing.objects.filter(
        buyer=request.user,
        listing_id=pk,
    ).delete()

    messages.success(request, "Listing removed from your saved list.")
    return redirect("saved_listings")
def manufacturer_profile(request, pk):
    manufacturer = get_object_or_404(
        ManufacturerProfile,
        pk=pk,
        is_verified=True,
    )

    listings = CapacityListing.objects.filter(
        manufacturer=manufacturer,
        is_active=True,
    ).order_by("-pk")

    paginator = Paginator(listings, 9)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "marketplace/manufacturer_profile.html",
        {
            "manufacturer": manufacturer,
            "page_obj": page_obj,
        },
    )
@login_required
def edit_business_profile(request):
    if request.user.role != "MANUFACTURER":
        raise PermissionDenied(
            "Only manufacturers can edit a business profile."
        )

    manufacturer = get_object_or_404(
        ManufacturerProfile,
        user=request.user,
    )

    if request.method == "POST":
        form = ManufacturerProfileForm(
            request.POST,
            instance=manufacturer,
        )

        if form.is_valid():
            verification_fields = {
                "business_name",
                "city",
                "state",
            }

            needs_review = bool(
                verification_fields.intersection(form.changed_data)
            )

            profile = form.save(commit=False)

            if needs_review:
                profile.is_verified = False
                profile.kyc_status = ManufacturerProfile.KycStatus.UNDER_REVIEW

            profile.save()

            if needs_review:
                messages.success(
                    request,
                    "Business details updated. Your listings are hidden "
                    "until an administrator verifies the updated profile.",
                )
            else:
                messages.success(
                    request,
                    "Your business profile was updated.",
                )

            return redirect("edit_business_profile")
    else:
        form = ManufacturerProfileForm(instance=manufacturer)

    return render(
        request,
        "marketplace/edit_business_profile.html",
        {
            "form": form,
            "manufacturer": manufacturer,
        },
    )
@login_required
def notifications(request):
    items = Notification.objects.filter(
        recipient=request.user,
    )

    paginator = Paginator(items, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "marketplace/notifications.html",
        {"page_obj": page_obj},
    )


@login_required
@require_POST
def open_notification(request, pk):
    notification = get_object_or_404(
        Notification,
        pk=pk,
        recipient=request.user,
    )

    Notification.objects.filter(
        pk=notification.pk,
        recipient=request.user,
        is_read=False,
    ).update(is_read=True)

    if (
        notification.destination == Notification.Destination.ORDER_DETAIL
        and notification.order_id
    ):
        if order_queryset_for_user(request.user).filter(
            pk=notification.order_id,
        ).exists():
            return redirect("order_detail", pk=notification.order_id)

        messages.error(
            request,
            "That order is no longer available to your account.",
        )
        return redirect("notifications")

    destinations = {
        Notification.Destination.BUYER_REQUESTS:
            "my_quote_requests",
        Notification.Destination.BUYER_DASHBOARD:
            "buyer_dashboard",
        Notification.Destination.MANUFACTURER_DASHBOARD:
            "manufacturer_dashboard",
    }

    destination = destinations.get(
        notification.destination,
        "notifications",
    )

    return redirect(destination)
@login_required
@require_POST
def mark_all_notifications_read(request):
    updated = Notification.objects.filter(
        recipient=request.user,
        is_read=False,
    ).update(is_read=True)

    if updated:
        messages.success(
            request,
            "All your notifications are marked as read.",
        )
    else:
        messages.info(
            request,
            "You have no unread notifications.",
        )

    return redirect("notifications")
