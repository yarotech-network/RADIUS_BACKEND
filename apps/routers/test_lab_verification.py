from datetime import timedelta
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from .discovery import DiscoveryError
from .lab_verification import TABLES, approved_wifi, collect_lab, evaluate, package_context
from .models import RouterAuditEvent
from .test_local_lan import LocalLanTests


class LabVerificationTests(APITestCase):
    def wifi_approval(self):
        return {str(self.router.pk): {'intent_id': str(self.event.pk), 'interfaces': ['wlan1']}}

    def test_wifi_addition_requires_exact_package_and_protects_existing_ports(self):
        context = package_context(self.router)
        with override_settings(ROUTER_LOCAL_LAN_WIFI_EXTENSIONS=self.wifi_approval()):
            self.assertEqual(approved_wifi(self.router, context), ['wlan1'])
        for names in [['ether2'], ['ether1'], ['wifi1'], ['wlan1', 'wlan1'], ['bad/name']]:
            entry = self.wifi_approval()
            entry[str(self.router.pk)]['interfaces'] = names
            with override_settings(ROUTER_LOCAL_LAN_WIFI_EXTENSIONS=entry):
                self.assertEqual(approved_wifi(self.router, context), [])
        entry = self.wifi_approval()
        entry[str(self.router.pk)]['intent_id'] = 'another-package'
        with override_settings(ROUTER_LOCAL_LAN_WIFI_EXTENSIONS=entry):
            self.assertEqual(approved_wifi(self.router, context), [])

    def test_wireless_binding_requires_radio_identity_and_exact_membership(self):
        rows = self.rows()
        rows['ports'].append({'interface': 'wlan1', 'bridge': 'yr-hotspot', 'disabled': 'false', 'comment': 'Yarotech WiFi lab extension'})
        rows['interfaces'] = [{'name': 'wlan1', 'type': 'wlan', 'disabled': 'false'}]
        context = package_context(self.router)
        self.assertFalse(all(c['passed'] for c in evaluate(rows, context)))
        self.assertTrue(all(c['passed'] for c in evaluate(rows, context, ['wlan1'])))
        for key, value in [('type', 'ether'), ('disabled', 'true'), ('name', 'wlan2')]:
            original = rows['interfaces'][0][key]
            rows['interfaces'][0][key] = value
            self.assertFalse(all(c['passed'] for c in evaluate(rows, context, ['wlan1'])))
            rows['interfaces'][0][key] = original
        rows['ports'][-1]['comment'] = 'unexpected-owner'
        self.assertFalse(all(c['passed'] for c in evaluate(rows, context, ['wlan1'])))

    def test_wifi_approval_invalidates_old_evidence_and_is_displayed_without_rewriting_intent(self):
        checks = evaluate(self.rows(), package_context(self.router))
        with patch('apps.routers.lab_verification.collect_lab', return_value=checks):
            self.client.post(self.verify_url, self.body, format='json')
        original = self.event.details
        with override_settings(ROUTER_LOCAL_LAN_WIFI_EXTENSIONS=self.wifi_approval()):
            data = self.client.get(self.url).data['local_lab']
            self.assertEqual(data['status'], 'not_verified')
            self.assertIsNone(data['progress']['configuration']['checked_at'])
            self.assertEqual(data['client_interfaces'][-1]['name'], 'wlan1')
            self.assertEqual(data['client_interfaces'][-1]['role'], 'client')
            with patch('apps.routers.lab_verification.collect_lab', return_value=checks):
                response = self.client.post(self.verify_url, self.body, format='json')
            self.assertEqual(response.data['local_lab']['status'], 'verified')
            self.assertEqual(self.router.audit_events.filter(action='hotspot.lab_verified').first().details['wifi_interfaces'], ['wlan1'])
        self.assertEqual(self.client.get(self.url).data['local_lab']['status'], 'not_verified')
        self.event.refresh_from_db()
        self.assertEqual(self.event.details, original)

    def test_progress_survives_expiry_and_transport_failure_but_not_configuration_failure(self):
        rows = self.rows()
        rows['active'] = []
        with patch('apps.routers.lab_verification.collect_lab', return_value=evaluate(rows, package_context(self.router))):
            response = self.client.post(self.verify_url, self.body, format='json')
        progress = response.data['local_lab']['progress']
        self.assertTrue(progress['configuration']['passed'])
        self.assertTrue(progress['configuration']['fresh'])
        self.assertFalse(progress['customer_login']['passed'])
        RouterAuditEvent.objects.filter(action='hotspot.lab_verified').update(created_at=timezone.now()-timedelta(minutes=11))
        saved = self.client.get(self.url).data['local_lab']['progress']
        self.assertTrue(saved['configuration']['passed'])
        self.assertFalse(saved['configuration']['fresh'])
        with patch('apps.routers.lab_verification.collect_lab', side_effect=DiscoveryError('unreachable')):
            failed = self.client.post(self.verify_url, self.body, format='json')
        self.assertTrue(failed.data['local_lab']['progress']['configuration']['passed'])
        self.assertFalse(failed.data['local_lab']['progress']['configuration']['fresh'])
        rows['hotspots'] = []
        with patch('apps.routers.lab_verification.collect_lab', return_value=evaluate(rows, package_context(self.router))):
            changed = self.client.post(self.verify_url, self.body, format='json')
        self.assertFalse(changed.data['local_lab']['progress']['configuration']['passed'])
        self.assertFalse(changed.data['ready'])

    def test_progress_does_not_survive_revocation_or_changed_approval(self):
        with patch('apps.routers.lab_verification.collect_lab', return_value=evaluate(self.rows(), package_context(self.router))):
            self.client.post(self.verify_url, self.body, format='json')
        with override_settings(ROUTER_LOCAL_LAN_TARGETS={}):
            self.assertIsNone(self.client.get(self.url).data['local_lab']['progress']['configuration']['checked_at'])
        RouterAuditEvent.objects.create(router=self.router, action='hotspot.intent_revoked', details=self.body)
        self.assertIsNone(self.client.get(self.url).data['local_lab']['progress']['configuration']['checked_at'])

    def setUp(self):
        LocalLanTests.setUp(self)
        self.settings_override = override_settings(ROUTER_LOCAL_LAN_TARGETS=self.approvals)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        inventory = RouterAuditEvent.objects.create(router=self.router, action='hotspot.inventory_discovered', details={
            'router_version': self.router.updated_at.isoformat(), 'inventory': LocalLanTests.snapshot(self)})
        self.payload.update(authentication_mode='local_user', inventory_id=str(inventory.pk))
        self.payload.pop('expected_updated_at')
        self.event = RouterAuditEvent.objects.create(router=self.router, action='hotspot.intent_created', details={
            'version': 'hotspot-review-v1', 'intent': self.payload, 'router_version': self.router.updated_at.isoformat()})
        RouterAuditEvent.objects.create(router=self.router, action='hotspot.lab_package_exported', details={'intent_id': str(self.event.pk)})
        self.body = {'intent_id': str(self.event.pk)}
        self.verify_url = self.url + 'verify-local-lab/'

    def rows(self):
        owner = 'yarotech-lab:' + str(self.event.pk)
        user = 'yr-' + self.event.pk.hex[:16]
        return {
            'resource': [{'board-name': 'Lab model', 'version': '7.20.1 (stable)'}],
            'bridges': [{'name': 'yr-hotspot', 'disabled': 'false', 'comment': owner}],
            'ports': [{'interface': 'wifi1', 'bridge': 'yr-hotspot', 'disabled': 'false', 'comment': owner}],
            'addresses': [{'address': '10.40.0.1/24', 'interface': 'yr-hotspot', 'disabled': 'false', 'comment': owner},
                          {'address': '192.168.88.1/24', 'interface': 'ether2', 'disabled': 'false'}],
            'hotspots': [{'name': 'yr-hotspot', 'interface': 'yr-hotspot', 'profile': 'yr-profile', 'disabled': 'false'}],
            'profiles': [{'name': 'yr-profile', 'use-radius': 'false'}],
            'dhcp': [{'name': user, 'interface': 'yr-hotspot', 'address-pool': user, 'comment': owner, 'disabled': 'false'}],
            'leases': [{'server': user, 'status': 'bound'}],
            'users': [{'name': user, 'server': 'yr-hotspot', 'profile': user, 'comment': owner, 'disabled': 'false'}],
            'active': [{'user': user, 'server': 'yr-hotspot'}],
        }

    def test_live_evidence_and_no_production_transition(self):
        checks = evaluate(self.rows(), package_context(self.router))
        self.assertTrue(all(c['passed'] for c in checks))
        with patch('apps.routers.lab_verification.collect_lab', return_value=checks):
            response = self.client.post(self.verify_url, self.body, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['local_lab']['status'], 'verified')
        self.assertFalse(response.data['ready'])
        self.assertFalse(response.data['execution_enabled'])
        self.router.refresh_from_db()
        self.assertEqual(self.router.deployment_status, 'not_deployed')
        self.assertFalse(self.router.onboarding_checks.exists())
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertNotIn('NEVER-DISCLOSE', str(response.data))
        with patch('apps.routers.lab_verification.collect_lab', side_effect=DiscoveryError('tls_failed')):
            failed = self.client.post(self.verify_url, self.body, format='json')
        self.assertEqual(failed.data['local_lab']['status'], 'unreachable')
        self.assertEqual(failed.data['local_lab']['checks'], [])

    def test_missing_disabled_wrong_owner_and_other_user_cannot_pass(self):
        context = package_context(self.router)
        for key in TABLES:
            rows = self.rows()
            rows[key] = []
            self.assertFalse(all(c['passed'] for c in evaluate(rows, context)), key)
        for key in ['ports', 'bridges', 'addresses', 'users', 'dhcp', 'hotspots']:
            rows = self.rows()
            rows[key][0]['disabled'] = 'true'
            self.assertFalse(all(c['passed'] for c in evaluate(rows, context)), key)
        rows = self.rows()
        rows['active'][0]['user'] = 'another-user'
        self.assertFalse(all(c['passed'] for c in evaluate(rows, context)))
        rows = self.rows()
        rows['ports'][0]['comment'] = 'old-package'
        self.assertFalse(all(c['passed'] for c in evaluate(rows, context)))
        rows = self.rows()
        rows['ports'].append({'interface': 'ether1', 'bridge': 'yr-hotspot'})
        self.assertFalse(all(c['passed'] for c in evaluate(rows, context)))

    def test_expired_download_allowed_but_stale_evidence_and_revocation_blocked(self):
        RouterAuditEvent.objects.filter(pk=self.event.pk).update(created_at=timezone.now()-timedelta(hours=2))
        self.assertIsNotNone(package_context(self.router))
        with patch('apps.routers.lab_verification.collect_lab', return_value=evaluate(self.rows(), package_context(self.router))):
            self.assertEqual(self.client.post(self.verify_url, self.body, format='json').status_code, 200)
        RouterAuditEvent.objects.filter(action='hotspot.lab_verified').update(created_at=timezone.now()-timedelta(minutes=11))
        self.assertEqual(self.client.get(self.url).data['local_lab']['status'], 'stale')
        RouterAuditEvent.objects.create(router=self.router, action='hotspot.intent_revoked', details=self.body)
        with patch('apps.routers.lab_verification.collect_lab') as collect:
            self.assertEqual(self.client.post(self.verify_url, self.body, format='json').status_code, 409)
            collect.assert_not_called()

    def test_permission_approval_and_concurrent_changes(self):
        with patch('apps.routers.lab_verification.collect_lab') as collect:
            self.client.force_authenticate(self.staff)
            self.assertEqual(self.client.post(self.verify_url, self.body, format='json').status_code, 403)
            self.client.force_authenticate(self.manager)
            self.assertEqual(self.client.post(self.verify_url, {**self.body, 'url': 'https://example.com'}, format='json').status_code, 400)
            with override_settings(ROUTER_LOCAL_LAN_TARGETS={}):
                self.assertEqual(self.client.post(self.verify_url, self.body, format='json').status_code, 409)
            collect.assert_not_called()
        def change(*args):
            RouterAuditEvent.objects.create(router=self.router, action='hotspot.intent_revoked', details=self.body)
            return [{'check_type': 'local_login', 'passed': True}]
        with patch('apps.routers.lab_verification.collect_lab', side_effect=change):
            self.assertEqual(self.client.post(self.verify_url, self.body, format='json').status_code, 409)
        self.assertFalse(RouterAuditEvent.objects.filter(action='hotspot.lab_verified').exists())

    def test_transport_uses_approved_https_and_never_requests_passwords(self):
        self.router.routeros_username = 'lab-reader'
        self.router.routeros_password_encrypted = 'encrypted-placeholder'
        rows = self.rows()
        with patch('apps.routers.lab_verification.secret_store.decrypt', return_value='private'), patch('apps.routers.lab_verification.requests.Session') as factory, patch('apps.routers.lab_verification.read_table', side_effect=[rows[key] for key in TABLES]) as read:
            checks = collect_lab(self.router, package_context(self.router))
        self.assertTrue(all(c['passed'] for c in checks))
        session = factory.return_value.__enter__.return_value
        self.assertFalse(session.trust_env)
        self.assertTrue(session.verify)
        for call in read.call_args_list:
            self.assertTrue(call.args[1].startswith('https://192.168.88.1:'))
            self.assertNotIn('password', call.args[2])
            self.assertNotIn('mac-address', call.args[2])
