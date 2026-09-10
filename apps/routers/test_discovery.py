import json
import time
from copy import deepcopy
from datetime import timedelta
from unittest.mock import MagicMock, patch

import requests
from django.test import SimpleTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from .discovery import TABLES, DiscoveryError, destination, read_table, normalize, compatibility
from .models import NASDevice, RouterAuditEvent
from .test_hotspot_setup import HotspotSetupTests


def tables():
    result = {key: [] for key in TABLES}
    result.update({"resource": [{"board-name":"Lab model", "version":"7.20.1 (stable)", "architecture-name":"arm64"}],
                   "interfaces": [{"name":"ether1","type":"ether","disabled":"false"}, {"name":"ether2","type":"ether","disabled":"false"}, {"name":"wifi1","type":"wifi","disabled":"false"}],
                   "members": [{"list":"WAN","interface":"ether1"}],
                   "addresses": [{"interface":"ether2","address":"10.8.0.20/24"}],
                   "packages": [{"name":"routeros", "version":"7.20.1", "disabled":"false"}],
                   "device_mode": [{"hotspot":"true"}]})
    return result


def inventory():
    return normalize(tables(), "10.8.0.20")


class DiscoveryTransportTests(SimpleTestCase):
    def router(self):
        return NASDevice(wireguard_ip="10.8.0.20", deployment_status="deployed", is_active=True)

    @override_settings(WG_MANAGED_SUBNET="10.8.0.0/24", ROUTER_DISCOVERY_ALLOWED_CIDRS=["10.8.0.20/32"], ROUTER_DISCOVERY_HTTPS_PORT=443)
    def test_destination_is_assigned_approved_vpn_peer_only(self):
        router = self.router()
        self.assertEqual(destination(router), "https://10.8.0.20:443/rest")
        for address in ["127.0.0.1", "169.254.169.254", "10.8.0.21", "example.com", "::1", "10.9.0.20"]:
            router.wireguard_ip = address
            with self.subTest(address=address), self.assertRaises(DiscoveryError):
                destination(router)
        router.wireguard_ip = "10.8.0.20"
        router.deployment_status = "not_deployed"
        with self.assertRaisesRegex(DiscoveryError, "Provision"):
            destination(router)

    def response(self, body, status=200):
        response = MagicMock()
        response.status_code = status
        response.__enter__.return_value = response
        response.iter_content.return_value = [body]
        session = MagicMock()
        session.get.return_value = response
        return session

    def test_transport_allows_only_requested_properties_and_disables_redirects(self):
        session = self.response(json.dumps([{"name":"ether1", "password":"DO-NOT-COLLECT", "secret":"hidden"}]).encode())
        result = read_table(session, "https://10.8.0.20:443/rest/interface", "name", time.monotonic()+10)
        self.assertEqual(result, [{"name":"ether1"}])
        self.assertFalse(session.get.call_args.kwargs["allow_redirects"])
        self.assertTrue(session.get.call_args.kwargs["stream"])
        self.assertEqual(session.get.call_args.kwargs["params"], {".proplist":"name"})

    def test_redirect_auth_tls_and_invalid_responses_are_sanitized(self):
        for status, code in [(302,"redirect_refused"),(401,"authentication_failed"),(403,"authentication_failed"),(500,"service_unavailable")]:
            with self.subTest(status=status), self.assertRaises(DiscoveryError) as caught:
                read_table(self.response(b'private response', status), 'https://peer/rest/interface', 'name', time.monotonic()+10)
            self.assertEqual(caught.exception.code, code)
        for body in [b'x'*262145, b'not-json', json.dumps([{}]*513).encode(), b'[{"name":"bad\\nname"}]']:
            with self.assertRaises(DiscoveryError):
                read_table(self.response(body), 'https://peer/rest/interface', 'name', time.monotonic()+10)
        session = MagicMock()
        session.get.side_effect = requests.exceptions.SSLError('sensitive certificate/path details')
        with self.assertRaises(DiscoveryError) as caught:
            read_table(session, 'https://peer/rest/interface', 'name', time.monotonic()+10)
        self.assertEqual(caught.exception.code, 'tls_failed')
        self.assertNotIn('sensitive', str(caught.exception))

    def test_optional_menu_missing_and_expired_deadline(self):
        self.assertIsNone(read_table(self.response(b'',404), 'https://peer/rest/system/device-mode', 'hotspot', time.monotonic()+10, optional=True))
        session = MagicMock()
        with self.assertRaises(DiscoveryError):
            read_table(session, 'https://peer/rest/interface', 'name', time.monotonic()-1)
        session.get.assert_not_called()

    @override_settings(WG_MANAGED_SUBNET="10.8.0.0/24", ROUTER_DISCOVERY_ALLOWED_CIDRS=["10.8.0.20/32"], ROUTER_DISCOVERY_CA_BUNDLE="trusted-lab-ca.pem")
    def test_collector_uses_verified_tls_stored_credentials_and_no_environment_proxy(self):
        from .discovery import collect
        router = self.router()
        router.routeros_username = "reader"
        router.routeros_password_encrypted = "stored-ciphertext"
        with patch('apps.routers.discovery.secret_store.decrypt', return_value='private-password'), patch('apps.routers.discovery.requests.Session') as factory, patch('apps.routers.discovery.read_table', side_effect=list(tables().values())):
            session = factory.return_value.__enter__.return_value
            result = collect(router)
            self.assertFalse(session.trust_env)
            self.assertEqual(session.verify, "trusted-lab-ca.pem")
            self.assertEqual(session.auth, ("reader", "private-password"))
            self.assertNotIn('private-password', str(result))

    def test_protection_propagates_across_bridge_vlan_and_bond_dependencies(self):
        raw = tables()
        raw['interfaces'].extend([{"name":"uplink-bridge","type":"bridge"},{"name":"uplink-vlan","type":"vlan"},{"name":"uplink-bond","type":"bonding"}])
        raw['bridge_ports'] = [{"interface":"ether1","bridge":"uplink-bridge"}]
        raw['vlans'] = [{"name":"uplink-vlan","interface":"uplink-bridge"}]
        raw['bonds'] = [{"name":"uplink-bond","slaves":"uplink-vlan"}]
        result = normalize(raw, '10.8.0.20')
        for item in result['interfaces']:
            if item['name'].startswith('uplink') or item['name']=='ether1':
                self.assertIn('wan', item['protected_reasons'])
        self.assertEqual(next(p for p in result['interfaces'] if p['name']=='wifi1')['protected_reasons'], [])

    def test_compatibility_never_claims_execution_and_explains_blockers(self):
        router = self.router()
        router.model = 'Lab model'
        router.routeros_version = '7.20.1'
        observed = {**inventory(), 'state':'current'}
        result = compatibility(router, observed)
        self.assertEqual(result['status'], 'unverified')
        self.assertFalse(result['execution_enabled'])
        self.assertIsNone(result['generator'])
        observed.update(state='stale', hotspot_allowed=False, unavailable_sections=['packages'])
        router.model = 'Different model'
        result = compatibility(router, observed)
        self.assertEqual(result['status'], 'blocked')
        self.assertGreaterEqual(len(result['reasons']), 4)


