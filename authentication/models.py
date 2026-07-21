
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.contrib.auth.hashers import make_password, check_password
import uuid


class User(AbstractUser):
    """Custom User model with email verification"""
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=20, blank=True)
    is_email_verified = models.BooleanField(default=False)
    email_verification_token = models.CharField(max_length=100, blank=True, null=True)
    password_reset_token = models.CharField(max_length=100, blank=True, null=True)
    password_reset_expires = models.DateTimeField(blank=True, null=True)
    referral_code = models.CharField(max_length=20, unique=True, blank=True, null=True)
    referred_by = models.ForeignKey('self', on_delete=models.SET_NULL, blank=True, null=True, related_name='referrals')
    date_joined = models.DateTimeField(auto_now_add=True)
    last_login_ip = models.GenericIPAddressField(blank=True, null=True)
    transaction_pin_hash = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        help_text="Hashed transaction PIN"
    )
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    class Meta:
        ordering = ['-date_joined']
      
    def set_transaction_pin(self, pin):
        """Hash and store the transaction PIN."""
        self.transaction_pin_hash = make_password(str(pin))

    def check_transaction_pin(self, pin):
        """Verify the transaction PIN."""
        return check_password(str(pin), self.transaction_pin_hash)

    def has_transaction_pin(self):
        """Return True if a transaction PIN has been set."""
        return bool(self.transaction_pin_hash)
    
    def __str__(self):
        return self.email
    
    def save(self, *args, **kwargs):
        if not self.referral_code:
            self.referral_code = f"REF{uuid.uuid4().hex[:8].upper()}"
        
        super().save(*args, **kwargs)
    
    def get_full_name(self):
        if self.first_name or self.last_name:
            return f"{self.first_name} {self.last_name}".strip()
        return self.username

    def total_money_in(self):
      funding_requests = self.funding_requests.all()
      
      return sum(tx.amount for tx in funding_requests.filter(status="confirmed"))
    
    def total_money_out(self):
      transactions = self.transactions.all()
      
      return sum(tx.amount for tx in transactions.filter(status="success"))


class Profile(models.Model):
    """Extended user profile information"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    avatar = models.FileField(upload_to='avatars/', default='avatars/default.png', blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, default='Nigeria')
    timezone = models.CharField(max_length=50, default='Africa/Lagos')
    date_of_birth = models.DateField(blank=True, null=True)
    bio = models.TextField(max_length=500, blank=True)
    two_factor_enabled = models.BooleanField(default=False)
    login_notifications = models.BooleanField(default=True)
    transaction_notifications = models.BooleanField(default=True)
    marketing_emails = models.BooleanField(default=False)
    profile_completion = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'User Profile'
        verbose_name_plural = 'User Profiles'
    
    def __str__(self):
        return f"Profile of {self.user.email}"
    
    def calculate_completion(self):
        """Calculate profile completion percentage"""
        fields = [
            self.user.first_name,
            self.user.last_name,
            self.user.phone_number,
            self.avatar.name != 'avatars/default.png',
            self.address,
            self.city,
            self.state,
            self.country,
        ]
        completed = sum(1 for f in fields if f)
        self.profile_completion = int((completed / len(fields)) * 100)
        self.save(update_fields=['profile_completion'])
        return self.profile_completion

    