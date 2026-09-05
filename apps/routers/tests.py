import hashlib
import hmac
import json
import time
import uuid
import struct
from io import StringIO
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.tenants.models import Tenant, TenantMembership
from .models import (
    NASDevice,
    ProvisioningAgentRequest,
    RouterAuditEvent,
    RouterOnboardingCheck,
)
from .state_machine import RouterStateMachine
from .secret_store import secret_store
from .provisioners import (
    WireGuardConfigurationError,
    WireGuardManager,
)
from .radius_client import (
    RadiusAuthClient,
    RadiusDisconnectClient,
    RadiusProtocolError,
    RadiusUnavailable,
)


User = get_user_model()
PUBLIC_KEY_A = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
PUBLIC_KEY_B = "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB="


class RouterApiAndStateTests(APITestCase):
    @override_settings(WG_MANAGED_SUBNET="10.8.0.0/24")
    def test_complete_frontend_form_fields_round_trip_without_secret_disclosure(self):
        self.client.force_authenticate(self.manager)
        payload = {
            "name": "Form router", "ip_address": "192.0.2.40",
            "nas_secret": "form-nas-secret", "location": "First floor",
            "is_active": False, "wireguard_ip": "10.8.0.40",
            "wireguard_public_key": PUBLIC_KEY_A, "wireguard_port": 51821,
            "routeros_username": "operator", "routeros_password_encrypted": "form-password",
        }
        response = self.client.post(reverse("router-list"), payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        record = NASDevice.objects.get(pk=response.data["id"])
        self.assertEqual(record.tenant, self.tenant_a)
        for field in ("name", "ip_address", "location", "is_active", "wireguard_ip", "wireguard_public_key", "wireguard_port", "routeros_username"):
            self.assertEqual(response.data[field], payload[field])
        self.assertNotIn("nas_secret", response.data)
        self.assertNotIn("routeros_password_encrypted", response.data)
        self.assertEqual(secret_store.decrypt(record.nas_secret), "form-nas-secret")
        self.assertEqual(secret_store.decrypt(record.routeros_password_encrypted), "form-password")
        original_secret = record.nas_secret
        original_password = record.routeros_password_encrypted
        detail = reverse("router-detail", args=[record.pk])
        updated = self.client.patch(detail, {"name": "Edited router", "wireguard_ip": None, "wireguard_public_key": "", "location": "", "is_active": True}, format="json")
        self.assertEqual(updated.status_code, status.HTTP_200_OK, updated.data)
        record.refresh_from_db()
        self.assertEqual(record.nas_secret, original_secret)
        self.assertEqual(record.routeros_password_encrypted, original_password)
        self.assertIsNone(record.wireguard_ip)
        self.assertEqual(record.wireguard_public_key, "")
        self.assertTrue(record.is_active)
        cleared = self.client.patch(detail, {"routeros_password_encrypted": ""}, format="json")
        self.assertEqual(cleared.status_code, status.HTTP_400_BAD_REQUEST)
        cleared = self.client.post(detail + "replace-secrets/", {"routeros_password_encrypted": "", "current_password": "StrongPass-4821", "expected_updated_at": record.updated_at.isoformat()}, format="json")
        self.assertEqual(cleared.status_code, status.HTTP_200_OK)
        record.refresh_from_db()
        self.assertEqual(record.routeros_password_encrypted, "")

    def setUp(self):
        cache.clear()
        self.tenant_a = Tenant.objects.create(name="Tenant A", slug="tenant-a")
        self.tenant_b = Tenant.objects.create(name="Tenant B", slug="tenant-b")
        self.manager = User.objects.create_user(
            username="manager", email="manager@example.com", password="StrongPass-4821"
        )
        self.staff = User.objects.create_user(
            username="staff", email="staff@example.com", password="StrongPass-4821"
        )
        TenantMembership.objects.create(user=self.manager, tenant=self.tenant_a, role="manager")
        TenantMembership.objects.create(user=self.staff, tenant=self.tenant_a, role="staff")
        self.router_a = NASDevice.objects.create(
            tenant=self.tenant_a,
            name="Router A",
            ip_address="10.0.0.1",
            nas_secret="nas-secret-a",
        )
        self.router_b = NASDevice.objects.create(
            tenant=self.tenant_b,
            name="Router B",
            ip_address="10.0.0.2",
            nas_secret="nas-secret-b",
        )

    def test_router_list_is_tenant_scoped_and_hides_secrets(self):
        self.client.force_authenticate(self.staff)

        response = self.client.get(reverse("router-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in response.data["results"]], [str(self.router_a.id)])
        self.assertNotIn("nas_secret", response.data["results"][0])
        self.assertNotIn("routeros_password_encrypted", response.data["results"][0])

    def test_staff_cannot_create_router(self):
        self.client.force_authenticate(self.staff)

        response = self.client.post(
            reverse("router-list"),
            {"name": "Forbidden", "ip_address": "10.0.0.3", "nas_secret": "secret"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_manager_created_router_encrypts_credentials_at_rest(self):
        self.client.force_authenticate(self.manager)

        response = self.client.post(
            reverse("router-list"),
            {
                "name": "Encrypted Router",
                "ip_address": "10.0.0.3",
                "nas_secret": "plain-nas-secret",
                "routeros_password_encrypted": "plain-router-password",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        router = NASDevice.objects.get(pk=response.data["id"])
        self.assertTrue(router.nas_secret.startswith("enc:v1:"))
        self.assertTrue(router.routeros_password_encrypted.startswith("enc:v1:"))
        self.assertEqual(secret_store.decrypt(router.nas_secret), "plain-nas-secret")
        self.assertEqual(
            secret_store.decrypt(router.routeros_password_encrypted),
            "plain-router-password",
        )
        self.assertNotIn("nas_secret", response.data)
        self.assertNotIn("routeros_password_encrypted", response.data)

    def test_manager_cannot_retrieve_other_tenant_router(self):
        self.client.force_authenticate(self.manager)

        response = self.client.get(reverse("router-detail", args=[self.router_b.id]))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_transition_creates_audit_and_rejects_stale_transition(self):
        stale = NASDevice.objects.get(pk=self.router_a.pk)

        correlation_id = RouterStateMachine.transition(self.router_a, "reviewed")

        self.assertTrue(
            RouterAuditEvent.objects.filter(
                router=self.router_a,
                correlation_id=correlation_id,
                from_state="pending",
                to_state="reviewed",
            ).exists()
        )
        with self.assertRaisesRegex(ValueError, "reviewed -> reviewed"):
            RouterStateMachine.transition(stale, "reviewed")
        self.assertEqual(RouterAuditEvent.objects.filter(router=self.router_a).count(), 1)

    @patch("apps.routers.views.RadiusAuthClient.authenticate", return_value=True)
    def test_radius_test_records_acceptance_without_credentials(self, authenticate):
        self.client.force_authenticate(self.manager)

        response = self.client.post(
            reverse("router-test", args=[self.router_a.id]),
            {"username": "probe-user", "password": "probe-password"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"passed": True})
        authenticate.assert_called_once_with(
            username="probe-user",
            password="probe-password",
            shared_secret="nas-secret-a",
            nas_ip="10.0.0.1",
        )
        check = RouterOnboardingCheck.objects.get(
            router=self.router_a, check_type="radius_auth"
        )
        self.assertTrue(check.passed)
        self.assertNotIn("username", check.details)
        self.assertNotIn("password", check.details)

    @patch(
        "apps.routers.views.RadiusAuthClient.authenticate",
        side_effect=RadiusUnavailable("timeout"),
    )
    def test_radius_test_returns_retryable_failure_without_exception_details(self, authenticate):
        self.client.force_authenticate(self.manager)

        response = self.client.post(
            reverse("router-test", args=[self.router_a.id]),
            {"username": "probe-user", "password": "probe-password"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data, {"error": "RADIUS authentication service unavailable."})
        self.assertNotIn("timeout", str(response.data))

    @patch("apps.routers.views.RadiusAuthClient.authenticate", return_value=False)
    def test_radius_test_is_rate_limited(self, authenticate):
        self.client.force_authenticate(self.manager)
        responses = [
            self.client.post(
                reverse("router-test", args=[self.router_a.id]),
                {"username": "probe-user", "password": "probe-password"},
                format="json",
            )
            for _ in range(11)
        ]

        self.assertTrue(all(response.status_code == 200 for response in responses[:10]))
        self.assertEqual(responses[10].status_code, status.HTTP_429_TOO_MANY_REQUESTS)


@override_settings(
    ROUTER_PROVISIONING_AGENT_KEYS=["abcdefgh-super-secret-key"],
    WG_VPS_HOST="test-vps",
    WG_VPS_SSH_KEY="test-key",
)
class ProvisioningEndpointTests(APITestCase):
    api_key = "abcdefgh-super-secret-key"

    def setUp(self):
        cache.clear()
        tenant = Tenant.objects.create(name="Tenant A", slug="tenant-a")
        self.router = NASDevice.objects.create(
            tenant=tenant,
            name="Router A",
            ip_address="10.0.0.1",
            nas_secret="nas-secret",
            wireguard_public_key=PUBLIC_KEY_B,
        )

    def payload(self, **overrides):
        data = {
            "request_id": str(uuid.uuid4()),
            "action": "provision_wireguard_peer",
            "router_id": str(self.router.id),
            "wireguard_ip": "10.100.100.2",
            "public_key": PUBLIC_KEY_A,
        }
        data.update(overrides)
        return data

    def post_signed(self, payload, api_key=None, timestamp=None, signature=None):
        raw = json.dumps(payload).encode()
        timestamp = timestamp or str(int(time.time()))
        key = api_key or self.api_key
        signature = signature or hmac.new(
            key.encode(), f"{timestamp}.{raw.decode()}".encode(), hashlib.sha256
        ).hexdigest()
        return self.client.post(
            reverse("provisioning-agent"),
            data=raw,
            content_type="application/json",
            HTTP_X_PROVISIONING_TIMESTAMP=timestamp,
            HTTP_X_PROVISIONING_KEY_ID=key[:8],
            HTTP_X_PROVISIONING_SIGNATURE=signature,
        )

    @patch("apps.routers.provisioning_views.WireGuardManager.create_peer")
    def test_valid_request_executes_once_and_records_replay_id(self, create_peer):
        payload = self.payload()

        first = self.post_signed(payload)
        second = self.post_signed(payload)

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_409_CONFLICT)
        create_peer.assert_called_once_with(public_key=PUBLIC_KEY_A, allowed_ip="10.100.100.2")
        self.router.refresh_from_db()
        self.assertEqual(self.router.wireguard_public_key, PUBLIC_KEY_A)
        self.assertEqual(str(self.router.wireguard_ip), "10.100.100.2")
        self.assertEqual(self.router.deployment_status, "deployed")
        self.assertTrue(
            ProvisioningAgentRequest.objects.filter(request_id=payload["request_id"]).exists()
        )
        self.assertTrue(
            RouterOnboardingCheck.objects.filter(
                router=self.router, check_type="wireguard_peer", passed=True
            ).exists()
        )
        self.assertTrue(
            RouterAuditEvent.objects.filter(
                router=self.router, action="provision_wireguard_peer"
            ).exists()
        )

    def test_expired_timestamp_and_invalid_signature_are_rejected(self):
        expired = self.post_signed(self.payload(), timestamp=str(int(time.time()) - 301))
        invalid = self.post_signed(self.payload(), signature="invalid")

        self.assertEqual(expired.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(invalid.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(ProvisioningAgentRequest.objects.exists())

    def test_source_outside_agent_allowlist_is_rejected_before_processing(self):
        payload = self.payload()
        raw = json.dumps(payload).encode()
        timestamp = str(int(time.time()))
        signature = hmac.new(
            self.api_key.encode(),
            f"{timestamp}.{raw.decode()}".encode(),
            hashlib.sha256,
        ).hexdigest()
        forbidden = self.client.post(
            reverse("provisioning-agent"),
            data=raw,
            content_type="application/json",
            REMOTE_ADDR="198.51.100.20",
            HTTP_X_PROVISIONING_TIMESTAMP=timestamp,
            HTTP_X_PROVISIONING_KEY_ID=self.api_key[:8],
            HTTP_X_PROVISIONING_SIGNATURE=signature,
        )

        self.assertEqual(forbidden.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(
            ProvisioningAgentRequest.objects.filter(request_id=payload["request_id"]).exists()
        )

    def test_request_id_and_action_fields_are_required(self):
        missing_id = self.payload()
        missing_id.pop("request_id")
        missing_key = self.payload()
        missing_key.pop("public_key")

        first = self.post_signed(missing_id)
        second = self.post_signed(missing_key)

        self.assertEqual(first.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(ProvisioningAgentRequest.objects.exists())

    @patch(
        "apps.routers.provisioning_views.WireGuardManager.create_peer",
        side_effect=OSError("vps unavailable"),
    )
    def test_external_failure_releases_request_for_safe_retry(self, create_peer):
        payload = self.payload()

        response = self.post_signed(payload)

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertFalse(
            ProvisioningAgentRequest.objects.filter(request_id=payload["request_id"]).exists()
        )
        self.router.refresh_from_db()
        self.assertEqual(self.router.deployment_status, "failed")

    def test_peer_ip_or_key_cannot_be_assigned_to_two_routers(self):
        NASDevice.objects.create(
            tenant=self.router.tenant,
            name="Existing Peer",
            ip_address="10.0.0.5",
            nas_secret="secret",
            wireguard_ip="10.100.100.9",
            wireguard_public_key=PUBLIC_KEY_A,
        )

        response = self.post_signed(self.payload(public_key=PUBLIC_KEY_A))

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertFalse(ProvisioningAgentRequest.objects.exists())

    def test_rate_limit_rejects_request_above_boundary(self):
        cache.set("provisioning_rate_abcdefgh", 120, 60)

        response = self.post_signed(self.payload())

        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertFalse(ProvisioningAgentRequest.objects.exists())

    def test_rejects_invalid_key_and_ip_outside_managed_subnet(self):
        invalid_key = self.post_signed(self.payload(public_key="not-a-wireguard-key"))
        outside_ip = self.post_signed(self.payload(wireguard_ip="10.200.0.2"))

        self.assertEqual(invalid_key.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(outside_ip.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(ProvisioningAgentRequest.objects.exists())


class WireGuardManagerTests(APITestCase):
    def manager(self):
        return WireGuardManager(
            "ops@vpn.example.com",
            "C:/keys/wireguard_ed25519",
            known_hosts="C:/keys/known_hosts",
            interface="wg0",
            managed_subnet="10.100.100.0/24",
        )

    @patch("apps.routers.provisioners.subprocess.run")
    def test_create_peer_executes_argument_safe_command_and_persists(self, run):
        run.return_value = Mock(returncode=0, stdout="", stderr="")

        result = self.manager().create_peer(PUBLIC_KEY_A, "10.100.100.2")

        self.assertTrue(result)
        self.assertEqual(run.call_count, 2)
        peer_command = run.call_args_list[0].args[0]
        save_command = run.call_args_list[1].args[0]
        self.assertEqual(peer_command[-9:], [
            "ops@vpn.example.com", "sudo", "--", "wg", "set", "wg0",
            "peer", PUBLIC_KEY_A, "allowed-ips", "10.100.100.2/32",
        ][-9:])
        self.assertEqual(save_command[-6:], [
            "ops@vpn.example.com", "sudo", "--", "wg-quick", "save", "wg0"
        ])
        self.assertNotIn("shell", run.call_args_list[0].kwargs)

    @patch("apps.routers.provisioners.subprocess.run")
    def test_invalid_peer_input_is_rejected_before_ssh(self, run):
        manager = self.manager()

        with self.assertRaises(WireGuardConfigurationError):
            manager.create_peer("; rm -rf /", "10.100.100.2")
        with self.assertRaises(WireGuardConfigurationError):
            manager.create_peer(PUBLIC_KEY_A, "192.168.1.2")

        run.assert_not_called()

    @patch("apps.routers.provisioners.subprocess.run")
    def test_list_peers_parses_wireguard_dump(self, run):
        run.return_value = Mock(
            returncode=0,
            stderr="",
            stdout=(
                "private\tpublic\t51820\toff\n"
                f"{PUBLIC_KEY_A}\t(none)\t198.51.100.10:51820\t10.100.100.2/32"
                "\t1700000000\t1024\t2048\t25\n"
            ),
        )

        peers = self.manager().list_peers()

        self.assertEqual(peers[0]["public_key"], PUBLIC_KEY_A)
        self.assertEqual(peers[0]["allowed_ips"], ["10.100.100.2/32"])
        self.assertEqual(peers[0]["transfer_rx"], 1024)


class RouterSecretBackfillTests(APITestCase):
    def setUp(self):
        tenant = Tenant.objects.create(name="Tenant A", slug="tenant-a")
        self.router = NASDevice.objects.create(
            tenant=tenant,
            name="Legacy Router",
            ip_address="10.0.0.1",
            nas_secret="legacy-nas-secret",
            routeros_password_encrypted="legacy-router-password",
        )

    def test_command_is_dry_run_by_default_and_apply_is_rerunnable(self):
        dry_output = StringIO()
        call_command("encrypt_router_secrets", stdout=dry_output)
        self.router.refresh_from_db()

        self.assertEqual(self.router.nas_secret, "legacy-nas-secret")
        self.assertIn("Would encrypt credentials for 1 router(s).", dry_output.getvalue())

        apply_output = StringIO()
        call_command("encrypt_router_secrets", "--apply", stdout=apply_output)
        self.router.refresh_from_db()
        self.assertTrue(self.router.nas_secret.startswith("enc:v1:"))
        self.assertTrue(self.router.routeros_password_encrypted.startswith("enc:v1:"))
        self.assertEqual(secret_store.decrypt(self.router.nas_secret), "legacy-nas-secret")
        self.assertEqual(
            secret_store.decrypt(self.router.routeros_password_encrypted),
            "legacy-router-password",
        )

        second_output = StringIO()
        call_command("encrypt_router_secrets", "--apply", stdout=second_output)
        self.assertIn("Encrypted credentials for 0 router(s).", second_output.getvalue())


class RadiusAuthClientTests(APITestCase):
    class FakeSocket:
        def __init__(self, secret, response_code=2, valid_authenticator=True):
            self.secret = secret.encode()
            self.response_code = response_code
            self.valid_authenticator = valid_authenticator
            self.sent = None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def settimeout(self, timeout):
            self.timeout = timeout

        def sendto(self, packet, destination):
            self.sent = packet
            self.destination = destination

        def recvfrom(self, size):
            identifier = self.sent[1]
            header = struct.pack("!BBH", self.response_code, identifier, 20)
            authenticator = hashlib.md5(
                header + self.sent[4:20] + self.secret
            ).digest()
            if not self.valid_authenticator:
                authenticator = b"x" * 16
            return header + authenticator, ("127.0.0.1", 1812)

    @patch("apps.routers.radius_client.socket.socket")
    def test_access_accept_is_authenticated_and_password_is_obscured(self, socket_factory):
        fake_socket = self.FakeSocket("shared-secret")
        socket_factory.return_value = fake_socket
        client = RadiusAuthClient("127.0.0.1", timeout=2)

        accepted = client.authenticate(
            "probe-user", "probe-password", "shared-secret", "10.0.0.1"
        )

        self.assertTrue(accepted)
        self.assertNotIn(b"probe-password", fake_socket.sent)
        self.assertEqual(fake_socket.destination, ("127.0.0.1", 1812))
        self.assertEqual(fake_socket.timeout, 2.0)

    @patch("apps.routers.radius_client.socket.socket")
    def test_access_reject_is_a_valid_negative_result(self, socket_factory):
        socket_factory.return_value = self.FakeSocket("shared-secret", response_code=3)

        accepted = RadiusAuthClient("127.0.0.1").authenticate(
            "probe-user", "probe-password", "shared-secret", "10.0.0.1"
        )

        self.assertFalse(accepted)

    @patch("apps.routers.radius_client.socket.socket")
    def test_forged_response_authenticator_is_rejected(self, socket_factory):
        socket_factory.return_value = self.FakeSocket(
            "shared-secret", valid_authenticator=False
        )

        with self.assertRaises(RadiusProtocolError):
            RadiusAuthClient("127.0.0.1").authenticate(
                "probe-user", "probe-password", "shared-secret", "10.0.0.1"
            )

    @patch("apps.routers.radius_client.socket.socket")
    def test_disconnect_ack_is_authenticated(self, socket_factory):
        fake_socket = self.FakeSocket("shared-secret", response_code=41)
        socket_factory.return_value = fake_socket

        acknowledged = RadiusDisconnectClient("10.0.0.1").disconnect(
            session_id="session-42",
            shared_secret="shared-secret",
            nas_port_id="ether2",
            calling_station_id="AA-BB-CC-DD-EE-FF",
        )

        self.assertTrue(acknowledged)
        self.assertEqual(fake_socket.sent[0], 40)
        self.assertEqual(fake_socket.destination, ("10.0.0.1", 3799))
        self.assertNotIn(b"shared-secret", fake_socket.sent)

    @patch("apps.routers.radius_client.socket.socket")
    def test_disconnect_nak_is_valid_negative_result(self, socket_factory):
        socket_factory.return_value = self.FakeSocket(
            "shared-secret", response_code=42
        )

        acknowledged = RadiusDisconnectClient("10.0.0.1").disconnect(
            session_id="session-42",
            shared_secret="shared-secret",
        )

        self.assertFalse(acknowledged)
