from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.routers.secret_store import secret_store
from apps.tenants.models import Tenant, TenantMembership
from .models import TenantWhatsAppRoute
from .services import generate_route_url, resolve_route_token


User = get_user_model()


class WhatsAppRoutingTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Tenant A", slug="tenant-a")
        self.manager = User.objects.create_user(username="manager", email="manager@example.com", password="StrongPass-4821")
        self.staff = User.objects.create_user(username="staff", email="staff@example.com", password="StrongPass-4821")
        TenantMembership.objects.create(user=self.manager, tenant=self.tenant, role="manager")
        TenantMembership.objects.create(user=self.staff, tenant=self.tenant, role="staff")

    def test_manager_creates_route_with_encrypted_hidden_secrets(self):
        self.client.force_authenticate(self.manager)
        response = self.client.post(reverse("whatsapp-route-list"), {
            "phone_number_id": "2348012345678", "access_token_encrypted": "plain-token"
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        route = TenantWhatsAppRoute.objects.get(tenant=self.tenant)
        self.assertEqual(secret_store.decrypt(route.access_token_encrypted), "plain-token")
        self.assertNotIn("access_token_encrypted", response.data)
        self.assertNotIn("webhook_token", response.data)

    def test_staff_cannot_create_route(self):
        self.client.force_authenticate(self.staff)
        response = self.client.post(reverse("whatsapp-route-list"), {
            "phone_number_id": "2348012345678", "access_token_encrypted": "token"
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_generated_url_uses_configured_phone_and_resolves_tenant(self):
        TenantWhatsAppRoute.objects.create(tenant=self.tenant, phone_number_id="2348012345678", access_token_encrypted="enc", webhook_token="route-secret")
        url = generate_route_url(self.tenant)
        token = url.split("?text=", 1)[1]
        self.assertIn("wa.me/2348012345678", url)
        self.assertEqual(resolve_route_token(token), self.tenant)
        self.assertIsNone(resolve_route_token("malformed"))
