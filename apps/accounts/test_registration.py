import re
from contextlib import redirect_stdout
from io import StringIO
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.db import connections
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from apps.tenants.models import Tenant, TenantMembership
from .models import RegistrationEmailChallenge
from .registration import create_workspace, RegistrationError

BASE = '/api/v1/auth/registration/'

class RegistrationSetup:
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.email = 'owner@example.com'

    def send(self):
        response = self.client.post(BASE + 'email/', {'email': self.email})
        self.assertEqual(response.status_code, 200)
        return re.search(r'code is: (\d{6})', mail.outbox[-1].body).group(1)

    def proof(self):
        response = self.client.post(BASE + 'email/verify/', {'email': self.email, 'code': self.send()})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'no-store')
        return response.data['registration_token']

    def details(self, token):
        return {'registration_token': token, 'email': self.email, 'username': 'networkowner', 'first_name': 'Ada', 'last_name': 'Lovelace', 'phone': '08012345678', 'tenant_name': 'My Network', 'workspace_id': 'my-network', 'password': 'RobustNetwork-6382!', 'password_confirm': 'RobustNetwork-6382!'}


@override_settings(RESEND_API_KEY='', EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class RegistrationTests(RegistrationSetup, TestCase):
    def test_email_first_then_atomic_workspace_and_sign_in(self):
        token = self.proof()
        self.assertEqual(get_user_model().objects.count(), 0)
        self.assertEqual(Tenant.objects.count(), 0)
        record = RegistrationEmailChallenge.objects.get()
        self.assertNotIn(token.split(':')[1], record.token_hash)
        response = self.client.post(BASE, self.details(token))
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['workspace']['slug'], 'my-network')
        self.assertNotIn('access', response.data)
        user = get_user_model().objects.get()
        self.assertIsNotNone(user.email_verified_at)
        self.assertEqual(user.first_name, 'Ada')
        self.assertEqual(user.membership.role, 'owner')
        subscription = user.membership.tenant.subscription
        self.assertEqual(subscription.status, 'trial')
        self.assertTrue(subscription.is_trial)
        self.assertEqual(subscription.expires_at - subscription.started_at, timedelta(days=15))
        from apps.subscriptions.entitlements import entitlement_terms
        terms = entitlement_terms(user.membership.tenant)
        self.assertEqual(terms['max_routers'], 1)
        self.assertEqual(terms['daily_voucher_print_limit'], 50)
        self.assertFalse(terms['whatsapp_enabled'])
        self.assertEqual(self.client.post('/api/v1/auth/login/', {'username': user.username, 'password': 'RobustNetwork-6382!'}).status_code, 200)
        self.assertIn(self.client.post(BASE, self.details(token)).status_code, [400, 409])
        self.assertEqual(Tenant.objects.count(), 1)

    def test_wrong_code_attempts_are_persisted_and_cannot_be_bypassed(self):
        code = self.send()
        wrong = '000000' if code != '000000' else '111111'
        for _ in range(5):
            self.assertEqual(self.client.post(BASE+'email/verify/', {'email': self.email, 'code': wrong}).status_code, 400)
        self.assertEqual(RegistrationEmailChallenge.objects.get().attempts, 5)
        self.assertEqual(self.client.post(BASE+'email/verify/', {'email': self.email, 'code': code}).status_code, 400)
        self.assertFalse(get_user_model().objects.exists())

    def test_expired_code_and_resend_cooldown(self):
        code = self.send()
        self.client.post(BASE+'email/', {'email': self.email})
        self.assertEqual(len(mail.outbox), 1)
        RegistrationEmailChallenge.objects.update(expires_at=timezone.now()-timedelta(seconds=1))
        self.assertEqual(self.client.post(BASE+'email/verify/', {'email': self.email, 'code': code}).status_code, 400)

    def test_resend_replaces_previous_code(self):
        code = self.send()
        RegistrationEmailChallenge.objects.update(sent_at=timezone.now()-timedelta(minutes=2))
        with patch('apps.accounts.registration.secrets.randbelow', return_value=123456 if code != '123456' else 234567):
            new_code = self.send()
        self.assertNotEqual(new_code, code)
        self.assertEqual(self.client.post(BASE+'email/verify/', {'email': self.email, 'code': code}).status_code, 400)
        self.assertEqual(self.client.post(BASE+'email/verify/', {'email': self.email, 'code': new_code}).status_code, 200)

    def test_missing_forged_expired_or_different_email_proof_cannot_create(self):
        token = self.proof()
        for changed in [{'registration_token': ''}, {'registration_token': token+'bad'}, {'email': 'other@example.com'}]:
            self.assertEqual(self.client.post(BASE, {**self.details(token), **changed}).status_code, 400)
        RegistrationEmailChallenge.objects.update(expires_at=timezone.now()-timedelta(seconds=1))
        response = self.client.post(BASE, self.details(token))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['code'], 'verification_required')
        self.assertEqual(Tenant.objects.count(), 0)

    def test_workspace_id_conflict_can_be_corrected_with_same_proof(self):
        token = self.proof()
        Tenant.objects.create(name='Existing', slug='my-network')
        response = self.client.post(BASE, self.details(token))
        self.assertEqual(response.status_code, 400)
        self.assertIn('workspace_id', response.data)
        response = self.client.post(BASE, {**self.details(token), 'workspace_id': 'my-custom-network'})
        self.assertEqual(response.status_code, 201, response.data)

    def test_creation_failure_rolls_back_user_and_proof_consumption(self):
        token = self.proof()
        with patch.object(TenantMembership.objects, 'create', side_effect=RuntimeError('injected')):
            with self.assertRaises(RuntimeError): create_workspace(self.details(token))
        self.assertFalse(get_user_model().objects.exists())
        self.assertFalse(Tenant.objects.exists())
        self.assertIsNone(RegistrationEmailChallenge.objects.get().consumed_at)
        self.assertEqual(self.client.post(BASE, self.details(token)).status_code, 201)

    def test_trial_failure_rolls_back_workspace_and_keeps_registration_retryable(self):
        token = self.proof()
        with patch('apps.subscriptions.trials.SubscriptionPeriod.objects.create', side_effect=RuntimeError('injected')):
            with self.assertRaises(RuntimeError):
                create_workspace(self.details(token))
        from apps.subscriptions.models import TenantSubscription, SubscriptionPlan
        self.assertFalse(Tenant.objects.exists())
        self.assertFalse(get_user_model().objects.exists())
        self.assertFalse(TenantSubscription.objects.exists())
        self.assertFalse(SubscriptionPlan.objects.exists())
        self.assertIsNone(RegistrationEmailChallenge.objects.get().consumed_at)
        self.assertEqual(self.client.post(BASE, self.details(token)).status_code, 201)

    def test_delivery_failure_is_visible_and_retryable(self):
        with patch('apps.accounts.registration.send_verification_email', return_value=False):
            response = self.client.post(BASE+'email/', {'email': self.email})
        self.assertEqual(response.status_code, 503)
        self.assertIsNone(RegistrationEmailChallenge.objects.get().sent_at)
        self.assertFalse(get_user_model().objects.exists())
        self.send()

    @override_settings(REGISTRATION_EMAIL_BACKEND='django.core.mail.backends.console.EmailBackend')
    def test_console_explains_existing_email_and_cooldown(self):
        get_user_model().objects.create_user(username='existing', email=self.email)
        output = StringIO()
        with redirect_stdout(output):
            self.client.post(BASE+'email/', {'email': self.email})
        self.assertIn('already belongs to an account', output.getvalue())
        self.email = 'unused@example.com'
        output = StringIO()
        with redirect_stdout(output):
            self.client.post(BASE+'email/', {'email': self.email})
            self.client.post(BASE+'email/', {'email': self.email})
        self.assertIn('[Registration OTP] Code:', output.getvalue())
        self.assertIn('last 60 seconds', output.getvalue())

    def test_existing_email_does_not_create_challenge_or_send_mail(self):
        get_user_model().objects.create_user(username='existing', email=self.email)
        response = self.client.post(BASE+'email/', {'email': self.email.upper()})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(RegistrationEmailChallenge.objects.exists())
        self.assertEqual(len(mail.outbox), 0)


@override_settings(RESEND_API_KEY='', EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class ConcurrentRegistrationTests(RegistrationSetup, TransactionTestCase):
    def test_same_proof_creates_exactly_one_workspace_concurrently(self):
        token = self.proof()
        barrier = Barrier(2)
        def submit():
            connections.close_all()
            try:
                barrier.wait(timeout=10)
                try:
                    create_workspace(self.details(token))
                    return 'created'
                except RegistrationError:
                    return 'rejected'
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: submit(), range(2)))
        self.assertCountEqual(results, ['created', 'rejected'])
        self.assertEqual(get_user_model().objects.count(), 1)
        self.assertEqual(Tenant.objects.count(), 1)
