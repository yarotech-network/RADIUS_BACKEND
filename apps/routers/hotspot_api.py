from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from .hotspot_setup import HotspotIntentSerializer, StrictSerializer, save_intent, setup_result
from .discovery import collect, DiscoveryError
from .models import NASDevice, RouterAuditEvent


class SetupResultSerializer(serializers.Serializer):
    device_profile = serializers.DictField(child=serializers.CharField(allow_blank=True))
    compatibility = serializers.JSONField()
    discovery = serializers.JSONField(allow_null=True)
    version = serializers.CharField()
    execution_enabled = serializers.BooleanField()
    supported_targets = serializers.ListField(child=serializers.CharField())
    gate = serializers.CharField()
    inventory_source = serializers.CharField()
    intent = serializers.JSONField(allow_null=True)
    evidence = serializers.ListField(child=serializers.JSONField())
    ready = serializers.BooleanField()


class DiscoveryRequestSerializer(StrictSerializer):
    expected_updated_at = serializers.DateTimeField()


class LabPackageRequestSerializer(StrictSerializer):
    expected_updated_at = serializers.DateTimeField()
    intent_id = serializers.UUIDField()
    lab_acknowledged = serializers.BooleanField()
    dns_server = serializers.IPAddressField(protocol="IPv4")

    def validate_lab_acknowledged(self, value):
        if not value:
            raise serializers.ValidationError("Acknowledge that this is an unvalidated laboratory package.")
        return value


class LabPackageResultSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    generator = serializers.CharField()
    lab_only = serializers.BooleanField()
    hardware_validated = serializers.BooleanField()
    files = serializers.DictField(child=serializers.CharField())
    sha256 = serializers.DictField(child=serializers.CharField())


class RevokeIntentSerializer(serializers.Serializer):
    intent_id = serializers.UUIDField()


def private_response(data, status=200):
    response = Response(data, status=status)
    response["Cache-Control"] = "no-store"
    return response


class HotspotSetupActions:
    @extend_schema(request=LabPackageRequestSerializer, responses=LabPackageResultSerializer)
    @action(detail=True, methods=["post"], url_path="hotspot-setup/lab-package", throttle_classes=[ScopedRateThrottle], throttle_scope="router_hotspot_setup")
    def export_hotspot_lab_package(self, request, pk=None):
        from .hotspot_generator import generate
        router = self.get_object()
        serializer = LabPackageRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        with transaction.atomic():
            router = NASDevice.objects.select_for_update().get(pk=router.pk)
            if router.updated_at != values['expected_updated_at']:
                return private_response({'detail':'Router changed. Refresh before exporting.'}, 409)
            if router.deployment_status == 'deploying' or router.operations.filter(status__in=['pending','running']).exists():
                return private_response({'detail':'Wait for the current provisioning operation.'}, 409)
            result = setup_result(router)
            if not result['intent'] or result['intent']['id'] != str(values['intent_id']) or result['intent']['state'] != 'review':
                return private_response({'detail':'The selected review is no longer current. Save a fresh review.'}, 409)
            package = generate(router, result, values['dns_server'])
            previous = router.audit_events.filter(action='hotspot.lab_package_exported', details__intent_id=package['id']).first()
            if previous and previous.details.get('sha256') != package['sha256']:
                return private_response({'detail':'This review already has a different package. Revoke it and save a new review before changing the DNS server.'}, 409)
            RouterAuditEvent.objects.get_or_create(router=router, action='hotspot.lab_package_exported', details={
                'intent_id':package['id'], 'generator':package['generator'], 'sha256':package['sha256'], 'actor_id':request.user.pk,
            })
            return private_response(package)


    @extend_schema(request=DiscoveryRequestSerializer, responses=SetupResultSerializer)
    @action(detail=True, methods=["post"], url_path="hotspot-setup/discover", throttle_classes=[ScopedRateThrottle], throttle_scope="router_discovery")
    def discover_hotspot_router(self, request, pk=None):
        router = self.get_object()
        serializer = DiscoveryRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if router.updated_at != serializer.validated_data["expected_updated_at"]:
            return private_response({"detail": "Router changed. Reload before discovery."}, 409)
        if router.deployment_status == "deploying" or router.operations.filter(status__in=["pending", "running"]).exists():
            return private_response({"detail": "Wait for the current provisioning operation."}, 409)
        started = timezone.now()
        try:
            inventory = collect(router)
        except DiscoveryError as error:
            # Keep previous inventory. Store only a fixed error code, never HTTP bodies or credentials.
            RouterAuditEvent.objects.create(router=router, action="hotspot.discovery_failed", details={"code": error.code, "actor_id": request.user.pk})
            return private_response({"detail": str(error), "code": error.code}, 503)
        with transaction.atomic():
            current = NASDevice.objects.select_for_update().get(pk=router.pk)
            if current.updated_at != router.updated_at or current.deployment_status == "deploying" or current.operations.filter(status__in=["pending", "running"]).exists():
                return private_response({"detail": "Router changed during discovery. Reload and try again."}, 409)
            if current.audit_events.filter(action="hotspot.inventory_discovered", created_at__gte=started).exists():
                return private_response({"detail": "A newer inventory is already available. Refresh setup."}, 409)
            RouterAuditEvent.objects.create(router=current, action="hotspot.inventory_discovered", details={"router_version": current.updated_at.isoformat(), "actor_id": request.user.pk, "inventory": inventory})
            return private_response(setup_result(current))


    @extend_schema(methods=["GET"], responses=SetupResultSerializer)
    @extend_schema(methods=["POST"], request=HotspotIntentSerializer, responses=SetupResultSerializer)
    @action(detail=True, methods=["get", "post"], url_path="hotspot-setup", throttle_classes=[ScopedRateThrottle], throttle_scope="router_hotspot_setup")
    def hotspot_setup(self, request, pk=None):
        router = self.get_object()  # Tenant scoped and manager-only through the parent viewset.
        if request.method == "GET":
            return private_response(setup_result(router))
        serializer = HotspotIntentSerializer(data=request.data, context={"router": router})
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            router = NASDevice.objects.select_for_update().get(pk=router.pk)
            if router.updated_at != serializer.validated_data["expected_updated_at"]:
                return private_response({"detail": "Router changed. Reload before reviewing configuration."}, 409)
            if router.deployment_status == "deploying" or router.operations.filter(status__in=["pending", "running"]).exists():
                return private_response({"detail": "Wait for the current provisioning operation to finish."}, 409)
            serializer = HotspotIntentSerializer(data=request.data, context={"router": router})
            serializer.is_valid(raise_exception=True)
            save_intent(router, serializer.validated_data, request.user.pk)
            return private_response(setup_result(router))

    @extend_schema(request=RevokeIntentSerializer, responses=SetupResultSerializer)
    @action(detail=True, methods=["post"], url_path="hotspot-setup/revoke", throttle_classes=[ScopedRateThrottle], throttle_scope="router_hotspot_setup")
    def revoke_hotspot_setup(self, request, pk=None):
        router = self.get_object()
        serializer = RevokeIntentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        intent_id = str(serializer.validated_data["intent_id"])
        with transaction.atomic():
            router = NASDevice.objects.select_for_update().get(pk=router.pk)
            if not router.audit_events.filter(pk=intent_id, action="hotspot.intent_created").exists():
                return private_response({"detail": "Configuration review not found."}, 404)
            RouterAuditEvent.objects.get_or_create(router=router, action="hotspot.intent_revoked", details={"intent_id": intent_id})
            return private_response(setup_result(router))
