from django.contrib import admin
from django.utils.html import format_html

from . import services as family_services
from .models import (
    Family,
    FamilyMembership,
    FamilyWallet,
    FamilyWalletFunding,
    MemberServicePreset,
    PurchaseRequest,
    ScheduledPurchase,
    ScheduledPurchaseRun,
    SpendingLimit,
)

ROLE_COLORS = {
    FamilyMembership.Role.OWNER: '#FFB020',
    FamilyMembership.Role.ADMIN: '#7C6CFF',
    FamilyMembership.Role.MEMBER: '#00D9A3',
    FamilyMembership.Role.VIEWER: '#6B7098',
}


class FamilyMembershipInline(admin.TabularInline):
    model = FamilyMembership
    extra = 0
    fields = ('user', 'role', 'status', 'joined_at')
    readonly_fields = ('joined_at',)
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        # Adding a member means a permission check against the inviter —
        # that logic lives in services.invite_member. Admin add-forms
        # bypass it, so membership creation is disabled here.
        return False


@admin.register(Family)
class FamilyAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'member_count', 'wallet_balance_display', 'created_at')
    search_fields = ('name', 'owner__email', 'owner__username')
    list_select_related = ('owner',)
    date_hierarchy = 'created_at'
    inlines = [FamilyMembershipInline]
    readonly_fields = ('owner', 'created_at', 'updated_at')

    @admin.display(description='Members')
    def member_count(self, obj):
        return obj.active_members.count()

    @admin.display(description='Wallet balance')
    def wallet_balance_display(self, obj):
        try:
            return f"₦{obj.wallet.balance:,.2f}"
        except FamilyWallet.DoesNotExist:
            return "—"

    def has_add_permission(self, request):
        # Creating a family also means creating its wallet and the
        # owner's membership in one step — see services.create_family.
        # An admin add-form would create a Family with neither.
        return False


@admin.register(FamilyMembership)
class FamilyMembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'family', 'role_badge', 'status', 'invited_at', 'joined_at')
    list_filter = ('role', 'status')
    search_fields = ('user__email', 'user__username', 'family__name')
    list_select_related = ('user', 'family')
    readonly_fields = ('invited_by', 'invited_at', 'joined_at', 'removed_at')

    @admin.display(description='Role')
    def role_badge(self, obj):
        color = ROLE_COLORS.get(obj.role, '#888')
        return format_html('<span style="color:{}; font-weight:600;">{}</span>', color, obj.get_role_display())


@admin.register(FamilyWallet)
class FamilyWalletAdmin(admin.ModelAdmin):
    list_display = ('family', 'balance', 'total_funded', 'total_spent', 'updated_at')
    search_fields = ('family__name',)
    readonly_fields = ('family', 'balance', 'total_funded', 'total_spent', 'created_at', 'updated_at')

    def has_add_permission(self, request):
        return False  # created only via services.create_family

    def has_delete_permission(self, request, obj=None):
        return False  # financial record


@admin.register(FamilyWalletFunding)
class FamilyWalletFundingAdmin(admin.ModelAdmin):
    list_display = ('family', 'funded_by', 'amount', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('family__name', 'funded_by__email', 'funded_by__username')
    list_select_related = ('family', 'funded_by')
    readonly_fields = ('family', 'funded_by', 'amount', 'created_at')

    def has_add_permission(self, request):
        return False  # created only via services.fund_family_wallet

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MemberServicePreset)
class MemberServicePresetAdmin(admin.ModelAdmin):
    list_display = ('label', 'membership', 'service_type', 'recipient_identifier', 'provider')
    list_filter = ('service_type',)
    search_fields = ('label', 'recipient_identifier', 'membership__user__email')
    list_select_related = ('membership', 'membership__user', 'provider')


@admin.register(SpendingLimit)
class SpendingLimitAdmin(admin.ModelAdmin):
    list_display = ('membership', 'daily_limit', 'weekly_limit', 'monthly_limit', 'updated_at')
    search_fields = ('membership__user__email', 'membership__family__name')
    list_select_related = ('membership', 'membership__user')


class ScheduledPurchaseRunInline(admin.TabularInline):
    model = ScheduledPurchaseRun
    extra = 0
    fields = ('status', 'amount', 'reference', 'note', 'ran_at')
    readonly_fields = fields
    can_delete = False
    ordering = ('-ran_at',)

    def has_add_permission(self, request, obj=None):
        return False  # only ever created by services._run_single_schedule


