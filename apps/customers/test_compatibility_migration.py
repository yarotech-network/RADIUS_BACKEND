from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class CustomerCompatibilityMigrationTests(TransactionTestCase):
    def test_populated_customer_voucher_and_payment_are_preserved_without_inferred_links(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        before = [('customers','0003_deviceaccesssync_deviceaccesssession'), ('vouchers','0007_voucher_code_formats')]
        try:
            executor.migrate(before)
            old = executor.loader.project_state(before).apps
            tenant = old.get_model('tenants','Tenant').objects.create(name='Retained', slug='retained-customers')
            customer = old.get_model('customers','Customer').objects.create(tenant_id=tenant.pk, reference='EXISTING',
                name='Retained Name', email='same@example.test', notes='Retain this note')
            plan = old.get_model('vouchers','InternetPlan').objects.create(tenant_id=tenant.pk, name='Plan', price=10000, duration_hours=24)
            voucher = old.get_model('vouchers','Voucher').objects.create(tenant_id=tenant.pk, plan_id=plan.pk,
                username='RETAINCODE', password='RetainPass', status='used')
            payment = old.get_model('vouchers','PaymentTransaction').objects.create(tenant_id=tenant.pk, plan_id=plan.pk,
                reference='retained-payment', customer_email='same@example.test', amount=10000, voucher_id=voucher.pk)
            created_at = customer.created_at
            MigrationExecutor(connection).migrate(latest)
            new = MigrationExecutor(connection).loader.project_state(latest).apps
            saved = new.get_model('customers','Customer').objects.get(pk=customer.pk)
            self.assertEqual(saved.name, 'Retained Name')
            self.assertEqual(saved.notes, 'Retain this note')
            self.assertEqual(saved.created_at, created_at)
            self.assertEqual(saved.mac_address, '')
            self.assertEqual(saved.legacy_source, '')
            self.assertIsNone(saved.legacy_id)
            saved_voucher = new.get_model('vouchers','Voucher').objects.get(pk=voucher.pk)
            self.assertEqual(saved_voucher.username, 'RETAINCODE')
            self.assertEqual(saved_voucher.password, 'RetainPass')
            self.assertEqual(saved_voucher.status, 'used')
            self.assertIsNone(saved_voucher.customer_id)
            saved_payment = new.get_model('vouchers','PaymentTransaction').objects.get(pk=payment.pk)
            self.assertEqual(saved_payment.voucher_id, voucher.pk)
            self.assertEqual(saved_payment.amount, 10000)
            self.assertIsNone(saved_payment.customer_id)
        finally:
            MigrationExecutor(connection).migrate(latest)
