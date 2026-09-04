from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import NotFound
from django.db.models import Count, Sum
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta
from .serializers import (
    DashboardStatsSerializer,
    DisconnectSessionResponseSerializer,
    LiveUsersResponseSerializer,
)
from apps.vouchers.models import Voucher, PaymentTransaction
from apps.routers.models import NASDevice, RouterAuditEvent
from apps.agents.models import AgentProfile
from apps.core.permissions import IsTenantManager
from apps.routers.radius_client import RadiusError
from apps.routers.secret_store import secret_store

class DashboardStatsView(APIView):
    serializer_class = DashboardStatsSerializer
    def get(self, request):
        tenant = request.user.membership.tenant
        today = timezone.now().date()
        month_start = today.replace(day=1)

        return Response({
            "total_vouchers": Voucher.objects.filter(tenant=tenant).count(),
            "active_vouchers": Voucher.objects.filter(tenant=tenant, status="active").count(),
            "total_revenue": PaymentTransaction.objects.filter(
                tenant=tenant, status="success"
            ).aggregate(total=Sum("amount"))["total"] or 0,
            "total_agents": AgentProfile.objects.filter(tenant=tenant).count(),
            "total_routers": NASDevice.objects.filter(tenant=tenant).count(),
            "active_routers": NASDevice.objects.filter(
                tenant=tenant, onboarding_state="active"
            ).count(),
        })


class LiveUsersView(APIView):
    serializer_class = LiveUsersResponseSerializer
    def get(self, request):
        from apps.vouchers.models import Radacct
        from apps.routers.models import NASDevice

        tenant = request.user.membership.tenant
        router_addresses = NASDevice.objects.filter(tenant=tenant).values_list(
            "ip_address", "wireguard_ip"
        )
        router_ips = {
            str(address)
            for addresses in router_addresses
            for address in addresses
            if address is not None
        }
        sessions = Radacct.objects.filter(
            nasipaddress__in=router_ips,
            acctstoptime__isnull=True,
        )

        users = []
        for session in sessions:
            users.append({
                "session_id": session.radacctid,
                "username": session.username,
                "ip_address": session.nasipaddress,
                "client_ip": None,
                "session_time": session.acctsessiontime,
                "bytes_in": session.acctinputoctets,
                "bytes_out": session.acctoutputoctets,
                "connected_at": session.acctstarttime,
            })

        return Response({"users": users, "count": len(users)})


class DisconnectSessionView(APIView):
    permission_classes = [IsTenantManager]
    serializer_class = DisconnectSessionResponseSerializer

    def post(self, request, session_id):
        from apps.vouchers.models import Radacct
        from apps.vouchers.services import RadiusService

        tenant = request.user.membership.tenant
        router_addresses = NASDevice.objects.filter(tenant=tenant).values_list(
            "ip_address", "wireguard_ip"
        )
        router_ips = {
            str(address)
            for addresses in router_addresses
            for address in addresses
            if address is not None
        }
        try:
            session = Radacct.objects.get(
                radacctid=session_id,
                nasipaddress__in=router_ips,
                acctstoptime__isnull=True,
            )
        except Radacct.DoesNotExist as exc:
            raise NotFound("Active session not found.") from exc

        router = NASDevice.objects.filter(
            tenant=tenant,
            is_active=True,
        ).filter(
            Q(ip_address=session.nasipaddress)
            | Q(wireguard_ip=session.nasipaddress)
        ).first()
        if router is None:
            raise NotFound("Active router not found.")

        try:
            acknowledged = RadiusService.disconnect_session(
                session_id=session.sessionid,
                nas_ip=str(session.nasipaddress),
                nas_port=session.nasportid,
                callingsession_id="",
                shared_secret=secret_store.decrypt(router.nas_secret),
            )
        except RadiusError:
            return Response(
                {"error": "RADIUS disconnect service unavailable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        RouterAuditEvent.objects.create(
            router=router,
            action="radius_disconnect_request",
            from_state=router.onboarding_state,
            to_state=router.onboarding_state,
            details={
                "radacct_id": session.radacctid,
                "acknowledged": acknowledged,
            },
        )
        return Response({"acknowledged": acknowledged})
