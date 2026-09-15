from django.contrib import admin
from .models import (
    AgentProfile, AgentWallet, AgentWalletFundingPayment,
    AgentVoucherAllocation, AgentCreditAccount, AgentCreditLedger,
    AgentWalletTransaction, AgentCreditBatch, AgentCreditMovement,
)


class FinancialRecordAdmin(admin.ModelAdmin):
    """Corrections require an auditable service, not direct balance/history edits."""
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AgentProfile)
class AgentProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "tenant", "phone", "shop_name", "status", "commission_rate"]
    list_filter = ["status", "tenant"]
    search_fields = ["user__username", "shop_name"]

    def get_readonly_fields(self, request, obj=None):
        return ['user', 'tenant'] if obj else []


@admin.register(AgentWallet)
class AgentWalletAdmin(FinancialRecordAdmin):
    list_display = ["agent", "balance", "updated_at"]
    search_fields = ["agent__user__username"]


@admin.register(AgentWalletFundingPayment)
class AgentWalletFundingPaymentAdmin(FinancialRecordAdmin):
    list_display = ["reference", "wallet", "amount", "status", "created_at"]
    list_filter = ["status"]
    search_fields = ["reference"]


@admin.register(AgentVoucherAllocation)
class AgentVoucherAllocationAdmin(FinancialRecordAdmin):
    list_display = ["agent", "voucher", "allocation_type", "amount_charged", "commission_earned"]
    list_filter = ["allocation_type"]
    search_fields = ["agent__user__username", "voucher__username"]


@admin.register(AgentWalletTransaction)
class AgentWalletTransactionAdmin(FinancialRecordAdmin):
    list_display = ['reference', 'wallet', 'category', 'amount', 'previous_balance', 'new_balance', 'created_at']
    list_filter = ['category']
    search_fields = ['reference', 'wallet__agent__user__username']


@admin.register(AgentCreditAccount)
class AgentCreditAccountAdmin(FinancialRecordAdmin):
    list_display = ["agent", "credit_limit", "current_balance", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["agent__user__username"]


@admin.register(AgentCreditLedger)
class AgentCreditLedgerAdmin(FinancialRecordAdmin):
    list_display = ["credit_account", "amount", "description", "created_at"]
    search_fields = ["credit_account__agent__user__username", "description"]


admin.site.register(AgentCreditBatch, FinancialRecordAdmin)
admin.site.register(AgentCreditMovement, FinancialRecordAdmin)
