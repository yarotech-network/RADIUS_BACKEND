"""Isolated settings-policy tests; no database or provider connections."""
import runpy
import sys
import types
import unittest
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured


class ProviderSettingsTests(unittest.TestCase):
    def load(self, enabled=True, **changes):
        production = types.ModuleType('config.production_settings')
        values = dict(
            STAGING_PROVIDER_TESTING=enabled, RESEND_API_KEY='re_test_placeholder',
            PAYSTACK_SECRET_KEY='sk_test_placeholder', PAYSTACK_PUBLIC_KEY='pk_test_placeholder',
            DEFAULT_FROM_EMAIL='Yarotech <otp@testing.invalid>',
            RADIUS_REST_ENABLED=False, IOT_PUBLIC_PURCHASE_ENABLED=False,
            WHATSAPP_WEBHOOK_ENABLED=False, WHATSAPP_CONSUMER_ENABLED=False,
            WHATSAPP_SEND_ENABLED=False,
        )
        values.update(changes)
        production.__dict__.update(values)
        production.DATABASES = {'default': {'NAME': 'example_staging'}}
        production.REDIS_URL = 'redis://127.0.0.1:6379/9'
        production.CACHES = {'default': {}}
        production.Csv = lambda: list
        production.config = lambda name, default=None, cast=None: values.get(name, default)
        with patch.dict(sys.modules, {'config.production_settings': production}):
            return runpy.run_module('config.staging_settings')

    def test_default_still_uses_files_even_with_key(self):
        result = self.load(enabled=False)
        self.assertEqual(result['RESEND_API_KEY'], '')
        self.assertEqual(result['REGISTRATION_EMAIL_BACKEND'], result['EMAIL_BACKEND'])

    def test_opt_in_uses_resend_and_preserves_staging(self):
        result = self.load()
        self.assertTrue(result['STAGING_MODE'])
        self.assertEqual(result['REGISTRATION_EMAIL_BACKEND'], '')
        self.assertEqual(result['RESEND_API_KEY'], 're_test_placeholder')
        self.assertEqual(result['CACHES']['default']['KEY_PREFIX'], 'yarotech-radius-staging')

    def test_rejects_live_or_missing_keys(self):
        for field, value in [('PAYSTACK_SECRET_KEY', 'sk_live_no'),
                             ('PAYSTACK_PUBLIC_KEY', 'pk_live_no'),
                             ('RESEND_API_KEY', ''), ('PAYSTACK_SECRET_KEY', '')]:
            with self.subTest(field=field, value=value), self.assertRaises(ImproperlyConfigured):
                self.load(**{field: value})

    def test_rejects_missing_or_example_sender(self):
        for sender in ('', 'invalid', 'Yarotech <no-reply@example.com>'):
            with self.subTest(sender=sender), self.assertRaises(ImproperlyConfigured):
                self.load(DEFAULT_FROM_EMAIL=sender)

    def test_rejects_consumer_gate_changes(self):
        for flag in ('RADIUS_REST_ENABLED', 'IOT_PUBLIC_PURCHASE_ENABLED',
                     'WHATSAPP_WEBHOOK_ENABLED', 'WHATSAPP_CONSUMER_ENABLED', 'WHATSAPP_SEND_ENABLED'):
            with self.subTest(flag=flag), self.assertRaises(ImproperlyConfigured):
                self.load(**{flag: True})


if __name__ == '__main__':
    unittest.main()
