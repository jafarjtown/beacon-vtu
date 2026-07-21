from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit
from django.db import transaction as db_transaction
from decimal import Decimal
import json
import time
from .models import ServiceProvider, ServicePlan, Purchase
from wallet.models import Wallet
from transactions.models import Transaction
from notifications.models import Notification
from .utils import _buy_airtime, _buy_data

@login_required
def services_list_view(request):
    """Display all available services grouped by category"""
    providers = ServiceProvider.objects.filter(is_active=True, category="data")
    
    context = {"providers": providers}
    
    
    if request.method == "POST":
      network_id = request.POST.get("network")
      phone_number = request.POST.get("phone_number")
      service_type = request.POST.get("service_type")
      password = request.POST.get("password")

      if service_type == "data":
        plan_id = request.POST.get('plan')
        
        response = _buy_data(request.user, network_id, plan_id, phone_number)
        if response['success']:
          messages.success(request, response["message"])
        
      else:
        amount_preset = request.POST.get('amount_preset')
        raw_amount = request.POST.get('amount') if amount_preset == 'custom' else amount_preset 
        response = _buy_airtime(request.user, network_id, raw_amount, phone_number)
        if response['success']:
          messages.success(request, 'Airtime purchase Successful.')
        
    return render(request, 'services/services_list.html', context)


@login_required
def service_detail_view(request, category):
    """Service detail/purchase page"""
    providers = ServiceProvider.objects.filter(category=category, is_active=True).prefetch_related('plans')
    plans = []
    for p in providers:
        for plan in p.plans.filter(is_active=True):
            plans.append(plan)
    
    context = {
        'category': category,
        'category_display': dict(ServiceProvider.CATEGORY_CHOICES).get(category, category),
        'plans': plans,
    }
    return render(request, 'services/service_detail.html', context)



from phonenumbers import parse, is_valid_number
from phonenumbers import carrier
from phonenumbers.phonenumberutil import NumberParseException


def validate_phone(request):
    phone = request.GET.get("beneficiary")

    if not phone:
        return JsonResponse({
            "valid": False,
            "message": "Phone number is required."
        }, status=400)

    try:
        number = parse(phone, "NG")

        if not is_valid_number(number):
            return JsonResponse({
                "valid": False,
                "message": "Invalid phone number."
            })

        network = carrier.name_for_number(
            number,
            "en"
        )
        valid = False
        provider = request.GET.get("provider_id")
        print(provider)
        if provider.endswith("data"):
          provider = provider.replace("-data", "")
        if network.lower() == provider:
          valid = True
        return JsonResponse({
            "valid": valid,
            "network": network,
            "message": f"Number belongs to {network}."
        })

    except NumberParseException:
        return JsonResponse({
            "valid": False,
            "message": "Invalid phone number format."
        })
@login_required
@ratelimit(key='user', rate='10/m', method='POST')
@require_http_methods(["POST"])
def process_purchase(request):
    """Process purchase with password verification"""
    import json
    data = json.loads(request.body)
    
    plan_id = data.get('plan_id')
    beneficiary = data.get('beneficiary', '').strip()
    password = data.get('password', '')
    
    # Verify password
    if not request.user.check_password(password):
        return JsonResponse({'success': False, 'message': 'Incorrect password. Please try again.'})
    
    plan = get_object_or_404(ServicePlan, id=plan_id, is_active=True)
    
    # Check wallet balance
    wallet, _ = Wallet.objects.get_or_create(user=request.user)
    if wallet.balance < plan.amount:
        return JsonResponse({'success': False, 'message': 'Insufficient wallet balance. Please fund your wallet.'})
    
    # Check for duplicate (within last 2 minutes)
    recent = Purchase.objects.filter(
        user=request.user,
        plan=plan,
        beneficiary=beneficiary,
        created_at__gte=__import__('django.utils.timezone').utils.timezone.now() - __import__('datetime').timedelta(minutes=2)
    ).first()
    
    if recent:
        return JsonResponse({'success': False, 'message': 'Duplicate purchase detected. Please wait 2 minutes.'})
    
    # Process transaction
    with db_transaction.atomic():
        # Lock wallet
        wallet = Wallet.objects.select_for_update().get(user=request.user)
        
        if wallet.balance < plan.amount:
            return JsonResponse({'success': False, 'message': 'Insufficient balance'})
        
        # Create transaction record
        txn = Transaction.objects.create(
            user=request.user,
            transaction_type=plan.provider.category,
            amount=plan.amount,
            wallet_balance_before=wallet.balance,
            wallet_balance_after=wallet.balance - plan.amount,
            status='processing',
            service_provider=plan.provider.name,
            plan_name=plan.name,
            recipient=beneficiary
        )
        
        # Debit wallet
        wallet.debit(plan.amount)
        
        # Create purchase
        purchase = Purchase.objects.create(
            user=request.user,
            plan=plan,
            transaction=txn,
            beneficiary=beneficiary,
            amount=plan.amount,
            status='processing'
        )
        
        # Simulate API processing
        time.sleep(1.5)
        
        # Mock success (95% success rate)
        import random
        success = random.random() < 0.95
        
        if success:
            txn.status = 'success'
            purchase.status = 'completed'
            if plan.provider.category == 'electricity':
                purchase.token_code = f"{random.randint(100000000000, 999999999999)}"
            txn.save()
            purchase.save()
            
            # Notification
            Notification.objects.create(
                user=request.user,
                title=f'{plan.provider.get_category_display()} Purchase Successful',
                message=f'₦{plan.amount} {plan.name} purchased for {beneficiary}.',
                notification_type='success'
            )
            
            return JsonResponse({
                'success': True,
                'message': 'Purchase completed successfully!',
                'transaction_id': txn.transaction_id,
                'token': purchase.token_code if purchase.token_code else None
            })
        else:
            # Reverse on failure
            txn.status = 'failed'
            txn.error_message = 'Service provider error. Please try again.'
            purchase.status = 'failed'
            txn.save()
            purchase.save()
            
            # Refund
            wallet.credit(plan.amount)
            txn2 = Transaction.objects.create(
                user=request.user,
                transaction_type='refund',
                amount=plan.amount,
                wallet_balance_before=wallet.balance - plan.amount,
                wallet_balance_after=wallet.balance,
                status='success',
                recipient='Wallet',
                plan_name='Auto Refund'
            )
            
            Notification.objects.create(
                user=request.user,
                title='Purchase Failed - Refunded',
                message=f'₦{plan.amount} has been refunded to your wallet.',
                notification_type='warning'
            )
            
            return JsonResponse({
                'success': False,
                'message': 'Purchase failed. Amount has been refunded to your wallet.'
            })
