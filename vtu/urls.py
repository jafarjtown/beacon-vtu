"""VTU Project URL Configuration"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView
from django.shortcuts import render
from services import vtu
from .pwa_views import service_worker_view

# Custom error handlers
handler404 = 'core.views.custom_404'
handler500 = 'core.views.custom_500'

urlpatterns = [
    path('sw.js', service_worker_view, name='service_worker'),
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
    path('accounts/', include('authentication.urls')),
    path('dashboard/', include('dashboard.urls')),
    path('wallet/', include('wallet.urls')),
    path('transactions/', include('transactions.urls')),
    path('services/', include('services.urls')),
    path('links/', include('links.urls')),
    path('notifications/', include('notifications.urls')),
    path('commons/', include('commons.urls')),
    path('api/data/variations/', vtu.data_plans, name="api-data-plans")
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
