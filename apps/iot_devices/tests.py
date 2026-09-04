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
    def setUp(self):
        self.a = Tenant.objects.create(name="A", slug="a")
        self.b = Tenant.objects.create(name="B", slug="b")
        self.plan_a = InternetPlan.objects.create(tenant=self.a, name="A", price=1000, duration_hours=24, rate_limit="1M/1M")
        self.plan_b = InternetPlan.objects.create(tenant=self.b, name="B", price=1000, duration_hours=24, rate_limit="1M/1M")
        self.manager = User.objects.create_user(username="manager", email="manager@example.com", password="StrongPass-4821")
        self.staff = User.objects.create_user(username="staff", email="staff@example.com", password="StrongPass-4821")
        TenantMembership.objects.create(user=self.manager, tenant=self.a, role="manager")
        TenantMembership.objects.create(user=self.staff, tenant=self.a, role="staff")

    def payload(self, **overrides):
        data = {"mac_address": "aabbccddeeff", "device_name": "Camera", "plan": self.plan_a.id, "expires_at": timezone.now() + timedelta(days=1)}
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
