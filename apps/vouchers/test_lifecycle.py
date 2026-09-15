from datetime import timedelta
from io import StringIO
import json
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from apps.tenants.models import Tenant
from apps.routers.models import NASDevice
from .models import InternetPlan, Voucher, Radcheck
from .radius_test_support import RadiusTablesMixin
from .lifecycle import finalize_authenticated_voucher
from .serializers import VoucherSerializer


class LifecycleTests(RadiusTablesMixin, TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name='Lifecycle', slug='lifecycle')
        self.router = NASDevice.objects.create(tenant=self.tenant, name='NAS', ip_address='192.0.2.44',
            nas_secret='test', onboarding_state='active')
        self.plan = InternetPlan.objects.create(tenant=self.tenant, name='Day', price=1000, duration_hours=24)
        self.voucher = Voucher.objects.create(tenant=self.tenant, plan=self.plan, username='caseSensitiveCode', password='separatePass')

    def finalize(self, **kwargs):
        return finalize_authenticated_voucher(self.voucher.pk, credential_verified=True,
            nas_ip_address=self.router.ip_address, **kwargs)

    def test_unverified_and_wrong_nas_do_not_activate(self):
        self.assertFalse(self.voucher.activate())
        self.assertFalse(finalize_authenticated_voucher(self.voucher.pk, credential_verified=True,
            nas_ip_address='192.0.2.99')['allowed'])
        self.voucher.refresh_from_db()
        self.assertIsNone(self.voucher.expires_at)

    def test_first_auth_works_without_operator_subscription_and_never_extends(self):
        self.assertTrue(self.finalize()['activated'])
        self.voucher.refresh_from_db()
        original = self.voucher.expires_at
        stale = Voucher.objects.get(pk=self.voucher.pk)
        self.assertFalse(stale.activate(credential_verified=True, nas_ip_address=self.router.ip_address))
        self.assertEqual(stale.expires_at, original)
        self.assertEqual(stale.username, 'caseSensitiveCode')
        self.assertEqual(stale.password, 'separatePass')

    def test_stale_unused_instance_cannot_restart_paid_time(self):
        stale = self.voucher
        self.finalize()
        before = Voucher.objects.get(pk=stale.pk).expires_at
        self.assertFalse(stale.activate(credential_verified=True, nas_ip_address=self.router.ip_address))
        self.assertEqual(stale.expires_at, before)

    def test_sold_voucher_starts_once_and_used_without_deadline_is_denied(self):
        Voucher.objects.filter(pk=self.voucher.pk).update(status='sold')
        self.assertTrue(self.finalize()['activated'])
        Voucher.objects.filter(pk=self.voucher.pk).update(status='used', expires_at=None)
        self.assertFalse(self.finalize()['allowed'])

    def test_historical_deadline_and_stricter_radius_expiration_are_preserved(self):
        deadline = timezone.now()+timedelta(hours=2)
        Voucher.objects.filter(pk=self.voucher.pk).update(status='used', expires_at=deadline)
        self.assertTrue(self.finalize()['allowed'])
        self.voucher.refresh_from_db()
        self.assertEqual(self.voucher.expires_at, deadline)
        self.assertIsNone(self.voucher.activated_at)
        earlier = int((timezone.now()+timedelta(minutes=30)).timestamp())
        Radcheck.objects.create(username=self.voucher.username, attribute='Expiration', op=':=', value=str(earlier))
        self.assertLessEqual(self.finalize()['timeout'], 1800)
        self.voucher.refresh_from_db()
        self.assertEqual(int(self.voucher.expires_at.timestamp()), earlier)

    def test_invalid_expiration_does_not_write_activation(self):
        Radcheck.objects.create(username=self.voucher.username, attribute='Expiration', op=':=', value='unknown')
        self.assertFalse(self.finalize()['allowed'])
        self.voucher.refresh_from_db()
        self.assertIsNone(self.voucher.activated_at)

    def test_disabled_deleted_and_past_deadline_are_denied(self):
        for fields in ({'status':'disabled'}, {'status':'expired'},
                       {'status':'unused','deleted_at':timezone.now()},
                       {'status':'unused','deleted_at':None,'expires_at':timezone.now()-timedelta(seconds=1)}):
            Voucher.objects.filter(pk=self.voucher.pk).update(**fields)
            self.assertFalse(self.finalize()['allowed'])

    def test_device_lock_cannot_be_bypassed_and_first_binding_is_retained(self):
        Voucher.objects.filter(pk=self.voucher.pk).update(device_lock_enabled=True)
        self.assertFalse(self.finalize()['allowed'])
        self.assertTrue(self.finalize(mac_address='AA-BB-CC-DD-EE-01')['allowed'])
        self.assertFalse(self.finalize(mac_address='AA:BB:CC:DD:EE:02')['allowed'])
        self.assertTrue(self.finalize(mac_address='aa:bb:cc:dd:ee:01')['allowed'])
        self.voucher.refresh_from_db()
        self.assertEqual(self.voucher.bound_device_mac, 'AA:BB:CC:DD:EE:01')
        self.assertEqual(self.voucher.device_bound_nas_id, self.router.pk)

    def test_ambiguous_nas_or_inactive_tenant_is_denied(self):
        other = Tenant.objects.create(name='Other', slug='other-lifecycle')
        NASDevice.objects.create(tenant=other, name='Duplicate', ip_address=self.router.ip_address, nas_secret='test')
        self.assertFalse(self.finalize()['allowed'])
        self.tenant.is_active = False
        self.tenant.save()
        self.assertFalse(self.finalize()['allowed'])

    def test_audit_is_read_only_and_does_not_expose_credentials(self):
        Voucher.objects.filter(pk=self.voucher.pk).update(status='used', legacy_provenance={'source_id':7})
        before = Voucher.objects.values().get(pk=self.voucher.pk)
        output = StringIO()
        call_command('audit_voucher_compatibility', stdout=output)
        report = json.loads(output.getvalue())
        self.assertEqual(report['issue_counts']['consumed_without_deadline'], 1)
        self.assertNotIn(self.voucher.username, output.getvalue())
        self.assertNotIn(self.voucher.password, output.getvalue())
        self.assertEqual(Voucher.objects.values().get(pk=self.voucher.pk), before)
        self.voucher.refresh_from_db()
        data = VoucherSerializer(self.voucher).data
        self.assertFalse(data['can_edit'])
        self.assertNotIn('legacy_provenance', data)
        self.assertNotIn('bound_device_mac', data)

    def test_legacy_credentials_fit_without_normalization(self):
        self.voucher.username = 'aB' * 32
        self.voucher.password = 'Xy' * 32
        self.voucher.full_clean()
        self.voucher.save()
        self.voucher.refresh_from_db()
        self.assertEqual(self.voucher.username, 'aB' * 32)
        self.assertEqual(self.voucher.password, 'Xy' * 32)


from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.db import close_old_connections, connections
from django.test import TransactionTestCase, skipUnlessDBFeature


class ActivationConcurrencyTests(RadiusTablesMixin, TransactionTestCase):
    @skipUnlessDBFeature('has_select_for_update')
    def test_simultaneous_first_authentication_has_one_activation(self):
        tenant = Tenant.objects.create(name='Concurrent', slug='concurrent-activation')
        router = NASDevice.objects.create(tenant=tenant, name='NAS', ip_address='192.0.2.46',
            nas_secret='test', onboarding_state='active')
        plan = InternetPlan.objects.create(tenant=tenant, name='Day', price=1000, duration_hours=24)
        voucher = Voucher.objects.create(tenant=tenant, plan=plan, username='concurrent-code', password='test')
        barrier = Barrier(2)
        def authenticate():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return finalize_authenticated_voucher(voucher.pk, credential_verified=True, nas_ip_address=router.ip_address)
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: authenticate(), range(2)))
        self.assertTrue(all(result['allowed'] for result in results))
        self.assertEqual(sum(result['activated'] for result in results), 1)
        voucher.refresh_from_db()
        self.assertEqual(voucher.expires_at-voucher.activated_at, timedelta(days=1))
