from datetime import timedelta
from unittest.mock import patch
from django.db import connection
from django.db.models.deletion import ProtectedError
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase
from apps.vouchers.models import PaymentTransaction, Voucher
from .models import MacDevice, DeviceRenewal
from .tests import IoTDeviceTests
from .accounting import device_accounting


class DeviceLifecycleTests(APITestCase):
    setUp = IoTDeviceTests.setUp
    payload = IoTDeviceTests.payload

    def create(self, **changes):
        self.client.force_authenticate(self.manager)
        response = self.client.post(reverse('iot-device-list'), self.payload(**changes), format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return MacDevice.objects.get(pk=response.data['id'])

    def renew(self, device, key='renew-request-0001', **changes):
        data = {'plan': self.plan_a.pk, 'expected_version': device.version, **changes}
        return self.client.post(reverse('iot-device-renew', args=[device.pk]), data,
                                format='json', HTTP_IDEMPOTENCY_KEY=key)

    def action(self, device, action, **changes):
        return self.client.post(reverse('iot-device-lifecycle', args=[device.pk]),
            {'action': action, 'expected_version': device.version, **changes}, format='json')

    def test_renewal_keeps_unused_time_replays_and_snapshots_without_network_or_payment(self):
        device = self.create()
        previous = device.expires_at
        with CaptureQueriesContext(connection) as queries:
            response = self.renew(device)
        self.assertEqual(response.status_code, 200, response.data)
        replay = self.renew(device)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay['Idempotency-Replayed'], 'true')
        device.refresh_from_db()
        self.assertEqual(device.expires_at, previous + timedelta(hours=24))
        self.assertEqual(device.version, 2)
        self.assertEqual(response.data['network_enforcement'], 'not_connected')
        self.assertEqual(DeviceRenewal.objects.count(), 1)
        self.assertEqual(device.issued_terms['source'], 'operator_grant')
        self.plan_a.name = 'Changed later'
        self.plan_a.save()
        self.assertEqual(device.renewals.get().terms['name'], 'A')
        self.assertFalse(PaymentTransaction.objects.exists())
        self.assertFalse(Voucher.objects.exists())
        self.assertFalse(any('radcheck' in query['sql'].lower() or 'radreply' in query['sql'].lower() for query in queries))
        conflict = self.renew(device, plan=self.plan_b.pk)
        self.assertEqual(conflict.status_code, 409)

    def test_expired_renewal_starts_now_and_suspension_is_preserved(self):
        device = self.create(is_active=False)
        before = timezone.now() - timedelta(days=2)
        MacDevice.objects.filter(pk=device.pk).update(expires_at=before)
        device.refresh_from_db()
        now = timezone.now()
        with patch('apps.iot_devices.lifecycle.timezone.now', return_value=now):
            response = self.renew(device)
        self.assertEqual(response.status_code, 200, response.data)
        device.refresh_from_db()
        self.assertEqual(device.expires_at, now + timedelta(hours=24))
        self.assertEqual(device.configured_status, 'suspended')
        self.assertFalse(device.is_active)

    def test_revoked_and_deleted_cannot_renew_or_bypass_explicit_reactivation(self):
        device = self.create()
        self.assertEqual(self.action(device, 'revoke').status_code, 200)
        device.refresh_from_db()
        self.assertEqual(self.renew(device).status_code, 400)
        self.assertEqual(self.action(device, 'suspend').status_code, 400)
        for active in (True, False):
            response = self.client.patch(reverse('iot-device-detail', args=[device.pk]),
                {'is_active': active, 'expected_version': device.version}, format='json')
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.action(device, 'reactivate').status_code, 200)
        device.refresh_from_db()
        self.assertEqual(self.action(device, 'delete').status_code, 200)
        device.refresh_from_db()
        self.assertEqual(self.renew(device, key='renew-deleted-0001').status_code, 400)
        self.assertEqual(self.action(device, 'reactivate').status_code, 400)
        self.assertIsNotNone(device.deleted_at)

    def test_remove_retains_device_and_renewal_history(self):
        device = self.create()
        self.assertEqual(self.renew(device).status_code, 200)
        device.refresh_from_db()
        detail = reverse('iot-device-detail', args=[device.pk])
        self.assertEqual(self.client.delete(detail).status_code, 400)
        self.assertEqual(self.client.delete(detail, {'expected_version': 1}).status_code, 400)
        self.assertEqual(self.client.delete(detail + '?expected_version=1').status_code, 409)
        self.assertEqual(self.client.delete(detail + f'?expected_version={device.version}').status_code, 204)
        device.refresh_from_db()
        self.assertFalse(device.is_active)
        self.assertEqual(device.status, 'deleted')
        self.assertEqual(self.client.get(reverse('iot-device-list')).data['count'], 0)
        self.assertEqual(self.client.get(reverse('iot-device-list'), {'include_deleted': 'true'}).data['count'], 1)
        history = self.client.get(reverse('iot-device-renewals', args=[device.pk]))
        self.assertEqual(history.data['count'], 1)
        with self.assertRaises(ProtectedError):
            device.delete()

    def test_stale_edits_and_missing_renewal_key_do_not_mutate(self):
        device = self.create()
        self.assertEqual(self.action(device, 'suspend').status_code, 200)
        self.assertEqual(self.renew(device).status_code, 409)
        detail = reverse('iot-device-detail', args=[device.pk])
        for payload in ({'device_name': 'Stale'}, {'device_name': 'Stale', 'expected_version': 1}):
            self.assertEqual(self.client.patch(detail, payload, format='json').status_code, 409)
        response = self.client.post(reverse('iot-device-renew', args=[device.pk]),
            {'plan': self.plan_a.pk, 'expected_version': 2}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(DeviceRenewal.objects.exists())

    def test_staff_and_other_tenant_cannot_write_or_read_renewals(self):
        device = self.create()
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.renew(device).status_code, 403)
        self.assertEqual(self.action(device, 'suspend').status_code, 403)
        self.assertEqual(self.client.get(reverse('iot-device-renewals', args=[device.pk])).status_code, 403)
        self.client.force_authenticate(self.manager)
        foreign = MacDevice.objects.create(tenant=self.b, plan=self.plan_b, mac_address='AA:00:00:00:00:01')
        self.assertEqual(self.renew(foreign).status_code, 404)
        self.assertEqual(self.client.get(reverse('iot-device-renewals', args=[foreign.pk])).status_code, 404)
        self.assertEqual(self.renew(device, plan=self.plan_b.pk).status_code, 400)

    def test_active_mac_conflicts_but_inactive_history_is_allowed_and_accounting_is_ambiguous(self):
        device = self.create()
        response = self.client.post(reverse('iot-device-list'), self.payload(), format='json')
        self.assertEqual(response.status_code, 409)
        older = self.create(is_active=False)
        self.assertEqual(self.action(older, 'reactivate').status_code, 409)
        for rows in ([device], [older], [device, older]):
            accounting = device_accounting(rows, self.a)
            self.assertTrue(all(not value['available'] for value in accounting.values()))
            self.assertTrue(all(value['session_count'] is None for value in accounting.values()))

    def test_mac_validation_and_optional_plan(self):
        self.client.force_authenticate(self.manager)
        for mac in ('00:00:00:00:00:00', 'FF:FF:FF:FF:FF:FF', '01:22:33:44:55:66', 'invalid'):
            response = self.client.post(reverse('iot-device-list'), self.payload(mac_address=mac), format='json')
            self.assertEqual(response.status_code, 400, response.data)
        device = self.create(plan=None, access_type='permanent', expires_at=None)
        self.assertIsNone(device.plan)
        self.assertEqual(self.renew(device).status_code, 400)

    def test_invalid_plan_router_and_unknown_fields_fail_without_mutation(self):
        device = self.create()
        self.plan_a.plan_type = 'voucher'
        self.plan_a.save()
        self.assertEqual(self.renew(device).status_code, 400)
        self.plan_a.plan_type = 'iot_mac'
        self.plan_a.save()
        self.router.is_active = False
        self.router.save()
        self.assertEqual(self.renew(device, key='disabled-router-0001').status_code, 400)
        self.assertFalse(DeviceRenewal.objects.exists())
        device.refresh_from_db()
        self.assertEqual(device.version, 1)
        response = self.client.patch(reverse('iot-device-detail', args=[device.pk]),
            {'expected_version': 1, 'status': 'active', 'speed_limit': 'unlimited'}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_renewal_ledger_failure_rolls_back_deadline_and_version(self):
        device = self.create()
        before = device.expires_at
        from rest_framework.exceptions import ValidationError
        with patch('apps.iot_devices.models.DeviceRenewal.objects.create', side_effect=ValidationError('Unavailable')):
            response = self.renew(device)
        self.assertEqual(response.status_code, 400)
        device.refresh_from_db()
        self.assertEqual(device.expires_at, before)
        self.assertEqual(device.version, 1)


    def test_expired_active_device_renews_from_now_with_fractional_plan_duration(self):
        from decimal import Decimal
        device = self.create()
        MacDevice.objects.filter(pk=device.pk).update(expires_at=timezone.now() - timedelta(days=1))
        self.plan_a.duration_hours = Decimal('0.25')
        self.plan_a.save()
        now = timezone.now()
        with patch('apps.iot_devices.lifecycle.timezone.now', return_value=now):
            response = self.renew(device)
        self.assertEqual(response.status_code, 200, response.data)
        device.refresh_from_db()
        self.assertEqual(device.expires_at, now + timedelta(minutes=15))
        self.assertEqual(device.status, 'active')
        self.assertEqual(device.renewals.get().terms['duration_seconds'], 900)

    def test_anonymous_requests_are_denied(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(reverse('iot-device-list')).status_code, 401)

    def test_archived_plan_and_router_restriction_prevent_new_grants(self):
        from apps.routers.models import NASDevice
        device = self.create()
        from apps.vouchers.models import InternetPlan
        archived = InternetPlan.objects.create(tenant=self.a, name='Archived', price=1000, duration_hours=24,
            plan_type='iot_mac', archived_at=timezone.now(), is_active=False, is_public=False, agent_enabled=False)
        self.assertEqual(self.renew(device, plan=archived.pk).status_code, 400)
        self.plan_a.public_router = NASDevice.objects.create(tenant=self.a, name='Restricted', ip_address='192.0.2.90')
        self.plan_a.save()
        self.assertEqual(self.renew(device, key='restricted-router-0001').status_code, 400)
        self.assertFalse(DeviceRenewal.objects.exists())
