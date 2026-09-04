from rest_framework import viewsets, generics, permissions, status
from rest_framework.response import Response
from django.db.models import Count
from .models import Tenant, TenantMembership, TenantSetting
from .serializers import TenantSerializer, TenantMembershipSerializer, TenantSettingSerializer
from apps.core.permissions import IsPlatformAdmin, IsTenantManager, IsTenantOwner


class TenantViewSet(viewsets.ModelViewSet):
    """Platform admins see all tenants; owners see their own."""
    serializer_class = TenantSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Tenant.objects.none()
        if self.request.user.is_platform_admin:
            return Tenant.objects.annotate(
                member_count=Count("memberships"),
                voucher_count=Count("vouchers"),
            ).order_by("-created_at", "-id")
        return Tenant.objects.filter(
            memberships__user=self.request.user
        ).annotate(
            member_count=Count("memberships"),
            voucher_count=Count("vouchers"),
        ).order_by("-created_at", "-id")

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [permissions.IsAuthenticated()]
        return [IsPlatformAdmin()]


class TenantMembershipViewSet(viewsets.ModelViewSet):
    serializer_class = TenantMembershipSerializer

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [permissions.IsAuthenticated()]
        return [(IsPlatformAdmin | IsTenantOwner)()]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return TenantMembership.objects.none()
        if self.request.user.is_platform_admin:
            return TenantMembership.objects.all()
        return TenantMembership.objects.filter(tenant=self.request.user.membership.tenant)

    def perform_create(self, serializer):
        if self.request.user.is_platform_admin:
            serializer.save()
        else:
            serializer.save(tenant=self.request.user.membership.tenant)


class TenantSettingView(generics.RetrieveUpdateAPIView):
    serializer_class = TenantSettingSerializer
    permission_classes = [IsTenantManager]

    def get_object(self):
        settings, _ = TenantSetting.objects.get_or_create(
            tenant=self.request.user.membership.tenant
        )
        return settings
