from rest_framework import serializers
from .models import InternetPlan, Voucher, PaymentTransaction


class InternetPlanSerializer(serializers.ModelSerializer):
    price_display = serializers.CharField(source="get_price_display", read_only=True)

    class Meta:
        model = InternetPlan
        fields = [
            "id", "name", "price", "price_display", "duration_hours",
            "rate_limit", "data_limit", "voucher_prefix", "is_active", "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class VoucherSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source="plan.name", read_only=True)
    plan_duration = serializers.CharField(source="plan.duration_hours", read_only=True)
    price_display = serializers.CharField(source="plan.get_price_display", read_only=True)
    tenant_name = serializers.CharField(source="tenant.name", read_only=True)
    agent_name = serializers.CharField(source="agent.user.username", read_only=True, default=None)

    class Meta:
        model = Voucher
        fields = [
            "id", "username", "password", "plan", "plan_name", "plan_duration",
            "price_display", "tenant", "tenant_name", "agent", "agent_name",
            "status", "generation_source", "device_limit", "expires_at",
            "activated_at", "created_at",
        ]
        read_only_fields = ["id", "status", "expires_at", "activated_at", "created_at"]
        extra_kwargs = {
            "password": {"write_only": True},
            "tenant": {"read_only": True},
            "agent": {"read_only": True},
            "generation_source": {"read_only": True},
        }

    def validate_plan(self, value):
        request = self.context.get("request")
        if request and value.tenant_id != request.user.membership.tenant_id:
            raise serializers.ValidationError("Plan does not belong to your tenant.")
        return value


class VoucherGenerateSerializer(serializers.Serializer):
    plan_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, max_value=100)
    prefix = serializers.CharField(max_length=10, required=False, default="")

    def validate_plan_id(self, value):
        tenant = self.context.get("tenant")
        query = InternetPlan.objects.filter(id=value, is_active=True)
        if tenant is not None:
            query = query.filter(tenant=tenant)
        if not query.exists():
            raise serializers.ValidationError("Plan not found or inactive.")
        return value


class PaymentTransactionSerializer(serializers.ModelSerializer):
    voucher_username = serializers.CharField(source="voucher.username", read_only=True, default=None)

    class Meta:
        model = PaymentTransaction
        fields = [
            "id", "reference", "amount", "status", "customer_email",
            "customer_name", "customer_phone", "voucher", "voucher_username",
            "tenant", "plan", "paystack_reference", "created_at", "paid_at",
        ]
        read_only_fields = ["id", "status", "created_at", "paid_at"]