class DiscoveryApiTests(APITestCase):
    def setUp(self):
        HotspotSetupTests.setUp(self)
        self.discovery_url = self.url + 'discover/'
        self.body = {'expected_updated_at': self.router.updated_at.isoformat()}

    def discover(self):
        with patch('apps.routers.hotspot_api.collect', return_value=inventory()):
            return self.client.post(self.discovery_url, self.body, format='json')

    def test_discovery_persists_observed_snapshot_without_modifying_router_or_ready_state(self):
        response = self.discover()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['discovery']['model'], 'Lab model')
        self.assertEqual(response.data['discovery']['source'], 'routeros_https')
        self.assertFalse(response.data['ready'])
        self.router.refresh_from_db()
        self.assertEqual(self.router.onboarding_state, 'pending')
        self.assertIsNone(self.router.last_seen_at)
        self.assertEqual(self.client.get(self.url).data['discovery']['id'], response.data['discovery']['id'])

    def test_staff_and_cross_tenant_requests_do_not_contact_router(self):
        other = NASDevice.objects.create(name='Other', tenant=self.other, ip_address='192.0.2.2', nas_secret='secret')
        with patch('apps.routers.hotspot_api.collect') as collect:
            response = self.client.post(f'/api/v1/routers/{other.pk}/hotspot-setup/discover/', self.body, format='json')
            self.assertEqual(response.status_code, 404)
            self.client.force_authenticate(self.staff)
            self.assertEqual(self.client.post(self.discovery_url, self.body, format='json').status_code, 403)
            collect.assert_not_called()

    def test_failure_preserves_previous_inventory_and_logs_only_error_code(self):
        original = self.discover().data['discovery']['id']
        with patch('apps.routers.hotspot_api.collect', side_effect=DiscoveryError('tls_failed')):
            response = self.client.post(self.discovery_url, self.body, format='json')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.client.get(self.url).data['discovery']['id'], original)
        event = RouterAuditEvent.objects.filter(action='hotspot.discovery_failed').get()
        self.assertEqual(set(event.details), {'code','actor_id'})

    def test_changed_router_during_collection_does_not_commit_snapshot(self):
        def changed(_router):
            NASDevice.objects.filter(pk=self.router.pk).update(updated_at=timezone.now())
            return inventory()
        with patch('apps.routers.hotspot_api.collect', side_effect=changed):
            self.assertEqual(self.client.post(self.discovery_url, self.body, format='json').status_code, 409)
        self.assertFalse(RouterAuditEvent.objects.filter(action='hotspot.inventory_discovered').exists())

    def test_out_of_order_discovery_cannot_replace_newer_result(self):
        def newer(_router):
            RouterAuditEvent.objects.create(router=self.router, action='hotspot.inventory_discovered', details={'router_version':self.router.updated_at.isoformat(),'inventory':inventory()})
            return inventory()
        with patch('apps.routers.hotspot_api.collect', side_effect=newer):
            self.assertEqual(self.client.post(self.discovery_url, self.body, format='json').status_code, 409)
        self.assertEqual(RouterAuditEvent.objects.filter(action='hotspot.inventory_discovered').count(), 1)

    def test_discovery_bound_reviews_cannot_change_protected_ports_or_invent_interfaces(self):
        observed = self.discover().data['discovery']
        payload = {**self.payload, 'inventory_id':observed['id']}
        result = self.client.post(self.url, payload, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(result.data['inventory_source'], 'routeros_https')
        self.assertEqual(result.data['intent']['expires_at'], RouterAuditEvent.objects.get(pk=observed['id']).created_at + timedelta(minutes=10))
        for changes in [{'name':'invented'}, {'role':'client'}]:
            bad = deepcopy(payload)
            bad['interfaces'][0].update(changes)
            self.assertEqual(self.client.post(self.url, bad, format='json').status_code, 400)
        RouterAuditEvent.objects.filter(pk=observed['id']).update(created_at=timezone.now()-timedelta(minutes=11))
        self.assertEqual(self.client.post(self.url, payload, format='json').status_code, 400)
        self.assertEqual(self.client.get(self.url).data['intent']['state'], 'stale')

    def test_discovery_rejects_arbitrary_destination_fields_and_busy_router(self):
        with patch('apps.routers.hotspot_api.collect') as collect:
            self.assertEqual(self.client.post(self.discovery_url, {**self.body,'url':'https://127.0.0.1/'}, format='json').status_code, 400)
            NASDevice.objects.filter(pk=self.router.pk).update(deployment_status='deploying')
            self.assertEqual(self.client.post(self.discovery_url, self.body, format='json').status_code, 409)
            collect.assert_not_called()
