from .models import Notification
from django.conf import settings


PRIVATE_INDEXING_URL_NAMES = {
    "login",
    "logout",
    "register",
    "register_manufacturer",
    "password_change",
    "password_change_done",
    "password_reset",
    "password_reset_done",
    "password_reset_confirm",
    "password_reset_complete",
    "my_quote_requests",
    "buyer_dashboard",
    "buyer_orders",
    "manufacturer_dashboard",
    "manufacturer_orders",
    "order_detail",
    "send_order_message",
    "review_order",
    "mark_milestone_complete",
    "fund_milestone",
    "start_milestone",
    "respond_to_milestone",
    "release_milestone_payment",
    "update_quote_status",
    "request_quote",
    "create_listing",
    "my_listings",
    "edit_listing",
    "send_quotation",
    "respond_to_quotation",
    "saved_listings",
    "save_listing",
    "remove_saved_listing",
    "edit_business_profile",
    "notifications",
    "open_notification",
    "mark_all_notifications_read",
}


def notification_count(request):
    unread_count = 0

    if request.user.is_authenticated:
        unread_count = Notification.objects.filter(
            recipient=request.user,
            is_read=False,
        ).count()

    return {
        "unread_notification_count": unread_count,
    }


def platform_readiness(request):
    return {
        "google_analytics_id": settings.GOOGLE_ANALYTICS_ID,
        "google_site_verification": settings.GOOGLE_SITE_VERIFICATION,
        "bing_site_verification": settings.BING_SITE_VERIFICATION,
        "site_origin": settings.SITE_ORIGIN,
        "allow_indexing": settings.ALLOW_INDEXING,
        "private_indexing_url_names": PRIVATE_INDEXING_URL_NAMES,
        "legal_entity_name": settings.LEGAL_ENTITY_NAME,
        "legal_contact_email": settings.LEGAL_CONTACT_EMAIL,
        "legal_contact_label": settings.LEGAL_CONTACT_LABEL,
        "canonical_url": f"{settings.SITE_ORIGIN}{request.path}",
    }
