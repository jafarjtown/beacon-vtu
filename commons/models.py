import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

User = get_user_model()


class Family(models.Model):
    """A household/group using a shared wallet. The creator becomes the
    first FamilyMembership with role=OWNER — see services.create_family."""

    name = models.CharField(max_length=100)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='owned_families')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'families'
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    @property
    def active_members(self):
        return self.memberships.filter(status=FamilyMembership.Status.ACTIVE)


class FamilyMembership(models.Model):
    """The join between a User and a Family, carrying their role. This is
    where permission checks live — see the can_* properties below, which
    map directly onto the permission table in the product spec. One user
    can belong to a family only once (enforced by unique_together)."""

    class Role(models.TextChoices):
        OWNER = 'owner', 'Owner'
        ADMIN = 'admin', 'Admin'
        MEMBER = 'member', 'Member'
        VIEWER = 'viewer', 'Viewer'

    class Status(models.TextChoices):
        INVITED = 'invited', 'Invited'
        ACTIVE = 'active', 'Active'
        REMOVED = 'removed', 'Removed'

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='family_memberships')
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBER)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.INVITED)

    invited_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='family_invites_sent',
    )
    invited_at = models.DateTimeField(auto_now_add=True)
    joined_at = models.DateTimeField(null=True, blank=True)
    removed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [('family', 'user')]
        ordering = ['-role', 'invited_at']

    def __str__(self):
        return f"{self.user} in {self.family} ({self.get_role_display()})"

    # ---------- permissions, mapped directly from the product spec ----------
    # NOTE: the spec's permission table lists "Fund wallet" only under
    # Owner, but its own worked example shows non-owners funding the
    # wallet too. Resolved here as: funding is open to any ACTIVE member
    # (it only adds money, never spends it, so it's low-risk to leave
    # permissive) — everything that spends or reorganizes the family
    # follows the table exactly as written.

    @property
    def is_active(self):
        return self.status == self.Status.ACTIVE

    @property
    def can_fund_wallet(self):
        return self.is_active and self.role in (self.Role.OWNER, self.Role.ADMIN, self.Role.MEMBER)

    @property
    def can_add_members(self):
        return self.is_active and self.role in (self.Role.OWNER, self.Role.ADMIN)

    @property
    def can_remove_members(self):
        return self.is_active and self.role == self.Role.OWNER

    @property
    def can_create_schedule(self):
        return self.is_active and self.role in (self.Role.OWNER, self.Role.ADMIN)

    @property
    def can_manage_services(self):
        return self.is_active and self.role in (self.Role.OWNER, self.Role.ADMIN)

    @property
    def can_set_spending_limits(self):
        return self.is_active and self.role == self.Role.OWNER

    @property
    def can_approve_requests(self):
        return self.is_active and self.role == self.Role.OWNER

    @property
    def can_request_purchase(self):
        return self.is_active and self.role in (self.Role.OWNER, self.Role.ADMIN, self.Role.MEMBER)

    @property
    def can_view_all_transactions(self):
        return self.is_active and self.role in (self.Role.OWNER, self.Role.ADMIN)


class FamilyWallet(models.Model):
    """The shared pot. Deliberately a separate model from the personal
    Wallet, not a reuse of it — a family wallet has different semantics
    (many funders, permissioned spending, per-member limits) that don't
    fit the personal-wallet shape. debit()/credit() follow the same
    interface convention as the personal Wallet for consistency."""

    family = models.OneToOneField(Family, on_delete=models.CASCADE, related_name='wallet')
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_funded = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_spent = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.family.name} wallet — ₦{self.balance}"

    def credit(self, amount):
        self.balance += amount
        self.total_funded += amount
        self.save(update_fields=['balance', 'total_funded', 'updated_at'])

    def debit(self, amount):
        self.balance -= amount
        self.total_spent += amount
        self.save(update_fields=['balance', 'total_spent', 'updated_at'])


class FamilyWalletFunding(models.Model):
    """One record per top-up, so the wallet can show 'funded by' the way
    the product spec's example does (Jafaru ₦20,000, Mum ₦10,000, ...)."""

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name='fundings')
    funded_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='family_fundings')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.funded_by} funded ₦{self.amount} into {self.family}"


