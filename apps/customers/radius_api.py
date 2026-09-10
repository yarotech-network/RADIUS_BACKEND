import hmac
import math
from django.conf import settings
from django.contrib.auth.hashers import check_password
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.parsers import FormParser, JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.routers.selectors import tenant_radius_addresses
from .models import PPPoEService


class RadiusDecisionSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=50)
    password = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)
    packet_src_ip = serializers.IPAddressField()
    service_type = serializers.ChoiceField(choices=["Framed-User", "Framed", "2"])
    framed_protocol = serializers.ChoiceField(choices=["PPP", "1"])
    nas_port_type = serializers.ChoiceField(choices=["Ethernet", "15"])


class PPPoERadiusDecision(APIView):
    authentication_classes = []
    permission_classes = []
    parser_classes = [FormParser, JSONParser]
    throttle_classes = []  # Private endpoint; dedicated token is checked before password hashing.

    @extend_schema(request=RadiusDecisionSerializer, responses={200:dict,403:dict,503:dict})
    def post(self, request):
        token = settings.PPPOE_RADIUS_TOKEN
        if len(token) < 32:
            return Response({"detail":"PPPoE authentication is not configured."},status=503)
        supplied = request.headers.get("X-Radius-Token", "")
        if len(supplied)>512 or not hmac.compare_digest(supplied.encode(), token.encode()):
            return Response({"detail":"Access denied."},status=403)
        payload = RadiusDecisionSerializer(data=request.data)
        if not payload.is_valid():
            return Response({"detail":"Access denied."},status=403)
        data = payload.validated_data
        service = PPPoEService.objects.select_related("tenant", "customer", "router").filter(username=data["username"]).first()
        if service is None or not check_password(data["password"], service.password_hash):
            return Response({"detail":"Access denied."},status=403)
        now = timezone.now()
        source = data["packet_src_ip"]
        valid = (not service.suspended and service.expires_at > now and service.tenant.is_active
                 and not service.customer.archived_at and service.customer.tenant_id == service.tenant_id
                 and service.router.tenant_id == service.tenant_id and service.router.is_active
                 and service.router.onboarding_state == "active" and source == str(service.router.radius_ip)
                 and source in tenant_radius_addresses(service.tenant))
        remaining = math.floor((service.expires_at-now).total_seconds())
        if not valid or remaining < 1:
            return Response({"detail":"Access denied."},status=403)
        attributes = {"reply:Service-Type":"Framed-User", "reply:Framed-Protocol":"PPP",
                      "reply:Mikrotik-Rate-Limit":service.rate_limit,
                      "reply:Session-Timeout":min(3600,remaining), "reply:Acct-Interim-Interval":60}
        response = Response({name:{"value":[value],"op":":=","do_xlat":False} for name,value in attributes.items()})
        response["Cache-Control"] = "no-store"
        return response
