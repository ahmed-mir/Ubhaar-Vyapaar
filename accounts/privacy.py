"""User-scoped privacy export and account-closure operations."""

import logging
from uuid import uuid4

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import User

logger = logging.getLogger("accounts.privacy")


def lock_active_workflow_accounts(user_ids):
    """Serialize account-scoped writes against closure in stable ID order."""
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("Workflow participant locks require transaction.atomic().")
    ids = sorted({int(user_id) for user_id in user_ids if user_id is not None})
    if not ids:
        return False
    locked_users = list(
        User.objects.select_for_update()
        .filter(pk__in=ids)
        .only("pk", "is_active")
        .order_by("pk")
    )
    return len(locked_users) == len(ids) and all(
        user.is_active for user in locked_users
    )


def has_active_workflows(user):
    """Whether closure could abandon an open marketplace obligation."""
    from marketplace.models import (
        Order,
        PaymentTransaction,
        Quotation,
        QuoteRequest,
    )

    profile = getattr(user, "manufacturer_profile", None)
    order_scope = Q(buyer=user)
    quote_scope = Q()
    payment_scope = Q(buyer=user) | Q(milestone__order__buyer=user)
    if profile is not None:
        order_scope |= Q(manufacturer=profile)
        quote_scope = Q(listing__manufacturer=profile)
        payment_scope |= Q(milestone__order__manufacturer=profile)

    active_order_statuses = tuple(
        value
        for value, _label in Order.Status.choices
        if value not in (Order.Status.COMPLETED, Order.Status.CANCELLED)
    )
    if Order.objects.filter(
        order_scope,
        status__in=active_order_statuses,
    ).exists():
        return True

    open_quotes = QuoteRequest.objects.filter(quote_scope | Q(buyer=user)).filter(
        Q(status=QuoteRequest.Status.PENDING)
        | Q(quotation__status=Quotation.Status.SENT)
        | Q(
            quotation__status=Quotation.Status.ACCEPTED,
            quotation__order__isnull=True,
        )
        | Q(
            status=QuoteRequest.Status.ACCEPTED,
            quotation__isnull=True,
        )
    )
    if open_quotes.exists():
        return True

    return PaymentTransaction.objects.filter(
        payment_scope,
        status=PaymentTransaction.Status.CREATED,
    ).exists()


def _iso(value):
    return value.isoformat() if value is not None else None


