from apps.core.api import tenant_for
from rest_framework import viewsets
from rest_framework import permissions
from .models import MacDevice
from .serializers import MacDeviceSerializer
from apps.core.permissions import IsTenantManager
from apps.core.mixins import AuditedCrudMixin
from rest_framework.response import Response
from .accounting import device_accounting


class MacDeviceViewSet(AuditedCrudMixin, viewsets.ModelViewSet):
    filterset_fields = ["is_active", "plan", "router", "access_type"]
    search_fields = ["device_name", "mac_address"]
    serializer_class = MacDeviceSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return MacDevice.objects.none()
        return MacDevice.objects.filter(tenant=tenant_for(self.request)).select_related("plan", "router")

    def perform_create(self, serializer):
        serializer.save(tenant=tenant_for(self.request))

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [permissions.IsAuthenticated()]
        return [IsTenantManager()]

    def list(self, request, *args, **kwargs):
        rows = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        context = self.get_serializer_context()
        context["device_accounting"] = device_accounting(rows, tenant_for(request))
        return self.get_paginated_response(self.get_serializer(rows, many=True, context=context).data)

    def retrieve(self, request, *args, **kwargs):
        device = self.get_object()
        context = self.get_serializer_context()
        context["device_accounting"] = device_accounting([device], tenant_for(request))
        return Response(self.get_serializer(device, context=context).data)
