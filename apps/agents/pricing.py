from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def agent_price(retail, rate):
    """Per-voucher margin retained by the agent, never a second wallet credit."""
    try:
        percent = Decimal(str(rate))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError('Invalid agent commission rate.') from exc
    if not percent.is_finite() or not 0 <= percent <= 100:
        raise ValueError('Agent commission must be between 0 and 100 percent.')
    if type(retail) is not int or not 0 <= retail <= 2147483647:
        raise ValueError('Invalid retail amount.')
    cost = int((Decimal(retail) * (100 - percent) / 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    return {'agent_cost': cost, 'commission_amount': retail - cost, 'commission_rate': str(percent)}
