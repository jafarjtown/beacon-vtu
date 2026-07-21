from django.contrib import admin, messages
from .models import ServiceProvider, ServicePlan, Purchase, ApiProviderResponse

@admin.register(ServiceProvider)
class ServiceProviderAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'code', 'is_active', 'requires_validation']
    list_filter = ['category', 'is_active']
    search_fields = ['name', 'code']

@admin.register(ServicePlan)
class ServicePlanAdmin(admin.ModelAdmin):
    list_display = ['provider', 'name', 'amount', 'validity', 'is_active']
    list_filter = ['provider__category', 'is_active']
    search_fields = ['name', 'provider__name']
    list_select_related = ['provider']

@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'plan', 'beneficiary', 'amount', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['user__email', 'beneficiary', 'api_reference']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(ApiProviderResponse)
class ApiProviderResponseAdmin(admin.ModelAdmin):
    list_display = (
        "provider",
        "updated_at",
        "created_at",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
    )
    search_fields = (
        "provider__name",
        "provider__api_id",
    )

    actions = ["update_from_vtpass"]

    @admin.action(description="Update selected providers from VTpass")
    def update_from_vtpass(self, request, queryset):
        success = 0

        for api_response in queryset:
            try:
                api_response.update_from_vtpass()
                success += 1
            except Exception as e:
                self.message_user(
                    request,
                    f"Failed to update {api_response.provider}: {e}",
                    level=messages.ERROR,
                )

        if success:
            self.message_user(
                request,
                f"Successfully updated {success} provider(s).",
                level=messages.SUCCESS,
            )