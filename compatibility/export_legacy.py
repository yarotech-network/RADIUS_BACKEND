"""Run with the legacy Django environment; export only, no ORM saves or services.

YAROTECH_EXPORT_PATH=/private/path/source.json ./venv/bin/python manage.py shell -c "exec(open('/path/export_legacy.py').read())"
"""
import hashlib
import json
import os
from pathlib import Path
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, transaction


def export_snapshot(destination):
    destination = Path(destination).resolve()
    if destination.exists():
        raise RuntimeError('Refusing to overwrite an existing source archive.')
    if connection.vendor != 'postgresql':
        raise RuntimeError('Run this exporter against the restored PostgreSQL source.')
    if not str(connection.settings_dict['NAME']).endswith('_staging'):
        raise RuntimeError('Export only from a restored database ending in _staging.')
    tables = {}
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
            cursor.execute("SET LOCAL statement_timeout = '120s'")
            cursor.execute("SET LOCAL lock_timeout = '5s'")
            names = connection.introspection.table_names(cursor)
            # Export every discovered table except ephemeral browser sessions. Unknown
            # business tables must reach coverage rather than disappear through a prefix filter.
            selected = [name for name in names if name != 'django_session']
            for name in sorted(selected):
                columns = [column.name for column in connection.introspection.get_table_description(cursor, name)]
                constraints = connection.introspection.get_constraints(cursor, name)
                pk = next((item['columns'] for item in constraints.values() if item.get('primary_key')), [])
                if len(pk) != 1:
                    raise RuntimeError('Source table needs an explicit stable key: '+name)
                quoted = connection.ops.quote_name
                cursor.execute('SELECT '+','.join(quoted(column) for column in columns)+' FROM '+quoted(name)+' ORDER BY '+quoted(pk[0]))
                rows = []
                while True:
                    batch = cursor.fetchmany(1000)
                    if not batch:
                        break
                    rows.extend(dict(zip(columns, row)) for row in batch)
                tables[name] = {'pk':pk[0], 'columns':columns, 'rows':rows}
    archive = {'format':'yarotech-legacy-source-v1', 'tables':tables,
        'excluded_tables': sorted(set(names) - set(selected))}
    encoded = json.dumps(archive, cls=DjangoJSONEncoder, sort_keys=True, separators=(',',':')).encode()
    fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'wb') as output:
        output.write(encoded)
    print(json.dumps({'archive_sha256':hashlib.sha256(encoded).hexdigest(), 'counts':{name:len(table['rows']) for name,table in tables.items()}}))


if os.environ.get('YAROTECH_EXPORT_PATH'):
    export_snapshot(os.environ['YAROTECH_EXPORT_PATH'])
else:
    raise RuntimeError('Set YAROTECH_EXPORT_PATH to a new private archive path.')
