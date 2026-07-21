from .models import SiteSettings
from notifications.models import Notification


def site_settings(request):
    """Add site settings to all templates"""
    return {
        'site_settings': SiteSettings.load(),
        'theme': request.session.get('theme', 'light'),
    }


def notifications_count(request):
    """Add unread notification count to all templates"""
    count = 0
    if request.user.is_authenticated:
        count = Notification.objects.filter(user=request.user, is_read=False).count()
    return {'unread_notifications': count}