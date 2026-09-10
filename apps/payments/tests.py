import hashlib
import hmac
import json
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.agents.models import AgentProfile, AgentWallet, AgentWalletFundingPayment
from apps.tenants.models import Tenant, TenantSetting
from apps.vouchers.models import InternetPlan, PaymentTransaction, Voucher
from apps.subscriptions.models import SubscriptionPayment, SubscriptionPlan, TenantSubscription
from .delivery import build_credential_email, run_one_delivery
from .models import PaymentDelivery, PaystackWebhookEvent


User = get_user_model()


class PaystackWebhookTests(APITestCase):
    secret = "tenant-paystack-secret"

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Tenant A", slug="tenant-a")
        TenantSetting.objects.create(
            tenant=self.tenant,
            paystack_secret_key=self.secret,
        )
        self.plan = InternetPlan.objects.create(
            tenant=self.tenant,
            name="Standard",
            price=100_000,
            duration_hours=24,
            rate_limit="5M/10M",
        )
        self.payment = PaymentTransaction.objects.create(
            reference="voucher-payment-1",
            amount=self.plan.price,
            customer_email="buyer@example.com",
            tenant=self.tenant,
            plan=self.plan,
        )

    def event(self, reference=None, amount=None, event_id=9001):
        return {
            "event": "charge.success",
            "data": {
                "id": event_id,
                "reference": reference or self.payment.reference,
                "amount": amount if amount is not None else self.payment.amount,
                "currency": "NGN",
                "status": "success",
                "paid_at": "2026-09-04T12:00:00Z",
            },
        }

    def verified(self, payload):
        return {"status": True, "data": payload["data"]}

    def post_event(self, payload, secret=None):
        raw = json.dumps(payload).encode()
        signature = hmac.new(
            (secret or self.secret).encode(), raw, hashlib.sha512
        ).hexdigest()
        return self.client.post(
            reverse("paystack-webhook", args=["route-token"]),
            data=raw,
            content_type="application/json",
            HTTP_X_PAYSTACK_SIGNATURE=signature,
        )

    def test_invalid_signature_is_rejected_before_event_is_stored(self):
        raw = json.dumps(self.event()).encode()

        response = self.client.post(
            reverse("paystack-webhook", args=["route-token"]),
            data=raw,
            content_type="application/json",
            HTTP_X_PAYSTACK_SIGNATURE="invalid",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(PaystackWebhookEvent.objects.exists())
        self.assertFalse(Voucher.objects.exists())

    def test_malformed_json_is_rejected(self):
        response = self.client.post(
            reverse("paystack-webhook", args=["route-token"]),
            data=b"not-json",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(PaystackWebhookEvent.objects.exists())

    @patch("apps.vouchers.services.Radcheck.objects.create")
    @patch("apps.payments.webhooks.get_paystack_service")
    def test_verified_event_fulfills_voucher_once(self, service_factory, radius_create):
        payload = self.event()
        service_factory.return_value.verify_transaction.return_value = self.verified(payload)

        first = self.post_event(payload)
        second = self.post_event(payload)

        self.payment.refresh_from_db()
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(second.json()["status"], "duplicate")
        self.assertEqual(self.payment.status, "success")
        self.assertIsNotNone(self.payment.voucher)
        self.assertEqual(Voucher.objects.count(), 1)
        self.assertEqual(PaystackWebhookEvent.objects.filter(processed=True).count(), 1)
        # Fulfilment queues the access-code email exactly once, even across webhook replays.
        self.assertEqual(PaymentDelivery.objects.filter(payment=self.payment, status="pending").count(), 1)
        # Customer vouchers carry a single readable access code as both username and password.
        voucher = self.payment.voucher
        self.assertEqual(voucher.username, voucher.password)
        self.assertRegex(voucher.username, r"^[ABCDEFGHJKMNPQRTUVWXYZ234678]{8}$")

    @patch("apps.vouchers.services.Radcheck.objects.create")
    @patch("apps.payments.webhooks.get_paystack_service")
    def test_fulfilled_payment_without_email_queues_no_delivery(self, service_factory, radius_create):
        PaymentTransaction.objects.filter(pk=self.payment.pk).update(customer_email="")
        payload = self.event()
        service_factory.return_value.verify_transaction.return_value = self.verified(payload)
        self.assertEqual(self.post_event(payload).status_code, status.HTTP_200_OK)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "success")
        self.assertFalse(PaymentDelivery.objects.exists())

    @patch("apps.payments.webhooks.get_paystack_service")
    def test_amount_mismatch_does_not_fulfill_or_store_event(self, service_factory):
        payload = self.event()
        verification = self.verified(payload)
        verification["data"] = {**payload["data"], "amount": self.payment.amount - 1}
        service_factory.return_value.verify_transaction.return_value = verification

        response = self.post_event(payload)

        self.payment.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.payment.status, "pending")
        self.assertFalse(Voucher.objects.exists())
        self.assertFalse(PaystackWebhookEvent.objects.exists())

    @patch("apps.payments.webhooks.get_paystack_service")
    def test_verification_outage_returns_retryable_failure(self, service_factory):
        service_factory.return_value.verify_transaction.side_effect = OSError("timeout")

        response = self.post_event(self.event())

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertFalse(PaystackWebhookEvent.objects.exists())

    @patch("apps.vouchers.services.Radcheck.objects.create", side_effect=RuntimeError("radius down"))
    @patch("apps.payments.webhooks.get_paystack_service")
    def test_fulfillment_failure_rolls_back_event_payment_and_voucher(
        self, service_factory, radius_create
    ):
        payload = self.event()
        service_factory.return_value.verify_transaction.return_value = self.verified(payload)

        response = self.post_event(payload)

        self.payment.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(self.payment.status, "pending")
        self.assertFalse(Voucher.objects.exists())
        self.assertFalse(PaystackWebhookEvent.objects.exists())

    @patch("apps.payments.webhooks.get_paystack_service")
    def test_wallet_funding_event_credits_wallet_once(self, service_factory):
        user = User.objects.create_user(
            username="agent", email="agent@example.com", password="StrongPass-4821"
        )
        agent = AgentProfile.objects.create(
            user=user,
            tenant=self.tenant,
            phone="08012345678",
            status="active",
        )
        wallet = AgentWallet.objects.create(agent=agent, balance=10_000)
        funding = AgentWalletFundingPayment.objects.create(
            wallet=wallet,
            amount=50_000,
            reference="agent-fund-1",
        )
        payload = self.event(reference=funding.reference, amount=funding.amount, event_id=9002)
        service_factory.return_value.verify_transaction.return_value = self.verified(payload)

        first = self.post_event(payload)
        second = self.post_event(payload)

        wallet.refresh_from_db()
        funding.refresh_from_db()
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.json()["status"], "duplicate")
        self.assertEqual(wallet.balance, 60_000)
        self.assertEqual(funding.status, "success")

    @override_settings(PAYSTACK_SECRET_KEY=secret)
    @patch("apps.payments.webhooks.get_paystack_service")
    def test_subscription_event_activates_subscription_once(self, service_factory):
        plan = SubscriptionPlan.objects.create(
            name="Business", price=250_000, duration_days=30
        )
        payment = SubscriptionPayment.objects.create(
            tenant=self.tenant,
            plan=plan,
            reference="subscription-payment-1",
            amount=plan.price,
        )
        payload = self.event(
            reference=payment.reference,
            amount=payment.amount,
            event_id=9003,
        )
        service_factory.return_value.verify_transaction.return_value = self.verified(payload)

        first = self.post_event(payload)
        second = self.post_event(payload)

        payment.refresh_from_db()
        subscription = TenantSubscription.objects.get(tenant=self.tenant)
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.json()["status"], "duplicate")
        self.assertEqual(payment.status, "success")
        self.assertEqual(payment.subscription, subscription)
        self.assertEqual(subscription.plan, plan)
        self.assertEqual(TenantSubscription.objects.count(), 1)


class PaymentPublicApiTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Tenant A", slug="tenant-a")
        TenantSetting.objects.create(
            tenant=self.tenant,
            paystack_secret_key="tenant-paystack-secret",
        )
        self.plan = InternetPlan.objects.create(
            tenant=self.tenant,
            name="Standard",
            price=100_000,
            duration_hours=24,
            rate_limit="5M/10M",
        )

    @patch("apps.payments.views.get_paystack_service")
    def test_initialize_uses_server_plan_price_and_returns_reference(self, service_factory):
        service_factory.return_value.initialize_transaction.return_value = {
            "data": {"authorization_url": "https://checkout.paystack.test/abc"}
        }

        response = self.client.post(
            reverse("buy-voucher"),
            {
                "plan_id": self.plan.id,
                "email": "buyer@example.com",
                "amount": 1,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payment = PaymentTransaction.objects.get(reference=response.data["reference"])
        self.assertEqual(payment.amount, self.plan.price)
        self.assertEqual(
            service_factory.return_value.initialize_transaction.call_args.kwargs["amount"],
            self.plan.price,
        )

    def test_initialize_rejects_invalid_email_and_plan(self):
        bad_email = self.client.post(
            reverse("buy-voucher"),
            {"plan_id": self.plan.id, "email": "not-an-email"},
            format="json",
        )
        bad_plan = self.client.post(
            reverse("buy-voucher"),
            {"plan_id": 999999, "email": "buyer@example.com"},
            format="json",
        )

        self.assertEqual(bad_email.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(bad_plan.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(PaymentTransaction.objects.exists())

    @patch("apps.payments.views.get_paystack_service")
    def test_provider_failure_keeps_pending_reference_for_reconciliation(self, service_factory):
        service_factory.return_value.initialize_transaction.side_effect = OSError("timeout")

        response = self.client.post(
            reverse("buy-voucher"),
            {"plan_id": self.plan.id, "email": "buyer@example.com"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        payment = PaymentTransaction.objects.get(reference=response.data["reference"])
        self.assertEqual(payment.status, "pending")

    def test_callback_handles_missing_and_unknown_reference(self):
        missing = self.client.get(reverse("payment-callback"))
        unknown = self.client.get(
            reverse("payment-callback"), {"reference": "unknown-reference"}
        )

        self.assertEqual(missing.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(unknown.status_code, status.HTTP_404_NOT_FOUND)

    def fulfilled_payment(self, code="ABCDEFGH", password=None, voucher_status="unused"):
        voucher = Voucher.objects.create(
            tenant=self.tenant, plan=self.plan, username=code, password=password or code, status=voucher_status,
            generation_source="customer",
        )
        return PaymentTransaction.objects.create(
            reference=f"ref-voucher-{voucher.pk}", amount=self.plan.price, customer_email="buyer@example.com",
            tenant=self.tenant, plan=self.plan, voucher=voucher, status="success",
        )

    def test_callback_reveals_access_code_only_while_voucher_is_unused(self):
        pending = PaymentTransaction.objects.create(
            reference="ref-pending", amount=self.plan.price, customer_email="buyer@example.com",
            tenant=self.tenant, plan=self.plan,
        )
        response = self.client.get(reverse("payment-callback"), {"reference": pending.reference})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["status"], "pending")
        self.assertIsNone(response.json()["access_code"])
        self.assertIsNone(response.json()["plan"])

        unused = self.fulfilled_payment("ABCDEFGH")
        response = self.client.get(reverse("payment-callback"), {"reference": unused.reference})
        body = response.json()
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(body["status"], "success")
        self.assertEqual(body["voucher"], "ABCDEFGH")
        self.assertEqual(body["access_code"], "ABCDEFGH")
        self.assertTrue(body["code_revealed"])
        self.assertEqual(body["plan"], {"name": "Standard", "duration_hours": 24, "data_limit": 0})
        self.assertEqual(body["tenant_name"], "Tenant A")
        self.assertEqual(body["customer_email_masked"], "b\u2022\u2022\u2022@example.com")
        self.assertNotIn("buyer@example.com", json.dumps(body))

        used = self.fulfilled_payment("JKMNPQRT", voucher_status="active")
        body = self.client.get(reverse("payment-callback"), {"reference": used.reference}).json()
        self.assertIsNone(body["voucher"])
        self.assertTrue(body["fulfilled"])
        self.assertNotIn("JKMNPQRT", json.dumps(body))
        self.assertIsNone(body["access_code"])
        self.assertFalse(body["code_revealed"])

        # Legacy vouchers with a separate password never leak it through the public endpoint.
        legacy = self.fulfilled_payment("legacyuser", password="separate-secret")
        body = self.client.get(reverse("payment-callback"), {"reference": legacy.reference}).json()
        self.assertIsNone(body["voucher"])
        self.assertTrue(body["fulfilled"])
        self.assertIsNone(body["access_code"])
        self.assertNotIn("separate-secret", json.dumps(body))

    def test_public_results_redact_all_non_unused_credentials(self):
        for voucher_status in ("active", "expired", "disabled"):
            payment = self.fulfilled_payment(f"SECRET-{voucher_status}", voucher_status=voucher_status)
            for endpoint in ("payment-callback", "payment-verify"):
                with self.subTest(voucher_status=voucher_status, endpoint=endpoint):
                    if endpoint == "payment-callback":
                        response = self.client.get(reverse(endpoint), {"reference": payment.reference})
                    else:
                        # Already fulfilled: verification returns without contacting Paystack.
                        response = self.client.post(reverse(endpoint), {"reference": payment.reference}, format="json")
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response["Cache-Control"], "no-store")
                    body = response.json()
                    self.assertTrue(body["fulfilled"])
                    self.assertIsNone(body["voucher"])
                    self.assertIsNone(body["access_code"])
                    self.assertFalse(body["code_revealed"])
                    self.assertNotIn(payment.voucher.username, json.dumps(body))

    def test_credential_email_contains_code_plan_and_reference_once(self):
        payment = self.fulfilled_payment("WXYZ2346")
        subject, text, html = build_credential_email(payment)
        self.assertEqual(subject, "Your Tenant A Wi-Fi access code")
        for body in (text, html):
            self.assertIn("WXYZ2346", body)
            self.assertIn("Standard", body)
            self.assertIn("1 day", body)
            self.assertIn("Unlimited data", body)
            self.assertIn(payment.reference, body)
            self.assertIn("both username and password", body)

    @override_settings(RESEND_API_KEY="re_test_key", DEFAULT_FROM_EMAIL="Tenant <no-reply@example.com>")
    @patch("apps.payments.delivery.requests.post")
    def test_delivery_worker_sends_through_resend_when_configured(self, post):
        post.return_value = Mock(status_code=200, json=lambda: {"id": "email-1"})
        payment = self.fulfilled_payment("R2D2C3P6")
        delivery = PaymentDelivery.objects.create(payment=payment)

        self.assertTrue(run_one_delivery())
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, "accepted")
        post.assert_called_once()
        url, kwargs = post.call_args[0][0], post.call_args[1]
        self.assertEqual(url, "https://api.resend.com/emails")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer re_test_key")
        self.assertEqual(kwargs["headers"]["Idempotency-Key"], f"payment-delivery/{delivery.pk}")
        self.assertEqual(kwargs["json"]["to"], ["buyer@example.com"])
        self.assertEqual(kwargs["json"]["from"], "Tenant <no-reply@example.com>")
        self.assertIn("R2D2C3P6", kwargs["json"]["text"])
        self.assertIn("R2D2C3P6", kwargs["json"]["html"])
        self.assertFalse(run_one_delivery())

    @override_settings(RESEND_API_KEY="re_test_key")
    @patch("apps.payments.delivery.requests.post")
    def test_resend_rejection_fails_delivery_and_outage_leaves_it_unknown(self, post):
        rejected = PaymentDelivery.objects.create(payment=self.fulfilled_payment("AAAA2222"))
        post.return_value = Mock(status_code=422, json=lambda: {"message": "invalid from"})
        self.assertTrue(run_one_delivery())
        rejected.refresh_from_db()
        self.assertEqual((rejected.status, rejected.error_code), ("failed", "email_not_accepted"))

        outage = PaymentDelivery.objects.create(payment=self.fulfilled_payment("BBBB3333"))
        post.return_value = Mock(status_code=503, json=lambda: {})
        self.assertTrue(run_one_delivery())
        outage.refresh_from_db()
        self.assertEqual((outage.status, outage.error_code), ("unknown", "delivery_outcome_unknown"))

    @override_settings(RESEND_API_KEY="", EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_delivery_worker_falls_back_to_django_mail_without_resend(self):
        from django.core import mail

        payment = self.fulfilled_payment("CCCC4444")
        PaymentDelivery.objects.create(payment=payment)
        self.assertTrue(run_one_delivery())
        self.assertEqual(PaymentDelivery.objects.get(payment=payment).status, "accepted")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["buyer@example.com"])
        self.assertIn("CCCC4444", mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].alternatives[0][1], "text/html")
