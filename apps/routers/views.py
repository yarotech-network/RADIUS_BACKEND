from django.conf import settings
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import serializers
from rest_framework.throttling import ScopedRateThrottle
from drf_spectacular.utils import extend_schema, inline_serializer
from .models import NASDevice, RouterAuditEvent, RouterOnboardingCheck
from .serializers import (
    NASDeviceSerializer, RouterAuditEventSerializer,
    RouterOnboardingCheckSerializer,
    RouterRadiusTestSerializer,
)
from .state_machine import RouterStateMachine
from apps.core.permissions import IsTenantManager
from .radius_client import RadiusAuthClient, RadiusError
from .secret_store import secret_store


class NASDeviceViewSet(viewsets.ModelViewSet):
    serializer_class = NASDeviceSerializer
    throttle_scope = None

    def get_serializer_class(self):
        if self.action == "test":
            return RouterRadiusTestSerializer
        return super().get_serializer_class()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return NASDevice.objects.none()
        return NASDevice.objects.filter(tenant=self.request.user.membership.tenant)

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [permissions.IsAuthenticated()]
        return [IsTenantManager()]

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.user.membership.tenant)

    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        router = self.get_object()
        to_state = request.data.get("to_state")
        try:
            correlation_id = RouterStateMachine.transition(
                router, to_state, action="manual_transition"
            )
            return Response({"correlation_id": str(correlation_id)})
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["get"])
    def audit(self, request, pk=None):
        router = self.get_object()
        events = RouterAuditEvent.objects.filter(router=router)
        return Response(RouterAuditEventSerializer(events, many=True).data)

    @action(detail=True, methods=["get"])
    def checks(self, request, pk=None):
        router = self.get_object()
        checks = RouterOnboardingCheck.objects.filter(router=router)
        return Response(RouterOnboardingCheckSerializer(checks, many=True).data)

    @extend_schema(
        request=RouterRadiusTestSerializer,
        responses={
            200: inline_serializer(
                name="RouterRadiusTestResult",
                fields={"passed": serializers.BooleanField()},
            ),
            503: inline_serializer(
                name="RouterRadiusUnavailable",
                fields={"error": serializers.CharField()},
            ),
        },
    )
    @action(
        detail=True,
        methods=["post"],
        throttle_classes=[ScopedRateThrottle],
        throttle_scope="router_radius_test",
    )
    def test(self, request, pk=None):
        router = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        client = RadiusAuthClient(
            settings.RADIUS_AUTH_HOST,
            settings.RADIUS_AUTH_PORT,
            settings.RADIUS_AUTH_TIMEOUT,
        )
        try:
            passed = client.authenticate(
                username=serializer.validated_data["username"],
                password=serializer.validated_data["password"],
                shared_secret=secret_store.decrypt(router.nas_secret),
                nas_ip=router.ip_address,
            )
        except RadiusError:
            RouterOnboardingCheck.objects.update_or_create(
                router=router,
                check_type="radius_auth",
                defaults={"passed": False, "details": {"outcome": "unavailable"}},
            )
            return Response(
                {"error": "RADIUS authentication service unavailable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        RouterOnboardingCheck.objects.update_or_create(
            router=router,
            check_type="radius_auth",
            defaults={
                "passed": passed,
                "details": {"outcome": "accepted" if passed else "rejected"},
            },
        )
        RouterAuditEvent.objects.create(
            router=router,
            action="radius_auth_test",
            from_state=router.onboarding_state,
            to_state=router.onboarding_state,
            details={"passed": passed},
        )
        return Response({"passed": passed})
