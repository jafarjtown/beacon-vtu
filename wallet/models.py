from django.db import models
from django.contrib.auth import get_user_model
import uuid

User = get_user_model()


class Wallet(models.Model):
    """User wallet for storing funds"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='wallet')
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_funded = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_spent = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Wallet'
        verbose_name_plural = 'Wallets'
    
    def __str__(self):
        return f"Wallet of {self.user.email} - ₦{self.balance}"
    
    def credit(self, amount):
        """Credit wallet balance"""
        self.balance += amount
        self.total_funded += amount
        self.save()
    
    def debit(self, amount):
        """Debit wallet balance"""
        if self.balance >= amount:
            self.balance -= amount
            self.total_spent += amount
            self.save()
            return True
        return False


class FundingRequest(models.Model):
    """Mock bank transfer funding requests"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ]
    
    request_id = models.CharField(max_length=20, unique=True, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='funding_requests')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    bank_name = models.CharField(max_length=100)
    account_name = models.CharField(max_length=200)
    account_number = models.CharField(max_length=20)
    reference_number = models.CharField(max_length=50, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    notes = models.TextField(blank=True)
    processed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Funding #{self.request_id} - ₦{self.amount} ({self.status})"
    
    def save(self, *args, **kwargs):
        if not self.request_id:
            self.request_id = f"FND-{uuid.uuid4().hex[:8].upper()}"
        if not self.reference_number:
            self.reference_number = f"REF{uuid.uuid4().hex[:12].upper()}"
        super().save(*args, **kwargs)
