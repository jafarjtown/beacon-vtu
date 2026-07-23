"""
Business logic for Beacon Family — the shared wallet, membership/roles,
spending limits, recurring schedules, and one-off purchase requests.

Kept out of views.py for the same reason as the links app: every function
here either returns the object it created/affected or raises a
FamilyError subclass, so views (and later, a periodic task or an API
endpoint) can call these without re-deriving the wallet/permission logic
each time.

Requires python-dateutil for correct calendar-month arithmetic
(`pip install python-dateutil`) — plain timedelta math gets "every 1st of
the month" subtly wrong across months of different lengths.
"""
from datetime import timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from services import vtu

from .models import (
    Family,
    FamilyMembership,
    FamilyWallet,
    FamilyWalletFunding,
    MemberServicePreset,
    PurchaseRequest,
    ScheduledPurchase,
    ScheduledPurchaseRun,
    SpendingLimit,
)

MAX_MEMBERS_PER_FAMILY = 20


class FamilyError(Exception):
    """Base class for every failure in this module."""


class PermissionDeniedError(FamilyError):
    pass


class AlreadyMemberError(FamilyError):
    pass


class InsufficientBalanceError(FamilyError):
    pass


class SpendingLimitExceededError(FamilyError):
    pass


class InvalidScheduleError(FamilyError):
    pass


# ==================================================================
# Family + membership
# ==================================================================

@transaction.atomic
def create_family(*, owner, name):
    """Create a family, its wallet, and the owner's own membership, all
    in one step — there's no useful state where a Family exists without
    both of those, so callers never have to remember to create them."""
    family = Family.objects.create(owner=owner, name=name)
    FamilyWallet.objects.create(family=family)
    FamilyMembership.objects.create(
        family=family,
        user=owner,
        role=FamilyMembership.Role.OWNER,
        status=FamilyMembership.Status.ACTIVE,
        joined_at=timezone.now(),
    )
    return family


def _require(condition, message):
    if not condition:
        raise PermissionDeniedError(message)


def invite_member(*, family, invited_by, invitee, role=FamilyMembership.Role.MEMBER):
    """Invite `invitee` (a User) into `family`. Doesn't auto-activate —
    see accept_invite for that step."""
    inviter_membership = _get_active_membership(family, invited_by)
    _require(inviter_membership.can_add_members, "You don't have permission to add members.")

    if FamilyMembership.objects.filter(family=family, user=invitee).exists():
        raise AlreadyMemberError("This person is already part of the family.")

    if family.memberships.exclude(status=FamilyMembership.Status.REMOVED).count() >= MAX_MEMBERS_PER_FAMILY:
        raise FamilyError(f"Families are limited to {MAX_MEMBERS_PER_FAMILY} members.")

    return FamilyMembership.objects.create(
        family=family, user=invitee, role=role, invited_by=invited_by,
    )


def accept_invite(*, membership, user):
    if membership.user_id != user.id:
        raise PermissionDeniedError("This invite isn't addressed to you.")
    membership.status = FamilyMembership.Status.ACTIVE
    membership.joined_at = timezone.now()
    membership.save(update_fields=['status', 'joined_at'])
    return membership


def remove_member(*, family, removed_by, membership):
    remover_membership = _get_active_membership(family, removed_by)
    _require(remover_membership.can_remove_members, "You don't have permission to remove members.")
    if membership.role == FamilyMembership.Role.OWNER:
        raise FamilyError("The family owner can't be removed.")

    membership.status = FamilyMembership.Status.REMOVED
    membership.removed_at = timezone.now()
    membership.save(update_fields=['status', 'removed_at'])
    return membership


def _get_active_membership(family, user):
    try:
        return family.memberships.get(user=user, status=FamilyMembership.Status.ACTIVE)
    except FamilyMembership.DoesNotExist:
        raise PermissionDeniedError("You're not an active member of this family.")


# ==================================================================
# Wallet funding
# ==================================================================

