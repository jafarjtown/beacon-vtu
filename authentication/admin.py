from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Profile


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    verbose_name_plural = 'Profile'
    fk_name = 'user'


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ['email', 'username', 'first_name', 'last_name', 'is_email_verified', 'is_staff', 'date_joined']
    list_filter = ['is_email_verified', 'is_staff', 'is_superuser', 'date_joined']
    search_fields = ['email', 'username', 'first_name', 'last_name']
    ordering = ['-date_joined']
    inlines = [ProfileInline]
    
    fieldsets = UserAdmin.fieldsets + (
        ('Verification', {'fields': ('is_email_verified', 'email_verification_token')}),
        ('Referral', {'fields': ('referral_code', 'referred_by')}),
        ('Security', {'fields': ('last_login_ip',)}),
    )


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'city', 'state', 'country', 'profile_completion', 'updated_at']
    list_filter = ['country', 'profile_completion']
    search_fields = ['user__email', 'user__username']