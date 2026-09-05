from apps.core.api import tenant_for
from rest_framework import viewsets
from rest_framework import permissions
from .models import MacDevice
from .serializers import MacDeviceSerializer
from apps.core.permissions import IsTenantManager
from apps.core.mixins import AuditedCrudMixin


class MacDeviceViewSet(AuditedCrudMixin, viewsets.ModelViewSet):
    filterset_fields = ["is_active", "plan"]
    search_fields = ["device_name", "mac_address"]
    serializer_class = MacDeviceSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return MacDevice.objects.none()
        return MacDevice.objects.filter(tenant=tenant_for(self.request))

    def perform_create(self, serializer):
        serializer.save(tenant=tenant_for(self.request))

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [permissions.IsAuthenticated()]
        return [IsTenantManager()]
