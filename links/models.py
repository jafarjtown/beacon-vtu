import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.shortcuts import reverse
from django.utils import timezone

User = get_user_model()

# How close to expiry a link counts as "expiring soon" in the UI.
EXPIRES_SOON_THRESHOLD = timedelta(hours=24)


class ClaimLink(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        DISABLED = 'disabled', 'Disabled'
        EXPIRED = 'expired', 'Expired'
        COMPLETED = 'completed', 'Completed'

    class ServiceType(models.TextChoices):
        AIRTIME = 'airtime', 'Airtime'
        DATA = 'data', 'Data'

    link_id = models.CharField(max_length=20, unique=True, editable=False, db_index=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='claim_links')

    service_type = models.CharField(max_length=20, choices=ServiceType.choices)

    # Snapshots taken at creation time so a link keeps displaying correctly
    # even if the provider/plan behind it is later renamed or removed.
    provider = models.CharField(max_length=100)
    plan_name = models.CharField(max_length=200, blank=True)

    # Optional live references for analytics/reporting. Nullable + SET_NULL
    # so deleting a provider or plan later never breaks an existing link.
    network = models.ForeignKey(
        'services.ServiceProvider', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='claim_links',
    )
    plan = models.JSONField(default=dict)

    amount_per_slot = models.DecimalField(max_digits=10, decimal_places=2)
    total_slots = models.PositiveIntegerField(default=1)
    used_slots = models.PositiveIntegerField(default=0)

    # Null means "never expires" — previously this was forced to a
    # DateTimeField, which made "never" silently expire the link instantly.
    expiry_date = models.DateTimeField(null=True, blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    notes = models.TextField(blank=True, help_text="Personal notes about this link")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['status', 'expiry_date']),
        ]

    def __str__(self):
        return f"{self.link_id} - {self.plan_name or self.provider} ({self.used_slots}/{self.total_slots})"

    def save(self, *args, **kwargs):
        if not self.link_id:
            self.link_id = self._generate_link_id()
        self._recompute_status()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_link_id():
        # Regenerate on the rare chance of a collision rather than trusting
        # 8 hex chars blindly.
        for _ in range(5):
            candidate = f"LNK-{uuid.uuid4().hex[:8].upper()}"
            if not ClaimLink.objects.filter(link_id=candidate).exists():
                return candidate
        raise RuntimeError("Could not generate a unique link_id after 5 attempts")

    def _recompute_status(self):
        """Derive status from current slot/expiry state. Only moves a link
        OUT of 'active' automatically — disabling is always explicit."""
        if self.status == self.Status.ACTIVE:
            if self.expiry_date and timezone.now() > self.expiry_date:
                self.status = self.Status.EXPIRED
            elif self.used_slots >= self.total_slots:
                self.status = self.Status.COMPLETED

    def refresh_status(self):
        """Public entry point to recompute + persist status outside of a
        normal save (e.g. from claim_slot, or a periodic cleanup job)."""
        self._recompute_status()
        self.save(update_fields=['status', 'updated_at', 'used_slots'])

    # ---------- computed display properties ----------

    @property
    def total_reserved(self):
        return self.total_slots * self.amount_per_slot

    @property
    def remaining_slots(self):
        return max(self.total_slots - self.used_slots, 0)

    @property
    def refundable_amount(self):
        """What should go back to the wallet if this link is disabled now."""
        return self.remaining_slots * self.amount_per_slot

    @property
    def is_expired(self):
        expired_by_date = bool(self.expiry_date and timezone.now() > self.expiry_date)
        return expired_by_date or self.status in (
            self.Status.EXPIRED, self.Status.COMPLETED, self.Status.DISABLED,
        )

    @property
    def is_claimable(self):
        return self.status == self.Status.ACTIVE and not self.is_expired and self.remaining_slots > 0

    @property
    def expires_in_days(self):
        """Whole days until expiry. None if the link never expires."""
        if not self.expiry_date:
            return None
        delta = self.expiry_date - timezone.now()
        return max(delta.days, 0)

    @property
    def expires_soon(self):
        if not self.expiry_date:
            return False
        return timezone.now() <= self.expiry_date <= timezone.now() + EXPIRES_SOON_THRESHOLD

    @property
    def percent_claimed(self):
        if not self.total_slots:
            return 0
        return round(self.used_slots / self.total_slots * 100)

    @property
    def item_label(self):
        if self.service_type == self.ServiceType.DATA:
            return self.plan_name or "Data"
        return f"₦{self.amount_per_slot:,.0f} Airtime"

    @property
    def share_url(self):
        base = getattr(settings, 'SITE_URL', None) or f"https://{settings.ALLOWED_HOSTS[0]}"
        return f"{base.rstrip('/')}{self.get_absolute_url()}"

    def get_absolute_url(self):
        return reverse('links:claim', kwargs={'link_id': self.link_id})

    def claimed_slots(self):
        return self.slots.filter(is_claimed=True)


class ClaimSlot(models.Model):
    link = models.ForeignKey(ClaimLink, on_delete=models.CASCADE, related_name='slots')
    claimed_by = models.CharField(max_length=100, blank=True, help_text="Phone number of claimant")
    claimed_at = models.DateTimeField(blank=True, null=True)
    is_claimed = models.BooleanField(default=False, db_index=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"Slot {self.id} of {self.link.link_id}"

    @property
    def masked_phone(self):
        """e.g. '08031234567' -> '0803***567'. Falls back gracefully for
        short/malformed values instead of raising on slice math."""
        phone = self.claimed_by
        if not phone or len(phone) < 7:
            return phone or ""
        return f"{phone[:4]}{'*' * (len(phone) - 7)}{phone[-3:]}"
