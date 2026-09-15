import json
import uuid
from datetime import timedelta
from unittest.mock import patch, Mock
import requests
from django.contrib.auth import get_user_model
from django.test import override_settings, TransactionTestCase
from django.db import connection
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase, APIClient
from apps.payments.services import get_payment_paystack_service
from apps.routers.secret_store import secret_store
from apps.tenants.models import TenantMembership
from apps.vouchers.models import InternetPlan, PaymentTransaction, Voucher, Radcheck, Radreply, Radacct, Radpostauth
from . import test_webhook
from .models import (WhatsAppOrder, WhatsAppConversation, WhatsAppInboundEvent,
    WhatsAppOutbound, WhatsAppSenderWatermark, WhatsAppProcessedEvent)
from .conversations import process_event, queue_message
from .orders import process_order
from .outbound import send_one, process_delivery_status
from .provider import verify_endpoint, ProviderFailure, send_payload
from .reminders import schedule_order_reminders


@override_settings(**test_webhook.WEBHOOK_SETTINGS, WHATSAPP_CONSUMER_ENABLED=True,
    WHATSAPP_SEND_ENABLED=True, WHATSAPP_GRAPH_VERSION='v25.0', PAYSTACK_SECRET_KEY='sk_test_original')
class WorkflowTests(TransactionTestCase):
    message = test_webhook.WhatsAppWebhookTests.message
    envelope = test_webhook.WhatsAppWebhookTests.envelope
    post_payload = test_webhook.WhatsAppWebhookTests.post_payload

    def setUp(self):
        self.created_tables = []
        for model in (Radcheck, Radreply, Radacct, Radpostauth):
            if model._meta.db_table not in connection.introspection.table_names():
                with connection.schema_editor() as editor:
                    editor.create_model(model)
                self.created_tables.append(model)
        test_webhook.WhatsAppWebhookTests.setUp(self)
        self.plan = InternetPlan.objects.create(tenant=self.a, name='Day pass', price=50000, duration_hours=24)
        self.sequence = 0

    def tearDown(self):
        for model in reversed(self.created_tables):
            with connection.schema_editor() as editor:
                editor.delete_model(model)

    def inbound(self, text=None, process=True):
        self.sequence += 1
        key = f'flow.{self.sequence}'
        response = self.post_payload(self.envelope([self.message(key, text, offset=self.sequence)]))
        self.assertEqual(response.status_code, 200, response.content)
        event = WhatsAppInboundEvent.objects.get(message_id=key)
        if process:
            process_event(event.pk)
        return event

    def order(self):
        self.inbound()
        self.inbound('1')
        self.inbound('buyer@example.com')
        return WhatsAppOrder.objects.get()

    def initialize(self, order):
        with patch('apps.vouchers.services.PaystackService.initialize_transaction', return_value={
            'status': True, 'data': {'reference': order.payment.reference, 'authorization_url':'https://checkout.paystack.com/test-flow'}}):
            self.assertTrue(process_order(order.pk))
        order.refresh_from_db()
        self.assertEqual(order.state, 'pending')
        self.assertTrue(order.checkout_encrypted)

    def fulfill(self, order):
        WhatsAppOrder.objects.filter(pk=order.pk).update(state='pending', next_check_at=timezone.now())
        with patch('apps.vouchers.services.PaystackService.verify_transaction', return_value={'status':True, 'data':{
            'reference': order.payment.reference, 'status':'success', 'amount': order.payment.amount, 'currency':'NGN'}}):
            self.assertTrue(process_order(order.pk))
        order.refresh_from_db()
        return WhatsAppOutbound.objects.get(dedup_key=f'voucher:{order.pk}')

    def only_pending(self, row):
        WhatsAppOutbound.objects.exclude(pk=row.pk).filter(state='pending').update(state='accepted')

    def test_menu_email_order_preserves_terms_and_account_and_deduplicates_event(self):
        order = self.order()
        self.assertEqual(order.payment.amount, 50000)
        self.assertEqual(order.payment.purchased_terms['device_limit'], 1)
        self.assertEqual(secret_store.decrypt(order.payment_secret_encrypted), 'sk_test_original')
        self.assertFalse(process_event(order.source_event_id))
        self.inbound('MENU')
        self.inbound('1')
        self.inbound('buyer@example.com')
        self.assertEqual(WhatsAppOrder.objects.count(), 1)
        self.assertEqual(PaymentTransaction.objects.count(), 1)
        self.assertIsNone(order.hold.released_at)

    def test_menu_selection_does_not_silently_change_price(self):
        self.inbound()
        self.inbound('1')
        InternetPlan.objects.filter(pk=self.plan.pk).update(price=75000)
        self.inbound('buyer@example.com')
        self.assertFalse(WhatsAppOrder.objects.exists())
        self.assertEqual(WhatsAppConversation.objects.get().menu[0]['price'], 75000)

    def test_invalid_email_does_not_create_payment(self):
        self.inbound()
        self.inbound('1')
        self.inbound('not-an-email')
        self.assertFalse(PaymentTransaction.objects.exists())

    def test_stale_selection_cannot_be_processed_under_another_tenant(self):
        event = self.inbound(process=False)
        from .shared_routing import token_for_entry
        self.inbound('START '+token_for_entry(self.rb))
        process_event(event.pk)
        self.assertEqual(WhatsAppProcessedEvent.objects.get(event=event).outcome, 'stale_selection')
        self.assertFalse(WhatsAppOrder.objects.exists())

    def test_newer_processed_event_prevents_older_transition(self):
        self.inbound()
        old = self.inbound('1', process=False)
        self.inbound('MENU')
        process_event(old.pk)
        self.assertEqual(WhatsAppProcessedEvent.objects.get(event=old).outcome, 'out_of_order')
        self.assertEqual(WhatsAppConversation.objects.get().state, 'menu')

    def test_initialize_timeout_does_not_initialize_a_second_payment(self):
        order = self.order()
        with patch('apps.vouchers.services.PaystackService.initialize_transaction', side_effect=requests.ReadTimeout()) as initialize:
            process_order(order.pk)
            WhatsAppOrder.objects.filter(pk=order.pk).update(next_check_at=timezone.now())
            with patch('apps.vouchers.services.PaystackService.verify_transaction', side_effect=requests.ReadTimeout()):
                process_order(order.pk)
            self.assertEqual(initialize.call_count, 1)
        order.refresh_from_db()
        self.assertEqual(order.state, 'unknown')
        self.assertEqual(PaymentTransaction.objects.count(), 1)
        self.assertIsNone(order.hold.released_at)

    def test_untrusted_checkout_url_is_not_sent(self):
        order = self.order()
        with patch('apps.vouchers.services.PaystackService.initialize_transaction', return_value={'status':True, 'data':{
            'reference':order.payment.reference, 'authorization_url':'https://evil.example/pay'}}):
            process_order(order.pk)
        self.assertFalse(WhatsAppOutbound.objects.filter(kind='checkout').exists())
        order.refresh_from_db()
        self.assertEqual(order.state, 'unknown')

    def test_paid_fulfillment_and_automatic_delivery_are_once_only(self):
        order = self.order()
        self.initialize(order)
        delivery = self.fulfill(order)
        self.assertEqual(order.state, 'fulfilled')
        self.assertEqual(Voucher.objects.count(), 1)
        self.assertEqual(Radcheck.objects.filter(attribute='Cleartext-Password').count(), 1)
        self.assertFalse(process_order(order.pk))
        self.assertEqual(WhatsAppOutbound.objects.filter(kind='credentials').count(), 1)
        self.assertIsNotNone(order.hold.released_at)
        self.only_pending(delivery)
        with patch('apps.whatsapp_routing.outbound.send_payload', return_value='wamid.delivery') as send:
            self.assertTrue(send_one(delivery.pk))
            self.assertFalse(send_one(delivery.pk))
            self.assertEqual(send.call_count, 1)
        delivery.refresh_from_db()
        self.assertEqual(delivery.state, 'accepted')

    def test_paid_rights_survive_subscription_expiry(self):
        from apps.subscriptions.models import TenantSubscription
        order = self.order()
        self.initialize(order)
        TenantSubscription.objects.filter(tenant=self.a).update(expires_at=timezone.now()-timedelta(days=1))
        delivery = self.fulfill(order)
        self.only_pending(delivery)
        with patch('apps.whatsapp_routing.outbound.send_payload', return_value='wamid.after-expiry'):
            self.assertTrue(send_one(delivery.pk))
        self.assertEqual(Voucher.objects.count(), 1)

    def test_account_changes_do_not_redirect_verification(self):
        order = self.order()
        with override_settings(PAYSTACK_SECRET_KEY='sk_test_replacement'):
            self.assertEqual(get_payment_paystack_service(order.payment).secret_key, 'sk_test_original')

    def test_unknown_send_and_stale_worker_claim_are_not_retried(self):
        self.inbound()
        row = WhatsAppOutbound.objects.get()
        with patch('apps.whatsapp_routing.outbound.send_payload', side_effect=ProviderFailure('timeout', ambiguous=True)) as send:
            self.assertTrue(send_one(row.pk))
            self.assertFalse(send_one(row.pk))
            self.assertEqual(send.call_count, 1)
        row.refresh_from_db()
        self.assertEqual(row.state, 'unknown')
        row.state, row.started_at = 'sending', timezone.now()-timedelta(minutes=6)
        row.save()
        with patch('apps.whatsapp_routing.outbound.send_payload') as send:
            self.assertFalse(send_one(row.pk))
            send.assert_not_called()

    def test_expired_free_text_window_blocks_delivery(self):
        order = self.order()
        delivery = self.fulfill(order)
        self.only_pending(delivery)
        WhatsAppSenderWatermark.objects.update(provider_timestamp=int(timezone.now().timestamp())-86401)
        with patch('apps.whatsapp_routing.outbound.send_payload') as send:
            self.assertFalse(send_one(delivery.pk))
            send.assert_not_called()
        delivery.refresh_from_db()
        self.assertEqual(delivery.error_code, 'customer_reply_window_closed')

    def test_delivery_status_is_scoped_and_does_not_regress_read_to_sent(self):
        order = self.order()
        delivery = self.fulfill(order)
        delivery.state, delivery.provider_message_id = 'accepted', 'wamid.sent-voucher'
        delivery.save()
        for index, state in enumerate(['read', 'sent', 'failed']):
            status = {'id':delivery.provider_message_id, 'recipient_id':'2348012345678',
                'timestamp':str(self.now+index+10), 'status':state}
            self.post_payload(self.envelope([], [status]))
            event = WhatsAppInboundEvent.objects.filter(kind='status').order_by('-pk').first()
            process_delivery_status(event.pk)
        delivery.refresh_from_db()
        self.assertEqual(delivery.state, 'read')
        self.assertEqual(Voucher.objects.count(), 1)

    def test_expiry_reminder_is_opt_in_unique_and_invalidated_by_changed_deadline(self):
        order = self.order()
        self.fulfill(order)
        voucher = order.payment.voucher
        Voucher.objects.filter(pk=voucher.pk).update(status='active', activated_at=timezone.now()-timedelta(hours=23), expires_at=timezone.now()+timedelta(hours=1))
        self.ra.reminder_preferences = {'enabled':True, 'expiry_enabled':True, 'expiry_template':'voucher_expiring'}
        self.ra.save()
        self.assertEqual(schedule_order_reminders(order.pk), 0)
        WhatsAppOrder.objects.filter(pk=order.pk).update(reminders_opt_in=True)
        self.assertEqual(schedule_order_reminders(order.pk), 1)
        self.assertEqual(schedule_order_reminders(order.pk), 0)
        row = WhatsAppOutbound.objects.get(kind='expiry_reminder')
        self.only_pending(row)
        Voucher.objects.filter(pk=voucher.pk).update(expires_at=timezone.now()+timedelta(hours=1, minutes=5))
        with patch('apps.whatsapp_routing.outbound.send_payload') as send:
            self.assertFalse(send_one(row.pk))
            send.assert_not_called()

    def test_unused_reminder_requires_radius_evidence(self):
        order = self.order()
        self.fulfill(order)
        WhatsAppOrder.objects.filter(pk=order.pk).update(reminders_opt_in=True)
        PaymentTransaction.objects.filter(pk=order.payment_id).update(paid_at=timezone.now()-timedelta(hours=25))
        self.ra.reminder_preferences = {'enabled':True, 'unused_enabled':True, 'unused_template':'voucher_unused'}
        self.ra.save()
        with patch('apps.whatsapp_routing.reminders.Radacct.objects.filter') as accounting:
            accounting.return_value.exists.return_value = True
            self.assertEqual(schedule_order_reminders(order.pk), 0)
        with patch('apps.whatsapp_routing.reminders.Radacct.objects.filter') as accounting, patch('apps.whatsapp_routing.reminders.Radpostauth.objects.filter') as accepted:
            accounting.return_value.exists.return_value = False
            accepted.return_value.exists.return_value = False
            self.assertEqual(schedule_order_reminders(order.pk), 1)

    def test_provider_validation_checks_number_and_never_follows_redirects(self):
        response = Mock(status_code=200)
        response.json.return_value = {'id':'12345', 'display_phone_number':'+234 8012345678', 'code_verification_status':'VERIFIED'}
        with patch('apps.whatsapp_routing.provider.requests.get', return_value=response) as get:
            verify_endpoint(self.endpoint)
            self.assertFalse(get.call_args.kwargs['allow_redirects'])
            self.assertNotIn('access_token', get.call_args.kwargs['params'])
        response.json.return_value['display_phone_number'] = '+2348000000000'
        with patch('apps.whatsapp_routing.provider.requests.get', return_value=response):
            with self.assertRaises(ProviderFailure):
                verify_endpoint(self.endpoint)

    def test_provider_verification_api_is_platform_only_and_rejects_stale_result(self):
        client = APIClient()
        admin = get_user_model().objects.create_user(username='wa-admin', email='wa-admin@example.com', is_platform_admin=True)
        client.force_authenticate(admin)
        def changed(endpoint):
            from .models import SharedWhatsAppEndpoint
            SharedWhatsAppEndpoint.objects.filter(pk=1).update(version=uuid.uuid4(), verified_at=None)
        with patch('apps.whatsapp_routing.provider.verify_endpoint', side_effect=changed):
            response = client.post(reverse('whatsapp-verify-endpoint'), {'expected_version':str(self.endpoint.version)}, format='json')
        self.assertEqual(response.status_code, 409)
        self.endpoint.refresh_from_db()
        self.assertIsNone(self.endpoint.verified_at)
        member = get_user_model().objects.create_user(username='wa-manager', email='wa-manager@example.com')
        TenantMembership.objects.create(user=member, tenant=self.a, role='manager')
        client.force_authenticate(member)
        self.assertEqual(client.post(reverse('whatsapp-verify-endpoint'), {'expected_version':str(self.endpoint.version)}, format='json').status_code, 403)

    def test_recovery_is_tenant_scoped_and_resend_requires_acknowledgement(self):
        order = self.order()
        self.fulfill(order)
        client = APIClient()
        manager = get_user_model().objects.create_user(username='wa-recovery', email='wa-recovery@example.com')
        TenantMembership.objects.create(user=manager, tenant=self.a, role='manager')
        client.force_authenticate(manager)
        url = reverse('whatsapp-order-recovery', args=[order.pk])
        payload = {'action':'resend', 'request_id':str(uuid.uuid4())}
        self.assertEqual(client.post(url, payload, format='json').status_code, 400)
        payload['acknowledge_duplicate_risk'] = True
        self.assertEqual(client.post(url, payload, format='json').status_code, 200)
        self.assertEqual(client.post(url, payload, format='json').status_code, 200)
        self.assertEqual(WhatsAppOutbound.objects.filter(kind='credentials').count(), 2)
        TenantMembership.objects.filter(user=manager).update(tenant=self.b)
        client.force_authenticate(get_user_model().objects.get(pk=manager.pk))
        self.assertEqual(client.post(url, payload, format='json').status_code, 404)

    def test_revoked_link_prevents_initialization_of_queued_purchase(self):
        order = self.order()
        self.ra.revoked_at = timezone.now()
        self.ra.save()
        with patch('apps.vouchers.services.PaystackService.initialize_transaction') as initialize:
            self.assertFalse(process_order(order.pk))
            initialize.assert_not_called()
        order.refresh_from_db()
        self.assertEqual(order.state, 'recovery')

    def test_rich_message_parser_tolerates_malformed_optional_fields(self):
        from .conversations import _text
        for value in [{'type':'button', 'button':None}, {'type':'text', 'text':[]},
                      {'type':'interactive', 'interactive':'invalid'},
                      {'type':'interactive', 'interactive':{'button_reply':[]}}]:
            self.assertEqual(_text(value), '')

    def test_provider_send_distinguishes_safe_retry_and_unknown_outcome(self):
        for error, retryable, ambiguous in [(requests.ConnectTimeout(), True, False),
                                           (requests.ReadTimeout(), False, True)]:
            with patch('apps.whatsapp_routing.provider.requests.post', side_effect=error):
                with self.assertRaises(ProviderFailure) as caught:
                    send_payload(self.endpoint, {'type':'text'})
                self.assertEqual(caught.exception.retryable, retryable)
                self.assertEqual(caught.exception.ambiguous, ambiguous)
        response = Mock(status_code=200)
        response.json.return_value = {'messages':[{'id':'wamid.accepted'}]}
        with patch('apps.whatsapp_routing.provider.requests.post', return_value=response) as post:
            self.assertEqual(send_payload(self.endpoint, {'type':'text'}), 'wamid.accepted')
            self.assertFalse(post.call_args.kwargs['allow_redirects'])

    def test_changed_reminder_template_blocks_queued_send(self):
        order = self.order()
        self.fulfill(order)
        WhatsAppOrder.objects.filter(pk=order.pk).update(reminders_opt_in=True)
        PaymentTransaction.objects.filter(pk=order.payment_id).update(paid_at=timezone.now()-timedelta(hours=25))
        self.ra.reminder_preferences = {'enabled':True, 'unused_enabled':True, 'unused_template':'voucher_unused'}
        self.ra.save()
        self.assertEqual(schedule_order_reminders(order.pk), 1)
        row = WhatsAppOutbound.objects.get(kind='unused_reminder')
        self.only_pending(row)
        self.ra.reminder_preferences['unused_template'] = 'replacement_template'
        self.ra.save()
        with patch('apps.whatsapp_routing.outbound.send_payload') as send:
            self.assertFalse(send_one(row.pk))
            send.assert_not_called()

    def test_expired_operator_cannot_access_workflow_controls(self):
        from rest_framework_simplejwt.tokens import RefreshToken
        from apps.subscriptions.models import TenantSubscription
        user = get_user_model().objects.create_user(username='wa-expired', email='expired@example.com')
        TenantMembership.objects.create(user=user, tenant=self.a, role='owner')
        TenantSubscription.objects.filter(tenant=self.a).update(expires_at=timezone.now()-timedelta(seconds=1))
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION='Bearer '+str(RefreshToken.for_user(user).access_token))
        for name in ('whatsapp-reminders', 'whatsapp-orders'):
            response = client.get(reverse(name))
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.data['code'], 'subscription_required')

    def test_reminder_settings_default_off_and_require_approved_template_name(self):
        from .reminders import DEFAULTS
        user = get_user_model().objects.create_user(username='wa-prefs', email='prefs@example.com')
        TenantMembership.objects.create(user=user, tenant=self.a, role='owner')
        client = APIClient()
        client.force_authenticate(user)
        url = reverse('whatsapp-reminders')
        response = client.get(url)
        self.assertFalse(response.data['enabled'])
        data = {**DEFAULTS, 'expected_version':str(self.ra.version), 'enabled':True, 'unused_enabled':True}
        self.assertEqual(client.put(url, data, format='json').status_code, 400)
        data['unused_template'] = 'voucher_unused'
        self.assertEqual(client.put(url, data, format='json').status_code, 200)
        self.assertEqual(client.put(url, data, format='json').status_code, 409)

    def test_stop_cancels_reminders_after_selection_expires_and_blocks_older_opt_in(self):
        order = self.order()
        WhatsAppOrder.objects.filter(pk=order.pk).update(reminders_opt_in=True)
        self.inbound('REMINDERS ON', process=False)
        old_event = WhatsAppInboundEvent.objects.order_by('-pk').first()
        from .models import WhatsAppRoutedSender
        WhatsAppRoutedSender.objects.filter(pk=order.hold.binding_id).update(expires_at=timezone.now()-timedelta(minutes=1))
        event = self.inbound('STOP')
        order.refresh_from_db()
        self.assertFalse(order.reminders_opt_in)
        self.assertEqual(WhatsAppProcessedEvent.objects.get(event=event).outcome, 'reminders_opted_out')
        process_event(old_event.pk)
        order.refresh_from_db()
        self.assertFalse(order.reminders_opt_in)

    def test_verified_failed_payment_releases_hold_without_issuing_voucher(self):
        order = self.order()
        WhatsAppOrder.objects.filter(pk=order.pk).update(state='unknown')
        with patch('apps.vouchers.services.PaystackService.verify_transaction', return_value={'status':True, 'data':{
            'reference':order.payment.reference, 'amount':order.payment.amount, 'currency':'NGN', 'status':'failed'}}):
            self.assertTrue(process_order(order.pk))
        order.refresh_from_db()
        self.assertEqual(order.state, 'failed')
        self.assertIsNotNone(order.hold.released_at)
        self.assertFalse(Voucher.objects.exists())

    def test_safe_delivery_retry_keeps_same_outbound_record(self):
        order = self.order()
        row = self.fulfill(order)
        self.only_pending(row)
        with patch('apps.whatsapp_routing.outbound.send_payload', side_effect=ProviderFailure('meta_rate_limited', retryable=True)) as send:
            self.assertTrue(send_one(row.pk))
            self.assertFalse(send_one(row.pk))
            self.assertEqual(send.call_count, 1)
        row.refresh_from_db()
        self.assertEqual(row.state, 'pending')
        WhatsAppOutbound.objects.filter(pk=row.pk).update(next_attempt_at=timezone.now())
        with patch('apps.whatsapp_routing.outbound.send_payload', return_value='wamid.retry'):
            self.assertTrue(send_one(row.pk))
        row.refresh_from_db()
        self.assertEqual(row.attempts, 2)
        self.assertEqual(WhatsAppOutbound.objects.filter(kind='credentials').count(), 1)

    def test_each_whatsapp_purchase_gets_its_own_contact_even_for_same_sender_email(self):
        first = self.order()
        first_contact = first.payment.customer_id
        self.assertIsNotNone(first_contact)
        self.fulfill(first)
        self.inbound('MENU')
        self.inbound('1')
        event = self.inbound('buyer@example.com')
        second = WhatsAppOrder.objects.get(source_event=event)
        self.assertNotEqual(first_contact, second.payment.customer_id)
        self.assertFalse(process_event(event.pk))
        from apps.customers.models import Customer
        self.assertEqual(Customer.objects.count(), 2)
