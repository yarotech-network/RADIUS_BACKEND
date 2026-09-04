from django.contrib import admin
from .models import (
    AgentProfile, AgentWallet, AgentWalletFundingPayment,
    AgentVoucherAllocation, AgentCreditAccount, AgentCreditLedger,
)


@admin.register(AgentProfile)
class AgentProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "tenant", "phone", "shop_name", "status", "commission_rate"]
    list_filter = ["status", "tenant"]
    search_fields = ["user__username", "shop_name"]


@admin.register(AgentWallet)
class AgentWalletAdmin(admin.ModelAdmin):
    list_display = ["agent", "balance", "updated_at"]
    search_fields = ["agent__user__username"]


@admin.register(AgentWalletFundingPayment)
class AgentWalletFundingPaymentAdmin(admin.ModelAdmin):
    list_display = ["reference", "wallet", "amount", "status", "created_at"]
    list_filter = ["status"]
    search_fields = ["reference"]


@admin.register(AgentVoucherAllocation)
class AgentVoucherAllocationAdmin(admin.ModelAdmin):
    list_display = ["agent", "voucher", "allocation_type", "amount_charged", "commission_earned"]
    list_filter = ["allocation_type"]
    search_fields = ["agent__user__username", "voucher__username"]


@admin.register(AgentCreditAccount)
class AgentCreditAccountAdmin(admin.ModelAdmin):
    list_display = ["agent", "credit_limit", "current_balance", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["agent__user__username"]


@admin.register(AgentCreditLedger)
class AgentCreditLedgerAdmin(admin.ModelAdmin):
    list_display = ["credit_account", "amount", "description", "created_at"]
    search_fields = ["credit_account__agent__user__username", "description"]
