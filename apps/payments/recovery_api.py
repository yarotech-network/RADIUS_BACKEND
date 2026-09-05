from django.db import transaction
from django.db.models import OuterRef, Subquery
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.core.permissions import IsTenantManager
from apps.core.api import tenant_for, audit
from apps.core.commands import idempotent
from apps.vouchers.models import PaymentTransaction
from .models import PaymentDelivery
from .services import get_paystack_service
from .recovery import fulfill_verified_voucher
from drf_spectacular.utils import extend_schema


class RecoverySerializer(serializers.ModelSerializer):
    fulfillment_status = serializers.SerializerMethodField()
    delivery_status = serializers.SerializerMethodField()
    class Meta:
        model = PaymentTransaction
        fields = ["id", "reference", "amount", "status", "verified_at", "voucher", "fulfillment_status", "delivery_status"]
    def get_fulfillment_status(self, obj) -> str:
        return "fulfilled" if obj.voucher_id else ("paid_unfulfilled" if obj.verified_at else "unverified")
    def get_delivery_status(self, obj) -> str:
        if hasattr(obj, "latest_delivery_status"):
            return obj.latest_delivery_status or "not_requested"
        return obj.deliveries.values_list("status", flat=True).first() or "not_requested"


class PaymentDeliverySerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentDelivery
        fields = ["id", "payment", "status", "error_code", "created_at", "started_at", "completed_at"]
        read_only_fields = fields


class DeliveryRequestSerializer(serializers.Serializer):
    acknowledge_duplicate_risk = serializers.BooleanField(default=False)


class PaymentRecoveryViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsTenantManager]
    serializer_class = RecoverySerializer
    filterset_fields = ["status", "plan"]
    search_fields = ["reference"]
    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return PaymentTransaction.objects.none()
        latest = PaymentDelivery.objects.filter(payment_id=OuterRef("pk")).order_by("-created_at", "id").values("status")[:1]
        return PaymentTransaction.objects.filter(tenant=tenant_for(self.request)).annotate(latest_delivery_status=Subquery(latest)).order_by("-created_at", "id")

    @extend_schema(request=None, responses=RecoverySerializer)
    @action(detail=True, methods=["post"])
    @idempotent
    def retry(self, request, pk=None):
        payment = self.get_object()
        try:
            verified = get_paystack_service(payment.tenant).verify_transaction(payment.reference)["data"]
        except Exception:
            return Response({"error": "Payment verification unavailable."}, status=503)
        try:
            payment = fulfill_verified_voucher(payment, verified)
        except ValueError:
            return Response({"error": "Payment verification or plan validation failed."}, status=409)
        except Exception:
            return Response({"error": "Payment verified; fulfillment requires retry."}, status=503)
        audit(request, "payment.recovered", payment)
        return Response(self.get_serializer(payment).data)

    @extend_schema(request=DeliveryRequestSerializer, responses={202: PaymentDeliverySerializer})
    @action(detail=True, methods=["post"])
    @idempotent
    def deliver(self, request, pk=None):
        serializer = DeliveryRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = self.get_object()
        with transaction.atomic():
            payment = PaymentTransaction.objects.select_for_update().get(pk=payment.pk)
            if payment.status != "success" or not payment.voucher_id:
                return Response({"error": "Only fulfilled payments can be delivered."}, status=409)
            latest = payment.deliveries.first()
            if latest and latest.status in ("pending", "sending"):
                return Response(PaymentDeliverySerializer(latest).data, status=202)
            if latest and latest.status in ("accepted", "unknown") and not serializer.validated_data["acknowledge_duplicate_risk"]:
                return Response({"error": "Delivery may already have occurred. Explicitly acknowledge duplicate delivery risk to resend."}, status=409)
            delivery = PaymentDelivery.objects.create(payment=payment)
            audit(request, "payment.delivery_requested", payment, {"delivery_id": str(delivery.pk)})
        return Response(PaymentDeliverySerializer(delivery).data, status=202)


class PaymentDeliveryViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsTenantManager]
    serializer_class = PaymentDeliverySerializer
    filterset_fields = ["payment", "status"]
    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return PaymentDelivery.objects.none()
        return PaymentDelivery.objects.filter(payment__tenant=tenant_for(self.request))
