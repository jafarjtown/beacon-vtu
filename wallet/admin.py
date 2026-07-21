from django.contrib import admin
from .models import Wallet, FundingRequest


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ['user', 'balance', 'total_funded', 'total_spent', 'is_active', 'updated_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['user__email', 'user__username']
    readonly_fields = ['total_funded', 'total_spent', 'created_at', 'updated_at']


@admin.register(FundingRequest)
class FundingRequestAdmin(admin.ModelAdmin):
    list_display = ['request_id', 'user', 'amount', 'status', 'reference_number', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['request_id', 'user__email', 'reference_number']
    readonly_fields = ['request_id', 'reference_number', 'created_at']
    date_hierarchy = 'created_at'
