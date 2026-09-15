import uuid
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema
from apps.core.api import tenant_for
from apps.core.models import AuditEvent
from apps.core.permissions import IsPlatformAdmin, IsTenantManager
from apps.routers.secret_store import secret_store
from apps.subscriptions.entitlements import require_whatsapp
from apps.tenants.models import Tenant
from .models import SharedWhatsAppEndpoint, TenantWhatsAppEntryRoute, new_entry_selector
from .shared_routing import configured_key, hash_key_fingerprint, entry_preview
from .webhook import webhook_configured
from django.conf import settings


class StaleRoutingSettings(APIException):
    status_code = 409
    default_detail = 'Settings changed. Reload and review before saving again.'


def keys_ready():
    try:
        configured_key('WHATSAPP_TENANT_ROUTING_SIGNING_KEY')
        configured_key('WHATSAPP_SENDER_HASH_KEY')
        return True
    except ImproperlyConfigured:
        return False


def endpoint_data(endpoint):
    return {'exists': endpoint is not None, 'version': str(endpoint.version) if endpoint else None,
        'phone_number_id': endpoint.phone_number_id if endpoint else '',
        'display_number': endpoint.display_number if endpoint else '',
        'is_active': endpoint.is_active if endpoint else False,
        'token_saved': bool(endpoint and endpoint.access_token_encrypted),
        'provider_verified': bool(endpoint and endpoint.verified_at), 'routing_keys_ready': keys_ready(),
        'sales_available': sales_configured(endpoint),
        'webhook_enabled': getattr(settings, 'WHATSAPP_WEBHOOK_ENABLED', False),
        'webhook_configured': webhook_configured()}


def sales_configured(endpoint):
    from .provider import api_url
    if not endpoint or not keys_ready():
        return False
    try:
        api_url(endpoint.phone_number_id)
    except ImproperlyConfigured:
        return False
    return bool(endpoint and endpoint.is_active and endpoint.verified_at and keys_ready()
        and endpoint.hash_key_fingerprint == hash_key_fingerprint()
        and settings.WHATSAPP_WEBHOOK_ENABLED and webhook_configured()
        and settings.WHATSAPP_CONSUMER_ENABLED and settings.WHATSAPP_SEND_ENABLED
        and settings.WHATSAPP_GRAPH_VERSION)


class SharedEndpointWrite(serializers.Serializer):
    expected_version = serializers.UUIDField(allow_null=True)
    phone_number_id = serializers.RegexField(r'^[0-9]{1,100}$', max_length=100)
    display_number = serializers.RegexField(r'^\+?[1-9][0-9]{6,14}$', max_length=16)
    access_token = serializers.CharField(max_length=500, required=False, trim_whitespace=False, write_only=True)
    is_active = serializers.BooleanField()

    def validate_access_token(self, value):
        if not value.strip() or value.startswith('enc:v1:'):
            raise ValidationError('Provide a non-empty plaintext replacement token.')
        return value


class SharedEndpointRead(serializers.Serializer):
    exists = serializers.BooleanField()
    version = serializers.UUIDField(allow_null=True)
    phone_number_id = serializers.CharField()
    display_number = serializers.CharField()
    is_active = serializers.BooleanField()
    token_saved = serializers.BooleanField()
    provider_verified = serializers.BooleanField()
    routing_keys_ready = serializers.BooleanField()
    sales_available = serializers.BooleanField()
    webhook_enabled = serializers.BooleanField()
    webhook_configured = serializers.BooleanField()


