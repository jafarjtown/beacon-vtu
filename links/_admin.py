from django.contrib import admin
from .models import ClaimLink, ClaimSlot

class ClaimSlotInline(admin.TabularInline):
    model = ClaimSlot
    extra = 0
    readonly_fields = ['claimed_at', 'ip_address']

@admin.register(ClaimLink)
class ClaimLinkAdmin(admin.ModelAdmin):
    list_display = ['link_id', 'user', 'service_type', 'plan_name', 'amount', 'used_slots', 'total_slots', 'status', 'expiry_date']
    list_filter = ['status', 'service_type', 'created_at']
    search_fields = ['link_id', 'user__email', 'plan_name']
    readonly_fields = ['link_id', 'created_at']
    inlines = [ClaimSlotInline]

@admin.register(ClaimSlot)
class ClaimSlotAdmin(admin.ModelAdmin):
    list_display = ['id', 'link', 'claimed_by', 'is_claimed', 'claimed_at']
    list_filter = ['is_claimed']