@transaction.atomic
def fund_family_wallet(*, family, funded_by, amount):
    """Add money to the shared pot. Deliberately open to any active
    member, not just the owner — see the note on FamilyMembership."""
    amount = Decimal(amount)
    if amount <= 0:
        raise FamilyError("Amount must be greater than zero.")
    if amount > funded_by.wallet.balance:
        raise FamilyError("Insufficiant wallet balance, fund your wallet and try again.")
      
    membership = _get_active_membership(family, funded_by)
    _require(membership.can_fund_wallet, "You don't have permission to fund this wallet.")

    wallet = FamilyWallet.objects.select_for_update().get(family=family)
    wallet.credit(amount)
    funded_by.wallet.debit(amount)
    FamilyWalletFunding.objects.create(family=family, funded_by=funded_by, amount=amount)
    return wallet


# ==================================================================
# Spending limits
# ==================================================================

def set_spending_limit(*, family, set_by, membership, daily=None, weekly=None, monthly=None):
    setter_membership = _get_active_membership(family, set_by)
    _require(setter_membership.can_set_spending_limits, "You don't have permission to set spending limits.")

    limit, _ = SpendingLimit.objects.get_or_create(membership=membership)
    limit.daily_limit = daily
    limit.weekly_limit = weekly
    limit.monthly_limit = monthly
    limit.save()
    return limit


def _period_start(period, now):
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == 'daily':
        return start_of_day
    if period == 'weekly':
        return start_of_day - timedelta(days=start_of_day.weekday())
    if period == 'monthly':
        return start_of_day.replace(day=1)
    raise ValueError(f"unknown period {period!r}")


def _spent_in_period(membership, period_start):
    """Sum of everything actually paid out for this member since
    period_start — successful scheduled runs plus approved one-off
    requests. Used to enforce spending limits."""
    schedule_spend = ScheduledPurchaseRun.objects.filter(
        schedule__beneficiary=membership,
        status=ScheduledPurchaseRun.Status.SUCCESS,
        ran_at__gte=period_start,
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    request_spend = PurchaseRequest.objects.filter(
        requested_by=membership,
        status=PurchaseRequest.Status.APPROVED,
        reviewed_at__gte=period_start,
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    return schedule_spend + request_spend


def _check_spending_limit(membership, amount):
    try:
        limit = membership.spending_limit
    except SpendingLimit.DoesNotExist:
        return  # no limit configured — unrestricted

    now = timezone.now()
    checks = (
        ('daily', limit.daily_limit),
        ('weekly', limit.weekly_limit),
        ('monthly', limit.monthly_limit),
    )
    for period, cap in checks:
        if cap is None:
            continue
        spent = _spent_in_period(membership, _period_start(period, now))
        if spent + amount > cap:
            raise SpendingLimitExceededError(
                f"This would exceed the {period} spending limit for {membership.user} "
                f"(₦{spent:,.2f} already spent of ₦{cap:,.2f})."
            )


# ==================================================================
# Purchase requests (member-initiated, owner-approved)
# ==================================================================

def request_purchase(*, family, requested_by, preset, amount, note="", plan):
    amount = Decimal(amount)
    if amount <= 0:
        raise FamilyError("Amount must be greater than zero.")

    membership = _get_active_membership(family, requested_by)
    _require(membership.can_request_purchase, "You don't have permission to request purchases.")
    if preset.membership_id != membership.id:
        raise PermissionDeniedError("You can only request purchases using your own saved services.")

    return PurchaseRequest.objects.create(
        family=family, requested_by=membership, preset=preset, amount=amount, note=note, plan=plan,
    )


@transaction.atomic
def approve_purchase_request(*, request, reviewed_by):
    """Approve and immediately execute a pending request. Left PENDING
    (not auto-rejected) on insufficient funds or a limit breach, so the
    owner can top up the wallet or adjust the limit and try again rather
    than the member having to re-submit the whole request."""
    reviewer_membership = _get_active_membership(request.family, reviewed_by)
    _require(reviewer_membership.can_approve_requests, "You don't have permission to approve requests.")

    if request.status != PurchaseRequest.Status.PENDING:
        raise FamilyError("This request has already been reviewed.")

    wallet = FamilyWallet.objects.select_for_update().get(family=request.family)
    if wallet.balance < request.amount:
        raise InsufficientBalanceError("The family wallet doesn't have enough balance for this request.")

    _check_spending_limit(request.requested_by, request.amount)
    
    reference = _deliver_purchase(preset=request.preset, amount=request.amount, plan=request.plan)
    
    wallet.debit(request.amount)
    request.status = PurchaseRequest.Status.APPROVED
    request.reviewed_by = reviewed_by
    request.reviewed_at = timezone.now()
    request.reference = reference
    request.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'reference'])
    return request


