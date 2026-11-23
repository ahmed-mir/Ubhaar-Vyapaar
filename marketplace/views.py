import logging
import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import EmailMessage
from django.db import DatabaseError, connection, transaction
from django.core.validators import validate_email
from django.core.paginator import Paginator
from django.db.models import Case, Count, IntegerField, Prefetch, Q, When
from django.db import IntegrityError, transaction
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode, urljoin
from xml.sax.saxutils import escape

from django.conf import settings
from django.http import Http404, HttpResponse, HttpResponsePermanentRedirect, JsonResponse
from django.urls import reverse
from django.templatetags.static import static
from urllib.parse import urlencode, urljoin

from accounts.privacy import lock_active_workflow_accounts

from .forms import (
    CapacityListingEditForm,
    CapacityListingForm,
    BuyNowForm,
    ContactSubmissionForm,
    WaitlistEntryForm,
    OrderMessageForm,
    QuoteRequestForm,
    QuotationForm,
    ManufacturerProfileForm,
    ReviewForm,
)
from .upload_security import LISTING_IMAGE_TOO_LARGE_MESSAGE
from .idempotency import (
    BUY_NOW_ACTION,
    REQUEST_QUOTE_ACTION,
    issue_workflow_action_token,
    workflow_action_digest,
)
from .models import (
    CapacityListing,
    ContactSubmission,
    ManufacturerProfile,
    Milestone,
    Notification,
    Order,
    PaymentTransaction,
    PaymentWebhookEvent,
    QuoteRequest,
    Quotation,
    Review,
    SavedListing,
    WaitlistEntry,
)
from .locations import canonical_india_state_ut_name
from .payments import (
    amount_to_paise,
    checkout_signature_is_valid,
    get_razorpay_client,
    razorpay_test_mode_enabled,
    webhook_signature_is_valid,
)

logger = logging.getLogger(__name__)


class _InactiveWorkflowParticipants(Exception):
    """Raised when an account closes before new work can be committed."""

CONTACT_SUBMISSION_WINDOW_SECONDS = 60 * 60
CONTACT_SUBMISSION_LIMIT = 5
CONTACT_SUBMISSION_SESSION_KEY = "contact_submission_times"
WAITLIST_SUBMISSION_WINDOW_SECONDS = 60 * 60
WAITLIST_SUBMISSION_LIMIT = 5
WAITLIST_SUBMISSION_SESSION_KEY = "waitlist_submission_times"


def _absolute_site_url(path="/"):
    return urljoin(f"{settings.SITE_ORIGIN}/", path)


def _is_real_configured_email(value):
    email = (value or "").strip()
    if not email:
        return False

    try:
        validate_email(email)
    except ValidationError:
        return False

    domain = email.rsplit("@", 1)[-1].lower()
    reserved_domains = {"example.com", "example.org", "example.net", "example"}
    return domain not in reserved_domains and not (
        domain.endswith(".example") or domain.endswith(".test")
    )


def _manufacturer_schema(manufacturer, display_name=None):
    profile_url = _absolute_site_url(
        reverse("manufacturer_profile", kwargs={"pk": manufacturer.pk})
    )
    organization = {
        "@type": "Organization",
        "name": display_name or manufacturer.business_name or "Manufacturer",
        "url": profile_url,
    }
    if manufacturer.description:
        organization["description"] = manufacturer.description
    return organization
def legal_page_context():
    legal_email = settings.LEGAL_CONTACT_EMAIL
    return {
        "legal_entity_name": (settings.LEGAL_ENTITY_NAME or "").strip(),
        "legal_contact_email": legal_email.strip() if _is_real_configured_email(legal_email) else "",
        "legal_contact_label": (
            settings.LEGAL_CONTACT_LABEL.strip()
            if _is_real_configured_email(legal_email) and settings.LEGAL_CONTACT_LABEL
            else ""
        ),
        "grievance_officer_name": (settings.GRIEVANCE_OFFICER_NAME or "").strip(),
        "grievance_contact_email": (
            settings.GRIEVANCE_CONTACT_EMAIL.strip()
            if _is_real_configured_email(settings.GRIEVANCE_CONTACT_EMAIL)
            else ""
        ),
        "manufacturer_required_documents": settings.MANUFACTURER_REQUIRED_DOCUMENTS,
        "manufacturer_review_time": (settings.MANUFACTURER_REVIEW_TIME or "").strip(),
        "terms_version": settings.TERMS_VERSION,
        "privacy_policy_version": settings.PRIVACY_POLICY_VERSION,
    }


PUBLIC_PAGE_CONTENTS = {
    "how_it_works": [
        ("buyers", "For buyers"),
        ("manufacturers", "For manufacturers"),
        ("orders-and-payments", "Orders and payment status"),
    ],
    "for_manufacturers": [
        ("who-its-for", "Who the marketplace is for"),
        ("listing-capacity", "Listing capacity"),
        ("quotes-and-orders", "Quotes and orders"),
        ("verification-status", "Verification status"),
    ],
    "trust_safety": [
        ("verified-means", "What Verified means"),
        ("verified-does-not-mean", "What Verified does not mean"),
        ("sample-data", "Sample data"),
        ("communication-and-reporting", "Communication and reporting"),
    ],
    "faq": [
        ("faq-marketplace", "Marketplace"),
        ("faq-buyers", "Buyers"),
        ("faq-manufacturers", "Manufacturers"),
        ("faq-quotations", "Quotations"),
        ("faq-orders", "Orders and milestones"),
        ("faq-verification", "Verification"),
        ("faq-payments", "Payments"),
        ("faq-accounts", "Accounts"),
    ],
    "privacy_policy": [
        ("information-we-collect", "Information collected"),
        ("how-information-is-used", "How information is used"),
        ("registration-consent", "Registration and consent"),
        ("cookies-and-storage", "Cookies and browser storage"),
        ("service-providers", "Service providers"),
        ("data-retention", "Data retention"),
        ("security", "Security"),
        ("user-rights", "User requests"),
        ("childrens-data", "Children's data"),
        ("policy-changes", "Policy version"),
    ],
    "terms": [
        ("terms-payments", "Payments"),
        ("accounts-and-roles", "Accounts and roles"),
        ("listings-quotes-orders", "Listings, quotations, and orders"),
        ("communication-reviews", "Communication and reviews"),
        ("prohibited-conduct", "Prohibited conduct"),
        ("user-content", "User content"),
        ("suspension-termination", "Suspension or termination"),
        ("availability-liability-disputes", "Availability and disputes"),
        ("terms-contact-version", "Contact and version"),
    ],
}


def public_page_context(page_name):
    return {"contents_items": PUBLIC_PAGE_CONTENTS.get(page_name, [])}


def privacy_policy(request):
    return render(
        request,
        "marketplace/privacy_policy.html",
        {**legal_page_context(), **public_page_context("privacy_policy")},
    )


