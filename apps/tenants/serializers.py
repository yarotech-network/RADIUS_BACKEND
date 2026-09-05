from rest_framework import serializers
from .models import Tenant, TenantMembership, TenantSetting
from decimal import Decimal


class TenantSerializer(serializers.ModelSerializer):
    member_count = serializers.IntegerField(read_only=True, default=0)
    voucher_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Tenant
        fields = [
            "id", "name", "slug", "phone", "email", "address",
            "is_active", "is_platform_admin", "created_at", "updated_at",
            "member_count", "voucher_count",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class TenantMembershipSerializer(serializers.ModelSerializer):
    user_display = serializers.CharField(source="user.username", read_only=True)
    tenant_display = serializers.CharField(source="tenant.name", read_only=True)

    def validate_user(self, user):
        if user.is_platform_admin or hasattr(user, "agent_profile") or user.staff_assignments.exists():
            raise serializers.ValidationError("Use a dedicated tenant account for memberships.")
        return user

    class Meta:
        model = TenantMembership
        fields = ["id", "user", "tenant", "role", "user_display", "tenant_display", "created_at"]
        read_only_fields = ["id", "created_at"]


class TenantSettingSerializer(serializers.ModelSerializer):
    agent_commission_percent = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=Decimal("0"), max_value=Decimal("100"), required=False)
    max_funding_amount = serializers.IntegerField(min_value=1, required=False)
    class Meta:
        model = TenantSetting
        fields = [
            "id", "tenant", "paystack_secret_key", "paystack_public_key",
            "agent_commission_percent", "voucher_prefix", "max_funding_amount",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant", "updated_at"]
        extra_kwargs = {
            "paystack_secret_key": {"write_only": True},
            "paystack_public_key": {"write_only": True},
        }


class TenantProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = ["id", "name", "slug", "phone", "email", "address", "is_active", "updated_at"]
        read_only_fields = ["id", "slug", "is_active", "updated_at"]
