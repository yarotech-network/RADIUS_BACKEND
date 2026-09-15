from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class WhatsAppDisplayMigrationTests(TransactionTestCase):
    def test_inbox_expansion_preserves_shared_routes_bindings_and_open_holds(self):
        import uuid
        from django.utils import timezone
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        before = [('whatsapp_routing', '0004_sharedwhatsappendpoint_tenantwhatsappentryroute_and_more')]
        try:
            executor.migrate(before)
            old = executor.loader.project_state(before).apps
            tenant = old.get_model('tenants', 'Tenant').objects.create(name='Shared history', slug='shared-history')
            endpoint = old.get_model('whatsapp_routing', 'SharedWhatsAppEndpoint').objects.create(
                phone_number_id='12345', display_number='+2348012345678', access_token_encrypted='saved-ciphertext')
            route = old.get_model('whatsapp_routing', 'TenantWhatsAppEntryRoute').objects.create(tenant_id=tenant.pk)
            binding = old.get_model('whatsapp_routing', 'WhatsAppRoutedSender').objects.create(
                endpoint_id=endpoint.pk, route_id=route.pk, customer_hash='h'*64,
                version=uuid.uuid4(), endpoint_version=endpoint.version, route_selector=route.selector,
                expires_at=timezone.now(), last_activity_at=timezone.now())
            hold = old.get_model('whatsapp_routing', 'WhatsAppRoutingHold').objects.create(
                binding_id=binding.pk, binding_version=binding.version, tenant_id=tenant.pk, reference='retained-hold')
            MigrationExecutor(connection).migrate(latest)
            new = MigrationExecutor(connection).loader.project_state(latest).apps
            self.assertEqual(new.get_model('whatsapp_routing', 'SharedWhatsAppEndpoint').objects.get(pk=1).access_token_encrypted, 'saved-ciphertext')
            self.assertEqual(new.get_model('whatsapp_routing', 'WhatsAppRoutedSender').objects.get(pk=binding.pk).version, binding.version)
            self.assertEqual(new.get_model('whatsapp_routing', 'TenantWhatsAppEntryRoute').objects.get(pk=route.pk).selector, route.selector)
            self.assertIsNone(new.get_model('whatsapp_routing', 'WhatsAppRoutingHold').objects.get(pk=hold.pk).released_at)
            self.assertFalse(new.get_model('whatsapp_routing', 'WhatsAppInboundEvent').objects.exists())
            self.assertFalse(new.get_model('whatsapp_routing', 'WhatsAppSenderWatermark').objects.exists())
        finally:
            MigrationExecutor(connection).migrate(latest)

    def test_existing_connection_is_preserved_without_guessing_public_number(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        before = [('whatsapp_routing', '0002_alter_tenantwhatsapproute_access_token_encrypted')]
        try:
            executor.migrate(before)
            old = executor.loader.project_state(before).apps
            tenant = old.get_model('tenants', 'Tenant').objects.create(name='Historical', slug='historical-whatsapp')
            route = old.get_model('whatsapp_routing', 'TenantWhatsAppRoute').objects.create(
                tenant_id=tenant.pk, phone_number_id='99887766', access_token_encrypted='historical-ciphertext', webhook_token='historical-route-secret')
            binding = old.get_model('whatsapp_routing', 'WhatsAppSenderBinding').objects.create(tenant_id=tenant.pk, phone_number='2348012345678')
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            new = executor.loader.project_state(latest).apps
            saved = new.get_model('whatsapp_routing', 'TenantWhatsAppRoute').objects.get(pk=route.pk)
            self.assertEqual(saved.display_number, '')
            self.assertEqual(saved.phone_number_id, '99887766')
            self.assertEqual(saved.access_token_encrypted, 'historical-ciphertext')
            self.assertEqual(saved.webhook_token, 'historical-route-secret')
            self.assertEqual(new.get_model('whatsapp_routing', 'WhatsAppSenderBinding').objects.get(pk=binding.pk).phone_number, '2348012345678')
            for name in ('SharedWhatsAppEndpoint', 'TenantWhatsAppEntryRoute', 'WhatsAppRoutedSender', 'WhatsAppRoutingHold', 'WhatsAppInboundEvent', 'WhatsAppSenderWatermark'):
                self.assertFalse(new.get_model('whatsapp_routing', name).objects.exists())
        finally:
            MigrationExecutor(connection).migrate(latest)

    def test_workflow_expansion_preserves_accepted_inbox_and_watermark(self):
        import uuid
        from django.utils import timezone
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        before = [('whatsapp_routing', '0005_whatsappinboundevent_whatsappsenderwatermark')]
        try:
            executor.migrate(before)
            old = executor.loader.project_state(before).apps
            tenant = old.get_model('tenants', 'Tenant').objects.create(name='Inbox history', slug='inbox-history')
            endpoint = old.get_model('whatsapp_routing', 'SharedWhatsAppEndpoint').objects.create(
                phone_number_id='12345', display_number='+2348012345678', access_token_encrypted='retained-ciphertext')
            route = old.get_model('whatsapp_routing', 'TenantWhatsAppEntryRoute').objects.create(tenant_id=tenant.pk)
            event = old.get_model('whatsapp_routing', 'WhatsAppInboundEvent').objects.create(
                endpoint_id=endpoint.pk, endpoint_version=endpoint.version, phone_number_id='12345',
                tenant_id=tenant.pk, customer_hash='c'*64, message_id='wamid.history', kind='message',
                provider_timestamp=1234567890, payload_encrypted='retained-payload', payload_fingerprint='f'*64,
                state='ready', binding_version=uuid.uuid4())
            old.get_model('whatsapp_routing', 'WhatsAppSenderWatermark').objects.create(
                endpoint_id=endpoint.pk, phone_number_id='12345', customer_hash='c'*64, provider_timestamp=1234567890)
            MigrationExecutor(connection).migrate(latest)
            new = MigrationExecutor(connection).loader.project_state(latest).apps
            saved = new.get_model('whatsapp_routing', 'WhatsAppInboundEvent').objects.get(pk=event.pk)
            self.assertEqual(saved.payload_encrypted, 'retained-payload')
            self.assertEqual(saved.state, 'ready')
            self.assertEqual(new.get_model('whatsapp_routing', 'WhatsAppSenderWatermark').objects.get().provider_timestamp, 1234567890)
            self.assertEqual(new.get_model('whatsapp_routing', 'TenantWhatsAppEntryRoute').objects.get(pk=route.pk).reminder_preferences, {})
            for name in ('WhatsAppConversation', 'WhatsAppOrder', 'WhatsAppOutbound', 'WhatsAppProcessedEvent'):
                self.assertFalse(new.get_model('whatsapp_routing', name).objects.exists())
        finally:
            MigrationExecutor(connection).migrate(latest)