def terms(request):
    return render(
        request,
        "marketplace/terms.html",
        {**legal_page_context(), **public_page_context("terms")},
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


def health(request):
    return JsonResponse({"status": "ok"})


_readiness_failure_logged = False


def _check_readiness_database():
    with transaction.atomic():
        with connection.cursor() as cursor:
            if connection.vendor == "postgresql":
                # Scope the readiness query timeout to this transaction.
                cursor.execute("SET LOCAL statement_timeout = '3000ms'")
            cursor.execute("SELECT 1")
            cursor.fetchone()


def ready(request):
    """Check the primary database without exposing connection details."""
    global _readiness_failure_logged

    try:
        _check_readiness_database()
    except DatabaseError as exc:
        if not _readiness_failure_logged:
            logger.warning(
                "Database readiness check failed (%s).",
                type(exc).__name__,
            )
            _readiness_failure_logged = True
        response = JsonResponse({"status": "not_ready"}, status=503)
        # Django's request logger otherwise emits an ERROR for every health
        # poll. The generic incident warning above is logged once per outage.
        response._has_been_logged = True
        return response

    _readiness_failure_logged = False
    return JsonResponse({"status": "ready"})


def about(request):
    return render(request, "marketplace/about.html")


def how_it_works(request):
    return render(request, "marketplace/how_it_works.html", public_page_context("how_it_works"))


def for_manufacturers(request):
    context = public_page_context("for_manufacturers")
    context.update(legal_page_context())
    return render(request, "marketplace/for_manufacturers.html", context)


@require_http_methods(["GET", "POST"])
def contact(request):
    if request.method == "POST":
        form = ContactSubmissionForm(request.POST)

        if (request.POST.get("company_website") or "").strip():
            messages.success(
                request,
                "Thanks for contacting Ubhaar-Vyapaar. Your message has been received.",
            )
            return redirect("contact")

        if form.is_valid():
            if _contact_submission_rate_limited(request):
                form.add_error(
                    None,
                    "Please try again later before sending another message.",
                )
                return render(
                    request,
                    "marketplace/contact.html",
                    {**legal_page_context(), "form": form},
                    status=429,
                )

            submission = form.save()
            _record_contact_submission(request)
            recipient = legal_page_context()["legal_contact_email"]
            if recipient:
                _send_contact_notification(submission, recipient)

            messages.success(
                request,
                "Thanks for contacting Ubhaar-Vyapaar. Your message has been received.",
            )
            return redirect("contact")
    else:
        initial = {}
        if request.user.is_authenticated:
            initial["name"] = (
                request.user.get_full_name().strip()
                or request.user.get_username()
            )
            initial["email"] = request.user.email
        form = ContactSubmissionForm(initial=initial)

    return render(
        request,
        "marketplace/contact.html",
        {**legal_page_context(), "form": form},
    )


def _contact_submission_rate_limited(request):
    now = int(timezone.now().timestamp())
    recent = [
        timestamp
        for timestamp in request.session.get(CONTACT_SUBMISSION_SESSION_KEY, [])
        if isinstance(timestamp, int)
        and 0 <= now - timestamp < CONTACT_SUBMISSION_WINDOW_SECONDS
    ]
    request.session[CONTACT_SUBMISSION_SESSION_KEY] = recent
    return len(recent) >= CONTACT_SUBMISSION_LIMIT


def _record_contact_submission(request):
    now = int(timezone.now().timestamp())
    timestamps = request.session.get(CONTACT_SUBMISSION_SESSION_KEY, [])
    recent = [
        timestamp
        for timestamp in timestamps
        if isinstance(timestamp, int)
        and 0 <= now - timestamp < CONTACT_SUBMISSION_WINDOW_SECONDS
    ]
    recent.append(now)
    request.session[CONTACT_SUBMISSION_SESSION_KEY] = recent


def _waitlist_submission_rate_limited(request):
    now = int(timezone.now().timestamp())
    recent = [
        timestamp
        for timestamp in request.session.get(WAITLIST_SUBMISSION_SESSION_KEY, [])
        if isinstance(timestamp, int)
        and 0 <= now - timestamp < WAITLIST_SUBMISSION_WINDOW_SECONDS
    ]
    request.session[WAITLIST_SUBMISSION_SESSION_KEY] = recent
    return len(recent) >= WAITLIST_SUBMISSION_LIMIT


def _record_waitlist_submission(request):
    now = int(timezone.now().timestamp())
    timestamps = request.session.get(WAITLIST_SUBMISSION_SESSION_KEY, [])
    recent = [
        timestamp
        for timestamp in timestamps
        if isinstance(timestamp, int)
        and 0 <= now - timestamp < WAITLIST_SUBMISSION_WINDOW_SECONDS
    ]
    recent.append(now)
    request.session[WAITLIST_SUBMISSION_SESSION_KEY] = recent


def _send_contact_notification(submission, recipient):
    try:
        admin_path = reverse(
            "admin:marketplace_contactsubmission_change",
            args=(submission.pk,),
        )
        admin_url = _absolute_site_url(admin_path)
        submitted_at = timezone.localtime(submission.created_at).isoformat(
            timespec="seconds"
        )
        body = (
            f"Name: {submission.name}\n"
            f"Email: {submission.email}\n"
            f"Role: {submission.get_role_display()}\n"
            f"Submitted: {submitted_at}\n\n"
            f"Message:\n{submission.message}\n\n"
            f"Admin record: {admin_url}\n"
        )
        email = EmailMessage(
            subject=f"Website contact enquiry #{submission.pk}",
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient],
            reply_to=[submission.email],
        )
        if email.send(fail_silently=False) != 1:
            logger.error(
                "Contact notification was not accepted by the email backend "
                "for submission id=%s.",
                submission.pk,
            )
    except Exception:
        logger.exception(
            "Contact notification delivery failed for submission id=%s.",
            submission.pk,
        )
        if settings.SENTRY_ENABLED:
            try:
                import sentry_sdk

                sentry_sdk.capture_exception()
            except Exception:
                logger.exception(
                    "Could not report contact notification failure to Sentry "
                    "for submission id=%s.",
                    submission.pk,
                )


def pricing_fees(request):
    return render(request, "marketplace/pricing_fees.html")


def trust_safety(request):
    context = public_page_context("trust_safety")
    if not legal_page_context()["legal_contact_email"]:
        context["contents_items"] = [
            item for item in context["contents_items"]
            if item[0] != "communication-and-reporting"
        ]
    context.update(legal_page_context())
    return render(request, "marketplace/trust_safety.html", context)


def faq(request):
    faq_groups = [
        {
            "id": "faq-getting-started",
            "title": "Getting started",
            "items": [
                {"question": "What is Ubhaar-Vyapaar?", "answer": "Ubhaar-Vyapaar is a B2B marketplace where Buyers can discover manufacturing capacity and Manufacturers can describe available capacity."},
                {"question": "How do I find manufacturing capacity?", "answer": "Browse active listings or search and filter by the details available in the marketplace."},
                {"question": "What are Sample listings?", "answer": "Sample listings demonstrate the marketplace. They are clearly labeled, cannot be purchased or quoted, and may be saved as Samples."},
                {"question": "Can a manufacturer pause a listing?", "answer": "Yes. Paused listings may remain visible, are labeled as paused, and are not prioritized in default discovery."},
            ],
        },
        {
            "id": "faq-buyer-routes",
            "title": "Buyer purchase paths",
            "items": [
                {"question": "How do Buyers purchase?", "answer": "Buy Now is available on eligible fixed-price listings. For custom quantities or terms, submit a Request Quote, review the Manufacturer's quotation, and accept it to create an order."},
                {"question": "What is Buy Now?", "answer": "Buy Now lets a Buyer confirm the displayed fixed-price terms on an eligible listing and create an order directly. It is not available on every listing."},
                {"question": "What is Request Quote?", "answer": "Request Quote sends a Buyer's quantity, requirements, and delivery location to a Manufacturer, who can respond with a quotation."},
            ],
        },
        {
            "id": "faq-quotations",
            "title": "Quote requests",
            "items": [
                {"question": "How do I request a quotation?", "answer": "Open an eligible listing and select Request Quote. Provide the requested quantity, requirements, and delivery location."},
                {"question": "What can a manufacturer manage?", "answer": "A Manufacturer account can create and edit capacity listings, respond to Buyer quote requests with quotations, and manage orders from accepted quotations or eligible direct purchases, including milestones."},
            ],
        },
        {
            "id": "faq-orders",
            "title": "Orders and milestones",
            "items": [
                {"question": "What happens when a buyer accepts or declines a quotation?", "answer": "The Buyer may accept or decline. Accepting creates an order with the accepted terms, messages, and production milestones; declining does not create an order."},
                {"question": "How do order messages, milestones, and reviews work?", "answer": "Order participants can exchange messages and update production milestones. A buyer can leave a review after an order is completed, subject to the existing review rules."},
            ],
        },
        {
            "id": "faq-verification-payments",
            "title": "Verification and payments",
            "items": [
                {"question": "What does Verified mean?", "answer": "The Verified badge appears only on eligible non-Sample manufacturer profiles when the profile's existing verification flag is approved. KYC status by itself does not display the badge. This status is not a product or transaction guarantee."},
                {"question": "Are payments real?", "pilot_payment_notice": True},
                {"question": "Is Ubhaar-Vyapaar currently using escrow?", "answer": "No. The platform does not provide live escrow, settlement, or Manufacturer payout. Milestone release remains simulated."},
                {"question": "Does the platform collect a fee?", "answer": "The current application does not calculate or collect platform fees. Any listing or quotation prices are part of the Buyer–Manufacturer commercial discussion."},
                {"question": "How can I contact support?", "answer": "Use the Contact page for platform questions or concerns."},
            ],
        },
    ]
    context = public_page_context("faq")
    context["faq_groups"] = faq_groups
    return render(request, "marketplace/faq.html", context)


def grievance_redressal(request):
    return render(request, "marketplace/grievance_redressal.html", legal_page_context())


def help_page(request):
    return render(request, "marketplace/help.html", legal_page_context())


def absolute_url(request, path):
    return urljoin(
        f"{settings.SITE_ORIGIN}/",
        path.lstrip("/"),
    )


