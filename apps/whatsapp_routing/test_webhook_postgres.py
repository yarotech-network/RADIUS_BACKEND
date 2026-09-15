"""Run against a disposable PostgreSQL test DB; SQLite cannot prove row-lock behavior."""
import hashlib
import hmac
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from django.db import connection, connections, close_old_connections
from django.test import Client, TransactionTestCase, override_settings
from .models import WhatsAppInboundEvent, WhatsAppRoutedSender
from . import test_webhook


@skipUnless(connection.vendor == 'postgresql', 'Requires PostgreSQL row locks')
@override_settings(**test_webhook.WEBHOOK_SETTINGS)
class ConcurrentWebhookTests(TransactionTestCase):
    setUp = test_webhook.WhatsAppWebhookTests.setUp
    message = test_webhook.WhatsAppWebhookTests.message
    envelope = test_webhook.WhatsAppWebhookTests.envelope

    def test_simultaneous_duplicate_delivery_creates_one_receipt_and_binding(self):
        raw = json.dumps(self.envelope([self.message()])).encode()
        signature = 'sha256='+hmac.new(b'app-secret-test-only', raw, hashlib.sha256).hexdigest()
        barrier = Barrier(2)
        def deliver():
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout TO '5s'")
                    cursor.execute("SET statement_timeout TO '10s'")
                barrier.wait(timeout=10)
                response = Client(enforce_csrf_checks=True).post(self.url, raw,
                    content_type='application/json', HTTP_X_HUB_SIGNATURE_256=signature)
                return response.status_code, response.json()
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(deliver) for _ in range(2)]
            results = [future.result(timeout=20) for future in futures]
        self.assertEqual([status for status, _ in results], [200, 200])
        self.assertEqual(sum(body['received'] for _, body in results), 1)
        self.assertEqual(sum(body['duplicates'] for _, body in results), 1)
        self.assertEqual(WhatsAppInboundEvent.objects.count(), 1)
        self.assertEqual(WhatsAppRoutedSender.objects.count(), 1)
