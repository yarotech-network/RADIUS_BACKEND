from apps.core.api import tenant_for
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
from apps.core.pagination import StandardResultsPagination
from apps.core.commands import idempotent
from rest_framework.exceptions import ValidationError
from django.core.exceptions import ValidationError as ModelValidationError
from apps.routers.selectors import tenant_radius_addresses

class DashboardStatsView(APIView):
    serializer_class = DashboardStatsSerializer
    def get(self, request):
        tenant = tenant_for(request)
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
            "currency": "NGN",
            "amount_unit": "kobo",
            "observed_at": timezone.now(),
            "pending_payments": PaymentTransaction.objects.filter(tenant=tenant, status="pending").count(),
            "paid_unfulfilled_payments": PaymentTransaction.objects.filter(tenant=tenant, verified_at__isnull=False, voucher__isnull=True).count(),
        })


class LiveUsersView(APIView):
    serializer_class = LiveUsersResponseSerializer
    def get(self, request):
        from apps.vouchers.models import Radacct
        from apps.routers.models import NASDevice

        tenant = tenant_for(request)
        router_ips = tenant_radius_addresses(tenant)
        sessions = Radacct.objects.filter(
            nasipaddress__in=router_ips,
            acctstoptime__isnull=True,
        ).order_by("-radacctid")
        if request.query_params.get("username"):
            sessions = sessions.filter(username__icontains=request.query_params["username"])
        if request.query_params.get("router"):
            try:
                router = NASDevice.objects.get(pk=request.query_params["router"], tenant=tenant)
            except (NASDevice.DoesNotExist, ValueError, ModelValidationError):
                raise ValidationError({"router": "Router not found."})
            sessions = sessions.filter(nasipaddress__in=[ip for ip in (router.ip_address, router.wireguard_ip) if ip])
        pagination = StandardResultsPagination()
        page = pagination.paginate_queryset(sessions, request, view=self)
        router_map = {}
        for router in NASDevice.objects.filter(tenant=tenant).only("id", "name", "ip_address", "wireguard_ip"):
            for address in (router.ip_address, router.wireguard_ip):
                if address:
                    router_map[str(address)] = router

        users = []
        for session in page:
            router = router_map.get(str(session.nasipaddress))
            users.append({
                "session_id": session.radacctid,
                "username": session.username,
                "ip_address": session.nasipaddress,
                "client_ip": None,
                "session_time": session.acctsessiontime,
                "bytes_in": session.acctinputoctets,
                "bytes_out": session.acctoutputoctets,
                "connected_at": session.acctstarttime,
                "router_id": str(router.pk) if router else None,
                "router_name": router.name if router else None,
            })

        return Response({"users": users, "count": pagination.page.paginator.count, "current_page": pagination.page.number, "total_pages": pagination.page.paginator.num_pages, "observed_at": timezone.now(), "source": "radius_accounting"})


class DisconnectSessionView(APIView):
    permission_classes = [IsTenantManager]
    serializer_class = DisconnectSessionResponseSerializer

    @idempotent
    def post(self, request, session_id):
        from apps.vouchers.models import Radacct
        from apps.vouchers.services import RadiusService

        tenant = tenant_for(request)
        router_ips = tenant_radius_addresses(tenant)
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
