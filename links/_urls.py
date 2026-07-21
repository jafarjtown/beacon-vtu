from django.urls import path
from . import views

app_name = 'links'

urlpatterns = [
    path('', views.my_links_view, name='my_links'),
    path('create/', views.create_link_view, name='create'),
    path('<str:link_id>/', views.link_detail_view, name='detail'),
    path('<str:link_id>/toggle/', views.toggle_link_view, name='toggle'),
    path('claim/<str:link_id>/', views.claim_page_view, name='claim'),
]
