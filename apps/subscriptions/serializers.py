from rest_framework import serializers
from .models import SubscriptionPlan, TenantSubscription, SubscriptionPayment


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    price_display = serializers.SerializerMethodField()

    class Meta:
        model = SubscriptionPlan
        fields = ["id", "name", "price", "price_display", "duration_days", "features", "is_active"]

    def get_price_display(self, obj) -> str:
        return f"\u20a6{obj.price / 100:,.0f}"


class TenantSubscriptionSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source="plan.name", read_only=True)
    is_expired = serializers.SerializerMethodField()

    class Meta:
        model = TenantSubscription
        fields = [
            "id", "tenant", "plan", "plan_name", "status",
            "started_at", "expires_at", "is_trial", "is_expired",
        ]
        read_only_fields = [
            "id", "tenant", "status", "started_at", "expires_at", "is_trial"
        ]

    def get_is_expired(self, obj) -> bool:
        return not obj.is_active


class SubscriptionCheckoutSerializer(serializers.Serializer):
    plan_id = serializers.PrimaryKeyRelatedField(
        source="plan",
        queryset=SubscriptionPlan.objects.filter(is_active=True),
    )

    def validate_plan_id(self, plan):
        if plan.price <= 0 or plan.duration_days <= 0:
            raise serializers.ValidationError("This subscription plan cannot be purchased.")
        return plan


class SubscriptionPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPayment
        fields = [
            "reference", "amount", "status", "plan", "subscription",
            "created_at", "completed_at",
        ]
        read_only_fields = fields
