from django.urls import path

from . import views

app_name = 'beacon_family'

urlpatterns = [
    path('', views.family_list_view, name='list'),
    path('create/', views.create_family_view, name='create'),
    path('invites/<int:membership_id>/accept/', views.accept_invite_view, name='accept_invite'),

    path('<int:family_id>/', views.family_dashboard_view, name='dashboard'),
    path('<int:family_id>/fund/', views.fund_wallet_view, name='fund_wallet'),

    path('<int:family_id>/members/', views.members_view, name='members'),
    path('<int:family_id>/members/invite/', views.invite_member_view, name='invite_member'),
    path('<int:family_id>/members/<int:membership_id>/remove/', views.remove_member_view, name='remove_member'),
    path('<int:family_id>/members/<int:membership_id>/limits/', views.spending_limits_view, name='spending_limits'),

    path('<int:family_id>/presets/', views.presets_view, name='presets'),
    path('<int:family_id>/presets/create/', views.create_preset_view, name='create_preset'),

    path('<int:family_id>/schedules/', views.schedules_view, name='schedules'),
    path('<int:family_id>/schedules/create/', views.create_schedule_view, name='create_schedule'),
    path('<int:family_id>/schedules/<int:schedule_id>/toggle/', views.toggle_schedule_view, name='toggle_schedule'),

    path('<int:family_id>/requests/', views.requests_view, name='requests'),
    path('<int:family_id>/requests/create/', views.create_request_view, name='create_request'),
    path('<int:family_id>/requests/<int:request_id>/approve/', views.approve_request_view, name='approve_request'),
    path('<int:family_id>/requests/<int:request_id>/reject/', views.reject_request_view, name='reject_request'),
]
