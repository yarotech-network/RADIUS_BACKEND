from datetime import timedelta
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from apps.tenants.models import Tenant, TenantMembership
from apps.vouchers.models import InternetPlan
from .models import MacDevice

User = get_user_model()

class IoTDeviceTests(APITestCase):
    def test_complete_frontend_form_fields_create_and_edit(self):
        self.client.force_authenticate(self.manager)
        expiry = (timezone.now() + timedelta(days=10)).replace(microsecond=0)
        response = self.client.post(reverse("iot-device-list"), self.payload(
            mac_address="aa-bb-cc-dd-ee-10", expires_at=expiry.isoformat(), is_active=False,
        ), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        device = MacDevice.objects.get(pk=response.data["id"])
        self.assertEqual(device.mac_address, "AA:BB:CC:DD:EE:10")
        self.assertEqual(device.plan, self.plan_a)
        self.assertEqual(device.expires_at, expiry)
        self.assertFalse(device.is_active)
        self.assertEqual(response.data["plan_name"], self.plan_a.name)
        new_expiry = expiry + timedelta(days=1)
        detail = reverse("iot-device-detail", args=[device.pk])
        edited = self.client.patch(detail, {
            "expected_version": device.version, "mac_address": "AA:BB:CC:DD:EE:11", "device_name": "Edited camera",
            "plan": self.plan_a.pk, "expires_at": new_expiry.isoformat(), "is_active": True,
        }, format="json")
        self.assertEqual(edited.status_code, status.HTTP_200_OK, edited.data)
        device.refresh_from_db()
        self.assertEqual(device.device_name, "Edited camera")
        self.assertEqual(device.mac_address, "AA:BB:CC:DD:EE:11")
        self.assertEqual(device.expires_at, new_expiry)
        self.assertTrue(device.is_active)
        denied = self.client.patch(detail, {"plan": self.plan_b.pk}, format="json")
        self.assertEqual(denied.status_code, status.HTTP_400_BAD_REQUEST)
        device.refresh_from_db()
        self.assertEqual(device.plan, self.plan_a)

    def setUp(self):
        self.a = Tenant.objects.create(name="A", slug="a")
        self.b = Tenant.objects.create(name="B", slug="b")
        self.plan_a = InternetPlan.objects.create(tenant=self.a, name="A", price=1000, duration_hours=24, rate_limit="1M/1M", plan_type="iot_mac")
        self.plan_b = InternetPlan.objects.create(tenant=self.b, name="B", price=1000, duration_hours=24, rate_limit="1M/1M", plan_type="iot_mac")
        from apps.routers.models import NASDevice
        self.router = NASDevice.objects.create(tenant=self.a, name="Assigned", ip_address="192.0.2.40")
        self.manager = User.objects.create_user(username="manager", email="manager@example.com", password="StrongPass-4821")
        self.staff = User.objects.create_user(username="staff", email="staff@example.com", password="StrongPass-4821")
        TenantMembership.objects.create(user=self.manager, tenant=self.a, role="manager")
        TenantMembership.objects.create(user=self.staff, tenant=self.a, role="staff")

    def payload(self, **overrides):
        data = {"router": str(self.router.pk), "access_type": "timed", "mac_address": "aabbccddeeff", "device_name": "Camera", "plan": self.plan_a.id, "expires_at": timezone.now() + timedelta(days=1)}
        data.update(overrides)
        return data

    def test_manager_creates_normalized_tenant_bound_device(self):
        self.client.force_authenticate(self.manager)
        response = self.client.post(reverse("iot-device-list"), self.payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        device = MacDevice.objects.get()
        self.assertEqual(device.mac_address, "AA:BB:CC:DD:EE:FF")
        self.assertEqual(device.tenant, self.a)

    def test_cross_tenant_plan_and_invalid_mac_are_rejected(self):
        self.client.force_authenticate(self.manager)
        cross = self.client.post(reverse("iot-device-list"), self.payload(plan=self.plan_b.id), format="json")
        invalid = self.client.post(reverse("iot-device-list"), self.payload(mac_address="not-a-mac"), format="json")
        self.assertEqual(cross.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(MacDevice.objects.exists())

    def test_staff_cannot_create_and_list_is_tenant_scoped(self):
        own = MacDevice.objects.create(mac_address="AA:BB:CC:DD:EE:01", device_name="Own", plan=self.plan_a, tenant=self.a, expires_at=timezone.now() + timedelta(days=1))
        MacDevice.objects.create(mac_address="AA:BB:CC:DD:EE:02", device_name="Other", plan=self.plan_b, tenant=self.b, expires_at=timezone.now() + timedelta(days=1))
        self.client.force_authenticate(self.staff)
        denied = self.client.post(reverse("iot-device-list"), self.payload(), format="json")
        listed = self.client.get(reverse("iot-device-list"))
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual([item["id"] for item in listed.data["results"]], [own.id])

    def test_router_bound_permanent_access_and_tenant_validation(self):
        from apps.routers.models import NASDevice
        own = NASDevice.objects.create(tenant=self.a, name="Lab", ip_address="192.0.2.10")
        other = NASDevice.objects.create(tenant=self.b, name="Other", ip_address="192.0.2.11")
        self.client.force_authenticate(self.manager)
        response = self.client.post(reverse("iot-device-list"), self.payload(
            router=str(own.pk), access_type="permanent", vlan_id=42, description="Lobby camera", expires_at=None,
        ), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertIsNone(response.data["expires_at"])
        self.assertEqual(response.data["router_name"], "Lab")
        self.assertEqual(response.data["vlan_id"], 42)
        detail = reverse("iot-device-detail", args=[response.data["id"]])
        for payload in [{"router": str(other.pk)}, {"vlan_id": 4095}, {"access_type": "timed", "expires_at": None}]:
            rejected = self.client.patch(detail, {**payload, "expected_version": 1}, format="json")
            self.assertEqual(rejected.status_code, 400, rejected.data)
        device = MacDevice.objects.get(pk=response.data["id"])
        self.assertEqual(device.router_id, own.pk)
        self.assertEqual(device.access_type, "permanent")
        filtered = self.client.get(reverse("iot-device-list"), {"router": str(other.pk)})
        self.assertEqual(filtered.data["count"], 0)


from rest_framework.test import APITransactionTestCase
from django.db import connection
from apps.vouchers.models import Radacct
from apps.routers.models import NASDevice
from .accounting import device_accounting


class DeviceAccountingTests(APITransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.created_accounting = Radacct._meta.db_table not in connection.introspection.table_names()
        if cls.created_accounting:
            with connection.schema_editor() as editor:
                editor.create_model(Radacct)

    @classmethod
    def tearDownClass(cls):
        if cls.created_accounting:
            with connection.schema_editor() as editor:
                editor.delete_model(Radacct)
        super().tearDownClass()

    def test_usage_matches_normalized_mac_and_assigned_tenant_router(self):
        Radacct.objects.all().delete()
        tenant = Tenant.objects.create(name="Lab", slug="lab")
        other = Tenant.objects.create(name="Other", slug="other")
        plan = InternetPlan.objects.create(tenant=tenant, name="IoT", price=1000, duration_hours=24)
        router = NASDevice.objects.create(tenant=tenant, name="Lab", ip_address="192.0.2.20")
        NASDevice.objects.create(tenant=other, name="Other", ip_address="192.0.2.21")
        device = MacDevice.objects.create(tenant=tenant, plan=plan, router=router, device_name="Camera", mac_address="AA:BB:CC:DD:EE:FF", access_type="permanent")
        now = timezone.now()
        for username, ip, stopped, incoming in [
            ("aa-bb-cc-dd-ee-ff", "192.0.2.20", None, 100),
            ("AABB.CCDD.EEFF", "192.0.2.20", now, 200),
            ("AABBCCDDEEFF", "192.0.2.21", None, 9999),
            ("112233445566", "192.0.2.20", None, 9999),
        ]:
            Radacct.objects.create(sessionid=username, username=username, nasipaddress=ip,
                acctstarttime=now, acctstoptime=stopped, acctinputoctets=incoming, acctoutputoctets=10)
        data = device_accounting([device], tenant)[device.pk]
        self.assertTrue(data["available"])
        self.assertEqual(data["session_count"], 2)
        self.assertEqual(data["open_sessions"], 1)
        self.assertEqual(data["bytes_total"], 320)
        device.router = None
        self.assertIsNone(device_accounting([device], tenant)[device.pk]["bytes_total"])
        Radacct.objects.all().delete()
