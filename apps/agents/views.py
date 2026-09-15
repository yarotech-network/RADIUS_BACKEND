from rest_framework import generics
from apps.payments.callbacks import payment_callback_url
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
from .serializers import AgentPlanSerializer, AgentWalletTransactionSerializer
from .models import AgentWalletTransaction
from .serializers import FundingVerificationSerializer, FundingPolicySerializer
from rest_framework.throttling import ScopedRateThrottle


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
    throttle_scope = 'agent_funding_verify'
    queryset = AgentWallet.objects.none()
    serializer_class = AgentWalletSerializer
    permission_classes = [IsAgent]

    @extend_schema(responses=FundingPolicySerializer)
    @action(detail=False, methods=['get'])
    def policy(self, request):
        from apps.tenants.models import TenantSetting
        from .funding_terms import funding_policy
        setting = TenantSetting.objects.filter(tenant=request.user.agent_profile.tenant).first()
        return Response(FundingPolicySerializer(funding_policy(setting)).data)

    @extend_schema(request=FundingVerificationSerializer, responses=AgentFundingPaymentSerializer)
    @action(detail=False, methods=['post'], throttle_classes=[ScopedRateThrottle])
    def verify(self, request):
        from django.shortcuts import get_object_or_404
        from .funding import verify_wallet_funding, FundingVerificationUnavailable, FundingVerificationMismatch
        serializer = FundingVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = get_object_or_404(AgentWalletFundingPayment,
            wallet__agent=request.user.agent_profile, reference=serializer.validated_data['reference'])
        try:
            payment = verify_wallet_funding(payment)
        except FundingVerificationUnavailable:
            return Response({'detail': 'Payment verification is temporarily unavailable. Retry checking this reference before paying again.'}, status=503)
        except FundingVerificationMismatch:
            return Response({'detail': 'Payment details could not be matched. Contact your operator before paying again.'}, status=409)
        return Response(AgentFundingPaymentSerializer(payment).data)

    @extend_schema(responses=AgentWalletTransactionSerializer(many=True))
    @action(detail=False, methods=['get'])
    def transactions(self, request):
        query = AgentWalletTransaction.objects.filter(
            wallet__agent=request.user.agent_profile,
        ).order_by('-created_at', '-id')
        page = self.paginate_queryset(query)
        return self.get_paginated_response(AgentWalletTransactionSerializer(page, many=True).data)

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
        try:
            payment = AgentService.fund_wallet(
                agent=request.user.agent_profile,
                amount=serializer.validated_data['amount'],
                reference=reference,
                expected_total=serializer.validated_data.get('expected_total'),
            )
        except ValueError as exc:
            return Response({'error': str(exc)}, status=400)
        from .funding_terms import funding_total
        totals = {'amount': payment.amount, 'fee': funding_total(payment) - payment.amount, 'total_amount': funding_total(payment)}

        # Initialize Paystack
        from apps.payments.services import get_paystack_service
        try:
            service = get_paystack_service(request.user.agent_profile.tenant)
            result = service.initialize_transaction(
                email=request.user.email,
                amount=totals['total_amount'],
                reference=reference,
                callback_url=payment_callback_url("wallet"),
            )
            authorization_url = result["data"]["authorization_url"]
        except Exception:
            return Response({"error": "Payment provider unavailable", "reference": reference, **totals}, status=503)

        return Response({
            "authorization_url": authorization_url,
            "reference": reference,
            **totals,
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


class AgentPlansView(generics.ListAPIView):
    permission_classes = [IsAgent]
    serializer_class = AgentPlanSerializer

    def get_queryset(self):
        from apps.vouchers.models import InternetPlan
        if getattr(self, 'swagger_fake_view', False):
            return InternetPlan.objects.none()
        return InternetPlan.objects.filter(tenant=self.request.user.agent_profile.tenant,
            is_active=True, agent_enabled=True, archived_at__isnull=True,
            plan_type='voucher').order_by('price', 'id')
