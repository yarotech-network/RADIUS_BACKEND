from rest_framework import viewsets
from rest_framework import permissions
from .models import MacDevice
from .serializers import MacDeviceSerializer
from apps.core.permissions import IsTenantManager


class MacDeviceViewSet(viewsets.ModelViewSet):
    serializer_class = MacDeviceSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return MacDevice.objects.none()
        return MacDevice.objects.filter(tenant=self.request.user.membership.tenant)

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.user.membership.tenant)

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [permissions.IsAuthenticated()]
        return [IsTenantManager()]
