from rest_framework import serializers
from .models import TenantWhatsAppRoute
from apps.routers.secret_store import secret_store


class TenantWhatsAppRouteSerializer(serializers.ModelSerializer):
    access_token_encrypted = serializers.CharField(max_length=500, write_only=True, trim_whitespace=False)

    def validate_access_token_encrypted(self, value):
        if value.startswith("enc:v1:"):
            raise serializers.ValidationError("Provide a plaintext access token, not stored ciphertext.")
        return value
    class Meta:
        model = TenantWhatsAppRoute
        fields = [
            "id", "tenant", "phone_number_id", "access_token_encrypted",
            "is_active", "created_at",
        ]
        read_only_fields = ["id", "tenant", "created_at"]
        extra_kwargs = {
            "access_token_encrypted": {"write_only": True},
        }

    def create(self, validated_data):
        validated_data["access_token_encrypted"] = secret_store.encrypt(
            validated_data["access_token_encrypted"]
        )
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if "access_token_encrypted" in validated_data:
            validated_data["access_token_encrypted"] = secret_store.encrypt(
                validated_data["access_token_encrypted"]
            )
        return super().update(instance, validated_data)
