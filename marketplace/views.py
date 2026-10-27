import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import EmailMessage
from django.core.validators import validate_email
from django.core.paginator import Paginator
from django.db.models import Case, Count, IntegerField, Q, When
from django.db import IntegrityError, transaction
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

from .forms import (
    CapacityListingEditForm,
    CapacityListingForm,
    ContactSubmissionForm,
    WaitlistEntryForm,
    OrderMessageForm,
    QuoteRequestForm,
    QuotationForm,
    ManufacturerProfileForm,
    ReviewForm,
)
from .models import (
    CapacityListing,
    ContactSubmission,
    ManufacturerProfile,
    Milestone,
    Notification,
    Order,
    QuoteRequest,
    Quotation,
    Review,
    SavedListing,
    WaitlistEntry,
)

logger = logging.getLogger(__name__)

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


def _manufacturer_schema(manufacturer):
    profile_url = _absolute_site_url(
        reverse("manufacturer_profile", kwargs={"pk": manufacturer.pk})
    )
    organization = {
        "@type": "Organization",
        "name": manufacturer.business_name,
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
            messages.success(request, "Your message has been received.")
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

            messages.success(request, "Your message has been received.")
            return redirect("contact")
    else:
        form = ContactSubmissionForm()

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
                {"question": "How do I find manufacturing capacity?", "answer": "Browse active listings or search and filter by the details available in the marketplace."},
                {"question": "Can a manufacturer pause a listing?", "answer": "Yes. Paused listings may remain visible, are labeled as paused, and are not prioritized in default discovery."},
                {"question": "Can I change my password?", "answer": "Yes. Signed-in users can change their password from account settings."},
            ],
        },
        {
            "id": "faq-quotations",
            "title": "Quote requests",
            "items": [
                {"question": "How do I request a quotation?", "answer": "Open a listing that accepts requests and provide the requested quantity, requirements, and delivery location. Sample listings are illustrative and do not accept quote requests."},
                {"question": "What can a manufacturer manage?", "answer": "A manufacturer account can create and edit capacity listings, respond to quote requests with quotations, and manage accepted orders and milestones."},
            ],
        },
        {
            "id": "faq-orders",
            "title": "Orders and milestones",
            "items": [
                {"question": "What happens when a buyer accepts or declines a quotation?", "answer": "A buyer can accept or decline a quotation. Acceptance creates an order with the accepted terms, messages, and production milestones."},
                {"question": "How do order messages, milestones, and reviews work?", "answer": "Order participants can exchange messages and update production milestones. A buyer can leave a review after an order is completed, subject to the existing review rules."},
            ],
        },
        {
            "id": "faq-verification-payments",
            "title": "Verification and payments",
            "items": [
                {"question": "What does Verified mean?", "answer": "The Verified badge appears only on eligible non-Sample manufacturer profiles when the profile's existing verification flag is approved. KYC status by itself does not display the badge. This status is not a product or transaction guarantee."},
                {"question": "Does Ubhaar-Vyapaar process payments?", "answer": "No. The platform does not process real payments or collect, hold, or release money. Funding and release states shown in the order workflow are simulated and do not represent actual funds."},
                {"question": "Does the platform collect a fee?", "answer": "The current application does not calculate or collect platform fees. Any listing or quotation prices are part of the Buyer–Manufacturer commercial discussion."},
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

MARKETPLACE_QUERY_PARAMS = {
    "q", "category", "location", "moq", "max_price", "lead_time",
    "verification", "sort", "page",
}

LANDING_FAQ_ITEMS = [
    {
        "question": "How do I find capacity?",
        "answer": "Browse the marketplace or use search and filters to find active listings that match your needs.",
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
        "question": "How do I request a quote?",
        "answer": "Open a listing that accepts requests and submit your quantity, requirements, and delivery location. Sample listings do not accept quote requests.",
    },
    {
        "question": "What happens when a quotation is accepted?",
        "answer": "Accepting a quotation creates an order with the agreed terms, order messages, and production milestones.",
    },
    {
        "question": "Does the platform process payments or escrow?",
        "answer": "No. Payments and escrow are not processed by the platform. Any funding or release labels in the order workflow are simulated.",
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
                "Thanks — your interest has been recorded. We’ll use your email only in relation to early access.",
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
                    "Thanks — your interest has been recorded. We’ll use your email only in relation to early access.",
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
        discovery_listings.select_related("manufacturer").order_by("-pk")[:6]
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
            "has_featured_capacity": len(featured_listings) >= 3,
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

    category_labels = dict(available_categories)
    active_filter_specs = [
        ("q", query, f'Search: {query}'),
        ("category", selected_category, f'Category: {category_labels.get(selected_category, selected_category)}'),
        ("location", location, f"Location: {location}"),
        ("moq", moq, f"MOQ up to {moq}"),
        ("max_price", max_price, f"Price up to ₹{max_price}"),
        ("lead_time", lead_time, f"Lead time up to {lead_time} days"),
        ("verification", verification, "Verified only" if verification else ""),
        ("sort", sort if sort != "newest" else "", f"Sort: {sort.replace('_', ' ').title()}"),
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
            "canonical_url": canonical_url,
            "pagination_query": pagination_query,
            "active_filters": active_filters,
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
        ManufacturerProfile.objects.select_related("user").prefetch_related(
            "reviews", "reviews__buyer", "reviews__order",
        ),
        pk=pk,
    )
    if not manufacturer.is_verified and not manufacturer.is_demo:
        raise Http404

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
                "name": manufacturer.business_name,
                "item": canonical_url,
            },
        ],
    }

    manufacturer_schema = None if manufacturer.is_demo else {
        "@context": "https://schema.org",
        **_manufacturer_schema(manufacturer),
    }

    return render(
        request,
        "marketplace/manufacturer_profile.html",
        {
            "manufacturer": manufacturer,
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
