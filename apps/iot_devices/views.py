from django.db import transaction
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from drf_spectacular.utils import extend_schema
from apps.core.commands import idempotent
from apps.core.api import audit
from .serializers import DeviceActionSerializer, RenewalRequestSerializer, RenewalSerializer
from .lifecycle import check_version, transition, renew
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
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]
    filterset_fields = ["is_active", "plan", "router", "access_type"]
    search_fields = ["device_name", "mac_address"]
    serializer_class = MacDeviceSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return MacDevice.objects.none()
        query = MacDevice.objects.filter(tenant=tenant_for(self.request)).select_related('plan', 'router')
        if self.action == 'list' and self.request.query_params.get('include_deleted') != 'true':
            query = query.filter(deleted_at__isnull=True).exclude(status='deleted')
        if getattr(self, '_lock_device', False):
            query = query.select_for_update(of=('self',))
        return query

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


    def get_object(self):
        if self.request.method in ('PUT','PATCH','DELETE') or self.action in ('lifecycle','renew'):
            self._lock_device = True
        return super().get_object()

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        device = self.get_object()
        try:
            version = int(request.query_params.get('expected_version', ''))
        except (TypeError, ValueError):
            raise ValidationError('Provide the expected device version.')
        check_version(device, version)
        transition(device, 'delete')
        audit(request, 'macdevice.deleted', device, {'version':device.version, 'retained':True})
        return Response(status=204)

    @extend_schema(request=DeviceActionSerializer, responses=MacDeviceSerializer)
    @action(detail=True, methods=['post'])
    @idempotent
    @transaction.atomic
    def lifecycle(self, request, pk=None):
        serializer = DeviceActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device = self.get_object()
        check_version(device, serializer.validated_data['expected_version'])
        transition(device, serializer.validated_data['action'])
        audit(request, 'macdevice.'+serializer.validated_data['action'], device, {'version':device.version})
        return Response(self.get_serializer(device).data)

    @extend_schema(request=RenewalRequestSerializer, responses=MacDeviceSerializer)
    @action(detail=True, methods=['post'])
    @idempotent
    @transaction.atomic
    def renew(self, request, pk=None):
        if not request.headers.get('Idempotency-Key'):
            raise ValidationError('An Idempotency-Key is required for renewal.')
        serializer = RenewalRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device = self.get_object()
        check_version(device, serializer.validated_data['expected_version'])
        # Snapshot the selected plan while its definition is locked.
        from apps.vouchers.models import InternetPlan
        plan = InternetPlan.objects.select_for_update().filter(tenant=tenant_for(request), pk=serializer.validated_data['plan'].pk).first()
        if plan is None:
            raise ValidationError({'plan': 'Choose a plan belonging to this tenant.'})
        renew(device, plan, request.user)
        audit(request, 'macdevice.renewed', device, {'version':device.version, 'source':'operator_grant'})
        return Response(self.get_serializer(device).data)

    @extend_schema(responses=RenewalSerializer(many=True))
    @action(detail=True, methods=['get'])
    def renewals(self, request, pk=None):
        device = self.get_object()
        rows = device.renewals.filter(tenant=tenant_for(request))
        return self.get_paginated_response(RenewalSerializer(self.paginate_queryset(rows), many=True).data)
