from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Tenant, TenantMembership


User = get_user_model()


class TenantIsolationTests(APITestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(name="Tenant A", slug="tenant-a")
        self.tenant_b = Tenant.objects.create(name="Tenant B", slug="tenant-b")
        self.owner_a = User.objects.create_user(
            username="owner-a", email="owner-a@example.com", password="StrongPass-4821"
        )
        self.owner_b = User.objects.create_user(
            username="owner-b", email="owner-b@example.com", password="StrongPass-4821"
        )
        self.staff_a = User.objects.create_user(
            username="staff-a", email="staff-a@example.com", password="StrongPass-4821"
        )
        TenantMembership.objects.create(user=self.owner_a, tenant=self.tenant_a, role="owner")
        TenantMembership.objects.create(user=self.owner_b, tenant=self.tenant_b, role="owner")
        TenantMembership.objects.create(user=self.staff_a, tenant=self.tenant_a, role="staff")

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def test_owner_list_contains_only_own_tenant(self):
        self.authenticate(self.owner_a)

        response = self.client.get(reverse("tenant-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in response.data["results"]], [self.tenant_a.id])

    def test_owner_cannot_retrieve_other_tenant(self):
        self.authenticate(self.owner_a)

        response = self.client.get(reverse("tenant-detail", args=[self.tenant_b.id]))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_owner_cannot_modify_tenant(self):
        self.authenticate(self.owner_a)

        response = self.client.patch(
            reverse("tenant-detail", args=[self.tenant_a.id]),
            {"name": "Unauthorized rename"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.tenant_a.refresh_from_db()
        self.assertEqual(self.tenant_a.name, "Tenant A")

    def test_staff_cannot_create_membership_or_escalate_role(self):
        candidate = User.objects.create_user(
            username="candidate", email="candidate@example.com", password="StrongPass-4821"
        )
        self.authenticate(self.staff_a)

        response = self.client.post(
            reverse("tenant-membership-list"),
            {"user": candidate.id, "tenant": self.tenant_a.id, "role": "owner"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(TenantMembership.objects.filter(user=candidate).exists())

    def test_owner_creates_membership_only_in_own_tenant(self):
        candidate = User.objects.create_user(
            username="candidate", email="candidate@example.com", password="StrongPass-4821"
        )
        self.authenticate(self.owner_a)

        response = self.client.post(
            reverse("tenant-membership-list"),
            {"user": candidate.id, "tenant": self.tenant_b.id, "role": "staff"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(TenantMembership.objects.get(user=candidate).tenant, self.tenant_a)

    def test_owner_cannot_update_other_tenant_membership(self):
        membership_b = self.owner_b.membership
        self.authenticate(self.owner_a)

        response = self.client.patch(
            reverse("tenant-membership-detail", args=[membership_b.id]),
            {"role": "staff"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        membership_b.refresh_from_db()
        self.assertEqual(membership_b.role, "owner")

    def test_staff_cannot_read_or_update_tenant_secrets(self):
        self.authenticate(self.staff_a)

        get_response = self.client.get(reverse("tenant-settings"))
        patch_response = self.client.patch(
            reverse("tenant-settings"),
            {"paystack_secret_key": "attacker-key"},
            format="json",
        )

        self.assertEqual(get_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(patch_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_settings_are_bound_to_own_tenant(self):
        self.authenticate(self.owner_a)

        response = self.client.patch(
            reverse("tenant-settings"),
            {"tenant": self.tenant_b.id, "voucher_prefix": "A-"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["tenant"], self.tenant_a.id)
        self.assertEqual(self.tenant_a.settings.voucher_prefix, "A-")
        self.assertFalse(hasattr(self.tenant_b, "settings"))

    def test_platform_admin_can_list_all_tenants_without_membership(self):
        platform_admin = User.objects.create_user(
            username="platform-admin",
            email="platform@example.com",
            password="StrongPass-4821",
            is_platform_admin=True,
        )
        self.authenticate(platform_admin)

        response = self.client.get(reverse("tenant-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {item["id"] for item in response.data["results"]},
            {self.tenant_a.id, self.tenant_b.id},
        )
