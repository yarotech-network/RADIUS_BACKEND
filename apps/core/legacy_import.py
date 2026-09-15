"""Reviewed, target-only import engine. Source archives are immutable input.

A reviewed plan supplies explicit model fields and source references. This deliberately
refuses to guess money conversions, account privileges, payment evidence or old keys.
"""
import hashlib
import json
from collections import Counter
from decimal import Decimal
from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.utils import timezone
from apps.routers.secret_store import secret_store
from .models import LegacyImportRun, LegacyRecord

ALLOWED_APPS = {'accounts','tenants','routers','vouchers','subscriptions','agents','customers','iot_devices','whatsapp_routing'}
# These are evidence tables, never runnable old jobs or financial balances.
ARCHIVE_TABLES = {'django_admin_log','django_migrations','django_content_type','auth_permission','auth_group','auth_group_permissions',
    'auth_user_groups','auth_user_user_permissions','vouchers_platformaccessaudit','vouchers_routerauditevent',
    'vouchers_routeronboardingcheck','vouchers_agentregistrationaudit','vouchers_financialactionaudit',
    'vouchers_macdeviceauditevent','vouchers_voucherdevicebindingaudit','vouchers_routerdeploymentlog'}


class ImportBlocked(Exception):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',',':'), default=str).encode()).hexdigest()


def read_archive(path):
    encoded = path.read_bytes()
    data = json.loads(encoded)
    if data.get('format') != 'yarotech-legacy-source-v1':
        raise ImportBlocked('Unsupported source format.')
    return data, hashlib.sha256(encoded).hexdigest()


def source_rows(archive):
    result = {}
    for table, definition in archive['tables'].items():
        for row in definition['rows']:
            key = table+':'+str(row[definition['pk']])
            if key in result:
                raise ImportBlocked('Duplicate source key: '+key)
            result[key] = row
    return result


def coverage(archive, plan, source_digest):
    rows = source_rows(archive)
    if plan.get('format') != 'yarotech-import-plan-v1' or plan.get('source_digest') != source_digest:
        raise ImportBlocked('Plan/source digest mismatch.')
    mapped = {record['source'] for record in plan.get('records', [])}
    archived = set()
    for item in plan.get('archive_only', []):
        if item['table'] not in ARCHIVE_TABLES or not item.get('reason'):
            raise ImportBlocked('Archive-only disposition is not allowed for '+item['table'])
        archived.update(key for key in rows if key.startswith(item['table']+':'))
    if mapped - set(rows):
        raise ImportBlocked('Plan references missing source records.')
    missing = Counter(key.split(':',1)[0] for key in set(rows) - mapped - archived)
    return {'source_rows':len(rows), 'planned_records':len(plan.get('records', [])),
        'unmapped_tables':dict(sorted(missing.items())), 'source_digest':source_digest, 'plan_digest':digest(plan)}


def draft_plan(archive, source_digest):
    # No literal credentials or business values are copied into a public report.
    return {'format':'yarotech-import-plan-v1', 'source_digest':source_digest,
        'records':[], 'archive_only':[{'table':table, 'reason':'Retain original evidence encrypted; do not replay.'}
            for table in archive['tables'] if table in ARCHIVE_TABLES],
        'reconciliation':[], 'unmapped_tables':{table:len(value['rows']) for table,value in archive['tables'].items() if table not in ARCHIVE_TABLES}}


def _value(value, source, created, source_cipher):
    if not isinstance(value, dict):
        return value
    if set(value) == {'$ref'}:
        if value['$ref'] not in created:
            raise KeyError(value['$ref'])
        return created[value['$ref']].pk
    if set(value) == {'$source'}:
        return source[value['$source']]
    if set(value) == {'$ngn_to_kobo'}:
        amount = Decimal(str(source[value['$ngn_to_kobo']])) * 100
        if not amount.is_finite() or amount != amount.to_integral_value() or amount < 0:
            raise ImportBlocked('Money cannot be represented exactly in kobo.')
        return int(amount)
    if set(value) == {'$reencrypt'}:
        ciphertext = source[value['$reencrypt']]
        if not ciphertext:
            return ''
        if not source_cipher or not ciphertext.startswith('enc:v1:'):
            raise ImportBlocked('A source encryption key and recognized encrypted value are required.')
        return secret_store.encrypt(source_cipher.decrypt(ciphertext[7:].encode()).decode())
    if any(str(key).startswith('$') for key in value):
        raise ImportBlocked('Unknown field transformation.')
    return value  # Explicit JSON snapshot; never evaluated as code.


def _validate_links(obj):
    tenant_id = getattr(obj, 'tenant_id', None)
    for field in obj._meta.fields:
        if field.many_to_one or field.one_to_one:
            if getattr(obj, field.attname) is None or field.name in ('tenant','actor','user','created_by'):
                continue
            related = getattr(obj, field.name)
            if tenant_id and getattr(related, 'tenant_id', tenant_id) != tenant_id:
                raise ImportBlocked('Cross-tenant relation on '+obj._meta.label+'.'+field.name)


def _reconcile(archive, plan, created):
    # Each declared check must compare exact source and imported values, not display strings.
    reports = []
    for check in plan.get('reconciliation', []):
        table, column = check['source_table'], check['source_column']
        source_total = sum((Decimal(str(row[column] or 0)) for row in archive['tables'][table]['rows']), Decimal(0))
        source_total *= Decimal(str(check.get('multiplier', 1)))
        targets = [obj for obj in created.values() if obj._meta.label_lower == check['target_model'].lower()]
        target_total = sum((Decimal(str(getattr(obj, check['target_field']) or 0)) for obj in targets), Decimal(0))
        if source_total != target_total:
            raise ImportBlocked('Reconciliation mismatch: '+table+'.'+column)
        reports.append({'source_table':table, 'source_column':column, 'matched':True, 'count':len(targets)})
    return reports


