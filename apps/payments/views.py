from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from .services import get_paystack_service
from .serializers import InitializePaymentSerializer
from apps.vouchers.models import PaymentTransaction
from apps.vouchers.serializers import PaymentTransactionSerializer
import secrets
from apps.core.commands import idempotent


class InitializePaymentView(APIView):
    """Initialize a Paystack payment for voucher purchase."""

    permission_classes = [permissions.AllowAny]
    serializer_class = InitializePaymentSerializer

    @idempotent
    def post(self, request):
        serializer = InitializePaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        plan = serializer.validated_data["plan"]
        email = serializer.validated_data["email"]
        name = serializer.validated_data.get("name", "")
        phone = serializer.validated_data.get("phone", "")
        reference = f"yarotech-{secrets.token_hex(12)}"

        # Create pending transaction
        transaction = PaymentTransaction.objects.create(
            reference=reference,
            amount=plan.price,
            customer_email=email,
            customer_name=name,
            customer_phone=phone,
            plan=plan,
            tenant=plan.tenant,
        )

        # Initialize Paystack
        service = get_paystack_service(plan.tenant)
        try:
            result = service.initialize_transaction(
                email=email,
                amount=plan.price,
                reference=reference,
                metadata={
                    "transaction_id": transaction.id,
                    "plan_id": plan.id,
                    "custom_fields": [
                        {"display_name": "Plan", "variable_name": "plan", "value": plan.name},
                    ],
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


class PaymentCallbackView(APIView):
    """Handle Paystack return URL callback."""

    permission_classes = [permissions.AllowAny]
    serializer_class = PaymentTransactionSerializer

    def get(self, request):
        reference = request.query_params.get("reference")
        if not reference:
            return Response({"error": "Missing reference"}, status=400)

        try:
            transaction = PaymentTransaction.objects.get(reference=reference)
        except PaymentTransaction.DoesNotExist:
            return Response({"error": "Payment not found"}, status=404)
        return Response({
            "status": transaction.status,
            "reference": reference,
            "voucher": transaction.voucher.username if transaction.voucher else None,
        })