@admin.register(ScheduledPurchase)
class ScheduledPurchaseAdmin(admin.ModelAdmin):
    list_display = ('preset', 'beneficiary', 'amount', 'frequency', 'next_run_at', 'is_active')
    list_filter = ('frequency', 'is_active')
    search_fields = ('preset__label', 'beneficiary__user__email', 'family__name')
    list_select_related = ('preset', 'beneficiary', 'beneficiary__user', 'family')
    inlines = [ScheduledPurchaseRunInline]
    readonly_fields = (
        'family', 'beneficiary', 'preset', 'amount', 'frequency',
        'day_of_week', 'day_of_month', 'created_by', 'created_at', 'updated_at',
    )
    # is_active and next_run_at stay editable — pausing a schedule or
    # nudging its next run date doesn't touch any money, unlike every
    # other field here which was set by services.create_scheduled_purchase
    # alongside validation this admin form would otherwise bypass.
    fields = readonly_fields + ('is_active', 'next_run_at')

    def has_add_permission(self, request):
        return False


@admin.register(ScheduledPurchaseRun)
class ScheduledPurchaseRunAdmin(admin.ModelAdmin):
    list_display = ('schedule', 'status_badge', 'amount', 'reference', 'ran_at')
    list_filter = ('status', 'ran_at')
    search_fields = ('schedule__preset__label', 'reference')
    list_select_related = ('schedule', 'schedule__preset')
    readonly_fields = ('schedule', 'status', 'amount', 'reference', 'note', 'ran_at')

    @admin.display(description='Status')
    def status_badge(self, obj):
        color = '#00D9A3' if obj.status == obj.Status.SUCCESS else '#FF6B6B'
        return format_html('<span style="color:{}; font-weight:600;">{}</span>', color, obj.get_status_display())

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False  # audit trail


@admin.register(PurchaseRequest)
class PurchaseRequestAdmin(admin.ModelAdmin):
    list_display = ('requested_by', 'preset', 'amount', 'status_badge', 'created_at', 'reviewed_by')
    list_filter = ('status', 'created_at')
    search_fields = ('requested_by__user__email', 'preset__label', 'family__name')
    list_select_related = ('requested_by', 'requested_by__user', 'preset', 'family', 'reviewed_by')
    actions = ['approve_requests', 'reject_requests']
    readonly_fields = (
        'family', 'requested_by', 'preset', 'amount', 'note',
        'reviewed_by', 'reviewed_at', 'reference', 'created_at',
    )
    fields = readonly_fields + ('status', 'rejection_reason')

    @admin.display(description='Status')
    def status_badge(self, obj):
        colors = {
            obj.Status.PENDING: '#FFB020',
            obj.Status.APPROVED: '#00D9A3',
            obj.Status.REJECTED: '#FF6B6B',
        }
        return format_html(
            '<span style="color:{}; font-weight:600;">{}</span>',
            colors.get(obj.status, '#888'), obj.get_status_display(),
        )

    def has_add_permission(self, request):
        return False

    @admin.action(description='Approve selected requests')
    def approve_requests(self, request, queryset):
        # Routed through services.approve_purchase_request so approving
        # from the admin debits the wallet and delivers the purchase the
        # same way approving from the app does — no separate admin-only
        # path for money movement.
        approved, failed = 0, 0
        for req in queryset.filter(status=PurchaseRequest.Status.PENDING):
            try:
                family_services.approve_purchase_request(request=req, reviewed_by=request.user)
                approved += 1
            except family_services.FamilyError as exc:
                failed += 1
                self.message_user(request, f"Could not approve request #{req.id}: {exc}", level='ERROR')
        if approved:
            self.message_user(request, f"Approved {approved} request(s).")

    @admin.action(description='Reject selected requests')
    def reject_requests(self, request, queryset):
        rejected, failed = 0, 0
        for req in queryset.filter(status=PurchaseRequest.Status.PENDING):
            try:
                family_services.reject_purchase_request(
                    request=req, reviewed_by=request.user, reason='Rejected via admin.',
                )
                rejected += 1
            except family_services.FamilyError as exc:
                failed += 1
                self.message_user(request, f"Could not reject request #{req.id}: {exc}", level='ERROR')
        if rejected:
            self.message_user(request, f"Rejected {rejected} request(s).")
