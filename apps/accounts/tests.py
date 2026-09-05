from datetime import datetime, timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.tenants.models import Tenant, TenantMembership


User = get_user_model()


class RegistrationTests(APITestCase):
    def valid_payload(self, **overrides):
        payload = {
            "username": "new_owner",
            "email": "owner@example.com",
            "password": "StrongPass-4821",
            "password_confirm": "StrongPass-4821",
            "tenant_name": "New Network",
            "phone": "08012345678",
        }
        payload.update(overrides)
        return payload

    def test_registration_creates_hashed_user_tenant_owner_and_tokens(self):
        response = self.client.post(reverse("register"), self.valid_payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(username="new_owner")
        membership = TenantMembership.objects.select_related("tenant").get(user=user)
        self.assertTrue(user.check_password("StrongPass-4821"))
        self.assertNotEqual(user.password, "StrongPass-4821")
        self.assertEqual(membership.role, "owner")
        self.assertEqual(membership.tenant.slug, "new-network")
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_registration_rejects_password_mismatch_without_partial_writes(self):
        response = self.client.post(
            reverse("register"),
            self.valid_payload(password_confirm="DifferentPass-4821"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(username="new_owner").exists())
        self.assertFalse(Tenant.objects.filter(slug="new-network").exists())

    def test_registration_rejects_duplicate_tenant_slug_without_creating_user(self):
        Tenant.objects.create(name="Existing", slug="new-network")

        response = self.client.post(reverse("register"), self.valid_payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(username="new_owner").exists())


class AuthenticationTests(APITestCase):
    def setUp(self):
        self.password = "StrongPass-4821"
        self.user = User.objects.create_user(
            username="owner",
            email="owner@example.com",
            password=self.password,
        )

    def test_login_returns_tokens_for_active_user(self):
        response = self.client.post(
            reverse("login"),
            {"username": self.user.username, "password": self.password},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_login_rejects_inactive_user(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

        response = self.client.post(
            reverse("login"),
            {"username": self.user.username, "password": self.password},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_current_user_requires_authentication(self):
        response = self.client.get(reverse("current-user"))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class PasswordResetTests(APITestCase):
    def setUp(self):
        self.old_password = "StrongPass-4821"
        self.new_password = "NewStrongPass-5932"
        self.user = User.objects.create_user(
            username="reset-owner",
            email="reset@example.com",
            password=self.old_password,
        )

    def reset_credentials(self):
        return {
            "uid": urlsafe_base64_encode(force_bytes(self.user.pk)),
            "token": default_token_generator.make_token(self.user),
        }

    def test_request_sends_reset_link_for_active_account(self):
        response = self.client.post(
            reverse("password-reset"),
            {"email": "RESET@example.com"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])
        self.assertIn("uid=", mail.outbox[0].body)
        self.assertIn("token=", mail.outbox[0].body)

    def test_request_does_not_reveal_unknown_email(self):
        known = self.client.post(
            reverse("password-reset"),
            {"email": self.user.email},
            format="json",
        )
        known_message = known.data["message"]
        mail.outbox.clear()

        unknown = self.client.post(
            reverse("password-reset"),
            {"email": "unknown@example.com"},
            format="json",
        )

        self.assertEqual(unknown.status_code, status.HTTP_200_OK)
        self.assertEqual(unknown.data["message"], known_message)
        self.assertEqual(mail.outbox, [])

    def test_valid_confirmation_changes_password_and_token_is_one_time(self):
        credentials = self.reset_credentials()
        payload = {
            **credentials,
            "password": self.new_password,
            "password_confirm": self.new_password,
        }

        response = self.client.post(reverse("password-reset-confirm"), payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.new_password))
        replay = self.client.post(reverse("password-reset-confirm"), payload, format="json")
        self.assertEqual(replay.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_token_does_not_change_password(self):
        credentials = self.reset_credentials()
        response = self.client.post(
            reverse("password-reset-confirm"),
            {
                **credentials,
                "token": "invalid-token",
                "password": self.new_password,
                "password_confirm": self.new_password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.old_password))

    def test_expired_token_does_not_change_password(self):
        issued_at = datetime.now() - timedelta(seconds=settings.PASSWORD_RESET_TIMEOUT + 1)
        with patch.object(default_token_generator, "_now", return_value=issued_at):
            credentials = self.reset_credentials()
        response = self.client.post(
            reverse("password-reset-confirm"),
            {**credentials, "password": self.new_password, "password_confirm": self.new_password},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.old_password))

    def test_confirmation_rejects_mismatched_passwords_without_changing_account(self):
        response = self.client.post(
            reverse("password-reset-confirm"),
            {**self.reset_credentials(), "password": self.new_password, "password_confirm": "Different-Password-7342"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password_confirm", response.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.old_password))

    def test_reset_token_cannot_be_used_for_another_account(self):
        other = User.objects.create_user(
            username="other-reset-owner", email="other-reset@example.com", password=self.old_password,
        )
        credentials = self.reset_credentials()
        response = self.client.post(
            reverse("password-reset-confirm"),
            {**credentials, "uid": urlsafe_base64_encode(force_bytes(other.pk)),
             "password": self.new_password, "password_confirm": self.new_password},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        for user in (self.user, other):
            user.refresh_from_db()
            self.assertTrue(user.check_password(self.old_password))

    def test_old_refresh_cannot_restore_access_after_password_reset(self):
        old_refresh = str(RefreshToken.for_user(self.user))
        reset = self.client.post(
            reverse("password-reset-confirm"),
            {**self.reset_credentials(), "password": self.new_password, "password_confirm": self.new_password},
            format="json",
        )
        self.assertEqual(reset.status_code, status.HTTP_200_OK)
        refreshed = self.client.post(reverse("token-refresh"), {"refresh": old_refresh}, format="json")
        # Implementations may reject refresh itself or reject its stale password
        # claim when the resulting access token reaches an authenticated view.
        if refreshed.status_code == status.HTTP_200_OK:
            self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refreshed.data['access']}")
            self.assertEqual(self.client.get(reverse("current-user")).status_code, status.HTTP_401_UNAUTHORIZED)
        else:
            self.assertEqual(refreshed.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_confirmation_enforces_django_password_validation(self):
        response = self.client.post(
            reverse("password-reset-confirm"),
            {
                **self.reset_credentials(),
                "password": "password",
                "password_confirm": "password",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data)

    def test_password_reset_revokes_jwt_issued_before_change(self):
        access_token = str(RefreshToken.for_user(self.user).access_token)
        credentials = self.reset_credentials()
        self.client.post(
            reverse("password-reset-confirm"),
            {
                **credentials,
                "password": self.new_password,
                "password_confirm": self.new_password,
            },
            format="json",
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

        response = self.client.get(reverse("current-user"))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_password_reset_requests_are_rate_limited(self):
        responses = [
            self.client.post(
                reverse("password-reset"),
                {"email": "unknown@example.com"},
                format="json",
                REMOTE_ADDR="192.0.2.10",
            )
            for _ in range(6)
        ]

        self.assertTrue(all(response.status_code == 200 for response in responses[:5]))
        self.assertEqual(responses[5].status_code, status.HTTP_429_TOO_MANY_REQUESTS)
