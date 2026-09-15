import re
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APITestCase

from apps.accounts.models import EmailChangeRequest
from apps.tenants.models import Tenant, TenantMembership

User = get_user_model()


@override_settings(RESEND_API_KEY='', REGISTRATION_EMAIL_BACKEND='',
                   EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class IdentityCompatibilityTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.tenant = Tenant.objects.create(name='Home', slug='home')
        self.other = Tenant.objects.create(name='Other', slug='other')
        self.user = User.objects.create_user('owner', 'owner@example.test', 'Strong-fixture-472!')
        self.member = TenantMembership.objects.create(user=self.user, tenant=self.tenant, role='owner')

    def login(self, identifier):
        return self.client.post('/api/v1/auth/login/', {'username': identifier, 'password': 'Strong-fixture-472!'}, format='json')

    def test_email_and_username_login_preserve_password_hash(self):
        password_hash = self.user.password
        self.assertEqual(self.login('OWNER@EXAMPLE.TEST').status_code, 200)
        self.assertEqual(self.login('owner').status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.password, password_hash)

    def test_ambiguous_username_email_is_rejected(self):
        User.objects.create_user('owner@example.test', 'different@example.test', 'Strong-fixture-472!')
        self.assertEqual(self.login('owner@example.test').status_code, 401)

    def test_inactive_membership_blocks_tenant_access_and_exposes_no_role(self):
        self.member.is_active = False
        self.member.save()
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get('/api/v1/plans/').status_code, 403)
        me = self.client.get('/api/v1/auth/user/').data
        self.assertFalse(me['membership_active'])
        self.assertIsNone(me['workspace_role'])

    def test_combined_account_uses_separate_server_contexts(self):
        self.user.is_platform_admin = True
        self.user.save()
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get('/api/v1/tenants/').data['count'], 2)
        self.assertEqual(self.client.get('/api/v1/plans/').status_code, 403)
        self.client.credentials(HTTP_X_ACCESS_CONTEXT='workspace', HTTP_X_TENANT_ID=str(self.other.pk))
        self.assertEqual(self.client.get('/api/v1/tenants/').data['count'], 1)
        self.assertEqual(self.client.get('/api/v1/plans/').status_code, 200)
        self.assertEqual(self.client.get('/api/v1/platform/audit-events/').status_code, 403)
        self.assertEqual(self.client.get(f'/api/v1/tenants/{self.other.pk}/').status_code, 404)

    def test_platform_admin_can_receive_membership(self):
        admin = User.objects.create_user('platform', 'platform@example.test', is_platform_admin=True)
        self.client.force_authenticate(admin)
        response = self.client.post('/api/v1/tenant-memberships/', {
            'user': admin.pk, 'tenant': self.tenant.pk, 'role': 'owner'}, format='json')
        self.assertEqual(response.status_code, 201, response.data)

    def test_final_active_owner_cannot_be_suspended(self):
        second = User.objects.create_user('inactive', 'inactive@example.test')
        TenantMembership.objects.create(user=second, tenant=self.tenant, role='owner', is_active=False)
        self.client.force_authenticate(self.user)
        response = self.client.patch(f'/api/v1/tenant-memberships/{self.member.pk}/', {'is_active': False}, format='json')
        self.assertEqual(response.status_code, 400)
        self.member.refresh_from_db()
        self.assertTrue(self.member.is_active)

    def test_suspension_preserves_membership_and_reactivation(self):
        member_user = User.objects.create_user('staff', 'staff@example.test')
        member = TenantMembership.objects.create(user=member_user, tenant=self.tenant, role='staff')
        self.client.force_authenticate(self.user)
        for active in (False, True):
            response = self.client.patch(f'/api/v1/tenant-memberships/{member.pk}/', {'is_active': active}, format='json')
            self.assertEqual(response.status_code, 200, response.data)
            member.refresh_from_db()
            self.assertEqual(member.is_active, active)

    def test_direct_email_replacement_is_rejected(self):
        self.client.force_authenticate(self.user)
        response = self.client.patch('/api/v1/auth/user/', {'email': 'new@example.test'}, format='json')
        self.assertEqual(response.status_code, 400)

    def request_email(self):
        self.client.force_authenticate(self.user)
        return self.client.post('/api/v1/auth/email-change/', {
            'email': 'new@example.test', 'password': 'Strong-fixture-472!'}, format='json')

    def test_email_changes_only_after_code_and_replay_is_denied(self):
        self.assertEqual(self.request_email().status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'owner@example.test')
        code = re.search(r'code is: (\d{6})', mail.outbox[-1].body).group(1)
        record = EmailChangeRequest.objects.get(user=self.user)
        self.assertNotEqual(record.code_hash, code)
        response = self.client.post('/api/v1/auth/email-change/confirm/', {'code': code}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'new@example.test')
        self.assertIsNotNone(self.user.email_verified_at)
        self.assertEqual(self.client.post('/api/v1/auth/email-change/confirm/', {'code': code}, format='json').status_code, 400)

    def test_email_failed_attempts_are_durable(self):
        self.request_email()
        record = EmailChangeRequest.objects.get(user=self.user)
        code = re.search(r'code is: (\d{6})', mail.outbox[-1].body).group(1)
        wrong = '111111' if code != '111111' else '222222'
        for _ in range(5):
            self.client.post('/api/v1/auth/email-change/confirm/', {'code': wrong}, format='json')
        record.refresh_from_db()
        self.assertEqual(record.attempts, 5)
        self.assertEqual(self.client.post('/api/v1/auth/email-change/confirm/', {'code': code}, format='json').status_code, 400)

    @patch('apps.tenants.views.send_owner_setup', return_value=False)
    def test_owner_setup_creation_failure_retry_and_confirmation(self, sender):
        self.user.is_platform_admin = True
        self.user.save()
        self.client.force_authenticate(self.user)
        payload = {'name': 'New', 'slug': 'new', 'owner_email': 'invite@example.test', 'owner_username': 'invited'}
        response = self.client.post('/api/v1/tenants/', payload, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['owner_delivery_status'], 'failed')
        tenant = Tenant.objects.get(slug='new')
        owner = tenant.memberships.get(role='owner').user
        self.assertFalse(owner.has_usable_password())
        self.assertTrue(owner.owner_setup_pending)
        self.assertEqual(self.client.post('/api/v1/tenants/', payload, format='json').status_code, 400)
        sender.return_value = True
        self.assertEqual(self.client.post(f'/api/v1/tenants/{tenant.pk}/resend-owner-setup/').status_code, 200)
        token = default_token_generator.make_token(owner)
        self.client.force_authenticate(None)
        response = self.client.post('/api/v1/auth/password-reset/confirm/', {
            'uid': urlsafe_base64_encode(force_bytes(owner.pk)), 'token': token,
            'password': 'New-owner-password-724!', 'password_confirm': 'New-owner-password-724!',
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        owner.refresh_from_db()
        self.assertFalse(owner.owner_setup_pending)
        self.assertTrue(owner.check_password('New-owner-password-724!'))
        self.assertIsNotNone(owner.email_verified_at)

    def test_legacy_identity_lengths_are_preserved(self):
        tenant = Tenant.objects.create(name='Legacy', business_name='Display', slug='a' * 120, phone='1' * 30)
        tenant.full_clean()
        self.assertEqual(tenant.slug, 'a' * 120)

    def test_workspace_header_does_not_grant_platform_permissions(self):
        self.client.force_authenticate(self.user)
        for context in ('platform', 'workspace', 'invalid'):
            self.client.credentials(HTTP_X_ACCESS_CONTEXT=context)
            self.assertEqual(self.client.get('/api/v1/platform/audit-events/').status_code, 403)

    def test_expired_and_cross_user_codes_cannot_change_email(self):
        from datetime import timedelta
        from django.utils import timezone
        self.request_email()
        code = re.search(r'code is: (\d{6})', mail.outbox[-1].body).group(1)
        other = User.objects.create_user('another', 'another@example.test')
        self.client.force_authenticate(other)
        self.assertEqual(self.client.post('/api/v1/auth/email-change/confirm/', {'code': code}).status_code, 400)
        self.client.force_authenticate(self.user)
        EmailChangeRequest.objects.filter(user=self.user).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client.post('/api/v1/auth/email-change/confirm/', {'code': code}).status_code, 400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'owner@example.test')

    @patch('apps.accounts.identity.deliver_identity_email', return_value=False)
    def test_failed_email_delivery_expires_code_and_preserves_verified_address(self, sender):
        verified = self.user.email_verified_at
        self.assertEqual(self.request_email().status_code, 503)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email_verified_at, verified)
        self.assertEqual(self.user.email, 'owner@example.test')
        self.assertEqual(self.request_email().status_code, 503)
        self.assertEqual(sender.call_count, 2)

    def test_new_email_claimed_before_confirmation_is_not_overwritten(self):
        self.request_email()
        code = re.search(r'code is: (\d{6})', mail.outbox[-1].body).group(1)
        User.objects.create_user('other', 'new@example.test')
        self.assertEqual(self.client.post('/api/v1/auth/email-change/confirm/', {'code': code}).status_code, 400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'owner@example.test')

    @patch('apps.tenants.serializers.TenantMembership.objects.create', side_effect=RuntimeError('fixture failure'))
    def test_owner_creation_failure_rolls_back_tenant_and_account(self, create):
        from apps.tenants.serializers import TenantSerializer
        serializer = TenantSerializer(data={'name': 'Rollback', 'slug': 'rollback', 'owner_email': 'rollback@example.test', 'owner_username': 'rollback'})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        with self.assertRaises(RuntimeError):
            serializer.save()
        self.assertFalse(Tenant.objects.filter(slug='rollback').exists())
        self.assertFalse(User.objects.filter(username='rollback').exists())

    def test_pending_owner_cannot_bypass_setup_via_registration_verification(self):
        from apps.accounts.verification import issue_code
        owner = User.objects.create_user('pending', 'pending@example.test', password=None, owner_setup_pending=True, email_verified_at=None)
        _, code = issue_code(owner)
        self.assertEqual(self.client.post('/api/v1/auth/verify-email/', {'email': owner.email, 'code': code}).status_code, 400)
        owner.refresh_from_db()
        self.assertIsNone(owner.email_verified_at)
