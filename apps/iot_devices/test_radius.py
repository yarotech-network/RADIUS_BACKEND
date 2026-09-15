from datetime import timedelta
from django.db import connection
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITransactionTestCase
from apps.tenants.models import Tenant
from apps.routers.models import NASDevice
from apps.vouchers.models import InternetPlan, Voucher, Radcheck, Radreply, Radacct
from apps.vouchers.terms import snapshot_plan
from .models import MacDevice


@override_settings(RADIUS_REST_ENABLED=True, RADIUS_REST_TOKEN='radius-test-token-with-at-least-32-bytes')
class RadiusBoundaryTests(APITransactionTestCase):
    def setUp(self):
        self.created = []
        for model in (Radcheck, Radreply, Radacct):
            if model._meta.db_table not in connection.introspection.table_names():
                with connection.schema_editor() as editor:
                    editor.create_model(model)
                self.created.append(model)
        self.tenant = Tenant.objects.create(name='Radius', slug='radius-boundary')
        self.router = NASDevice.objects.create(tenant=self.tenant, name='NAS', ip_address='192.0.2.44', onboarding_state='active')
        self.plan = InternetPlan.objects.create(tenant=self.tenant, name='Plan', price=1000, duration_hours=24)
        self.voucher = Voucher.objects.create(tenant=self.tenant, plan=self.plan, username='CODEABC123', password='private-pass', purchased_terms=snapshot_plan(self.plan))
        self.payload = {'username': self.voucher.username, 'packet_src_ip': self.router.ip_address, 'calling_station_id': 'AA:BB:CC:DD:EE:FF'}

    def tearDown(self):
        for model in reversed(self.created):
            with connection.schema_editor() as editor:
                editor.delete_model(model)
        super().tearDown()

    def post(self, phase='authorize', **data):
        return self.client.post(reverse('hotspot-radius-'+phase), {**self.payload, **data}, format='json',
            HTTP_X_RADIUS_TOKEN='radius-test-token-with-at-least-32-bytes')

    def test_untrusted_request_and_foreign_nas_are_denied(self):
        self.assertEqual(self.client.post(reverse('hotspot-radius-authorize'), self.payload, format='json').status_code, 403)
        self.assertEqual(self.post(packet_src_ip='192.0.2.99').status_code, 403)
        self.voucher.refresh_from_db()
        self.assertIsNone(self.voucher.expires_at)

    def test_authorize_does_not_activate_and_trusted_post_auth_never_extends(self):
        response = self.post()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data['control:Cleartext-Password']['do_xlat'])
        self.voucher.refresh_from_db()
        self.assertIsNone(self.voucher.expires_at)
        response = self.post('post-auth', session_timeout=60)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertLessEqual(response.data['reply:Session-Timeout']['value'][0], 60)
        self.voucher.refresh_from_db()
        deadline = self.voucher.expires_at
        self.post('post-auth')
        self.voucher.refresh_from_db()
        self.assertEqual(self.voucher.expires_at, deadline)

    def test_iot_requires_matching_mac_nas_status_and_future_deadline(self):
        device = MacDevice.objects.create(tenant=self.tenant, router=self.router, mac_address='AA:BB:CC:DD:EE:FF',
            status='active', expires_at=timezone.now()+timedelta(hours=1), speed_limit='1M/1M')
        self.assertEqual(self.post(username='AABBCCDDEEFF').status_code, 200)
        self.assertEqual(self.post(username='AABBCCDDEEFF', calling_station_id='AA:BB:CC:DD:EE:01').status_code, 403)
        self.assertEqual(self.post(username='AABBCCDDEEFF', packet_src_ip='192.0.2.99').status_code, 403)
        device.status, device.is_active = 'suspended', False
        device.save()
        self.assertEqual(self.post(username='AABBCCDDEEFF').status_code, 403)

    def test_exhausted_cap_denies_access(self):
        device = MacDevice.objects.create(tenant=self.tenant, router=self.router, mac_address='AA:BB:CC:DD:EE:FF',
            status='active', access_type='permanent', data_limit_bytes=100)
        Radacct.objects.create(username='AA-BB-CC-DD-EE-FF', sessionid='cap-test', nasipaddress=self.router.ip_address,
            acctstarttime=timezone.now(), acctinputoctets=100, acctoutputoctets=1)
        self.assertEqual(self.post(username='AABBCCDDEEFF').status_code, 403)
        device.data_limit_bytes=1000
        device.save()
        response=self.post(username='AABBCCDDEEFF')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['reply:Mikrotik-Total-Limit']['value'], [899])

    def test_disabled_integration_fails_closed(self):
        with override_settings(RADIUS_REST_ENABLED=False):
            self.assertEqual(self.post().status_code, 503)
