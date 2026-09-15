from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class WalletExpansionMigrationTests(TransactionTestCase):
    def test_existing_balance_and_sale_are_preserved_without_invented_history(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        before = [('agents', '0002_initial'), ('vouchers', '0007_voucher_code_formats')]
        try:
            executor.migrate(before)
            old = executor.loader.project_state(before).apps
            user = old.get_model('accounts', 'User').objects.create(username='migration-agent', email='migration@agent.test')
            tenant = old.get_model('tenants', 'Tenant').objects.create(name='Preserved', slug='preserved-wallet')
            agent = old.get_model('agents', 'AgentProfile').objects.create(user_id=user.pk, tenant_id=tenant.pk, phone='08000000000', commission_rate='17.50')
            wallet = old.get_model('agents', 'AgentWallet').objects.create(agent_id=agent.pk, balance=876543)
            credit = old.get_model('agents', 'AgentCreditAccount').objects.create(agent_id=agent.pk, credit_limit=50000, current_balance=-1234)
            ledger = old.get_model('agents', 'AgentCreditLedger').objects.create(credit_account_id=credit.pk, amount=-1234, description='Retained historical credit')
            plan = old.get_model('vouchers', 'InternetPlan').objects.create(tenant_id=tenant.pk, name='Old', price=100000, duration_hours=24)
            voucher = old.get_model('vouchers', 'Voucher').objects.create(tenant_id=tenant.pk, plan_id=plan.pk, username='OLDCODE1', password='old')
            allocation = old.get_model('agents', 'AgentVoucherAllocation').objects.create(agent_id=agent.pk, voucher_id=voucher.pk, amount_charged=12345, commission_earned=222)
            old.get_model('agents', 'AgentWalletFundingPayment').objects.create(wallet_id=wallet.pk, amount=54321, reference='old-funding-migration', status='success')
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            new = executor.loader.project_state(latest).apps
            self.assertEqual(new.get_model('agents', 'AgentWallet').objects.get(pk=wallet.pk).balance, 876543)
            saved = new.get_model('agents', 'AgentVoucherAllocation').objects.get(pk=allocation.pk)
            self.assertEqual((saved.amount_charged, saved.commission_earned), (12345, 222))
            self.assertIsNone(saved.commission_rate_snapshot)
            self.assertIsNone(saved.retail_price)
            self.assertIsNone(saved.wallet_transaction_id)
            self.assertFalse(new.get_model('agents', 'AgentWalletTransaction').objects.exists())
            saved_credit = new.get_model('agents', 'AgentCreditAccount').objects.get(pk=credit.pk)
            self.assertEqual((saved_credit.credit_limit, saved_credit.current_balance), (50000, -1234))
            self.assertEqual(new.get_model('agents', 'AgentCreditLedger').objects.get(pk=ledger.pk).amount, -1234)
            self.assertIsNone(saved.credit_batch_id)
            self.assertFalse(new.get_model('agents', 'AgentCreditBatch').objects.exists())
            self.assertFalse(new.get_model('agents', 'AgentCreditMovement').objects.exists())
        finally:
            MigrationExecutor(connection).migrate(latest)
