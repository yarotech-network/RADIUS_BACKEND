"""Load with the LEGACY checkout on sys.path, for read-only restored-source export."""
import os
from config.settings import *  # noqa: F403
from django.core.exceptions import ImproperlyConfigured

source_name = os.environ.get('SOURCE_EXPORT_DB_NAME', '')
if not source_name.endswith('_staging'):
    raise ImproperlyConfigured('SOURCE_EXPORT_DB_NAME must identify a restored staging database.')
DATABASES = {'default': {
    'ENGINE':'django.db.backends.postgresql',
    'NAME':source_name,
    'USER':os.environ['SOURCE_EXPORT_DB_USER'],
    'PASSWORD':os.environ['SOURCE_EXPORT_DB_PASSWORD'],
    'HOST':'127.0.0.1',
    'PORT':os.environ.get('SOURCE_EXPORT_DB_PORT','5432'),
    'OPTIONS':{'options':'-c default_transaction_read_only=on'},
}}
EMAIL_BACKEND = 'django.core.mail.backends.dummy.EmailBackend'
