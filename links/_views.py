from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django_ratelimit.decorators import ratelimit
from datetime import timedelta
from .models import ClaimLink, ClaimSlot
from wallet.models import Wallet
from transactions.models import Transaction
from notifications.models import Notification
from services.models import ServiceProvider, ServicePlan


@login_required
def my_links_view(request):
    """List all claim links created by user"""
    links = ClaimLink.objects.filter(user=request.user)
    return render(request, 'links/my_links.html', {'links': links})


@login_required
def create_link_view(request):
    """Create a new claim link"""
    providers = ServiceProvider.objects.filter(
        category__in=['airtime', 'data'], is_active=True
    ).prefetch_related('plans')
    
    if request.method == 'POST':
        plan_id = request.POST.get('plan_id')
        network_id = request.POST.get('network')
      
        slots = int(request.POST.get('slots', 1))
        expiry_days = int(request.POST.get('expiry_days', 7))
        notes = request.POST.get('notes', '')

        network = get_object_or_404(ServiceProvider, id=network_id, is_active=True)
        plan = None
        # total_amount = plan.amount * slots


        # Check if provider is for airtime or data
        if network.category == "airtime":
          
          amount_preset = request.POST.get('amount_preset')
          if amount_preset == 'custom':
            amount_per_slot = int(request.POST.get('amount'))
            
          amount_per_slot = int(amount_preset)
          total_amount = amount_per_slot * slots
        else:
          plan_id = request.POST.get("plan")
          plan = get_object_or_404(ServicePlan, id = plan_id, is_active=True)
          total_amount = plan.amount * slots
          amount_per_slot = plan.amount

        
        # Check wallet
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        if wallet.balance < total_amount:
            messages.error(request, 'Insufficient wallet balance.')
            return redirect('links:create')
        
        # Deduct wallet
        wallet.debit(total_amount)
        
        # Create link
        link = ClaimLink.objects.create(
            user=request.user,
            service_type=network.category,
            provider=network.name,
            amount=amount_per_slot,
            total_slots=slots,
            expiry_date=timezone.now() + timedelta(days=expiry_days),
            notes=notes
        )
        
        # Create empty slots
        for _ in range(slots):
            ClaimSlot.objects.create(link=link)
        
        # Record transaction
        transaction = Transaction.objects.create(
            user=request.user,
            transaction_type=network.category,
            amount=total_amount,
            wallet_balance_before=wallet.balance + total_amount,
            wallet_balance_after=wallet.balance,
            status='success',
            service_provider=network.name,
            plan_name=f"{network.category} (Claim Link x{slots})",
            recipient='Claim Link'
        )
        if plan:
          link.plan_name = plan.name
          link.plan_id = plan.id
          transaction.plan_name = f"{transaction.plan_name} {plan.name}"
        else:
          link.plan_name = 'Airtime'
          transaction.plan_name = f"{transaction.plan_name} Airtime"
        transaction.save()
        link.save()
        
        messages.success(request, f'Claim link created! Share: {link.share_url}')
        return redirect('links:my_links')
    
    context = {
      'providers': providers,
      'providers_airtime': providers.filter(category='airtime'),
      'providers_data': providers.filter(category='data'),
      'plans': [plan for p in providers.filter(category='data') for plan in p.plans.all() ]
    }
    return render(request, 'links/create_link.html', context)


@login_required
def link_detail_view(request, link_id):
    """View claim link details and manage"""
    link = get_object_or_404(ClaimLink, link_id=link_id, user=request.user)
    slots = link.slots.all()
    return render(request, 'links/link_detail.html', {'link': link, 'slots': slots})


@login_required
@require_http_methods(["POST"])
def toggle_link_view(request, link_id):
    """Enable/disable a claim link"""
    link = get_object_or_404(ClaimLink, link_id=link_id, user=request.user)
    
    if link.status == 'disabled':
        if link.is_expired:
            messages.error(request, 'Cannot enable expired link.')
        else:
            link.status = 'active'
            messages.success(request, 'Link enabled.')
    else:
        link.status = 'disabled'
        messages.success(request, 'Link disabled.')
    
    link.save()
    return redirect('links:detail', link_id=link.link_id)


def claim_page_view(request, link_id):
    """Public claim page - no login required"""
    link = get_object_or_404(ClaimLink, link_id=link_id)
    if link.is_expired:
        return render(request, 'links/claim_expired.html', {'link': link})
    
    if request.method == 'POST':
        
        phone = request.POST.get('phone_number', '').strip()
        
        if not phone or len(phone) < 10:
            messages.error(request, 'Please enter a valid phone number.')
            return render(request, 'links/claim_page.html', {'link': link})
        # check if number is already claimed
        if link.slots.filter(claimed_by=phone).exists():
          return render(request, 'links/claim_expired.html', {'link': link, 'message': 'This Phone number is already used.'})
        # Find first unclaimed slot
        slot = link.slots.filter(is_claimed=False).first()
        if not slot:
            link.status = 'completed'
            link.save()
            return render(request, 'links/claim_expired.html', {'link': link, 'message': 'All slots have been claimed.'})
        
        # Claim slot
        slot.claimed_by = phone
        slot.is_claimed = True
        slot.claimed_at = timezone.now()
        slot.ip_address = request.META.get('REMOTE_ADDR')
        slot.user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]
        slot.save()
        
        link.used_slots = link.slots.filter(is_claimed=True).count()
        if link.used_slots >= link.total_slots:
            link.status = 'completed'
        link.save()
        
        return render(request, 'links/claim_success.html', {
            'slot': slot,
            'claim': link,
            'phone': phone,
            'plan_name': link.provider
        })
    
    return render(request, 'links/claim_page.html', {'link': link})
