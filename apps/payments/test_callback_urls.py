from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from rest_framework.test import APITestCase
from apps.vouchers.models import InternetPlan
from apps.vouchers.services import PaystackService
from apps.subscriptions.models import SubscriptionPlan
from apps.tenants.models import Tenant, TenantMembership
from apps.agents.models import AgentProfile, AgentWallet
from .callbacks import payment_callback_url, validate_callback_origin


class CallbackUrlTests(SimpleTestCase):
    @override_settings(PAYSTACK_CALLBACK_ORIGIN="https://portal.example.test/")
    def test_all_return_paths_are_frontend_paths(self):
        for kind, path in {"voucher": "/pay/result", "subscription": "/settings/subscription", "wallet": "/agent/wallet/return"}.items():
            self.assertEqual(payment_callback_url(kind), "https://portal.example.test" + path)

    def test_invalid_origins_are_rejected(self):
        for origin in ("", "/local", "//evil.test", "javascript:alert(1)", "https://user:password@site.test", "https://site.test/path", "https://site.test?next=bad", "https://site.test#fragment", "https://site.test:99999", " https://site.test"):
            with self.subTest(origin=origin), self.assertRaises(ImproperlyConfigured):
                validate_callback_origin(origin)
        self.assertEqual(validate_callback_origin("http://localhost:5173/"), "http://localhost:5173")

    def test_production_requires_explicit_https(self):
        for origin in ("", "http://localhost:5173", "http://portal.example.test"):
            with self.subTest(origin=origin), self.assertRaises(ImproperlyConfigured):
                validate_callback_origin(origin, require_https=True)
        self.assertEqual(validate_callback_origin("https://portal.example.test", require_https=True), "https://portal.example.test")

    @patch("apps.vouchers.services.requests.post")
    def test_provider_receives_callback_url_and_existing_fields(self, post):
        PaystackService(secret_key="test-only").initialize_transaction(email="buyer@example.test", amount=50000, reference="test-reference", metadata={"plan_id": 1}, callback_url="https://portal.example.test/pay/result")
        self.assertEqual(post.call_args.kwargs["json"], {"email": "buyer@example.test", "amount": 50000, "reference": "test-reference", "metadata": {"plan_id": 1}, "callback_url": "https://portal.example.test/pay/result"})


@override_settings(PAYSTACK_CALLBACK_ORIGIN="https://portal.example.test/")
class CheckoutReturnTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Return test", slug="return-test")
        users = get_user_model()
        self.owner = users.objects.create_user(username="owner", email="owner@example.test")
        TenantMembership.objects.create(user=self.owner, tenant=self.tenant, role="owner")
        self.agent_user = users.objects.create_user(username="agent", email="agent@example.test")
        agent = AgentProfile.objects.create(user=self.agent_user, tenant=self.tenant, phone="08012345678", status="active")
        AgentWallet.objects.create(agent=agent, balance=0)
        self.internet = InternetPlan.objects.create(tenant=self.tenant, name="Internet", price=50000, duration_hours=24, rate_limit="5M/10M")
        self.business = SubscriptionPlan.objects.create(name="Business", price=100000, duration_days=30)

    @patch("apps.vouchers.services.requests.post")
    def test_each_checkout_sends_the_correct_callback_to_paystack(self, post):
        post.return_value.json.return_value = {"data": {"authorization_url": "https://checkout.paystack.test/checkout"}}
        flows = [
            (None, "buy-voucher", {"plan_id": self.internet.pk, "email": "buyer@example.test", "callback_url": "https://untrusted.test"}, "/pay/result"),
            (self.owner, "subscription-checkout", {"plan_id": self.business.pk}, "/settings/subscription"),
            (self.agent_user, "agent-wallet-fund", {"amount": 50000}, "/agent/wallet/return"),
        ]
        for user, route, payload, path in flows:
            with self.subTest(route=route):
                self.client.force_authenticate(user)
                response = self.client.post(reverse(route), payload, format="json")
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(post.call_args.kwargs["json"]["callback_url"], "https://portal.example.test" + path)
                self.assertEqual(post.call_args.kwargs["json"]["reference"], response.data["reference"])
