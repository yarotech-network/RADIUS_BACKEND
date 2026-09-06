from rest_framework import serializers
from apps.vouchers.serializers import VoucherGenerateSerializer
from .models import (
    AgentProfile, AgentWallet, AgentWalletFundingPayment,
    AgentVoucherAllocation, AgentCreditAccount,
)


class AgentProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    wallet_balance = serializers.IntegerField(source="wallet.balance", read_only=True, default=0)

    class Meta:
        model = AgentProfile
        fields = [
            "id", "user", "username", "tenant", "phone", "shop_name",
            "status", "commission_rate", "wallet_balance", "created_at",
        ]
        read_only_fields = [
            "id", "user", "tenant", "status", "commission_rate",
            "wallet_balance", "created_at",
        ]


class AgentWalletSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentWallet
        fields = ["id", "agent", "balance", "updated_at"]
        read_only_fields = ["id", "agent", "balance", "updated_at"]


class AgentFundingPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentWalletFundingPayment
        fields = ["id", "reference", "amount", "status", "created_at", "completed_at"]
        read_only_fields = fields


class AgentWalletFundingSerializer(serializers.Serializer):
    amount = serializers.IntegerField(min_value=50_000, help_text="Minimum \u20a6500")

    def validate_amount(self, value):
        agent = self.context["agent"]
        tenant_settings = getattr(agent.tenant, "settings", None)
        maximum = tenant_settings.max_funding_amount if tenant_settings else 100_000
        if value > maximum:
            raise serializers.ValidationError(
                f"Amount exceeds the tenant funding limit of {maximum} kobo."
            )
        return value


class FundingCheckoutSerializer(serializers.Serializer):
    authorization_url = serializers.URLField()
    reference = serializers.CharField()


class AgentVoucherAllocationSerializer(serializers.ModelSerializer):
    voucher_username = serializers.CharField(source="voucher.username", read_only=True)
    # The single access code the agent hands to the customer (username doubles as the password).
    # None for vouchers issued before single-code credentials, whose password stays print-only.
    access_code = serializers.SerializerMethodField()

    class Meta:
        model = AgentVoucherAllocation
        fields = [
            "id", "agent", "voucher", "voucher_username", "access_code",
            "allocation_type", "amount_charged", "commission_earned", "created_at",
        ]

    def get_access_code(self, allocation):
        return allocation.voucher.access_code


class AgentGeneratedVouchersSerializer(serializers.Serializer):
    vouchers = AgentVoucherAllocationSerializer(many=True)


class AgentVoucherGenerateSerializer(VoucherGenerateSerializer):
    quantity = serializers.IntegerField(min_value=1, max_value=100, default=1)


class AgentStatsSerializer(serializers.Serializer):
    wallet_balance = serializers.IntegerField()
    vouchers_today = serializers.IntegerField()
    commission_this_month = serializers.IntegerField()
    total_vouchers = serializers.IntegerField()


class AgentLoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)