def execute_import(archive, plan, source_digest, *, apply=False, source_cipher=None):
    name = str(connection.settings_dict['NAME'])
    if not (name.endswith('_staging') or name.startswith('test_yarotech_')):
        raise ImportBlocked('Import is restricted to a staging or disposable test database.')
    if getattr(settings, 'WHATSAPP_CONSUMER_ENABLED', False) or getattr(settings, 'WHATSAPP_SEND_ENABLED', False):
        raise ImportBlocked('Disable message consumers and sends before importing.')
    if getattr(settings, 'RADIUS_REST_ENABLED', False):
        raise ImportBlocked('Disable RADIUS access while importing.')
    report = coverage(archive, plan, source_digest)
    if report['unmapped_tables']:
        raise ImportBlocked('Unmapped source tables: '+', '.join(report['unmapped_tables']))
    rows = source_rows(archive)
    financial_columns = {'vouchers_agentwallet':'balance_kobo', 'vouchers_agentwallettransaction':'amount_kobo',
        'vouchers_agentcreditaccount':'outstanding_kobo', 'vouchers_agentcreditledger':'amount_kobo',
        'vouchers_paymenttransaction':'amount', 'vouchers_subscriptionpayment':'amount_kobo',
        'vouchers_agentwalletfundingpayment':'requested_wallet_credit_kobo'}
    checked = {(item['source_table'],item['source_column']) for item in plan.get('reconciliation', [])}
    for table,column in financial_columns.items():
        if archive['tables'].get(table, {}).get('rows') and (table,column) not in checked:
            raise ImportBlocked('A financial reconciliation check is required for '+table+'.'+column)
    with transaction.atomic():
        if connection.vendor == 'postgresql':
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(hashtext('yarotech_import_v1'))")
        prior = LegacyImportRun.objects.filter(source_digest=source_digest).first()
        if prior:
            if prior.plan_digest != report['plan_digest'] or not prior.completed_at:
                raise ImportBlocked('Import identity requires reconciliation.')
            return {**prior.summary, 'already_imported':True}
        # Do not merge a replacement snapshot into a database accepting real traffic.
        if LegacyImportRun.objects.exists() or apps.get_model('accounts','User').objects.exists() or apps.get_model('tenants','Tenant').objects.exists():
            raise ImportBlocked('Use a fresh staging database for a full replacement import.')
        run = LegacyImportRun.objects.create(source_digest=source_digest, plan_digest=report['plan_digest'])
        created, by_source = {}, {}
        pending = list(plan.get('records', []))
        while pending:
            following = []
            for record in pending:
                key = record.get('key', record['source'])
                if key in created:
                    raise ImportBlocked('Duplicate target key: '+key)
                model = apps.get_model(record['model'])
                if model._meta.app_label not in ALLOWED_APPS or not model._meta.managed:
                    raise ImportBlocked('Model is not an import target: '+record['model'])
                fields = {field.attname:field for field in model._meta.concrete_fields}
                if set(record['fields']) - set(fields) or model._meta.pk.attname in record['fields']:
                    raise ImportBlocked('Unknown field or manually assigned target ID: '+key)
                source = rows[record['source']]
                try:
                    values = {name:_value(value, source, created, source_cipher) for name,value in record['fields'].items()}
                except KeyError:
                    following.append(record)
                    continue
                values = {name:fields[name].to_python(value) for name,value in values.items()}
                if model._meta.label_lower == 'accounts.user':
                    required = {'password','is_active','is_staff','is_superuser','is_platform_admin','email_verified_at'}
                    if not required.issubset(values):
                        raise ImportBlocked('Explicit account privilege and verification mapping required: '+key)
                if model._meta.label_lower == 'iot_devices.macdevice':
                    values['mac_address'] = model.normalize_mac(values['mac_address'])
                    values['mac_address_compact'] = values['mac_address'].replace(':','')
                obj = model(**values)
                try:
                    obj.full_clean(validate_unique=False, validate_constraints=False)
                    _validate_links(obj)
                except ValidationError:
                    raise ImportBlocked('Target validation failed for '+key+'; inspect its mapping privately.')
                # Bulk insertion deliberately bypasses model services and signals (no trial, charge, message or provisioning).
                model.objects.bulk_create([obj])
                timestamps = {name:value for name,value in values.items() if getattr(fields[name], 'auto_now', False) or getattr(fields[name], 'auto_now_add', False)}
                if timestamps:
                    model.objects.filter(pk=obj.pk).update(**timestamps)
                    for name,value in timestamps.items():
                        setattr(obj,name,value)
                created[key] = obj
                by_source.setdefault(record['source'], []).append({'model':model._meta.label_lower, 'pk':str(obj.pk)})
            if len(following) == len(pending):
                raise ImportBlocked('Unresolved references or dependency cycle in reviewed plan.')
            pending = following
        report['reconciliation'] = _reconcile(archive, plan, created)
        for key,row in rows.items():
            LegacyRecord.objects.create(run=run, source_key=key, source_digest=digest(row),
                payload_encrypted=secret_store.encrypt(json.dumps(row, sort_keys=True)), targets=by_source.get(key, []))
        report['imported_by_model'] = dict(Counter(obj._meta.label_lower for obj in created.values()))
        report['applied'] = bool(apply)
        run.summary, run.completed_at = report, timezone.now()
        run.save(update_fields=['summary','completed_at'])
        if not apply:
            transaction.set_rollback(True)
        return report
