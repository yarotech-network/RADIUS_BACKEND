from rest_framework import serializers
from .models import InternetPlan, Voucher, PaymentTransaction, BandwidthProfile
from apps.core.api import tenant_for


class InternetPlanSerializer(serializers.ModelSerializer):
    bandwidth_profile = serializers.PrimaryKeyRelatedField(queryset=BandwidthProfile.objects.none(), allow_null=True, required=False)
    bandwidth_profile_name = serializers.CharField(source="bandwidth_profile.name", read_only=True, default=None)
    service_type = serializers.ChoiceField(choices=["hotspot"], required=False, default="hotspot")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            self.fields["bandwidth_profile"].queryset = BandwidthProfile.objects.filter(tenant=tenant_for(request))
            if request.method in ("POST", "PUT", "PATCH"):
                self.fields["bandwidth_profile"].queryset = self.fields["bandwidth_profile"].queryset.select_for_update()
        self.fields["rate_limit"].required = False

    def validate(self, attrs):
        if any(key in self.initial_data for key in ("free_access", "free_tier", "cooldown_minutes")):
            raise serializers.ValidationError({"free_access": "Free access enforcement is not available."})
        attrs.pop("service_type", None)
        selected = attrs.get("bandwidth_profile", serializers.empty)
        if selected is not serializers.empty and selected is not None:
            if not selected.is_active and (not self.instance or self.instance.bandwidth_profile_id != selected.pk):
                raise serializers.ValidationError({"bandwidth_profile": "Choose an active bandwidth profile."})
            if "rate_limit" in attrs and attrs["rate_limit"] != selected.rate_limit:
                raise serializers.ValidationError({"rate_limit": "Speed must match the selected profile."})
            attrs["rate_limit"] = selected.rate_limit
        elif self.instance and selected is serializers.empty and "rate_limit" in attrs and attrs["rate_limit"] != self.instance.rate_limit:
            # Older API clients can still change a custom rate without understanding profiles.
            attrs["bandwidth_profile"] = None
        if not self.instance and not attrs.get("rate_limit"):
            raise serializers.ValidationError({"rate_limit": "Enter a custom speed or select a bandwidth profile."})
        return attrs

    def to_representation(self, instance):
        result = super().to_representation(instance)
        result["service_type"] = "hotspot"
        return result

    duration_hours = serializers.IntegerField(min_value=1, max_value=2147483647)
    price_display = serializers.CharField(source="get_price_display", read_only=True)

    class Meta:
        model = InternetPlan
        fields = [
            "id", "name", "price", "price_display", "duration_hours",
            "rate_limit", "data_limit", "voucher_prefix", "is_active", "created_at",
            "bandwidth_profile", "bandwidth_profile_name", "service_type",
        ]
        read_only_fields = ["id", "created_at"]


class VoucherSerializer(serializers.ModelSerializer):
    device_limit = serializers.IntegerField(min_value=1, max_value=2147483647, required=False)
    plan_name = serializers.CharField(source="plan.name", read_only=True)
    plan_duration = serializers.CharField(source="plan.duration_hours", read_only=True)
    price_display = serializers.CharField(source="plan.get_price_display", read_only=True)
    tenant_name = serializers.CharField(source="tenant.name", read_only=True)
    agent_name = serializers.CharField(source="agent.user.username", read_only=True, default=None)
    # Username when it doubles as the password (single-code vouchers); None for legacy or manual
    # vouchers, whose separate password remains write-only and print-only.
    access_code = serializers.CharField(read_only=True)

    class Meta:
        model = Voucher
        fields = [
            "id", "username", "password", "access_code", "plan", "plan_name", "plan_duration",
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

    def validate_username(self, value):
        if value.lower().startswith("yrp-"):
            raise serializers.ValidationError("This prefix is reserved for subscriber services.")
        return value

    def validate_plan(self, value):
        request = self.context.get("request")
        if request and value.tenant_id != request.user.membership.tenant_id:
            raise serializers.ValidationError("Plan does not belong to your tenant.")
        if not value.is_active:
            raise serializers.ValidationError("Plan is inactive.")
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


class BandwidthProfileSerializer(serializers.ModelSerializer):
    upload_kbps = serializers.IntegerField(min_value=1, max_value=10000000)
    download_kbps = serializers.IntegerField(min_value=1, max_value=10000000)
    rate_limit = serializers.CharField(read_only=True)
    plan_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = BandwidthProfile
        fields = ["id", "name", "upload_kbps", "download_kbps", "rate_limit", "is_active", "created_at", "plan_count"]
        read_only_fields = ["id", "created_at"]

    def validate(self, attrs):
        unknown = set(self.initial_data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({"non_field_errors": "Unknown profile fields are not accepted."})
        if self.instance:
            for field in ("upload_kbps", "download_kbps"):
                if field in attrs and attrs[field] != getattr(self.instance, field):
                    raise serializers.ValidationError({field: "Speeds are immutable. Create another profile to change speed."})
        return attrs
