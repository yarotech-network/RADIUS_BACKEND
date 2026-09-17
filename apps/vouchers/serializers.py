from rest_framework import serializers
from decimal import Decimal
from apps.routers.models import NASDevice
from .terms import duration_seconds
from .device_policy import NewDeviceCountField, max_new_devices
from .models import InternetPlan, Voucher, PaymentTransaction, BandwidthProfile
from apps.core.api import tenant_for


class InternetPlanSerializer(serializers.ModelSerializer):
    max_devices = serializers.SerializerMethodField()

    def get_max_devices(self, instance):
        return max_new_devices()

    public_router = serializers.PrimaryKeyRelatedField(queryset=NASDevice.objects.none(), allow_null=True, required=False)
    duration_seconds = serializers.IntegerField(read_only=True)
    bandwidth_profile = serializers.PrimaryKeyRelatedField(queryset=BandwidthProfile.objects.none(), allow_null=True, required=False)
    bandwidth_profile_name = serializers.CharField(source="bandwidth_profile.name", read_only=True, default=None)
    service_type = serializers.ChoiceField(choices=["hotspot", "iot_mac"], required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            self.fields["public_router"].queryset = NASDevice.objects.filter(tenant=tenant_for(request))
            self.fields["bandwidth_profile"].queryset = BandwidthProfile.objects.filter(tenant=tenant_for(request))
            if request.method in ("POST", "PUT", "PATCH"):
                self.fields["bandwidth_profile"].queryset = self.fields["bandwidth_profile"].queryset.select_for_update()
        self.fields["rate_limit"].required = False

    def validate(self, attrs):
        if any(key in self.initial_data for key in ("free_access", "free_tier", "cooldown_minutes")):
            raise serializers.ValidationError({"free_access": "Free access enforcement is not available."})
        if self.instance and self.instance.archived_at:
            raise serializers.ValidationError('Archived plans are read-only.')
        service_type = attrs.pop('service_type', None)
        if service_type:
            expected_type = 'voucher' if service_type == 'hotspot' else 'iot_mac'
            if 'plan_type' in attrs and attrs['plan_type'] != expected_type:
                raise serializers.ValidationError({'plan_type': 'Service type does not match plan type.'})
            attrs['plan_type'] = expected_type
        kind = attrs.get('plan_type', getattr(self.instance, 'plan_type', 'voucher'))
        router = attrs.get('public_router', getattr(self.instance, 'public_router', None))
        if router and kind != 'iot_mac':
            raise serializers.ValidationError({'public_router': 'Router binding applies to IoT / MAC plans.'})
        if kind == 'iot_mac' and attrs.get('is_public', getattr(self.instance, 'is_public', True)) and not router:
            raise serializers.ValidationError({'public_router': 'Select a router for a public IoT / MAC plan.'})
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

        return attrs

    def to_representation(self, instance):
        result = super().to_representation(instance)
        result['service_type'] = 'hotspot' if instance.plan_type == 'voucher' else 'iot_mac'
        return result

    duration_hours = serializers.DecimalField(max_digits=16, decimal_places=6, min_value=Decimal('0.000139'), max_value=Decimal('596523.235'), coerce_to_string=False)

    def validate_duration_hours(self, value):
        duration_seconds(value)
        return value

    def validate_rate_limit(self, value):
        import re
        if value and not re.fullmatch(r'[0-9kKmMgG./ ]+', value):
            raise serializers.ValidationError('Use a RouterOS numeric rate expression, e.g. 5M/10M.')
        return value.strip()
    price_display = serializers.CharField(source="get_price_display", read_only=True)

    class Meta:
        model = InternetPlan
        fields = [
            "id", "name", "price", "price_display", "duration_hours",
            "rate_limit", "data_limit", "voucher_prefix", "voucher_code_format", "is_active", "created_at",
            "bandwidth_profile", "bandwidth_profile_name", "service_type", "duration_seconds",
            "is_public", "agent_enabled", "plan_type", "public_router", "archived_at", "max_devices",
        ]
        read_only_fields = ["id", "created_at", "archived_at"]


class VoucherSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()

    def get_status(self, instance):
        from .status_rules import effective_status
        return effective_status(instance)

    can_edit = serializers.SerializerMethodField()

    def get_can_edit(self, voucher):
        return not (voucher.status != 'unused' or voucher.legacy_provenance or voucher.is_used or
            voucher.first_used_at or voucher.used_at or voucher.last_used_at or voucher.expires_at or voucher.activated_at or voucher.deleted_at or
            hasattr(voucher, 'payment') or hasattr(voucher, 'agent_allocation'))

    device_limit = serializers.IntegerField(min_value=1, max_value=10, required=False)
    plan_name = serializers.CharField(source="service_terms.name", read_only=True)
    plan_duration = serializers.CharField(source="service_terms.duration_hours", read_only=True)
    price_display = serializers.CharField(source="get_price_display", read_only=True)
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
            "status", "generation_source", "device_limit", "expires_at", "can_edit",
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
        if not value.is_active or value.archived_at or value.plan_type != 'voucher':
            raise serializers.ValidationError("Plan is inactive.")
        return value


class VoucherGenerateSerializer(serializers.Serializer):
    device_limit = NewDeviceCountField()
    plan_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, max_value=100)
    prefix = serializers.CharField(max_length=10, required=False, default="")

    def validate_plan_id(self, value):
        tenant = self.context.get("tenant")
        query = InternetPlan.objects.filter(id=value, is_active=True, archived_at__isnull=True, plan_type='voucher')
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
