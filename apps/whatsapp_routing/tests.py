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
        from apps.subscriptions.test_support import grant_test_subscription
        grant_test_subscription(self.tenant)
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
        TenantWhatsAppRoute.objects.create(tenant=self.tenant, phone_number_id="99887766", display_number='+2348012345678', access_token_encrypted="enc", webhook_token="route-secret")
        url = generate_route_url(self.tenant)
        token = url.split("?text=", 1)[1]
        self.assertIn("wa.me/2348012345678", url)
        self.assertEqual(resolve_route_token(token), self.tenant)
        self.assertIsNone(resolve_route_token("malformed"))

    def test_missing_display_number_never_uses_provider_id_as_customer_number(self):
        TenantWhatsAppRoute.objects.create(tenant=self.tenant, phone_number_id='99887766', access_token_encrypted='enc', webhook_token='secret')
        self.assertIsNone(generate_route_url(self.tenant))

    def test_patch_preserves_token_and_does_not_expose_it(self):
        self.client.force_authenticate(self.manager)
        result = self.client.post(reverse('whatsapp-route-list'), {'phone_number_id': '12345', 'access_token_encrypted': 'private-test-token'}, format='json')
        self.assertEqual(result.status_code, 201, result.data)
        route = TenantWhatsAppRoute.objects.get(pk=result.data['id'])
        original = route.access_token_encrypted
        response = self.client.patch(reverse('whatsapp-route-detail', args=[route.pk]), {'display_number': '+2348012345678'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data['token_saved'])
        self.assertNotIn('access_token_encrypted', response.data)
        self.assertNotIn('webhook_token', response.data)
        self.assertNotIn('private-test-token', str(response.data))
        route.refresh_from_db()
        self.assertEqual(route.access_token_encrypted, original)

    def test_duplicate_connection_returns_validation_error(self):
        self.client.force_authenticate(self.manager)
        payload = {'phone_number_id': '12345', 'access_token_encrypted': 'token'}
        self.assertEqual(self.client.post(reverse('whatsapp-route-list'), payload, format='json').status_code, 201)
        self.assertEqual(self.client.post(reverse('whatsapp-route-list'), payload, format='json').status_code, 400)
        self.assertEqual(TenantWhatsAppRoute.objects.count(), 1)

    def test_invalid_numbers_and_blank_token_do_not_create_route(self):
        self.client.force_authenticate(self.manager)
        for fields in [{'display_number': '123&text=bad'}, {'phone_number_id': 'not-an-id'}, {'access_token_encrypted': '   '}]:
            payload = {'phone_number_id': '12345', 'access_token_encrypted': 'token', **fields}
            self.assertEqual(self.client.post(reverse('whatsapp-route-list'), payload, format='json').status_code, 400)
        self.assertFalse(TenantWhatsAppRoute.objects.exists())

    def test_cross_tenant_route_not_visible(self):
        other = Tenant.objects.create(name='Other', slug='other')
        route = TenantWhatsAppRoute.objects.create(tenant=other, phone_number_id='1234', access_token_encrypted='enc', webhook_token='other-secret')
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.client.get(reverse('whatsapp-route-detail', args=[route.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('whatsapp-route-list')).data['count'], 0)

    def test_expired_subscription_cannot_resolve_or_create_route(self):
        from django.utils import timezone
        from apps.subscriptions.models import TenantSubscription
        route = TenantWhatsAppRoute.objects.create(tenant=self.tenant, phone_number_id='1234', display_number='+2348012345678', access_token_encrypted='enc', webhook_token='secret')
        token = route.generate_route_token()
        TenantSubscription.objects.filter(tenant=self.tenant).update(expires_at=timezone.now())
        self.assertIsNone(resolve_route_token(token))
        self.assertIsNone(generate_route_url(self.tenant))