def build_user_export(user):
    """Build a user-owned JSON document with explicit, allowlisted fields."""
    from marketplace.models import (
        CapacityListing,
        Milestone,
        Notification,
        Order,
        OrderMessage,
        PaymentTransaction,
        Quotation,
        QuoteRequest,
        Review,
        SavedListing,
    )

    profile = getattr(user, "manufacturer_profile", None)
    order_scope = Q(buyer=user)
    if profile is not None:
        order_scope |= Q(manufacturer=profile)

    orders = list(
        Order.objects.filter(order_scope)
        .select_related("listing", "manufacturer")
        .order_by("pk")
    )
    order_ids = [order.pk for order in orders]

    quote_requests = QuoteRequest.objects.filter(buyer=user).select_related(
        "listing", "listing__manufacturer"
    )
    if profile is not None:
        quotations = Quotation.objects.filter(
            Q(quote_request__listing__manufacturer=profile)
            | Q(quote_request__buyer=user)
        ).select_related("quote_request", "quote_request__listing")
        listings = CapacityListing.objects.filter(manufacturer=profile).order_by("pk")
    else:
        quotations = Quotation.objects.filter(
            quote_request__buyer=user
        ).select_related("quote_request", "quote_request__listing")
        listings = CapacityListing.objects.none()

    payments = PaymentTransaction.objects.filter(
        Q(buyer=user) | Q(milestone__order_id__in=order_ids)
    ).select_related("milestone", "milestone__order").order_by("pk")

    return {
        "exported_at": timezone.now().isoformat(),
        "account": {
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "phone": user.phone,
            "role": user.role,
            "date_joined": _iso(user.date_joined),
            "terms_accepted_at": _iso(user.terms_accepted_at),
            "terms_version": user.terms_version,
            "privacy_acknowledged_at": _iso(user.privacy_acknowledged_at),
            "privacy_policy_version": user.privacy_policy_version,
        },
        "manufacturer_profile": (
            {
                "business_name": profile.business_name,
                "description": profile.description,
                "city": profile.city,
                "state": profile.state,
                "pincode": profile.pincode,
                "is_verified": profile.is_verified,
                "kyc_status": profile.kyc_status,
            }
            if profile is not None
            else None
        ),
        "listings": [
            {
                "title": listing.title,
                "category": listing.category,
                "description": listing.description,
                "machine_type": listing.machine_type,
                "materials": listing.materials,
                "technical_capabilities": listing.technical_capabilities,
                "minimum_quantity": listing.minimum_quantity,
                "price_per_unit": str(listing.price_per_unit),
                "batch_price": (
                    str(listing.batch_price)
                    if listing.batch_price is not None
                    else None
                ),
                "production_days": listing.production_days,
                "available_capacity": listing.available_capacity,
                "capacity_period": listing.capacity_period,
                "cluster": listing.cluster,
                "availability_status": listing.availability_status,
                "is_active": listing.is_active,
                "image_storage_name": listing.image.name if listing.image else "",
            }
            for listing in listings
        ],
        "quote_requests": [
            {
                "request_id": quote.pk,
                "listing_title": quote.listing.title,
                "quantity": quote.quantity,
                "requirements": quote.requirements,
                "delivery_location": quote.delivery_location,
                "status": quote.status,
                "created_at": _iso(quote.created_at),
            }
            for quote in quote_requests.order_by("pk")
        ],
        "quotations": [
            {
                "request_id": quotation.quote_request_id,
                "listing_title": quotation.quote_request.listing.title,
                "price_per_unit": str(quotation.price_per_unit),
                "quantity": quotation.quantity,
                "production_days": quotation.production_days,
                "message": (
                    quotation.message
                    if profile is not None
                    and quotation.quote_request.listing.manufacturer_id == profile.pk
                    else None
                ),
                "status": quotation.status,
                "created_at": _iso(quotation.created_at),
                "responded_at": _iso(quotation.responded_at),
            }
            for quotation in quotations.order_by("pk")
        ],
        "orders": [
            {
                "order_id": order.pk,
                "source": order.source,
                "status": order.status,
                "listing_title": order.listing.title,
                "manufacturer_business_name": order.manufacturer.business_name,
                "buyer_supplied_details": (
                    {
                        key: order.specifications_snapshot[key]
                        for key in ("requirements", "delivery_location")
                        if key in (order.specifications_snapshot or {})
                    }
                    if order.buyer_id == user.pk
                    else None
                ),
                "quantity": order.quantity,
                "agreed_unit_price": str(order.agreed_unit_price),
                "total_amount": str(order.total_amount),
                "agreed_production_days": order.agreed_production_days,
                "created_at": _iso(order.created_at),
                "updated_at": _iso(order.updated_at),
            }
            for order in orders
        ],
        "milestones": [
            {
                "order_id": milestone.order_id,
                "title": milestone.title,
                "percentage": milestone.percentage,
                "amount": str(milestone.amount) if milestone.amount is not None else None,
                "status": milestone.status,
                "funding_status": milestone.funding_status,
                "funded_at": _iso(milestone.funded_at),
                "released_at": _iso(milestone.released_at),
                "started_at": _iso(milestone.started_at),
                "completed_at": _iso(milestone.completed_at),
                "approved_at": _iso(milestone.approved_at),
            }
            for milestone in Milestone.objects.filter(order_id__in=order_ids)
            .order_by("order_id", "pk")
        ],
        "payments": [
            {
                "order_id": payment.milestone.order_id,
                "milestone_title": payment.milestone.title,
                "amount": str(payment.amount),
                "currency": payment.currency,
                "status": payment.status,
                "created_at": _iso(payment.created_at),
                "updated_at": _iso(payment.updated_at),
                "captured_at": _iso(payment.captured_at),
            }
            for payment in payments
        ],
        "order_messages": [
            {
                "order_id": message.order_id,
                "body": message.body,
                "created_at": _iso(message.created_at),
            }
            for message in OrderMessage.objects.filter(
                order_id__in=order_ids,
            ).order_by("order_id", "pk")
        ],
        "reviews_authored": [
            {
                "order_id": review.order_id,
                "ratings": {
                    "quality": review.quality_rating,
                    "timeliness": review.timeliness_rating,
                    "communication": review.communication_rating,
                    "overall": review.overall_rating,
                },
                "comment": review.comment,
                "created_at": _iso(review.created_at),
            }
            for review in Review.objects.filter(buyer=user).order_by("pk")
        ],
        "saved_listings": [
            {"title": saved.listing.title, "saved_at": _iso(saved.created_at)}
            for saved in SavedListing.objects.filter(buyer=user)
            .select_related("listing")
            .order_by("pk")
        ],
        "notifications": [
            {
                "destination": notification.destination,
                "is_read": notification.is_read,
                "created_at": _iso(notification.created_at),
            }
            for notification in Notification.objects.filter(recipient=user).order_by("pk")
        ],
    }


