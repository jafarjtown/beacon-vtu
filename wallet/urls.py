from django.urls import path
from . import views

app_name = 'wallet'

urlpatterns = [
    path('', views.wallet_view, name='wallet'),
    path('fund/', views.fund_wallet_view, name='fund'),
    path('fund/<str:request_id>/', views.funding_detail_view, name='funding_detail'),
    path('fund/<str:request_id>/confirm/', views.confirm_payment_view, name='confirm_payment'),
    path('history/', views.funding_history_view, name='funding_history'),
]
