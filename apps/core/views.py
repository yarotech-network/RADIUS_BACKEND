from django.db.models import Sum
from rest_framework import viewsets, serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from apps.core.permissions import IsPlatformAdmin, IsTenantManager
from apps.core.api import tenant_for
from apps.core.models import AuditEvent
from apps.routers.models import NASDevice
from apps.routers.serializers import NASDeviceSerializer
from apps.vouchers.models import PaymentTransaction, Voucher
from apps.vouchers.serializers import PaymentTransactionSerializer
from apps.tenants.models import Tenant
from apps.agents.models import AgentProfile


class AuditSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEvent
        fields = ["id", "tenant", "actor", "action", "resource", "details", "created_at"]
        read_only_fields = fields


class AuditViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsTenantManager]
    serializer_class = AuditSerializer
    filterset_fields = ["action", "actor"]
    search_fields = ["resource"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return AuditEvent.objects.none()
        return AuditEvent.objects.filter(tenant=tenant_for(self.request))


class PlatformAuditViewSet(AuditViewSet):
    permission_classes = [IsPlatformAdmin]
    filterset_fields = ["tenant", "action", "actor"]
    def get_queryset(self):
        return AuditEvent.objects.all()


class PlatformRouterViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsPlatformAdmin]
    serializer_class = NASDeviceSerializer
    queryset = NASDevice.objects.select_related("tenant").order_by("-created_at", "id")
    filterset_fields = ["tenant", "is_active", "onboarding_state", "deployment_status"]
    search_fields = ["name", "ip_address", "location"]


class PlatformPaymentViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsPlatformAdmin]
    serializer_class = PaymentTransactionSerializer
    queryset = PaymentTransaction.objects.select_related("voucher").order_by("-created_at", "id")
    filterset_fields = ["tenant", "status", "plan"]
    search_fields = ["reference"]


class PlatformStatsSerializer(serializers.Serializer):
    tenants = serializers.IntegerField()
    active_tenants = serializers.IntegerField()
    routers = serializers.IntegerField()
    onboarded_routers = serializers.IntegerField()
    agents = serializers.IntegerField()
    vouchers = serializers.IntegerField()
    successful_payment_amount = serializers.IntegerField()
    pending_payments = serializers.IntegerField()
    currency = serializers.CharField()
    amount_unit = serializers.CharField()
    successful_wallet_funding_amount = serializers.IntegerField()
    successful_subscription_amount = serializers.IntegerField()


class PlatformStatsView(APIView):
    serializer_class = PlatformStatsSerializer
    permission_classes = [IsPlatformAdmin]
    def get(self, request):
        from apps.agents.models import AgentWalletFundingPayment
        from apps.subscriptions.models import SubscriptionPayment
        return Response({
            "tenants": Tenant.objects.count(),
            "active_tenants": Tenant.objects.filter(is_active=True).count(),
            "routers": NASDevice.objects.count(),
            "onboarded_routers": NASDevice.objects.filter(onboarding_state="active").count(),
            "agents": AgentProfile.objects.count(),
            "vouchers": Voucher.objects.count(),
            "successful_payment_amount": PaymentTransaction.objects.filter(status="success").aggregate(total=Sum("amount"))["total"] or 0,
            "pending_payments": PaymentTransaction.objects.filter(status="pending").count(),
            "currency": "NGN", "amount_unit": "kobo",
            "successful_wallet_funding_amount": AgentWalletFundingPayment.objects.filter(status="success").aggregate(total=Sum("amount"))["total"] or 0,
            "successful_subscription_amount": SubscriptionPayment.objects.filter(status="success").aggregate(total=Sum("amount"))["total"] or 0,
        })


from apps.agents.models import AgentWalletFundingPayment
from apps.agents.serializers import AgentFundingPaymentSerializer
from apps.subscriptions.models import SubscriptionPayment
from apps.subscriptions.serializers import SubscriptionPaymentSerializer


class PlatformWalletPaymentSerializer(AgentFundingPaymentSerializer):
    tenant_id = serializers.IntegerField(source="wallet.agent.tenant_id", read_only=True)
    agent_id = serializers.IntegerField(source="wallet.agent_id", read_only=True)
    class Meta(AgentFundingPaymentSerializer.Meta):
        fields = [*AgentFundingPaymentSerializer.Meta.fields, "tenant_id", "agent_id"]


class PlatformWalletPaymentViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsPlatformAdmin]
    serializer_class = PlatformWalletPaymentSerializer
    queryset = AgentWalletFundingPayment.objects.select_related("wallet__agent").order_by("-created_at", "-id")
    filterset_fields = ["status", "wallet__agent__tenant", "wallet__agent"]
    search_fields = ["reference"]


class PlatformSubscriptionPaymentSerializer(SubscriptionPaymentSerializer):
    class Meta(SubscriptionPaymentSerializer.Meta):
        fields = ["id", "tenant", *SubscriptionPaymentSerializer.Meta.fields]


class PlatformSubscriptionPaymentViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsPlatformAdmin]
    serializer_class = PlatformSubscriptionPaymentSerializer
    queryset = SubscriptionPayment.objects.order_by("-created_at", "-id")
    filterset_fields = ["tenant", "status", "plan"]
    search_fields = ["reference"]
