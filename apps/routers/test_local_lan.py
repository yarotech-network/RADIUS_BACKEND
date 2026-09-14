from copy import deepcopy
from unittest.mock import patch

from django.test import override_settings
from rest_framework.test import APITestCase

from .discovery import DiscoveryError, destination, normalize
from .local_lan import approved_target, preparation_review
from .models import RouterAuditEvent
from .test_discovery import tables
from .test_hotspot_setup import HotspotSetupTests
from .test_hotspot_generator import assert_hotspot_server_ownership


@override_settings(ROUTER_DISCOVERY_HTTPS_PORT=443, ROUTER_LOCAL_LAN_TARGETS={})
class LocalLanTests(APITestCase):
    def setUp(self):
        HotspotSetupTests.setUp(self)
        self.router.ip_address = '192.168.88.1'
        self.router.model = 'Lab model'
        self.router.routeros_version = '7.20.1'
        self.router.save()
        self.target = {'address': '192.168.88.1', 'management_interface': 'ether2',
                       'wan_interface': 'ether1', 'preparation_interfaces': ['wifi1']}
        self.approvals = {str(self.router.pk): self.target}

    def snapshot(self, bridged=False):
        rows = tables()
        rows['addresses'] = [{'interface': 'bridgeLocal' if bridged else 'ether2', 'address': '192.168.88.1/24'}]
        if bridged:
            rows['interfaces'].append({'name': 'bridgeLocal', 'type': 'bridge', 'disabled': 'false'})
            rows['bridges'] = [{'name': 'bridgeLocal', 'vlan-filtering': 'false'}]
            rows['bridge_ports'] = [{'interface': name, 'bridge': 'bridgeLocal'} for name in ('ether1', 'ether2', 'wifi1')]
        result = normalize(rows, self.target['address'], self.target)
        result.update(connection_mode='local_lan', management_ip=self.target['address'], local_target=deepcopy(self.target))
        result['preparation'] = preparation_review(self.target, result)
        return result

    def test_exact_router_approval_and_private_ip_required(self):
        with self.assertRaises(DiscoveryError):
            destination(self.router, 'local_lan')
        with override_settings(ROUTER_LOCAL_LAN_TARGETS=self.approvals):
            self.assertEqual(destination(self.router, 'local_lan'), 'https://192.168.88.1:443/rest')
            with self.assertRaises(DiscoveryError):
                destination(self.router)  # No fake deployed VPN.
            self.router.ip_address = '192.168.88.2'
            self.assertIsNone(approved_target(self.router))
        for address in ['127.0.0.1', '169.254.169.254', '8.8.8.8', 'localhost', '::1']:
            self.router.ip_address = address
            with override_settings(ROUTER_LOCAL_LAN_TARGETS={str(self.router.pk): {**self.target, 'address': address}}):
                self.assertIsNone(approved_target(self.router))

    def test_protected_bridge_members_require_manual_preparation(self):
        observed = self.snapshot(bridged=True)
        for port in observed['interfaces']:
            self.assertIn('management', port['protected_reasons'])
        self.assertEqual(observed['preparation']['ports'][0]['state'], 'review_required')
        self.assertNotIn('/interface bridge port remove', str(observed['preparation']))

    def test_local_discovery_api_and_export_preserve_deployment_state(self):
        with override_settings(ROUTER_LOCAL_LAN_TARGETS=self.approvals):
            with patch('apps.routers.hotspot_api.collect', return_value=self.snapshot()) as collect:
                result = self.client.post(self.url+'discover/', {'expected_updated_at': self.router.updated_at.isoformat(), 'connection_mode':'local_lan'}, format='json')
            self.assertEqual(result.status_code, 200, result.data)
            self.assertEqual(collect.call_args.kwargs['connection_mode'], 'local_lan')
            self.assertTrue(result.data['local_lan_available'])
            self.assertNotIn('wireguard_peer', [e['check_type'] for e in result.data['evidence']])
            self.payload.update(expected_updated_at=self.router.updated_at.isoformat(), inventory_id=result.data['discovery']['id'])
            review = self.client.post(self.url, self.payload, format='json')
            self.assertEqual(review.status_code, 200, review.data)
            body = {'expected_updated_at': self.router.updated_at.isoformat(), 'intent_id':review.data['intent']['id'], 'lab_acknowledged':True, 'dns_server':'192.168.0.1'}
            response = self.client.post(self.url+'lab-package/', body, format='json')
            self.assertEqual(response.status_code, 200, response.data)
            stage = response.data['files']['stage.rsc']
            self.assertIn('192.168.88.1', stage)
            self.assertIn('Management Ethernet port changed', stage)
            self.assertNotIn('/interface bridge port remove', stage)
            self.router.refresh_from_db()
            self.assertEqual(self.router.deployment_status, 'not_deployed')
            self.assertFalse(review.data['ready'])
        # Revoking approval also revokes export of a previously valid review.
        self.assertEqual(self.client.post(self.url+'lab-package/', body, format='json').status_code, 400)

    def test_local_mode_keeps_tenant_permissions_and_rejects_arbitrary_endpoint(self):
        body = {'expected_updated_at': self.router.updated_at.isoformat(), 'connection_mode':'local_lan'}
        with patch('apps.routers.hotspot_api.collect') as collect:
            self.client.force_authenticate(self.staff)
            self.assertEqual(self.client.post(self.url+'discover/', body, format='json').status_code, 403)
            self.client.force_authenticate(self.manager)
            self.assertEqual(self.client.post(self.url+'discover/', {**body, 'url':'http://localhost'}, format='json').status_code, 400)
            collect.assert_not_called()

    def test_management_client_selection_and_bridged_wan_blocked(self):
        observed = self.snapshot(bridged=True)
        with override_settings(ROUTER_LOCAL_LAN_TARGETS=self.approvals):
            event = RouterAuditEvent.objects.create(router=self.router, action='hotspot.inventory_discovered', details={'router_version':self.router.updated_at.isoformat(), 'inventory':observed})
            result = self.client.get(self.url)
            self.assertEqual(result.data['compatibility']['status'], 'blocked')
            self.payload.update(expected_updated_at=self.router.updated_at.isoformat(), inventory_id=str(event.pk))
            self.payload['interfaces'][1]['role'] = 'client'
            self.assertEqual(self.client.post(self.url, self.payload, format='json').status_code, 400)


    def test_local_user_review_and_export_without_radius(self):
        with override_settings(ROUTER_LOCAL_LAN_TARGETS=self.approvals):
            event = RouterAuditEvent.objects.create(router=self.router, action='hotspot.inventory_discovered', details={'router_version':self.router.updated_at.isoformat(), 'inventory':self.snapshot()})
            self.payload.update(expected_updated_at=self.router.updated_at.isoformat(), inventory_id=str(event.pk), authentication_mode='local_user', radius_server='')
            review = self.client.post(self.url, self.payload, format='json')
            self.assertEqual(review.status_code, 200, review.data)
            self.assertIn('use-radius=no', review.data['intent']['script_preview'])
            body = {'expected_updated_at':self.router.updated_at.isoformat(), 'intent_id':review.data['intent']['id'], 'lab_acknowledged':True, 'dns_server':'192.168.0.1'}
            with patch('apps.routers.secret_store.secret_store.decrypt', side_effect=AssertionError('No saved credential reads')):
                first = self.client.post(self.url+'lab-package/', body, format='json')
                second = self.client.post(self.url+'lab-package/', body, format='json')
            self.assertEqual(first.status_code, 200, first.data)
            self.assertEqual(first.data, second.data)
            assert_hotspot_server_ownership(self, first.data)
            stage, activate, cleanup = [first.data['files'][name] for name in ('stage.rsc', 'activate.rsc', 'cleanup.rsc')]
            for script in (stage, activate, cleanup):
                self.assertIn('use-radius=no login-by=http-chap', script)
                self.assertNotIn('radius-accounting=', script)
                self.assertNotIn('radius-interim-update=', script)
                self.assertIn('session-timeout=15m idle-timeout="5m" rate-limit="2M/2M"', script)
                self.assertNotIn('idle-timeout=5m', script)
            self.assertNotIn('/radius ', stage)
            self.assertIn('password=[:rndstr length=24]', stage)
            self.assertIn('shared-users=1 session-timeout=15m', stage)
            self.assertIn('limit-uptime=1h limit-bytes-total=104857600 disabled=yes', stage)
            self.assertIn(f'server="{self.payload["hotspot_name"]}"', stage)
            self.assertIn('Management Ethernet port changed', activate)
            self.assertIn('Set a private test-user password', activate)
            self.assertIn('/ip hotspot active remove', cleanup)
            self.assertIn('/ip hotspot user remove', cleanup)
            self.assertIn('/ip hotspot user profile remove', cleanup)
            self.assertNotIn('reset-configuration', stage+activate+cleanup)
            self.assertFalse(first.data['hardware_validated'])
            self.assertFalse(self.client.get(self.url).data['ready'])
            self.router.refresh_from_db()
            self.assertEqual(self.router.deployment_status, 'not_deployed')
            for changes in ({'radius_server':'10.8.0.1'}, {'authentication_mode':'unknown'}, {'mode':'existing'}, {'inventory_id':None}):
                self.assertEqual(self.client.post(self.url, {**self.payload, **changes}, format='json').status_code, 400)
        self.assertEqual(self.client.post(self.url, self.payload, format='json').status_code, 400)

    def test_local_user_mode_cannot_use_a_vpn_snapshot(self):
        observed = self.snapshot()
        observed['connection_mode'] = 'wireguard'
        with override_settings(ROUTER_LOCAL_LAN_TARGETS=self.approvals):
            event = RouterAuditEvent.objects.create(router=self.router, action='hotspot.inventory_discovered', details={'router_version':self.router.updated_at.isoformat(), 'inventory':observed})
            self.payload.update(expected_updated_at=self.router.updated_at.isoformat(), inventory_id=str(event.pk), authentication_mode='local_user', radius_server='')
            self.assertEqual(self.client.post(self.url, self.payload, format='json').status_code, 400)

    def test_radius_default_still_requires_server(self):
        self.payload.update(expected_updated_at=self.router.updated_at.isoformat())
        self.payload.pop('radius_server')
        response = self.client.post(self.url, self.payload, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('radius_server', response.data)
