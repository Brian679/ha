from .models import Notification


def portal_context(request):
    if request.user.is_authenticated:
        return {"unread_notification_count": Notification.objects.filter(user=request.user, read_at__isnull=True).count()}
    return {"unread_notification_count": 0}
