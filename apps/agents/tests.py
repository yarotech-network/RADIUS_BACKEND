from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import close_old_connections
from django.test import TransactionTestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.tenants.models import Tenant, TenantSetting
from apps.vouchers.models import InternetPlan, Voucher
from .models import (
    AgentProfile,
    AgentVoucherAllocation,
    AgentWallet,
    AgentWalletFundingPayment,
)
from .services import AgentService


User = get_user_model()


class AgentFixtureMixin:
    def create_agent(self, username="agent", status_value="active", balance=100_000):
        user = User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="StrongPass-4821",
        )
        agent = AgentProfile.objects.create(
            user=user,
            tenant=self.tenant,
            phone="08012345678",
            status=status_value,
        )
        wallet = AgentWallet.objects.create(agent=agent, balance=balance)
        return user, agent, wallet


class AgentApiTests(AgentFixtureMixin, APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Tenant A", slug="tenant-a")
        TenantSetting.objects.create(tenant=self.tenant, max_funding_amount=100_000)
        self.user, self.agent, self.wallet = self.create_agent()

    def test_active_agent_can_login(self):
        response = self.client.post(
            reverse("agent-login"),
            {"username": self.user.username, "password": "StrongPass-4821"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)

    def test_inactive_user_cannot_login_as_agent(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

        response = self.client.post(
            reverse("agent-login"),
            {"username": self.user.username, "password": "StrongPass-4821"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_suspended_agent_with_existing_auth_cannot_access_dashboard(self):
        self.agent.status = "suspended"
        self.agent.save(update_fields=["status"])
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse("agent-dashboard"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_agent_cannot_change_tenant_status_or_commission(self):
        other = Tenant.objects.create(name="Tenant B", slug="tenant-b")
        self.client.force_authenticate(self.user)

        response = self.client.patch(
            reverse("agent-detail", args=[self.agent.id]),
            {"tenant": other.id, "status": "suspended", "commission_rate": "99.00"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.tenant, self.tenant)
        self.assertEqual(self.agent.status, "active")
        self.assertEqual(str(self.agent.commission_rate), "10.00")

    def test_wallet_funding_enforces_minimum_and_tenant_maximum(self):
        self.client.force_authenticate(self.user)

        too_small = self.client.post(reverse("agent-wallet-fund"), {"amount": 49_999}, format="json")
        too_large = self.client.post(reverse("agent-wallet-fund"), {"amount": 100_001}, format="json")

        self.assertEqual(too_small.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(too_large.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(AgentWalletFundingPayment.objects.exists())

    @patch("apps.vouchers.services.Radcheck.objects.create")
    def test_agent_sale_returns_the_access_code_to_hand_to_the_customer(self, radius_create):
        plan = InternetPlan.objects.create(tenant=self.tenant, name="Daily", price=25_000, duration_hours=24, rate_limit="5M/10M")
        self.client.force_authenticate(self.user)

        response = self.client.post(
            reverse("agent-voucher-generate"), {"plan_id": plan.pk, "quantity": 2}, format="json",
            HTTP_IDEMPOTENCY_KEY="agent-sale-access-code-1",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        rows = response.data["vouchers"]
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(row["access_code"], row["voucher_username"])
            self.assertRegex(row["access_code"], r"^[ABCDEFGHJKMNPQRTUVWXYZ234678]{8}$")
        history = self.client.get(reverse("agent-voucher-history"))
        self.assertEqual({r["access_code"] for r in history.data["results"]}, {r["access_code"] for r in rows})


class AgentWalletServiceTests(AgentFixtureMixin, APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Tenant A", slug="tenant-a")
        self.user, self.agent, self.wallet = self.create_agent()
        self.plan = InternetPlan.objects.create(
            tenant=self.tenant,
            name="Standard",
            price=60_000,
            duration_hours=24,
            rate_limit="5M/10M",
        )

    @patch("apps.vouchers.services.Radcheck.objects.create")
    def test_voucher_purchase_debits_wallet_and_creates_allocation(self, radius_create):
        vouchers, allocations = AgentService.generate_voucher_from_wallet(
            self.agent, self.plan.id
        )

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 40_000)
        self.assertEqual(len(vouchers), 1)
        self.assertEqual(len(allocations), 1)
        self.assertEqual(allocations[0].amount_charged, 60_000)

    @patch("apps.vouchers.services.Radcheck.objects.create", side_effect=RuntimeError("radius unavailable"))
    def test_radius_failure_rolls_back_wallet_voucher_and_allocation(self, radius_create):
        with self.assertRaisesRegex(RuntimeError, "radius unavailable"):
            AgentService.generate_voucher_from_wallet(self.agent, self.plan.id)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 100_000)
        self.assertFalse(Voucher.objects.exists())
        self.assertFalse(AgentVoucherAllocation.objects.exists())

    def test_duplicate_funding_completion_credits_wallet_once(self):
        payment = AgentWalletFundingPayment.objects.create(
            wallet=self.wallet,
            amount=50_000,
            reference="funding-1",
        )

        first = AgentService.complete_wallet_funding(payment)
        second = AgentService.complete_wallet_funding(payment)

        self.wallet.refresh_from_db()
        payment.refresh_from_db()
        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(self.wallet.balance, 150_000)
        self.assertEqual(payment.status, "success")
        self.assertIsNotNone(payment.completed_at)


class AgentWalletConcurrencyTests(AgentFixtureMixin, TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Tenant A", slug="tenant-a")
        self.user, self.agent, self.wallet = self.create_agent(balance=100_000)
        self.plan = InternetPlan.objects.create(
            tenant=self.tenant,
            name="Whole balance",
            price=100_000,
            duration_hours=24,
            rate_limit="5M/10M",
        )

    def test_simultaneous_spending_cannot_overdraw_wallet(self):
        barrier = Barrier(2)

        def spend_once():
            close_old_connections()
            agent = AgentProfile.objects.get(pk=self.agent.pk)
            barrier.wait(timeout=5)
            try:
                AgentService.generate_voucher_from_wallet(agent, self.plan.pk)
                return "success"
            except ValueError:
                return "insufficient"
            finally:
                close_old_connections()

        with patch("apps.vouchers.services.Radcheck.objects.create"):
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(lambda _: spend_once(), range(2)))

        self.wallet.refresh_from_db()
        self.assertCountEqual(results, ["success", "insufficient"])
        self.assertEqual(self.wallet.balance, 0)
        self.assertEqual(Voucher.objects.count(), 1)
        self.assertEqual(AgentVoucherAllocation.objects.count(), 1)

    def test_simultaneous_duplicate_completion_credits_wallet_once(self):
        payment = AgentWalletFundingPayment.objects.create(
            wallet=self.wallet,
            amount=50_000,
            reference="funding-concurrent",
        )
        barrier = Barrier(2)

        def complete_once():
            close_old_connections()
            current = AgentWalletFundingPayment.objects.get(pk=payment.pk)
            barrier.wait(timeout=5)
            result = AgentService.complete_wallet_funding(current)
            close_old_connections()
            return result

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: complete_once(), range(2)))

        self.wallet.refresh_from_db()
        self.assertCountEqual(results, [True, False])
        self.assertEqual(self.wallet.balance, 150_000)
