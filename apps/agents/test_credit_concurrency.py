import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.contrib.auth import get_user_model
from django.db import close_old_connections
from django.test import TransactionTestCase, skipUnlessDBFeature
from rest_framework.exceptions import ValidationError
from apps.tenants.models import Tenant, TenantMembership
from apps.subscriptions.test_support import grant_test_subscription
from apps.vouchers.models import InternetPlan
from .tests import AgentFixtureMixin
from .models import AgentCreditAccount, AgentCreditBatch, AgentCreditLedger
from .credit import execute_credit


@skipUnlessDBFeature('has_select_for_update')
class CreditConcurrencyTests(AgentFixtureMixin, TransactionTestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name='Credit race', slug='credit-race')
        grant_test_subscription(self.tenant)
        _, self.agent, _ = self.create_agent()
        self.owner = get_user_model().objects.create_user(username='credit-owner', email='credit-owner@race.test')
        TenantMembership.objects.create(user=self.owner, tenant=self.tenant, role='owner')
        self.plan = InternetPlan.objects.create(tenant=self.tenant, name='Daily', price=10000, duration_hours=24, agent_enabled=True)
        self.account = AgentCreditAccount.objects.create(agent=self.agent, credit_limit=9000)

    def run_race(self, keys):
        barrier = Barrier(2)
        def issue(key):
            close_old_connections()
            try:
                tenant = Tenant.objects.get(pk=self.tenant.pk)
                actor = get_user_model().objects.get(pk=self.owner.pk)
                barrier.wait(timeout=10)
                try:
                    return execute_credit(tenant, self.agent.pk, actor, 'issue', key,
                        {'plan_id': self.plan.pk, 'quantity': 1, 'expected_total': 9000}).pk
                except ValidationError:
                    return None
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(issue, keys))

    def test_concurrent_issuance_cannot_exceed_limit(self):
        results = self.run_race([str(uuid.uuid4()), str(uuid.uuid4())])
        self.assertEqual(sum(result is not None for result in results), 1)
        self.account.refresh_from_db()
        self.assertEqual(self.account.current_balance, 9000)
        self.assertEqual(AgentCreditBatch.objects.count(), 1)

    def test_same_request_creates_one_obligation(self):
        key = str(uuid.uuid4())
        results = self.run_race([key, key])
        self.assertIsNotNone(results[0])
        self.assertEqual(results[0], results[1])
        self.assertEqual(AgentCreditLedger.objects.count(), 1)
