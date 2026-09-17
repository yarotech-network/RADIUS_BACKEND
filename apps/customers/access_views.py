from datetime import timedelta
from django.db.models import Q, Count, Max, Sum, Case, When, Value, CharField
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import serializers, permissions, viewsets
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema
from apps.core.api import tenant_for
from apps.core.pagination import StandardResultsPagination
from apps.routers.models import NASDevice
from apps.routers.selectors import tenant_radius_addresses
from apps.vouchers.models import Voucher
from apps.vouchers.status_rules import classify, filter_status
from .models import DeviceAccessSync, DeviceAccessSession


class AccessFilters(serializers.Serializer):
    search = serializers.CharField(required=False, max_length=200)
    status = serializers.ChoiceField(choices=Voucher.STATUS_CHOICES, required=False)
    activity = serializers.ChoiceField(choices=['online', 'offline', 'never_connected', 'unknown'], required=False)
    source = serializers.ChoiceField(choices=Voucher.SOURCE_CHOICES, required=False)
    plan = serializers.IntegerField(required=False, min_value=1)
    router = serializers.UUIDField(required=False)
    start = serializers.DateField(required=False)
    end = serializers.DateField(required=False)

    def validate(self, attrs):
        if attrs.get('start') and attrs.get('end') and attrs['start'] > attrs['end']:
            raise serializers.ValidationError('Start must not be after end.')
        return attrs


class AccessSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    buyer_name = serializers.SerializerMethodField()
    buyer_email = serializers.SerializerMethodField()
    buyer_phone = serializers.SerializerMethodField()
    reference = serializers.SerializerMethodField()
    plan = serializers.CharField(source='service_terms.name')
    source = serializers.CharField(source='generation_source')
    date = serializers.DateTimeField(source='access_date')
    status = serializers.CharField(source='effective_status')
    connection = serializers.CharField()
    devices = serializers.IntegerField()
    sessions = serializers.IntegerField()
    last_seen = serializers.DateTimeField(allow_null=True)
    bytes_total = serializers.SerializerMethodField()
    expires_at = serializers.DateTimeField(allow_null=True)
    access_code = serializers.SerializerMethodField()

    def payment(self, obj):
        payment = getattr(obj, 'payment', None)
        return payment if payment and payment.tenant_id == obj.tenant_id and payment.status == 'success' else None

    def get_buyer_name(self, obj):
        p = self.payment(obj)
        return p.customer_name if p else ''

    def get_buyer_email(self, obj):
        p = self.payment(obj)
        return p.customer_email if p else ''

    def get_buyer_phone(self, obj):
        p = self.payment(obj)
        return p.customer_phone if p else ''

    def get_reference(self, obj):
        p = self.payment(obj)
        return p.reference if p else f'Voucher #{obj.pk}'

    def get_bytes_total(self, obj):
        return (obj.incoming or 0) + (obj.outgoing or 0)

    def get_access_code(self, obj):
        member = getattr(self.context['request'].user, 'membership', None)
        return obj.username if self.context.get('reveal') and member and member.role in ('owner', 'manager') else None


class CustomerAccessViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AccessSerializer
    pagination_class = StandardResultsPagination
    filter_backends = []

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Voucher.objects.none()
        tenant = tenant_for(self.request)
        now = timezone.now()
        self.sync = DeviceAccessSync.objects.filter(pk=1).first()
        self.fresh = bool(self.sync and self.sync.completed_at and self.sync.completed_at >= now - timedelta(minutes=2))
        evidence = Q(deviceaccesssession__tenant=tenant)
        recent = evidence & Q(deviceaccesssession__stopped_at__isnull=True,
            deviceaccesssession__last_seen_at__gte=now-timedelta(minutes=5), deviceaccesssession__last_seen_at__lte=now)
        if not self.fresh:
            recent &= Q(deviceaccesssession__pk__isnull=True)
        query = classify(Voucher.objects.filter(tenant=tenant, deleted_at__isnull=True, plan__plan_type='voucher'), tenant, now)
        query = query.annotate(
            devices=Count('deviceaccesssession__mac_address', distinct=True, filter=evidence),
            sessions=Count('deviceaccesssession', filter=evidence),
            opens=Count('deviceaccesssession', filter=evidence & Q(deviceaccesssession__stopped_at__isnull=True)),
            online=Count('deviceaccesssession', filter=recent),
            last_seen=Max('deviceaccesssession__last_seen_at', filter=evidence),
            incoming=Sum('deviceaccesssession__bytes_in', filter=evidence),
            outgoing=Sum('deviceaccesssession__bytes_out', filter=evidence),
            access_date=Coalesce('payment__paid_at', 'payment__created_at', 'created_at'),
        ).filter(Q(payment__status='success', payment__tenant=tenant) | (Q(payment__isnull=True) & (Q(sessions__gt=0) | Q(has_accounting=True))))
        query = query.annotate(connection=Case(
            When(online__gt=0, then=Value('online')),
            When(Q(opens__gt=0) | Q(sessions=0, has_accounting=True), then=Value('unknown')),
            When(sessions=0, then=Value('never_connected')),
            default=Value('offline'), output_field=CharField()))
        filters = AccessFilters(data=self.request.query_params)
        filters.is_valid(raise_exception=True)
        values = filters.validated_data
        if 'status' in values:
            query = filter_status(query, values['status'])
        for param, field in [('activity', 'connection'), ('source', 'generation_source'), ('plan', 'plan_id')]:
            if param in values:
                query = query.filter(**{field: values[param]})
        for param, lookup in [('start', 'access_date__date__gte'), ('end', 'access_date__date__lte')]:
            if param in values:
                query = query.filter(**{lookup: values[param]})
        sessions = DeviceAccessSession.objects.filter(tenant=tenant)
        if 'router' in values:
            router = NASDevice.objects.filter(pk=values['router'], tenant=tenant).first()
            if not router:
                raise serializers.ValidationError({'router': 'Router not found.'})
            addresses = {str(ip) for ip in (router.ip_address, router.wireguard_ip) if ip} & tenant_radius_addresses(tenant)
            query = query.filter(pk__in=sessions.filter(nas_address__in=addresses).values('voucher_id'))
        if values.get('search'):
            search = values['search']
            from .device_access_sync import canonical_mac
            query = query.filter(Q(payment__customer_name__icontains=search) | Q(payment__customer_email__icontains=search) |
                Q(payment__customer_phone__icontains=search) | Q(payment__reference__icontains=search) |
                Q(pk__in=sessions.filter(mac_address__icontains=canonical_mac(search) or search).values('voucher_id')))
        return query.select_related('payment', 'plan').order_by('-access_date', '-id')

    @extend_schema(parameters=[AccessFilters])
    def list(self, request, *args, **kwargs):
        query = self.get_queryset()
        response = self.get_paginated_response(self.get_serializer(self.paginate_queryset(query), many=True).data)
        response.data.update(synced_at=self.sync.completed_at if self.sync else None, sync_fresh=self.fresh,
            timezone=timezone.get_current_timezone_name())
        response['Cache-Control'] = 'no-store'
        return response

    def retrieve(self, request, *args, **kwargs):
        obj = self.get_object()
        response = Response(AccessSerializer(obj, context={**self.get_serializer_context(), 'reveal': True}).data)
        response['Cache-Control'] = 'no-store'
        return response
