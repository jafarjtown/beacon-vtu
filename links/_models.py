from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.shortcuts import reverse
from datetime import timedelta
import uuid

from services.models import ServicePlan
User = get_user_model()


class ClaimLink(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('disabled', 'Disabled'),
        ('expired', 'Expired'),
        ('completed', 'Completed'),
    ]
    
    link_id = models.CharField(max_length=20, unique=True, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='claim_links')
    service_type = models.CharField(max_length=20, choices=[
        ('airtime', 'Airtime'),
        ('data', 'Data'),
    ])
    provider = models.CharField(max_length=100)
    plan_name = models.CharField(max_length=200)
    plan_id = models.CharField(max_length=20, default="")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    total_slots = models.PositiveIntegerField(default=1)
    used_slots = models.PositiveIntegerField(default=0)
    expiry_date = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    notes = models.TextField(blank=True, help_text="Personal notes about this link")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.link_id} - {self.plan_name} ({self.used_slots}/{self.total_slots})"
    
    def save(self, *args, **kwargs):
        if not self.link_id:
            self.link_id = f"LNK-{uuid.uuid4().hex[:8].upper()}"
        # Auto-update status
        if self.status == 'active':
            if timezone.now() > self.expiry_date:
                self.status = 'expired'
            elif self.used_slots >= self.total_slots:
                self.status = 'completed'
        super().save(*args, **kwargs)

    @property
    def total_reserved(self):
      return self.total_slots * self.amount
    @property
    
    def remaining_slots(self):
        return self.total_slots - self.used_slots

    def expires_in(self):
      exp = timezone.now() - self.expiry_date
      return exp.days
  
    @property
    def is_expired(self):
        return timezone.now() > self.expiry_date or self.status in ['expired', 'completed', 'disabled']
    
    @property
    def share_url(self):
        from django.conf import settings
        return f"{settings.ALLOWED_HOSTS[0]}/links/claim/{self.link_id}/"

    def get_absolute_url(self):
      return reverse("links:claim", kwargs={"link_id":self.link_id})

  
    def percent_claimed(self):
      return self.used_slots / self.total_slots * 100

    def item_label(self):
      suffix = "Airtime"
      prefix = "₦"
      amount = self.amount
      if self.service_type == "data":
          suffix = "Data"
          prefix = ""
          plan = ServicePlan.objects.get(id=self.plan_id)
          amount =f"{plan.data_value}{plan.data_weight}"
      return f"{prefix}{amount} {suffix}"

    def expires_soon(self):
      return True
    
    
    def claimed_slots(self):
      return self.slots.filter(is_claimed=True)
      
class ClaimSlot(models.Model):
    link = models.ForeignKey(ClaimLink, on_delete=models.CASCADE, related_name='slots')
    claimed_by = models.CharField(max_length=100, blank=True, help_text="Phone number of claimant")
    claimed_at = models.DateTimeField(blank=True, null=True)
    is_claimed = models.BooleanField(default=False)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True)
    
    class Meta:
        ordering = ['id']
    
    def __str__(self):
        return f"Slot {self.id} of {self.link.link_id}"


    def claimed_phone(self):
      return f'{self.claimed_by[:4]}****{self.claimed_by[8:]}'