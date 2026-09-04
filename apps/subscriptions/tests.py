from datetime import timedelta
from io import StringIO
import threading
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import close_old_connections
from django.test import TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from apps.tenants.models import Tenant, TenantMembership
from .models import SubscriptionPayment, SubscriptionPlan, TenantSubscription
from .services import SubscriptionService

User = get_user_model()

class SubscriptionApiTests(APITestCase):
    def setUp(self):
        self.plan = SubscriptionPlan.objects.create(name="Starter", price=100000, duration_days=30)
        SubscriptionPlan.objects.create(name="Retired", price=50000, duration_days=30, is_active=False)
        self.tenant = Tenant.objects.create(name="Tenant A", slug="tenant-a")
        self.user = User.objects.create_user(username="owner", email="owner@example.com", password="StrongPass-4821")
        TenantMembership.objects.create(user=self.user, tenant=self.tenant, role="owner")

    def test_public_pricing_returns_only_active_plans(self):
        response = self.client.get(reverse("subscription-plan-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in response.data["results"]], [self.plan.id])

    def test_missing_subscription_returns_404_without_creating_on_get(self):
        self.client.force_authenticate(self.user)
        response = self.client.get(reverse("tenant-subscription"))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(TenantSubscription.objects.exists())

    def test_subscription_is_read_only_and_tenant_bound(self):
        subscription = TenantSubscription.objects.create(tenant=self.tenant, plan=self.plan, status="trial", expires_at=timezone.now() + timedelta(days=5), is_trial=True)
        self.client.force_authenticate(self.user)
        get_response = self.client.get(reverse("tenant-subscription"))
        patch_response = self.client.patch(reverse("tenant-subscription"), {"status": "active"}, format="json")
        self.assertEqual(get_response.data["id"], subscription.id)
        self.assertEqual(patch_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    @patch("apps.subscriptions.views.get_paystack_service")
    def test_owner_checkout_uses_server_price_and_platform_paystack(self, service_factory):
        service_factory.return_value.initialize_transaction.return_value = {
            "data": {"authorization_url": "https://checkout.paystack.test/subscription"}
        }
        self.client.force_authenticate(self.user)

        response = self.client.post(
            reverse("subscription-checkout"),
            {"plan_id": self.plan.id, "amount": 1},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payment = SubscriptionPayment.objects.get(reference=response.data["reference"])
        self.assertEqual(payment.tenant, self.tenant)
        self.assertEqual(payment.plan, self.plan)
        self.assertEqual(payment.amount, self.plan.price)
        self.assertIsNone(payment.subscription)
        service_factory.assert_called_once_with()
        self.assertEqual(
            service_factory.return_value.initialize_transaction.call_args.kwargs["amount"],
            self.plan.price,
        )

    def test_checkout_requires_owner_and_active_valid_plan(self):
        manager = User.objects.create_user(
            username="manager", email="manager@example.com", password="StrongPass-4821"
        )
        TenantMembership.objects.create(user=manager, tenant=self.tenant, role="manager")
        self.client.force_authenticate(manager)
        forbidden = self.client.post(
            reverse("subscription-checkout"), {"plan_id": self.plan.id}, format="json"
        )
        self.client.force_authenticate(self.user)
        inactive = SubscriptionPlan.objects.get(name="Retired")
        invalid = self.client.post(
            reverse("subscription-checkout"), {"plan_id": inactive.id}, format="json"
        )

        self.assertEqual(forbidden.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(SubscriptionPayment.objects.exists())

    @patch("apps.subscriptions.views.get_paystack_service")
    def test_provider_failure_retains_pending_payment_for_reconciliation(self, service_factory):
        service_factory.return_value.initialize_transaction.side_effect = OSError("timeout")
        self.client.force_authenticate(self.user)

        response = self.client.post(
            reverse("subscription-checkout"), {"plan_id": self.plan.id}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        payment = SubscriptionPayment.objects.get(reference=response.data["reference"])
        self.assertEqual(payment.status, "pending")

    def test_payment_status_is_tenant_scoped(self):
        payment = SubscriptionPayment.objects.create(
            tenant=self.tenant,
            plan=self.plan,
            reference="subscription-status-1",
            amount=self.plan.price,
        )
        other_tenant = Tenant.objects.create(name="Tenant B", slug="tenant-b")
        other = User.objects.create_user(
            username="other", email="other@example.com", password="StrongPass-4821"
        )
        TenantMembership.objects.create(user=other, tenant=other_tenant, role="owner")

        self.client.force_authenticate(self.user)
        visible = self.client.get(
            reverse("subscription-payment-status", args=[payment.reference])
        )
        self.client.force_authenticate(other)
        hidden = self.client.get(
            reverse("subscription-payment-status", args=[payment.reference])
        )

        self.assertEqual(visible.status_code, status.HTTP_200_OK)
        self.assertEqual(hidden.status_code, status.HTTP_404_NOT_FOUND)


class SubscriptionServiceTests(APITestCase):
    def setUp(self):
        self.plan = SubscriptionPlan.objects.create(
            name="Starter", price=100000, duration_days=30
        )
        self.tenant = Tenant.objects.create(name="Tenant A", slug="tenant-a")

    def payment(self, reference="subscription-payment-1"):
        return SubscriptionPayment.objects.create(
            tenant=self.tenant,
            plan=self.plan,
            reference=reference,
            amount=self.plan.price,
        )

    def test_first_payment_activates_subscription_and_is_idempotent(self):
        payment = self.payment()

        first = SubscriptionService.complete_payment(payment)
        payment.refresh_from_db()
        subscription = TenantSubscription.objects.get(tenant=self.tenant)
        first_expiration = subscription.expires_at
        second = SubscriptionService.complete_payment(payment)
        subscription.refresh_from_db()

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(payment.status, "success")
        self.assertEqual(payment.subscription, subscription)
        self.assertEqual(subscription.status, "active")
        self.assertFalse(subscription.is_trial)
        self.assertEqual(subscription.expires_at, first_expiration)

    def test_early_renewal_extends_from_current_expiration(self):
        old_expiration = timezone.now() + timedelta(days=10)
        subscription = TenantSubscription.objects.create(
            tenant=self.tenant,
            plan=self.plan,
            status="active",
            expires_at=old_expiration,
            is_trial=False,
        )

        SubscriptionService.complete_payment(self.payment())

        subscription.refresh_from_db()
        self.assertEqual(subscription.expires_at, old_expiration + timedelta(days=30))

    def test_expired_subscription_restarts_from_payment_time(self):
        TenantSubscription.objects.create(
            tenant=self.tenant,
            plan=self.plan,
            status="expired",
            expires_at=timezone.now() - timedelta(days=2),
            is_trial=False,
        )
        before = timezone.now()

        SubscriptionService.complete_payment(self.payment())

        subscription = TenantSubscription.objects.get(tenant=self.tenant)
        self.assertGreaterEqual(subscription.started_at, before)
        self.assertEqual(
            subscription.expires_at,
            subscription.started_at + timedelta(days=self.plan.duration_days),
        )

    def test_expiration_command_marks_only_due_subscriptions(self):
        due = TenantSubscription.objects.create(
            tenant=self.tenant,
            plan=self.plan,
            status="active",
            expires_at=timezone.now() - timedelta(seconds=1),
            is_trial=False,
        )
        other_tenant = Tenant.objects.create(name="Tenant B", slug="tenant-b")
        current = TenantSubscription.objects.create(
            tenant=other_tenant,
            plan=self.plan,
            status="active",
            expires_at=timezone.now() + timedelta(days=1),
            is_trial=False,
        )
        output = StringIO()

        call_command("expire_subscriptions", stdout=output)

        due.refresh_from_db()
        current.refresh_from_db()
        self.assertEqual(due.status, "expired")
        self.assertEqual(current.status, "active")
        self.assertIn("Expired 1 subscription(s).", output.getvalue())


class SubscriptionConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.plan = SubscriptionPlan.objects.create(
            name="Starter", price=100000, duration_days=30
        )
        self.tenant = Tenant.objects.create(name="Tenant A", slug="tenant-a")
        self.payment_ids = [
            SubscriptionPayment.objects.create(
                tenant=self.tenant,
                plan=self.plan,
                reference=f"concurrent-subscription-{index}",
                amount=self.plan.price,
            ).pk
            for index in range(2)
        ]

    def test_simultaneous_first_payments_preserve_both_extensions(self):
        barrier = threading.Barrier(2)
        errors = []

        def complete(payment_id):
            close_old_connections()
            try:
                payment = SubscriptionPayment.objects.get(pk=payment_id)
                barrier.wait(timeout=5)
                SubscriptionService.complete_payment(payment)
            except Exception as exc:  # pragma: no cover - asserted below
                errors.append(exc)
            finally:
                close_old_connections()

        threads = [
            threading.Thread(target=complete, args=(payment_id,))
            for payment_id in self.payment_ids
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(errors, [])
        subscription = TenantSubscription.objects.get(tenant=self.tenant)
        self.assertEqual(
            subscription.expires_at,
            subscription.started_at + timedelta(days=60),
        )
        self.assertEqual(
            SubscriptionPayment.objects.filter(status="success").count(), 2
        )
        self.assertEqual(TenantSubscription.objects.count(), 1)
