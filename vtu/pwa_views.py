"""
Serves sw.js at the SITE ROOT — deliberately NOT under /static/.

A service worker's default scope is limited to the directory it's served
from and everything below it. Since the rest of the static files (CSS,
JS, icons) correctly live under STATIC_URL (e.g. /static/), sw.js was
being registered from /static/sw.js — which meant its scope defaulted to
/static/* only. It could cache CSS/JS fine, but it never actually saw
navigation requests to real pages like /dashboard/ or /buy/, so the
"fall back to offline.html when the network is down" logic never fired
for anything that mattered. Serving this one file from the root instead
gives it scope over the whole origin, which is what registering it with
{ scope: '/' } in pwa-register.js actually expects.

Wire this into your PROJECT-level urls.py (the one with ROOT_URLCONF),
not an app's urls.py — it needs to live at the literal root path:

    from myproject.pwa_views import service_worker_view

    urlpatterns = [
        path('sw.js', service_worker_view, name='service_worker'),
        ...
    ]
"""
import os

from django.conf import settings
from django.contrib.staticfiles import finders
from django.http import HttpResponse, Http404


def service_worker_view(request):
    # Checks STATIC_ROOT first (the production path, after collectstatic
    # has run), then falls back to Django's static finders (the dev-time
    # mechanism, works before collectstatic has ever been run).
    candidates = []
    if getattr(settings, "STATIC_ROOT", None):
        candidates.append(os.path.join(settings.STATIC_ROOT, "sw.js"))
    found = finders.find("sw.js")
    if found:
        candidates.append(found)

    for path in candidates:
        if path and os.path.isfile(path):
            with open(path, "rb") as f:
                content = f.read()
            response = HttpResponse(content, content_type="application/javascript")
            # Belt-and-suspenders: explicitly declare root scope even
            # though serving from the root path already implies it —
            # protects against this ever being moved behind a prefix
            # (a reverse proxy rule, a URL refactor) without anyone
            # noticing the scope silently narrowed again.
            response["Service-Worker-Allowed"] = "/"
            # Service workers must never be cached by the browser/CDN —
            # an old cached sw.js can keep serving stale offline logic
            # indefinitely, which defeats the point of ever updating it.
            response["Cache-Control"] = "no-cache"
            return response

    raise Http404("sw.js not found — run collectstatic, or check STATICFILES_DIRS")
