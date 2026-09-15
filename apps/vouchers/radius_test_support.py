"""Disposable unmanaged RADIUS tables for database-backed tests."""
from django.db import connection
from .models import Radcheck, Radreply


class RadiusTablesMixin:
    @classmethod
    def setUpClass(cls):
        cls.radius_created = []
        for model in (Radcheck, Radreply):
            if model._meta.db_table not in connection.introspection.table_names():
                with connection.schema_editor() as editor:
                    editor.create_model(model)
                cls.radius_created.append(model)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        for model in reversed(cls.radius_created):
            with connection.schema_editor() as editor:
                editor.delete_model(model)
