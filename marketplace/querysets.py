"""Shared authorization-scoped querysets for marketplace records."""

from accounts.models import User

from .models import Order


def order_queryset_for_user(user):
    """Return exactly the Orders the current role may access in the UI."""
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

    if user.role == User.Role.BUYER:
        return orders.filter(buyer=user)

    if user.role == User.Role.MANUFACTURER:
        return orders.filter(manufacturer__user=user)

    return Order.objects.none()