class MemberServicePreset(models.Model):
    """A saved 'this is how we usually pay for X for this person' entry —
    e.g. Mum / MTN / 080XXXXXXXX — so schedules and requests don't need
    the phone/meter/smartcard number re-entered every time."""

    class ServiceType(models.TextChoices):
        AIRTIME = 'airtime', 'Airtime'
        DATA = 'data', 'Data'
        ELECTRICITY = 'electricity', 'Electricity'
        CABLE = 'cable', 'Cable TV'
        INTERNET = 'internet', 'Internet'

    membership = models.ForeignKey(FamilyMembership, on_delete=models.CASCADE, related_name='service_presets')
    service_type = models.CharField(max_length=20, choices=ServiceType.choices)
    label = models.CharField(max_length=100, help_text="e.g. 'Mum's MTN line', 'Dad's meter'")

    provider = models.ForeignKey(
        'services.ServiceProvider', null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    # Recipient identifier — phone number, meter number, or smartcard
    # number depending on service_type. Kept as one generic field rather
    # than three separate ones since only one is ever relevant at a time.
    recipient_identifier = models.CharField(max_length=100)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['label']

    def __str__(self):
        return f"{self.label} ({self.get_service_type_display()})"


class SpendingLimit(models.Model):
    """Per-member caps on the family wallet. Any of the three periods can
    be set independently — a member might have a monthly cap only, or
    all three at once, each enforced separately."""

    membership = models.OneToOneField(FamilyMembership, on_delete=models.CASCADE, related_name='spending_limit')
    daily_limit = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    weekly_limit = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    monthly_limit = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Limits for {self.membership.user}"


class ScheduledPurchase(models.Model):
    """The recurring-automation core of Beacon Family — 'every 1st of the
    month, buy Mum 10GB of MTN data.' Advanced by services.run_due_
    scheduled_purchases(), meant to be called from a periodic task
    (Celery beat / cron), never directly from a request."""

    class Frequency(models.TextChoices):
        DAILY = 'daily', 'Daily'
        WEEKLY = 'weekly', 'Weekly'
        MONTHLY = 'monthly', 'Monthly'

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name='scheduled_purchases')
    beneficiary = models.ForeignKey(FamilyMembership, on_delete=models.CASCADE, related_name='scheduled_purchases')
    preset = models.ForeignKey(MemberServicePreset, on_delete=models.PROTECT, related_name='schedules')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    plan = models.JSONField(default=dict)
    
    frequency = models.CharField(max_length=20, choices=Frequency.choices)
    # Only one of these is meaningful depending on frequency: day_of_week
    # for WEEKLY (0=Monday .. 6=Sunday), day_of_month for MONTHLY (1-31,
    # clamped to the actual last day of shorter months when advanced).
    day_of_week = models.PositiveSmallIntegerField(null=True, blank=True)
    day_of_month = models.PositiveSmallIntegerField(null=True, blank=True)

    is_active = models.BooleanField(default=True)
    next_run_at = models.DateTimeField()

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['next_run_at']

    def __str__(self):
        return f"{self.preset.label} — {self.get_frequency_display()} (next: {self.next_run_at:%d %b})"


class ScheduledPurchaseRun(models.Model):
    """One row per execution attempt of a ScheduledPurchase — this is
    what powers the 'Mum received 10GB data' / 'Electricity payment
    completed' activity feed, including the failed attempts."""

    class Status(models.TextChoices):
        SUCCESS = 'success', 'Success'
        FAILED_INSUFFICIENT_FUNDS = 'insufficient_funds', 'Insufficient funds'
        FAILED_LIMIT_EXCEEDED = 'limit_exceeded', 'Spending limit exceeded'
        FAILED_OTHER = 'failed', 'Failed'

    schedule = models.ForeignKey(ScheduledPurchase, on_delete=models.CASCADE, related_name='runs')
    status = models.CharField(max_length=20, choices=Status.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reference = models.CharField(max_length=40, blank=True)
    note = models.CharField(max_length=255, blank=True)
    ran_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-ran_at']

    def __str__(self):
        return f"{self.schedule} — {self.get_status_display()} @ {self.ran_at:%d %b %H:%M}"


class PurchaseRequest(models.Model):
    """A member asking the family wallet to pay for something one-off,
    subject to owner approval — e.g. 'Ibrahim requested ₦1,000 airtime.'"""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name='purchase_requests')
    requested_by = models.ForeignKey(FamilyMembership, on_delete=models.CASCADE, related_name='purchase_requests')
    preset = models.ForeignKey(MemberServicePreset, on_delete=models.PROTECT, related_name='requests')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    note = models.CharField(max_length=255, blank=True)
    plan = models.JSONField(default=dict)
    
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.CharField(max_length=255, blank=True)

    reference = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.requested_by.user} requested ₦{self.amount} ({self.get_status_display()})"
