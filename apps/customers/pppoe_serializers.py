from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import serializers
from apps.core.api import tenant_for
from apps.vouchers.models import BandwidthProfile
from .models import PPPoEPlan, PPPoEService


class StrictSerializer(serializers.Serializer):
    def validate(self, attrs):
        if set(self.initial_data) - set(self.fields):
            raise serializers.ValidationError("Unknown fields are not accepted.")
        return attrs


class PPPoEPlanSerializer(serializers.ModelSerializer):
    bandwidth_profile_name = serializers.CharField(source="bandwidth_profile.name", read_only=True)
    rate_limit = serializers.CharField(source="bandwidth_profile.rate_limit", read_only=True)
    duration_hours = serializers.IntegerField(min_value=1, max_value=8760)
    price = serializers.IntegerField(min_value=0, max_value=2147483647)

    class Meta:
        model = PPPoEPlan
        fields = ["id", "name", "bandwidth_profile", "bandwidth_profile_name", "rate_limit", "duration_hours", "price", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        self.fields["bandwidth_profile"].queryset = BandwidthProfile.objects.filter(tenant=tenant_for(request)) if request and not getattr(request.parser_context.get("view"), "swagger_fake_view", False) else BandwidthProfile.objects.none()

    def validate(self, attrs):
        allowed = {name for name, field in self.fields.items() if not field.read_only}
        if set(self.initial_data) - allowed:
            raise serializers.ValidationError("Unknown or read-only fields are not accepted.")
        if self.instance:
            for field in ("bandwidth_profile", "duration_hours", "price"):
                if field in attrs and attrs[field] != getattr(self.instance, field):
                    raise serializers.ValidationError({field:"Plan terms are immutable. Create another plan for different terms."})
        elif not attrs["bandwidth_profile"].is_active:
            raise serializers.ValidationError({"bandwidth_profile":"Choose an active profile."})
        return attrs


def validate_service_password(value):
    try:
        validate_password(value)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(exc.messages)
    return value


class ServiceCreateSerializer(StrictSerializer):
    customer = serializers.IntegerField(min_value=1)
    plan = serializers.IntegerField(min_value=1)
    router = serializers.UUIDField()
    password = serializers.CharField(min_length=12, max_length=128, trim_whitespace=False, write_only=True, validators=[validate_service_password])


class ServiceActionSerializer(StrictSerializer):
    expected_version = serializers.IntegerField(min_value=1)


class ServicePasswordSerializer(ServiceActionSerializer):
    password = serializers.CharField(min_length=12, max_length=128, trim_whitespace=False, write_only=True, validators=[validate_service_password])


class PPPoEServiceSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source="plan.name", read_only=True)
    router_name = serializers.CharField(source="router.name", read_only=True)
    status = serializers.SerializerMethodField()

    def get_status(self, obj) -> str:
        if obj.suspended:
            return "suspended"
        return "expired" if obj.expires_at <= timezone.now() else "configured"

    class Meta:
        model = PPPoEService
        fields = ["id", "customer", "plan", "plan_name", "router", "router_name", "username", "rate_limit", "period_hours", "expires_at", "suspended", "status", "version", "disconnect_state", "last_reconciled_at", "created_at"]
        read_only_fields = fields
