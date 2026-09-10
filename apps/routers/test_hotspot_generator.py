from copy import deepcopy
from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone
from rest_framework.test import APITestCase

from .hotspot_generator import quote
from .models import NASDevice, RouterAuditEvent
from .test_discovery import inventory
from . import test_hotspot_setup


class HotspotLabPackageTests(APITestCase):
    def setUp(self):
        test_hotspot_setup.HotspotSetupTests.setUp(self)
        self.router.model = 'Lab model'
        self.router.routeros_version = '7.20.1'
        self.router.wireguard_ip = '10.8.0.20'
        self.router.deployment_status = 'deployed'
        self.router.save()
        self.snapshot = RouterAuditEvent.objects.create(router=self.router, action='hotspot.inventory_discovered', details={'router_version':self.router.updated_at.isoformat(), 'inventory':inventory()})
        self.payload.update(expected_updated_at=self.router.updated_at.isoformat(), inventory_id=str(self.snapshot.pk))
        review = self.client.post(self.url, self.payload, format='json')
        self.assertEqual(review.status_code, 200, review.data)
        self.body = {'expected_updated_at':self.router.updated_at.isoformat(), 'intent_id':review.data['intent']['id'], 'lab_acknowledged':True, 'dns_server':'1.1.1.1'}
        self.export_url = self.url + 'lab-package/'

    def export(self, **changes):
        return self.client.post(self.export_url, {**self.body, **changes}, format='json')

    def test_secret_free_deterministic_package_has_separate_disabled_stage_and_activation(self):
        with patch('apps.routers.secret_store.secret_store.decrypt', side_effect=AssertionError('No credential reads')):
            first = self.export()
            self.assertEqual(first.status_code, 200, first.data)
            second = self.export()
        self.assertEqual(first.data, second.data)
        self.assertEqual(self.export(dns_server='8.8.8.8').status_code, 409)
        self.assertEqual(first['Cache-Control'], 'no-store')
        self.assertEqual(set(first.data['files']), {'stage.rsc','activate.rsc','cleanup.rsc','README.txt'})
        self.assertFalse(first.data['hardware_validated'])
        stage = first.data['files']['stage.rsc']
        self.assertIn('dns-server=1.1.1.1', stage)
        self.assertIn('out-interface-list=WAN', stage)
        self.assertIn('Management address does not match', stage)
        self.assertIn('7.20.1 (stable)', stage)
        self.assertIn('RADIUS must use', stage)
        commands = [line for line in stage.splitlines() if ' add ' in line]
        self.assertTrue(commands)
        for line in commands:
            if any(path in line for path in ['/ip address add', '/ip dhcp-server add', '/ip hotspot add', '/ip firewall nat add', '/interface bridge port add']):
                self.assertIn('disabled=yes', line)
        self.assertIn('disabled=no', first.data['files']['activate.rsc'])
        self.assertIn('on-error=', first.data['files']['activate.rsc'])
        self.assertIn('Ownership conflict', first.data['files']['cleanup.rsc'])
        self.assertNotIn('NEVER-DISCLOSE-THIS', str(first.data))
        for name in ['stage.rsc','activate.rsc','cleanup.rsc']:
            self.assertNotIn('/radius add', first.data['files'][name])
            self.assertNotIn('/radius set', first.data['files'][name])
            self.assertNotIn('reset-configuration', first.data['files'][name])
        self.assertEqual(RouterAuditEvent.objects.filter(action='hotspot.lab_package_exported').count(), 1)
        self.assertFalse(self.client.get(self.url).data['ready'])
        self.router.refresh_from_db()
        self.assertEqual(self.router.onboarding_state, 'pending')

    def test_acknowledgement_strict_body_and_dns_validation(self):
        for patch_value in [{'lab_acknowledged':False}, {'dns_server':'not-an-ip'}, {'dns_server':'10.40.0.2'}, {'dns_server':'127.0.0.1'}, {'url':'http://127.0.0.1'}, {'nas_secret':'bad'}]:
            with self.subTest(patch_value=patch_value):
                self.assertEqual(self.export(**patch_value).status_code, 400)
        self.assertFalse(RouterAuditEvent.objects.filter(action='hotspot.lab_package_exported').exists())

    def test_cross_tenant_lower_role_and_unauthenticated_denied(self):
        other = NASDevice.objects.create(tenant=self.other, name='Other', ip_address='192.0.2.99', nas_secret='other')
        self.assertEqual(self.client.post(f'/api/v1/routers/{other.pk}/hotspot-setup/lab-package/', self.body, format='json').status_code, 404)
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.export().status_code, 403)
        self.client.force_authenticate(None)
        self.assertIn(self.export().status_code, (401,403))

    def test_expired_revoked_and_changed_reviews_cannot_export(self):
        self.assertEqual(self.export(expected_updated_at=(timezone.now()-timedelta(days=1)).isoformat()).status_code, 409)
        RouterAuditEvent.objects.filter(pk=self.snapshot.pk).update(created_at=timezone.now()-timedelta(minutes=11))
        self.assertEqual(self.export().status_code, 409)
        RouterAuditEvent.objects.filter(pk=self.snapshot.pk).update(created_at=timezone.now())
        self.client.post(self.url+'revoke/', {'intent_id':self.body['intent_id']}, format='json')
        self.assertEqual(self.export().status_code, 409)

    def test_newer_snapshot_and_busy_router_reject_export(self):
        NASDevice.objects.filter(pk=self.router.pk).update(deployment_status='deploying')
        self.assertEqual(self.export().status_code, 409)
        NASDevice.objects.filter(pk=self.router.pk).update(deployment_status='deployed')
        RouterAuditEvent.objects.create(router=self.router, action='hotspot.inventory_discovered', details=self.snapshot.details)
        self.assertEqual(self.export().status_code, 409)

    def test_manual_review_and_incomplete_address_baseline_reject(self):
        old = deepcopy(self.snapshot.details)
        details = deepcopy(old)
        del details['inventory']['addresses']
        RouterAuditEvent.objects.filter(pk=self.snapshot.pk).update(details=details)
        self.assertEqual(self.export().status_code, 400)
        RouterAuditEvent.objects.filter(pk=self.snapshot.pk).update(details=old)
        response = self.client.post(self.url, {**self.payload, 'inventory_id':None}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.export(intent_id=response.data['intent']['id']).status_code, 400)

    def test_overlap_existing_hotspot_and_wrong_profile_reject(self):
        for change in [{'addresses':[{'address':'10.40.0.10/24','interface':'ether1'}]}, {'hotspots':[{'name':'live'}]}, {'hotspot_allowed':False}, {'model':'other'}]:
            details = deepcopy(self.snapshot.details)
            details['inventory'].update(change)
            RouterAuditEvent.objects.filter(pk=self.snapshot.pk).update(details=details)
            self.assertEqual(self.export().status_code, 400)

    def test_quotes_escape_routeros_interpolation_and_control_characters(self):
        self.assertEqual(quote('x$y"z\\'), '"x\\$y\\"z\\\\"')
        from rest_framework.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            quote('line\n:execute')
