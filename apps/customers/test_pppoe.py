from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password
from django.core.management import call_command, CommandError
from django.db import connection
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase
from apps.core.models import ApiCommand, AuditEvent
from apps.tenants.models import Tenant, TenantMembership
from apps.routers.models import NASDevice
from apps.vouchers.models import BandwidthProfile, Radacct
from .models import Customer, PPPoEPlan, PPPoEService
from .reconciliation import claim_services, reconcile_service


@override_settings(PPPOE_RADIUS_TOKEN="test-radius-token-0123456789abcdef0123456789")
class PPPoETests(APITestCase):
    @classmethod
    def setUpClass(cls):
        cls.created = Radacct._meta.db_table not in connection.introspection.table_names()
        if cls.created:
            with connection.schema_editor() as editor:
                editor.create_model(Radacct)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        if cls.created:
            with connection.schema_editor() as editor:
                editor.delete_model(Radacct)

    def setUp(self):
        self.tenant=Tenant.objects.create(name="A",slug="pppoe-a")
        self.other=Tenant.objects.create(name="B",slug="pppoe-b")
        User=get_user_model()
        self.manager=User.objects.create_user(username="pppoe-manager",email="pppoe-manager@example.com")
        self.staff=User.objects.create_user(username="pppoe-staff",email="pppoe-staff@example.com")
        TenantMembership.objects.create(tenant=self.tenant,user=self.manager,role="manager")
        TenantMembership.objects.create(tenant=self.tenant,user=self.staff,role="staff")
        self.client.force_authenticate(self.manager)
        self.customer=Customer.objects.create(tenant=self.tenant,name="Customer",reference="C-1")
        self.profile=BandwidthProfile.objects.create(tenant=self.tenant,name="Home",upload_kbps=2500,download_kbps=10000)
        self.plan=PPPoEPlan.objects.create(tenant=self.tenant,name="Monthly",bandwidth_profile=self.profile,duration_hours=720,price=1500000)
        self.router=NASDevice.objects.create(tenant=self.tenant,name="Router",ip_address="10.33.0.2",nas_secret="test-router-secret",onboarding_state="active")
        self.url="/api/v1/pppoe-services/"
        self.password="A-device-pass-4729!"

    def create(self, **overrides):
        data={"customer":self.customer.pk,"plan":self.plan.pk,"router":str(self.router.pk),"password":self.password,**overrides}
        return self.client.post(self.url,data,format="json",HTTP_IDEMPOTENCY_KEY="pppoe-create-0000001")

    def service(self):
        response=self.create()
        self.assertEqual(response.status_code,201,response.data)
        return PPPoEService.objects.get(pk=response.data["id"])

    def change(self, service, action, **data):
        return self.client.post(f"{self.url}{service.pk}/{action}/",{"expected_version":service.version,**data},format="json",HTTP_IDEMPOTENCY_KEY=f"pppoe-{action}-{service.version:016d}")

    def auth(self, service, **data):
        body={"username":service.username,"password":self.password,"packet_src_ip":self.router.ip_address,"service_type":"Framed-User","framed_protocol":"PPP","nas_port_type":"Ethernet",**data}
        return self.client.post("/api/v1/radius/pppoe/decision/",body,format="json",HTTP_X_RADIUS_TOKEN="test-radius-token-0123456789abcdef0123456789")

    def test_create_hashes_password_and_replays_without_disclosing_credentials(self):
        first=self.create(); second=self.create()
        self.assertEqual(first.status_code,201,first.data)
        self.assertEqual(first.json(),second.json())
        service=PPPoEService.objects.get()
        self.assertTrue(check_password(self.password,service.password_hash))
        self.assertNotEqual(service.password_hash,self.password)
        self.assertTrue(service.username.startswith("yrp-"))
        self.assertEqual(service.rate_limit,"2500k/10000k")
        for value in [str(first.data),str(list(ApiCommand.objects.values_list("response",flat=True))),str(list(AuditEvent.objects.values_list("details",flat=True)))]:
            self.assertNotIn(self.password,value)
            self.assertNotIn(service.password_hash,value)
        self.assertTrue(self.client.get(f"/api/v1/customers/{self.customer.pk}/").data["has_service"])

    def test_tenant_role_and_input_denials(self):
        other_customer=Customer.objects.create(tenant=self.other,name="Other",reference="C-1")
        self.assertEqual(self.create(customer=other_customer.pk).status_code,400)
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get(self.url).status_code,200)
        self.assertEqual(self.client.post(self.url,{},format="json").status_code,403)
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.client.post(self.url,{"customer":self.customer.pk,"plan":self.plan.pk,"router":str(self.router.pk),"password":self.password,"tenant":self.other.pk},format="json").status_code,400)
        self.assertEqual(PPPoEService.objects.count(),0)

    def test_renewal_replay_stale_version_and_suspension_are_independent(self):
        service=self.service();old=service.expires_at
        self.assertEqual(self.change(service,"renew").status_code,200)
        self.assertEqual(self.change(service,"renew").status_code,200)
        service.refresh_from_db();self.assertEqual(service.expires_at,old+timezone.timedelta(hours=720))
        response=self.client.post(f"{self.url}{service.pk}/renew/",{"expected_version":1},format="json",HTTP_IDEMPOTENCY_KEY="another-renew-key-0001")
        self.assertEqual(response.status_code,409)
        self.assertEqual(self.client.post(f"{self.url}{service.pk}/renew/",{"expected_version":service.version},format="json").status_code,400)
        self.assertEqual(self.change(service,"suspend").status_code,200)
        service.refresh_from_db();self.assertEqual(self.auth(service).status_code,403)
        self.assertEqual(self.change(service,"renew").status_code,200)
        service.refresh_from_db();self.assertTrue(service.suspended)
        self.assertEqual(self.change(service,"resume").status_code,200)

    def test_archive_requires_suspension_and_archived_service_cannot_resume(self):
        service=self.service();url=f"/api/v1/customers/{self.customer.pk}/archive/"
        self.assertEqual(self.client.post(url).status_code,400)
        self.assertEqual(self.change(service,"suspend").status_code,200)
        self.assertEqual(self.client.post(url).status_code,200)
        service.refresh_from_db();self.assertEqual(self.change(service,"resume").status_code,400)
        self.assertEqual(self.auth(service).status_code,403)

    def test_authentication_scope_expiry_and_snapshot(self):
        service=self.service()
        response=self.auth(service);self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(response.data["reply:Session-Timeout"]["value"],[3600])
        self.assertEqual(response.data["reply:Mikrotik-Rate-Limit"]["value"],["2500k/10000k"])
        self.assertFalse(response.data["reply:Mikrotik-Rate-Limit"]["do_xlat"])
        for data in [{"password":"bad"},{"packet_src_ip":"10.33.0.9"},{"service_type":"Login-User"},{"framed_protocol":"SLIP"},{"nas_port_type":"Wireless-802.11"}]:
            self.assertEqual(self.auth(service,**data).status_code,403)
        self.profile.is_active=False;self.profile.save()
        self.assertEqual(self.auth(service).status_code,200)
        PPPoEService.objects.filter(pk=service.pk).update(expires_at=timezone.now()-timezone.timedelta(seconds=1))
        self.assertEqual(self.auth(service).status_code,403)
        service.refresh_from_db();self.assertEqual(self.change(service,"resume").status_code,400)
        self.assertEqual(self.change(service,"renew").status_code,200)
        service.refresh_from_db();self.assertGreater(service.expires_at,timezone.now()+timezone.timedelta(hours=719))

    def test_auth_rejects_ambiguous_router_inactive_tenant_and_unconfigured_token(self):
        service=self.service()
        other=NASDevice.objects.create(tenant=self.other,name="Duplicate",ip_address=self.router.ip_address,nas_secret="other")
        self.assertEqual(self.auth(service).status_code,403)
        other.delete();self.tenant.is_active=False;self.tenant.save()
        self.assertEqual(self.auth(service).status_code,403)
        with override_settings(PPPOE_RADIUS_TOKEN=""):
            self.assertEqual(self.auth(service).status_code,503)
        with patch('apps.customers.radius_api.check_password') as check:
            response=self.client.post('/api/v1/radius/pppoe/decision/',{},format='json')
            self.assertEqual(response.status_code,403);check.assert_not_called()

    def test_password_replacement_invalidates_old_password_and_queues_cleanup(self):
        service=self.service();new="Replacement-pass-8830!"
        self.assertEqual(self.change(service,"password",password=new).status_code,200)
        service.refresh_from_db();self.assertEqual(service.disconnect_state,"pending")
        self.assertEqual(self.auth(service).status_code,403)
        self.assertEqual(self.auth(service,password=new).status_code,200)

    def test_plan_terms_are_immutable_and_cross_tenant_profile_is_rejected(self):
        url=f"/api/v1/pppoe-plans/{self.plan.pk}/"
        self.assertEqual(self.client.patch(url,{"duration_hours":24},format="json").status_code,400)
        self.assertEqual(self.client.patch(url,{"is_active":False},format="json").status_code,200)
        other=BandwidthProfile.objects.create(tenant=self.other,name="Other",upload_kbps=1,download_kbps=1)
        self.assertEqual(self.client.post('/api/v1/pppoe-plans/',{"name":"Bad","bandwidth_profile":other.pk,"duration_hours":24,"price":1},format="json").status_code,400)
        self.assertEqual(self.create().status_code,400)

    def test_reconciliation_lease_ack_and_cutoff_preserve_new_sessions(self):
        service=self.service();self.change(service,"password",password="Another-password-781!");service.refresh_from_db()
        def session(identity,started):
            return Radacct.objects.create(sessionid=identity,username=service.username,nasipaddress=self.router.ip_address,acctstarttime=started,nasportid="1")
        old=session("old-session",service.disconnect_before-timezone.timedelta(seconds=2))
        session("new-session",service.disconnect_before+timezone.timedelta(seconds=2))
        [(pk,token)]=claim_services(1)
        self.assertEqual(claim_services(1),[])
        with patch('apps.customers.reconciliation.RadiusService.disconnect_session',return_value=True) as disconnect:
            self.assertEqual(reconcile_service(pk,token),"acknowledged")
            self.assertEqual(disconnect.call_count,1)
            self.assertEqual(disconnect.call_args.kwargs['session_id'],'old-session')
        old.acctstoptime=timezone.now();old.save()
        [(pk,token)]=claim_services(1)
        self.assertEqual(reconcile_service(pk,token),"clear")
        self.assertEqual(Radacct.objects.filter(acctstoptime__isnull=True).count(),1)

    def test_worker_failure_is_persisted_and_resumable(self):
        service=self.service()
        with patch('apps.customers.management.commands.reconcile_pppoe_services.reconcile_service',side_effect=RuntimeError('private provider text')):
            with self.assertRaises(CommandError):call_command('reconcile_pppoe_services',limit=1)
        service.refresh_from_db();self.assertEqual(service.disconnect_state,'failed');self.assertIsNone(service.lease_token)
        call_command('reconcile_pppoe_services',limit=1)
        service.refresh_from_db();self.assertEqual(service.disconnect_state,'clear')
