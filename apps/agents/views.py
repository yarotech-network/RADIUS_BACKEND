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


class AgentProfileViewSet(viewsets.ModelViewSet):
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
    serializer_class = AgentWalletSerializer
    permission_classes = [IsAgent]

    @action(detail=False, methods=["get"])
    def balance(self, request):
        wallet, _ = AgentWallet.objects.get_or_create(
            agent=request.user.agent_profile
        )
        return Response(AgentWalletSerializer(wallet).data)

    @action(detail=False, methods=["post"])
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
        service = get_paystack_service(request.user.agent_profile.tenant)
        result = service.initialize_transaction(
            email=request.user.email,
            amount=payment.amount,
            reference=reference,
        )

        return Response({
            "authorization_url": result["data"]["authorization_url"],
            "reference": reference,
        })


class AgentVoucherGenerateView(viewsets.GenericViewSet):
    permission_classes = [IsAgent]
    serializer_class = AgentVoucherAllocationSerializer

    @action(detail=False, methods=["post"])
    def generate(self, request):
        plan_id = request.data.get("plan_id")
        quantity = request.data.get("quantity", 1)

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

    @action(detail=False, methods=["get"])
    def history(self, request):
        allocations = AgentVoucherAllocation.objects.filter(
            agent=request.user.agent_profile
        )
        return Response(AgentVoucherAllocationSerializer(allocations, many=True).data)

    @action(detail=False, methods=["get"])
    def stats(self, request):
        stats = AgentService.get_agent_stats(request.user.agent_profile)
        return Response(AgentStatsSerializer(stats).data)
