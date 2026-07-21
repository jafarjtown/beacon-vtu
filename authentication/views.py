
import uuid
from datetime import datetime, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_protect
from django_ratelimit.decorators import ratelimit
from .forms import (
    UserRegistrationForm, UserLoginForm, PasswordResetRequestForm,
    PasswordResetConfirmForm, ProfileUpdateForm, ChangePasswordForm,
    NotificationSettingsForm,
    TransactionPinForm
)
from .models import Profile
from core.models import SiteSettings
from wallet.models import Wallet
from links.services import _verify_pin
User = get_user_model()


def send_verification_email(user, request):
    """Send email verification link to user"""
    token = uuid.uuid4().hex
    user.email_verification_token = token
    user.save()
    
    verification_url = request.build_absolute_uri(
        f'/accounts/verify-email/{token}/'
    )
    
    subject = 'Verify Your Email - VTU Pro'
    html_message = render_to_string('accounts/email/verify_email.html', {
        'user': user,
        'verification_url': verification_url,
        'site_name': SiteSettings.load().site_name,
    })
    plain_message = strip_tags(html_message)
    
    send_mail(
        subject,
        plain_message,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        html_message=html_message,
        fail_silently=True,
    )


def send_password_reset_email(user, request):
    """Send password reset link to user"""
    token = uuid.uuid4().hex
    user.password_reset_token = token
    user.password_reset_expires = datetime.now() + timedelta(hours=1)
    user.save()
    
    reset_url = request.build_absolute_uri(
        f'/accounts/reset-password/{token}/'
    )
    
    subject = 'Password Reset Request - VTU Pro'
    html_message = render_to_string('accounts/email/reset_password.html', {
        'user': user,
        'reset_url': reset_url,
        'site_name': SiteSettings.load().site_name,
    })
    plain_message = strip_tags(html_message)
    
    send_mail(
        subject,
        plain_message,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        html_message=html_message,
        fail_silently=True,
    )


@ratelimit(key='ip', rate='5/m', method='POST')
def register_view(request):
    """User registration view with email verification"""
    if request.user.is_authenticated:
        return redirect('dashboard:index')
    
    if request.method == 'POST':
        
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            print(78)
            user = form.save(commit=False)
            user.username = user.email.split('@')[0]
            user.phone_number = form.cleaned_data['phone_number']
            
            # Handle referral
            referrer = form.cleaned_data.get('referral_code')
            if referrer:
                user.referred_by = referrer
            
            user.save()
            
            # Create wallet
            Wallet.objects.create(user=user)
            
            # Send verification email
            send_verification_email(user, request)
            
            messages.success(
                request,
                'Account created successfully! Please check your email to verify your account.'
            )
            return redirect('accounts:login')
    else:
        form = UserRegistrationForm()
    
    return render(request, 'accounts/register.html', {'form': form})


@ratelimit(key='ip', rate='10/m', method='POST')
def login_view(request):
    """User login view"""
    if request.user.is_authenticated:
        return redirect('dashboard:index')
    
    if request.method == 'POST':
        form = UserLoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']
            remember = form.cleaned_data.get('remember_me', False)
            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                messages.error(request, 'Invalid email or password.')
                return render(request, 'accounts/login.html', {'form': form})
            
            user = authenticate(request, username=user.email, password=password)
            print(user)
            
            if user is not None:
                if not user.is_email_verified:
                    messages.warning(
                        request,
                        'Please verify your email before logging in. '
                        '<a href="/accounts/resend-verification/" class="alert-link">Resend verification email</a>'
                    )
                    return render(request, 'accounts/login.html', {'form': form})
                
                login(request, user)
                
                # Update last login IP
                if request.META.get('HTTP_X_FORWARDED_FOR'):
                    user.last_login_ip = request.META['HTTP_X_FORWARDED_FOR'].split(',')[0].strip()
                else:
                    user.last_login_ip = request.META.get('REMOTE_ADDR')
                user.save()
                
                # Handle remember me
                if not remember:
                    request.session.set_expiry(0)
                else:
                    request.session.set_expiry(1209600)  # 2 weeks
                
                messages.success(request, f'Welcome back, {user.get_full_name() or user.email}!')
                return redirect('dashboard:index')
            else:
                messages.error(request, 'Invalid email or password.')
    else:
        form = UserLoginForm()
    
    return render(request, 'accounts/login.html', {'form': form})


def logout_view(request):
    """User logout view"""
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('core:landing')


def verify_email_view(request, token):
    """Email verification view"""
    try:
        user = User.objects.get(email_verification_token=token)
        if user.is_email_verified:
            messages.info(request, 'Your email is already verified.')
        else:
            user.is_email_verified = True
            user.email_verification_token = None
            user.save()
            messages.success(request, 'Email verified successfully! You can now log in.')
    except User.DoesNotExist:
        messages.error(request, 'Invalid or expired verification link.')
    
    return redirect('accounts:login')


