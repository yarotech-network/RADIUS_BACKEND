from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, serializers
from apps.vouchers.models import InternetPlan
from .models import Tenant


class PublicTenantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = ["id", "slug", "name"]


class PublicPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = InternetPlan
        fields = ["id", "name", "price", "duration_hours", "rate_limit", "data_limit"]


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

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return InternetPlan.objects.none()
        tenant = get_object_or_404(Tenant, slug=self.kwargs["slug"], is_active=True, is_platform_admin=False)
        return InternetPlan.objects.filter(tenant=tenant, is_active=True)
