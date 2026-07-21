from django.urls import path

from . import views

app_name = 'links'

urlpatterns = [
    path('', views.my_links_view, name='my_links'),
    path('create/', views.create_link_view, name='create'),
    path('<str:link_id>/', views.link_details_view, name='detail'),
    path('<str:link_id>/qr/', views.link_qr_code_view, name='qr_code'),
    path('<str:link_id>/disable/', views.disable_link_view, name='disable'),
    path('claim/<str:link_id>/', views.claim_page_view, name='claim'),
]
