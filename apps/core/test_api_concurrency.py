from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.db import connection, connections, close_old_connections
from django.test import TransactionTestCase
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework.test import APIClient
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.core.commands import idempotent
from apps.core.models import AuditEvent, ApiCommand
from apps.tenants.models import Tenant, TenantMembership
from apps.vouchers.models import InternetPlan, Voucher, PaymentTransaction, Radcheck
from apps.payments.recovery import fulfill_verified_voucher
from apps.agents.models import AgentProfile, AgentWallet, AgentWalletFundingPayment
from apps.agents.services import AgentService


class ConcurrentApiTests(TransactionTestCase):
    """Independent PostgreSQL connections exercise actual locks and rollback."""

    def setUp(self):
        self.assertEqual(connection.vendor, "postgresql")
        self.assertIn("test", connection.settings_dict["NAME"])
        self.created_radius_table = Radcheck._meta.db_table not in connection.introspection.table_names()
        if self.created_radius_table:
            with connection.schema_editor() as editor:
                editor.create_model(Radcheck)
        self.user = get_user_model().objects.create_user("concurrent", "concurrent@example.com", "Strong-Password-2819")
        self.tenant = Tenant.objects.create(name="Concurrent", slug="concurrent")
        self.plan = InternetPlan.objects.create(tenant=self.tenant, name="Day", price=5000, duration_hours=24, rate_limit="1M/1M")

    def tearDown(self):
        if self.created_radius_table:
            with connection.schema_editor() as editor:
                editor.delete_model(Radcheck)

    def parallel(self, function):
        barrier = Barrier(2)
        def run():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return function()
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(run) for _ in range(2)]
            return [future.result(timeout=20) for future in futures]

    def test_concurrent_verification_creates_one_voucher_and_radius_identity(self):
        from apps.vouchers.terms import snapshot_plan
        payment = PaymentTransaction.objects.create(tenant=self.tenant, plan=self.plan, reference="same-payment", amount=5000, customer_email="buyer@example.com", purchased_terms=snapshot_plan(self.plan))
        InternetPlan.objects.filter(pk=self.plan.pk).update(is_active=False, duration_hours=1)
        verified = {"reference": payment.reference, "status": "success", "currency": "NGN", "amount": 5000}
        results = self.parallel(lambda: fulfill_verified_voucher(PaymentTransaction.objects.get(pk=payment.pk), verified).voucher_id)
        self.assertEqual(results[0], results[1])
        self.assertEqual(Voucher.objects.count(), 1)
        self.assertEqual(Voucher.objects.get().service_terms['duration_hours'], 24)
        self.assertEqual(Radcheck.objects.filter(attribute="Cleartext-Password").count(), 1)

    def test_concurrent_wallet_spending_cannot_overdraw(self):
        agent = AgentProfile.objects.create(user=self.user, tenant=self.tenant, status="active", phone="08012345678")
        wallet = AgentWallet.objects.create(agent=agent, balance=5000)
        def spend():
            try:
                AgentService.generate_voucher_from_wallet(AgentProfile.objects.get(pk=agent.pk), self.plan.pk)
                return "issued"
            except ValueError:
                return "insufficient"
        self.assertCountEqual(self.parallel(spend), ["issued", "insufficient"])
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, 0)
        self.assertEqual(Voucher.objects.count(), 1)

    def test_duplicate_funding_completion_credits_once(self):
        agent = AgentProfile.objects.create(user=self.user, tenant=self.tenant, status="active", phone="08012345678")
        wallet = AgentWallet.objects.create(agent=agent)
        payment = AgentWalletFundingPayment.objects.create(wallet=wallet, amount=5000, reference="fund-once")
        results = self.parallel(lambda: AgentService.complete_wallet_funding(payment))
        self.assertCountEqual(results, [True, False])
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, 5000)

    def test_radius_failure_rolls_back_wallet_voucher_and_allocation(self):
        agent = AgentProfile.objects.create(user=self.user, tenant=self.tenant, status="active", phone="08012345678")
        wallet = AgentWallet.objects.create(agent=agent, balance=10000)
        original = Radcheck.objects.create
        calls = 0
        def fail_second(**kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("simulated database adapter failure")
            return original(**kwargs)
        with patch("apps.vouchers.services.Radcheck.objects.create", side_effect=fail_second):
            with self.assertRaises(RuntimeError):
                AgentService.generate_voucher_from_wallet(agent, self.plan.pk)
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, 10000)
        self.assertFalse(Voucher.objects.exists())
        self.assertFalse(Radcheck.objects.exists())
        self.assertFalse(agent.allocations.exists())

    def test_manual_voucher_crud_keeps_radius_rows_in_sync(self):
        TenantMembership.objects.create(user=self.user, tenant=self.tenant, role="owner")
        client = APIClient()
        client.force_authenticate(self.user)
        result = client.post("/api/v1/vouchers/", {"username": "manual-voucher", "password": "original-password", "plan": self.plan.pk, "device_limit": 1}, format="json")
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(Radcheck.objects.get(username="manual-voucher", attribute="Cleartext-Password").value, "original-password")
        path = f"/api/v1/vouchers/{result.data['id']}/"
        changed = client.patch(path, {"username": "renamed-voucher", "password": "changed-password"}, format="json")
        self.assertEqual(changed.status_code, 200, changed.data)
        self.assertFalse(Radcheck.objects.filter(username="manual-voucher").exists())
        self.assertEqual(Radcheck.objects.get(username="renamed-voucher", attribute="Cleartext-Password").value, "changed-password")
        self.assertEqual(client.delete(path).status_code, 204)
        self.assertFalse(Radcheck.objects.filter(username="renamed-voucher").exists())

    def test_inflight_idempotency_key_cannot_execute_twice(self):
        entered, release = Event(), Event()
        user = self.user
        class CommandView(APIView):
            @idempotent
            def post(self, request):
                entered.set()
                if not release.wait(timeout=10):
                    raise RuntimeError("test synchronization timed out")
                AuditEvent.objects.create(actor=request.user, action="command.executed", resource="test")
                return Response({"completed": True}, status=201)
        def invoke():
            close_old_connections()
            try:
                request = APIRequestFactory().post("/api/v1/test-command/", {"quantity": 1}, format="json", HTTP_IDEMPOTENCY_KEY="concurrency-key-0001")
                force_authenticate(request, user=user)
                return CommandView.as_view()(request)
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(invoke)
            try:
                self.assertTrue(entered.wait(timeout=10))
                second = pool.submit(invoke).result(timeout=10)
                self.assertEqual(second.status_code, 409)
            finally:
                release.set()
            self.assertEqual(first.result(timeout=10).status_code, 201)
        replay = invoke()
        self.assertEqual(replay.status_code, 201)
        self.assertEqual(replay["Idempotency-Replayed"], "true")
        self.assertEqual(AuditEvent.objects.filter(action="command.executed").count(), 1)
        self.assertEqual(ApiCommand.objects.count(), 1)