def reject_purchase_request(*, request, reviewed_by, reason=""):
    reviewer_membership = _get_active_membership(request.family, reviewed_by)
    _require(reviewer_membership.can_approve_requests, "You don't have permission to review requests.")

    if request.status != PurchaseRequest.Status.PENDING:
        raise FamilyError("This request has already been reviewed.")

    request.status = PurchaseRequest.Status.REJECTED
    request.reviewed_by = reviewed_by
    request.reviewed_at = timezone.now()
    request.rejection_reason = reason
    request.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'rejection_reason'])
    return request


# ==================================================================
# Scheduled (recurring) purchases
# ==================================================================

def create_scheduled_purchase(*, family, created_by, preset, amount, frequency,
                               day_of_week=None, day_of_month=None, plan={}):
    """beneficiary is deliberately NOT a separate parameter — it's always
    preset.membership. A preset already *is* a specific member's saved
    recipient details, so there's no legitimate case where the person a
    schedule pays out to should differ from whose preset it's using.
    Keeping them as two independent params earlier would have let a
    schedule bill against the wrong member's spending limit while
    delivering to someone else's phone number."""
    creator_membership = _get_active_membership(family, created_by)
    _require(creator_membership.can_create_schedule, "You don't have permission to create schedules.")

    beneficiary = preset.membership
    if beneficiary.family_id != family.id:
        raise InvalidScheduleError("That saved service doesn't belong to this family.")

    amount = Decimal(amount)
    if amount <= 0:
        raise InvalidScheduleError("Amount must be greater than zero.")
    if frequency == ScheduledPurchase.Frequency.WEEKLY and day_of_week is None:
        raise InvalidScheduleError("Weekly schedules need a day of the week.")
    if frequency == ScheduledPurchase.Frequency.MONTHLY and day_of_month is None:
        raise InvalidScheduleError("Monthly schedules need a day of the month.")

    next_run_at = _compute_next_run(
        frequency=frequency, day_of_week=day_of_week, day_of_month=day_of_month, from_dt=timezone.now(),
    )

    return ScheduledPurchase.objects.create(
        family=family, beneficiary=beneficiary, preset=preset, amount=amount, frequency=frequency,
        day_of_week=day_of_week, day_of_month=day_of_month, next_run_at=next_run_at, created_by=created_by,
        plan=plan
    )


def _compute_next_run(*, frequency, day_of_week, day_of_month, from_dt):
    """The first run should feel intuitive — 'every Monday' set up on a
    Wednesday should fire THIS coming Monday, not a week later than that."""
    if frequency == ScheduledPurchase.Frequency.DAILY:
        return from_dt + timedelta(days=1)

    if frequency == ScheduledPurchase.Frequency.WEEKLY:
        days_ahead = (int(day_of_week) - from_dt.weekday()) % 7
        days_ahead = days_ahead or 7  # today exactly -> next week, not today
        return from_dt + timedelta(days=days_ahead)

    if frequency == ScheduledPurchase.Frequency.MONTHLY:
        candidate = from_dt.replace(day=min(int(day_of_month), 28))  # safe mid-month anchor
        candidate = _set_day_clamped(candidate, int(day_of_month))
        if candidate <= from_dt:
            candidate = _set_day_clamped(candidate + relativedelta(months=1), int(day_of_month))
        return candidate

    raise ValueError(f"unknown frequency {frequency!r}")


