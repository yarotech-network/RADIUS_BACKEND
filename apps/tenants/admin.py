from django.contrib import admin
from .models import Tenant, TenantMembership, TenantSetting


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "is_active", "is_platform_admin", "created_at"]
    list_filter = ["is_active", "is_platform_admin"]
    search_fields = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            from apps.subscriptions.trials import assign_new_tenant_trial
            assign_new_tenant_trial(obj)


@admin.register(TenantMembership)
class TenantMembershipAdmin(admin.ModelAdmin):
    list_display = ["user", "tenant", "role", "created_at"]
    list_filter = ["role"]
    search_fields = ["user__username", "tenant__name"]


@admin.register(TenantSetting)
class TenantSettingAdmin(admin.ModelAdmin):
    list_display = ["tenant", "agent_commission_percent", "voucher_prefix", "max_funding_amount"]
    search_fields = ["tenant__name"]
