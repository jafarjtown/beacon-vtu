"""
Business logic for the links app, kept out of views.py so the same
create/claim/disable logic can be reused from anywhere else later —
a future mobile API endpoint, a management command, an admin action —
without duplicating the wallet + transaction handling each time.

Every public function here either returns the object it created/affected,
or raises a ClaimLinkError subclass. Views should catch ClaimLinkError and
display str(exc) — no need to branch on the specific subclass unless you
want a different message per failure type.
"""
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib.auth.hashers import check_password as check_hashed_value
from django.db import transaction
from django.utils import timezone

from wallet.models import Wallet
from transactions.models import Transaction
from notifications.models import Notification
from services.models import ApiProviderResponse
from services import vtu

from .models import ClaimLink, ClaimSlot
MIN_SLOTS = 1
MAX_SLOTS = 50
MAX_AMOUNT_PER_SLOT = Decimal('100000')
ALLOWED_EXPIRY_DAYS = {1, 3, 7, 30}  # 0 or None means "never expires"
PIN_LENGTH = 4


class ClaimLinkError(Exception):
    """Base class for every create/claim/disable failure in this module."""


class InvalidPinError(ClaimLinkError):
    pass


class InsufficientBalanceError(ClaimLinkError):
    pass


class InvalidLinkParametersError(ClaimLinkError):
    pass


class LinkNotClaimableError(ClaimLinkError):
    pass


class AlreadyClaimedError(ClaimLinkError):
    pass


def _verify_pin(user, pin):
    """Check a transaction PIN against its hash.

    ASSUMPTION: this expects `user.transaction_pin_hash` — a CharField
    populated via Django's own `make_password()` the same way the login
    password is, just stored separately since a transaction PIN and an
    account password are different credentials with different threat
    models (one's typed on a 12-button grid in public, the other isn't).
    Adjust the attribute path here if you store it elsewhere (e.g. on the
    Wallet model instead of User).
    """
    pin_hash = getattr(user, 'transaction_pin_hash', None)
    
    if not pin_hash:
        raise InvalidPinError("You haven't set a transaction PIN yet. Set one in Settings first.")
    if not pin or not pin.isdigit() or len(pin) != PIN_LENGTH:
        raise InvalidPinError(f"Enter your {PIN_LENGTH}-digit PIN.")
    if not check_hashed_value(pin, pin_hash):
        raise InvalidPinError("Incorrect PIN.")


def _validate_common_params(user, pin, slots, expiry_days):
    _verify_pin(user, pin)
    if slots < MIN_SLOTS or slots > MAX_SLOTS:
        raise InvalidLinkParametersError(f"Slots must be between {MIN_SLOTS} and {MAX_SLOTS}.")
    if expiry_days and expiry_days not in ALLOWED_EXPIRY_DAYS:
        raise InvalidLinkParametersError("Invalid expiry option.")


def _locked_wallet(user):
    """Get-or-create the wallet, then lock its row for the rest of the
    current transaction so two concurrent requests can't both pass a
    balance check before either one commits (double-spend race)."""
    wallet, _ = Wallet.objects.get_or_create(user=user)
    return Wallet.objects.select_for_update().get(pk=wallet.pk)


@transaction.atomic
def create_airtime_link(*, user, network, amount_per_slot, slots, expiry_days, pin, notes=""):
    """Create a claim link that pays out airtime on redemption.

    network         : ServiceProvider instance, category='airtime'
    amount_per_slot : naira value delivered to each claimant (Decimal-able)
    expiry_days     : one of ALLOWED_EXPIRY_DAYS, or 0/None for "never"
    pin             : the user's 4-digit transaction PIN, as entered

    Raises a ClaimLinkError subclass on any failure; nothing is persisted
    or debited from the wallet when that happens.
    """
    _validate_common_params(user, pin, slots, expiry_days)
    try:
        amount_per_slot = Decimal(amount_per_slot)
    except (InvalidOperation, TypeError, ValueError):
        raise InvalidLinkParametersError("Enter a valid amount.")
    if amount_per_slot <= 0 or amount_per_slot > MAX_AMOUNT_PER_SLOT:
        raise InvalidLinkParametersError(f"Amount must be between ₦1 and ₦{MAX_AMOUNT_PER_SLOT:,.0f}.")

    return _create_link(
        user=user,
        service_type=ClaimLink.ServiceType.AIRTIME,
        network=network,
        plan={
          "name": "Airtime",
          "amount": float(amount_per_slot),
        },
        plan_name="Airtime",
        amount_per_slot=amount_per_slot,
        slots=slots,
        expiry_days=expiry_days,
        notes=notes,
    )


@transaction.atomic
def create_data_link(*, user, network, plan_id, slots, expiry_days, pin, notes=""):
    """Create a claim link that pays out a data bundle on redemption.

    plan : ServicePlan instance belonging to `network`.
    pin  : the user's 4-digit transaction PIN, as entered
    """
    _validate_common_params(user, pin, slots, expiry_days)
    print(network)
    plan = ApiProviderResponse.objects.get(
        provider=network,
        
    )
    plan = list(filter(lambda pl: pl["variation_code"] == plan_id, plan.data.get("content").get("variations")))[0]
    amount = Decimal(plan.get('variation_amount'))
    
    return _create_link(
        user=user,
        service_type=ClaimLink.ServiceType.DATA,
        network=network,
        plan=plan,
        plan_name=plan.get("name"),
        amount_per_slot=amount,
        slots=slots,
        expiry_days=expiry_days,
        notes=notes,
    )


