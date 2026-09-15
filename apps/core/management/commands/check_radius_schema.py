"""Read-only check of the unmanaged RADIUS columns consumed by Django."""
import json
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from apps.vouchers.models import Radcheck, Radreply, Radacct, Radpostauth


class Command(BaseCommand):
    help = 'Check RADIUS table/column compatibility without reading credentials or changing schema.'

    def handle(self, *args, **options):
        missing = {}
        with connection.cursor() as cursor:
            tables = set(connection.introspection.table_names(cursor))
            for model in (Radcheck, Radreply, Radacct, Radpostauth):
                table = model._meta.db_table
                expected = {field.column for field in model._meta.concrete_fields}
                actual = {field.name for field in connection.introspection.get_table_description(cursor, table)} if table in tables else set()
                if expected - actual:
                    missing[table] = sorted(expected - actual)
        if missing:
            raise CommandError('Missing RADIUS columns: '+json.dumps(missing, sort_keys=True))
        self.stdout.write('RADIUS column names match. Query semantics, data ownership and real accounting remain separate acceptance checks.')
