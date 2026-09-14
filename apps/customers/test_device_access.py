from datetime import timedelta
from django.contrib.auth import get_user_model
from django.db import connection
from django.utils import timezone
from rest_framework.test import APITransactionTestCase
from apps.tenants.models import Tenant, TenantMembership
from apps.routers.models import NASDevice
from apps.vouchers.models import InternetPlan, Voucher, Radacct
from .models import DeviceAccessSession, DeviceAccessSync
from .device_access_sync import sync_device_access


class DeviceAccessTests(APITransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.created = "radacct" not in connection.introspection.table_names()
        if cls.created:
            with connection.schema_editor() as editor:
                editor.create_model(Radacct)

    @classmethod
    def tearDownClass(cls):
        if cls.created:
            with connection.schema_editor() as editor:
                editor.delete_model(Radacct)
        super().tearDownClass()

    def setUp(self):
        Radacct.objects.all().delete()
        self.tenant = Tenant.objects.create(name="Lab", slug="usage-lab")
        self.other = Tenant.objects.create(name="Other", slug="usage-other")
        self.user = get_user_model().objects.create_user(username="usage-owner")
        TenantMembership.objects.create(tenant=self.tenant, user=self.user, role="owner")
        self.client.force_authenticate(self.user)
        self.router = NASDevice.objects.create(tenant=self.tenant, name="Lab", ip_address="192.0.2.40")
        NASDevice.objects.create(tenant=self.other, name="Other", ip_address="192.0.2.41")
        plan = InternetPlan.objects.create(tenant=self.tenant, name="Daily", price=100, duration_hours=24)
        self.a = Voucher.objects.create(tenant=self.tenant, plan=plan, username="CODE-A", password="CODE-A", status="active", device_limit=3, expires_at=timezone.now()+timedelta(days=2))
        self.b = Voucher.objects.create(tenant=self.tenant, plan=plan, username="CODE-B", password="CODE-B", status="active")
        self.url = "/api/v1/customer-devices/"
        self.mac = "AA:BB:CC:DD:EE:FF"

    def row(self, session, code="CODE-A", mac="aa-bb-cc-dd-ee-ff", ip="192.0.2.40", start=None, stopped=False):
        start = start or timezone.now()-timedelta(minutes=1)
        return Radacct.objects.create(sessionid=session, username=code, callingstationid=mac, nasipaddress=ip,
            acctstarttime=start, acctstoptime=start+timedelta(seconds=30) if stopped else None,
            acctsessiontime=30, acctinputoctets=100, acctoutputoctets=200)

    def test_reconnect_shared_codes_and_new_code_before_expiry(self):
        self.row("one")
        self.row("two", mac="aabb.ccdd.eeff")
        self.row("three", code="CODE-B")
        self.row("four", mac="112233445566")
        sync_device_access()
        sync_device_access()
        self.assertEqual(DeviceAccessSession.objects.count(),4)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(response.data["summary"], {"devices":2,"distinct_codes":2})
        device = next(d for d in response.data["results"] if d["mac_address"]==self.mac)
        self.assertEqual((device["codes_used"],device["sessions"],device["bytes_total"]),(2,3,900))
        self.assertEqual(device["status"],"online")
        details = self.client.get(self.url+self.mac+"/codes/")
        self.assertEqual(details.data["count"],2)
        code = next(c for c in details.data["results"] if c["access_code"]=="CODE-A")
        self.assertEqual(code["sessions"],2)
        self.assertEqual(code["device_limit"],3)
        self.assertEqual(code["status"],"active")
        Radacct.objects.all().delete()
        sync_device_access()
        self.assertEqual(self.client.get(self.url).data["summary"]["distinct_codes"],2)

    def test_unknown_mac_wrong_nas_foreign_voucher_and_ambiguous_nas_are_excluded(self):
        self.row("missing",mac=None)
        self.row("invalid",mac="garbage")
        self.row("wrong-nas",ip="192.0.2.41")
        self.row("unknown-code",code="NOT-A-VOUCHER")
        other_plan=InternetPlan.objects.create(tenant=self.other,name="Other",price=100,duration_hours=24)
        Voucher.objects.create(tenant=self.other,plan=other_plan,username="OTHER",password="OTHER")
        self.row("foreign",code="OTHER")
        self.row("ambiguous")
        NASDevice.objects.create(tenant=self.other,name="Duplicate",ip_address="192.0.2.40")
        sync_device_access()
        self.assertEqual(DeviceAccessSession.objects.count(),0)
        self.assertEqual(self.client.get(self.url+self.mac+"/codes/").status_code,404)

    def test_period_lifetime_expiry_and_stale_online(self):
        self.row("old",start=timezone.now()-timedelta(days=40),stopped=True)
        self.row("recent",code="CODE-B")
        sync_device_access()
        today=self.client.get(self.url,{"period":"today"}).data["results"][0]
        self.assertEqual((today["codes_used"],today["lifetime_codes_used"]),(1,2))
        self.a.expires_at=timezone.now()-timedelta(days=1)
        self.a.save()
        details=self.client.get(self.url+self.mac+"/codes/").data["results"]
        self.assertEqual(next(d for d in details if d["access_code"]=="CODE-A")["status"],"expired")
        DeviceAccessSync.objects.update(completed_at=timezone.now()-timedelta(minutes=10))
        self.assertEqual(self.client.get(self.url,{"activity":"online"}).data["count"],0)
        self.assertEqual(self.client.get(self.url,{"activity":"unknown"}).data["count"],1)
        self.assertEqual(self.client.get(self.url,{"period":"custom","start":"2026-02-02","end":"2026-01-01"}).status_code,400)
        self.assertEqual(self.client.get(self.url,{"period":"invalid"}).status_code,400)

    def test_closed_sessions_cross_tenant_read_and_staff_redaction(self):
        self.row("closed",stopped=True)
        sync_device_access()
        self.assertEqual(self.client.get(self.url,{"activity":"offline"}).data["count"],1)
        member=self.user.membership
        member.role="staff"
        member.save()
        self.client.force_authenticate(get_user_model().objects.get(pk=self.user.pk))
        self.assertEqual(self.client.get(self.url+self.mac+"/codes/").data["results"][0]["access_code"],"Hidden")
        member.tenant=self.other
        member.save()
        self.client.force_authenticate(get_user_model().objects.get(pk=self.user.pk))
        self.assertEqual(self.client.get(self.url).data["count"],0)
        self.assertEqual(self.client.get(self.url+self.mac+"/codes/").status_code,404)
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(self.url).status_code,[401,403])

    def test_interim_update_replay_does_not_inflate_bytes(self):
        row=self.row("session")
        sync_device_access()
        row.acctinputoctets=500
        row.acctsessiontime=60
        row.save()
        sync_device_access()
        row.acctinputoctets=50
        row.save()
        sync_device_access()
        result=self.client.get(self.url).data["results"][0]
        self.assertEqual((result["codes_used"],result["sessions"],result["bytes_total"]),(1,1,700))
