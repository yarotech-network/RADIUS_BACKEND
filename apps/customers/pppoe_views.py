from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from apps.core.api import audit, tenant_for
from apps.core.commands import idempotent
from apps.core.mixins import AuditedCrudMixin
from apps.core.permissions import IsTenantManager
from apps.tenants.models import Tenant
from .models import PPPoEPlan, PPPoEService
from .pppoe_serializers import PPPoEPlanSerializer, PPPoEServiceSerializer, ServiceCreateSerializer, ServiceActionSerializer, ServicePasswordSerializer
from .pppoe_services import create_service, change_service


class PPPoEPlanViewSet(AuditedCrudMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    http_method_names = ["get", "post", "put", "patch", "head", "options"]
    serializer_class = PPPoEPlanSerializer
    filterset_fields = ["is_active"]
    search_fields = ["name"]
    ordering = ["name", "id"]

    def get_permissions(self):
        return [permissions.IsAuthenticated()] if self.action in ("list", "retrieve") else [IsTenantManager()]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return PPPoEPlan.objects.none()
        return PPPoEPlan.objects.filter(tenant=tenant_for(self.request)).select_related("bandwidth_profile")

    def perform_create(self, serializer):
        serializer.save(tenant=tenant_for(self.request))

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        Tenant.objects.select_for_update().get(pk=tenant_for(request).pk)
        return super().update(request, *args, **kwargs)


class PPPoEServiceViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = PPPoEServiceSerializer
    filterset_fields = ["customer"]
    ordering = ["id"]

    def get_permissions(self):
        return [permissions.IsAuthenticated()] if self.action in ("list", "retrieve") else [IsTenantManager()]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return PPPoEService.objects.none()
        return PPPoEService.objects.filter(tenant=tenant_for(self.request)).select_related("plan", "router")

    @extend_schema(request=ServiceCreateSerializer, responses={201:PPPoEServiceSerializer})
    @idempotent
    @transaction.atomic
    def create(self, request):
        payload = ServiceCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        service = create_service(tenant_for(request), payload.validated_data)
        audit(request, "pppoe_service.created", service)
        return Response(self.get_serializer(service).data, status=201)

    def change(self, request, command):
        self.get_object()  # Tenant-scoped 404 before entering the command.
        serializer = ServicePasswordSerializer if command == "password" else ServiceActionSerializer
        payload = serializer(data=request.data)
        payload.is_valid(raise_exception=True)
        service = change_service(tenant_for(request), self.kwargs["pk"], command, payload.validated_data)
        audit(request, f"pppoe_service.{command}", service)
        return Response(self.get_serializer(service).data)

    @extend_schema(request=ServiceActionSerializer, responses=PPPoEServiceSerializer)
    @action(detail=True, methods=["post"])
    @idempotent
    @transaction.atomic
    def renew(self, request, pk=None):
        if not request.headers.get("Idempotency-Key"):
            raise ValidationError("An Idempotency-Key is required for renewal.")
        return self.change(request, "renew")

    @extend_schema(request=ServiceActionSerializer, responses=PPPoEServiceSerializer)
    @action(detail=True, methods=["post"])
    @idempotent
    @transaction.atomic
    def suspend(self, request, pk=None):
        return self.change(request, "suspend")

    @extend_schema(request=ServiceActionSerializer, responses=PPPoEServiceSerializer)
    @action(detail=True, methods=["post"])
    @idempotent
    @transaction.atomic
    def resume(self, request, pk=None):
        return self.change(request, "resume")

    @extend_schema(request=ServicePasswordSerializer, responses=PPPoEServiceSerializer)
    @action(detail=True, methods=["post"], url_path="password")
    @idempotent
    @transaction.atomic
    def password(self, request, pk=None):
        return self.change(request, "password")
