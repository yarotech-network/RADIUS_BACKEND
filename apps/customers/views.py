from django.core import signing
from django.db import transaction
from django.utils import timezone
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
from .models import Customer
from .serializers import CustomerSerializer, ImportRequestSerializer, ImportPreviewSerializer, ImportResultSerializer
from .imports import SALT, fingerprint, parse_rows, validate_token


class CustomerViewSet(AuditedCrudMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin,
                      mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    http_method_names = ["get", "post", "put", "patch", "head", "options"]
    serializer_class = CustomerSerializer
    search_fields = ["reference", "name", "email", "phone"]
    ordering_fields = ["name", "reference", "created_at"]
    ordering = ["name", "id"]

    def get_permissions(self):
        return [permissions.IsAuthenticated()] if self.action in ("list", "retrieve") else [IsTenantManager()]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Customer.objects.none()
        from django.db.models import Exists, OuterRef
        from .models import PPPoEService
        query = Customer.objects.filter(tenant=tenant_for(self.request)).annotate(has_service=Exists(PPPoEService.objects.filter(customer_id=OuterRef("pk"))))
        if self.action == "list":
            state = self.request.query_params.get("status", "")
            if state not in ("", "current", "archived"):
                raise ValidationError({"status": "Use current or archived."})
            if state:
                query = query.filter(archived_at__isnull=state == "current")
        return query

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if not getattr(self, "swagger_fake_view", False):
            context["tenant"] = tenant_for(self.request)
        return context

    def lock_tenant(self):
        return Tenant.objects.select_for_update().get(pk=tenant_for(self.request).pk)

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        self.lock_tenant()
        return super().create(request, *args, **kwargs)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        self.lock_tenant()
        return super().update(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(tenant=tenant_for(self.request))

    @action(detail=True, methods=["post"])
    @idempotent
    @transaction.atomic
    def archive(self, request, pk=None):
        self.lock_tenant()
        customer = self.get_object()
        from .models import PPPoEService
        if PPPoEService.objects.filter(customer=customer, suspended=False).exists():
            raise ValidationError("Suspend this customer service before archiving.")
        if customer.archived_at is None:
            customer.archived_at = timezone.now()
            customer.save(update_fields=["archived_at", "updated_at"])
            audit(request, "customer.archived", customer)
        return Response(self.get_serializer(customer).data)

    @action(detail=True, methods=["post"])
    @idempotent
    @transaction.atomic
    def restore(self, request, pk=None):
        self.lock_tenant()
        customer = self.get_object()
        if customer.archived_at is not None:
            customer.archived_at = None
            customer.save(update_fields=["archived_at", "updated_at"])
            audit(request, "customer.restored", customer)
        return Response(self.get_serializer(customer).data)

    @extend_schema(request=ImportRequestSerializer, responses=ImportPreviewSerializer)
    @action(detail=False, methods=["post"], url_path="import-preview")
    def import_preview(self, request):
        payload = ImportRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        tenant = tenant_for(request)
        text = payload.validated_data["csv"]
        rows = parse_rows(text, tenant)
        token = signing.dumps(fingerprint(request, tenant, text), salt=SALT)
        return Response({"count": len(rows), "rows": rows, "preview_token": token})

    @extend_schema(request=ImportRequestSerializer, responses={201: ImportResultSerializer})
    @action(detail=False, methods=["post"], url_path="import-confirm")
    @idempotent
    @transaction.atomic
    def import_confirm(self, request):
        payload = ImportRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        tenant = self.lock_tenant()
        text = payload.validated_data["csv"]
        validate_token(request, tenant, text, payload.validated_data.get("preview_token", ""))
        rows = parse_rows(text, tenant)
        for row in rows:
            customer = Customer.objects.create(tenant=tenant, **row)
            audit(request, "customer.imported", customer)
        return Response({"count": len(rows)}, status=201)
