"""Rehearse conflict detection only on the disposable test database."""
from io import StringIO
import importlib
import json
from types import SimpleNamespace
from django.test import TransactionTestCase
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.core.management import call_command


class CodeFormatMigrationTests(TransactionTestCase):
    def test_conflicting_legacy_codes_are_reported_without_renaming(self):
        executor = MigrationExecutor(connection)
        before = [('vouchers', '0006_voucher_lifecycle_preservation')]
        after = [('vouchers', '0007_voucher_code_formats')]
        executor.migrate(before)
        old_apps = executor.loader.project_state(before).apps
        Tenant = old_apps.get_model('tenants', 'Tenant')
        Plan = old_apps.get_model('vouchers', 'InternetPlan')
        Voucher = old_apps.get_model('vouchers', 'Voucher')
        duplicate_id = None
        try:
            tenant = Tenant.objects.create(name='Migration', slug='format-migration')
            plan = Plan.objects.create(tenant_id=tenant.pk, name='Day', price=100, duration_hours=24)
            first = Voucher.objects.create(tenant_id=tenant.pk, plan_id=plan.pk, username='PreserveMe', password='original')
            duplicate = Voucher.objects.create(tenant_id=tenant.pk, plan_id=plan.pk, username='PRESERVEME', password='also-original')
            duplicate_id = duplicate.pk
            output = StringIO()
            call_command('audit_voucher_code_identities', stdout=output)
            self.assertEqual(json.loads(output.getvalue())['conflicting_groups'], 1)
            self.assertNotIn('PreserveMe', output.getvalue())
            migration = importlib.import_module('apps.vouchers.migrations.0007_voucher_code_formats')
            with self.assertRaisesRegex(RuntimeError, 'Conflicting voucher identities'):
                migration.check_existing_identities(old_apps, SimpleNamespace(connection=connection))
            first.refresh_from_db()
            duplicate.refresh_from_db()
            self.assertEqual((first.username, first.password), ('PreserveMe', 'original'))
            self.assertEqual((duplicate.username, duplicate.password), ('PRESERVEME', 'also-original'))
        finally:
            if duplicate_id:
                Voucher.objects.filter(pk=duplicate_id).delete()
            MigrationExecutor(connection).migrate(after)
