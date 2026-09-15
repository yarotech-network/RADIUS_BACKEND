import uuid
from django.db import transaction
from django.db.models import OuterRef, Subquery
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from drf_spectacular.utils import extend_schema
from apps.core.api import tenant_for
from apps.core.permissions import IsTenantManager
from apps.core.models import AuditEvent
from apps.routers.secret_store import secret_store
from apps.subscriptions.entitlements import require_whatsapp
from .models import TenantWhatsAppEntryRoute, SharedWhatsAppEndpoint, WhatsAppOrder, WhatsAppOutbound
from .shared_api import StaleRoutingSettings
from .reminders import DEFAULTS, preferences
from .conversations import queue_message, credential_text


class ReminderSettings(serializers.Serializer):
    expected_version = serializers.UUIDField(write_only=True)
    enabled = serializers.BooleanField()
    unused_enabled = serializers.BooleanField()
    expiry_enabled = serializers.BooleanField()
    unused_hours = serializers.IntegerField(min_value=1, max_value=720)
    short_lead_hours = serializers.IntegerField(min_value=1, max_value=24)
    medium_lead_hours = serializers.IntegerField(min_value=1, max_value=168)
    long_lead_hours = serializers.IntegerField(min_value=1, max_value=720)
    unused_template = serializers.RegexField(r'^[a-z0-9_]*$', max_length=80, allow_blank=True)
    expiry_template = serializers.RegexField(r'^[a-z0-9_]*$', max_length=80, allow_blank=True)
    language = serializers.RegexField(r'^[a-z]{2,3}(?:_[A-Z]{2})?$', max_length=10)


class ReminderSettingsView(APIView):
    permission_classes = [IsTenantManager]

    def get(self, request):
        tenant = tenant_for(request)
        route = TenantWhatsAppEntryRoute.objects.filter(tenant=tenant).first()
        return Response({'version': str(route.version) if route else None, **preferences(tenant.pk)})

    @extend_schema(request=ReminderSettings)
    def put(self, request):
        tenant = tenant_for(request)
        serializer = ReminderSettings(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        with transaction.atomic():
            SharedWhatsAppEndpoint.objects.select_for_update().filter(pk=1).first()
            route = get_object_or_404(TenantWhatsAppEntryRoute.objects.select_for_update(), tenant=tenant)
            if route.version != values.pop('expected_version'):
                raise StaleRoutingSettings()
            if values['enabled']:
                require_whatsapp(tenant)
                if values['unused_enabled'] and not values['unused_template'] or values['expiry_enabled'] and not values['expiry_template']:
                    raise ValidationError('Configure the approved reminder template names before enabling reminders.')
            route.reminder_preferences, route.version = values, uuid.uuid4()
            route.save(update_fields=['reminder_preferences', 'version'])
            AuditEvent.objects.create(tenant=tenant, actor=request.user, action='whatsapp.reminder_settings',
                resource=f'whatsapp.entry_route:{route.pk}', details={'enabled': values['enabled']})
        return Response({'version': str(route.version), **values})


class OrderSummary(serializers.ModelSerializer):
    payment_status = serializers.CharField(source='payment.status')
    fulfilled = serializers.SerializerMethodField()
    delivery_state = serializers.CharField(read_only=True, allow_null=True)
    class Meta:
        model = WhatsAppOrder
        fields = ['id', 'state', 'payment_status', 'fulfilled', 'error_code', 'delivery_state', 'created_at']
    def get_fulfilled(self, obj):
        return bool(obj.payment.status == 'success' and obj.payment.verified_at and obj.payment.voucher_id)


class OrderRecoveryList(generics.ListAPIView):
    permission_classes = [IsTenantManager]
    serializer_class = OrderSummary
    def get_queryset(self):
        return WhatsAppOrder.objects.filter(tenant=tenant_for(self.request)).select_related('payment').annotate(
            delivery_state=Subquery(WhatsAppOutbound.objects.filter(order_id=OuterRef('pk'), kind='credentials').order_by('-created_at').values('state')[:1])).order_by('-pk')


class RecoveryAction(serializers.Serializer):
    action = serializers.ChoiceField(choices=['recheck', 'resend'])
    acknowledge_duplicate_risk = serializers.BooleanField(default=False)
    request_id = serializers.UUIDField()


class OrderRecoveryAction(APIView):
    permission_classes = [IsTenantManager]
    @extend_schema(request=RecoveryAction)
    def post(self, request, pk):
        tenant = tenant_for(request)
        serializer = RecoveryAction(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        hint = get_object_or_404(WhatsAppOrder, pk=pk, tenant=tenant)
        with transaction.atomic():
            endpoint = SharedWhatsAppEndpoint.objects.select_for_update().get(pk=hint.endpoint_id)
            order = WhatsAppOrder.objects.select_for_update(of=('self',)).select_related('payment__voucher', 'tenant').get(pk=hint.pk)
            if order.claim:
                raise ValidationError('A worker is checking this order. Retry after it finishes.')
            if values['action'] == 'recheck':
                if order.state not in ('fulfilled', 'failed'):
                    order.state = 'unknown' if order.state == 'recovery' else order.state
                    order.next_check_at, order.attempts = timezone.now(), 0
                    order.save(update_fields=['state', 'next_check_at', 'attempts'])
            else:
                if not values['acknowledge_duplicate_risk']:
                    raise ValidationError('Confirm that another voucher message may reach the customer.')
                if not endpoint.verified_at or endpoint.phone_number_id != order.phone_number_id:
                    raise ValidationError('Verify the original WhatsApp number before retrying delivery.')
                try:
                    text = credential_text(order)
                except ValueError:
                    raise ValidationError('Only a verified fulfilled voucher can be resent.')
                row = queue_message(endpoint=endpoint, tenant_id=tenant.pk,
                    sender=secret_store.decrypt(order.recipient_encrypted), customer_hash=order.customer_hash,
                    text=text, dedup_key=f'manual:{order.pk}:{values["request_id"]}', order=order, kind='credentials')
                if row.state == 'pending':
                    row.endpoint_version = endpoint.version
                    row.save(update_fields=['endpoint_version'])
            AuditEvent.objects.create(tenant=tenant, actor=request.user, action='whatsapp.order_'+values['action'],
                resource=f'whatsapp.order:{order.pk}', details={'request_id': str(values['request_id'])})
        return Response({'detail': 'Recovery request recorded. The worker will process it.'})
