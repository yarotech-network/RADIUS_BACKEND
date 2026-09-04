from rest_framework import serializers
import re
from .models import MacDevice


class MacDeviceSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source="plan.name", read_only=True)

    class Meta:
        model = MacDevice
        fields = [
            "id", "mac_address", "device_name", "plan", "plan_name",
            "tenant", "is_active", "expires_at", "created_at",
        ]
        read_only_fields = ["id", "tenant", "created_at"]

    def validate_mac_address(self, value):
        compact = value.replace(":", "").replace("-", "").replace(".", "")
        if not re.fullmatch(r"[0-9A-Fa-f]{12}", compact):
            raise serializers.ValidationError("Enter a valid 12-digit MAC address.")
        return MacDevice.normalize_mac(compact)

    def validate_plan(self, value):
        request = self.context.get("request")
        if request and value.tenant_id != request.user.membership.tenant_id:
            raise serializers.ValidationError("Plan does not belong to your tenant.")
        return value
