from rest_framework import viewsets
from rest_framework import permissions
import secrets
from .models import TenantWhatsAppRoute
from .serializers import TenantWhatsAppRouteSerializer
from apps.core.permissions import IsTenantManager


class WhatsAppRouteViewSet(viewsets.ModelViewSet):
    serializer_class = TenantWhatsAppRouteSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return TenantWhatsAppRoute.objects.none()
        return TenantWhatsAppRoute.objects.filter(tenant=self.request.user.membership.tenant)

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [permissions.IsAuthenticated()]
        return [IsTenantManager()]

    def perform_create(self, serializer):
        serializer.save(
            tenant=self.request.user.membership.tenant,
            webhook_token=secrets.token_urlsafe(32),
        )
