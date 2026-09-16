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
# Explicit operator opt-in; keep the staging database and consumer safeguards.
STAGING_PROVIDER_TESTING = config('STAGING_PROVIDER_TESTING', default=False, cast=bool)
STAGING_ROUTER_TESTING = config('STAGING_ROUTER_TESTING', default=False, cast=bool)
if RADIUS_REST_ENABLED and not STAGING_ROUTER_TESTING:
    raise ImproperlyConfigured('Staging RADIUS requires STAGING_ROUTER_TESTING.')
if STAGING_ROUTER_TESTING:
    # This opt-in is specifically for the isolated VPS rehearsal, not live wg0.
    expected = {
        'WG_INTERFACE': 'wgstage', 'WG_MANAGED_SUBNET': '10.101.100.0/24',
        'WG_ENDPOINT_PORT': 51821, 'RADIUS_SERVER_WG_IP': '10.101.100.1',
        'ROUTER_RADIUS_AUTH_PORT': 18121, 'ROUTER_RADIUS_ACCT_PORT': 18131,
        'RADIUS_AUTH_HOST': '10.101.100.1', 'RADIUS_AUTH_PORT': 18121,
    }
    for name, value in expected.items():
        if globals().get(name) != value:
            raise ImproperlyConfigured(f'Router testing requires isolated {name}.')
    database = DATABASES['default']
    if (database.get('NAME') != 'yarotech_radius_staging'
            or database.get('USER') != 'yarotech_radius_staging'
            or database.get('HOST') != '127.0.0.1'
            or str(database.get('PORT')) != '5433'):
        raise ImproperlyConfigured('Router testing requires the isolated staging database.')
    if not RADIUS_REST_ENABLED or len(globals().get('RADIUS_REST_TOKEN', '')) < 32:
        raise ImproperlyConfigured('Router testing requires enabled REST with a private token.')
    if any((IOT_PUBLIC_PURCHASE_ENABLED, WHATSAPP_WEBHOOK_ENABLED,
            WHATSAPP_CONSUMER_ENABLED, WHATSAPP_SEND_ENABLED)):
        raise ImproperlyConfigured('Router testing must retain IoT purchase and WhatsApp gates.')
if STAGING_PROVIDER_TESTING:
    from django.core.validators import validate_email
    from django.core.exceptions import ValidationError
    from email.utils import parseaddr

    if not PAYSTACK_SECRET_KEY.startswith('sk_test_') or not PAYSTACK_PUBLIC_KEY.startswith('pk_test_'):
        raise ImproperlyConfigured('Provider testing requires Paystack test secret and public keys.')
    RESEND_API_KEY = config('RESEND_API_KEY', default='')
    if not RESEND_API_KEY.startswith('re_'):
        raise ImproperlyConfigured('Provider testing requires a Resend API key.')
    try:
        sender_address = parseaddr(DEFAULT_FROM_EMAIL)[1]
        validate_email(sender_address)
    except (ValidationError, ValueError):
        raise ImproperlyConfigured('Set DEFAULT_FROM_EMAIL to your verified Resend sender.') from None
    if sender_address.rsplit('@', 1)[1].lower() in ('example.com', 'yarotech.local'):
        raise ImproperlyConfigured('Replace the example Resend sender before provider testing.')
    if any((IOT_PUBLIC_PURCHASE_ENABLED,
            WHATSAPP_WEBHOOK_ENABLED, WHATSAPP_CONSUMER_ENABLED, WHATSAPP_SEND_ENABLED)):
        raise ImproperlyConfigured('Provider testing must retain the initial router, IoT and WhatsApp gates.')
    # Existing OTP/identity delivery selects Resend when this override is empty.
    REGISTRATION_EMAIL_BACKEND = ''
STAGING_WHATSAPP_RECIPIENTS = config('STAGING_WHATSAPP_RECIPIENTS', default='', cast=Csv())
# Loopback FreeRADIUS calls bypass the public HTTPS listener but still require the shared token.
SECURE_REDIRECT_EXEMPT = [r'^health/', r'^api/v1/radius/']
