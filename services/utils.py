from decimal import Decimal
from django.contrib.auth.hashers import check_password
from django.core.exceptions import ValidationError

from .models import ServiceProvider, ServicePlan, ApiProviderResponse
from wallet.models import Wallet
from transactions.models import Transaction

# Replace this with your actual VTU API
from .vtu import buy_airtime_api, buy_data_api

def _buy_airtime(user, network_id, amount, phone_number):
    """
    Purchase airtime.
    """

    amount = Decimal(str(amount))

    wallet = Wallet.objects.select_for_update().get(user=user)

    if wallet.balance < amount:
        raise ValidationError("Insufficient wallet balance.")

    response = buy_airtime_api(
        network=network_id,
        phone=phone_number,
        amount=float(amount)
    )

    if not response["success"]:
        raise ValidationError(response["message"])
    wallet_balance_before = wallet.balance
    wallet_balance_after = wallet_balance_before - amount
    wallet.balance -= amount
    wallet.save()

    Transaction.objects.create(
        user=user,
        amount=amount,
        plan_name="Airtime",
        transaction_type="airtime",
        status="success",
        reference_number=response["reference"],
        api_response=response,
        description=f"Airtime purchase for {phone_number}",
        wallet_balance_before=wallet_balance_before,
        wallet_balance_after=wallet_balance_after
    )

    return response

def _buy_data(user, network_id, plan_id, phone_number):
    """
    Purchase data bundle.
    """

    plan = ApiProviderResponse.objects.get(
        provider__api_id=network_id,
        
    )
    plan = list(filter(lambda pl: pl["variation_code"] == plan_id, plan.data.get("content").get("variations")))[0]
    plan["serviceID"] = network_id
    wallet = Wallet.objects.select_for_update().get(user=user)
    amount = Decimal(plan.get('variation_amount'))
    
    if wallet.balance < amount:
        raise ValidationError("Insufficient wallet balance.")

    response = buy_data_api(
        network=network_id,
        plan=plan,
        phone=phone_number
    )

    if not response["success"]:
        
        
        raise ValidationError(response["message"])
    
  
    wallet_balance_before = wallet.balance
    wallet_balance_after = wallet_balance_before - amount
    
    wallet.balance -= amount
    wallet.save()

    Transaction.objects.create(
        user=user,
        amount=amount,
        transaction_type="data",
        plan_name=plan.get("name"),
        status="success",
        reference_number=response["reference"],
        api_response=response,
        description=f"{plan.get("name")} for {phone_number}",
        wallet_balance_before=wallet_balance_before,
        wallet_balance_after=wallet_balance_after
  )

    return response