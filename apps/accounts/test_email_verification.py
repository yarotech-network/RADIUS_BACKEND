"""OTP email verification for new tenant accounts (public registration flow)."""

import re
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.tenants.models import TenantMembership

User = get_user_model()


def extract_code(body):
    match = re.search(r"Your verification code is: (\d{6})", body)
    assert match, "OTP not found in email body"
    return match.group(1)


class EmailVerificationFlowTests(APITestCase):
    # Each test gets its own client IP so the 10/minute verify throttle of one
    # test never leaks into the next (same convention as the password-reset tests).
    _ip = iter(f"192.0.2.{n}" for n in range(50, 100))

    def setUp(self):
        self.client.defaults["REMOTE_ADDR"] = next(self._ip)
        self.payload = {
            "username": "owner2",
            "email": "owner2@example.com",
            "password": "StrongPass-4821",
            "password_confirm": "StrongPass-4821",
            "tenant_name": "Second Network",
            "phone": "08012345678",
        }

    def register(self):
        response = self.client.post(reverse("register"), self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        return response

    def latest_code(self):
        return User.objects.get(username="owner2").email_codes.order_by("-created_at").first()

    # ---- registration issues an OTP and withholds tokens ----

    def test_register_sends_otp_and_creates_unverified_owner(self):
        self.register()

        user = User.objects.get(username="owner2")
        self.assertIsNone(user.email_verified_at)
        self.assertEqual(TenantMembership.objects.get(user=user).role, "owner")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["owner2@example.com"])
        # Only the hash is stored, never the code itself.
        self.assertNotEqual(extract_code(mail.outbox[0].body), self.latest_code().code_hash)

    def test_login_is_blocked_until_email_verified(self):
        self.register()

        response = self.client.post(
            reverse("login"),
            {"username": "owner2", "password": "StrongPass-4821"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["code"], "email_not_verified")
        self.assertEqual(response.data["email"], "owner2@example.com")
        self.assertNotIn("access", response.data)

    # ---- verification ----

    def verify(self, code, email="owner2@example.com"):
        return self.client.post(
            reverse("verify-email"), {"email": email, "code": code}, format="json"
        )

    def test_verify_with_correct_code_returns_tokens_and_activates_account(self):
        self.register()
        code = extract_code(mail.outbox[0].body)

        response = self.verify(code)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

        user = User.objects.get(username="owner2")
        self.assertIsNotNone(user.email_verified_at)
        self.assertIsNotNone(self.latest_code().consumed_at)

        # The tokens work immediately and login is now allowed.
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        me = self.client.get(reverse("current-user"))
        self.assertEqual(me.status_code, status.HTTP_200_OK)
        self.assertEqual(me.data["username"], "owner2")
        self.client.credentials()
        login = self.client.post(
            reverse("login"),
            {"username": "owner2", "password": "StrongPass-4821"},
            format="json",
        )
        self.assertEqual(login.status_code, status.HTTP_200_OK)
        self.assertIn("access", login.data)

    def test_verify_rejects_wrong_code_and_counts_attempts(self):
        self.register()

        response = self.verify("000000")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Incorrect code", response.data["detail"])
        self.assertEqual(self.latest_code().attempts, 1)

    def test_verify_locks_code_after_five_wrong_attempts(self):
        self.register()

        for _ in range(5):
            self.verify("000000")

        response = self.verify(extract_code(mail.outbox[0].body))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Too many wrong attempts", response.data["detail"])
        user = User.objects.get(username="owner2")
        self.assertIsNone(user.email_verified_at)

    def test_verify_rejects_expired_code(self):
        self.register()
        record = self.latest_code()
        record.expires_at = timezone.now() - timedelta(seconds=1)
        record.save()

        response = self.verify(extract_code(mail.outbox[0].body))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("expired", response.data["detail"])

    def test_verify_rejects_replayed_code_after_success(self):
        self.register()
        code = extract_code(mail.outbox[0].body)
        self.verify(code)

        response = self.verify(code)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_verify_is_generic_for_unknown_and_already_verified_accounts(self):
        self.register()
        # Unknown address: no hint that the account does not exist.
        response = self.verify("123456", email="nobody@example.com")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "Invalid code or email.")

        # Already verified: same generic answer (user should just sign in).
        self.verify(extract_code(mail.outbox[0].body))
        response = self.verify("123456")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "Invalid code or email.")

    # ---- resending ----

    def test_resend_issues_fresh_code_and_invalidates_previous(self):
        self.register()
        first = extract_code(mail.outbox[0].body)
        # The registration code was just issued — simulate a minute having passed
        # so the resend cooldown no longer applies.
        record = self.latest_code()
        record.created_at = timezone.now() - timedelta(seconds=61)
        record.save()

        response = self.client.post(
            reverse("resend-verification"), {"email": "owner2@example.com"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 2)
        second = extract_code(mail.outbox[1].body)
        self.assertNotEqual(first, second)

        # The old code no longer works; the new one does.
        self.assertEqual(self.verify(first).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.verify(second).status_code, status.HTTP_200_OK)

    def test_resend_cooldown_prevents_code_spam(self):
        self.register()

        self.client.post(
            reverse("resend-verification"), {"email": "owner2@example.com"}, format="json"
        )
        response = self.client.post(
            reverse("resend-verification"), {"email": "owner2@example.com"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("recently", response.data["message"])
        self.assertEqual(len(mail.outbox), 1)  # no second email within the cooldown

    def test_resend_is_generic_for_unknown_or_verified_emails(self):
        response = self.client.post(
            reverse("resend-verification"), {"email": "nobody@example.com"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("If an unverified account exists", response.data["message"])
        self.assertEqual(len(mail.outbox), 0)

        self.register()
        self.verify(extract_code(mail.outbox[0].body))
        before = len(mail.outbox)
        response = self.client.post(
            reverse("resend-verification"), {"email": "owner2@example.com"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), before)

    # ---- internal accounts are never gated ----

    def test_internally_created_accounts_are_verified_by_default(self):
        user = User.objects.create_user("internal", "internal@example.com", "StrongPass-4821")
        self.assertIsNotNone(user.email_verified_at)

        response = self.client.post(
            reverse("login"),
            {"username": "internal", "password": "StrongPass-4821"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)

    def test_platform_admin_login_is_never_blocked_by_verification(self):
        admin = User.objects.create_user(
            "rootadmin", "root@example.com", "StrongPass-4821", is_superuser=True
        )
        admin.email_verified_at = None  # even an unverified superuser must not be locked out
        admin.save(update_fields=["email_verified_at"])

        response = self.client.post(
            reverse("login"),
            {"username": "rootadmin", "password": "StrongPass-4821"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
