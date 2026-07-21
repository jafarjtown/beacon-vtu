import io
from decimal import Decimal, InvalidOperation

import qrcode
from qrcode.constants import ERROR_CORRECT_M

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_http_methods
from django.http import HttpResponse
from django_ratelimit.decorators import ratelimit

from services.models import ServiceProvider, ServicePlan

from .models import ClaimLink
from . import services as link_services


@login_required
def my_links_view(request):
    """List the current user's claim links, optionally filtered by
    ?status=active|disabled|expired|completed."""
    links = ClaimLink.objects.filter(user=request.user)
    status = request.GET.get('status', 'all')
    if status != 'all':
        links = links.filter(status=status)
    return render(request, 'links/my_links.html', {'links': links, 'active_filter': status})


@login_required
def create_link_view(request):
    """Create a new claim link (airtime or data). All the wallet/link/
    transaction logic lives in services.py — this view just parses the
    form and turns service-layer errors into user-facing messages."""
    providers = ServiceProvider.objects.filter(
            category__in=['airtime', 'data'], is_active=True
        ).prefetch_related('plans')
    def build_context():
        
        data_providers = providers.filter(category='data')
        return {
            'providers': providers,
            'providers_airtime': providers.filter(category='airtime'),
            'providers_data': data_providers,
            'plans': ServicePlan.objects.filter(provider__in=data_providers, is_active=True),
        }

    if request.method == 'POST':
        category = request.POST.get('service_type')
        
        network = providers.get(api_id=request.POST.get('network'), is_active=True)
        notes = request.POST.get('notes', '')
        pin = request.POST.get('pin', '')

        try:
            slots = int(request.POST.get('slots', 1))
        except (TypeError, ValueError):
            messages.error(request, 'Enter a valid number of slots.')
            return redirect('links:create')

        try:
            expiry_days = int(request.POST.get('expiry') or 0)
        except (TypeError, ValueError):
            expiry_days = 0

        try:
            if category == 'airtime':
                amount_preset = request.POST.get('amount_preset')
                raw_amount = request.POST.get('amount') if amount_preset == 'custom' else amount_preset
                link = link_services.create_airtime_link(
                    user=request.user,
                    network=network,
                    amount_per_slot=raw_amount,
                    slots=slots,
                    expiry_days=expiry_days,
                    pin=pin,
                    notes=notes,
                )
            else:
                plan = request.POST.get('plan')
                link = link_services.create_data_link(
                    user=request.user,
                    network=network,
                    plan_id=plan,
                    slots=slots,
                    expiry_days=expiry_days,
                    pin=pin,
                    notes=notes,
                )
        except link_services.InvalidPinError as exc:
            # Re-render (rather than redirect) so pin_error reaches the
            # template on this same response — that's what lets the PIN
            # modal reopen already in its shake/error state instead of
            # just flashing a banner and making the person start over.
            context = build_context()
            context['pin_error'] = str(exc)
            return render(request, 'links/create_link.html', context)
        except link_services.ClaimLinkError as exc:
            messages.error(request, str(exc))
            return redirect('links:create')

        messages.success(request, f'Claim link created! Share: {link.share_url}')
        return redirect('links:my_links')

    return render(request, 'links/create_link.html', build_context())


@login_required
def link_details_view(request, link_id):
    """View a claim link's details and claim history."""
    link = get_object_or_404(ClaimLink, link_id=link_id, user=request.user)
    return render(request, 'links/link_details.html', {'link': link, 'slots': link.slots.all()})


@cache_control(max_age=3600, public=True)
def link_qr_code_view(request, link_id):
    """Render the claim link as a scannable PNG.

    Deliberately public (no login_required), same as claim_page_view — the
    QR code encodes the same claim URL that's meant to be handed out, so
    it carries no more sensitivity than the link itself. This is what lets
    it be scanned by someone who isn't logged in.

    Size is configurable via ?size=sm|md|lg for the my_links thumbnail vs
    the bigger link_details display, without needing two separate views.
    """
    link = get_object_or_404(ClaimLink, link_id=link_id)

    box_size = {'sm': 4, 'md': 8, 'lg': 12}.get(request.GET.get('size'), 8)

    qr = qrcode.QRCode(
        error_correction=ERROR_CORRECT_M,  # tolerates ~15% damage/dirt — good for printed/screenshotted codes
        box_size=box_size,
        border=2,
    )
    qr.add_data(link.share_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0B0E1F", back_color="#FFFFFF")

    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    return HttpResponse(buffer.getvalue(), content_type='image/png')


@login_required
@require_http_methods(["POST"])
def disable_link_view(request, link_id):
    """Disable a link. Unclaimed slots are refunded to the wallet."""
    link = get_object_or_404(ClaimLink, link_id=link_id, user=request.user)

    if link.status != ClaimLink.Status.ACTIVE:
        messages.error(request, 'This link is already inactive.')
    else:
        refunded = link_services.disable_link(link=link)
        if refunded:
            messages.success(request, f'Link disabled. ₦{refunded:,.2f} was refunded to your wallet.')
        else:
            messages.success(request, 'Link disabled.')

    return redirect('links:detail', link_id=link.link_id)


@ratelimit(key='ip', rate='20/m', method='POST', block=True)
def claim_page_view(request, link_id):
    """Public claim page — no login required. Rate-limited by IP since
    this is the one unauthenticated write path in the whole app."""
    link = get_object_or_404(ClaimLink, link_id=link_id)

    if link.status == ClaimLink.Status.DISABLED:
        return render(request, 'links/claim_failed.html', {'link': link, 'reason': 'disabled'})
    if link.is_expired:
        return render(request, 'links/claim_failed.html', {'link': link, 'reason': 'expired'})

    if request.method == 'POST':
        phone = request.POST.get('phone_number', '').strip()
        if not phone or len(phone) < 10:
            messages.error(request, 'Please enter a valid phone number.')
            return render(request, 'links/claim_page.html', {'link': link})

        try:
            slot = link_services.claim_slot(
                link_id=link.link_id,
                phone_number=phone,
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
            )
        except link_services.AlreadyClaimedError:
            return render(request, 'links/claim_failed.html', {'link': link, 'reason': 'already_claimed'})
        except link_services.LinkNotClaimableError:
            link.refresh_from_db()
            reason = 'exhausted' if link.remaining_slots == 0 else 'expired'
            return render(request, 'links/claim_failed.html', {'link': link, 'reason': reason})

        return render(request, 'links/claim_successful.html', {'slot': slot, 'link': link, 'claim': slot})

    return render(request, 'links/claim_page.html', {'link': link})
