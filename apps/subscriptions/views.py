from django.db import transaction
from django.db.models.deletion import ProtectedError
from rest_framework.exceptions import APIException
from apps.core.api import audit
from .entitlements import snapshot_plan
from .models import SubscriptionPeriod
from apps.payments.callbacks import payment_callback_url
from apps.core.api import tenant_for
import secrets
from apps.core.commands import idempotent

from rest_framework import viewsets, generics, permissions, status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import ScopedRateThrottle

from apps.core.permissions import IsTenantOwner, IsPlatformAdmin
from apps.payments.services import get_paystack_service
from .models import SubscriptionPlan, TenantSubscription
from .models import SubscriptionPayment
from .serializers import (
    BusinessPlanSerializer,
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
        with transaction.atomic():
            plan = SubscriptionPlan.objects.select_for_update().get(pk=plan.pk)
            if not plan.is_active:
                from rest_framework.exceptions import ValidationError
                raise ValidationError({"plan_id": "This plan is no longer available."})
            payment = SubscriptionPayment.objects.create(
                tenant=tenant, plan=plan, reference=reference, amount=plan.price,
                plan_terms=snapshot_plan(plan),
            )

        try:
            result = get_paystack_service().initialize_transaction(
                email=request.user.email,
                amount=plan.price,
                reference=reference,
                callback_url=payment_callback_url("subscription"),
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


class SubscriptionPaymentVerifyView(SubscriptionPaymentStatusView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "subscription_verify"
    http_method_names = ["post", "options"]

    def post(self, request, *args, **kwargs):
        from .services import (
            verify_subscription_payment,
            SubscriptionVerificationUnavailable,
            SubscriptionVerificationMismatch,
        )
        payment = self.get_object()
        try:
            payment = verify_subscription_payment(payment)
        except SubscriptionVerificationUnavailable:
            return Response({"detail": "Paystack verification is temporarily unavailable. Retry verification; do not pay again."}, status=503)
        except SubscriptionVerificationMismatch:
            return Response({"detail": "Payment details could not be matched. Contact support before making another payment."}, status=409)
        return Response(self.get_serializer(payment).data)


class PlanConflict(APIException):
    status_code = 409
    default_detail = "The plan changed. Refresh and try again."


class BusinessPlanViewSet(viewsets.ModelViewSet):
    permission_classes = [IsPlatformAdmin]
    serializer_class = BusinessPlanSerializer
    queryset = SubscriptionPlan.objects.all().order_by("price", "id")
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]

    @idempotent
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.validated_data.pop("expected_version", None)
        plan = serializer.save()
        audit(request, "business_plan.created", plan)
        return Response(serializer.data, status=201)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        plan = self.get_queryset().select_for_update().get(pk=self.get_object().pk)
        serializer = self.get_serializer(plan, data=request.data, partial=kwargs.get("partial", False))
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data.pop("expected_version") != plan.version:
            raise PlanConflict()
        # Freeze legacy/manual rows created since the migration before changing catalogue terms.
        terms = snapshot_plan(plan)
        for payment in plan.payments.filter(plan_terms__isnull=True).iterator():
            payment.plan_terms = {**terms, "price": payment.amount}
            payment.save(update_fields=["plan_terms"])
        for subscription in plan.subscriptions.select_related("tenant"):
            from apps.tenants.models import Tenant
            Tenant.objects.select_for_update().get(pk=subscription.tenant_id)
            if not SubscriptionPeriod.objects.filter(tenant_id=subscription.tenant_id).exists() and subscription.expires_at > subscription.started_at:
                SubscriptionPeriod.objects.create(tenant_id=subscription.tenant_id, plan=plan, starts_at=subscription.started_at, ends_at=subscription.expires_at, terms=terms)
        serializer.save(version=plan.version + 1)
        audit(request, "business_plan.updated", plan)
        return Response(serializer.data)

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        plan = self.get_queryset().select_for_update().get(pk=self.get_object().pk)
        if plan.payments.exists() or plan.subscriptions.exists() or plan.periods.exists():
            raise PlanConflict("This plan has payment or subscription history. Deactivate it instead.")
        audit(request, "business_plan.deleted", plan)
        try:
            plan.delete()
        except ProtectedError:
            raise PlanConflict("This plan is in use. Deactivate it instead.")
        return Response(status=204)
