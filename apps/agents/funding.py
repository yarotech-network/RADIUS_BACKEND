"""Recover a known wallet top-up without initializing another charge."""
from django.db import transaction
from apps.payments.services import get_paystack_service
from .models import AgentWalletFundingPayment
from .services import AgentService
from .funding_terms import funding_total


class FundingVerificationUnavailable(Exception):
    pass


class FundingVerificationMismatch(Exception):
    pass


def verify_wallet_funding(payment):
    # Reload: another delivery may have completed since the caller read the row.
    payment = AgentWalletFundingPayment.objects.select_related('wallet__agent__tenant').get(pk=payment.pk)
    if payment.status == 'success':
        return payment
    try:
        result = get_paystack_service(payment.wallet.agent.tenant).verify_transaction(payment.reference)
    except Exception as exc:
        raise FundingVerificationUnavailable() from exc
    data = result.get('data') if isinstance(result, dict) else None
    if not isinstance(data, dict):
        raise FundingVerificationUnavailable()
    try:
        expected = funding_total(payment)
    except ValueError as exc:
        raise FundingVerificationMismatch() from exc
    if (data.get('reference') != payment.reference or data.get('currency') != 'NGN'
            or type(data.get('amount')) is not int or data['amount'] != expected):
        raise FundingVerificationMismatch()
    provider_status = data.get('status')
    if provider_status == 'success':
        try:
            AgentService.complete_wallet_funding(payment, data)
        except ValueError as exc:
            raise FundingVerificationMismatch() from exc
    elif provider_status in {'failed', 'abandoned', 'reversed'}:
        with transaction.atomic():
            locked = AgentWalletFundingPayment.objects.select_for_update().get(pk=payment.pk)
            if locked.status != 'success':
                locked.status = 'failed'
                locked.save(update_fields=['status'])
    payment.refresh_from_db()
    return payment