def sitemap_xml(request):
    public_urls = [
        (absolute_url(request, reverse("home")), "daily", "0.9"),
        (absolute_url(request, reverse("marketplace")), "daily", "0.9"),
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
        & Q(
            availability_status__in=[
                CapacityListing.AvailabilityStatus.AVAILABLE,
                CapacityListing.AvailabilityStatus.LIMITED,
            ]
        )
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
    ).exclude(
        user__username__startswith="demo_mfr_",
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
    private_paths = [
        "/admin/",
        "/accounts/password/change/",
        "/accounts/password/change/done/",
        "/buyer/",
        "/manufacturer/dashboard/",
        "/manufacturer/orders/",
        "/manufacturer/listings/",
        "/my-quote-requests/",
        "/saved-listings/",
        "/orders/",
        "/milestones/",
        "/notifications/",
    ]

    if not settings.ALLOW_INDEXING:
        lines = [
            "User-agent: *",
            "Disallow: /",
            "",
            "User-agent: OAI-SearchBot",
            "Disallow: /",
            "",
            "User-agent: GPTBot",
            "Disallow: /",
        ]
    else:
        lines = [
            "User-agent: OAI-SearchBot",
            *[f"Disallow: {path}" for path in private_paths],
            "Allow: /",
            "",
            "User-agent: GPTBot",
            *(
                ["Disallow: /"]
                if not settings.ALLOW_GPTBOT
                else [
                    *[f"Disallow: {path}" for path in private_paths],
                    "Allow: /",
                ]
            ),
            "",
            "User-agent: *",
            *[f"Disallow: {path}" for path in private_paths],
            "Allow: /",
        ]

    lines.extend(["", f"Sitemap: {sitemap_url}"])

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
            "source": Order.Source.QUOTATION,
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


def _lock_order_and_milestone(milestone_pk, *, buyer=None, manufacturer_user=None):
    """Lock a milestone's parent Order first, then the milestone row.

    Call only inside ``transaction.atomic()``. Reapply ownership filters after
    acquiring the parent lock so the mutation uses an authorized, current row.
    """
    scoped_milestones = Milestone.objects.filter(pk=milestone_pk)
    if buyer is not None:
        scoped_milestones = scoped_milestones.filter(order__buyer=buyer)
    if manufacturer_user is not None:
        scoped_milestones = scoped_milestones.filter(
            order__manufacturer__user=manufacturer_user,
        )

    order_id = scoped_milestones.values_list("order_id", flat=True).first()
    if order_id is None:
        raise Http404("Milestone not found.")

    order = get_object_or_404(Order.objects.select_for_update(), pk=order_id)

    if buyer is not None and order.buyer_id != buyer.pk:
        raise Http404("Milestone not found.")
    if manufacturer_user is not None and not ManufacturerProfile.objects.filter(
        pk=order.manufacturer_id,
        user_id=manufacturer_user.pk,
    ).exists():
        raise Http404("Milestone not found.")

    milestone = get_object_or_404(
        Milestone.objects.select_for_update(),
        pk=milestone_pk,
        order_id=order.pk,
    )
    return order, milestone


def refresh_order_status(order):
    """Recalculate status from fresh rows while the caller holds Order's lock."""
    previous_status = Order.objects.values_list("status", flat=True).get(
        pk=order.pk,
    )
    milestones = list(
        Milestone.objects.filter(order_id=order.pk).values_list(
            "status",
            "funding_status",
        )
    )

    if not milestones:
        order.status = previous_status
        return previous_status, order.status

    if all(
        status == Milestone.Status.APPROVED
        and funding_status == Milestone.FundingStatus.RELEASED
        for status, funding_status in milestones
    ):
        order.status = Order.Status.COMPLETED
    elif any(status == Milestone.Status.COMPLETED for status, _ in milestones):
        order.status = Order.Status.MILESTONE_PENDING
    elif any(
        status in {
            Milestone.Status.IN_PROGRESS,
            Milestone.Status.APPROVED,
            Milestone.Status.REJECTED,
        }
        for status, _ in milestones
    ):
        order.status = Order.Status.IN_PRODUCTION
    elif any(
        funding_status in {
            Milestone.FundingStatus.FUNDED,
            Milestone.FundingStatus.RELEASED,
        }
        for _, funding_status in milestones
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
    milestone.payment_enabled = _order_uses_razorpay_test_mode(milestone.order)
    milestone.has_captured_test_payment = milestone.payment_transactions.filter(
        status=PaymentTransaction.Status.CAPTURED
    ).exists()
    milestone.funding_status_label = milestone.get_funding_status_display()
    if milestone.payment_enabled:
        if milestone.funding_status == Milestone.FundingStatus.NOT_FUNDED:
            milestone.funding_status_label = "Payment due · Test Mode"
        elif milestone.has_captured_test_payment:
            milestone.funding_status_label = "Test payment recorded"
        elif milestone.funding_status == Milestone.FundingStatus.RELEASED:
            milestone.funding_status_label = "Release simulated"

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
            milestone.workflow_hint = (
                "Awaiting Buyer payment in Razorpay Test Mode."
                if milestone.payment_enabled
                else "Awaiting buyer demo funding."
            )
        else:
            milestone.workflow_hint = (
                "Payment recorded. Milestone ready to start."
                if milestone.has_captured_test_payment and user.role == "MANUFACTURER"
                else "Ready for manufacturer to start."
            )
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
                if milestone.payment_enabled:
                    return {
                        "title": f"Pay {milestone.title} (Test Mode)",
                        "body": "Razorpay Test Mode records a test payment only. Manufacturer payout remains simulated.",
                        "url_name": "fund_milestone",
                        "url_arg": milestone.pk,
                        "button": "Pay milestone",
                    }
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

    if order.quotation_id:
        origin_step = {
            "title": "Quotation accepted",
            "body": "Buyer accepted the quotation.",
            "complete": order.quotation.status == Quotation.Status.ACCEPTED,
            "date": order.quotation.responded_at,
        }
    else:
        origin_step = {
            "title": "Direct purchase confirmed",
            "body": "Buyer confirmed the listing's fixed-price terms.",
            "complete": True,
            "date": order.terms_locked_at,
        }

    return [
        origin_step,
        {
            "title": "Order created",
            "body": "Commercial terms were locked into the order.",
            "complete": True,
            "date": order.created_at,
        },
        {
            "title": "Milestones",
            "body": "Production checkpoints were created for this order.",
            "complete": has_milestones,
        },
        {
            "title": (
                "Milestone payments"
                if _order_uses_razorpay_test_mode(order)
                else "Demo funding"
            ),
            "body": (
                "Test payments are not live. Manufacturer payout and release remain simulated."
                if _order_uses_razorpay_test_mode(order)
                else "All milestone funding is simulated; no real money is held."
            ),
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

MARKETPLACE_QUERY_PARAMS = {
    "q", "category", "location", "moq", "max_price", "lead_time",
    "verification", "sort", "page",
}

LANDING_FAQ_ITEMS = [
    {
        "question": "What is Ubhaar-Vyapaar?",
        "answer": "A B2B marketplace for discovering manufacturing capacity and starting a Buyer–Manufacturer commercial conversation.",
    },
    {
        "question": "What does Verified mean?",
        "answer": "The Verified badge appears only for non-sample manufacturer accounts whose verification flag is approved. A KYC status by itself does not display the badge.",
    },
    {
        "question": "Can a listing be paused?",
        "answer": "Yes. Paused listings remain available to their owner for management but are not prioritised in default discovery.",
    },
    {
        "question": "What is Buy Now?",
        "answer": "Buy Now confirms displayed fixed-price terms on eligible listings. Other listings may support Request Quote for custom terms.",
    },
    {
        "question": "What is Request Quote?",
        "answer": "Send your quantity, requirements, and delivery location to the Manufacturer. Accepting the Manufacturer's quotation creates an order.",
    },
    {
        "question": "Are Sample listings transactional?",
        "answer": "No. Sample listings are for illustration and cannot be purchased or quoted. Buyers may save them while keeping their Sample label.",
    },
]


def home(request):
    if MARKETPLACE_QUERY_PARAMS.intersection(request.GET):
        query_string = request.META.get("QUERY_STRING", "")
        destination = "/marketplace/"
        if query_string:
            destination = f"{destination}?{query_string}"
        return HttpResponsePermanentRedirect(destination)

    waitlist_form = WaitlistEntryForm()
    home_status = 200
    if request.method == "POST":
        waitlist_form = WaitlistEntryForm(request.POST)
        success_url = f"{reverse('home')}#early-access"

        if (request.POST.get("website") or "").strip():
            messages.success(
                request,
                "Thanks — your interest has been recorded. We’ll use your email for the pilot updates you requested.",
            )
            return redirect(success_url)

        if waitlist_form.is_valid():
            if _waitlist_submission_rate_limited(request):
                waitlist_form.add_error(
                    None,
                    "Please try again later before submitting another request.",
                )
                home_status = 429
            else:
                email = waitlist_form.cleaned_data["email"]
                role = waitlist_form.cleaned_data["role"]
                if not WaitlistEntry.objects.filter(
                    email__iexact=email, role=role
                ).exists():
                    try:
                        with transaction.atomic():
                            waitlist_form.save()
                    except IntegrityError:
                        # A case-insensitive unique constraint also covers races.
                        if not WaitlistEntry.objects.filter(
                            email__iexact=email, role=role
                        ).exists():
                            raise
                _record_waitlist_submission(request)
                messages.success(
                    request,
                    "Thanks — your interest has been recorded. We’ll use your email for the pilot updates you requested.",
                )
                return redirect(success_url)

    site_url = _absolute_site_url()
    organization_schema = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": "Ubhaar-Vyapaar",
        "url": site_url,
        "logo": _absolute_site_url(static("marketplace/images/brand/logo-mark.svg")),
    }
    if _is_real_configured_email(settings.LEGAL_CONTACT_EMAIL):
        organization_schema["email"] = settings.LEGAL_CONTACT_EMAIL.strip()

    website_schema = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": "Ubhaar-Vyapaar",
        "alternateName": "Ubhaar Vyapaar",
        "url": site_url,
    }

    discovery_listings = CapacityListing.objects.filter(
        is_active=True,
        availability_status__in=[
            CapacityListing.AvailabilityStatus.AVAILABLE,
            CapacityListing.AvailabilityStatus.LIMITED,
        ],
    ).filter(
        Q(manufacturer__is_verified=True)
        | Q(manufacturer__user__username__startswith="demo_mfr_"),
    )
    category_counts = {
        item["category"]: item["total"]
        for item in discovery_listings.values("category").annotate(total=Count("pk"))
    }
    categories = [
        {"value": value, "label": label, "count": category_counts.get(value, 0)}
        for value, label in CapacityListing.Category.choices
        if category_counts.get(value, 0)
    ]
    featured_listings = list(
        CapacityListing.objects.filter(
            is_featured=True,
            is_active=True,
            availability_status__in=[
                CapacityListing.AvailabilityStatus.AVAILABLE,
                CapacityListing.AvailabilityStatus.LIMITED,
            ],
            manufacturer__is_verified=True,
        )
        .exclude(manufacturer__user__username__startswith="demo_mfr_")
        .exclude(image="")
        .select_related("manufacturer")
        .order_by("-pk")[:6]
    )

    if request.user.is_authenticated and request.user.role == "MANUFACTURER":
        manufacturer_cta_url = reverse("create_listing")
    elif request.user.is_authenticated:
        manufacturer_cta_url = reverse("for_manufacturers")
    else:
        manufacturer_cta_url = reverse("register_manufacturer")

    return render(
        request,
        "marketplace/landing.html",
        {
            "canonical_url": site_url,
            "organization_schema": organization_schema,
            "website_schema": website_schema,
            "categories": categories,
            "featured_listings": featured_listings,
            "manufacturer_cta_url": manufacturer_cta_url,
            "faq_items": LANDING_FAQ_ITEMS,
            "waitlist_form": waitlist_form,
        },
        status=home_status,
    )


def marketplace(request):
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

    listings = public_listings.select_related("manufacturer", "manufacturer__user")

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

    if verification == "verified":
        listings = listings.filter(manufacturer__is_verified=True).exclude(
            manufacturer__user__username__startswith="demo_mfr_",
        )

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

    if not moq.isdigit():
        moq = ""

    if not lead_time.isdigit():
        lead_time = ""

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

    has_marketplace_filters = any(
        (query, selected_category, location, moq, max_price, lead_time, verification)
    ) or sort != "newest"
    has_active_filters = any(
        (query, selected_category, location, moq, max_price, lead_time, verification)
    )
    canonical_url = f"{settings.SITE_ORIGIN}{request.path}"
    if page_obj.number > 1 and not has_marketplace_filters:
        canonical_url = f"{canonical_url}?page={page_obj.number}"

    pagination_params = {
        key: value
        for key, value in {
            "q": query,
            "category": selected_category,
            "location": location,
            "moq": moq,
            "max_price": max_price,
            "lead_time": lead_time,
            "verification": verification,
            "sort": sort if sort != "newest" else "",
        }.items()
        if value
    }
    pagination_query = urlencode(pagination_params)

    clear_filter_params = {"sort": sort} if sort != "newest" else {}
    clear_filters_url = reverse("marketplace")
    if clear_filter_params:
        clear_filters_url = f"{clear_filters_url}?{urlencode(clear_filter_params)}"

    category_labels = dict(available_categories)
    active_filter_specs = [
        ("q", query, f'Search: {query}'),
        ("category", selected_category, f'Category: {category_labels.get(selected_category, selected_category)}'),
        ("location", location, f"Location: {canonical_india_state_ut_name(location)}"),
        ("moq", moq, f"MOQ ≤ {moq}"),
        ("max_price", max_price, f"Unit price ≤ ₹{max_price}"),
        ("lead_time", lead_time, f"Lead time ≤ {lead_time} days"),
        ("verification", verification, "Verified only" if verification else ""),
    ]
    active_filters = []
    for filter_name, filter_value, label in active_filter_specs:
        if not filter_value:
            continue
        remaining_params = {
            key: value
            for key, value in pagination_params.items()
            if key != filter_name
        }
        remove_url = reverse("marketplace")
        if remaining_params:
            remove_url = f"{remove_url}?{urlencode(remaining_params)}"
        active_filters.append({"label": label, "remove_url": remove_url})

    has_sample_listings = any(
        listing.manufacturer.is_demo for listing in page_obj.object_list
    )

    site_url = _absolute_site_url()
    organization_schema = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": "Ubhaar-Vyapaar",
        "url": site_url,
        "logo": _absolute_site_url(
            static("marketplace/images/brand/logo-mark.svg")
        ),
    }
    if _is_real_configured_email(settings.LEGAL_CONTACT_EMAIL):
        organization_schema["email"] = settings.LEGAL_CONTACT_EMAIL.strip()

    website_schema = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": "Ubhaar-Vyapaar",
        "alternateName": "Ubhaar Vyapaar",
        "url": site_url,
    }

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
            "has_marketplace_filters": has_marketplace_filters,
            "has_active_filters": has_active_filters,
            "canonical_url": canonical_url,
            "pagination_query": pagination_query,
            "active_filters": active_filters,
            "active_filter_count": len(active_filters),
            "clear_filters_url": clear_filters_url,
            "has_sample_listings": has_sample_listings,
            "organization_schema": organization_schema,
            "website_schema": website_schema,
        },
    )
