from unittest.mock import patch
from django.core.cache import cache
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase
from apps.tenants.models import Tenant, TenantMembership
from .models import SubscriptionPayment, SubscriptionPlan, SubscriptionPeriod
from .entitlements import snapshot_plan


class SubscriptionVerificationTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.tenant = Tenant.objects.create(name="Verify", slug="verify")
        self.owner = get_user_model().objects.create_user(username="verify-owner")
        TenantMembership.objects.create(user=self.owner, tenant=self.tenant, role="owner")
        self.plan = SubscriptionPlan.objects.create(name="Bought", price=10000, duration_days=12, max_routers=2)
        self.payment = SubscriptionPayment.objects.create(tenant=self.tenant, plan=self.plan, reference="subscription-verify", amount=self.plan.price, plan_terms=snapshot_plan(self.plan))
        self.url = reverse("subscription-payment-verify", args=[self.payment.reference])
        self.client.force_authenticate(self.owner)
        self.provider = patch("apps.payments.services.get_paystack_service").start()
        self.addCleanup(patch.stopall)
        self.data = {"reference": self.payment.reference, "amount": 10000, "currency": "NGN", "status": "success"}
        self.provider.return_value.verify_transaction.side_effect = lambda ref: {"status": True, "data": self.data}

    def test_missing_webhook_recovers_saved_terms_once(self):
        self.plan.duration_days = 90
        self.plan.max_routers = 99
        self.plan.save()
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "success")
        period = SubscriptionPeriod.objects.get(payment=self.payment)
        self.assertEqual((period.ends_at-period.starts_at).days, 12)
        self.assertEqual(period.terms["max_routers"], 2)
        again = self.client.post(self.url)
        self.assertEqual(again.data, response.data)
        self.assertEqual(SubscriptionPeriod.objects.count(), 1)
        self.provider.assert_called_once_with()

    def test_non_success_does_not_activate(self):
        for state in ["pending", "ongoing", "abandoned", "failed", "reversed"]:
            self.data["status"] = state
            response = self.client.post(self.url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["status"], "pending")
        self.assertFalse(SubscriptionPeriod.objects.exists())

    def test_mismatch_does_not_activate(self):
        for key, value in [("reference", "another-payment"), ("amount", 1), ("amount", "10000"), ("currency", "USD")]:
            with self.subTest(key=key, value=value):
                original = self.data[key]
                self.data[key] = value
                self.assertEqual(self.client.post(self.url).status_code, 409)
                self.data[key] = original
        self.assertFalse(SubscriptionPeriod.objects.exists())

    def test_unavailable_and_malformed_provider_allow_retry(self):
        for result in [None, {"status": False}, {"status": True, "data": []}]:
            self.provider.return_value.verify_transaction.side_effect = None
            self.provider.return_value.verify_transaction.return_value = result
            self.assertEqual(self.client.post(self.url).status_code, 503)
        self.provider.return_value.verify_transaction.side_effect = OSError("unavailable")
        self.assertEqual(self.client.post(self.url).status_code, 503)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "pending")
        self.assertFalse(SubscriptionPeriod.objects.exists())
        self.provider.return_value.verify_transaction.side_effect = lambda ref: {"status": True, "data": self.data}
        self.assertEqual(self.client.post(self.url).data["status"], "success")

    def test_owner_boundary_and_get_is_read_only(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.client.get(reverse("subscription-payment-status", args=[self.payment.reference]))
        other = Tenant.objects.create(name="Other", slug="verify-other")
        self.payment.tenant = other
        self.payment.save()
        self.assertEqual(self.client.post(self.url).status_code, 404)
        TenantMembership.objects.filter(user=self.owner).update(role="manager")
        self.owner.refresh_from_db()
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.post(self.url).status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post(self.url).status_code, 401)
        self.provider.assert_not_called()

    def test_verification_rate_limited(self):
        self.data["status"] = "pending"
        for _ in range(10):
            self.assertEqual(self.client.post(self.url).status_code, 200)
        self.assertEqual(self.client.post(self.url).status_code, 429)