def _set_day_clamped(dt, day):
    """Set the day-of-month, clamped to the last real day of that month —
    'the 31st' on a schedule created in February shouldn't crash, it
    should land on the 28th/29th that month and the 31st whenever the
    month actually has one."""
    next_month = dt.replace(day=1) + relativedelta(months=1)
    last_day_of_month = (next_month - timedelta(days=1)).day
    return dt.replace(day=min(day, last_day_of_month))


@transaction.atomic
def _run_single_schedule(schedule, now):
    """Execute (or skip) one due schedule, and always advance
    next_run_at regardless of outcome — a failed attempt (e.g. the
    family wallet ran dry) shouldn't leave the schedule permanently
    'due', which would just make it retry-spam every time the periodic
    task runs. It gets one attempt per cycle, logged either way, and
    tries again next cycle."""
    wallet = FamilyWallet.objects.select_for_update().get(family_id=schedule.family_id)

    status = ScheduledPurchaseRun.Status.SUCCESS
    note = ''
    reference = ''

    if wallet.balance < schedule.amount:
        status = ScheduledPurchaseRun.Status.FAILED_INSUFFICIENT_FUNDS
        note = 'Family wallet balance was too low at run time.'
    else:
        try:
            _check_spending_limit(schedule.beneficiary, schedule.amount)
        except SpendingLimitExceededError as exc:
            status = ScheduledPurchaseRun.Status.FAILED_LIMIT_EXCEEDED
            note = str(exc)

    if status == ScheduledPurchaseRun.Status.SUCCESS:
        reference = _deliver_purchase(preset=schedule.preset, amount=schedule.amount)
        wallet.debit(schedule.amount)

    ScheduledPurchaseRun.objects.create(
        schedule=schedule, status=status, amount=schedule.amount, reference=reference, note=note,
    )

    schedule.next_run_at = _compute_next_run(
        frequency=schedule.frequency, day_of_week=schedule.day_of_week,
        day_of_month=schedule.day_of_month, from_dt=now,
    )
    schedule.save(update_fields=['next_run_at', 'updated_at'])


def run_due_scheduled_purchases(now=None):
    """Entry point for a periodic task (Celery beat / cron / management
    command) — NOT meant to be called from a request. Each due schedule
    runs in its own atomic block via _run_single_schedule, so one
    family's failure (bad wallet lock, delivery error) can't take down
    the whole batch."""
    now = now or timezone.now()
    due = ScheduledPurchase.objects.filter(is_active=True, next_run_at__lte=now)
    results = []
    for schedule in due:
        try:
            _run_single_schedule(schedule, now)
            results.append((schedule, True))
        except Exception as exc:  # noqa: BLE001 — intentionally broad: one bad schedule must not stop the rest
            results.append((schedule, False))
            ScheduledPurchaseRun.objects.create(
                schedule=schedule, status=ScheduledPurchaseRun.Status.FAILED_OTHER,
                amount=schedule.amount, note=str(exc)[:255],
            )
    return results


def _deliver_purchase(*, preset, amount, plan=None):
    """Send the actual airtime/data/bill payment for a preset's saved
    recipient. Placeholder — wire this up to your VTU provider client,
    the same way links.services._deliver_purchase is meant to be. Should
    return a reference string, or raise on failure so the caller's
    atomic block rolls back the wallet debit."""
    recipient_identifier = preset.recipient_identifier
    provider = preset.provider
    if preset.service_type == preset.ServiceType.DATA:
      print("Data purchase")
      plan["serviceID"] = provider.api_id
      response = vtu.buy_data_api(provider.api_id, plan, recipient_identifier)
      if response["success"]:
        print(response)
        return
      else:
        raise FamilyError(str(response["message"]))
    elif preset.service_type == preset.ServiceType.AIRTIME:
      print("Airtime purchase")
      amount = float(amount)
      response = vtu.buy_airtime_api(provider.api_id, recipient_identifier, amount)
      if response["success"]:
        print(response)
        return
      else:
        raise FamilyError(str(response["message"]))
    return ''