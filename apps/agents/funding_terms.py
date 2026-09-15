from decimal import Decimal, ROUND_HALF_UP


def funding_policy(setting):
    return {'minimum': 50000, 'maximum': setting.max_funding_amount if setting else 100000,
            'fee_percent': str(setting.agent_funding_fee_percent) if setting else '0.00',
            'flat_fee': setting.agent_funding_flat_fee if setting else 0, 'currency': 'NGN'}


def reserve_funding_terms(amount, policy):
    percent = Decimal(policy['fee_percent'])
    flat = policy['flat_fee']
    if (type(amount) is not int or not policy['minimum'] <= amount <= policy['maximum']
            or not percent.is_finite() or not 0 <= percent <= 100
            or type(flat) is not int or flat < 0):
        raise ValueError('Invalid funding amount or fee policy.')
    fee = int((Decimal(amount) * percent / 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP)) + flat
    if amount + fee > 2147483647:
        raise ValueError('The funding total exceeds the supported amount.')
    return {'version': 1, 'credit': amount, 'fee': fee, 'total': amount + fee,
            'fee_percent': str(percent), 'flat_fee': flat, 'currency': 'NGN'}


def funding_total(payment):
    terms = payment.funding_terms
    if terms is None:
        return payment.amount
    if (not isinstance(terms, dict) or terms.get('version') != 1 or terms.get('currency') != 'NGN'
            or any(type(terms.get(k)) is not int for k in ('credit', 'fee', 'total'))
            or terms['credit'] != payment.amount or terms['fee'] < 0
            or terms['total'] != terms['credit'] + terms['fee'] or not 0 < terms['total'] <= 2147483647):
        raise ValueError('Saved funding terms are inconsistent.')
    return terms['total']
