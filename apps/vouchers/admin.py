from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from .models import (
    InternetPlan, Voucher, PaymentTransaction,
    Radcheck, Radreply, Radacct, Radpostauth,
)


@admin.register(InternetPlan)
class InternetPlanAdmin(admin.ModelAdmin):
    list_display = ["name", "tenant", "price", "duration_hours", "rate_limit", "is_active"]
    list_filter = ["is_active", "is_public", "agent_enabled", "plan_type", "tenant"]
    readonly_fields = ['archived_at']

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.archived_at:
            return [f.name for f in obj._meta.fields]
        return self.readonly_fields

    actions = ['archive_selected']

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return not (obj and obj.archived_at) and super().has_change_permission(request, obj)

    @admin.action(description='Archive selected plans (retain issued access)', permissions=['change'])
    def archive_selected(self, request, queryset):
        try:
            count, _ = queryset.delete()
        except ValidationError as exc:
            self.message_user(request, '; '.join(exc.messages), level=messages.ERROR)
        else:
            self.message_user(request, f'{count} plans archived.', level=messages.SUCCESS)
    search_fields = ["name"]


@admin.register(Voucher)
class VoucherAdmin(admin.ModelAdmin):
    list_display = ["username", "plan", "status", "tenant", "created_at"]
    list_filter = ["status", "plan", "tenant"]
    search_fields = ["username"]
    readonly_fields = ["username", "password"]

    def get_readonly_fields(self, request, obj=None):
        return self.readonly_fields + (["plan", "tenant", "device_limit"] if obj else [])


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ["reference", "amount", "status", "customer_email", "created_at"]
    list_filter = ["status"]
    search_fields = ["reference", "customer_email"]


@admin.register(Radcheck)
class RadcheckAdmin(admin.ModelAdmin):
    list_display = ["username", "attribute", "op", "value"]
    search_fields = ["username"]


@admin.register(Radacct)
class RadacctAdmin(admin.ModelAdmin):
    list_display = ["username", "nasipaddress", "acctstarttime", "acctstoptime"]
    search_fields = ["username"]
