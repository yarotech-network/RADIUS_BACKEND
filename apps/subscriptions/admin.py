from django.contrib import admin
from .models import SubscriptionPlan, TenantSubscription, SubscriptionPayment


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ["name", "price", "duration_days", "max_routers", "whatsapp_enabled", "daily_voucher_print_limit", "is_active"]
    list_filter = ["is_active", "whatsapp_enabled"]
    # Changes go through the versioned platform API so purchased terms are protected.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    search_fields = ["name"]


@admin.register(TenantSubscription)
class TenantSubscriptionAdmin(admin.ModelAdmin):
    list_display = ["tenant", "plan", "status", "started_at", "expires_at", "is_trial"]
    list_filter = ["status", "is_trial"]
    search_fields = ["tenant__name"]


@admin.register(SubscriptionPayment)
class SubscriptionPaymentAdmin(admin.ModelAdmin):
    list_display = ["reference", "subscription", "amount", "status", "created_at"]
    list_filter = ["status"]
    search_fields = ["reference"]
