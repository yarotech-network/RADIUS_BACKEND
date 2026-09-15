import hashlib
import hmac
import io
import json
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.core.management import call_command
from django.db import OperationalError
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase
from apps.routers.secret_store import secret_store
from apps.subscriptions.test_support import grant_test_subscription
from apps.tenants.models import Tenant
from .models import (SharedWhatsAppEndpoint, TenantWhatsAppEntryRoute, WhatsAppInboundEvent,
    WhatsAppRoutedSender, WhatsAppSenderWatermark)
from .shared_routing import hash_key_fingerprint, token_for_entry, reserve_purchase
from .inbox import MAX_BODY, _route


WEBHOOK_SETTINGS = dict(WHATSAPP_WEBHOOK_ENABLED=True, WHATSAPP_APP_SECRET='app-secret-test-only',
    WHATSAPP_WEBHOOK_VERIFY_TOKEN='verify-test-only', WHATSAPP_TENANT_ROUTING_SIGNING_KEY='s'*32,
    WHATSAPP_SENDER_HASH_KEY='h'*32)


@override_settings(**WEBHOOK_SETTINGS)
class WhatsAppWebhookTests(APITestCase):
    def setUp(self):
        self.a = Tenant.objects.create(name='Inbox A', slug='inbox-a')
        self.b = Tenant.objects.create(name='Inbox B', slug='inbox-b')
        for tenant in (self.a, self.b):
            grant_test_subscription(tenant)
        self.ra = TenantWhatsAppEntryRoute.objects.create(tenant=self.a)
        self.rb = TenantWhatsAppEntryRoute.objects.create(tenant=self.b)
        self.endpoint = SharedWhatsAppEndpoint.objects.create(phone_number_id='12345',
            display_number='+2348012345678', access_token_encrypted='fixture-only', is_active=True,
            verified_at=timezone.now(), hash_key_fingerprint=hash_key_fingerprint())
        self.now = int(timezone.now().timestamp()) - 20
        self.url = reverse('whatsapp-webhook')
        self.client = Client(enforce_csrf_checks=True)

    def message(self, key='wamid.a', text=None, offset=0, sender='2348012345678'):
        return {'id': key, 'from': sender, 'timestamp': str(self.now+offset), 'type': 'text',
            'text': {'body': text if text is not None else 'START '+token_for_entry(self.ra)}}

    def envelope(self, messages, statuses=None, phone='12345'):
        return {'object': 'whatsapp_business_account', 'entry': [{'id': 'business-account', 'changes': [
            {'field': 'messages', 'value': {'messaging_product': 'whatsapp', 'metadata': {'phone_number_id': phone},
                'messages': messages, 'statuses': statuses or []}}]}]}

    def post_payload(self, payload, signature=None):
        raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        signature = signature if signature is not None else 'sha256='+hmac.new(b'app-secret-test-only', raw, hashlib.sha256).hexdigest()
        return self.client.post(self.url, raw, content_type='application/json', HTTP_X_HUB_SIGNATURE_256=signature)

    def test_challenge_is_plain_text_and_has_no_database_side_effect(self):
        response = self.client.get(self.url, {'hub.mode':'subscribe', 'hub.verify_token':'verify-test-only', 'hub.challenge':'123456'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'123456')
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertFalse(WhatsAppInboundEvent.objects.exists())
        self.endpoint.refresh_from_db()
        verified = self.endpoint.verified_at
        for token in ['wrong', '☃']:
            self.assertEqual(self.client.get(self.url, {'hub.mode':'subscribe', 'hub.verify_token':token, 'hub.challenge':'123'}).status_code, 403)
        self.endpoint.refresh_from_db()
        self.assertEqual(self.endpoint.verified_at, verified)

    def test_signature_checked_before_parsing_or_routing(self):
        with patch('apps.whatsapp_routing.webhook.parse_events') as parser:
            for signature in ['', 'bad', 'sha256='+'0'*64, '☃']:
                self.assertEqual(self.post_payload(b'not-json', signature).status_code, 403)
            parser.assert_not_called()
        self.assertFalse(WhatsAppRoutedSender.objects.exists())

    def test_raw_body_tampering_is_rejected(self):
        raw = json.dumps(self.envelope([self.message()])).encode()
        signature = 'sha256='+hmac.new(b'app-secret-test-only', raw, hashlib.sha256).hexdigest()
        self.assertEqual(self.post_payload(raw+b' ', signature).status_code, 403)
        self.assertEqual(self.post_payload(raw, signature).status_code, 200)

    def test_disabled_missing_secret_or_hash_key_change_fails_closed(self):
        for override in [{'WHATSAPP_WEBHOOK_ENABLED':False}, {'WHATSAPP_APP_SECRET':''},
                         {'WHATSAPP_WEBHOOK_VERIFY_TOKEN':''}, {'WHATSAPP_SENDER_HASH_KEY':'x'*32}]:
            with override_settings(**override):
                response = self.post_payload(self.envelope([self.message()]))
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response['Retry-After'], '60')
        self.assertFalse(WhatsAppInboundEvent.objects.exists())

    def test_all_messages_and_statuses_are_received_in_timestamp_order(self):
        first = self.message()
        second = self.message('wamid.b', 'plans', offset=1)
        status = {'id':'wamid.out', 'recipient_id':'2348012345678', 'timestamp':str(self.now+2), 'status':'delivered'}
        response = self.post_payload(self.envelope([second, first], [status]))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['received'], 3)
        self.assertEqual(WhatsAppInboundEvent.objects.filter(state='ready', tenant=self.a).count(), 2)
        self.assertEqual(WhatsAppInboundEvent.objects.filter(state='status', tenant__isnull=True).count(), 1)

    def test_duplicate_start_does_not_rebind_after_switch(self):
        original = self.envelope([self.message()])
        self.post_payload(original)
        first = WhatsAppInboundEvent.objects.get(message_id='wamid.a')
        self.post_payload(self.envelope([self.message('wamid.b', 'START '+token_for_entry(self.rb), offset=1)]))
        before = WhatsAppRoutedSender.objects.get()
        self.assertEqual(self.post_payload(original).json()['duplicates'], 1)
        after = WhatsAppRoutedSender.objects.get()
        self.assertEqual(after.route_id, self.rb.pk)
        self.assertEqual(after.version, before.version)
        self.assertEqual(after.expires_at, before.expires_at)
        first.refresh_from_db()
        self.assertEqual(first.tenant_id, self.a.pk)
        self.assertNotEqual(first.binding_version, after.version)

    def test_reused_identity_with_changed_content_is_quarantined(self):
        self.post_payload(self.envelope([self.message()]))
        response = self.post_payload(self.envelope([self.message(text='START '+token_for_entry(self.rb))]))
        self.assertEqual(response.json()['conflicts'], 1)
        self.assertEqual(WhatsAppInboundEvent.objects.get().state, 'conflict')
        self.assertEqual(WhatsAppRoutedSender.objects.get().route_id, self.ra.pk)

    def test_late_and_same_second_messages_do_not_use_new_tenant(self):
        self.post_payload(self.envelope([self.message()]))
        self.post_payload(self.envelope([self.message('wamid.b', 'START '+token_for_entry(self.rb), offset=3)]))
        for index, offset in enumerate([1, 3]):
            self.post_payload(self.envelope([self.message(f'late.{index}', 'buy', offset=offset)]))
        self.assertEqual(WhatsAppInboundEvent.objects.filter(state='stale', tenant__isnull=True).count(), 2)
        self.assertEqual(WhatsAppRoutedSender.objects.get().route_id, self.rb.pk)

    def test_old_and_future_events_do_not_poison_watermark(self):
        for index, offset in enumerate([-8*86400, 3600]):
            self.assertEqual(self.post_payload(self.envelope([self.message(f'bad-time.{index}', offset=offset)])).status_code, 200)
        self.assertFalse(WhatsAppSenderWatermark.objects.exists())
        self.post_payload(self.envelope([self.message()]))
        self.assertEqual(WhatsAppRoutedSender.objects.get().route_id, self.ra.pk)

    def test_pending_purchase_blocks_switch_in_inbox(self):
        self.post_payload(self.envelope([self.message()]))
        binding = WhatsAppRoutedSender.objects.get()
        reserve_purchase(endpoint_id=self.endpoint.pk, endpoint_version=self.endpoint.version,
            sender='2348012345678', binding_version=binding.version, reference='inbox-pending')
        self.post_payload(self.envelope([self.message('wamid.b', 'START '+token_for_entry(self.rb), offset=1)]))
        self.assertEqual(WhatsAppInboundEvent.objects.get(message_id='wamid.b').state, 'blocked')
        self.assertEqual(WhatsAppRoutedSender.objects.get().route_id, self.ra.pk)

    def test_unverified_endpoint_receives_without_faking_verification(self):
        self.endpoint.verified_at = None
        self.endpoint.save()
        self.assertEqual(self.post_payload(self.envelope([self.message()])).status_code, 200)
        self.assertEqual(WhatsAppInboundEvent.objects.get().reason, 'endpoint_unavailable')
        self.assertFalse(WhatsAppRoutedSender.objects.exists())
        self.endpoint.refresh_from_db()
        self.assertIsNone(self.endpoint.verified_at)

    def test_expired_tenant_does_not_route_new_purchase_messages(self):
        from apps.subscriptions.models import TenantSubscription
        self.post_payload(self.envelope([self.message()]))
        TenantSubscription.objects.filter(tenant=self.a).update(expires_at=timezone.now()-timedelta(days=1))
        self.post_payload(self.envelope([self.message('wamid.b', 'buy', offset=1)]))
        self.assertEqual(WhatsAppInboundEvent.objects.get(message_id='wamid.b').state, 'blocked')

    def test_unknown_phone_does_not_infer_tenant(self):
        response = self.post_payload(self.envelope([self.message()], phone='9999'))
        self.assertEqual(response.json()['ignored'], 1)
        self.assertFalse(WhatsAppInboundEvent.objects.exists())

    def test_malformed_second_event_and_oversized_body_write_nothing(self):
        malformed = self.message('invalid')
        malformed['timestamp'] = []
        for raw in [b'not-json', b'[]', b'\xff', json.dumps(self.envelope([self.message(), malformed])).encode()]:
            self.assertEqual(self.post_payload(raw).status_code, 400)
        self.assertEqual(self.post_payload(b'x'*(MAX_BODY+1)).status_code, 413)
        self.assertEqual(self.post_payload(self.envelope([self.message(str(i)) for i in range(101)])).status_code, 400)
        self.assertFalse(WhatsAppInboundEvent.objects.exists())
        self.assertFalse(WhatsAppRoutedSender.objects.exists())

    def test_database_failure_rolls_back_receipt_binding_and_watermark_then_retry_works(self):
        payload = self.envelope([self.message(), self.message('wamid.b', 'plans', offset=1)])
        calls = 0
        def fail_second(*args):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OperationalError('test failure')
            return _route(*args)
        with patch('apps.whatsapp_routing.inbox._route', side_effect=fail_second):
            self.assertEqual(self.post_payload(payload).status_code, 503)
        self.assertFalse(WhatsAppInboundEvent.objects.exists())
        self.assertFalse(WhatsAppRoutedSender.objects.exists())
        self.assertFalse(WhatsAppSenderWatermark.objects.exists())
        self.assertEqual(self.post_payload(payload).json()['received'], 2)

    def test_storage_and_diagnostics_do_not_expose_customer_content(self):
        self.post_payload(self.envelope([self.message()]))
        event = WhatsAppInboundEvent.objects.get()
        self.assertTrue(event.payload_encrypted.startswith('enc:v1:'))
        for private in ['2348012345678', token_for_entry(self.ra)]:
            self.assertNotIn(private, event.payload_encrypted)
            self.assertNotIn(private, event.payload_fingerprint)
        decoded = json.loads(secret_store.decrypt(event.payload_encrypted))
        self.assertEqual(decoded['item']['from'], '2348012345678')
        output = io.StringIO()
        call_command('whatsapp_inbox_status', stdout=output)
        summary = json.loads(output.getvalue())
        self.assertEqual(summary['states']['ready'], 1)
        self.assertFalse(summary['consumer_enabled'])
        self.assertNotIn('2348012345678', output.getvalue())
        self.assertNotIn('wamid.a', output.getvalue())

    def test_duplicate_identity_survives_endpoint_version_change(self):
        original = self.envelope([self.message()])
        self.post_payload(original)
        self.endpoint.version = uuid.uuid4()
        self.endpoint.save()
        self.assertEqual(self.post_payload(original).json()['duplicates'], 1)
        self.assertEqual(WhatsAppInboundEvent.objects.count(), 1)
