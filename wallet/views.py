from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit
from decimal import Decimal
from .models import Wallet, FundingRequest
from core.models import SiteSettings


@login_required
def wallet_view(request):
    """Wallet dashboard view"""
    wallet, created = Wallet.objects.get_or_create(user=request.user)
    funding_history = FundingRequest.objects.filter(user=request.user)[:10]
    
    context = {
        'wallet': wallet,
        'funding_history': funding_history,
        'settings': SiteSettings.load(),
    }
    return render(request, 'wallet/wallet.html', context)


@login_required
def fund_wallet_view(request):
    """Initiate wallet funding via bank transfer (mock)"""
    settings = SiteSettings.load()
    
    if request.method == 'POST':
        try:
            amount = Decimal(request.POST.get('amount', 0))
            if amount < settings.min_fund_amount:
                messages.error(request, f'Minimum funding amount is ₦{settings.min_fund_amount}')
                return redirect('wallet:fund')
            if amount > settings.max_fund_amount:
                messages.error(request, f'Maximum funding amount is ₦{settings.max_fund_amount}')
                return redirect('wallet:fund')
            
            funding = FundingRequest.objects.create(
                user=request.user,
                amount=amount,
                bank_name=settings.bank_name,
                account_name=settings.bank_account_name,
                account_number=settings.bank_account_number,
            )
            
            messages.success(
                request,
                f'Funding request created! Transfer ₦{amount} to the account below and click Confirm Payment.'
            )
            return redirect('wallet:funding_detail', request_id=funding.request_id)
            
        except Exception as e:
            messages.error(request, 'Invalid amount entered.')
            return redirect('wallet:fund')
    
    context = {
        'settings': settings,
    }
    return render(request, 'wallet/fund_wallet.html', context)


@login_required
def funding_detail_view(request, request_id):
    """View funding request details"""
    funding = get_object_or_404(FundingRequest, request_id=request_id, user=request.user)
    return render(request, 'wallet/funding_detail.html', {'funding': funding})


@login_required
def confirm_payment_view(request, request_id):
    """Confirm mock payment and credit wallet"""
    if request.method == 'POST':
        funding = get_object_or_404(FundingRequest, request_id=request_id, user=request.user)
        
        if funding.status == 'pending':
            wallet, created = Wallet.objects.get_or_create(user=request.user)
            wallet.credit(funding.amount)
            
            funding.status = 'confirmed'
            from django.utils import timezone
            funding.processed_at = timezone.now()
            funding.save()
            
            # Create notification
            from notifications.models import Notification
            Notification.objects.create(
                user=request.user,
                title='Wallet Funded',
                message=f'Your wallet has been credited with ₦{funding.amount}.',
                notification_type='success'
            )
            
            messages.success(
                request,
                f'Payment confirmed! ₦{funding.amount} has been credited to your wallet.'
            )
        else:
            messages.error(request, 'This funding request has already been processed.')
    
    return redirect('wallet:wallet')


@login_required
def funding_history_view(request):
    """View all funding history"""
    fundings = FundingRequest.objects.filter(user=request.user)
    return render(request, 'wallet/funding_history.html', {'fundings': fundings})
