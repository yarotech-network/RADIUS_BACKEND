from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.db import connection
from django.utils import timezone
from rest_framework.test import APITestCase
from apps.tenants.models import Tenant, TenantMembership
from .models import BandwidthProfile, InternetPlan, Voucher, Radcheck, Radreply
from .services import VoucherService


class BandwidthTests(APITestCase):
    @classmethod
    def setUpClass(cls):
        cls.created = []
        for model in (Radcheck, Radreply):
            if model._meta.db_table not in connection.introspection.table_names():
                with connection.schema_editor() as editor:
                    editor.create_model(model)
                cls.created.append(model)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        for model in reversed(cls.created):
            with connection.schema_editor() as editor:
                editor.delete_model(model)

    def setUp(self):
        self.tenant = Tenant.objects.create(name='A', slug='bandwidth-a')
        self.other = Tenant.objects.create(name='B', slug='bandwidth-b')
        User = get_user_model()
        self.manager = User.objects.create_user(username='band-manager', email='band-manager@example.com')
        self.staff = User.objects.create_user(username='band-staff', email='band-staff@example.com')
        TenantMembership.objects.create(tenant=self.tenant, user=self.manager, role='manager')
        TenantMembership.objects.create(tenant=self.tenant, user=self.staff, role='staff')
        self.client.force_authenticate(self.manager)
        self.profile = BandwidthProfile.objects.create(tenant=self.tenant, name='Standard', upload_kbps=2500, download_kbps=10000)
        self.plan = InternetPlan.objects.create(tenant=self.tenant, name='Daily', price=5050, duration_hours=24, rate_limit='5M/10M')
        self.url = '/api/v1/bandwidth-profiles/'
        self.plan_url = f'/api/v1/plans/{self.plan.pk}/'

    def attach(self):
        response = self.client.patch(self.plan_url, {'bandwidth_profile':self.profile.pk}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.plan.refresh_from_db()
        return response

    def test_profile_create_exact_units_validation_and_replay(self):
        payload = {'name':'Small', 'upload_kbps':512,'download_kbps':1500}
        first = self.client.post(self.url,payload,format='json',HTTP_IDEMPOTENCY_KEY='bandwidth-create-01')
        second = self.client.post(self.url,payload,format='json',HTTP_IDEMPOTENCY_KEY='bandwidth-create-01')
        self.assertEqual(first.status_code,201,first.data)
        self.assertEqual(first.data['rate_limit'],'512k/1500k')
        self.assertEqual(first.data,second.data)
        for key,value in [('upload_kbps',0),('download_kbps',10000001),('upload_kbps',1.5),('tenant',self.other.pk)]:
            self.assertEqual(self.client.post(self.url,{**payload,key:value},format='json').status_code,400)

    def test_tenant_scope_permissions_and_profile_assignment(self):
        other = BandwidthProfile.objects.create(tenant=self.other,name='Other',upload_kbps=1,download_kbps=1)
        self.assertEqual(self.client.get(f'{self.url}{other.pk}/').status_code,404)
        self.assertEqual(self.client.patch(self.plan_url,{'bandwidth_profile':other.pk},format='json').status_code,400)
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get(self.url).status_code,200)
        self.assertEqual(self.client.post(self.url,{'name':'Bad','upload_kbps':10,'download_kbps':10},format='json').status_code,403)
        self.assertEqual(self.client.patch(self.plan_url,{'bandwidth_profile':self.profile.pk},format='json').status_code,403)

    def test_linked_profile_speed_immutable_and_deletion_protected(self):
        self.attach()
        url = f'{self.url}{self.profile.pk}/'
        self.assertEqual(self.client.patch(url,{'upload_kbps':999},format='json').status_code,400)
        self.assertEqual(self.client.delete(url).status_code,400)
        self.assertEqual(self.client.patch(url,{'name':'Renamed','is_active':False},format='json').status_code,200)
        self.assertEqual(self.client.get(self.url).data['results'][0]['plan_count'],1)
        # Existing linkage may remain; a new plan cannot select the inactive profile.
        self.assertEqual(self.client.patch(self.plan_url,{'bandwidth_profile':self.profile.pk},format='json').status_code,200)
        self.assertEqual(self.client.post('/api/v1/plans/',{'name':'New','price':50,'duration_hours':1,'bandwidth_profile':self.profile.pk},format='json').status_code,400)

    def test_legacy_plan_and_service_contracts_remain_explicit(self):
        self.assertEqual(self.client.get(self.plan_url).data['rate_limit'],'5M/10M')
        self.assertIsNone(self.client.get(self.plan_url).data['bandwidth_profile'])
        response = self.attach()
        self.assertEqual(response.data['rate_limit'],'2500k/10000k')
        self.assertEqual(response.data['price'],5050)
        for payload in [{'service_type':'pppoe'},{'free_access':True},{'bandwidth_profile':self.profile.pk,'rate_limit':'1M/2M'}]:
            self.assertEqual(self.client.patch(self.plan_url,payload,format='json').status_code,400)
        response = self.client.patch(self.plan_url,{'rate_limit':'3M/5M'},format='json')
        self.assertEqual(response.status_code,200)
        self.assertIsNone(response.data['bandwidth_profile'])
        self.assertEqual(response.data['service_type'],'hotspot')

    def test_rate_snapshot_reaches_radius_without_rewriting_issued_voucher(self):
        self.attach()
        voucher = VoucherService.generate_vouchers(self.tenant,self.plan.pk,1)[0]
        self.assertEqual(voucher.rate_limit_snapshot,'2500k/10000k')
        row = Radreply.objects.get(username=voucher.username,attribute='Mikrotik-Rate-Limit')
        self.assertEqual((row.op,row.value),(':=','2500k/10000k'))
        self.client.patch(self.plan_url,{'rate_limit':'1M/2M'},format='json')
        row.refresh_from_db()
        self.assertEqual(row.value,'2500k/10000k')
        voucher.refresh_from_db()
        self.assertEqual(voucher.rate_limit_snapshot,'2500k/10000k')
        VoucherService.disable_voucher(voucher)
        self.assertFalse(Radreply.objects.filter(username=voucher.username).exists())

    def test_legacy_issuance_is_not_silently_backfilled(self):
        voucher = VoucherService.generate_vouchers(self.tenant,self.plan.pk,1)[0]
        self.assertEqual(voucher.rate_limit_snapshot,'')
        self.assertFalse(Radreply.objects.exists())

    def test_radius_failure_rolls_back_voucher_and_credentials(self):
        self.attach()
        with patch('apps.vouchers.services.Radreply.objects.create',side_effect=RuntimeError('reply failure')):
            with self.assertRaises(RuntimeError):
                VoucherService.generate_vouchers(self.tenant,self.plan.pk,1)
        self.assertFalse(Voucher.objects.exists())
        self.assertFalse(Radcheck.objects.exists())

    def test_expiry_removes_snapshot_reply_after_plan_is_detached(self):
        self.attach()
        voucher = VoucherService.generate_vouchers(self.tenant,self.plan.pk,1)[0]
        self.client.patch(self.plan_url,{'bandwidth_profile':None},format='json')
        voucher.status='active'; voucher.expires_at=timezone.now()-timezone.timedelta(seconds=1); voucher.save()
        self.assertEqual(VoucherService.expire_vouchers(),1)
        self.assertFalse(Radreply.objects.exists())

    def test_unused_edit_renames_reply_and_delete_cleans_up(self):
        self.attach()
        voucher = VoucherService.generate_vouchers(self.tenant,self.plan.pk,1)[0]
        old = voucher.username
        response = self.client.patch(f'/api/v1/vouchers/{voucher.pk}/', {'username':'changed-speed-user'}, format='json')
        self.assertEqual(response.status_code,200,response.data)
        self.assertFalse(Radreply.objects.filter(username=old).exists())
        self.assertEqual(Radreply.objects.get(username='changed-speed-user').value,'2500k/10000k')
        self.assertEqual(self.client.delete(f'/api/v1/vouchers/{voucher.pk}/').status_code,204)
        self.assertFalse(Radreply.objects.exists())
