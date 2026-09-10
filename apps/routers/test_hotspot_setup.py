from copy import deepcopy
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.tenants.models import Tenant, TenantMembership
from .models import NASDevice, RouterAuditEvent, RouterOnboardingCheck


class HotspotSetupTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.tenant = Tenant.objects.create(name="Setup tenant", slug="setup-tenant")
        self.other = Tenant.objects.create(name="Other tenant", slug="other-setup")
        User = get_user_model()
        self.manager = User.objects.create_user(username="setup-manager", email="setup-manager@example.com", password="test-password")
        self.staff = User.objects.create_user(username="setup-staff", email="setup-staff@example.com", password="test-password")
        TenantMembership.objects.create(user=self.manager, tenant=self.tenant, role="manager")
        TenantMembership.objects.create(user=self.staff, tenant=self.tenant, role="staff")
        self.router = NASDevice.objects.create(name="Lab router", tenant=self.tenant, ip_address="192.0.2.1", nas_secret="NEVER-DISCLOSE-THIS")
        self.url = f"/api/v1/routers/{self.router.pk}/hotspot-setup/"
        self.client.force_authenticate(self.manager)
        self.payload = {"expected_updated_at": self.router.updated_at.isoformat(), "model":"Lab model", "routeros_version":"7.20.1", "service":"hotspot", "mode":"fresh", "bridge":"yr-hotspot", "hotspot_name":"yr-hotspot", "profile_name":"yr-profile", "gateway":"10.40.0.1/24", "radius_server":"10.8.0.1", "inventory_confirmed":True, "interfaces":[{"name":"ether1", "kind":"ethernet", "role":"wan", "bridge":""}, {"name":"ether2", "kind":"ethernet", "role":"management", "bridge":""}, {"name":"wifi1", "kind":"wireless", "role":"client", "bridge":""}]}

    def test_persisted_deterministic_non_executable_review_and_no_secrets(self):
        first = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(first.status_code, 200, first.data)
        second = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(first.data["intent"]["id"], second.data["intent"]["id"])
        self.assertEqual(RouterAuditEvent.objects.filter(action="hotspot.intent_created").count(), 1)
        preview = first.data["intent"]["script_preview"]
        self.assertTrue(preview.startswith(':error "REVIEW ONLY'))
        self.assertTrue(all(line.startswith('#') for line in preview.splitlines()[1:]))
        self.assertNotIn("NEVER-DISCLOSE-THIS", str(first.data))
        self.assertFalse(first.data["ready"])
        self.assertFalse(first.data["execution_enabled"])
        self.assertEqual(first["Cache-Control"], "no-store")
        self.assertEqual(self.client.get(self.url).data["intent"]["id"], first.data["intent"]["id"])

    def test_tenant_isolation(self):
        other_router = NASDevice.objects.create(name="Other", tenant=self.other, ip_address="192.0.2.2", nas_secret="hidden")
        url = f"/api/v1/routers/{other_router.pk}/hotspot-setup/"
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, self.payload, format="json").status_code, 404)

    def test_staff_denied_for_read_write_and_revoke(self):
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, self.payload, format="json").status_code, 403)
        self.assertEqual(self.client.post(self.url+'revoke/', {}, format="json").status_code, 403)

    def test_rejects_unsafe_or_unsupported_input(self):
        for patch in [{"bridge": 'x"; /system reset-configuration'}, {"model":"x\n:execute"}, {"service":"pppoe"}, {"routeros_version":"6.49"}, {"gateway":"10.40.0.0/24"}, {"gateway":"127.0.0.1/24"}, {"inventory_confirmed":False}, {"nas_secret":"should-not-be-accepted"}]:
            with self.subTest(patch=patch):
                response = self.client.post(self.url, {**self.payload, **patch}, format="json")
                self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(RouterAuditEvent.objects.exists())

    def test_protects_uplinks_and_existing_bridge_membership(self):
        for index, changes in [(0,{"role":"unused"}), (1,{"role":"unused"}), (0,{"bridge":"yr-hotspot"}), (2,{"bridge":"existing-bridge"}), (2,{"name":"ether1"})]:
            payload = deepcopy(self.payload)
            payload["interfaces"][index].update(changes)
            self.assertEqual(self.client.post(self.url, payload, format="json").status_code, 400)

    def test_existing_mode_requires_matching_client_bridge(self):
        payload = deepcopy(self.payload)
        payload["mode"] = "existing"
        self.assertEqual(self.client.post(self.url, payload, format="json").status_code, 400)
        payload["interfaces"][2]["bridge"] = "yr-hotspot"
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotIn('/interface bridge port add', response.data["intent"]["script_preview"])

    def test_stale_router_and_busy_operation_reject_new_review(self):
        payload = {**self.payload, "expected_updated_at": (timezone.now()-timedelta(days=1)).isoformat()}
        self.assertEqual(self.client.post(self.url, payload, format="json").status_code, 409)
        NASDevice.objects.filter(pk=self.router.pk).update(deployment_status="deploying")
        self.assertEqual(self.client.post(self.url, self.payload, format="json").status_code, 409)

    def test_revocation_is_idempotent_and_preview_is_removed(self):
        result = self.client.post(self.url, self.payload, format="json").data
        for _ in range(2):
            response = self.client.post(self.url+'revoke/', {"intent_id":result["intent"]["id"]}, format="json")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["intent"]["state"], "revoked")
            self.assertIsNone(response.data["intent"]["script_preview"])
        self.assertEqual(RouterAuditEvent.objects.filter(action="hotspot.intent_revoked").count(), 1)

    def test_expiry_and_router_edit_invalidate_preview(self):
        result = self.client.post(self.url, self.payload, format="json").data
        RouterAuditEvent.objects.filter(pk=result["intent"]["id"]).update(created_at=timezone.now()-timedelta(hours=2))
        self.assertEqual(self.client.get(self.url).data["intent"]["state"], "expired")
        RouterAuditEvent.objects.filter(pk=result["intent"]["id"]).update(created_at=timezone.now())
        NASDevice.objects.filter(pk=self.router.pk).update(updated_at=timezone.now())
        result = self.client.get(self.url).data
        self.assertEqual(result["intent"]["state"], "stale")
        self.assertIsNone(result["intent"]["script_preview"])

    def test_old_or_failed_checks_never_report_ready(self):
        self.client.post(self.url, self.payload, format="json")
        for kind in ['wireguard_peer','radius_auth','radius_acct']:
            RouterOnboardingCheck.objects.create(router=self.router, check_type=kind, passed=True)
        result = self.client.get(self.url).data
        self.assertTrue(all(row["passed"] for row in result["evidence"]))
        self.assertFalse(result["ready"])
        RouterOnboardingCheck.objects.filter(router=self.router).update(checked_at=timezone.now()-timedelta(hours=1))
        self.assertTrue(all(not row["passed"] for row in self.client.get(self.url).data["evidence"]))


    def test_router_profile_is_stored_per_device_and_seeds_setup(self):
        from .serializers import NASDeviceSerializer
        serializer = NASDeviceSerializer(self.router, data={"model":"RB5009UG", "routeros_version":"7.20.1"}, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        response = self.client.get(self.url)
        self.assertEqual(response.data["device_profile"], {"model":"RB5009UG", "routeros_version":"7.20.1"})
        self.assertEqual(response.data["compatibility"]["status"], "discovery_required")
        serializer = NASDeviceSerializer(self.router, data={"routeros_version":"6.49.18"}, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        self.assertEqual(self.client.get(self.url).data["compatibility"]["status"], "unsupported")
        self.assertFalse(self.client.get(self.url).data["execution_enabled"])

    def test_invalid_hardware_profile_is_rejected_and_old_clients_can_omit_it(self):
        from .serializers import NASDeviceSerializer
        self.assertEqual(NASDeviceSerializer(self.router).data["model"], "")
        for payload in ({"model": 'router; :execute'}, {"routeros_version":"latest"}, {"routeros_version":"7.20\n/system reset-configuration"}):
            serializer = NASDeviceSerializer(self.router, data=payload, partial=True)
            self.assertFalse(serializer.is_valid())
