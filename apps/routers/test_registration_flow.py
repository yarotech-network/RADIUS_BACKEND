from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import override_settings
from rest_framework.test import APITestCase
from apps.tenants.models import Tenant, TenantMembership
from apps.subscriptions.test_support import grant_test_subscription
from .models import NASDevice, RouterRegistration, RouterOperation
from .secret_store import secret_store
from .operations import run_one_router_operation


@override_settings(WG_MANAGED_SUBNET='10.200.0.0/24', RADIUS_SERVER_WG_IP='10.200.0.1',
                   WG_VPS_ENDPOINT='vpn.example.net', WG_VPS_PUBLIC_KEY='AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=',
                   ROUTER_RADIUS_AUTH_PORT=18120, ROUTER_RADIUS_ACCT_PORT=18130,
                   ROUTER_SELF_SERVICE_PROVISIONING_ENABLED=False)
class RegistrationFlowTests(APITestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with connection.cursor() as cursor:
            cursor.execute('CREATE TABLE IF NOT EXISTS nas (nasname text, shortname text, type text, secret text, description text)')

    def setUp(self):
        self.tenant = Tenant.objects.create(name='Test workspace', slug='registration-workspace')
        grant_test_subscription(self.tenant)
        self.user = get_user_model().objects.create_user(username='registration-owner', email='owner@example.com')
        TenantMembership.objects.create(user=self.user, tenant=self.tenant, role='owner')
        self.client.force_authenticate(self.user)
        self.payload = dict(name='Branch router', hotspot_interface='bridge-lan', gateway_cidr='192.168.50.1/24', network_reviewed=True)

    def create(self, **changes):
        return self.client.post('/api/v1/routers/register/', {**self.payload, **changes}, format='json')

    def test_automatic_identity_and_legacy_script_without_external_calls(self):
        response = self.create()
        self.assertEqual(response.status_code, 201, response.data)
        router = NASDevice.objects.get(pk=response.data['id'])
        item = router.registration
        self.assertEqual(router.wireguard_ip, '10.200.0.3')
        self.assertEqual(router.onboarding_state, 'approved')
        self.assertEqual(item.error_code, 'server_provisioning_disabled')
        self.assertEqual(item.setup['dhcp_range'], '192.168.50.2-192.168.50.254')
        self.assertTrue(router.nas_secret.startswith('enc:v1:'))
        script = secret_store.decrypt(item.script_encrypted)
        self.assertIn('authentication-port=18120', script)
        self.assertIn('accounting-port=18130', script)
        self.assertIn('bridge-lan', script)
        self.assertNotIn('10.100.100.1', script)
        self.assertNotIn(secret_store.decrypt(router.nas_secret), str(response.data))
        self.assertNotIn(item.private_key_encrypted, str(response.data))
        self.assertFalse(RouterOperation.objects.exists())
        self.assertEqual(self.client.get(f'/api/v1/routers/{router.pk}/setup-script/').status_code, 409)

    def test_duplicate_post_is_replayed_without_new_router(self):
        first = self.client.post('/api/v1/routers/register/', self.payload, format='json', HTTP_IDEMPOTENCY_KEY='router-registration-unique-01')
        second = self.client.post('/api/v1/routers/register/', self.payload, format='json', HTTP_IDEMPOTENCY_KEY='router-registration-unique-01')
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(first.data, second.data)
        self.assertEqual(NASDevice.objects.count(), 1)

    def test_rejects_unreviewed_network_and_manual_credentials(self):
        for changes in ({'network_reviewed': False}, {'nas_secret': 'not-allowed'},
                        {'gateway_cidr': '10.200.0.1/24'}, {'hotspot_interface': 'bridge; /system reset'},
                        {'nat_mode': 'interface', 'wan_interface': 'bridge-lan'},
                        {'dhcp_range_mode': 'custom', 'dhcp_range': '192.168.50.1-192.168.50.5'}):
            with self.subTest(changes=changes):
                self.assertEqual(self.create(**changes).status_code, 400)
        self.assertFalse(NASDevice.objects.exists())

    def test_existing_hotspot_requires_profile(self):
        self.assertEqual(self.create(complete_hotspot_setup=False).status_code, 400)
        response = self.create(complete_hotspot_setup=False, hotspot_profile='existing-profile')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(RouterRegistration.objects.get().setup, {})

    def test_foreign_tenant_cannot_read_script_or_retry(self):
        response = self.create()
        router = NASDevice.objects.get(pk=response.data['id'])
        other = Tenant.objects.create(name='Other', slug='other-registration')
        grant_test_subscription(other)
        user = get_user_model().objects.create_user(username='other-owner', email='other@example.com')
        TenantMembership.objects.create(user=user, tenant=other, role='owner')
        self.client.force_authenticate(user)
        self.assertEqual(self.client.get(f'/api/v1/routers/{router.pk}/setup-script/').status_code, 404)
        self.assertEqual(self.client.post(f'/api/v1/routers/{router.pk}/setup-script/retry/', {}, format='json').status_code, 404)

    @override_settings(ROUTER_SELF_SERVICE_PROVISIONING_ENABLED=True)
    @patch('apps.routers.operations.WireGuardManager')
    def test_provision_then_release_script_never_claims_router_online(self, manager_class):
        manager_class.return_value.list_peers.return_value = []
        response = self.create()
        self.assertEqual(response.status_code, 201, response.data)
        router = NASDevice.objects.get(pk=response.data['id'])
        self.assertEqual(router.registration.status, 'preparing')
        run_one_router_operation()
        router.refresh_from_db()
        self.assertEqual(router.onboarding_state, 'waiting_for_vpn')
        result = self.client.get(f'/api/v1/routers/{router.pk}/setup-script/')
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(result['Cache-Control'], 'no-store')
        self.assertIn('/import file-name=', result.data['import_command'])

    @override_settings(ROUTER_SELF_SERVICE_PROVISIONING_ENABLED=True)
    @patch('apps.routers.operations.WireGuardManager')
    def test_failed_provisioning_retry_preserves_identity(self, manager_class):
        manager_class.return_value.list_peers.side_effect = RuntimeError('private diagnostic')
        response = self.create()
        router = NASDevice.objects.get(pk=response.data['id'])
        initial = (router.wireguard_ip, router.wireguard_public_key, router.nas_secret)
        run_one_router_operation()
        retry = self.client.post(f'/api/v1/routers/{router.pk}/setup-script/retry/', {}, format='json')
        self.assertEqual(retry.status_code, 200, retry.data)
        router.refresh_from_db()
        self.assertEqual(initial, (router.wireguard_ip, router.wireguard_public_key, router.nas_secret))
        self.assertEqual(RouterOperation.objects.filter(status='pending').count(), 1)
        self.assertNotIn('private diagnostic', str(retry.data))

    def test_duplicate_nas_identifier_rejected_without_partial_nas(self):
        self.assertEqual(self.create(nas_identifier='unique-router').status_code, 201)
        self.assertEqual(self.create(nas_identifier='unique-router').status_code, 400)
        self.assertEqual(NASDevice.objects.count(), 1)

    def test_allocator_respects_existing_radius_clients(self):
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO nas (nasname, shortname, type, secret, description) VALUES (%s,%s,%s,%s,%s)",
                           ['10.200.0.3', 'reserved', 'other', 'fixture-secret', 'Other client'])
        response = self.create()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['wireguard_ip'], '10.200.0.4')

    @override_settings(WG_VPS_PUBLIC_KEY='')
    def test_missing_server_settings_retains_one_recoverable_router(self):
        response = self.create()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['registration']['error_code'], 'server_configuration_required')
        self.assertFalse(RouterOperation.objects.exists())

    @override_settings(ROUTER_SELF_SERVICE_PROVISIONING_ENABLED=True)
    @patch('apps.routers.operations.WireGuardManager')
    def test_peer_address_conflict_never_overwrites_existing_peer(self, manager_class):
        manager_class.return_value.list_peers.return_value = [{'public_key': 'another-peer', 'allowed_ips': ['10.200.0.0/24']}]
        response = self.create()
        run_one_router_operation()
        manager_class.return_value.create_peer.assert_not_called()
        item = RouterRegistration.objects.get(router_id=response.data['id'])
        self.assertEqual(item.status, 'needs_attention')

    def test_direct_identity_edit_is_rejected(self):
        response = self.create()
        result = self.client.patch(f"/api/v1/routers/{response.data['id']}/", {'ip_address': '10.200.0.30'}, format='json')
        self.assertEqual(result.status_code, 400)
        result = self.client.post(f"/api/v1/routers/{response.data['id']}/provisioning/", {'action': 'provision'}, format='json')
        self.assertEqual(result.status_code, 409)
