from datetime import timedelta
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class LimitsMigrationTests(TransactionTestCase):
    def test_existing_purchases_and_access_are_preserved(self):
        before = [("subscriptions", "0002_subscription_payment_purchase_target")]
        after = [("subscriptions", "0005_subscriptionperiod_superseded")]
        executor = MigrationExecutor(connection)
        executor.migrate(before)
        try:
            apps = executor.loader.project_state(before).apps
            tenant = apps.get_model("tenants", "Tenant").objects.create(name="Legacy", slug="legacy-migration")
            plan = apps.get_model("subscriptions", "SubscriptionPlan").objects.create(name="Old terms", price=20000, duration_days=15)
            apps.get_model("subscriptions", "TenantSubscription").objects.create(tenant_id=tenant.pk, plan_id=plan.pk, started_at=timezone.now()-timedelta(days=2), expires_at=timezone.now()+timedelta(days=13), status="active")
            payment = apps.get_model("subscriptions", "SubscriptionPayment").objects.create(tenant_id=tenant.pk, plan_id=plan.pk, reference="legacy-migration", amount=15000)
            executor = MigrationExecutor(connection)
            executor.migrate(after)
            apps = executor.loader.project_state(after).apps
            upgraded = apps.get_model("subscriptions", "SubscriptionPayment").objects.get(pk=payment.pk)
            self.assertEqual(upgraded.plan_terms["price"], 15000)
            self.assertEqual(upgraded.plan_terms["duration_days"], 15)
            period = apps.get_model("subscriptions", "SubscriptionPeriod").objects.get(tenant_id=tenant.pk)
            self.assertIsNone(period.terms["max_routers"])
            self.assertIsNone(period.terms["daily_voucher_print_limit"])
            self.assertTrue(period.terms["whatsapp_enabled"])
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
