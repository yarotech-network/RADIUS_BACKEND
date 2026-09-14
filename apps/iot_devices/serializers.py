from rest_framework import serializers
import re
from .models import MacDevice
from apps.core.api import tenant_for


class DeviceAccountingSerializer(serializers.Serializer):
    available = serializers.BooleanField()
    session_count = serializers.IntegerField(allow_null=True)
    open_sessions = serializers.IntegerField(allow_null=True)
    bytes_total = serializers.IntegerField(allow_null=True)
    last_connected_at = serializers.DateTimeField(allow_null=True)


class MacDeviceSerializer(serializers.ModelSerializer):
    accounting = serializers.SerializerMethodField()

    def get_accounting(self, obj) -> dict:
        data = self.context.get("device_accounting", {}).get(obj.pk)
        return DeviceAccountingSerializer(data).data if data else None

    router_name = serializers.CharField(source="router.name", read_only=True, default=None)
    router_location = serializers.CharField(source="router.location", read_only=True, default=None)
    vlan_id = serializers.IntegerField(min_value=1, max_value=4094, allow_null=True, required=False)
    description = serializers.CharField(max_length=2000, allow_blank=True, required=False)
    plan_name = serializers.CharField(source="plan.name", read_only=True)

    class Meta:
        model = MacDevice
        fields = [
            "id", "mac_address", "device_name", "plan", "plan_name",
            "tenant", "is_active", "expires_at", "created_at",
            "router", "router_name", "router_location", "access_type", "vlan_id", "description", "accounting",
        ]
        read_only_fields = ["id", "tenant", "created_at"]

    def validate_mac_address(self, value):
        compact = value.replace(":", "").replace("-", "").replace(".", "")
        if not re.fullmatch(r"[0-9A-Fa-f]{12}", compact):
            raise serializers.ValidationError("Enter a valid 12-digit MAC address.")
        return MacDevice.normalize_mac(compact)

    def validate_plan(self, value):
        request = self.context.get("request")
        if request and value.tenant_id != tenant_for(request).pk:
            raise serializers.ValidationError("Plan does not belong to your tenant.")
        return value

    def validate_router(self, value):
        if value and value.tenant_id != tenant_for(self.context["request"]).pk:
            raise serializers.ValidationError("Router does not belong to your tenant.")
        return value

    def validate(self, attrs):
        access_type = attrs.get("access_type", getattr(self.instance, "access_type", "timed"))
        expiry = attrs.get("expires_at", getattr(self.instance, "expires_at", None))
        if access_type == "timed" and expiry is None:
            raise serializers.ValidationError({"expires_at": "An expiry is required for time-limited access."})
        if access_type == "permanent":
            attrs["expires_at"] = None
        # Older records can remain unassigned; the new router-bound workflow must select a router.
        if "access_type" in attrs and not attrs.get("router", getattr(self.instance, "router", None)):
            raise serializers.ValidationError({"router": "Choose a router for this device."})
        return attrs
