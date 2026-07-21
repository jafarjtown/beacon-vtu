from django.db import models
from django.contrib.auth import get_user_model
import uuid

User = get_user_model()


class Transaction(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('reversed', 'Reversed'),
    ]
    
    TYPE_CHOICES = [
        ('airtime', 'Airtime'),
        ('data', 'Data'),
        ('electricity', 'Electricity'),
        ('cable', 'Cable TV'),
        ('internet', 'Internet'),
        ('exam_pin', 'Exam Pin'),
        ('education', 'Education'),
        ('wallet_funding', 'Wallet Funding'),
        ('refund', 'Refund'),
    ]
    
    transaction_id = models.CharField(max_length=30, unique=True, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    wallet_balance_before = models.DecimalField(max_digits=12, decimal_places=2)
    wallet_balance_after = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    service_provider = models.CharField(max_length=100, blank=True)
    plan_name = models.CharField(max_length=200, blank=True)
    recipient = models.CharField(max_length=100, blank=True)
    reference_number = models.CharField(max_length=50, unique=True, blank=True)
    api_response = models.JSONField(blank=True, null=True)
    error_message = models.TextField(blank=True)
    is_duplicate = models.BooleanField(default=False)
    locked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    description = models.TextField()
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['status']),
            models.Index(fields=['transaction_type']),
        ]
    
    def __str__(self):
        return f"{self.transaction_id} - {self.transaction_type} - ₦{self.amount}"
    
    def save(self, *args, **kwargs):
        if not self.transaction_id:
            self.transaction_id = f"TXN-{uuid.uuid4().hex[:10].upper()}"
        if not self.reference_number:
            self.reference_number = f"REF{uuid.uuid4().hex[:12].upper()}"
        super().save(*args, **kwargs)
