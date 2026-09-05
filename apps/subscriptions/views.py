from apps.core.api import tenant_for
import secrets
from apps.core.commands import idempotent

from rest_framework import viewsets, generics, permissions, status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsTenantOwner
from apps.payments.services import get_paystack_service
from .models import SubscriptionPlan, TenantSubscription
from .models import SubscriptionPayment
from .serializers import (
    SubscriptionCheckoutSerializer,
    SubscriptionPaymentSerializer,
    SubscriptionPlanSerializer,
    TenantSubscriptionSerializer,
)


class SubscriptionPlanViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = SubscriptionPlanSerializer
    queryset = SubscriptionPlan.objects.filter(is_active=True)
    permission_classes = [permissions.AllowAny]


class TenantSubscriptionView(generics.RetrieveAPIView):
    serializer_class = TenantSubscriptionSerializer

    def get_object(self):
        try:
            return TenantSubscription.objects.select_related("plan").get(
                tenant=tenant_for(self.request)
            )
        except TenantSubscription.DoesNotExist as exc:
            raise NotFound("Subscription not found.") from exc


class SubscriptionCheckoutView(APIView):
    permission_classes = [IsTenantOwner]
    serializer_class = SubscriptionCheckoutSerializer

    @idempotent
    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        plan = serializer.validated_data["plan"]
        tenant = tenant_for(request)
        reference = f"subscription-{secrets.token_hex(12)}"
        payment = SubscriptionPayment.objects.create(
            tenant=tenant,
            plan=plan,
            reference=reference,
            amount=plan.price,
        )

        try:
            result = get_paystack_service().initialize_transaction(
                email=request.user.email,
                amount=plan.price,
                reference=reference,
                metadata={
                    "payment_type": "tenant_subscription",
                    "tenant_id": tenant.pk,
                    "plan_id": plan.pk,
                },
            )
            authorization_url = result["data"]["authorization_url"]
        except Exception:
            return Response(
                {"error": "Payment provider unavailable", "reference": reference},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response({
            "authorization_url": authorization_url,
            "reference": reference,
        })


class SubscriptionPaymentStatusView(generics.RetrieveAPIView):
    permission_classes = [IsTenantOwner]
    serializer_class = SubscriptionPaymentSerializer
    lookup_field = "reference"

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return SubscriptionPayment.objects.none()
        return SubscriptionPayment.objects.filter(
            tenant=tenant_for(self.request)
        ).select_related("plan", "subscription")
