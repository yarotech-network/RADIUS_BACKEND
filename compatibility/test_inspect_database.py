import hashlib
import importlib.util
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

spec = importlib.util.spec_from_file_location('inventory', Path(__file__).with_name('inspect_database.py'))
inventory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inventory)


class InventoryTests(unittest.TestCase):
    def test_schema_counts_relationships_without_data_or_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'source #1.sqlite3'
            with closing(sqlite3.connect(path)) as connection, connection:
                connection.executescript('''
                    CREATE TABLE tenant (id INTEGER PRIMARY KEY);
                    CREATE TABLE account (id INTEGER PRIMARY KEY, tenant_id INTEGER REFERENCES tenant(id),
                        password TEXT DEFAULT 'secret-default-do-not-export', email TEXT UNIQUE);
                    CREATE TABLE django_migrations (app TEXT, name TEXT);
                    INSERT INTO tenant VALUES (1);
                    INSERT INTO account VALUES (1, 1, 'secret-value-do-not-export', 'person@example.invalid');
                    INSERT INTO django_migrations VALUES ('vouchers', '0055_archive_internet_plans');
                ''')
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            result = inventory.inspect_sqlite(path)
            self.assertEqual(result['tables']['account']['rows'], 1)
            self.assertEqual(result['tables']['account']['foreign_keys'][0]['target_table'], 'tenant')
            self.assertTrue(any(index['unique'] for index in result['tables']['account']['indexes']))
            self.assertEqual(result['applied_migrations'], [['vouchers', '0055_archive_internet_plans']])
            output = json.dumps(result)
            for secret in ('secret-value-do-not-export', 'secret-default-do-not-export', 'person@example.invalid'):
                self.assertNotIn(secret, output)
            self.assertEqual(before, hashlib.sha256(path.read_bytes()).hexdigest())

    def test_missing_source_is_not_created(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'missing.sqlite3'
            with self.assertRaises(FileNotFoundError):
                inventory.inspect_sqlite(path)
            self.assertFalse(path.exists())

    def test_identifiers_are_quoted_and_empty_database_is_honest(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'source.sqlite3'
            with closing(sqlite3.connect(path)) as connection, connection:
                connection.execute('CREATE TABLE "odd""table" ("a""b" TEXT)')
            result = inventory.inspect_sqlite(path)
            self.assertEqual(result['tables']['odd"table']['rows'], 0)
            self.assertEqual(result['tables']['odd"table']['columns'][0]['name'], 'a"b')
            self.assertEqual(result['applied_migrations'], [])


if __name__ == '__main__':
    unittest.main()
