from rest_framework import serializers
from .models import Tenant, TenantMembership, TenantSetting
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.db import transaction, IntegrityError
from apps.core.api import platform_context


class TenantSerializer(serializers.ModelSerializer):
    owner_email = serializers.EmailField(write_only=True, required=False)
    owner_username = serializers.CharField(max_length=150, write_only=True, required=False, validators=[UnicodeUsernameValidator()])
    owner_setup_pending = serializers.SerializerMethodField()

    def get_owner_setup_pending(self, tenant) -> bool:
        if hasattr(tenant, "pending_owner_setup"):
            return tenant.pending_owner_setup
        return tenant.memberships.filter(role="owner", user__owner_setup_pending=True).exists()

    def validate(self, attrs):
        if self.instance:
            if "owner_email" in attrs or "owner_username" in attrs:
                raise serializers.ValidationError("Owner setup fields are only accepted when creating a tenant.")
            if "slug" in attrs and attrs["slug"] != self.instance.slug:
                raise serializers.ValidationError({"slug": "Existing storefront addresses cannot be changed."})
            return attrs
        email = attrs.get("owner_email", "").strip().lower()
        username = attrs.get("owner_username", "").strip()
        if not email or not username:
            raise serializers.ValidationError({"owner_email": "Owner email and username are required."})
        User = get_user_model()
        if User.objects.filter(email__iexact=email).exists() or User.objects.filter(username=username).exists():
            raise serializers.ValidationError({"owner_email": "Owner email or username is already in use."})
        attrs["owner_email"], attrs["owner_username"] = email, username
        return attrs

    def create(self, validated_data):
        email = validated_data.pop("owner_email")
        username = validated_data.pop("owner_username")
        try:
            with transaction.atomic():
                tenant = super().create(validated_data)
                owner = get_user_model().objects.create_user(username=username, email=email,
                    password=None, email_verified_at=None, owner_setup_pending=True)
                TenantMembership.objects.create(user=owner, tenant=tenant, role="owner")
                return tenant
        except IntegrityError:
            raise serializers.ValidationError("Tenant slug, owner email or username is already in use.")

    member_count = serializers.IntegerField(read_only=True, default=0)
    voucher_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Tenant
        fields = [
            "id", "name", "business_name", "slug", "phone", "email", "address",
            "is_active", "is_platform_admin", "created_at", "updated_at",
            "member_count", "voucher_count", "owner_email", "owner_username", "owner_setup_pending",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class TenantMembershipSerializer(serializers.ModelSerializer):
    user_display = serializers.CharField(source="user.username", read_only=True)
    tenant_display = serializers.CharField(source="tenant.name", read_only=True)

    def validate_user(self, user):
        if hasattr(user, "agent_profile") or user.staff_assignments.exists():
            raise serializers.ValidationError("Use a dedicated tenant account for memberships.")
        return user

    class Meta:
        model = TenantMembership
        fields = ["id", "user", "tenant", "role", "is_active", "user_display", "tenant_display", "created_at"]
        read_only_fields = ["id", "created_at"]


class TenantSettingSerializer(serializers.ModelSerializer):
    agent_funding_fee_percent = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=Decimal('0'), max_value=Decimal('100'), required=False)
    agent_funding_flat_fee = serializers.IntegerField(min_value=0, max_value=2147483647, required=False)
    agent_commission_percent = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=Decimal("0"), max_value=Decimal("100"), required=False)
    max_funding_amount = serializers.IntegerField(min_value=1, required=False)
    class Meta:
        model = TenantSetting
        fields = [
            "id", "tenant", "paystack_secret_key", "paystack_public_key",
            "agent_commission_percent", "voucher_prefix", "default_voucher_code_format", "max_funding_amount",
            "agent_funding_fee_percent", "agent_funding_flat_fee",
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
        fields = ["id", "name", "business_name", "slug", "phone", "email", "address", "is_active", "updated_at"]
        read_only_fields = ["id", "slug", "is_active", "updated_at"]
