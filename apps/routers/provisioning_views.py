from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import Q
from .models import (
    NASDevice,
    ProvisioningAgentRequest,
    RouterAuditEvent,
    RouterOnboardingCheck,
)
from .provisioners import WireGuardManager
from .serializers import ProvisioningRequestSerializer
import hmac
import hashlib
import ipaddress
import time


def _client_is_allowed(remote_address, allowed_networks):
    try:
        client = ipaddress.ip_address(remote_address)
    except ValueError:
        return False
    for configured_network in allowed_networks:
        try:
            network = ipaddress.ip_network(configured_network, strict=False)
        except ValueError:
            continue
        if client.version == network.version and client in network:
            return True
    return False


class ProvisioningAgentEndpoint(APIView):
    """HMAC-authenticated provisioning endpoint."""

    permission_classes = [permissions.AllowAny]
    serializer_class = ProvisioningRequestSerializer

    def post(self, request):
        if not _client_is_allowed(
            request.META.get("REMOTE_ADDR", ""),
            settings.ROUTER_PROVISIONING_AGENT_ALLOWED_NETWORKS,
        ):
            return Response({"error": "Source network not allowed"}, status=403)

        # Authenticate via HMAC
        timestamp = request.headers.get("X-Provisioning-Timestamp", "")
        signature = request.headers.get("X-Provisioning-Signature", "")
        key_id = request.headers.get("X-Provisioning-Key-Id", "")

        # Verify timestamp freshness (5 minutes)
        try:
            ts = int(timestamp)
            if abs(time.time() - ts) > 300:
                return Response({"error": "Request expired"}, status=401)
        except ValueError:
            return Response({"error": "Invalid timestamp"}, status=401)

        # Find matching API key
        agent_keys = settings.ROUTER_PROVISIONING_AGENT_KEYS
        matching_key = None
        for key in agent_keys:
            if len(key_id) == 8 and hmac.compare_digest(key[:8], key_id):
                matching_key = key
                break

        if not matching_key:
            return Response({"error": "Invalid key"}, status=401)

        # Verify signature
        payload = request.body.decode()
        message = f"{timestamp}.{payload}"
        computed = hmac.new(matching_key.encode(), message.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, computed):
            return Response({"error": "Invalid signature"}, status=401)

        serializer = ProvisioningRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        request_id = data["request_id"]

        if ProvisioningAgentRequest.objects.filter(request_id=request_id).exists():
            return Response({"error": "Duplicate request"}, status=409)

        # Rate limiting
        cache_key = f"provisioning_rate_{key_id}"
        if cache.add(cache_key, 1, 60):
            count = 1
        else:
            try:
                count = cache.incr(cache_key)
            except ValueError:
                cache.set(cache_key, 1, 60)
                count = 1
        if count > 120:
            return Response({"error": "Rate limit exceeded"}, status=429)

        # Process action
        action = data["action"]
        router_id = data["router_id"]

        try:
            router = NASDevice.objects.get(id=router_id)
        except NASDevice.DoesNotExist:
            return Response({"error": "Router not found"}, status=404)

        request_record, created = ProvisioningAgentRequest.objects.get_or_create(
            request_id=request_id,
            defaults={
                "key_id": key_id,
                "action": action,
                "router": router,
                "payload": request.data,
            },
        )
        if not created:
            return Response({"error": "Duplicate request"}, status=409)

        if action == "provision_wireguard_peer":
            conflict = NASDevice.objects.exclude(pk=router.pk).filter(
                Q(wireguard_ip=data["wireguard_ip"])
                | Q(wireguard_public_key=data["public_key"])
            ).exists()
            if conflict:
                request_record.delete()
                return Response({"error": "WireGuard peer already assigned"}, status=409)

        try:
            with transaction.atomic():
                router = NASDevice.objects.select_for_update().get(pk=router.pk)
                if action == "provision_wireguard_peer":
                    router.wireguard_ip = data["wireguard_ip"]
                    router.wireguard_public_key = data["public_key"]
                elif not router.wireguard_public_key:
                    request_record.delete()
                    return Response({"error": "Router has no WireGuard peer"}, status=409)
                router.deployment_status = "deploying"
                router.save(update_fields=[
                    "wireguard_ip", "wireguard_public_key", "deployment_status", "updated_at"
                ])
        except IntegrityError:
            request_record.delete()
            return Response({"error": "WireGuard peer already assigned"}, status=409)

        # Dispatch action
        try:
            wg_manager = WireGuardManager(
                settings.WG_VPS_HOST,
                settings.WG_VPS_SSH_KEY,
                known_hosts=settings.WG_SSH_KNOWN_HOSTS,
                interface=settings.WG_INTERFACE,
                managed_subnet=settings.WG_MANAGED_SUBNET,
                use_sudo=settings.WG_SSH_USE_SUDO,
                save_config=settings.WG_SAVE_CONFIG,
            )
            if action == "provision_wireguard_peer":
                wg_manager.create_peer(
                    public_key=data["public_key"],
                    allowed_ip=data["wireguard_ip"],
                )
            else:
                wg_manager.remove_peer(public_key=router.wireguard_public_key)
        except Exception:
            NASDevice.objects.filter(pk=router.pk).update(deployment_status="failed")
            request_record.delete()
            return Response({"error": "Provisioning operation failed"}, status=503)

        with transaction.atomic():
            router = NASDevice.objects.select_for_update().get(pk=router.pk)
            deployed = action == "provision_wireguard_peer"
            router.deployment_status = "deployed" if deployed else "not_deployed"
            router.save(update_fields=["deployment_status", "updated_at"])
            RouterOnboardingCheck.objects.update_or_create(
                router=router,
                check_type="wireguard_peer",
                defaults={
                    "passed": deployed,
                    "details": {"request_id": str(request_id), "action": action},
                },
            )
            RouterAuditEvent.objects.create(
                router=router,
                action=action,
                from_state=router.onboarding_state,
                to_state=router.onboarding_state,
                details={"request_id": str(request_id)},
            )

        return Response({"status": "ok", "action": action})
