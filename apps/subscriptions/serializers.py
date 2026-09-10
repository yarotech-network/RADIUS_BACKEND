from rest_framework import serializers
from .models import SubscriptionPlan, TenantSubscription, SubscriptionPayment


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    price_display = serializers.SerializerMethodField()

    class Meta:
        model = SubscriptionPlan
        fields = ["id", "name", "price", "price_display", "duration_days", "features", "is_active", "max_routers", "daily_voucher_print_limit", "whatsapp_enabled", "version"]

    def get_price_display(self, obj) -> str:
        return f"\u20a6{obj.price / 100:,.0f}"


class TenantSubscriptionSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source="plan.name", read_only=True)
    is_expired = serializers.SerializerMethodField()
    entitlements = serializers.SerializerMethodField()

    class Meta:
        model = TenantSubscription
        fields = [
            "id", "tenant", "plan", "plan_name", "status",
            "started_at", "expires_at", "is_trial", "is_expired", "entitlements",
        ]
        read_only_fields = [
            "id", "tenant", "status", "started_at", "expires_at", "is_trial"
        ]

    def get_is_expired(self, obj) -> bool:
        return not obj.is_active

    def get_entitlements(self, obj) -> dict:
        from apps.routers.models import NASDevice
        from .entitlements import current_period, print_day, snapshot_plan
        from .models import VoucherPrintAuthorization, SubscriptionPeriod
        from django.utils import timezone
        period = current_period(obj.tenant) or SubscriptionPeriod.objects.filter(tenant=obj.tenant, starts_at__lte=timezone.now(), superseded=False).order_by("-ends_at").first()
        terms = period.terms if period else snapshot_plan(obj.plan)
        return {
            "terms": terms,
            "plan_id": period.plan_id if period else obj.plan_id,
            "enabled": obj.is_active,
            "routers_used": NASDevice.objects.filter(tenant=obj.tenant).count(),
            "vouchers_prepared_today": VoucherPrintAuthorization.objects.filter(tenant=obj.tenant, day=print_day()).count(),
            "day": str(print_day()), "timezone": "Africa/Lagos",
            "upcoming": [{"starts_at": item.starts_at, "ends_at": item.ends_at, "terms": item.terms} for item in SubscriptionPeriod.objects.filter(tenant=obj.tenant, superseded=False, starts_at__gt=timezone.now()).order_by("starts_at")],
        }


class SubscriptionCheckoutSerializer(serializers.Serializer):
    plan_id = serializers.PrimaryKeyRelatedField(
        source="plan",
        queryset=SubscriptionPlan.objects.filter(is_active=True, internal_code__isnull=True),
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


class BusinessPlanSerializer(SubscriptionPlanSerializer):
    max_routers = serializers.IntegerField(min_value=0, max_value=2147483647, allow_null=True, required=False)
    daily_voucher_print_limit = serializers.IntegerField(min_value=0, max_value=2147483647, allow_null=True, required=False)
    expected_version = serializers.IntegerField(min_value=1, write_only=True, required=False)

    def validate(self, attrs):
        if self.instance is not None and "expected_version" not in attrs:
            raise serializers.ValidationError({"expected_version": "Reload the plan and provide its version."})
        return attrs

    price = serializers.IntegerField(min_value=1, max_value=2147483647)
    duration_days = serializers.IntegerField(min_value=1, max_value=36500)
    features = serializers.ListField(
        child=serializers.CharField(max_length=300, allow_blank=False),
        max_length=30, required=False, default=list,
    )

    class Meta(SubscriptionPlanSerializer.Meta):
        fields = SubscriptionPlanSerializer.Meta.fields + ["expected_version"]
        read_only_fields = ["id", "price_display", "version"]
