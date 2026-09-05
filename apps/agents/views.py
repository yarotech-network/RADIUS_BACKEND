from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import AgentProfile, AgentWallet, AgentVoucherAllocation
from .serializers import (
    AgentProfileSerializer, AgentWalletSerializer,
    AgentVoucherAllocationSerializer, AgentStatsSerializer,
    AgentWalletFundingSerializer,
)
from .services import AgentService
from apps.core.permissions import IsAgent
from apps.core.commands import idempotent
from apps.vouchers.serializers import VoucherGenerateSerializer
from .serializers import AgentFundingPaymentSerializer
from .models import AgentWalletFundingPayment
from drf_spectacular.utils import extend_schema
from .serializers import FundingCheckoutSerializer, AgentGeneratedVouchersSerializer
from .serializers import AgentVoucherGenerateSerializer


class AgentProfileViewSet(viewsets.ModelViewSet):
    http_method_names = ["get", "patch", "head", "options"]
    serializer_class = AgentProfileSerializer
    permission_classes = [IsAgent]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return AgentProfile.objects.none()
        return AgentProfile.objects.filter(user=self.request.user)

    @action(detail=False, methods=["get"])
    def me(self, request):
        profile = AgentProfile.objects.get(user=request.user)
        return Response(AgentProfileSerializer(profile).data)


class AgentWalletViewSet(viewsets.GenericViewSet):
    queryset = AgentWallet.objects.none()
    serializer_class = AgentWalletSerializer
    permission_classes = [IsAgent]

    @extend_schema(responses=AgentFundingPaymentSerializer(many=True))
    @action(detail=False, methods=["get"])
    def payments(self, request):
        query = AgentWalletFundingPayment.objects.filter(wallet__agent=request.user.agent_profile).order_by("-created_at", "-id")
        if request.query_params.get("status"):
            query = query.filter(status=request.query_params["status"])
        if request.query_params.get("reference"):
            query = query.filter(reference=request.query_params["reference"])
        page = self.paginate_queryset(query)
        return self.get_paginated_response(AgentFundingPaymentSerializer(page, many=True).data)

    @action(detail=False, methods=["get"])
    def balance(self, request):
        wallet, _ = AgentWallet.objects.get_or_create(
            agent=request.user.agent_profile
        )
        return Response(AgentWalletSerializer(wallet).data)

    @extend_schema(request=AgentWalletFundingSerializer, responses=FundingCheckoutSerializer)
    @action(detail=False, methods=["post"])
    @idempotent
    def fund(self, request):
        serializer = AgentWalletFundingSerializer(
            data=request.data,
            context={"agent": request.user.agent_profile},
        )
        serializer.is_valid(raise_exception=True)

        import secrets
        reference = f"agent-fund-{secrets.token_hex(12)}"
        payment = AgentService.fund_wallet(
            agent=request.user.agent_profile,
            amount=serializer.validated_data["amount"],
            reference=reference,
        )

        # Initialize Paystack
        from apps.payments.services import get_paystack_service
        try:
            service = get_paystack_service(request.user.agent_profile.tenant)
            result = service.initialize_transaction(
                email=request.user.email,
                amount=payment.amount,
                reference=reference,
            )
            authorization_url = result["data"]["authorization_url"]
        except Exception:
            return Response({"error": "Payment provider unavailable", "reference": reference}, status=503)

        return Response({
            "authorization_url": authorization_url,
            "reference": reference,
        })


class AgentVoucherGenerateView(viewsets.GenericViewSet):
    queryset = AgentVoucherAllocation.objects.none()
    permission_classes = [IsAgent]
    serializer_class = AgentVoucherAllocationSerializer

    @extend_schema(request=AgentVoucherGenerateSerializer, responses={201: AgentGeneratedVouchersSerializer})
    @action(detail=False, methods=["post"])
    @idempotent
    def generate(self, request):
        serializer = AgentVoucherGenerateSerializer(data=request.data, context={"tenant": request.user.agent_profile.tenant})
        serializer.is_valid(raise_exception=True)
        plan_id = serializer.validated_data["plan_id"]
        quantity = serializer.validated_data["quantity"]

        try:
            vouchers, allocations = AgentService.generate_voucher_from_wallet(
                agent=request.user.agent_profile,
                plan_id=plan_id,
                quantity=quantity,
            )
            return Response({
                "vouchers": AgentVoucherAllocationSerializer(allocations, many=True).data,
            }, status=status.HTTP_201_CREATED)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(responses=AgentVoucherAllocationSerializer(many=True))
    @action(detail=False, methods=["get"])
    def history(self, request):
        allocations = AgentVoucherAllocation.objects.filter(
            agent=request.user.agent_profile
        ).select_related("voucher", "voucher__plan").order_by("-created_at", "-id")
        if request.query_params.get("status"):
            allocations = allocations.filter(voucher__status=request.query_params["status"])
        page = self.paginate_queryset(allocations)
        return self.get_paginated_response(AgentVoucherAllocationSerializer(page, many=True).data)

    @extend_schema(responses=AgentStatsSerializer)
    @action(detail=False, methods=["get"])
    def stats(self, request):
        stats = AgentService.get_agent_stats(request.user.agent_profile)
        return Response(AgentStatsSerializer(stats).data)
