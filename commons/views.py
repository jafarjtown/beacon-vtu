from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods
from services.models import ServiceProvider

from .models import (
    Family,
    FamilyMembership,
    MemberServicePreset,
    PurchaseRequest,
    ScheduledPurchase,
    ScheduledPurchaseRun,
)
from . import services as family_services


def _get_membership_or_404(family, user):
    """Authorization for VIEWING a family's pages — separate from the
    stricter per-ACTION permission checks already enforced inside
    services.py. A viewer with no special permissions can still reach
    the dashboard; they just won't see action buttons they can't use."""
    membership = family.memberships.filter(user=user).exclude(status=FamilyMembership.Status.REMOVED).first()
    if not membership:
        raise family_services.PermissionDeniedError("You're not part of this family.")
    return membership


def _redirect_with_error(request, exc, to, *args, **kwargs):
    messages.error(request, str(exc))
    return redirect(to, *args, **kwargs)


@login_required
def family_list_view(request):
    """Landing page — every family the user belongs to (owner or
    invited), plus a prompt to create one if they have none yet. Split
    into two querysets here (not filtered in the template) so the
    "no families yet" empty state can correctly account for someone who
    has pending invites but zero active families."""
    all_memberships = request.user.family_memberships.exclude(
        status=FamilyMembership.Status.REMOVED
    ).select_related('family', 'family__wallet')
    active_memberships = [m for m in all_memberships if m.status == FamilyMembership.Status.ACTIVE]
    pending_invites = [m for m in all_memberships if m.status == FamilyMembership.Status.INVITED]
    return render(request, 'beacon_family/family_list.html', {
        'active_memberships': active_memberships,
        'pending_invites': pending_invites,
    })


