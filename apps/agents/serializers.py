from rest_framework import serializers
from apps.vouchers.serializers import VoucherGenerateSerializer
from apps.tenants.public_api import PublicPlanSerializer
from .models import (
    AgentProfile, AgentWallet, AgentWalletFundingPayment,
    AgentVoucherAllocation, AgentCreditAccount, AgentWalletTransaction,
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
    total_amount = serializers.SerializerMethodField()
    fee = serializers.SerializerMethodField()

    def get_total_amount(self, obj):
        from .funding_terms import funding_total
        return funding_total(obj)

    def get_fee(self, obj):
        return self.get_total_amount(obj) - obj.amount

    class Meta:
        model = AgentWalletFundingPayment
        fields = ["id", "reference", "amount", "fee", "total_amount", "status", "created_at", "completed_at"]
        read_only_fields = fields


class AgentWalletFundingSerializer(serializers.Serializer):
    expected_total = serializers.IntegerField(min_value=1, max_value=2147483647, required=False)
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
    amount = serializers.IntegerField()
    fee = serializers.IntegerField()
    total_amount = serializers.IntegerField()
    authorization_url = serializers.URLField()
    reference = serializers.CharField()


class FundingVerificationSerializer(serializers.Serializer):
    reference = serializers.CharField(max_length=100)


class FundingPolicySerializer(serializers.Serializer):
    minimum = serializers.IntegerField()
    maximum = serializers.IntegerField()
    fee_percent = serializers.CharField()
    flat_fee = serializers.IntegerField()
    currency = serializers.CharField()


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
            "retail_price", "commission_rate_snapshot", "wallet_transaction",
        ]

    def get_access_code(self, allocation):
        return allocation.voucher.access_code


class AgentGeneratedVouchersSerializer(serializers.Serializer):
    vouchers = AgentVoucherAllocationSerializer(many=True)


class AgentVoucherGenerateSerializer(VoucherGenerateSerializer):
    quantity = serializers.IntegerField(min_value=1, max_value=100, default=1)
    device_limit = serializers.IntegerField(min_value=1, max_value=1, default=1)


class AgentWalletTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentWalletTransaction
        fields = ['id', 'reference', 'category', 'amount', 'previous_balance', 'new_balance', 'created_at']
        read_only_fields = fields


class AgentPlanSerializer(PublicPlanSerializer):
    agent_cost = serializers.SerializerMethodField()
    commission_amount = serializers.SerializerMethodField()
    commission_rate = serializers.SerializerMethodField()

    class Meta(PublicPlanSerializer.Meta):
        fields = [*PublicPlanSerializer.Meta.fields, 'agent_cost', 'commission_amount', 'commission_rate']

    def pricing(self, plan):
        from .pricing import agent_price
        try:
            return agent_price(plan.price, self.context['request'].user.agent_profile.commission_rate)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def get_agent_cost(self, plan):
        return self.pricing(plan)['agent_cost']

    def get_commission_amount(self, plan):
        return self.pricing(plan)['commission_amount']

    def get_commission_rate(self, plan):
        return self.pricing(plan)['commission_rate']

    def get_max_devices(self, plan):
        return 1


class AgentStatsSerializer(serializers.Serializer):
    wallet_balance = serializers.IntegerField()
    vouchers_today = serializers.IntegerField()
    commission_this_month = serializers.IntegerField()
    total_vouchers = serializers.IntegerField()


class AgentLoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)
