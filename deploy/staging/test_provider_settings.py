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
        production.DATABASES = changes.get('DATABASES', {'default': {'NAME': 'example_staging'}})
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

    def router_values(self):
        return dict(STAGING_ROUTER_TESTING=True, RADIUS_REST_ENABLED=True,
                    RADIUS_REST_TOKEN='test-only-' + 'x' * 40,
                    WG_INTERFACE='wgstage', WG_MANAGED_SUBNET='10.101.100.0/24',
                    WG_ENDPOINT_PORT=51821, RADIUS_SERVER_WG_IP='10.101.100.1',
                    ROUTER_RADIUS_AUTH_PORT=18121, ROUTER_RADIUS_ACCT_PORT=18131,
                    RADIUS_AUTH_HOST='10.101.100.1', RADIUS_AUTH_PORT=18121,
                    DATABASES={'default': dict(NAME='yarotech_radius_staging',
                        USER='yarotech_radius_staging', HOST='127.0.0.1', PORT='5433')})

    def test_explicit_router_profile_preserves_provider_and_cache(self):
        result = self.load(**self.router_values())
        self.assertTrue(result['RADIUS_REST_ENABLED'])
        self.assertEqual(result['RESEND_API_KEY'], 're_test_placeholder')
        self.assertEqual(result['CACHES']['default']['KEY_PREFIX'], 'yarotech-radius-staging')

    def test_router_profile_rejects_live_network_and_weak_token(self):
        for key, value in [('WG_INTERFACE', 'wg0'), ('WG_MANAGED_SUBNET', '10.100.100.0/24'),
                           ('WG_ENDPOINT_PORT', 51820), ('RADIUS_SERVER_WG_IP', '10.100.100.1'),
                           ('ROUTER_RADIUS_AUTH_PORT', 1812), ('ROUTER_RADIUS_ACCT_PORT', 1813),
                           ('RADIUS_AUTH_HOST', '169.58.42.82'), ('RADIUS_AUTH_PORT', 1812),
                           ('RADIUS_REST_TOKEN', 'short'), ('RADIUS_REST_ENABLED', False),
                           ('WHATSAPP_SEND_ENABLED', True), ('IOT_PUBLIC_PURCHASE_ENABLED', True)]:
            values = self.router_values()
            values[key] = value
            with self.subTest(key=key), self.assertRaises(ImproperlyConfigured):
                self.load(**values)

    def test_router_profile_rejects_wrong_database(self):
        for key, value in [('NAME', 'hotspot'), ('USER', 'postgres'),
                           ('HOST', '169.58.42.82'), ('PORT', '5432')]:
            values = self.router_values()
            values['DATABASES']['default'][key] = value
            with self.subTest(key=key), self.assertRaises(ImproperlyConfigured):
                self.load(**values)

    def test_rest_requires_opt_in_without_provider_testing(self):
        with self.assertRaises(ImproperlyConfigured):
            self.load(enabled=False, RADIUS_REST_ENABLED=True)


if __name__ == '__main__':
    unittest.main()
