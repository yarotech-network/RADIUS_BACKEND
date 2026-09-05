from django.db import transaction
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.core.api import tenant_for, audit
from apps.core.commands import idempotent
from apps.core.permissions import IsTenantManager
from .models import RouterOperation, NASDevice
from .serializers import NASDeviceSerializer
from .services import RouterService
from drf_spectacular.utils import extend_schema


class RouterOperationSerializer(serializers.ModelSerializer):
    class Meta:
        model = RouterOperation
        fields = ["id", "router", "action", "status", "attempts", "error_code", "created_at", "completed_at"]
        read_only_fields = fields


class ProvisionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["provision", "suspend"])


class ReplaceSecretsSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)
    nas_secret = serializers.CharField(max_length=255, required=False, write_only=True, trim_whitespace=False)
    routeros_password_encrypted = serializers.CharField(max_length=255, required=False, write_only=True, allow_blank=True, trim_whitespace=False)
    expected_updated_at = serializers.DateTimeField()


class HealthCheckSerializer(serializers.Serializer):
    check_type = serializers.CharField()
    passed = serializers.BooleanField()
    checked_at = serializers.DateTimeField()


class RouterHealthSerializer(serializers.Serializer):
    router = serializers.UUIDField()
    is_active = serializers.BooleanField()
    onboarding_state = serializers.CharField()
    deployment_status = serializers.CharField()
    last_seen_at = serializers.DateTimeField(allow_null=True)
    observed_at = serializers.DateTimeField()
    checks = HealthCheckSerializer(many=True)
    online = serializers.BooleanField(allow_null=True)
    telemetry_available = serializers.BooleanField()


class RouterOperationViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsTenantManager]
    serializer_class = RouterOperationSerializer
    filterset_fields = ["router", "status", "action"]
    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return RouterOperation.objects.none()
        return RouterOperation.objects.filter(router__tenant=tenant_for(self.request))


class RouterOperationActions:
    @extend_schema(request=ProvisionSerializer, responses={202: RouterOperationSerializer})
    @action(detail=True, methods=["post"], url_path="provisioning")
    @idempotent
    def provisioning(self, request, pk=None):
        serializer = ProvisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        router = self.get_object()
        with transaction.atomic():
            router = NASDevice.objects.select_for_update().get(pk=router.pk)
            if router.deployment_status == "deploying" or RouterOperation.objects.filter(router=router, status__in=["pending", "running"]).exists():
                return Response({"error": "A router operation is already pending."}, status=409)
            if not router.wireguard_public_key or (serializer.validated_data["action"] == "provision" and (not router.is_active or not router.wireguard_ip)):
                return Response({"error": "Active router and WireGuard configuration are required."}, status=400)
            operation = RouterOperation.objects.create(router=router, action=serializer.validated_data["action"], payload={"public_key": router.wireguard_public_key, "wireguard_ip": router.wireguard_ip})
            router.deployment_status = "deploying"
            router.save(update_fields=["deployment_status", "updated_at"])
            audit(request, "router.provisioning_requested", router, {"operation_id": str(operation.pk)})
        return Response(RouterOperationSerializer(operation).data, status=202)

    @extend_schema(request=ReplaceSecretsSerializer, responses=NASDeviceSerializer)
    @action(detail=True, methods=["post"], url_path="replace-secrets")
    @idempotent
    def replace_secrets(self, request, pk=None):
        serializer = ReplaceSecretsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        if not request.user.check_password(values.pop("current_password")):
            return Response({"error": "Current password is incorrect."}, status=400)
        expected = values.pop("expected_updated_at")
        if not values:
            return Response({"error": "At least one replacement secret is required."}, status=400)
        router = self.get_object()
        with transaction.atomic():
            router = NASDevice.objects.select_for_update().get(pk=router.pk)
            if router.updated_at != expected:
                return Response({"error": "Router changed; reload before replacing secrets."}, status=409)
            if router.deployment_status == "deploying" or router.operations.filter(status__in=["pending", "running"]).exists():
                return Response({"error": "Wait for the pending provisioning operation."}, status=409)
            update = NASDeviceSerializer(router, data=values, partial=True)
            update.is_valid(raise_exception=True)
            update.save()
            if "nas_secret" in values and router.deployment_status == "deployed":
                RouterService.register_nas_client(router)
            audit(request, "router.secrets_replaced", router, {"fields": list(values)})
        return Response(NASDeviceSerializer(router).data)

    @extend_schema(responses=RouterHealthSerializer)
    @action(detail=True, methods=["get"])
    def health(self, request, pk=None):
        router = self.get_object()
        checks = list(router.onboarding_checks.order_by("check_type").values("check_type", "passed", "checked_at"))
        return Response({"router": str(router.pk), "is_active": router.is_active, "onboarding_state": router.onboarding_state, "deployment_status": router.deployment_status, "last_seen_at": router.last_seen_at, "observed_at": timezone.now(), "checks": checks, "online": None, "telemetry_available": False})
