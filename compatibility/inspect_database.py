"""Read-only schema inventory. No row contents, defaults, or credentials are exported.

SQLite: python compatibility/inspect_database.py --sqlite PATH
Django shell: runpy.run_path(PATH)['print_django_inventory']()
"""
import argparse
import json
import sqlite3
from pathlib import Path


def _quoted(identifier):
    return '"' + identifier.replace('"', '""') + '"'


def inspect_sqlite(path):
    # resolve(strict=True) and mode=ro prevent accidentally creating a database.
    source = Path(path).resolve(strict=True)
    connection = sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)
    try:
        connection.execute('PRAGMA query_only=ON')
        connection.execute('BEGIN')
        tables = {}
        for (name,) in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall():
            columns = [
                {'name': row[1], 'type': row[2], 'not_null': bool(row[3]),
                 'primary_key_position': row[5]}
                for row in connection.execute('PRAGMA table_info(' + _quoted(name) + ')')
            ]
            foreign_keys = [
                {'column': row[3], 'target_table': row[2], 'target_column': row[4],
                 'on_update': row[5], 'on_delete': row[6]}
                for row in connection.execute('PRAGMA foreign_key_list(' + _quoted(name) + ')')
            ]
            indexes = []
            for index in connection.execute('PRAGMA index_list(' + _quoted(name) + ')').fetchall():
                indexes.append({
                    'name': index[1], 'unique': bool(index[2]), 'partial': bool(index[4]),
                    'columns': [row[2] for row in connection.execute(
                        'PRAGMA index_info(' + _quoted(index[1]) + ')')],
                })
            tables[name] = {
                'rows': connection.execute('SELECT COUNT(*) FROM ' + _quoted(name)).fetchone()[0],
                'columns': columns, 'foreign_keys': foreign_keys, 'indexes': indexes,
            }
        migrations = []
        if 'django_migrations' in tables:
            migrations = [list(row) for row in connection.execute(
                'SELECT app, name FROM django_migrations ORDER BY app, name')]
        return {'format_version': 1, 'engine': 'sqlite', 'tables': tables,
                'applied_migrations': migrations,
                'limitations': ['Local snapshot only; not production freshness or PostgreSQL proof.',
                                'Expression/partial index definitions and CHECK expressions are not exported.',
                                'Counts do not verify field values, business rules, or transfer compatibility.']}
    finally:
        connection.rollback()
        connection.close()


def inspect_django():
    """Run in the OLD project's configured Django shell, on PostgreSQL only.

    All inspection queries share a read-only snapshot. Per-statement timeout
    prevents one large accounting table from holding the snapshot indefinitely.
    Failure aborts the inventory rather than reporting incomplete success.
    """
    from django.db import connection, transaction

    if connection.vendor != 'postgresql':
        raise RuntimeError('Use --sqlite for SQLite; the Django collector requires PostgreSQL.')
    if connection.in_atomic_block or not connection.get_autocommit():
        raise RuntimeError('Run from a fresh Django shell outside an existing transaction.')
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
            cursor.execute("SET LOCAL statement_timeout = '15s'")
            cursor.execute("SET LOCAL lock_timeout = '2s'")
            cursor.execute('SHOW server_version')
            version = cursor.fetchone()[0]
            tables = {}
            for name in sorted(connection.introspection.table_names(cursor)):
                columns = connection.introspection.get_table_description(cursor, name)
                constraints = connection.introspection.get_constraints(cursor, name)
                cursor.execute('SELECT COUNT(*) FROM ' + connection.ops.quote_name(name))
                tables[name] = {
                    'rows': cursor.fetchone()[0],
                    'columns': [
                        {'name': column.name, 'type_code': column.type_code,
                         'null_ok': column.null_ok, 'internal_size': column.internal_size,
                         'precision': column.precision, 'scale': column.scale}
                        for column in columns
                    ],
                    # Exclude raw SQL/defaults and CHECK expressions; retain relational metadata.
                    'constraints': {key: {field: value.get(field) for field in (
                        'columns', 'primary_key', 'unique', 'foreign_key', 'check', 'index'
                    )} for key, value in constraints.items()},
                }
            migrations = []
            if 'django_migrations' in tables:
                cursor.execute('SELECT app, name FROM django_migrations ORDER BY app, name')
                migrations = [list(row) for row in cursor.fetchall()]
    return {'format_version': 1, 'engine': 'postgresql', 'server_version': version,
            'tables': tables, 'applied_migrations': migrations,
            'limitations': ['Schema/count inventory only; no customer values or credentials exported.',
                            'Not a backup, data transfer, or proof of application compatibility.']}


def print_django_inventory():
    print(json.dumps(inspect_django(), indent=2, sort_keys=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sqlite', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(inspect_sqlite(args.sqlite), indent=2, sort_keys=True))