def resend_verification_view(request):
    """Resend verification email"""
    if request.method == 'POST':
        email = request.POST.get('email')
        try:
            user = User.objects.get(email=email)
            if not user.is_email_verified:
                send_verification_email(user, request)
                messages.success(request, 'Verification email sent! Please check your inbox.')
            else:
                messages.info(request, 'Your email is already verified.')
        except User.DoesNotExist:
            messages.error(request, 'No account found with this email.')
    
    return render(request, 'accounts/resend_verification.html')


@ratelimit(key='ip', rate='3/m', method='POST')
def forgot_password_view(request):
    """Forgot password view"""
    if request.method == 'POST':
        form = PasswordResetRequestForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            try:
                user = User.objects.get(email=email)
                send_password_reset_email(user, request)
                messages.success(
                    request,
                    'Password reset instructions have been sent to your email.'
                )
                return redirect('accounts:login')
            except User.DoesNotExist:
                messages.error(request, 'No account found with this email.')
    else:
        form = PasswordResetRequestForm()
    
    return render(request, 'accounts/forgot_password.html', {'form': form})


def reset_password_view(request, token):
    """Password reset confirmation view"""
    try:
        user = User.objects.get(
            password_reset_token=token,
            password_reset_expires__gt=datetime.now()
        )
    except User.DoesNotExist:
        messages.error(request, 'Invalid or expired reset link.')
        return redirect('accounts:forgot_password')
    
    if request.method == 'POST':
        form = PasswordResetConfirmForm(request.POST)
        if form.is_valid():
            user.set_password(form.cleaned_data['password1'])
            user.password_reset_token = None
            user.password_reset_expires = None
            user.save()
            messages.success(request, 'Password reset successfully! Please log in with your new password.')
            return redirect('accounts:login')
    else:
        form = PasswordResetConfirmForm()
    
    return render(request, 'accounts/reset_password.html', {'form': form})


@login_required
def profile_view(request):
    """User profile view"""
    profile = request.user.profile
    profile.calculate_completion()
    
    if request.method == 'POST':
        form = ProfileUpdateForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            # Update user fields
            request.user.first_name = form.cleaned_data.get('first_name', request.user.first_name)
            request.user.last_name = form.cleaned_data.get('last_name', request.user.last_name)
            request.user.phone_number = form.cleaned_data.get('phone_number', request.user.phone_number)
            request.user.save()
            
            form.save()
            profile.calculate_completion()
            messages.success(request, 'Profile updated successfully!')
            return redirect('accounts:profile')
    else:
        initial = {
            'first_name': request.user.first_name,
            'last_name': request.user.last_name,
            'email': request.user.email,
            'phone_number': request.user.phone_number,
        }
        form = ProfileUpdateForm(instance=profile, initial=initial)
    
    context = {
        'form': form,
        'profile': profile,
        'referral_link': request.build_absolute_uri(f'/accounts/register/?ref={request.user.referral_code}'),
    }
    return render(request, 'accounts/profile.html', context)


@login_required
def change_password_view(request):
    """Change password view"""
    if request.method == 'POST':
        form = ChangePasswordForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, 'Password changed successfully!')
            return redirect('accounts:profile')
    else:
        form = ChangePasswordForm(request.user)
    
    return render(request, 'accounts/change_password.html', {'form': form})


@login_required
def settings_view(request):
    password_form = ChangePasswordForm(request.user)
    pin_form = TransactionPinForm(user=request.user)

    if request.method == "POST":
        form_id = request.POST.get("form_id")

        # Change password
        if form_id == "password":
            password_form = ChangePasswordForm(request.user, request.POST)

            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, "Password updated successfully.")
                return redirect("accounts:settings")

        # Create/Update transaction PIN
        elif form_id == "transaction_pin":
            pin_form = TransactionPinForm(
                request.POST,
                user=request.user
            )

            if pin_form.is_valid():
                pin_form.save()
                messages.success(request, "Transaction PIN updated successfully.")
                return redirect("accounts:settings")

    context = {
        "password_form": password_form,
        "pin_form": pin_form,
    }

    return render(request, "accounts/settings.html", context)


@login_required
def delete_account_view(request):
    """Delete account view"""
    if request.method == 'POST':
        password = request.POST.get('password')
        user = authenticate(request, username=request.user.username, password=password)
        if user is not None:
            user.delete()
            logout(request)
            messages.success(request, 'Your account has been deleted.')
            return redirect('core:landing')
        else:
            messages.error(request, 'Incorrect password. Account deletion cancelled.')
    
    return render(request, 'accounts/delete_account.html')


def verify_user_pin(request):
  success = False
  message = ""
  pin = request.GET.get('pin')
  try:
    _verify_pin(request.user, pin)
    success = True
    message = "Pin verify successfully"
  except Exception as e:
    message = str(e)
  return JsonResponse({
    "success": success,
    "message": message
  })