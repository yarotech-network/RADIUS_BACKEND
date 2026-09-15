from rest_framework import serializers
from copy import copy
from django.core.exceptions import ValidationError as DjangoValidationError
from .lifecycle import check_version, validate_grant, apply_plan_snapshot
from .models import MacDevice
from apps.vouchers.models import InternetPlan
from apps.core.api import tenant_for


class DeviceAccountingSerializer(serializers.Serializer):
    available = serializers.BooleanField()
    session_count = serializers.IntegerField(allow_null=True)
    open_sessions = serializers.IntegerField(allow_null=True)
    bytes_total = serializers.IntegerField(allow_null=True)
    last_connected_at = serializers.DateTimeField(allow_null=True)


class MacDeviceSerializer(serializers.ModelSerializer):
    accounting = serializers.SerializerMethodField()
    status = serializers.CharField(source='effective_status', read_only=True)
    expected_version = serializers.IntegerField(min_value=1, required=False, write_only=True)
    network_enforcement = serializers.SerializerMethodField()

    def get_network_enforcement(self, obj) -> str:
        return 'not_connected'


    def get_accounting(self, obj) -> dict:
        data = self.context.get("device_accounting", {}).get(obj.pk)
        return DeviceAccountingSerializer(data).data if data else None

    router_name = serializers.CharField(source="router.name", read_only=True, default=None)
    router_location = serializers.CharField(source="router.location", read_only=True, default=None)
    vlan_id = serializers.IntegerField(min_value=1, max_value=4094, allow_null=True, required=False)
    description = serializers.CharField(max_length=2000, allow_blank=True, required=False)
    plan_name = serializers.CharField(source="plan.name", read_only=True, default=None)

    class Meta:
        model = MacDevice
        fields = [
            "id", "status", "version", "expected_version", "deleted_at", "speed_limit", "data_limit_bytes", "network_enforcement", "mac_address", "device_name", "plan", "plan_name",
            "tenant", "is_active", "expires_at", "created_at",
            "router", "router_name", "router_location", "access_type", "vlan_id", "description", "accounting",
        ]
        read_only_fields = ["id", "tenant", "created_at", "version", "deleted_at", "speed_limit", "data_limit_bytes"]

    def validate_mac_address(self, value):
        try:
            return MacDevice.normalize_mac(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages)

    def validate_plan(self, value):
        request = self.context.get("request")
        if request and value and value.tenant_id != tenant_for(request).pk:
            raise serializers.ValidationError("Plan does not belong to your tenant.")
        return value

    def validate_router(self, value):
        if value and value.tenant_id != tenant_for(self.context["request"]).pk:
            raise serializers.ValidationError("Router does not belong to your tenant.")
        return value

    def validate(self, attrs):
        allowed = {name for name, field in self.fields.items() if not field.read_only}
        if set(self.initial_data) - allowed:
            raise serializers.ValidationError('Unknown or read-only device fields are not accepted.')
        if self.instance:
            check_version(self.instance, attrs.pop('expected_version', None))
            if self.instance.configured_status == 'deleted':
                raise serializers.ValidationError('Deleted registrations cannot be edited.')
            if self.instance.configured_status == 'revoked' and 'is_active' in attrs:
                raise serializers.ValidationError('Use the explicit reactivation action for a revoked registration.')
        else:
            attrs.pop('expected_version', None)
        candidate = copy(self.instance) if self.instance else MacDevice(tenant=tenant_for(self.context['request']))
        for key, value in attrs.items():
            setattr(candidate, key, value)
        if candidate.access_type == 'permanent':
            attrs['expires_at'] = candidate.expires_at = None
        if candidate.access_type == 'timed' and not candidate.expires_at:
            raise serializers.ValidationError({'expires_at':'An expiry is required for time-limited access.'})
        granting = self.instance is None or any(key in attrs and attrs[key] != getattr(self.instance, key)
            for key in ('plan', 'router', 'expires_at', 'access_type', 'mac_address')) or attrs.get('is_active') is True
        if granting:
            validate_grant(candidate)
            if 'plan' in attrs:
                attrs['plan'] = candidate.plan
            if 'router' in attrs:
                attrs['router'] = candidate.router
        return attrs

    def create(self, validated_data):
        device = MacDevice(**validated_data)
        device.status = 'active' if device.is_active else 'suspended'
        apply_plan_snapshot(device)
        device.save()
        return device

    def update(self, instance, validated_data):
        changed_plan = 'plan' in validated_data and validated_data['plan'] != instance.plan
        for key, value in validated_data.items():
            setattr(instance, key, value)
        if 'is_active' in validated_data:
            instance.status = 'active' if validated_data['is_active'] else 'suspended'
        if changed_plan:
            apply_plan_snapshot(instance)
        instance.version += 1
        instance.save()
        return instance


class DeviceActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=['suspend','reactivate','revoke','delete'])
    expected_version = serializers.IntegerField(min_value=1)


class RenewalRequestSerializer(serializers.Serializer):
    plan = serializers.PrimaryKeyRelatedField(queryset=InternetPlan.objects.all())
    expected_version = serializers.IntegerField(min_value=1)


class RenewalSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    previous_expiry = serializers.DateTimeField(allow_null=True)
    expires_at = serializers.DateTimeField()
    terms = serializers.JSONField()
    created_at = serializers.DateTimeField()
