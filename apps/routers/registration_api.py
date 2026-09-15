from django.db import transaction
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from apps.core.api import tenant_for
from apps.core.commands import idempotent
from .models import NASDevice, RouterRegistration, RouterAuditEvent
from .registration import RegistrationSerializer, register, prepare
from .secret_store import secret_store
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from .serializers import NASDeviceSerializer

ScriptResultSerializer = inline_serializer(name='RouterSetupScript', fields={
    'filename': serializers.CharField(), 'script': serializers.CharField(),
    'sha256': serializers.CharField(), 'import_command': serializers.CharField(),
})


def registration_summary(router):
    try:
        item = router.registration
    except RouterRegistration.DoesNotExist:
        return None
    return {
        'nas_identifier': item.nas_identifier, 'hotspot_interface': item.hotspot_interface,
        'hotspot_profile': item.hotspot_profile, 'notes': item.notes, 'setup': item.setup,
        'status': item.status, 'error_code': item.error_code,
        'script_sha256': item.script_sha256 if item.status == 'ready' else '',
    }


class RouterRegistrationActions:
    @extend_schema(request=RegistrationSerializer, responses={201: NASDeviceSerializer})
    @action(detail=False, methods=['post'], url_path='register')
    @idempotent
    def register_router(self, request):
        serializer = RegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        router = register(tenant_for(request), request.user, serializer.validated_data)
        return Response(self.get_serializer(router).data, status=201)

    @extend_schema(request=None, responses=serializers.DictField())
    @action(detail=True, methods=['post'], url_path='setup-script/retry')
    @idempotent
    def retry_setup_script(self, request, pk=None):
        selected = self.get_object()
        with transaction.atomic():
            router = NASDevice.objects.select_for_update().get(pk=selected.pk)
            try:
                registration = router.registration
            except RouterRegistration.DoesNotExist:
                raise ValidationError('This router uses the manual setup flow.')
            if not router.is_active or router.onboarding_state == 'suspended':
                raise ValidationError('Reactivate the router before preparing its script.')
            if registration.status == 'ready':
                return Response(registration_summary(router))
            prepare(registration)
            return Response(registration_summary(router))

    @extend_schema(responses=ScriptResultSerializer)
    @action(detail=True, methods=['get'], url_path='setup-script')
    def setup_script(self, request, pk=None):
        router = self.get_object()
        try:
            registration = router.registration
        except RouterRegistration.DoesNotExist:
            raise ValidationError('This router uses the manual setup flow.')
        if (registration.status != 'ready' or not registration.script_encrypted
                or not router.is_active or router.onboarding_state == 'suspended'):
            return Response({'detail': 'Server preparation must complete before downloading the script.'}, status=409)
        RouterAuditEvent.objects.create(router=router, action='setup_script_revealed', details={'actor_id': request.user.pk})
        return Response({
            'filename': f'yarotech-{router.pk}.rsc',
            'script': secret_store.decrypt(registration.script_encrypted),
            'sha256': registration.script_sha256,
            'import_command': f'/import file-name="yarotech-{router.pk}.rsc"',
        }, headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})
