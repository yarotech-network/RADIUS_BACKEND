from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core import signing
from django.db import IntegrityError, transaction
from rest_framework.test import APITestCase
from apps.tenants.models import Tenant, TenantMembership
from apps.core.models import AuditEvent
from .models import Customer


class CustomerTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="A", slug="customer-a")
        self.other = Tenant.objects.create(name="B", slug="customer-b")
        User = get_user_model()
        self.manager = User.objects.create_user(username="customer-manager", email="customer-manager@example.com")
        self.staff = User.objects.create_user(username="customer-staff", email="customer-staff@example.com")
        self.outsider = User.objects.create_user(username="customer-outsider", email="customer-outsider@example.com")
        TenantMembership.objects.create(tenant=self.tenant, user=self.manager, role="manager")
        TenantMembership.objects.create(tenant=self.tenant, user=self.staff, role="staff")
        self.client.force_authenticate(self.manager)
        self.url = "/api/v1/customers/"
        self.customer = Customer.objects.create(tenant=self.tenant, reference="C-001", name="Ada")
        self.detail = f"{self.url}{self.customer.pk}/"

    def preview(self, text):
        response = self.client.post(self.url+"import-preview/", {"csv":text}, format="json")
        self.assertEqual(response.status_code,200,response.data)
        return response.data["preview_token"]

    def confirm(self, text, token, **headers):
        return self.client.post(self.url+"import-confirm/", {"csv":text,"preview_token":token}, format="json", **headers)

    def test_create_replay_and_duplicate_reference(self):
        payload={"name":"New customer","reference":"c-002","email":"new@example.com"}
        headers={"HTTP_IDEMPOTENCY_KEY":"customer-create-00001"}
        first=self.client.post(self.url,payload,format="json",**headers)
        second=self.client.post(self.url,payload,format="json",**headers)
        self.assertEqual(first.status_code,201,first.data)
        self.assertEqual(first.data,second.data)
        self.assertEqual(first.data["reference"],"C-002")
        self.assertEqual(Customer.objects.filter(reference="C-002").count(),1)
        self.assertEqual(self.client.post(self.url,payload,format="json").status_code,400)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Customer.objects.create(tenant=self.tenant, reference="c-002", name="Duplicate")
        Customer.objects.create(tenant=self.other, reference="c-002", name="Other tenant")

    def test_scope_and_role_permissions(self):
        other=Customer.objects.create(tenant=self.other,reference="OTHER",name="Hidden")
        self.assertEqual(self.client.get(self.url).data["count"],1)
        for method,tail in [("get",""),("patch",""),("post","archive/"),("post","restore/")]:
            response=getattr(self.client,method)(f"{self.url}{other.pk}/{tail}",{},format="json")
            self.assertEqual(response.status_code,404)
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get(self.detail).status_code,200)
        for url in [self.url,self.detail+"archive/",self.detail+"restore/",self.url+"import-preview/",self.url+"import-confirm/"]:
            self.assertEqual(self.client.post(url,{},format="json").status_code,403)
        self.assertEqual(self.client.patch(self.detail,{"name":"Bad"},format="json").status_code,403)
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.get(self.url).status_code,403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url).status_code,401)

    def test_archive_restore_retention_filters_and_edit(self):
        self.assertEqual(self.client.delete(self.detail).status_code,405)
        for _ in range(2):
            self.assertEqual(self.client.post(self.detail+"archive/").status_code,200)
        self.assertEqual(AuditEvent.objects.filter(action="customer.archived").count(),1)
        self.assertEqual(self.client.get(self.url,{"status":"current"}).data["count"],0)
        self.assertEqual(self.client.get(self.url,{"status":"archived"}).data["count"],1)
        self.assertEqual(self.client.patch(self.detail,{"name":"Blocked"},format="json").status_code,400)
        self.assertEqual(self.client.post(self.detail+"restore/").status_code,200)
        self.assertEqual(self.client.patch(self.detail,{"name":"Updated"},format="json").status_code,200)
        self.assertEqual(self.client.patch(self.detail,{"reference":"NEW"},format="json").status_code,400)
        self.assertEqual(self.client.get(self.url,{"search":"Updated"}).data["count"],1)
        self.assertEqual(self.client.get(self.url,{"status":"online"}).status_code,400)

    def test_unknown_or_readonly_inputs_are_rejected(self):
        for key,value in [("tenant",self.other.pk),("archived_at",None),("password","secret"),("service_type","pppoe")]:
            response=self.client.post(self.url,{"name":"Bad","reference":"C-003",key:value},format="json")
            self.assertEqual(response.status_code,400,response.data)
        self.assertEqual(Customer.objects.count(),1)

    def test_import_preview_has_no_writes_and_confirm_is_atomic_replayable(self):
        text='reference,name,email,address\nC-002,"First, customer",first@example.com,"Road, 2"\nC-003,Second,,\n'
        token=self.preview(text)
        self.assertEqual(Customer.objects.count(),1)
        response=self.confirm(text,token,HTTP_IDEMPOTENCY_KEY="customer-import-0001")
        self.assertEqual(response.status_code,201,response.data)
        self.assertEqual(response.data,{"count":2})
        self.assertEqual(self.confirm(text,token,HTTP_IDEMPOTENCY_KEY="customer-import-0001").data,{"count":2})
        self.assertEqual(Customer.objects.count(),3)
        self.assertEqual(AuditEvent.objects.filter(action="customer.imported").count(),2)
        self.assertTrue(all(event.details=={} for event in AuditEvent.objects.filter(action="customer.imported")))

    def test_import_validation_and_duplicate_recheck(self):
        for text in ['name\nName','reference,name,name\nA,B,C','reference,name\nC-002,A\nc-002,B','reference,name,email\nC-002,Valid,ok@example.com\nC-003,Invalid,bad','reference,name\nC-001,Duplicate','reference,name\n','reference,name\nA,B,extra','reference,name\n'+''.join(f'C-{i},Name\n' for i in range(201))]:
            self.assertEqual(self.client.post(self.url+"import-preview/",{"csv":text},format="json").status_code,400)
        text='reference,name\nC-002,First\nC-003,Second'
        token=self.preview(text)
        Customer.objects.create(tenant=self.tenant,reference="C-003",name="Created after preview")
        self.assertEqual(self.confirm(text,token).status_code,400)
        self.assertFalse(Customer.objects.filter(reference="C-002").exists())
        huge='reference,name\n'+('x'*262145)
        self.assertEqual(self.client.post(self.url+"import-preview/",{"csv":huge},format="json").status_code,400)

    def test_preview_token_bound_to_content_actor_and_tenant_and_expires(self):
        text='reference,name\nC-002,New'
        token=self.preview(text)
        self.assertEqual(self.confirm(text+' changed',token).status_code,400)
        self.assertEqual(self.confirm(text,token+'tampered').status_code,400)
        self.assertEqual(self.confirm(text,'').status_code,400)
        self.client.force_authenticate(self.staff)
        TenantMembership.objects.filter(user=self.staff).update(role="manager")
        self.staff.refresh_from_db()
        self.assertEqual(self.confirm(text,token).status_code,400)
        self.client.force_authenticate(self.manager)
        with patch('apps.customers.imports.signing.loads', side_effect=signing.SignatureExpired()):
            self.assertEqual(self.confirm(text,token).status_code,400)
        self.assertEqual(Customer.objects.count(),1)

    def test_import_rolls_back_on_second_audit_failure(self):
        text='reference,name\nC-002,First\nC-003,Second'
        token=self.preview(text)
        with patch('apps.customers.views.audit',side_effect=[None,IntegrityError('failed')]):
            self.assertEqual(self.confirm(text,token).status_code,409)
        self.assertEqual(Customer.objects.count(),1)
