from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.tenants.models import Tenant, TenantMembership
from .models import InternetPlan, Voucher
from .services import VoucherService


User = get_user_model()


class VoucherFixtureMixin:
    def make_plan(self, tenant, name="Standard", price=100_000):
        return InternetPlan.objects.create(
            tenant=tenant,
            name=name,
            price=price,
            duration_hours=24,
            rate_limit="5M/10M",
        )


class VoucherServiceTests(VoucherFixtureMixin, APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Tenant A", slug="tenant-a")
        self.plan = self.make_plan(self.tenant)

    @patch("apps.vouchers.services.Radcheck.objects.create")
    def test_generation_creates_voucher_and_radius_credentials_atomically(self, radius_create):
        vouchers = VoucherService.generate_vouchers(self.tenant, self.plan.id, 2, prefix="A-")

        self.assertEqual(len(vouchers), 2)
        self.assertEqual(Voucher.objects.filter(tenant=self.tenant).count(), 2)
        self.assertEqual(radius_create.call_count, 4)
        self.assertTrue(all(voucher.username.startswith("A-") for voucher in vouchers))

    @patch("apps.vouchers.services.Radcheck.objects.create")
    def test_generated_credentials_are_one_readable_access_code(self, radius_create):
        # Customers read the code off a screen or an email, so username and password are the
        # same 8-character code drawn from an alphabet without look-alike characters.
        vouchers = VoucherService.generate_vouchers(self.tenant, self.plan.id, 5, prefix="WU-")
        for voucher in vouchers:
            self.assertEqual(voucher.username, voucher.password)
            self.assertRegex(voucher.username, r"^WU-[ABCDEFGHJKMNPQRTUVWXYZ234678]{8}$")
        self.assertEqual(len({v.username for v in vouchers}), 5)
        # RADIUS receives the same code as the cleartext password.
        password_rows = [c.kwargs for c in radius_create.call_args_list if c.kwargs["attribute"] == "Cleartext-Password"]
        self.assertEqual({r["username"] for r in password_rows}, {v.username for v in vouchers})
        self.assertTrue(all(r["value"] == r["username"] for r in password_rows))
        for forbidden in "0O1Il5S":
            self.assertNotIn(forbidden, Voucher.ACCESS_CODE_ALPHABET)

    @patch("apps.vouchers.services.Radcheck.objects.create", side_effect=RuntimeError("radius unavailable"))
    def test_generation_rolls_back_voucher_when_radius_write_fails(self, radius_create):
        with self.assertRaisesRegex(RuntimeError, "radius unavailable"):
            VoucherService.generate_vouchers(self.tenant, self.plan.id, 1)

        self.assertFalse(Voucher.objects.exists())

    @patch("apps.vouchers.services.Radcheck.objects.filter")
    def test_expiry_removes_radius_rows_for_every_expired_voucher(self, radius_filter):
        expired = Voucher.objects.create(
            username="expired-user",
            password="secret",
            tenant=self.tenant,
            plan=self.plan,
            status="active",
            expires_at=timezone.now() - timedelta(minutes=1),
        )

        count = VoucherService.expire_vouchers()

        self.assertEqual(count, 1)
        expired.refresh_from_db()
        self.assertEqual(expired.status, "expired")
        radius_filter.assert_called_once_with(username__in=["expired-user"])
        radius_filter.return_value.delete.assert_called_once_with()

    @patch("apps.vouchers.services.Radcheck.objects.filter")
    def test_disable_rolls_back_status_when_radius_delete_fails(self, radius_filter):
        voucher = Voucher.objects.create(
            username="unused-user",
            password="secret",
            tenant=self.tenant,
            plan=self.plan,
        )
        radius_filter.return_value.delete.side_effect = RuntimeError("radius unavailable")

        with self.assertRaisesRegex(RuntimeError, "radius unavailable"):
            VoucherService.disable_voucher(voucher)

        voucher.refresh_from_db()
        self.assertEqual(voucher.status, "unused")

    def test_activation_sets_status_and_expiration(self):
        voucher = Voucher.objects.create(
            username="activate-user",
            password="secret",
            tenant=self.tenant,
            plan=self.plan,
        )
        before = timezone.now()

        activated = VoucherService.activate_voucher(voucher)

        voucher.refresh_from_db()
        self.assertTrue(activated)
        self.assertEqual(voucher.status, "active")
        self.assertGreaterEqual(voucher.activated_at, before)
        self.assertEqual(voucher.expires_at, voucher.activated_at + timedelta(hours=24))


class VoucherApiTests(VoucherFixtureMixin, APITestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(name="Tenant A", slug="tenant-a")
        self.tenant_b = Tenant.objects.create(name="Tenant B", slug="tenant-b")
        self.plan_a = self.make_plan(self.tenant_a, name="Plan A")
        self.plan_b = self.make_plan(self.tenant_b, name="Plan B")
        self.manager = User.objects.create_user(
            username="manager", email="manager@example.com", password="StrongPass-4821"
        )
        self.staff = User.objects.create_user(
            username="staff", email="staff@example.com", password="StrongPass-4821"
        )
        TenantMembership.objects.create(user=self.manager, tenant=self.tenant_a, role="manager")
        TenantMembership.objects.create(user=self.staff, tenant=self.tenant_a, role="staff")

    def test_plan_list_is_tenant_scoped(self):
        self.client.force_authenticate(self.manager)

        response = self.client.get(reverse("plan-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in response.data["results"]], [self.plan_a.id])

    def test_staff_cannot_create_plan(self):
        self.client.force_authenticate(self.staff)

        response = self.client.post(
            reverse("plan-list"),
            {
                "name": "Forbidden",
                "price": 1000,
                "duration_hours": 1,
                "rate_limit": "1M/1M",
                "data_limit": 0,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("apps.vouchers.services.Radcheck.objects.create")
    def test_manager_generates_voucher_for_own_plan(self, radius_create):
        self.client.force_authenticate(self.manager)

        response = self.client.post(
            reverse("voucher-generate"),
            {"plan_id": self.plan_a.id, "quantity": 2, "prefix": "A-"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(response.data), 2)
        self.assertEqual(Voucher.objects.filter(tenant=self.tenant_a).count(), 2)

    def test_manager_cannot_generate_from_another_tenant_plan(self):
        self.client.force_authenticate(self.manager)

        response = self.client.post(
            reverse("voucher-generate"),
            {"plan_id": self.plan_b.id, "quantity": 1},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Voucher.objects.exists())

    def test_generation_rejects_quantity_above_limit(self):
        self.client.force_authenticate(self.manager)

        response = self.client.post(
            reverse("voucher-generate"),
            {"plan_id": self.plan_a.id, "quantity": 101},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_voucher_list_is_tenant_scoped(self):
        own = Voucher.objects.create(
            username="own-user", password="secret", tenant=self.tenant_a, plan=self.plan_a
        )
        Voucher.objects.create(
            username="other-user", password="secret", tenant=self.tenant_b, plan=self.plan_b
        )
        self.client.force_authenticate(self.manager)

        response = self.client.get(reverse("voucher-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in response.data["results"]], [own.id])

    def test_voucher_api_exposes_single_access_code_but_never_a_separate_password(self):
        legacy = Voucher.objects.create(username="legacy-user", password="separate", tenant=self.tenant_a, plan=self.plan_a)
        single = Voucher.objects.create(username="ABCDEFGH", password="ABCDEFGH", tenant=self.tenant_a, plan=self.plan_a)
        self.client.force_authenticate(self.manager)

        rows = {item["id"]: item for item in self.client.get(reverse("voucher-list")).data["results"]}

        self.assertIsNone(rows[legacy.id]["access_code"])
        self.assertEqual(rows[single.id]["access_code"], "ABCDEFGH")
        self.assertNotIn("password", rows[legacy.id])
        self.assertNotIn("separate", str(rows))