def listing_detail(request, pk):
    listing = get_object_or_404(
        CapacityListing.objects.select_related(
            "manufacturer", "manufacturer__user",
        ).prefetch_related("manufacturer__reviews"),
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

    can_buy_now = (
        request.user.is_authenticated
        and request.user.role == "BUYER"
        and _listing_is_buy_now_eligible(listing)
    )

    social_image_url = (
        urljoin(f"{settings.SITE_ORIGIN}/", listing.image.url)
        if listing.image and not listing.manufacturer.is_demo
        else ""
    )
    listing_url = _absolute_site_url(
        reverse("listing_detail", kwargs={"pk": listing.pk})
    )
    marketplace_url = _absolute_site_url(reverse("marketplace"))
    breadcrumb_schema = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": 1,
                "name": "Marketplace",
                "item": marketplace_url,
            },
            {
                "@type": "ListItem",
                "position": 2,
                "name": listing.title,
                "item": listing_url,
            },
        ],
    }
    service_schema = {
        "@context": "https://schema.org",
        "@type": "Service",
        "name": listing.title,
        "url": listing_url,
        "provider": _manufacturer_schema(listing.manufacturer),
    }
    if listing.description:
        service_schema["description"] = listing.description
    if social_image_url:
        service_schema["image"] = social_image_url

    availability = {
        CapacityListing.AvailabilityStatus.AVAILABLE: "https://schema.org/InStock",
        CapacityListing.AvailabilityStatus.LIMITED: "https://schema.org/LimitedAvailability",
    }.get(listing.availability_status)
    if (
        listing.is_active
        and listing.manufacturer.is_verified
        and not listing.manufacturer.is_demo
        and availability
        and listing.price_per_unit is not None
        and listing.price_per_unit > 0
    ):
        price = format(listing.price_per_unit, "f")
        service_schema["offers"] = {
            "@type": "Offer",
            "url": listing_url,
            "price": price,
            "priceCurrency": "INR",
            "availability": availability,
            "priceSpecification": {
                "@type": "UnitPriceSpecification",
                "price": price,
                "priceCurrency": "INR",
                "unitText": "unit",
            },
        }

    similar_listings = list(
        CapacityListing.objects.filter(
            is_active=True,
            category=listing.category,
        ).filter(
            Q(manufacturer__is_verified=True)
            | Q(manufacturer__user__username__startswith="demo_mfr_"),
        ).exclude(pk=listing.pk).select_related(
            "manufacturer", "manufacturer__user",
        ).order_by("-pk")[:3]
    )

    if listing.manufacturer.is_demo:
        service_schema = None

    return render(
        request,
        "marketplace/listing_detail.html",
        {
            "listing": listing,
            "is_saved": is_saved,
            "social_image_url": social_image_url,
            "breadcrumb_schema": breadcrumb_schema,
            "service_schema": service_schema,
            "similar_listings": similar_listings,
            "can_buy_now": can_buy_now,
        },
    )


def _listing_is_buy_now_eligible(listing):
    return bool(
        listing.is_active
        and listing.manufacturer.is_verified
        and not listing.manufacturer.is_demo
        and listing.availability_status
        in {
            CapacityListing.AvailabilityStatus.AVAILABLE,
            CapacityListing.AvailabilityStatus.LIMITED,
        }
        and listing.price_per_unit is not None
        and listing.price_per_unit > 0
    )


