from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.utils.text import slugify
from apps.tenants.models import Tenant, TenantMembership

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    role = serializers.CharField(read_only=True)
    tenant_name = serializers.CharField(source="membership.tenant.name", read_only=True, default=None)

    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "phone", "role", "tenant_name"]
        read_only_fields = ["id", "role", "tenant_name"]


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(min_length=3)
    email = serializers.EmailField()
    password = serializers.CharField(
        min_length=8,
        write_only=True,
        validators=[validate_password],
    )
    password_confirm = serializers.CharField(write_only=True)
    tenant_name = serializers.CharField(min_length=2)
    phone = serializers.CharField(min_length=10)

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Username already taken.")
        return value

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email already registered.")
        return value

    def validate_tenant_name(self, value):
        slug = slugify(value)
        if not slug:
            raise serializers.ValidationError("Tenant name must contain letters or numbers.")
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
        return user


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(min_length=8, write_only=True)
    password_confirm = serializers.CharField(write_only=True)

    def validate(self, data):
        if data["password"] != data["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": "Passwords don't match."})
        return data


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField()
    new_password = serializers.CharField(
        min_length=8,
        validators=[validate_password],
    )

    def validate_old_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect.")
        return value
