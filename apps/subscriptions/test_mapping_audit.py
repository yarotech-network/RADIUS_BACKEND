import json
from io import StringIO
from django.test import TestCase
from django.core.management import call_command, CommandError
from apps.tenants.models import Tenant
from .models import SubscriptionPeriod, SubscriptionPayment
from .test_support import grant_test_subscription


class SubscriptionMappingAuditTests(TestCase):
    def audit(self, blocked=False):
        output = StringIO()
        if blocked:
            with self.assertRaises(CommandError):
                call_command('audit_subscription_compatibility', stdout=output)
        else:
            call_command('audit_subscription_compatibility', stdout=output)
        return json.loads(output.getvalue())

    def test_missing_subscription_is_reported_without_customer_details_or_writes(self):
        tenant = Tenant.objects.create(name='Do not expose name', slug='hidden-name')
        report = self.audit(blocked=True)
        self.assertEqual(report['sample_ids']['missing_subscription_tenant'], [tenant.pk])
        self.assertNotIn(tenant.name, json.dumps(report))
        self.assertFalse(hasattr(tenant, 'subscription'))

    def test_explicit_platform_exemption_and_complete_period_pass(self):
        Tenant.objects.create(name='Platform', slug='platform', is_platform_admin=True)
        tenant = Tenant.objects.create(name='Paid', slug='paid')
        grant_test_subscription(tenant)
        self.assertEqual(self.audit()['counts'], {})

    def test_overlap_is_reported_without_modifying_history(self):
        tenant = Tenant.objects.create(name='Paid', slug='paid')
        sub = grant_test_subscription(tenant)
        original = SubscriptionPeriod.objects.get(tenant=tenant)
        SubscriptionPeriod.objects.create(tenant=tenant, plan=sub.plan, starts_at=original.starts_at,
            ends_at=original.ends_at, terms=original.terms)
        self.assertEqual(self.audit(blocked=True)['counts']['overlapping_period'], 1)
        self.assertEqual(SubscriptionPeriod.objects.filter(superseded=False).count(), 2)

    def test_missing_snapshot_and_success_without_period_are_reported(self):
        tenant = Tenant.objects.create(name='Paid', slug='paid')
        sub = grant_test_subscription(tenant)
        payment = SubscriptionPayment.objects.create(tenant=tenant, plan=sub.plan, reference='secret-reference',
            amount=100, status='success')
        report = self.audit(blocked=True)
        self.assertEqual(report['counts']['payment_without_snapshot'], 1)
        self.assertEqual(report['counts']['successful_payment_without_period'], 1)
        self.assertNotIn(payment.reference, json.dumps(report))
        payment.refresh_from_db()
        self.assertIsNone(payment.plan_terms)

    def test_scope_mismatch_is_reported(self):
        tenant = Tenant.objects.create(name='A', slug='a')
        other = Tenant.objects.create(name='B', slug='b')
        sub = grant_test_subscription(tenant)
        other_sub = grant_test_subscription(other)
        payment = SubscriptionPayment.objects.create(tenant=other, plan=other_sub.plan,
            subscription=sub, reference='cross-scope', amount=100, status='success', plan_terms={})
        period = SubscriptionPeriod.objects.get(tenant=tenant)
        period.payment = payment
        period.save()
        report = self.audit(blocked=True)
        self.assertEqual(report['counts']['period_payment_scope_mismatch'], 1)
        self.assertEqual(report['counts']['payment_subscription_scope_mismatch'], 1)
