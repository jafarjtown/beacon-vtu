from django.contrib import admin
from django.utils.html import format_html

from . import services as link_services
from .models import ClaimLink, ClaimSlot

STATUS_COLORS = {
    ClaimLink.Status.ACTIVE: '#00A86B',
    ClaimLink.Status.DISABLED: '#D64545',
    ClaimLink.Status.EXPIRED: '#B8860B',
    ClaimLink.Status.COMPLETED: '#4B4FE0',
}


class ClaimSlotInline(admin.TabularInline):
    """Read-only view of a link's slots from the ClaimLink change page.
    Slots are only ever created/claimed through services.py, so nothing
    here is editable — this is for inspection, not data entry."""
    model = ClaimSlot
    extra = 0
    can_delete = False
    fields = ('id', 'masked_phone_display', 'is_claimed', 'claimed_at', 'ip_address')
    readonly_fields = ('id', 'masked_phone_display', 'is_claimed', 'claimed_at', 'ip_address')

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description='Claimed by')
    def masked_phone_display(self, obj):
        return obj.masked_phone or '—'


@admin.register(ClaimLink)
class ClaimLinkAdmin(admin.ModelAdmin):
    list_display = (
        'link_id', 'user', 'service_type', 'item_summary', 'slots_summary',
        'amount_display', 'status_badge', 'expiry_display', 'created_at',
    )
    list_filter = ('status', 'service_type', 'created_at', 'network')
    search_fields = ('link_id', 'user__email', 'user__username', 'provider', 'plan_name')
    date_hierarchy = 'created_at'
    list_select_related = ('user', 'network')
    list_per_page = 50
    ordering = ('-created_at',)
    actions = ['disable_and_refund_links']
    inlines = [ClaimSlotInline]

    readonly_fields = (
        'link_id', 'user', 'service_type', 'provider', 'plan_name', 'network', 'plan',
        'amount_per_slot', 'total_slots', 'used_slots', 'remaining_slots_display',
        'total_reserved_display', 'refundable_amount_display', 'status_badge',
        'share_url_display', 'created_at', 'updated_at',
    )

    fieldsets = (
        ('Link', {
            'fields': ('link_id', 'user', 'status_badge', 'share_url_display'),
        }),
        ('Service', {
            'fields': ('service_type', 'provider', 'plan_name', 'network', 'plan'),
        }),
        ('Slots & value', {
            'fields': (
                'amount_per_slot', 'total_slots', 'used_slots',
                'remaining_slots_display', 'total_reserved_display', 'refundable_amount_display',
            ),
        }),
        ('Expiry & notes', {
            # These two are the only fields admins can actually edit — they
            # don't touch wallet balances, so changing them here is safe.
            'fields': ('expiry_date', 'notes'),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
        }),
    )

    def has_add_permission(self, request):
        # Creating a link means debiting a wallet and reserving slots —
        # that logic lives in services.create_airtime_link /
        # create_data_link. Admin add-forms bypass it entirely, so it's
        # disabled here rather than risk an unbacked link being created.
        return False

    def has_delete_permission(self, request, obj=None):
        # Links are a financial record (they represent reserved wallet
        # funds). Disable + refund via the action below instead of
        # deleting, so the audit trail stays intact.
        return False

    @admin.display(description='Item')
    def item_summary(self, obj):
        return obj.item_label

    @admin.display(description='Slots')
    def slots_summary(self, obj):
        return f"{obj.used_slots} / {obj.total_slots}"

    @admin.display(description='Per slot')
    def amount_display(self, obj):
        return f"₦{obj.amount_per_slot:,.2f}"

    @admin.display(description='Status')
    def status_badge(self, obj):
        color = STATUS_COLORS.get(obj.status, '#888888')
        return format_html(
            '<span style="color:{}; font-weight:600;">{}</span>',
            color, obj.get_status_display(),
        )

    @admin.display(description='Expires')
    def expiry_display(self, obj):
        if not obj.expiry_date:
            return 'Never'
        return obj.expiry_date.strftime('%d %b %Y, %H:%M')

    @admin.display(description='Remaining slots')
    def remaining_slots_display(self, obj):
        return obj.remaining_slots

    @admin.display(description='Total reserved')
    def total_reserved_display(self, obj):
        return f"₦{obj.total_reserved:,.2f}"

    @admin.display(description='Refundable if disabled now')
    def refundable_amount_display(self, obj):
        return f"₦{obj.refundable_amount:,.2f}"

    @admin.display(description='Share URL')
    def share_url_display(self, obj):
        return format_html('<a href="{0}" target="_blank">{0}</a>', obj.share_url)

    @admin.action(description='Disable selected links and refund unclaimed slots')
    def disable_and_refund_links(self, request, queryset):
        # Goes through services.disable_link so the refund + transaction
        # record are created the same way a user-triggered disable would
        # be — no separate admin-only code path for money movement.
        disabled_count = 0
        total_refunded = 0
        skipped_count = 0

        for link in queryset:
            if link.status != ClaimLink.Status.ACTIVE:
                skipped_count += 1
                continue
            refunded = link_services.disable_link(link=link)
            disabled_count += 1
            total_refunded += refunded

        if disabled_count:
            self.message_user(
                request,
                f"Disabled {disabled_count} link(s). ₦{total_refunded:,.2f} refunded in total.",
            )
        if skipped_count:
            self.message_user(
                request,
                f"Skipped {skipped_count} link(s) that were already inactive.",
            )


@admin.register(ClaimSlot)
class ClaimSlotAdmin(admin.ModelAdmin):
    """Mainly useful for support/fraud lookups — e.g. finding every slot a
    given phone number has claimed across all links."""
    list_display = ('id', 'link', 'masked_phone_display', 'is_claimed', 'claimed_at', 'ip_address')
    list_filter = ('is_claimed', 'claimed_at')
    search_fields = ('claimed_by', 'ip_address', 'link__link_id')
    list_select_related = ('link',)
    readonly_fields = ('link', 'claimed_by', 'claimed_at', 'is_claimed', 'ip_address', 'user_agent')
    list_per_page = 50

    def has_add_permission(self, request):
        # Slots are only ever created as a side effect of ClaimLink
        # creation (see services._create_link).
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description='Claimed by')
    def masked_phone_display(self, obj):
        return obj.masked_phone or '—'
