from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework.exceptions import ValidationError
from apps.tenants.models import Tenant, TenantMembership
from apps.subscriptions.test_support import grant_test_subscription
from apps.vouchers.models import PaymentTransaction
from .models import SharedWhatsAppEndpoint, TenantWhatsAppEntryRoute, WhatsAppRoutedSender
from .shared_routing import (bind_sender, resolve_sender, reserve_purchase, release_purchase,
    customer_hash, hash_key_fingerprint, token_for_entry, resolve_entry)


@override_settings(WHATSAPP_TENANT_ROUTING_SIGNING_KEY='s'*32, WHATSAPP_SENDER_HASH_KEY='h'*32)
class SharedRoutingTests(APITestCase):
    def setUp(self):
        self.a = Tenant.objects.create(name='A', slug='shared-a')
        self.b = Tenant.objects.create(name='B', slug='shared-b')
        for tenant in (self.a, self.b):
            grant_test_subscription(tenant)
        self.ra = TenantWhatsAppEntryRoute.objects.create(tenant=self.a)
        self.rb = TenantWhatsAppEntryRoute.objects.create(tenant=self.b)
        self.endpoint = SharedWhatsAppEndpoint.objects.create(phone_number_id='12345',
            display_number='+2348012345678', access_token_encrypted='test-only',
            is_active=True, verified_at=timezone.now(), hash_key_fingerprint=hash_key_fingerprint())
        self.args = dict(endpoint_id=1, endpoint_version=self.endpoint.version, sender='2348012345678')
        self.manager = get_user_model().objects.create_user(username='shared-manager', email='shared@example.com')
        TenantMembership.objects.create(user=self.manager, tenant=self.a, role='manager')

    def bind(self, route=None):
        return bind_sender(**self.args, token=token_for_entry(route or self.ra))

    def test_signed_start_format_tampering_and_revocation(self):
        token = token_for_entry(self.ra)
        self.assertRegex(token, r'^[A-Za-z0-9_-]{43}\.[A-Za-z0-9_-]{43}$')
        self.assertEqual(resolve_entry(token), self.ra)
        self.assertIsNone(resolve_entry(('A' if token[0] != 'A' else 'B')+token[1:]))
        self.ra.revoked_at = timezone.now()
        self.ra.save()
        self.assertIsNone(resolve_entry(token))

    def test_sender_is_hashed_normalized_and_stale_switch_is_rejected(self):
        binding = self.bind()
        self.assertEqual(binding.customer_hash, customer_hash('+'+self.args['sender']))
        self.assertNotIn(self.args['sender'], binding.customer_hash)
        self.assertEqual(self.bind().pk, binding.pk)
        self.assertIsNone(resolve_sender(**self.args, expected_version=None))
        switched = self.bind(self.rb)
        self.assertNotEqual(binding.version, switched.version)
        self.assertIsNone(resolve_sender(**self.args, expected_version=binding.version))
        self.assertEqual(resolve_sender(**self.args, expected_version=switched.version).route_id, self.rb.pk)

    def test_unverified_endpoint_and_changed_hash_key_fail_closed(self):
        self.endpoint.verified_at = None
        self.endpoint.save()
        with self.assertRaises(ValidationError):
            self.bind()
        self.endpoint.verified_at = timezone.now()
        self.endpoint.save()
        with override_settings(WHATSAPP_SENDER_HASH_KEY='different-key-value-that-is-long-enough'):
            with self.assertRaises(ValidationError):
                self.bind()

    def test_expiry_and_route_rotation_invalidate_queued_messages(self):
        binding = self.bind()
        WhatsAppRoutedSender.objects.filter(pk=binding.pk).update(expires_at=timezone.now()-timedelta(seconds=1))
        self.assertIsNone(resolve_sender(**self.args, expected_version=binding.version))
        fresh = self.bind()
        self.assertNotEqual(binding.version, fresh.version)
        self.ra.selector = 'a'*43
        self.ra.save()
        self.assertIsNone(resolve_sender(**self.args, expected_version=fresh.version))

    def test_pending_hold_survives_binding_expiry_and_reservation_is_idempotent(self):
        binding = self.bind()
        args = dict(**self.args, binding_version=binding.version, reference='purchase-1')
        hold = reserve_purchase(**args)
        self.assertEqual(reserve_purchase(**args).pk, hold.pk)
        with self.assertRaises(ValidationError):
            reserve_purchase(**{**args, 'reference': 'purchase-2'})
        WhatsAppRoutedSender.objects.filter(pk=binding.pk).update(expires_at=timezone.now()-timedelta(seconds=1))
        with self.assertRaises(ValidationError):
            self.bind(self.rb)
        self.assertEqual(self.bind().route_id, self.ra.pk)

    def test_only_verified_terminal_payment_releases_hold(self):
        binding = self.bind()
        hold = reserve_purchase(**self.args, binding_version=binding.version, reference='payment-1')
        payment = PaymentTransaction.objects.create(tenant=self.a, reference=hold.reference, amount=100, customer_email='test@example.com')
        for status, verified in [('pending', None), ('failed', None), ('success', timezone.now())]:
            payment.status, payment.verified_at = status, verified
            payment.save()
            with self.assertRaises(ValidationError):
                release_purchase(hold.reference)
            with self.assertRaises(ValidationError):
                self.bind(self.rb)
        payment.status = 'failed'
        payment.save()
        self.assertIsNotNone(release_purchase(hold.reference).released_at)
        self.assertEqual(self.bind(self.rb).route_id, self.rb.pk)

    def test_other_tenant_payment_cannot_release_hold(self):
        binding = self.bind()
        hold = reserve_purchase(**self.args, binding_version=binding.version, reference='wrong-tenant')
        PaymentTransaction.objects.create(tenant=self.b, reference=hold.reference, amount=100,
            status='failed', verified_at=timezone.now(), customer_email='test@example.com')
        with self.assertRaises(ValidationError):
            release_purchase(hold.reference)

    def test_fulfilled_verified_payment_releases_once(self):
        from apps.vouchers.models import InternetPlan, Voucher
        binding = self.bind()
        hold = reserve_purchase(**self.args, binding_version=binding.version, reference='fulfilled')
        plan = InternetPlan.objects.create(tenant=self.a, name='Day', price=100, duration_hours=24)
        voucher = Voucher.objects.create(tenant=self.a, plan=plan, username='TESTSHARED', password='test')
        PaymentTransaction.objects.create(tenant=self.a, reference=hold.reference, amount=100,
            status='success', verified_at=timezone.now(), voucher=voucher, customer_email='test@example.com')
        released = release_purchase(hold.reference)
        self.assertIsNotNone(released.released_at)
        self.assertEqual(release_purchase(hold.reference).released_at, released.released_at)
        self.assertEqual(self.bind(self.rb).route_id, self.rb.pk)

    def test_expired_tenant_cannot_bind_or_resolve_but_can_reconcile(self):
        from apps.subscriptions.models import TenantSubscription
        binding = self.bind()
        hold = reserve_purchase(**self.args, binding_version=binding.version, reference='expired-tenant')
        TenantSubscription.objects.filter(tenant=self.a).update(expires_at=timezone.now()-timedelta(days=1))
        self.assertIsNone(resolve_sender(**self.args, expected_version=binding.version))
        with self.assertRaises(ValidationError):
            self.bind()
        PaymentTransaction.objects.create(tenant=self.a, reference=hold.reference, amount=100,
            status='failed', verified_at=timezone.now(), customer_email='test@example.com')
        self.assertIsNotNone(release_purchase(hold.reference).released_at)

    def test_shared_number_replacement_is_blocked_by_pending_purchase(self):
        binding = self.bind()
        reserve_purchase(**self.args, binding_version=binding.version, reference='pending-number-change')
        admin = get_user_model().objects.create_user(username='endpoint-admin', email='endpoint-admin@example.com', is_platform_admin=True)
        self.client.force_authenticate(admin)
        response = self.client.put(reverse('whatsapp-shared-endpoint'), {
            'expected_version': str(self.endpoint.version), 'phone_number_id': '98765',
            'display_number': '+2348012345678', 'is_active': True}, format='json')
        self.assertEqual(response.status_code, 400)
        self.endpoint.refresh_from_db()
        self.assertEqual(self.endpoint.phone_number_id, '12345')

    def test_manager_only_changes_own_link_with_stale_write_protection(self):
        self.client.force_authenticate(self.manager)
        url = reverse('whatsapp-entry-route')
        before = self.client.get(url)
        self.assertEqual(before.status_code, 200)
        self.assertFalse(before.data['sales_available'])
        self.assertNotIn('access_token', str(before.data))
        old_token = token_for_entry(self.ra)
        payload = {'action': 'rotate', 'expected_version': before.data['version']}
        self.assertEqual(self.client.post(url, payload, format='json').status_code, 200)
        self.assertEqual(self.client.post(url, payload, format='json').status_code, 409)
        self.assertIsNone(resolve_entry(old_token))
        self.rb.refresh_from_db()
        self.assertIsNone(self.rb.rotated_at)
        self.assertEqual(self.client.get(reverse('whatsapp-shared-endpoint')).status_code, 403)

    def test_platform_save_hides_token_clears_verification_and_blocks_stale_retry(self):
        admin = get_user_model().objects.create_user(username='shared-admin', email='admin-shared@example.com', is_platform_admin=True)
        self.client.force_authenticate(admin)
        url = reverse('whatsapp-shared-endpoint')
        payload = {'expected_version': str(self.endpoint.version), 'phone_number_id': '12345',
            'display_number': '+2348012345678', 'is_active': True, 'access_token': 'private-test-token', 'provider_verified': True}
        response = self.client.put(url, payload, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data['token_saved'])
        self.assertFalse(response.data['provider_verified'])
        self.assertNotIn('private-test-token', str(response.data))
        self.assertEqual(self.client.put(url, payload, format='json').status_code, 409)

    def test_get_does_not_create_entry_and_staff_is_denied(self):
        self.ra.delete()
        self.client.force_authenticate(self.manager)
        self.assertFalse(self.client.get(reverse('whatsapp-entry-route')).data['exists'])
        self.assertFalse(TenantWhatsAppEntryRoute.objects.filter(tenant=self.a).exists())
        TenantMembership.objects.filter(user=self.manager).update(role='staff')
        self.client.force_authenticate(get_user_model().objects.get(pk=self.manager.pk))
        self.assertEqual(self.client.post(reverse('whatsapp-entry-route'), {'action':'create', 'expected_version': None}, format='json').status_code, 403)
