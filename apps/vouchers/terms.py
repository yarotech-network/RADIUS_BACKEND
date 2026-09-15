"""Server-owned issued terms. Duration is enforced in whole seconds."""
from decimal import Decimal, ROUND_HALF_UP
from django.core.exceptions import ValidationError
from django.db import transaction


def duration_seconds(hours):
    seconds = int((Decimal(str(hours)) * 3600).to_integral_value(rounding=ROUND_HALF_UP))
    if not 1 <= seconds <= 2147483647:
        raise ValidationError("Duration must be between one second and 2147483647 seconds.")
    return seconds


def snapshot_plan(plan, device_limit=1):
    from .code_formats import resolved_format
    if type(device_limit) is not int or not 1 <= device_limit <= 10:
        raise ValidationError('Device limit must be between 1 and 10.')
    total = plan.price * device_limit
    if total > 2147483647:
        raise ValidationError('The selected device total exceeds the supported purchase amount.')
    hours = Decimal(str(plan.duration_hours))
    return {
        'version': 3, 'tenant_id': plan.tenant_id, 'plan_id': plan.pk,
        'base_price': plan.price, 'total_price': total, 'currency': 'NGN',
        'voucher_code_format': resolved_format(plan), 'voucher_prefix': plan.voucher_prefix,
        'name': plan.name, 'price': total,
        'duration_hours': int(hours) if hours == hours.to_integral_value() else float(hours), 'duration_seconds': duration_seconds(hours),
        'data_limit': plan.data_limit, 'rate_limit': plan.rate_limit or '',
        'radius_rate_limit': plan.rate_limit or '', 'device_limit': device_limit,
    }


def resolved_terms(voucher):
    if voucher.purchased_terms is not None:
        terms = dict(voucher.purchased_terms)
        if 'duration_seconds' not in terms:
            terms['duration_seconds'] = duration_seconds(terms['duration_hours'])
        terms.setdefault('device_limit', voucher.device_limit)
        if voucher.issued_duration_seconds is not None:
            terms['duration_seconds'] = voucher.issued_duration_seconds
        return terms
    return historical_terms(voucher)


def historical_terms(voucher):
    from .models import Radcheck, Radreply
    checks = dict(Radcheck.objects.filter(username=voucher.username).values_list('attribute', 'value'))
    seconds = voucher.issued_duration_seconds
    if seconds is None and voucher.activated_at and voucher.expires_at:
        seconds = int((voucher.expires_at - voucher.activated_at).total_seconds())
    if seconds is None:
        raw = checks.get('Max-Days') or checks.get('Session-Timeout')
        if raw and str(raw).isdigit():
            seconds = int(raw)
    if seconds is None or seconds <= 0:
        raise ValidationError('Issued duration is unknown. Reconcile this voucher before editing its plan or activating it.')
    terms = snapshot_plan(voucher.plan)
    terms.update(version=2, device_limit=voucher.device_limit)
    for field in ("base_price", "total_price", "currency"):
        terms.pop(field, None)
    terms.update(duration_seconds=seconds, duration_hours=seconds / 3600)
    terms['radius_rate_limit'] = Radreply.objects.filter(username=voucher.username,
        attribute='Mikrotik-Rate-Limit').values_list('value', flat=True).first() or voucher.rate_limit_snapshot or ''
    terms['rate_limit'] = terms['radius_rate_limit']
    raw_cap = checks.get('Max-Total-Octets')
    if raw_cap and str(raw_cap).isdigit():
        terms['data_limit'] = int(raw_cap) // (1024 * 1024)
    elif checks:
        terms['data_limit'] = 0
    payment = getattr(voucher, 'payment', None)
    allocation = getattr(voucher, 'agent_allocation', None)
    if payment:
        terms['price'] = payment.amount
    elif allocation:
        terms['price'] = allocation.amount_charged
    terms.pop('voucher_code_format', None)
    terms.pop('voucher_prefix', None)
    terms['provenance'] = 'legacy_issued_duration_and_available_evidence'
    return terms


@transaction.atomic
def freeze_plan_contracts(plan):
    """Caller holds the plan lock; no RADIUS writes or expiry resets here."""
    from .models import Voucher
    if plan.paymenttransaction_set.filter(purchased_terms__isnull=True, voucher__isnull=True).exists():
        raise ValidationError('An older unfulfilled order has no saved terms. Reconcile it before editing or archiving this plan.')
    for voucher in Voucher.objects.select_for_update().filter(plan=plan, purchased_terms__isnull=True).iterator():
        voucher.plan = plan
        terms = historical_terms(voucher)
        Voucher.objects.filter(pk=voucher.pk, purchased_terms__isnull=True).update(
            purchased_terms=terms, issued_duration_seconds=terms['duration_seconds'])


def validate_reserved_price(terms):
    """Version-2 historical orders retain their existing price semantics."""
    if terms.get('version') != 3:
        return
    base, count, total = (terms.get(key) for key in ('base_price', 'device_limit', 'total_price'))
    if (any(type(value) is not int for value in (base, count, total)) or
            not 1 <= count <= 10 or base < 0 or total != base * count or
            total > 2147483647 or type(terms.get('price')) is not int or terms.get('price') != total or terms.get('currency') != 'NGN'):
        raise ValueError('Reserved purchase terms are inconsistent.')
