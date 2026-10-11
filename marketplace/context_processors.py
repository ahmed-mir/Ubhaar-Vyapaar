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
    }