def _create_link(*, user, service_type, network, plan, plan_name, amount_per_slot, slots, expiry_days, notes):
    """Shared core: wallet debit + link + slots + transaction, all atomic.
    Both create_airtime_link and create_data_link funnel into this after
    doing their service-specific validation, so there's exactly one place
    that touches the wallet for link creation."""
    total_amount = amount_per_slot * slots

    wallet = _locked_wallet(user)
    if wallet.balance < total_amount:
        raise InsufficientBalanceError("Insufficient wallet balance.")

    balance_before = wallet.balance
    wallet.debit(total_amount)

    expiry_date = timezone.now() + timedelta(days=expiry_days) if expiry_days else None

    link = ClaimLink.objects.create(
        user=user,
        service_type=service_type,
        provider=network.name,
        network=network,
        plan=plan,
        plan_name=plan_name,
        amount_per_slot=amount_per_slot,
        total_slots=slots,
        expiry_date=expiry_date,
        notes=notes,
    )
    ClaimSlot.objects.bulk_create([ClaimSlot(link=link) for _ in range(slots)])

    Transaction.objects.create(
        user=user,
        transaction_type=service_type,
        amount=total_amount,
        wallet_balance_before=balance_before,
        wallet_balance_after=wallet.balance,
        status='success',
        service_provider=network.name,
        plan_name=f"{plan_name} (Claim Link x{slots})",
        recipient='Claim Link',
    )

    return link


@transaction.atomic
def disable_link(*, link):
    """Disable a link and refund the reserved value of its unclaimed slots.
    Safe to call on an already-inactive link — returns Decimal('0') as a
    no-op instead of double-refunding."""
    link = ClaimLink.objects.select_for_update().get(pk=link.pk)
    if link.status != ClaimLink.Status.ACTIVE:
        return Decimal('0')

    refund_amount = link.refundable_amount
    link.status = ClaimLink.Status.DISABLED
    link.save(update_fields=['status', 'updated_at'])

    if refund_amount > 0:
        wallet = _locked_wallet(link.user)
        balance_before = wallet.balance
        wallet.credit(refund_amount)
        Transaction.objects.create(
            user=link.user,
            transaction_type='refund',
            amount=refund_amount,
            wallet_balance_before=balance_before,
            wallet_balance_after=wallet.balance,
            status='success',
            service_provider=link.provider,
            plan_name=f"Refund: unclaimed slots on {link.link_id}",
            recipient='Wallet',
        )
    return refund_amount


@transaction.atomic
def claim_slot(*, link_id, phone_number, ip_address, user_agent):
    """Claim one slot on a link for `phone_number`, deliver the purchase,
    and notify the link's owner. Returns the claimed ClaimSlot.

    Raises a ClaimLinkError subclass if the link can't be claimed right
    now. Row-locks the link for the duration of the check-and-claim so two
    people hitting the last slot at the same instant can't both succeed.
    """
    link = ClaimLink.objects.select_for_update().get(link_id=link_id)

    if link.is_expired or link.status != ClaimLink.Status.ACTIVE:
        raise LinkNotClaimableError("This link is no longer active.")

    if link.slots.filter(claimed_by=phone_number, is_claimed=True).exists():
        raise AlreadyClaimedError("This phone number has already claimed this link.")

    slot = link.slots.select_for_update().filter(is_claimed=False).first()
    if not slot:
        # Someone else took the last slot in a concurrent request. Don't
        # write a status change here — their transaction already did, and
        # writing one from inside this exception path would just get
        # rolled back when this atomic block unwinds.
        raise LinkNotClaimableError("All slots have been claimed.")

    # Deliver BEFORE marking the slot claimed. If the upstream provider
    # call fails or raises, the whole atomic block rolls back — the slot
    # stays unclaimed and can be tried again, instead of being burned on a
    # delivery that never happened.
    _deliver_purchase(link=link, phone_number=phone_number)

    slot.claimed_by = phone_number
    slot.is_claimed = True
    slot.claimed_at = timezone.now()
    slot.ip_address = ip_address
    slot.user_agent = (user_agent or '')[:500]
    slot.save()

    link.used_slots = link.slots.filter(is_claimed=True).count()
    link.refresh_status()

    Notification.objects.create(
        user=link.user,
        title="Your claim link was used",
        message=f"{phone_number} just claimed {link.item_label} from link {link.link_id}.",
        category='claim_link',
    )

    return slot


def _deliver_purchase(*, link, phone_number):
    """Send the actual airtime/data to `phone_number`. """

    # determine if its Airtime or Data link
    link_type = link.service_type
    network = link.network.api_id
    if link_type == ClaimLink.ServiceType.DATA:
      plan = link.plan
      plan["serviceID"] = network
      response = vtu.buy_data_api(network, plan, phone_number)
      if response["success"]:
        print(response)
        return
      else:
        raise Exception(str(response["message"]))
    elif link_type == ClaimLink.ServiceType.AIRTIME:
      amount = float(link.amount_per_slot)
      response = vtu.buy_airtime_api(network, phone_number, amount)
      if response["success"]:
        print(response)
        return
      else:
        raise Exception(str(response["message"]))
    