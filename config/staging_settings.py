"""Production-like isolation for the operator-run VPS rehearsal."""
from .production_settings import *  # noqa: F403
from .production_settings import config
from django.core.exceptions import ImproperlyConfigured

STAGING_MODE = True
if not DATABASES['default']['NAME'].endswith('_staging'):
    raise ImproperlyConfigured('Staging requires a separate database ending in _staging.')
if not REDIS_URL.rstrip('/').endswith('/9'):
    raise ImproperlyConfigured('Staging requires reserved Redis database 9.')
CACHES['default']['KEY_PREFIX'] = 'yarotech-radius-staging'
EMAIL_BACKEND = 'django.core.mail.backends.filebased.EmailBackend'
EMAIL_FILE_PATH = '/var/lib/yarotech-radius-staging/mail'
REGISTRATION_EMAIL_BACKEND = EMAIL_BACKEND
RESEND_API_KEY = ''
STAGING_WHATSAPP_RECIPIENTS = config('STAGING_WHATSAPP_RECIPIENTS', default='', cast=Csv())
# Loopback FreeRADIUS calls bypass the public HTTPS listener but still require the shared token.
SECURE_REDIRECT_EXEMPT = [r'^health/', r'^api/v1/radius/']
