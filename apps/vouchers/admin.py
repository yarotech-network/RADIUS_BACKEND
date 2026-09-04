from django.contrib import admin
from .models import (
    InternetPlan, Voucher, PaymentTransaction,
    Radcheck, Radreply, Radacct, Radpostauth,
)


@admin.register(InternetPlan)
class InternetPlanAdmin(admin.ModelAdmin):
    list_display = ["name", "tenant", "price", "duration_hours", "rate_limit", "is_active"]
    list_filter = ["is_active", "tenant"]
    search_fields = ["name"]


@admin.register(Voucher)
class VoucherAdmin(admin.ModelAdmin):
    list_display = ["username", "plan", "status", "tenant", "created_at"]
    list_filter = ["status", "plan", "tenant"]
    search_fields = ["username"]
    readonly_fields = ["username", "password"]


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