class SharedEndpointView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(responses=SharedEndpointRead)
    def get(self, request):
        return Response(endpoint_data(SharedWhatsAppEndpoint.objects.filter(pk=1).first()))

    @extend_schema(request=SharedEndpointWrite, responses=SharedEndpointRead)
    def put(self, request):
        serializer = SharedEndpointWrite(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        with transaction.atomic():
            endpoint, created = SharedWhatsAppEndpoint.objects.get_or_create(pk=1)
            endpoint = SharedWhatsAppEndpoint.objects.select_for_update().get(pk=endpoint.pk)
            if (None if created else endpoint.version) != values['expected_version']:
                raise StaleRoutingSettings()
            if not values.get('access_token') and not endpoint.access_token_encrypted:
                raise ValidationError('An access token is required for the shared endpoint.')
            if values['is_active'] and not keys_ready():
                raise ValidationError('Configure routing and sender-hashing keys before enabling routing previews.')
            fingerprint = hash_key_fingerprint() if keys_ready() else ''
            if endpoint.hash_key_fingerprint and endpoint.hash_key_fingerprint != fingerprint:
                raise ValidationError('Sender hash key changed. Reconcile existing sender bindings before changing this endpoint.')
            # Endpoint identity must not be reassigned while purchases are unresolved.
            if endpoint.phone_number_id and endpoint.phone_number_id != values['phone_number_id']:
                from .models import WhatsAppRoutingHold
                if WhatsAppRoutingHold.objects.filter(binding__endpoint=endpoint, released_at__isnull=True).exists():
                    raise ValidationError('Resolve pending purchases before replacing the shared phone number.')
            for field in ('phone_number_id', 'display_number', 'is_active'):
                setattr(endpoint, field, values[field])
            if values.get('access_token'):
                endpoint.access_token_encrypted = secret_store.encrypt(values['access_token'])
            endpoint.hash_key_fingerprint = fingerprint
            endpoint.version = uuid.uuid4()
            endpoint.verified_at = None
            endpoint.save()
            AuditEvent.objects.create(actor=request.user, action='whatsapp.shared_endpoint_saved',
                resource='whatsapp.shared_endpoint:1', details={'token_replaced': bool(values.get('access_token'))})
        return Response(endpoint_data(endpoint))


class EntryRouteWrite(serializers.Serializer):
    action = serializers.ChoiceField(choices=['create', 'rotate', 'revoke'])
    expected_version = serializers.UUIDField(allow_null=True)


class VerifyEndpointWrite(serializers.Serializer):
    expected_version = serializers.UUIDField()


class VerifyEndpointView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(request=VerifyEndpointWrite, responses=SharedEndpointRead)
    def post(self, request):
        from .provider import verify_endpoint, ProviderFailure
        serializer = VerifyEndpointWrite(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            endpoint = SharedWhatsAppEndpoint.objects.select_for_update().filter(pk=1).first()
            if not endpoint or endpoint.version != serializer.validated_data['expected_version']:
                raise StaleRoutingSettings()
            attempt = uuid.uuid4()
            endpoint.verification_attempt = attempt
            endpoint.save(update_fields=['verification_attempt'])
        error = ''
        try:
            verify_endpoint(endpoint)
        except ProviderFailure as exc:
            error = exc.code
        except Exception:
            error = 'verification_unavailable'
        with transaction.atomic():
            current = SharedWhatsAppEndpoint.objects.select_for_update().get(pk=1)
            if current.version != endpoint.version or current.verification_attempt != attempt:
                raise StaleRoutingSettings()
            current.verified_at = None if error else timezone.now()
            current.save(update_fields=['verified_at'])
            AuditEvent.objects.create(actor=request.user, action='whatsapp.provider_verification',
                resource='whatsapp.shared_endpoint:1', details={'verified': not bool(error), 'code': error})
        if error:
            return Response({'detail': 'Provider verification did not succeed.', 'code': error}, status=400)
        return Response(endpoint_data(current))


class EntryRouteRead(serializers.Serializer):
    exists = serializers.BooleanField()
    version = serializers.UUIDField(allow_null=True)
    revoked = serializers.BooleanField()
    shared_number = serializers.CharField()
    preview_url = serializers.CharField(allow_null=True)
    routing_keys_ready = serializers.BooleanField()
    sales_available = serializers.BooleanField()


def entry_data(tenant):
    route = TenantWhatsAppEntryRoute.objects.filter(tenant=tenant).first()
    endpoint = SharedWhatsAppEndpoint.objects.filter(pk=1).first()
    ready = keys_ready()
    return {'exists': bool(route), 'version': str(route.version) if route else None,
        'revoked': bool(route and route.revoked_at), 'shared_number': endpoint.display_number if endpoint else '',
        'preview_url': entry_preview(route, endpoint) if ready else None,
        'routing_keys_ready': ready, 'sales_available': sales_configured(endpoint) and bool(route and not route.revoked_at)}


class EntryRouteView(APIView):
    permission_classes = [IsTenantManager]

    @extend_schema(responses=EntryRouteRead)
    def get(self, request):
        return Response(entry_data(tenant_for(request)))

    @extend_schema(request=EntryRouteWrite, responses=EntryRouteRead)
    def post(self, request):
        tenant = tenant_for(request)
        serializer = EntryRouteWrite(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        with transaction.atomic():
            SharedWhatsAppEndpoint.objects.select_for_update().filter(pk=1).first()
            Tenant.objects.select_for_update().get(pk=tenant.pk)
            route = TenantWhatsAppEntryRoute.objects.select_for_update().filter(tenant=tenant).first()
            if (route.version if route else None) != values['expected_version']:
                raise StaleRoutingSettings()
            if values['action'] != 'revoke':
                require_whatsapp(tenant)
            if values['action'] == 'create':
                if route:
                    raise ValidationError('A link already exists. Rotate it explicitly to replace it.')
                route = TenantWhatsAppEntryRoute.objects.create(tenant=tenant)
            else:
                if not route:
                    raise ValidationError('Create a link first.')
                if values['action'] == 'rotate':
                    route.selector = new_entry_selector()
                    route.rotated_at = timezone.now()
                    route.revoked_at = None
                else:
                    route.revoked_at = timezone.now()
                route.version = uuid.uuid4()
                route.save()
            AuditEvent.objects.create(tenant=tenant, actor=request.user, action=f'whatsapp.entry_{values["action"]}',
                resource=f'whatsapp.entry_route:{route.pk}', details={})
        return Response(entry_data(tenant))
