from datetime import timedelta
from importlib import import_module
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class IoTMigrationTests(TransactionTestCase):
    def test_populated_registration_retains_identity_deadline_and_flags(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        before = [node for node in latest if node[0] != 'iot_devices'] + [('iot_devices', '0002_macdevice_access_type_macdevice_description_and_more')]
        try:
            executor.migrate(before)
            old = executor.loader.project_state(before).apps
            tenant = old.get_model('tenants', 'Tenant').objects.create(name='Retained', slug='iot-migration')
            plan = old.get_model('vouchers', 'InternetPlan').objects.create(tenant_id=tenant.pk, name='Legacy', price=500, duration_hours=24)
            expiry = timezone.now() - timedelta(days=1)
            device = old.get_model('iot_devices', 'MacDevice').objects.create(tenant_id=tenant.pk, plan_id=plan.pk,
                device_name='Original', mac_address='aabb.ccdd.eeff', is_active=False, expires_at=expiry, description='Retain', vlan_id=42)
            MigrationExecutor(connection).migrate(latest)
            new = MigrationExecutor(connection).loader.project_state(latest).apps
            saved = new.get_model('iot_devices', 'MacDevice').objects.get(pk=device.pk)
            self.assertEqual(saved.mac_address, 'aabb.ccdd.eeff')
            self.assertEqual(saved.mac_address_compact, 'AABBCCDDEEFF')
            self.assertEqual(saved.expires_at, expiry)
            self.assertEqual(saved.created_at, device.created_at)
            self.assertFalse(saved.is_active)
            self.assertEqual(saved.status, 'suspended')
            self.assertEqual(saved.plan_id, plan.pk)
            self.assertEqual(saved.description, 'Retain')
            self.assertEqual(saved.vlan_id, 42)
            self.assertIsNone(saved.issued_terms)
            self.assertIsNone(saved.legacy_uuid)
            self.assertIsNone(saved.deleted_at)
            self.assertEqual(saved.speed_limit, '')
            self.assertEqual(saved.version, 1)
        finally:
            MigrationExecutor(connection).migrate(latest)

    def test_preflight_rejects_invalid_or_conflicting_history_without_partial_backfill(self):
        executor = MigrationExecutor(connection)
        apps = executor.loader.project_state(executor.loader.graph.leaf_nodes()).apps
        tenant = apps.get_model('tenants', 'Tenant').objects.create(name='Collision', slug='iot-collision')
        Device = apps.get_model('iot_devices', 'MacDevice')
        first = Device.objects.create(tenant_id=tenant.pk, mac_address='AA:BB:CC:DD:EE:FF')
        second = Device.objects.create(tenant_id=tenant.pk, mac_address='aabb.ccdd.eeff')
        migration = import_module('apps.iot_devices.migrations.0003_devicerenewal_alter_macdevice_options_and_more')
        from types import SimpleNamespace
        for address in ('aabb.ccdd.eeff', '00:00:00:00:00:00'):
            Device.objects.filter(pk=second.pk).update(mac_address=address)
            with self.assertRaises(RuntimeError):
                with transaction.atomic():
                    migration.preserve_registrations(apps, SimpleNamespace(connection=connection))
            first.refresh_from_db()
            self.assertEqual(first.mac_address_compact, '')
            self.assertEqual(first.status, '')
