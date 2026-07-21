import pytz
from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin


class TimezoneMiddleware(MiddlewareMixin):
    """Middleware to handle user timezone preferences"""
    
    def process_request(self, request):
        if request.user.is_authenticated and hasattr(request.user, 'profile'):
            tz = request.user.profile.timezone
            if tz:
                timezone.activate(pytz.timezone(tz))
            else:
                timezone.deactivate()
        else:
            timezone.deactivate()
