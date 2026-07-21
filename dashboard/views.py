from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count
from django.utils import timezone
from datetime import timedelta
from transactions.models import Transaction
from notifications.models import Notification
from wallet.models import Wallet
from links.models import ClaimLink
from decimal import Decimal
@login_required
def dashboard_view(request):
    """Main user dashboard"""
    wallet, _ = Wallet.objects.get_or_create(user=request.user)
    
    # Recent transactions
    recent_transactions = Transaction.objects.filter(user=request.user)[:5]
    
    # Stats
    total_purchases = Transaction.objects.filter(
        user=request.user, status='success'
    ).exclude(transaction_type='wallet_funding').exclude(transaction_type='refund').count()
    
    total_spent = Transaction.objects.filter(
        user=request.user, status='success'
    ).exclude(transaction_type='wallet_funding').exclude(transaction_type='refund').aggregate(
        total=Sum('amount')
    )['total'] or 0
    
    # Notifications
    notifications = Notification.objects.filter(user=request.user)[:5]
    unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
    
    # Quick stats
    today = timezone.now().date()
    month_ago = today - timedelta(days=30)
    
    monthly_transactions = Transaction.objects.filter(
        user=request.user, created_at__date__gte=month_ago, status='success'
    )
    
    # Active claim links
    active_links = ClaimLink.objects.filter(
        user=request.user, status='active'
    ).count()
    
    # Profile completion
    profile = request.user.profile
    profile.calculate_completion()

    stats = {
      'active_links': active_links,
      'month_spend': float(monthly_transactions.aggregate(total=Sum('amount'))['total'] or 0),
      'tx_count': monthly_transactions.count()
    }
  
    context = {
        'wallet': wallet,
        'recent_transactions': recent_transactions,
        'total_purchases': total_purchases,
        'total_spent': total_spent,
        'notifications': notifications,
        'unread_count': unread_count,
        'stats': stats,
        'profile_completion': profile.profile_completion,
    }
    return render(request, 'dashboard/index.html', context)
