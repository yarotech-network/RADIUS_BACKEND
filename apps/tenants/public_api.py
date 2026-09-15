from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, serializers
from apps.vouchers.models import InternetPlan
from .models import Tenant


class PublicTenantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = ["id", "slug", "name"]


class PublicPlanSerializer(serializers.ModelSerializer):
    max_devices = serializers.SerializerMethodField()

    def get_max_devices(self, instance):
        from apps.vouchers.device_policy import max_new_devices
        return max_new_devices()

    duration_hours = serializers.DecimalField(max_digits=16, decimal_places=6, coerce_to_string=False, read_only=True)
    class Meta:
        model = InternetPlan
        fields = ["id", "name", "price", "duration_hours", "rate_limit", "data_limit", "max_devices", "plan_type"]


class PublicTenantView(generics.RetrieveAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = PublicTenantSerializer
    queryset = Tenant.objects.filter(is_active=True, is_platform_admin=False)
    lookup_field = "slug"


class PublicPlansView(generics.ListAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = PublicPlanSerializer
    search_fields = ["name"]
    ordering_fields = ["price", "duration_hours"]
    ordering = ["price", "id"]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        return response

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return InternetPlan.objects.none()
        tenant = get_object_or_404(Tenant, slug=self.kwargs["slug"], is_active=True, is_platform_admin=False)
        from apps.subscriptions.access import tenant_access
        if tenant_access(tenant)["required"]:
            return InternetPlan.objects.none()
        from django.conf import settings
        from django.db.models import Q
        query = InternetPlan.objects.filter(tenant=tenant, is_active=True, is_public=True, archived_at__isnull=True)
        if getattr(settings, 'IOT_PUBLIC_PURCHASE_ENABLED', False) and getattr(settings, 'RADIUS_REST_ENABLED', False):
            return query.filter(Q(plan_type='voucher') | Q(plan_type='iot_mac', public_router__is_active=True, public_router__tenant=tenant, public_router__onboarding_state='active'))
        return query.filter(plan_type='voucher')
