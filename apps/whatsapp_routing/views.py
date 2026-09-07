from django.db import transaction
from apps.tenants.models import Tenant
from apps.subscriptions.entitlements import require_whatsapp
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
        tenant = tenant_for(self.request)
        with transaction.atomic():
            Tenant.objects.select_for_update().get(pk=tenant.pk)
            require_whatsapp(tenant)
            serializer.save(tenant=tenant, webhook_token=secrets.token_urlsafe(32))

    def perform_update(self, serializer):
        tenant = tenant_for(self.request)
        with transaction.atomic():
            Tenant.objects.select_for_update().get(pk=tenant.pk)
            if serializer.validated_data.get("is_active", serializer.instance.is_active):
                require_whatsapp(tenant)
            serializer.save()
