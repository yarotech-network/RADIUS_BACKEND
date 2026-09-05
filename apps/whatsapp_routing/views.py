from apps.core.api import tenant_for
from rest_framework import viewsets
from rest_framework import permissions
import secrets
from .models import TenantWhatsAppRoute
from .serializers import TenantWhatsAppRouteSerializer
from apps.core.permissions import IsTenantManager
from apps.core.mixins import AuditedCrudMixin


class WhatsAppRouteViewSet(AuditedCrudMixin, viewsets.ModelViewSet):
    filterset_fields = ["is_active"]
    search_fields = ["phone_number_id"]
    serializer_class = TenantWhatsAppRouteSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return TenantWhatsAppRoute.objects.none()
        return TenantWhatsAppRoute.objects.filter(tenant=tenant_for(self.request))

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [permissions.IsAuthenticated()]
        return [IsTenantManager()]

    def perform_create(self, serializer):
        serializer.save(
            tenant=tenant_for(self.request),
            webhook_token=secrets.token_urlsafe(32),
        )