class ActiveWorkflowError(Exception):
    """Account closure must wait until open marketplace obligations resolve."""


@transaction.atomic
def close_account(user_id, password):
    """Anonymize an eligible account while preserving transaction relations."""
    from marketplace.models import (
        CapacityListing,
        ManufacturerProfile,
        Notification,
        Order,
        OrderMessage,
        QuoteRequest,
        Milestone,
        Review,
        SavedListing,
    )

    user = User.objects.select_for_update().get(pk=user_id)
    if not user.is_active:
        return False
    if user.is_staff or user.is_superuser or not user.check_password(password):
        return False

    # Workflow creators lock participant User rows before creating an Order,
    # QuoteRequest, or Quotation. Holding this lock therefore closes the
    # eligibility-check/create race without taking Order locks in the reverse
    # order used by milestone/payment transitions.
    if has_active_workflows(user):
        raise ActiveWorkflowError

    old_role = user.role
    profile = ManufacturerProfile.objects.select_for_update().filter(user=user).first()
    replacement_id = uuid4().hex

    user.username = f"closed-{replacement_id}"
    user.email = f"closed-{replacement_id}@invalid.local"
    user.first_name = ""
    user.last_name = ""
    user.phone = ""
    user.is_active = False
    user.last_login = None
    user.terms_accepted_at = None
    user.privacy_acknowledged_at = None
    user.terms_version = ""
    user.privacy_policy_version = ""
    user.set_unusable_password()
    user.save(
        update_fields=(
            "username",
            "email",
            "first_name",
            "last_name",
            "phone",
            "is_active",
            "last_login",
            "terms_accepted_at",
            "privacy_acknowledged_at",
            "terms_version",
            "privacy_policy_version",
            "password",
        )
    )

    if old_role == User.Role.MANUFACTURER and profile is not None:
        profile.business_name = "Closed manufacturer account"
        profile.description = ""
        profile.city = ""
        profile.state = ""
        profile.pincode = ""
        profile.is_verified = False
        profile.save(
            update_fields=(
                "business_name",
                "description",
                "city",
                "state",
                "pincode",
                "is_verified",
            )
        )
        CapacityListing.objects.filter(manufacturer=profile).update(
            is_active=False,
            availability_status=CapacityListing.AvailabilityStatus.PAUSED,
        )

    if old_role == User.Role.BUYER:
        QuoteRequest.objects.filter(buyer=user).update(
            requirements="",
            delivery_location="",
        )
        Review.objects.filter(buyer=user).update(comment="")
        Milestone.objects.filter(order__buyer=user).update(buyer_feedback="")
        for order in Order.objects.filter(buyer=user).only(
            "pk", "specifications_snapshot"
        ):
            snapshot = dict(order.specifications_snapshot or {})
            if snapshot.pop("delivery_location", None) is not None:
                order.specifications_snapshot = snapshot
                order.save(update_fields=("specifications_snapshot",))

    OrderMessage.objects.filter(sender=user).update(
        body="[Message content removed at account closure]"
    )
    SavedListing.objects.filter(buyer=user).delete()
    Notification.objects.filter(recipient=user).delete()

    event_id = uuid4().hex
    transaction.on_commit(
        lambda: logger.info(
            "Account closure completed event_id=%s",
            event_id,
        )
    )
    return True
