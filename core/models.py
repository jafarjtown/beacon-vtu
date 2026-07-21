from django.db import models
from django.contrib.auth import get_user_model
import uuid

User = get_user_model()


class SiteSettings(models.Model):
    """Global site configuration"""
    site_name = models.CharField(max_length=100, default="VTU Pro")
    tagline = models.CharField(max_length=200, default="Fast. Secure. Reliable.")
    logo = models.FileField(upload_to='site/', blank=True, null=True)
    favicon = models.FileField(upload_to='site/', blank=True, null=True)
    primary_color = models.CharField(max_length=7, default="#6366f1")
    secondary_color = models.CharField(max_length=7, default="#8b5cf6")
    support_email = models.EmailField(default="support@vtuapp.com")
    support_phone = models.CharField(max_length=20, blank=True)
    bank_name = models.CharField(max_length=100, default="Mock Bank Nigeria")
    bank_account_name = models.CharField(max_length=200, default="VTU Pro Limited")
    bank_account_number = models.CharField(max_length=20, default="1234567890")
    min_fund_amount = models.DecimalField(max_digits=10, decimal_places=2, default=100.00)
    max_fund_amount = models.DecimalField(max_digits=10, decimal_places=2, default=500000.00)
    referral_bonus_percent = models.DecimalField(max_digits=5, decimal_places=2, default=2.00)
    maintenance_mode = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Site Setting"
        verbose_name_plural = "Site Settings"

    def __str__(self):
        return self.site_name

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass

    @classmethod
    def load(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        return obj


class Announcement(models.Model):
    """Site-wide announcements"""
    title = models.CharField(max_length=200)
    content = models.TextField()
    is_active = models.BooleanField(default=True)
    priority = models.IntegerField(default=0, help_text="Higher number = higher priority")
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-priority', '-created_at']

    def __str__(self):
        return self.title


class SupportTicket(models.Model):
    """Customer support tickets"""
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
    ]
    
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    
    ticket_id = models.CharField(max_length=20, unique=True, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tickets')
    subject = models.CharField(max_length=200)
    message = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"#{self.ticket_id} - {self.subject}"

    def save(self, *args, **kwargs):
        if not self.ticket_id:
            self.ticket_id = f"TKT-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)


class TicketReply(models.Model):
    """Replies to support tickets"""
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name='replies')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    message = models.TextField()
    is_staff_reply = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Ticket Replies"
        ordering = ['created_at']

    def __str__(self):
        return f"Reply to {self.ticket.ticket_id}"