@login_required
def create_family_view(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if not name:
            messages.error(request, 'Give your family a name.')
            return redirect('beacon_family:create')
        family = family_services.create_family(owner=request.user, name=name)
        messages.success(request, f'"{family.name}" is set up — invite your first family member.')
        return redirect('beacon_family:dashboard', family_id=family.id)
    return render(request, 'beacon_family/create_family.html')


@login_required
def family_dashboard_view(request, family_id):
    family = get_object_or_404(Family, id=family_id)
    try:
        membership = _get_membership_or_404(family, request.user)
    except family_services.PermissionDeniedError as exc:
        return _redirect_with_error(request, exc, 'beacon_family:list')

    recent_runs = ScheduledPurchaseRun.objects.filter(
        schedule__family=family
    ).select_related('schedule', 'schedule__preset')[:8]

    upcoming = ScheduledPurchase.objects.filter(family=family, is_active=True).select_related(
        'preset', 'beneficiary', 'beneficiary__user'
    )[:5]
    pending_requests = PurchaseRequest.objects.filter(
        family=family, status=PurchaseRequest.Status.PENDING
    ).select_related('preset', 'requested_by', 'requested_by__user')

    context = {
        'family': family,
        'membership': membership,
        'wallet': getattr(family, 'wallet', None),
        'upcoming_schedules': upcoming,
        'pending_requests': pending_requests,
        'recent_runs': recent_runs,
        'member_count': family.active_members.count(),
    }
    return render(request, 'beacon_family/dashboard.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def invite_member_view(request, family_id):
    family = get_object_or_404(Family, id=family_id)
    if request.method == 'POST':
        from django.contrib.auth import get_user_model
        User = get_user_model()

        identifier = request.POST.get('email', '').strip()
        role = request.POST.get('role', FamilyMembership.Role.MEMBER)
        invitee = User.objects.filter(email__iexact=identifier).first()
        if not invitee:
            messages.error(request, f"No Beacon account found for {identifier}.")
            return redirect('beacon_family:invite_member', family_id=family.id)

        try:
            family_services.invite_member(family=family, invited_by=request.user, invitee=invitee, role=role)
        except family_services.FamilyError as exc:
            return _redirect_with_error(request, exc, 'beacon_family:invite_member', family_id=family.id)

        messages.success(request, f'Invited {invitee}.')
        return redirect('beacon_family:members', family_id=family.id)

    return render(request, 'beacon_family/invite_member.html', {'family': family})


@login_required
@require_http_methods(["POST"])
def accept_invite_view(request, membership_id):
    membership = get_object_or_404(FamilyMembership, id=membership_id)
    try:
        family_services.accept_invite(membership=membership, user=request.user)
    except family_services.FamilyError as exc:
        return _redirect_with_error(request, exc, 'beacon_family:list')
    messages.success(request, f'You joined {membership.family.name}.')
    return redirect('beacon_family:dashboard', family_id=membership.family_id)


@login_required
def members_view(request, family_id):
    family = get_object_or_404(Family, id=family_id)
    try:
        membership = _get_membership_or_404(family, request.user)
    except family_services.PermissionDeniedError as exc:
        return _redirect_with_error(request, exc, 'beacon_family:list')

    members = family.memberships.exclude(status=FamilyMembership.Status.REMOVED).select_related('user')
    return render(request, 'beacon_family/members.html', {
        'family': family, 'membership': membership, 'members': members,
    })


@login_required
@require_http_methods(["POST"])
def remove_member_view(request, family_id, membership_id):
    family = get_object_or_404(Family, id=family_id)
    target = get_object_or_404(FamilyMembership, id=membership_id, family=family)
    try:
        family_services.remove_member(family=family, removed_by=request.user, membership=target)
    except family_services.FamilyError as exc:
        return _redirect_with_error(request, exc, 'beacon_family:members', family_id=family.id)
    messages.success(request, f'{target.user} removed from the family.')
    return redirect('beacon_family:members', family_id=family.id)


@login_required
@require_http_methods(["GET", "POST"])
def spending_limits_view(request, family_id, membership_id):
    family = get_object_or_404(Family, id=family_id)
    target = get_object_or_404(FamilyMembership, id=membership_id, family=family)

    if request.method == 'POST':
        def parse_limit(field):
            raw = request.POST.get(field, '').strip()
            return Decimal(raw) if raw else None

        try:
            family_services.set_spending_limit(
                family=family, set_by=request.user, membership=target,
                daily=parse_limit('daily_limit'), weekly=parse_limit('weekly_limit'),
                monthly=parse_limit('monthly_limit'),
            )
        except (family_services.FamilyError, InvalidOperation) as exc:
            messages.error(request, str(exc) if isinstance(exc, family_services.FamilyError) else 'Enter valid amounts.')
            return redirect('beacon_family:spending_limits', family_id=family.id, membership_id=target.id)

        messages.success(request, f'Spending limits updated for {target.user}.')
        return redirect('beacon_family:members', family_id=family.id)

    return render(request, 'beacon_family/spending_limits.html', {'family': family, 'target': target})


@login_required
def presets_view(request, family_id):
    family = get_object_or_404(Family, id=family_id)
    try:
        membership = _get_membership_or_404(family, request.user)
    except family_services.PermissionDeniedError as exc:
        return _redirect_with_error(request, exc, 'beacon_family:list')

    presets = MemberServicePreset.objects.filter(membership__family=family).select_related(
        'membership', 'membership__user', 'provider'
    )
    if not request.user == family.owner:
      presets = presets.filter(membership__user=request.user)
    return render(request, 'beacon_family/presets.html', {
        'family': family, 'membership': membership, 'presets': presets,
    })


@login_required
@require_http_methods(["GET", "POST"])
def create_preset_view(request, family_id):
    family = get_object_or_404(Family, id=family_id)
    membership = get_object_or_404(FamilyMembership, family=family, user=request.user)
    providers = ServiceProvider.objects.all()
    if request.method == 'POST':
        target_membership_id = request.POST.get('membership_id')
        target = get_object_or_404(FamilyMembership, id=target_membership_id, family=family)
        provider = get_object_or_404(ServiceProvider, api_id=request.POST.get("service_provider"))
        service_type = request.POST.get('service_type')
        # Setting up a preset for yourself is always fine; setting one up
        # on someone else's behalf (e.g. a young child's line) requires
        # can_manage_services — mirrors the same "self or admin" pattern
        # used for who's allowed to touch a member's saved services.
        if target.id != membership.id and not membership.can_manage_services:
            messages.error(request, "You don't have permission to add services for other members.")
            return redirect('beacon_family:create_preset', family_id=family.id)

        m_service_preset = MemberServicePreset.objects.create(
            membership=target,
            service_type=service_type,
            label=request.POST.get('label', '').strip(),
            provider=provider,
            recipient_identifier=request.POST.get('recipient_identifier', '').strip(),
        )
        
          
        messages.success(request, 'Service saved.')
        return redirect('beacon_family:presets', family_id=family.id)

    members = family.memberships.filter(status=FamilyMembership.Status.ACTIVE).select_related('user')
    return render(request, 'beacon_family/create_preset.html', {'family': family, 'members': members, 'providers': providers})


@login_required
def schedules_view(request, family_id):
    family = get_object_or_404(Family, id=family_id)
    try:
        membership = _get_membership_or_404(family, request.user)
    except family_services.PermissionDeniedError as exc:
        return _redirect_with_error(request, exc, 'beacon_family:list')

    schedules = ScheduledPurchase.objects.filter(family=family).select_related(
        'preset', 'beneficiary', 'beneficiary__user'
    )
    return render(request, 'beacon_family/schedules.html', {
        'family': family, 'membership': membership, 'schedules': schedules,
    })


@login_required
@require_http_methods(["GET", "POST"])
def create_schedule_view(request, family_id):
    family = get_object_or_404(Family, id=family_id)

    if request.method == 'POST':
        preset = get_object_or_404(MemberServicePreset, id=request.POST.get('preset'), membership__family=family)
        frequency = request.POST.get('frequency')
        amount = request.POST.get('amount')
        plan = {}
        if preset.service_type == preset.ServiceType.DATA:
          plan_id = request.POST.get('service_plan')
          plan = preset.provider.api_response
          plan = list(filter(lambda pl: pl["variation_code"] == plan_id, plan.data.get("content").get("variations")))[0]
          amount = plan.get('variation_amount')
        try:
            family_services.create_scheduled_purchase(
                family=family, created_by=request.user, preset=preset,
                amount=amount, frequency=frequency,
                day_of_week=request.POST.get('day_of_week') or None,
                day_of_month=request.POST.get('day_of_month') or None,
                plan=plan,
            )
        except (family_services.FamilyError, InvalidOperation) as exc:
            messages.error(request, str(exc) if isinstance(exc, family_services.FamilyError) else 'Enter a valid amount.')
            return redirect('beacon_family:create_schedule', family_id=family.id)

        messages.success(request, 'Schedule created.')
        return redirect('beacon_family:schedules', family_id=family.id)

    presets = MemberServicePreset.objects.filter(membership__family=family).select_related('membership__user')
    return render(request, 'beacon_family/create_schedule.html', {'family': family, 'presets': presets})


@login_required
@require_http_methods(["POST"])
def toggle_schedule_view(request, family_id, schedule_id):
    family = get_object_or_404(Family, id=family_id)
    schedule = get_object_or_404(ScheduledPurchase, id=schedule_id, family=family)
    membership = get_object_or_404(FamilyMembership, family=family, user=request.user)

    if not membership.can_create_schedule:
        messages.error(request, "You don't have permission to manage schedules.")
        return redirect('beacon_family:schedules', family_id=family.id)

    schedule.is_active = not schedule.is_active
    schedule.save(update_fields=['is_active', 'updated_at'])
    messages.success(request, 'Schedule paused.' if not schedule.is_active else 'Schedule resumed.')
    return redirect('beacon_family:schedules', family_id=family.id)


@login_required
def requests_view(request, family_id):
    family = get_object_or_404(Family, id=family_id)
    try:
        membership = _get_membership_or_404(family, request.user)
    except family_services.PermissionDeniedError as exc:
        return _redirect_with_error(request, exc, 'beacon_family:list')

    requests_qs = PurchaseRequest.objects.filter(family=family).select_related(
        'preset', 'requested_by', 'requested_by__user'
    )
    return render(request, 'beacon_family/requests.html', {
        'family': family, 'membership': membership, 'requests': requests_qs,
    })


@login_required
@require_http_methods(["GET", "POST"])
def create_request_view(request, family_id):
    family = get_object_or_404(Family, id=family_id)
    membership = get_object_or_404(FamilyMembership, family=family, user=request.user)

    if request.method == 'POST':
        preset = get_object_or_404(MemberServicePreset, id=request.POST.get('preset'), membership=membership)
        amount = request.POST.get('amount')
        plan={}
        if preset.service_type == 'data':
          plan_id = request.POST.get('service_plan')
          plan = preset.provider.api_response
          plan = list(filter(lambda pl: pl["variation_code"] == plan_id, plan.data.get("content").get("variations")))[0]
          amount = plan.get('variation_amount')
        try:
            family_services.request_purchase(
                family=family, requested_by=request.user, preset=preset,
                amount=amount, note=request.POST.get('note', ''),
                plan=plan
            )
        except (family_services.FamilyError, InvalidOperation) as exc:
            messages.error(request, str(exc) if isinstance(exc, family_services.FamilyError) else 'Enter a valid amount.')
            return redirect('beacon_family:create_request', family_id=family.id)

        messages.success(request, 'Request sent to the family owner.')
        return redirect('beacon_family:requests', family_id=family.id)

    own_presets = MemberServicePreset.objects.filter(membership=membership)
    return render(request, 'beacon_family/create_request.html', {'family': family, 'presets': own_presets})


@login_required
@require_http_methods(["POST"])
def approve_request_view(request, family_id, request_id):
    family = get_object_or_404(Family, id=family_id)
    purchase_request = get_object_or_404(PurchaseRequest, id=request_id, family=family)
    try:
        family_services.approve_purchase_request(request=purchase_request, reviewed_by=request.user)
    except family_services.FamilyError as exc:
        return _redirect_with_error(request, exc, 'beacon_family:requests', family_id=family.id)
    messages.success(request, f'Approved — ₦{purchase_request.amount:,.2f} sent to {purchase_request.requested_by.user}.')
    return redirect('beacon_family:requests', family_id=family.id)


@login_required
@require_http_methods(["POST"])
def reject_request_view(request, family_id, request_id):
    family = get_object_or_404(Family, id=family_id)
    purchase_request = get_object_or_404(PurchaseRequest, id=request_id, family=family)
    try:
        family_services.reject_purchase_request(
            request=purchase_request, reviewed_by=request.user, reason=request.POST.get('reason', ''),
        )
    except family_services.FamilyError as exc:
        return _redirect_with_error(request, exc, 'beacon_family:requests', family_id=family.id)
    messages.success(request, 'Request rejected.')
    return redirect('beacon_family:requests', family_id=family.id)


@login_required
@require_http_methods(["GET", "POST"])
def fund_wallet_view(request, family_id):
    family = get_object_or_404(Family, id=family_id)

    if request.method == 'POST':
        try:
            family_services.fund_family_wallet(
                family=family, funded_by=request.user, amount=request.POST.get('amount'),
            )
        except (family_services.FamilyError, InvalidOperation) as exc:
            messages.error(request, str(exc) if isinstance(exc, family_services.FamilyError) else 'Enter a valid amount.')
            return redirect('beacon_family:fund_wallet', family_id=family.id)

        messages.success(request, 'Family wallet funded.')
        return redirect('beacon_family:dashboard', family_id=family.id)

    recent_fundings = family.fundings.select_related('funded_by')[:10]
    return render(request, 'beacon_family/fund_wallet.html', {'family': family, 'recent_fundings': recent_fundings})
