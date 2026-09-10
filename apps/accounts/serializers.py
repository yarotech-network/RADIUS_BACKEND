from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.utils.text import slugify
from apps.tenants.models import Tenant, TenantMembership

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    role = serializers.CharField(read_only=True)
    tenant_id = serializers.IntegerField(source="membership.tenant_id", read_only=True, default=None)
    tenant_name = serializers.CharField(source="membership.tenant.name", read_only=True, default=None)

    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "phone", "role", "tenant_name", "tenant_id"]
        read_only_fields = ["id", "role", "tenant_name"]


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(min_length=3, max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(
        min_length=8,
        write_only=True,
        trim_whitespace=False,
        validators=[validate_password],
    )
    password_confirm = serializers.CharField(write_only=True, trim_whitespace=False)
    tenant_name = serializers.CharField(min_length=2, max_length=200)
    phone = serializers.CharField(min_length=10, max_length=20)

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Username already taken.")
        return value

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Email already registered.")
        return value

    def validate_tenant_name(self, value):
        slug = slugify(value)
        if not slug:
            raise serializers.ValidationError("Tenant name must contain letters or numbers.")
        if len(slug) > 50:
            raise serializers.ValidationError("Tenant name produces a slug longer than 50 characters.")
        if Tenant.objects.filter(slug=slug).exists():
            raise serializers.ValidationError("A tenant with this name already exists.")
        return value

    def validate(self, data):
        if data["password"] != data["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": "Passwords don't match."})
        return data

    @transaction.atomic
    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            password=validated_data["password"],
            phone=validated_data.get("phone", ""),
        )
        # Internal flows are verified by default; public sign-up is the one path
        # that must confirm the address via OTP before the account unlocks.
        user.email_verified_at = None
        user.save(update_fields=["email_verified_at"])
        tenant = Tenant.objects.create(
            name=validated_data["tenant_name"],
            slug=slugify(validated_data["tenant_name"]),
            phone=validated_data.get("phone", ""),
            email=validated_data["email"],
        )
        TenantMembership.objects.create(
            user=user,
            tenant=tenant,
            role="owner",
        )
        from apps.subscriptions.trials import assign_new_tenant_trial
        assign_new_tenant_trial(tenant)
        return user


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class VerifyEmailSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(min_length=4, max_length=12, trim_whitespace=True)


class ResendVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField()



class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(min_length=8, write_only=True, trim_whitespace=False)
    password_confirm = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, data):
        if data["password"] != data["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": "Passwords don't match."})
        return data


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(
        min_length=8,
        write_only=True, trim_whitespace=False,
        validators=[validate_password],
    )

    def validate_old_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect.")
        return value
