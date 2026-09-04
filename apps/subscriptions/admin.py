from django.contrib import admin
from .models import SubscriptionPlan, TenantSubscription, SubscriptionPayment


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ["name", "price", "duration_days", "is_active"]
    list_filter = ["is_active"]
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
