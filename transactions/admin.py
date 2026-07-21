from django.contrib import admin
from .models import Transaction

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ['transaction_id', 'user', 'transaction_type', 'amount', 'status', 'recipient', 'created_at']
    list_filter = ['status', 'transaction_type', 'created_at']
    search_fields = ['transaction_id', 'user__email', 'reference_number', 'recipient']
    readonly_fields = ['transaction_id', 'reference_number', 'created_at', 'updated_at']
    date_hierarchy = 'created_at'
