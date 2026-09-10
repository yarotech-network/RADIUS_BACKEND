from apps.core.api import tenant_for
from rest_framework import viewsets, generics, permissions, status
from rest_framework.response import Response
from django.db.models import Count
from .models import Tenant, TenantMembership, TenantSetting
from .serializers import TenantSerializer, TenantMembershipSerializer, TenantSettingSerializer
from apps.core.permissions import IsPlatformAdmin, IsTenantManager, IsTenantOwner
from django.db import transaction
from rest_framework.exceptions import ValidationError
from .serializers import TenantProfileSerializer
from apps.core.api import audit


class TenantViewSet(viewsets.ModelViewSet):
    """Platform admins see all tenants; owners see their own."""
    serializer_class = TenantSerializer
    filterset_fields = ["is_active", "is_platform_admin"]
    search_fields = ["name", "slug"]

    @transaction.atomic
    def perform_create(self, serializer):
        from apps.subscriptions.trials import assign_new_tenant_trial
        assign_new_tenant_trial(serializer.save())

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Tenant.objects.none()
        if self.request.user.is_platform_admin:
            return Tenant.objects.annotate(
                member_count=Count("memberships", distinct=True),
                voucher_count=Count("vouchers", distinct=True),
            ).order_by("-created_at", "-id")
        return Tenant.objects.filter(
            memberships__user=self.request.user
        ).annotate(
            member_count=Count("memberships", distinct=True),
            voucher_count=Count("vouchers", distinct=True),
        ).order_by("-created_at", "-id")

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [permissions.IsAuthenticated()]
        return [IsPlatformAdmin()]


class TenantMembershipViewSet(viewsets.ModelViewSet):
    serializer_class = TenantMembershipSerializer
    filterset_fields = ["role", "user", "tenant"]
    ordering = ["id"]

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [permissions.IsAuthenticated()]
        return [(IsPlatformAdmin | IsTenantOwner)()]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return TenantMembership.objects.none()
        if self.request.user.is_platform_admin:
            return TenantMembership.objects.all()
        return TenantMembership.objects.filter(tenant=tenant_for(self.request))

    def perform_create(self, serializer):
        if self.request.user.is_platform_admin:
            serializer.save()
        else:
            serializer.save(tenant=tenant_for(self.request))

    def perform_update(self, serializer):
        with transaction.atomic():
            Tenant.objects.select_for_update().get(pk=serializer.instance.tenant_id)
            for field in ("user", "tenant"):
                value = serializer.validated_data.get(field)
                if value and value.pk != getattr(serializer.instance, f"{field}_id"):
                    raise ValidationError({field: "Membership identity cannot be changed."})
            self.check_last_owner(serializer.instance, serializer.validated_data.get("role", serializer.instance.role))
            serializer.save()

    def check_last_owner(self, membership, role):
        if membership.role == "owner" and role != "owner" and not TenantMembership.objects.filter(tenant_id=membership.tenant_id, role="owner").exclude(pk=membership.pk).exists():
            raise ValidationError("The final tenant owner cannot be removed.")

    def perform_destroy(self, instance):
        with transaction.atomic():
            Tenant.objects.select_for_update().get(pk=instance.tenant_id)
            self.check_last_owner(instance, None)
            instance.delete()


class TenantSettingView(generics.RetrieveUpdateAPIView):
    serializer_class = TenantSettingSerializer
    permission_classes = [IsTenantManager]

    def get_object(self):
        settings, _ = TenantSetting.objects.get_or_create(
            tenant=tenant_for(self.request)
        )
        return settings

    def perform_update(self, serializer):
        with transaction.atomic():
            audit(self.request, "tenant.settings_updated", serializer.save())


class TenantProfileView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsTenantManager]
    serializer_class = TenantProfileSerializer

    def get_object(self):
        return tenant_for(self.request)

    def perform_update(self, serializer):
        with transaction.atomic():
            audit(self.request, "tenant.profile_updated", serializer.save())
