from django.db import models
from django.contrib.auth import get_user_model
from django.conf import settings
from django.utils import timezone


import uuid
import requests

User = get_user_model()


class ApiProviderResponse(models.Model):
    data = models.JSONField(default=dict, blank=True)
    provider = models.OneToOneField(
        "ServiceProvider",
        on_delete=models.CASCADE,
        related_name="api_response",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def update_from_vtpass(self):
        """
        Fetch the latest service variations from VTpass and update this record.
        """

        payload = {
            "serviceID": self.provider.api_id,
        }

        headers = {
            "api-key": settings.VTPASS_API_KEY,
            "public-key": settings.VTPASS_PUBLIC_KEY,
            "secret-key": settings.VTPASS_SECRET_KEY,
            "Content-Type": "application/json",
        }

        response = requests.get(
            settings.VTPASS_VARIATIONS_URL,
            json=payload,
            headers=headers,
            timeout=30,
        )

        response.raise_for_status()
        data = response.json()
        self.data = data
        self.save(update_fields=["data", "updated_at"])

        return data
class ServiceProvider(models.Model):
    CATEGORY_CHOICES = [
        ('airtime', 'Airtime'),
        ('data', 'Data'),
        ('electricity', 'Electricity'),
        ('cable', 'Cable TV'),
        ('internet', 'Internet'),
        ('exam_pin', 'Exam Pin'),
        ('education', 'Education'),
    ]
    
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    code = models.CharField(max_length=50, unique=True)
    logo = models.FileField(upload_to='providers/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    requires_validation = models.BooleanField(default=False)
    validation_endpoint = models.CharField(max_length=200, blank=True)
    api_id = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['category', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"


class ServicePlan(models.Model):

    DATA_WEIGHT = [
      ("mb", "MegaByte"),
      ("gb", "GigaByte")
    ]
    
    provider = models.ForeignKey(ServiceProvider, on_delete=models.CASCADE, related_name='plans')
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    original_amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    description = models.TextField(blank=True)
    validity = models.CharField(max_length=100, blank=True, help_text="e.g., 30 Days")
    is_active = models.BooleanField(default=True)
    requires_beneficiary = models.BooleanField(default=True)
    beneficiary_label = models.CharField(max_length=50, default="Phone Number")
    beneficiary_placeholder = models.CharField(max_length=100, default="e.g., 08012345678")
    created_at = models.DateTimeField(auto_now_add=True)

    data_weight = models.CharField(max_length=2, choices=DATA_WEIGHT, default="", blank=True)
    data_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    class Meta:
        ordering = ['provider', 'amount']
    
    def __str__(self):
        return f"{self.provider.name} - {self.name} (₦{self.amount})"
    
    @property
    def discount_percent(self):
        if self.original_amount and self.original_amount > self.amount:
            return int(((self.original_amount - self.amount) / self.original_amount) * 100)
        return 0


class Purchase(models.Model):
    STATUS_CHOICES = [
        ('initiated', 'Initiated'),
        ('validated', 'Validated'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='purchases')
    plan = models.ForeignKey(ServicePlan, on_delete=models.SET_NULL, null=True)
    transaction = models.OneToOneField('transactions.Transaction', on_delete=models.CASCADE, null=True, blank=True)
    beneficiary = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='initiated')
    api_reference = models.CharField(max_length=100, blank=True)
    token_code = models.CharField(max_length=100, blank=True, help_text="For electricity/token purchases")
    receipt_url = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Purchase {self.id} - {self.plan} for {self.beneficiary}"
