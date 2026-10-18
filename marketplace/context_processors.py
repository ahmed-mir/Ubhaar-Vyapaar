from .models import Notification
from django.conf import settings


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
        "legal_entity_name": settings.LEGAL_ENTITY_NAME,
        "legal_contact_email": settings.LEGAL_CONTACT_EMAIL,
        "legal_contact_label": settings.LEGAL_CONTACT_LABEL,
        "canonical_url": f"{settings.SITE_ORIGIN}{request.path}",
    }