@require_http_methods(["GET", "POST"])
def buy_now(request, pk):
    if not request.user.is_authenticated:
        return redirect(f"{reverse('login')}?next={request.path}")
    if request.user.role != "BUYER":
        raise PermissionDenied("Only buyers can purchase listings.")

    listing = get_object_or_404(
        CapacityListing.objects.select_related("manufacturer", "manufacturer__user"),
        pk=pk,
        is_active=True,
        manufacturer__is_verified=True,
    )
    if not _listing_is_buy_now_eligible(listing):
        raise Http404("This listing is not available for direct purchase.")

    form = BuyNowForm(
        request.POST if request.method == "POST" else None,
        listing=listing,
    )
    action_token = (
        request.POST.get("action_token", "")
        if request.method == "POST"
        else issue_workflow_action_token(
            user=request.user,
            listing=listing,
            action=BUY_NOW_ACTION,
        )
    )
    if request.method == "POST" and form.is_valid():
        action_digest = workflow_action_digest(
            action_token,
            user=request.user,
            listing=listing,
            action=BUY_NOW_ACTION,
        )
        if action_digest is None:
            form.add_error(None, "This purchase form has expired. Reload it to continue.")
            action_token = issue_workflow_action_token(
                user=request.user,
                listing=listing,
                action=BUY_NOW_ACTION,
            )
        else:
            existing_order = Order.objects.filter(
                buy_now_action_digest=action_digest,
                buyer=request.user,
                listing=listing,
                source=Order.Source.BUY_NOW,
            ).first()
            if existing_order is not None:
                messages.info(request, "This purchase was already submitted.")
                return redirect("order_detail", pk=existing_order.pk)

            if Order.objects.filter(buy_now_action_digest=action_digest).exists():
                form.add_error(None, "This purchase form is invalid. Reload it to continue.")
                action_token = issue_workflow_action_token(
                    user=request.user,
                    listing=listing,
                    action=BUY_NOW_ACTION,
                )
            else:
                quantity = form.cleaned_data["quantity"]
                unit_price = listing.price_per_unit
                total = unit_price * quantity
                delivery_location = form.cleaned_data["delivery_location"].strip()
                order = None
                try:
                    with transaction.atomic():
                        if not lock_active_workflow_accounts(
                            (request.user.pk, listing.manufacturer.user_id)
                        ):
                            raise _InactiveWorkflowParticipants
                        order = Order.objects.create(
                            source=Order.Source.BUY_NOW,
                            quotation=None,
                            buy_now_action_digest=action_digest,
                            buyer=request.user,
                            manufacturer=listing.manufacturer,
                            listing=listing,
                            specifications_snapshot={
                                "listing_title": listing.title,
                                "listing_category": listing.get_category_display(),
                                "delivery_location": delivery_location,
                                "machine_type": listing.machine_type,
                                "materials": listing.materials,
                                "technical_capabilities": listing.technical_capabilities,
                                "purchase_source": "BUY_NOW",
                            },
                            quantity=quantity,
                            agreed_unit_price=unit_price,
                            total_amount=total,
                            agreed_production_days=listing.production_days,
                            status=Order.Status.AWAITING_FUNDING,
                            terms_locked_at=timezone.now(),
                        )
                        first_milestone = (total * Decimal("0.80")).quantize(
                            Decimal("0.01")
                        )
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
                                    amount=first_milestone,
                                ),
                                Milestone(
                                    order=order,
                                    title="Ready to ship",
                                    description=(
                                        "Final packing or dispatch readiness checkpoint."
                                    ),
                                    percentage=20,
                                    amount=total - first_milestone,
                                ),
                            ]
                        )
                        create_order_notification(
                            request.user,
                            f"Direct purchase Order #{order.pk} was created. Review its milestone payment options.",
                            order,
                        )
                        create_order_notification(
                            listing.manufacturer.user,
                            f"A Buyer placed direct purchase Order #{order.pk} for {concise_label(listing.title)}.",
                            order,
                        )
                except _InactiveWorkflowParticipants:
                    form.add_error(
                        None,
                        "An account involved in this purchase is no longer active. "
                        "Refresh the page or contact support.",
                    )
                    action_token = issue_workflow_action_token(
                        user=request.user,
                        listing=listing,
                        action=BUY_NOW_ACTION,
                    )
                except IntegrityError:
                    order = Order.objects.filter(
                        buy_now_action_digest=action_digest,
                        buyer=request.user,
                        listing=listing,
                        source=Order.Source.BUY_NOW,
                    ).first()
                    if order is None:
                        raise
                    messages.info(request, "This purchase was already submitted.")
                    return redirect("order_detail", pk=order.pk)

                if order is not None:
                    messages.success(request, "Direct purchase confirmed. Your order is ready.")
                    return redirect("order_detail", pk=order.pk)

    quantity = form["quantity"].value() or form.fields["quantity"].initial
    try:
        requested_quantity = max(0, int(quantity))
    except (TypeError, ValueError):
        requested_quantity = max(1, listing.minimum_quantity)
    estimated_total = listing.price_per_unit * requested_quantity
    first_milestone = (estimated_total * Decimal("0.80")).quantize(Decimal("0.01"))
    return render(
        request,
        "marketplace/buy_now.html",
        {
            "form": form,
            "listing": listing,
            "estimated_total": estimated_total,
            "first_milestone": first_milestone,
            "second_milestone": estimated_total - first_milestone,
            "action_token": action_token,
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

    if listing.manufacturer.is_demo:
        messages.info(
            request,
            "This is a sample listing and is not accepting quote requests.",
        )
        return redirect("listing_detail", pk=listing.pk)

    if request.method == "POST":
        form = QuoteRequestForm(request.POST, listing=listing)
        action_token = request.POST.get("action_token", "")

        if form.is_valid():
            action_digest = workflow_action_digest(
                action_token,
                user=request.user,
                listing=listing,
                action=REQUEST_QUOTE_ACTION,
            )
            if action_digest is None:
                form.add_error(
                    None,
                    "This quote request form has expired. Reload it to continue.",
                )
                action_token = issue_workflow_action_token(
                    user=request.user,
                    listing=listing,
                    action=REQUEST_QUOTE_ACTION,
                )
            else:
                existing_quote = QuoteRequest.objects.filter(
                    action_digest=action_digest,
                    buyer=request.user,
                    listing=listing,
                ).first()
                if existing_quote is not None:
                    messages.info(request, "This quote request was already submitted.")
                    return redirect("my_quote_requests")

                if QuoteRequest.objects.filter(action_digest=action_digest).exists():
                    form.add_error(
                        None,
                        "This quote request form is invalid. Reload it to continue.",
                    )
                    action_token = issue_workflow_action_token(
                        user=request.user,
                        listing=listing,
                        action=REQUEST_QUOTE_ACTION,
                    )
                else:
                    quote = None
                    try:
                        with transaction.atomic():
                            if not lock_active_workflow_accounts(
                                (request.user.pk, listing.manufacturer.user_id)
                            ):
                                raise _InactiveWorkflowParticipants
                            quote = form.save(commit=False)
                            quote.buyer = request.user
                            quote.listing = listing
                            quote.action_digest = action_digest
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
                    except _InactiveWorkflowParticipants:
                        form.add_error(
                            None,
                            "An account involved in this request is no longer active. "
                            "Refresh the page or contact support.",
                        )
                        action_token = issue_workflow_action_token(
                            user=request.user,
                            listing=listing,
                            action=REQUEST_QUOTE_ACTION,
                        )
                    except IntegrityError:
                        quote = QuoteRequest.objects.filter(
                            action_digest=action_digest,
                            buyer=request.user,
                            listing=listing,
                        ).first()
                        if quote is None:
                            raise
                        messages.info(request, "This quote request was already submitted.")
                        return redirect("my_quote_requests")

                    if quote is not None:
                        messages.success(
                            request,
                            "Your quote request was submitted.",
                        )

                        return redirect("request_quote", pk=listing.pk)
    else:
        form = QuoteRequestForm(listing=listing)
        action_token = issue_workflow_action_token(
            user=request.user,
            listing=listing,
            action=REQUEST_QUOTE_ACTION,
        )

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
            "action_token": action_token,
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
    for order in active_orders:
        order.status_label = _order_status_label(
            order, _order_uses_razorpay_test_mode(order)
        )

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
    ).select_related(
        "order", "order__manufacturer", "order__manufacturer__user", "order__listing"
    )
    funding_milestones = list(funding_milestones)
    for milestone in funding_milestones:
        milestone.payment_enabled = _order_uses_razorpay_test_mode(milestone.order)

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

    return render(
        request,
        "marketplace/buyer_dashboard.html",
        {
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

    for order in orders:
        order.payment_test_mode = _order_uses_razorpay_test_mode(order)
        order.status_label = _order_status_label(order, order.payment_test_mode)

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

    for order in orders:
        order.payment_test_mode = _order_uses_razorpay_test_mode(order)
        order.status_label = _order_status_label(order, order.payment_test_mode)

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
    payment_test_mode = _order_uses_razorpay_test_mode(order)
    for step in timeline_steps:
        if step["title"] == "Demo funding" and payment_test_mode:
            step["title"] = "Milestone payments"
            step["body"] = (
                "Test payments are not live. Manufacturer payout and release remain simulated."
            )
    activity_items = Notification.objects.filter(
        recipient=request.user,
        order=order,
    ).order_by("-created_at", "-pk")[:8]

    return render(
        request,
        "marketplace/order_detail.html",
        {
            "order": order,
            "payment_test_mode": payment_test_mode,
            "order_origin_label": (
                "Direct purchase confirmed"
                if order.source == Order.Source.BUY_NOW
                else "Quotation accepted"
            ),
            "order_status_label": _order_status_label(order, payment_test_mode),
            "milestones": milestones,
            "financial_summary": financial_summary,
            "next_action": next_action,
            "timeline_steps": timeline_steps,
            "activity_items": activity_items,
            "message_form": OrderMessageForm(),
            "review_form": ReviewForm(),
        },
    )


def _order_uses_razorpay_test_mode(order):
    return bool(
        razorpay_test_mode_enabled()
        and order.manufacturer.is_verified
        and not order.manufacturer.is_demo
    )


def _order_status_label(order, payment_test_mode=False):
    if payment_test_mode:
        if order.status == Order.Status.AWAITING_FUNDING:
            return "Awaiting milestone payment"
        if order.status == Order.Status.FUNDED:
            return "Milestone payment recorded"
    return order.get_status_display()


def _mark_payment_captured(payment_transaction, payment_id):
    with transaction.atomic():
        payment_scope = PaymentTransaction.objects.filter(
            pk=payment_transaction.pk,
        )
        milestone_order_id, milestone_id = payment_scope.values_list(
            "milestone__order_id",
            "milestone_id",
        ).get()
        order = Order.objects.select_for_update().get(pk=milestone_order_id)
        milestone = Milestone.objects.select_for_update().get(
            pk=milestone_id,
            order_id=order.pk,
        )
        saved_payment = PaymentTransaction.objects.select_for_update().get(
            pk=payment_transaction.pk,
            milestone_id=milestone.pk,
        )
        if saved_payment.status == PaymentTransaction.Status.CAPTURED:
            return False

        saved_payment.status = PaymentTransaction.Status.CAPTURED
        saved_payment.provider_payment_id = payment_id
        saved_payment.captured_at = timezone.now()
        saved_payment.save(
            update_fields=(
                "status",
                "provider_payment_id",
                "captured_at",
                "updated_at",
            )
        )

        milestone_updated = Milestone.objects.filter(
            pk=milestone.pk,
            order__buyer=saved_payment.buyer,
            status=Milestone.Status.PENDING,
            funding_status=Milestone.FundingStatus.NOT_FUNDED,
        ).update(
            funding_status=Milestone.FundingStatus.FUNDED,
            funded_at=timezone.now(),
        )
        if milestone_updated:
            milestone.refresh_from_db()
            previous_order_status, _ = refresh_order_status(order)
            create_order_notification(
                order.manufacturer.user,
                (
                    f"Payment recorded in Razorpay Test Mode for {concise_label(milestone.title)} "
                    f"on Order #{order.pk}. The milestone is ready to start; "
                    "Manufacturer payout remains simulated."
                ),
                order,
            )
            create_order_notification(
                saved_payment.buyer,
                (
                    f"Test payment recorded for {concise_label(milestone.title)} "
                    f"on Order #{order.pk}. Manufacturer payout remains simulated."
                ),
                order,
            )
            notify_order_status_change(order, previous_order_status)
        return bool(milestone_updated)


def _mark_payment_failed(payment_transaction, payment_id=""):
    with transaction.atomic():
        saved_payment = PaymentTransaction.objects.select_for_update().get(
            pk=payment_transaction.pk
        )
        if saved_payment.status == PaymentTransaction.Status.CAPTURED:
            return False
        saved_payment.status = PaymentTransaction.Status.FAILED
        if payment_id:
            saved_payment.provider_payment_id = payment_id
        saved_payment.save(
            update_fields=("status", "provider_payment_id", "updated_at")
        )
        return True


def _gateway_payment_matches(payment_transaction, payment, gateway_order):
    try:
        amount = amount_to_paise(payment_transaction.amount)
        return bool(
            payment.get("order_id") == payment_transaction.provider_order_id
            and gateway_order.get("id") == payment_transaction.provider_order_id
            and int(payment.get("amount", -1)) == amount
            and int(gateway_order.get("amount", -1)) == amount
            and payment.get("currency") == payment_transaction.currency == "INR"
            and gateway_order.get("currency") == payment_transaction.currency
        )
    except (TypeError, ValueError, ArithmeticError):
        return False


def _start_razorpay_milestone_payment(milestone, buyer):
    with transaction.atomic():
        order, locked = _lock_order_and_milestone(
            milestone.pk,
            buyer=buyer,
        )
        locked.order = order
        add_milestone_action_flags(locked, buyer)
        if not locked.can_fund or not _order_uses_razorpay_test_mode(locked.order):
            return None, "This milestone cannot be paid in its current state."
        if locked.amount is None or locked.amount <= 0:
            return None, "This milestone does not have a payable amount."

        payment_transaction = PaymentTransaction.objects.select_for_update().filter(
            milestone=locked,
            provider=PaymentTransaction.Provider.RAZORPAY,
            status=PaymentTransaction.Status.CREATED,
        ).order_by("-created_at", "-pk").first()
        if payment_transaction and payment_transaction.amount != locked.amount:
            payment_transaction.status = PaymentTransaction.Status.FAILED
            payment_transaction.save(update_fields=("status", "updated_at"))
            payment_transaction = None

        if payment_transaction is None:
            payment_transaction = PaymentTransaction.objects.create(
                buyer=buyer,
                milestone=locked,
                amount=locked.amount,
                currency="INR",
                provider=PaymentTransaction.Provider.RAZORPAY,
            )

        if payment_transaction.provider_order_id:
            return payment_transaction, ""

        try:
            expected_paise = amount_to_paise(locked.amount)
            gateway_order = get_razorpay_client().order.create(
                data={
                    "amount": expected_paise,
                    "currency": "INR",
                    "receipt": f"uv-m{locked.pk}-t{payment_transaction.pk}",
                    "notes": {
                        "milestone_id": str(locked.pk),
                        "payment_transaction_id": str(payment_transaction.pk),
                    },
                }
            )
            if (
                not gateway_order.get("id")
                or int(gateway_order.get("amount", -1)) != expected_paise
                or gateway_order.get("currency") != "INR"
            ):
                raise ValueError("Razorpay returned an inconsistent order.")
            payment_transaction.provider_order_id = gateway_order["id"]
            payment_transaction.save(
                update_fields=("provider_order_id", "updated_at")
            )
        except Exception as exc:
            payment_transaction.status = PaymentTransaction.Status.FAILED
            payment_transaction.save(update_fields=("status", "updated_at"))
            logger.warning(
                "Razorpay Test Mode order creation failed for transaction %s (%s)",
                payment_transaction.pk,
                type(exc).__name__,
            )
            return None, "Test payment could not be started. Please try again."
        return payment_transaction, ""


@login_required
@require_POST
def verify_milestone_payment(request):
    if request.user.role != "BUYER":
        raise PermissionDenied("Only buyers can verify milestone payments.")

    transaction_id = request.POST.get("payment_transaction_id", "")
    try:
        payment_transaction = PaymentTransaction.objects.select_related(
            "milestone__order__manufacturer",
            "milestone__order__manufacturer__user",
        ).get(pk=transaction_id, buyer=request.user)
    except (PaymentTransaction.DoesNotExist, ValueError, TypeError):
        raise Http404("Payment transaction not found.")

    gateway_order_id = request.POST.get("razorpay_order_id", "")
    payment_id = request.POST.get("razorpay_payment_id", "")
    signature = request.POST.get("razorpay_signature", "")
    if (
        not _order_uses_razorpay_test_mode(payment_transaction.milestone.order)
        or not payment_transaction.provider_order_id
        or gateway_order_id != payment_transaction.provider_order_id
        or not checkout_signature_is_valid(gateway_order_id, payment_id, signature)
    ):
        messages.error(request, "The test payment could not be verified.")
        return redirect("order_detail", pk=payment_transaction.milestone.order_id)

    if payment_transaction.status == PaymentTransaction.Status.CAPTURED:
        messages.success(request, "This test payment has already been recorded.")
        return redirect("order_detail", pk=payment_transaction.milestone.order_id)

    try:
        client = get_razorpay_client()
        payment = client.payment.fetch(payment_id)
        gateway_order = client.order.fetch(gateway_order_id)
    except Exception as exc:
        logger.warning(
            "Razorpay Test Mode verification failed for transaction %s (%s)",
            payment_transaction.pk,
            type(exc).__name__,
        )
        messages.error(request, "The test payment could not be verified. You can try again.")
        return redirect("order_detail", pk=payment_transaction.milestone.order_id)

    if (
        not _gateway_payment_matches(payment_transaction, payment, gateway_order)
        or payment.get("id") != payment_id
        or payment.get("status") != "captured"
        or gateway_order.get("status") != "paid"
    ):
        messages.error(request, "The test payment is not captured for this order.")
        return redirect("order_detail", pk=payment_transaction.milestone.order_id)

    _mark_payment_captured(payment_transaction, payment_id)
    messages.success(
        request,
        "Test payment recorded. Manufacturer payout remains simulated.",
    )
    return redirect("order_detail", pk=payment_transaction.milestone.order_id)


@login_required
@require_POST
def report_milestone_payment_failure(request):
    if request.user.role != "BUYER":
        raise PermissionDenied("Only buyers can report milestone payments.")
    try:
        payment_transaction = PaymentTransaction.objects.select_related(
            "milestone__order"
        ).get(
            pk=request.POST.get("payment_transaction_id", ""),
            buyer=request.user,
        )
    except (PaymentTransaction.DoesNotExist, ValueError, TypeError):
        raise Http404("Payment transaction not found.")

    gateway_order_id = request.POST.get("razorpay_order_id", "")
    payment_id = request.POST.get("razorpay_payment_id", "")
    if (
        gateway_order_id == payment_transaction.provider_order_id
        and payment_id
        and razorpay_test_mode_enabled()
    ):
        try:
            gateway_payment = get_razorpay_client().payment.fetch(payment_id)
            if (
                gateway_payment.get("order_id") == gateway_order_id
                and gateway_payment.get("status") == "failed"
                and int(gateway_payment.get("amount", -1))
                == amount_to_paise(payment_transaction.amount)
                and gateway_payment.get("currency") == "INR"
            ):
                _mark_payment_failed(payment_transaction, payment_id)
        except Exception as exc:
            logger.warning(
                "Razorpay failure confirmation failed for transaction %s (%s)",
                payment_transaction.pk,
                type(exc).__name__,
            )
    messages.info(request, "Payment was not completed. You can try again.")
    return redirect("order_detail", pk=payment_transaction.milestone.order_id)


@csrf_exempt
@require_POST
def razorpay_webhook(request):
    if not razorpay_test_mode_enabled():
        return HttpResponse(status=404)
    signature = request.headers.get("X-Razorpay-Signature", "")
    event_id = request.headers.get("X-Razorpay-Event-Id", "").strip()
    if not event_id or len(event_id) > 128 or not webhook_signature_is_valid(
        request.body, signature
    ):
        return HttpResponse(status=400)
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return HttpResponse(status=400)

    event_type = str(payload.get("event", ""))[:80]
    with transaction.atomic():
        event, created = PaymentWebhookEvent.objects.get_or_create(
            event_id=event_id,
            defaults={"event_type": event_type},
        )
        if not created:
            return HttpResponse("ok", content_type="text/plain")

        entity = (
            payload.get("payload", {}).get("payment", {}).get("entity", {})
        )
        order_id = entity.get("order_id")
        payment_id = entity.get("id")
        payment_transaction = PaymentTransaction.objects.filter(
            provider=PaymentTransaction.Provider.RAZORPAY,
            provider_order_id=order_id,
        ).first()
        if payment_transaction is None:
            event.status = PaymentWebhookEvent.ProcessingStatus.IGNORED
            event.processing_note = "No matching payment transaction."
        else:
            event.payment_transaction = payment_transaction
            amount_matches = False
            try:
                amount_matches = (
                    int(entity.get("amount", -1))
                    == amount_to_paise(payment_transaction.amount)
                    and entity.get("currency") == payment_transaction.currency == "INR"
                )
            except (TypeError, ValueError, ArithmeticError):
                pass

            if event_type == "payment.captured" and entity.get("status") == "captured" and payment_id and amount_matches:
                _mark_payment_captured(payment_transaction, payment_id)
                event.status = PaymentWebhookEvent.ProcessingStatus.PROCESSED
                event.processing_note = "Captured payment verified against transaction."
            elif event_type == "payment.failed" and entity.get("status") == "failed" and payment_id and amount_matches:
                _mark_payment_failed(payment_transaction, payment_id)
                event.status = PaymentWebhookEvent.ProcessingStatus.PROCESSED
                event.processing_note = "Failed payment recorded; milestone remains payable."
            else:
                event.status = PaymentWebhookEvent.ProcessingStatus.IGNORED
                event.processing_note = "Unsupported or mismatched payment event."
        event.processed_at = timezone.now()
        event.save(
            update_fields=(
                "event_type",
                "status",
                "payment_transaction",
                "processed_at",
                "processing_note",
            )
        )
    return HttpResponse("ok", content_type="text/plain")


@login_required
@require_http_methods(["GET", "POST"])
def fund_milestone(request, pk):
    if request.user.role != "BUYER":
        raise PermissionDenied("Only buyers can fund milestones.")

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
    test_mode = milestone.payment_enabled

    if request.method == "GET":
        return render(
            request,
            "marketplace/fund_milestone.html",
            {
                "milestone": milestone,
                "order": milestone.order,
                "razorpay_test_mode": test_mode,
            },
        )

    if not milestone.can_fund:
        messages.info(
            request,
            "This milestone cannot be funded in its current state.",
        )
        return redirect("order_detail", pk=milestone.order_id)

    if test_mode:
        payment_transaction, error_message = _start_razorpay_milestone_payment(
            milestone, request.user
        )
        if not payment_transaction:
            messages.error(request, error_message)
            return redirect("order_detail", pk=milestone.order_id)
        return render(
            request,
            "marketplace/razorpay_checkout.html",
            {
                "order": milestone.order,
                "milestone": milestone,
                "payment_transaction": payment_transaction,
                "razorpay_key_id": settings.RAZORPAY_KEY_ID,
                "razorpay_order_id": payment_transaction.provider_order_id,
                "amount_paise": amount_to_paise(payment_transaction.amount),
                "checkout_options": {
                    "key": settings.RAZORPAY_KEY_ID,
                    "amount": amount_to_paise(payment_transaction.amount),
                    "currency": "INR",
                    "name": "Ubhaar-Vyapaar",
                    "description": f"{milestone.title} · Order #{milestone.order_id}",
                    "order_id": payment_transaction.provider_order_id,
                    "theme": {"color": "#176b50"},
                },
                "verify_url": reverse("verify_milestone_payment"),
                "failure_url": reverse("report_milestone_payment_failure"),
            },
        )

    with transaction.atomic():
        order, milestone = _lock_order_and_milestone(
            pk,
            buyer=request.user,
        )
        add_milestone_action_flags(milestone, request.user)
        updated = 0
        if milestone.can_fund:
            updated = Milestone.objects.filter(
                pk=milestone.pk,
                order_id=order.pk,
                order__buyer=request.user,
                status=Milestone.Status.PENDING,
                funding_status=Milestone.FundingStatus.NOT_FUNDED,
            ).update(
                funding_status=Milestone.FundingStatus.FUNDED,
                funded_at=timezone.now(),
            )

        if updated:
            milestone.refresh_from_db()
            previous_order_status, _ = refresh_order_status(order)
            milestone_title = concise_label(milestone.title)

            create_order_notification(
                order.manufacturer.user,
                (
                    f"Buyer funded the {milestone_title} milestone for "
                    f"Order #{order.pk} (demo funding). Start it "
                    "when production is ready."
                ),
                order,
            )
            create_order_notification(
                request.user,
                (
                    f"Demo funding confirmed for {milestone_title} on "
                    f"Order #{order.pk}. No real money was processed."
                ),
                order,
            )
            notify_order_status_change(order, previous_order_status)

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
                "This milestone cannot be started until its funding step is recorded.",
        )
        return redirect("order_detail", pk=milestone.order_id)

    with transaction.atomic():
        order, milestone = _lock_order_and_milestone(
            pk,
            manufacturer_user=request.user,
        )
        add_milestone_action_flags(milestone, request.user)
        updated = 0
        if milestone.can_start:
            updated = Milestone.objects.filter(
                pk=milestone.pk,
                order_id=order.pk,
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
            previous_order_status, _ = refresh_order_status(order)
            milestone_title = concise_label(milestone.title)
            create_order_notification(
                order.buyer,
                (
                    f"Manufacturer started the {milestone_title} milestone "
                    f"for Order #{order.pk}."
                ),
                order,
            )
            notify_order_status_change(order, previous_order_status)

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
            if lock_active_workflow_accounts(
                (order.buyer_id, order.manufacturer.user_id)
            ):
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
                sent = True
            else:
                sent = False

        if sent:
            messages.success(request, "Message sent.")
        else:
            messages.error(request, "This account is no longer active.")
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
            with transaction.atomic():
                if lock_active_workflow_accounts(
                    (request.user.pk, order.manufacturer.user_id)
                ):
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
                    reviewed = True
                else:
                    form.add_error(None, "This account is no longer active.")
                    reviewed = False

            if reviewed:
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

    if not milestone.can_submit:
        messages.info(
            request,
            "This milestone must be funded and in progress before submission.",
        )
        return redirect("order_detail", pk=milestone.order_id)

    with transaction.atomic():
        order, milestone = _lock_order_and_milestone(
            pk,
            manufacturer_user=request.user,
        )
        add_milestone_action_flags(milestone, request.user)
        updated = Milestone.objects.filter(
            pk=milestone.pk,
            order_id=order.pk,
            order__manufacturer__user=request.user,
            order__status__in=[
                Order.Status.CONFIRMED,
                Order.Status.AWAITING_FUNDING,
                Order.Status.FUNDED,
                Order.Status.IN_PRODUCTION,
                Order.Status.MILESTONE_PENDING,
                Order.Status.READY_TO_SHIP,
                Order.Status.SHIPPED,
            ],
            status=Milestone.Status.IN_PROGRESS,
            funding_status=Milestone.FundingStatus.FUNDED,
        ).update(
            status=Milestone.Status.COMPLETED,
            completed_at=timezone.now(),
        )
        if updated:
            milestone.refresh_from_db()
            previous_order_status, _ = refresh_order_status(order)
            milestone_title = concise_label(milestone.title)

            create_order_notification(
                order.buyer,
                message=(
                    f"{milestone_title} milestone is ready for your approval "
                    f"on Order #{order.pk}. Review the work and approve "
                    "or request changes."
                ),
                order=order,
            )
            notify_order_status_change(order, previous_order_status)

    if updated:
        messages.success(request, "Milestone submitted for buyer approval.")
    else:
        messages.info(request, "This milestone has already changed.")

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

    with transaction.atomic():
        order, milestone = _lock_order_and_milestone(
            pk,
            buyer=request.user,
        )
        update_fields = {
            "status": decision,
            "buyer_feedback": feedback,
            "approved_at": timezone.now()
            if decision == Milestone.Status.APPROVED
            else None,
            "completed_at": None
            if decision == Milestone.Status.REJECTED
            else milestone.completed_at,
            "updated_at": timezone.now(),
        }
        updated = Milestone.objects.filter(
            pk=milestone.pk,
            order__buyer=request.user,
            order__status__in=[
                Order.Status.CONFIRMED,
                Order.Status.AWAITING_FUNDING,
                Order.Status.FUNDED,
                Order.Status.IN_PRODUCTION,
                Order.Status.MILESTONE_PENDING,
                Order.Status.READY_TO_SHIP,
                Order.Status.SHIPPED,
            ],
            status=Milestone.Status.COMPLETED,
        ).update(**update_fields)

        if updated:
            milestone.refresh_from_db()
            previous_order_status, _ = refresh_order_status(order)
            response_label = (
                "approved"
                if decision == Milestone.Status.APPROVED
                else "requested changes for"
            )
            milestone_title = concise_label(milestone.title)

            create_order_notification(
                order.manufacturer.user,
                message=(
                    f"The buyer {response_label} the {milestone_title} milestone "
                    f"on Order #{order.pk}."
                ),
                order=order,
            )
            notify_order_status_change(order, previous_order_status)

    if updated:
        messages.success(request, "Milestone response saved.")
    else:
        messages.info(request, "This milestone has already changed.")
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
        order, milestone = _lock_order_and_milestone(
            pk,
            buyer=request.user,
        )
        add_milestone_action_flags(milestone, request.user)
        updated = 0
        if milestone.can_release:
            updated = Milestone.objects.filter(
                pk=milestone.pk,
                order_id=order.pk,
                order__buyer=request.user,
                status=Milestone.Status.APPROVED,
                funding_status=Milestone.FundingStatus.FUNDED,
            ).update(
                funding_status=Milestone.FundingStatus.RELEASED,
                released_at=timezone.now(),
            )

        if updated:
            milestone.refresh_from_db()
            previous_order_status, _ = refresh_order_status(order)
            milestone_title = concise_label(milestone.title)

            create_order_notification(
                order.manufacturer.user,
                (
                    f"Buyer released demo payment for milestone "
                    f"{milestone_title} on Order #{order.pk}. "
                    "No real money was transferred."
                ),
                order,
            )
            create_order_notification(
                request.user,
                (
                    f"Demo payment released for milestone "
                    f"{milestone_title} on Order #{order.pk}. "
                    "No real money was transferred."
                ),
                order,
            )
            notify_order_status_change(order, previous_order_status)

            if (
                previous_order_status != Order.Status.COMPLETED
                and order.status == Order.Status.COMPLETED
            ):
                create_order_notification(
                    request.user,
                    message=(
                        f"Order #{order.pk} is complete. "
                        "You can now leave a review."
                    ),
                    order=order,
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
    for order in active_orders:
        order.status_label = _order_status_label(
            order, _order_uses_razorpay_test_mode(order)
        )

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
    ).select_related("order", "order__buyer", "order__listing").prefetch_related(
        Prefetch(
            "payment_transactions",
            queryset=PaymentTransaction.objects.filter(
                status=PaymentTransaction.Status.CAPTURED,
            ),
        ),
    )

    # Only call a funding record a test payment when a captured gateway
    # transaction exists; older demo-funded milestones remain labelled as demo.
    for milestone in milestones_ready_to_start:
        milestone.payment_test_mode = bool(
            milestone.payment_transactions.all()
        )

    milestones_ready_to_submit = Milestone.objects.filter(
        order__manufacturer__user=request.user,
        order__status__in=[
            Order.Status.IN_PRODUCTION,
            Order.Status.FUNDED,
        ],
        status=Milestone.Status.IN_PROGRESS,
        funding_status=Milestone.FundingStatus.FUNDED,
    ).select_related("order", "order__buyer", "order__listing")

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
        form_is_valid = form.is_valid()

        if getattr(request, "_listing_image_too_large", False):
            form.add_error("image", LISTING_IMAGE_TOO_LARGE_MESSAGE)
        elif form_is_valid:
            pending_listing = form.save(commit=False)
            with transaction.atomic():
                if lock_active_workflow_accounts((request.user.pk,)):
                    manufacturer = ManufacturerProfile.objects.select_for_update().get(
                        pk=manufacturer.pk,
                        user=request.user,
                    )
                    pending_listing.manufacturer = manufacturer
                    pending_listing.is_active = True
                    pending_listing.save()
                    created = True
                else:
                    form.add_error(None, "This account is no longer active.")
                    created = False

            if created:
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
        form_is_valid = form.is_valid()

        if getattr(request, "_listing_image_too_large", False):
            form.add_error("image", LISTING_IMAGE_TOO_LARGE_MESSAGE)
        elif form_is_valid:
            pending_listing = form.save(commit=False)
            with transaction.atomic():
                if lock_active_workflow_accounts((request.user.pk,)):
                    listing = CapacityListing.objects.select_for_update().get(
                        pk=listing.pk,
                        manufacturer__user=request.user,
                    )
                    for field_name in form.changed_data:
                        setattr(
                            listing,
                            field_name,
                            getattr(pending_listing, field_name),
                        )
                    listing.save()
                    updated = True
                else:
                    form.add_error(None, "This account is no longer active.")
                    updated = False

            if updated:
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
        QuoteRequest.objects.select_related(
            "listing",
            "listing__manufacturer__user",
            "buyer",
        ),
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
                if not lock_active_workflow_accounts(
                    (request.user.pk, quote_request.buyer_id)
                ):
                    messages.error(
                        request,
                        "An account involved in this request is no longer active. "
                        "Refresh the page or contact support.",
                    )
                    return redirect("manufacturer_dashboard")
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
            "quote_request__listing__manufacturer__user",
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
        updated = 0
        if lock_active_workflow_accounts(
            (
                request.user.pk,
                quotation.quote_request.listing.manufacturer.user_id,
            )
        ):
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
                        f"quotation for {listing_title}. Review its milestone "
                        "funding options to start production."
                    ),
                    order=order,
                )

    if updated:
        if new_status == Quotation.Status.ACCEPTED:
            messages.success(
                request,
                "You accepted the quotation and an order was created. No payment is taken at acceptance.",
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
        CapacityListing.objects.select_related(
            "manufacturer",
            "manufacturer__user",
        ),
        Q(manufacturer__is_verified=True)
        | Q(manufacturer__user__username__startswith="demo_mfr_"),
        pk=pk,
        is_active=True,
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
        ManufacturerProfile.objects.select_related("user").prefetch_related(
            "reviews",
        ),
        pk=pk,
    )
    if not manufacturer.user.is_active:
        raise Http404
    if not manufacturer.is_verified and not manufacturer.is_demo:
        raise Http404

    manufacturer_public_name = manufacturer.business_name.strip() or "Manufacturer"

    listings = CapacityListing.objects.filter(
        manufacturer=manufacturer,
        is_active=True,
    ).select_related("manufacturer", "manufacturer__user").order_by("-pk")

    paginator = Paginator(listings, 9)
    page_obj = paginator.get_page(request.GET.get("page"))
    canonical_url = f"{settings.SITE_ORIGIN}{request.path}"
    if page_obj.number > 1:
        canonical_url = f"{canonical_url}?page={page_obj.number}"

    marketplace_url = _absolute_site_url(reverse("marketplace"))
    breadcrumb_schema = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": 1,
                "name": "Marketplace",
                "item": marketplace_url,
            },
            {
                "@type": "ListItem",
                "position": 2,
                "name": manufacturer_public_name,
                "item": canonical_url,
            },
        ],
    }

    manufacturer_schema = None if manufacturer.is_demo else {
        "@context": "https://schema.org",
        **_manufacturer_schema(manufacturer, manufacturer_public_name),
    }

    return render(
        request,
        "marketplace/manufacturer_profile.html",
        {
            "manufacturer": manufacturer,
            "manufacturer_public_name": manufacturer_public_name,
            "page_obj": page_obj,
            "canonical_url": canonical_url,
            "manufacturer_schema": manufacturer_schema,
            "breadcrumb_schema": breadcrumb_schema,
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
            pending_profile = form.save(commit=False)

            with transaction.atomic():
                if lock_active_workflow_accounts((request.user.pk,)):
                    manufacturer = ManufacturerProfile.objects.select_for_update().get(
                        pk=manufacturer.pk,
                        user=request.user,
                    )
                    for field_name in form.changed_data:
                        setattr(
                            manufacturer,
                            field_name,
                            getattr(pending_profile, field_name),
                        )
                    profile = manufacturer

                    if needs_review:
                        profile.is_verified = False
                        profile.kyc_status = ManufacturerProfile.KycStatus.UNDER_REVIEW

                    profile.save()
                    updated = True
                else:
                    form.add_error(None, "This account is no longer active.")
                    updated = False

            if not updated:
                return render(
                    request,
                    "marketplace/edit_business_profile.html",
                    {"form": form, "manufacturer": manufacturer},
                )

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
