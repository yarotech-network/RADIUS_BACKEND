from datetime import timedelta
from django.utils import timezone
from apps.vouchers.models import PaymentTransaction, Voucher
from apps.vouchers.filters import VoucherFilter
from apps.vouchers.status_rules import classify
from .test_device_access import DeviceAccessTests
from .models import DeviceAccessSync
from .device_access_sync import sync_device_access


class CustomerAccessTests(DeviceAccessTests):
    def purchase(self, voucher=None, reference='purchase-1', status='success'):
        return PaymentTransaction.objects.create(tenant=self.tenant, voucher=voucher or self.a,
            plan=self.a.plan, amount=100, status=status, reference=reference, customer_email='same@example.com')

    def test_unused_purchase_visible_without_device(self):
        self.a.status = 'unused'
        self.a.save()
        self.purchase()
        response = self.client.get('/api/v1/customer-access/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['count'], 1)
        row = response.data['results'][0]
        self.assertEqual((row['devices'], row['connection'], row['access_code']), (0, 'never_connected', None))
        self.assertEqual(self.client.get(f'/api/v1/customer-access/{self.a.pk}/').data['access_code'], self.a.username)

    def test_purchase_identity_and_usage_not_duplicated(self):
        self.purchase()
        self.purchase(self.b, 'purchase-2')
        self.row('s1')
        self.row('s2', mac='11:22:33:44:55:66')
        sync_device_access()
        response = self.client.get('/api/v1/customer-access/')
        self.assertEqual(response.data['count'], 2)
        row = next(r for r in response.data['results'] if r['id'] == self.a.pk)
        self.assertEqual((row['devices'], row['sessions'], row['bytes_total']), (2, 2, 600))
        self.assertEqual(row['connection'], 'online')

    def test_anonymous_and_stale_and_tenant_filters(self):
        self.row('s1')
        sync_device_access()
        self.assertEqual(self.client.get('/api/v1/customer-access/').data['count'], 1)
        DeviceAccessSync.objects.update(completed_at=timezone.now()-timedelta(minutes=3))
        response = self.client.get('/api/v1/customer-access/?activity=unknown')
        self.assertEqual(response.data['count'], 1)
        self.assertFalse(response.data['sync_fresh'])
        self.assertEqual(self.client.get('/api/v1/customer-access/?activity=online').data['count'], 0)
        self.assertEqual(self.client.get('/api/v1/customer-access/?search=nomatch').data['count'], 0)
        self.assertEqual(self.client.get('/api/v1/customer-access/?status=bad').status_code, 400)

    def test_expiry_precedence_and_used_history(self):
        self.a.expires_at = timezone.now()-timedelta(seconds=1)
        self.a.save()
        self.b.status = 'disabled'
        self.b.expires_at = self.a.expires_at
        self.b.first_used_at = timezone.now()-timedelta(days=1)
        self.b.save()
        query = classify(Voucher.objects.filter(tenant=self.tenant), self.tenant)
        expired = VoucherFilter({'status': 'expired'}, queryset=query).qs
        self.assertEqual(list(expired.values_list('pk', flat=True)), [self.a.pk])
        used = VoucherFilter({'status': 'used'}, queryset=query).qs
        self.assertEqual(set(used.values_list('pk', flat=True)), {self.a.pk, self.b.pk})
        self.b.first_used_at = None
        self.b.save()
        self.assertNotIn(self.b.pk, VoucherFilter({'status':'used'}, queryset=query).qs.values_list('pk', flat=True))
        response = self.client.get('/api/v1/vouchers/?status=expired')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['results'][0]['status'], 'expired')
        self.a.refresh_from_db()
        self.assertEqual(self.a.status, 'active')

    def test_unfulfilled_and_failed_excluded(self):
        self.purchase(status='failed')
        self.assertEqual(self.client.get('/api/v1/customer-access/').data['count'], 0)

    def test_accounting_update_is_freshness_source(self):
        row = self.row('s1', start=timezone.now()-timedelta(hours=2))
        from apps.vouchers.models import Radacct
        Radacct.objects.filter(sessionid='s1').update(acctupdatetime=timezone.now(), acctsessiontime=1)
        sync_device_access()
        self.assertEqual(self.client.get('/api/v1/customer-access/').data['results'][0]['connection'], 'online')

    def test_access_staff_redaction_tenant_isolation_and_paging(self):
        self.purchase()
        self.purchase(self.b, 'purchase-2')
        response = self.client.get('/api/v1/customer-access/?page_size=1')
        self.assertEqual((response.data['count'], len(response.data['results'])), (2, 1))
        self.assertEqual(self.client.get('/api/v1/customer-access/?search=same@example.com').data['count'], 2)
        member = self.user.membership
        member.role = 'staff'
        member.save()
        from django.contrib.auth import get_user_model
        self.client.force_authenticate(get_user_model().objects.get(pk=self.user.pk))
        self.assertIsNone(self.client.get(f'/api/v1/customer-access/{self.a.pk}/').data['access_code'])
        member.tenant = self.other
        member.save()
        self.client.force_authenticate(get_user_model().objects.get(pk=self.user.pk))
        self.assertEqual(self.client.get('/api/v1/customer-access/').data['count'], 0)
        self.assertEqual(self.client.get(f'/api/v1/customer-access/{self.a.pk}/').status_code, 404)

    def test_attributable_accounting_without_mac_still_counts_as_used(self):
        self.a.status = 'unused'
        self.a.save()
        self.purchase()
        self.row('no-mac', mac='')
        sync_device_access()
        response = self.client.get('/api/v1/customer-access/?status=used')
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['connection'], 'unknown')

    def test_exact_expiry_boundary_and_status_ordering(self):
        from unittest.mock import patch
        from apps.vouchers.status_rules import effective_status
        now = timezone.now()
        self.a.expires_at = now
        self.a.save()
        self.assertEqual(effective_status(self.a, now), 'expired')
        with patch('apps.vouchers.status_rules.timezone.now', return_value=now):
            response = self.client.get('/api/v1/vouchers/?status=expired&ordering=status')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(self.client.get('/api/v1/vouchers/?status=invalid').status_code, 400)

    def test_sold_is_purchase_history_across_lifecycle(self):
        self.purchase()
        for state in ('unused', 'sold', 'active', 'used', 'expired', 'disabled'):
            with self.subTest(state=state):
                self.a.status = state
                self.a.save()
                for endpoint in ('vouchers', 'customer-access'):
                    response = self.client.get(f'/api/v1/{endpoint}/?status=sold')
                    self.assertEqual(response.status_code, 200, response.data)
                    self.assertEqual([r['id'] for r in response.data['results']], [self.a.pk])
                    self.assertEqual(response.data['results'][0]['status'], state)
        self.a.refresh_from_db()
        self.assertEqual(self.a.status, 'disabled')

    def test_sold_excludes_incomplete_failed_and_cross_tenant_payments(self):
        payment = self.purchase(status='pending')
        for status in ('pending', 'failed', 'abandoned'):
            payment.status = status
            payment.save()
            self.assertEqual(self.client.get('/api/v1/vouchers/?status=sold').data['count'], 0)
        payment.status = 'success'
        payment.tenant = self.other
        payment.save()
        self.assertEqual(self.client.get('/api/v1/vouchers/?status=sold').data['count'], 0)
        # Activation alone is not a sale; explicitly imported sold state remains visible.
        self.b.status = 'sold'
        self.b.save()
        self.assertEqual(self.client.get('/api/v1/vouchers/?status=sold').data['count'], 1)
