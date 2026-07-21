from django.urls import path
from . import views

app_name = 'services'

urlpatterns = [
    path('', views.services_list_view, name='list'),
    path('<str:category>/', views.service_detail_view, name='detail'),
    path('api/validate/', views.validate_phone, name='validate'),
    path('api/purchase/', views.process_purchase, name='purchase'),
]
