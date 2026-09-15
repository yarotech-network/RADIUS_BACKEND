from unittest.mock import patch
from django.test import TestCase
from django.db import transaction, IntegrityError
from django.core.exceptions import ValidationError
from apps.tenants.models import Tenant, TenantSetting
from apps.subscriptions.test_support import grant_test_subscription
from .models import InternetPlan, Voucher, Radcheck
from .code_formats import generate_code, LEGACY_ALPHABET
from .services import VoucherService
from .terms import snapshot_plan
from .serializers import InternetPlanSerializer
from .radius_test_support import RadiusTablesMixin


class CodeFormatTests(RadiusTablesMixin, TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name='Formats', slug='formats')
        grant_test_subscription(self.tenant)
        self.plan = InternetPlan.objects.create(tenant=self.tenant, name='Daily', price=1000, duration_hours=24)

    def issue(self, quantity=1, **kwargs):
        return VoucherService.generate_vouchers(self.tenant, self.plan.pk, quantity, **kwargs)

    def test_numeric_alphabetic_and_mixed_formats(self):
        for _ in range(10):
            self.assertRegex(generate_code('xy','numeric'), r'^XY[0-9]{8}$')
            self.assertRegex(generate_code('','alphabetic'), r'^[A-Z]{6}$')
            mixed = generate_code('', 'alphanumeric')
            self.assertEqual(len(mixed), 6)
            self.assertTrue(any(c.isdigit() for c in mixed))
            self.assertTrue(any(c.isalpha() for c in mixed))
        with self.assertRaises(ValidationError):
            generate_code('bad-prefix', 'numeric')
        self.assertFalse(InternetPlanSerializer(data={'voucher_code_format':'unknown'}).is_valid())

    def test_business_default_is_resolved_at_reservation(self):
        setting = TenantSetting.objects.create(tenant=self.tenant, default_voucher_code_format='numeric')
        self.plan.voucher_code_format = 'tenant_default'
        self.plan.voucher_prefix = 'DAY'
        self.plan.save()
        terms = snapshot_plan(self.plan)
        setting.default_voucher_code_format = 'alphabetic'
        setting.save()
        voucher = self.issue(source='customer', purchased_terms=terms)[0]
        self.assertRegex(voucher.username, r'^DAY[0-9]{8}$')
        self.assertEqual(voucher.password, voucher.username)
        self.assertEqual(voucher.purchased_terms['voucher_code_format'], 'numeric')
        new = self.issue()[0]
        self.assertRegex(new.username, r'^DAY[A-Z]{6}$')

    def test_paid_format_and_prefix_survive_plan_edits(self):
        self.plan.voucher_code_format = 'numeric'
        self.plan.voucher_prefix = 'OLD'
        self.plan.save()
        terms = snapshot_plan(self.plan)
        self.plan.voucher_code_format = 'alphabetic'
        self.plan.voucher_prefix = 'NEW'
        self.plan.save()
        voucher = self.issue(source='customer', purchased_terms=terms)[0]
        self.assertRegex(voucher.username, r'^OLD[0-9]{8}$')

    def test_older_order_without_format_keeps_previous_generation(self):
        terms = snapshot_plan(self.plan)
        terms.pop('voucher_code_format')
        terms.pop('voucher_prefix')
        self.plan.voucher_code_format = 'numeric'
        self.plan.voucher_prefix = 'NEW'
        self.plan.save()
        voucher = self.issue(source='customer', purchased_terms=terms)[0]
        self.assertEqual(len(voucher.username), 8)
        self.assertTrue(set(voucher.username) <= set(LEGACY_ALPHABET))

    def test_collisions_skip_existing_codes_and_radius_only_identities(self):
        existing = Voucher.objects.create(tenant=self.tenant, plan=self.plan, username='reserved', password='original')
        Radcheck.objects.create(username='RADIUSONLY', attribute='Cleartext-Password', op=':=', value='old')
        with patch.object(Voucher, 'generate_credentials', side_effect=[('RESERVED','RESERVED'),('radiusonly','radiusonly'),('FREECODE','FREECODE')]) as generate:
            voucher = self.issue()[0]
        self.assertEqual(generate.call_count, 3)
        self.assertEqual(voucher.username, 'FREECODE')
        existing.refresh_from_db()
        self.assertEqual(existing.password, 'original')
        self.assertEqual(Radcheck.objects.get(username='RADIUSONLY').value, 'old')

    def test_casefold_constraint_prevents_duplicate_identity(self):
        Voucher.objects.create(tenant=self.tenant, plan=self.plan, username='reserved', password='original')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Voucher.objects.create(tenant=self.tenant, plan=self.plan, username='RESERVED', password='new')

    def test_exhaustion_rolls_back_whole_batch_and_credentials(self):
        Voucher.objects.create(tenant=self.tenant, plan=self.plan, username='RESERVED', password='original')
        attempts = [('FIRSTCODE','FIRSTCODE')]+[('reserved','reserved')]*100
        with patch.object(Voucher, 'generate_credentials', side_effect=attempts) as generate:
            with self.assertRaises(ValidationError):
                self.issue(2)
        self.assertEqual(generate.call_count, 101)
        self.assertFalse(Voucher.objects.filter(username='FIRSTCODE').exists())
        self.assertFalse(Radcheck.objects.filter(username='FIRSTCODE').exists())

    def test_issued_code_and_snapshot_remain_unchanged(self):
        voucher = self.issue()[0]
        before = Voucher.objects.filter(pk=voucher.pk).values().get()
        self.plan.voucher_code_format = 'numeric'
        self.plan.save()
        self.assertEqual(Voucher.objects.filter(pk=voucher.pk).values().get(), before)
