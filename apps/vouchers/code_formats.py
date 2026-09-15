"""Format policy for future voucher issuance; existing credentials stay untouched."""
import secrets
import re
from django.core.exceptions import ValidationError
from django.db.models import Value, CharField
from django.db.models.functions import Replace, Lower

FORMAT_CHOICES = [('legacy', 'Readable mixed (existing)'), ('numeric', 'Numbers only'),
    ('alphabetic', 'Letters only'), ('alphanumeric', 'Letters and numbers')]
PLAN_FORMAT_CHOICES = [('tenant_default', 'Business default')] + FORMAT_CHOICES
LETTERS = 'ABCDEFGHJKLMNPQRSTUVWXYZ'
DIGITS = '23456789'
LEGACY_ALPHABET = 'ABCDEFGHJKMNPQRTUVWXYZ234678'


def generate_code(prefix='', code_format='legacy'):
    if code_format not in dict(FORMAT_CHOICES):
        raise ValidationError('Unsupported voucher code format.')
    pattern = '[A-Za-z0-9_-]+' if code_format == 'legacy' else '[A-Za-z0-9]+'
    if prefix and (len(prefix) > 10 or not re.fullmatch(pattern, prefix)):
        raise ValidationError('Prefix must contain at most 10 letters or numbers.')
    # Preserve previous prefix spelling for the explicit existing format.
    prefix = prefix if code_format == 'legacy' else prefix.upper()
    alphabet = {'legacy':LEGACY_ALPHABET, 'numeric':'0123456789', 'alphabetic':LETTERS,
        'alphanumeric':LETTERS+DIGITS}[code_format]
    length = 8 if code_format in ('legacy', 'numeric') else 6
    for _ in range(100):
        body = ''.join(secrets.choice(alphabet) for _ in range(length))
        if code_format != 'alphanumeric' or (any(c in LETTERS for c in body) and any(c in DIGITS for c in body)):
            return prefix+body
    raise ValidationError('Could not generate a voucher code. Retry the request.')


def resolved_format(plan):
    if plan.voucher_code_format != 'tenant_default':
        return plan.voucher_code_format
    from apps.tenants.models import TenantSetting
    return TenantSetting.objects.filter(tenant_id=plan.tenant_id).values_list('default_voucher_code_format', flat=True).first() or 'legacy'


def identity_exists(code):
    from .models import Voucher, Radcheck, Radreply
    from apps.customers.models import PPPoEService
    from apps.iot_devices.models import MacDevice
    if (Voucher.objects.annotate(identity=Lower("username")).filter(identity=code.lower()).exists() or
        Radcheck.objects.filter(username__iexact=code).exists() or
        Radreply.objects.filter(username__iexact=code).exists() or
        PPPoEService.objects.filter(username__iexact=code).exists()):
        return True
    if len(code) != 12:
        return False
    return MacDevice.objects.annotate(compact=Replace(Replace('mac_address',Value(':'),Value('')),Value('-'),Value(''), output_field=CharField())).filter(compact__iexact=code).exists()
