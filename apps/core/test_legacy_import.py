from unittest.mock import Mock, patch
from django.test import TestCase, SimpleTestCase, override_settings
from django.core.exceptions import ImproperlyConfigured
from apps.tenants.models import Tenant
from apps.routers.secret_store import secret_store
from apps.vouchers.services import PaystackService
from apps.whatsapp_routing.provider import send_payload, ProviderFailure
from .legacy_import import execute_import, coverage, draft_plan, ImportBlocked, digest
from .models import LegacyImportRun, LegacyRecord


@override_settings(WHATSAPP_CONSUMER_ENABLED=False, WHATSAPP_SEND_ENABLED=False, RADIUS_REST_ENABLED=False)
class LegacyImportTests(TestCase):
    def setUp(self):
        self.archive = {'format':'yarotech-legacy-source-v1', 'tables': {
            'vouchers_tenant': {'pk':'id','columns':['id','name','slug'], 'rows':[{'id':7,'name':'Imported','slug':'imported'}]}}}
        self.sha = digest(self.archive)
        self.plan = draft_plan(self.archive, self.sha)
        self.plan['records'] = [{'source':'vouchers_tenant:7', 'model':'tenants.Tenant',
            'fields':{'name':{'$source':'name'}, 'slug':{'$source':'slug'}}}]

    def test_rehearsal_rolls_back_and_apply_replays_without_duplication(self):
        self.assertFalse(execute_import(self.archive, self.plan, self.sha)['applied'])
        self.assertFalse(Tenant.objects.exists())
        self.assertFalse(LegacyImportRun.objects.exists())
        self.assertTrue(execute_import(self.archive, self.plan, self.sha, apply=True)['applied'])
        self.assertTrue(execute_import(self.archive, self.plan, self.sha, apply=True)['already_imported'])
        self.assertEqual(Tenant.objects.count(), 1)
        evidence = LegacyRecord.objects.get()
        self.assertNotIn('Imported', evidence.payload_encrypted)
        self.assertIn('Imported', secret_store.decrypt(evidence.payload_encrypted))

    def test_unmapped_finance_cannot_be_archived_away(self):
        self.archive['tables']['vouchers_agentwallet'] = {'pk':'id','rows':[{'id':1,'balance_kobo':500}]}
        with self.assertRaisesMessage(ImportBlocked, 'Unmapped source tables'):
            execute_import(self.archive, self.plan, self.sha, apply=True)
        self.plan['archive_only'] = [{'table':'vouchers_agentwallet','reason':'Skip'}]
        with self.assertRaisesMessage(ImportBlocked, 'Archive-only'):
            coverage(self.archive, self.plan, self.sha)
        self.assertFalse(Tenant.objects.exists())

    def test_financial_mismatch_rolls_back_every_record(self):
        self.plan['records'][0]['fields']['phone'] = '0'
        self.plan['reconciliation'] = [{'source_table':'vouchers_tenant','source_column':'id',
            'target_model':'tenants.Tenant','target_field':'phone'}]
        with self.assertRaisesMessage(ImportBlocked, 'Reconciliation mismatch'):
            execute_import(self.archive, self.plan, self.sha, apply=True)
        self.assertFalse(Tenant.objects.exists())
        self.assertFalse(LegacyRecord.objects.exists())

    def test_source_mismatch_or_changed_completed_plan_is_blocked(self):
        with self.assertRaisesMessage(ImportBlocked, 'digest mismatch'):
            execute_import(self.archive, self.plan, 'different')
        execute_import(self.archive, self.plan, self.sha, apply=True)
        self.plan['records'][0]['fields']['name']='Changed'
        with self.assertRaisesMessage(ImportBlocked, 'identity requires reconciliation'):
            execute_import(self.archive, self.plan, self.sha, apply=True)
        self.assertEqual(Tenant.objects.get().name, 'Imported')

    def test_enabled_consumers_block_import(self):
        with override_settings(WHATSAPP_CONSUMER_ENABLED=True):
            with self.assertRaisesMessage(ImportBlocked, 'Disable message'):
                execute_import(self.archive, self.plan, self.sha)
        with override_settings(RADIUS_REST_ENABLED=True):
            with self.assertRaisesMessage(ImportBlocked, 'Disable RADIUS'):
                execute_import(self.archive, self.plan, self.sha)


@override_settings(STAGING_MODE=True, STAGING_WHATSAPP_RECIPIENTS=[])
class StagingProviderTests(SimpleTestCase):
    def test_live_payment_key_is_rejected_before_network(self):
        with patch('apps.vouchers.services.requests.post') as network:
            with self.assertRaises(ImproperlyConfigured):
                PaystackService('sk_live_example')
            network.assert_not_called()
        self.assertEqual(PaystackService('sk_test_example').secret_key, 'sk_test_example')

    def test_messages_outside_allowlist_never_reach_provider(self):
        with patch('apps.whatsapp_routing.provider.requests.post') as network:
            with self.assertRaises(ProviderFailure):
                send_payload(Mock(), {'to':'2348000000000'})
            network.assert_not_called()
        with override_settings(STAGING_WHATSAPP_RECIPIENTS=['']):
            with self.assertRaises(ProviderFailure):
                send_payload(Mock(), {'to':''})
