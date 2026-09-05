from rest_framework import serializers
from .models import NASDevice, RouterAuditEvent, RouterOnboardingCheck
from .secret_store import secret_store
from django.conf import settings
from .provisioners import (
    WireGuardConfigurationError,
    validate_managed_ip,
    validate_wireguard_public_key,
)


class NASDeviceSerializer(serializers.ModelSerializer):
    nas_secret = serializers.CharField(max_length=255, write_only=True, trim_whitespace=False)
    routeros_password_encrypted = serializers.CharField(max_length=255, write_only=True, required=False, allow_blank=True, trim_whitespace=False)
    wireguard_port = serializers.IntegerField(min_value=1, max_value=65535, required=False)
    tenant_name = serializers.CharField(source="tenant.name", read_only=True)

    class Meta:
        model = NASDevice
        fields = [
            "id", "name", "ip_address", "nas_secret", "wireguard_ip",
            "wireguard_public_key", "wireguard_port", "routeros_username",
            "routeros_password_encrypted", "location", "tenant", "tenant_name",
            "onboarding_state", "deployment_status", "is_active",
            "last_seen_at", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "tenant", "onboarding_state", "deployment_status", "last_seen_at", "created_at", "updated_at"]
        extra_kwargs = {
            "nas_secret": {"write_only": True},
            "routeros_password_encrypted": {"write_only": True},
        }

    def validate_wireguard_public_key(self, value):
        if not value:
            return value
        try:
            return validate_wireguard_public_key(value)
        except WireGuardConfigurationError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate_nas_secret(self, value):
        if value.startswith("enc:v1:"):
            raise serializers.ValidationError("Provide a plaintext replacement, not stored ciphertext.")
        return value

    def validate_routeros_password_encrypted(self, value):
        if value.startswith("enc:v1:"):
            raise serializers.ValidationError("Provide a plaintext replacement, not stored ciphertext.")
        return value

    def validate_wireguard_ip(self, value):
        if value is None:
            return value
        try:
            return validate_managed_ip(value, settings.WG_MANAGED_SUBNET)
        except WireGuardConfigurationError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def create(self, validated_data):
        validated_data["nas_secret"] = secret_store.encrypt(validated_data["nas_secret"])
        if validated_data.get("routeros_password_encrypted"):
            validated_data["routeros_password_encrypted"] = secret_store.encrypt(
                validated_data["routeros_password_encrypted"]
            )
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if "nas_secret" in validated_data:
            validated_data["nas_secret"] = secret_store.encrypt(validated_data["nas_secret"])
        if validated_data.get("routeros_password_encrypted"):
            validated_data["routeros_password_encrypted"] = secret_store.encrypt(
                validated_data["routeros_password_encrypted"]
            )
        return super().update(instance, validated_data)


class RouterAuditEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = RouterAuditEvent
        fields = [
            "id", "router", "action", "from_state", "to_state",
            "correlation_id", "details", "created_at",
        ]


class RouterOnboardingCheckSerializer(serializers.ModelSerializer):
    class Meta:
        model = RouterOnboardingCheck
        fields = ["id", "router", "check_type", "passed", "details", "checked_at"]


class ProvisioningRequestSerializer(serializers.Serializer):
    request_id = serializers.UUIDField()
    action = serializers.ChoiceField(
        choices=["provision_wireguard_peer", "suspend_wireguard_peer"]
    )
    router_id = serializers.UUIDField()
    public_key = serializers.CharField(max_length=255, required=False)
    wireguard_ip = serializers.IPAddressField(required=False)

    def validate_public_key(self, value):
        try:
            return validate_wireguard_public_key(value)
        except WireGuardConfigurationError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate_wireguard_ip(self, value):
        try:
            return validate_managed_ip(value, settings.WG_MANAGED_SUBNET)
        except WireGuardConfigurationError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate(self, attrs):
        if attrs["action"] == "provision_wireguard_peer":
            missing = [name for name in ("public_key", "wireguard_ip") if not attrs.get(name)]
            if missing:
                raise serializers.ValidationError(
                    {name: "This field is required for provisioning." for name in missing}
                )
        return attrs


class RouterRadiusTestSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=253)
    password = serializers.CharField(max_length=128, write_only=True, trim_whitespace=False)


class RouterTransitionSerializer(serializers.Serializer):
    to_state = serializers.ChoiceField(choices=NASDevice.ONBOARDING_STATES)
