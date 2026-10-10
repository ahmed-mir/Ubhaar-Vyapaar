from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.core.paginator import Paginator
from django.db import transaction
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from decimal import Decimal, InvalidOperation

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
from django.db.models import Q
from django.views.decorators.http import require_POST


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


def notify_order_status_change(order, previous_status):
    if previous_status == order.status:
        return

    status_label = order.get_status_display()
    message = f"Order #{order.pk} status changed to {status_label}."

    create_order_notification(order.buyer, message, order)
    create_order_notification(order.manufacturer.user, message, order)


def refresh_order_status(order):
    previous_status = order.status
    milestones = list(order.milestones.all())

    if not milestones:
        return previous_status, order.status

    if all(
        milestone.status == Milestone.Status.APPROVED
        for milestone in milestones
    ):
        order.status = Order.Status.COMPLETED
    elif any(
        milestone.status == Milestone.Status.COMPLETED
        for milestone in milestones
    ):
        order.status = Order.Status.MILESTONE_PENDING
    elif any(
        milestone.status == Milestone.Status.REJECTED
        for milestone in milestones
    ):
        order.status = Order.Status.IN_PRODUCTION
    else:
        order.status = Order.Status.IN_PRODUCTION

    if previous_status != order.status:
        order.save(update_fields=["status", "updated_at"])

    return previous_status, order.status

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

    listings = CapacityListing.objects.filter(
        is_active=True,
        manufacturer__is_verified=True,
    ).select_related("manufacturer")

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

    if sort == "price":
        listings = listings.order_by("price_per_unit", "-pk")
    elif sort == "lead_time":
        listings = listings.order_by("production_days", "-pk")
    else:
        listings = listings.order_by("-pk")

    paginator = Paginator(listings, 9)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "marketplace/home.html",
        {
            "listings": page_obj,
            "page_obj": page_obj,
            "query": query,
            "categories": CapacityListing.Category.choices,
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
        pk=pk,
        is_active=True,
        manufacturer__is_verified=True,
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
        pk=pk,
        is_active=True,
        manufacturer__is_verified=True,
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
                        f"New quote request #{quote.pk}: "
                        f"{quote.quantity} units requested."
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

    return render(
        request,
        "marketplace/order_detail.html",
        {
            "order": order,
            "message_form": OrderMessageForm(),
            "review_form": ReviewForm(),
        },
    )


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
                f"New message on order #{order.pk}.",
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
                f"The buyer reviewed order #{order.pk}.",
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

    if milestone.status in {
        Milestone.Status.PENDING,
        Milestone.Status.REJECTED,
    }:
        milestone.status = Milestone.Status.COMPLETED
        milestone.completed_at = timezone.now()
        milestone.save(update_fields=["status", "completed_at", "updated_at"])
        previous_order_status, _ = refresh_order_status(milestone.order)

        create_order_notification(
            milestone.order.buyer,
            message=(
                f"Milestone '{milestone.title}' is ready for review "
                f"on order #{milestone.order_id}."
            ),
            order=milestone.order,
        )
        notify_order_status_change(milestone.order, previous_order_status)

        messages.success(
            request,
            "Milestone marked complete for buyer review.",
        )
    else:
        messages.info(request, "This milestone cannot be marked complete.")

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

    milestone.save(
        update_fields=[
            "status",
            "buyer_feedback",
            "approved_at",
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

    create_order_notification(
        milestone.order.manufacturer.user,
        message=(
            f"The buyer {response_label} milestone "
            f"'{milestone.title}' on order #{milestone.order_id}."
        ),
        order=milestone.order,
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

    messages.success(request, "Milestone response saved.")
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
        "quotations_accepted": Quotation.objects.filter(
            quote_request__listing__manufacturer__user=request.user,
            status=Quotation.Status.ACCEPTED,
        ).count(),
        "unread_notifications": Notification.objects.filter(
            recipient=request.user,
            is_read=False,
        ).count(),
        "active_orders": Order.objects.filter(
            manufacturer__user=request.user,
        ).exclude(
            status__in=[
                Order.Status.COMPLETED,
                Order.Status.CANCELLED,
            ],
        ).count(),
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
                    Notification.objects.create(
                        recipient_id=quote_request.buyer_id,
                        message=(
                            f"A manufacturer sent a quotation for "
                            f"your request #{quote_request.pk}."
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
            response_label = (
                "accepted"
                if new_status == Quotation.Status.ACCEPTED
                else "declined"
            )

            order = None
            order_created = False

            if new_status == Quotation.Status.ACCEPTED:
                quotation.status = Quotation.Status.ACCEPTED
                quotation.responded_at = timezone.now()
                order, order_created = create_order_from_quotation(quotation)

            manufacturer_user = quotation.quote_request.listing.manufacturer.user
            response_message = (
                f"The buyer {response_label} your quotation "
                f"for request #{quotation.quote_request_id}."
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
                        f"Order #{order.pk} was created from your "
                        f"accepted quotation."
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
        return redirect("order_detail", pk=notification.order_id)

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
